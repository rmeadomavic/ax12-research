#!/usr/bin/env python3
"""
UMBUS Server — Reusable service layer for RadioMaster AX12 tools.

Reads UMBUS frames from /dev/ttyS0, broadcasts via SSE, and exposes a
REST API for state queries and config persistence. Other tools import
this module and extend it with their own routes and logic.

Usage as standalone (live monitor):
    su 0 python3 tools/umbus_server.py
    su 0 python3 tools/umbus_server.py --demo

Usage as library:
    from umbus_server import UMBUSService
    svc = UMBUSService(port=8081)
    svc.add_route('POST', '/api/my-action', my_handler)
    svc.set_html(my_html_string)
    svc.run()
"""

import os, sys, json, time, threading, queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import deque
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import UMBUSDecoder, FrameType

SERIAL_PORT = '/dev/ttyS0'
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'docs', 'control-map.json')


class UMBUSService:
    """Core service: serial reader, SSE broadcaster, HTTP server, config store."""

    def __init__(self, port=8081, demo=False):
        self.port = port
        self.demo = demo
        self.sse_queues = []
        self.sse_lock = threading.Lock()
        self.custom_routes = {}  # {('METHOD', '/path'): handler_fn}
        self.html = '<html><body><h1>UMBUS Server</h1><p>No UI configured.</p></body></html>'
        self.running = True

        # Live state
        self.state = {
            'gimbals': [0, 0, 0, 0],
            'channels': [32768] * 33,
            'frame_count': 0,
            'fps': 0.0,
            'connected': False,
            'demo': demo,
        }

        # Config (persisted to disk)
        self.config = self._load_config()

        # Frame callbacks: list of fn(frame_type, gimbals, channels)
        self.frame_callbacks = []

    # --- Config persistence ---

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
                print(f"Loaded config: {CONFIG_PATH} (phase: {cfg.get('phase', '?')})")
                return cfg
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: could not load config: {e}")
        return {'version': 1, 'device': 'RadioMaster AX12', 'phase': 'none'}

    def save_config(self):
        self.config['timestamp'] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)

    # --- SSE broadcasting ---

    def broadcast(self, event_type, data):
        msg = f"event: {event_type}\ndata: {json.dumps(data, separators=(',',':'))}\n\n".encode()
        with self.sse_lock:
            dead = []
            for q in self.sse_queues:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self.sse_queues.remove(q)

    def broadcast_log(self, msg):
        self.broadcast('log', {'ts': time.strftime('%H:%M:%S'), 'msg': msg})

    # --- Serial reader ---

    def _serial_reader(self):
        fd = os.open(SERIAL_PORT, os.O_RDONLY | os.O_NONBLOCK)
        decoder = UMBUSDecoder()
        ftimes = deque(maxlen=100)
        self.state['connected'] = True
        self.broadcast('status', {'connected': True})
        self.broadcast_log(f'Connected to {SERIAL_PORT}')
        skip = 0

        try:
            while self.running:
                try:
                    data = os.read(fd, 4096)
                    for frame in decoder.feed(data):
                        if frame.frame_type not in (FrameType.CHANNEL_DATA, 0x77):
                            continue
                        now = time.time()
                        ftimes.append(now)
                        self.state['frame_count'] += 1
                        if frame.gimbals:
                            self.state['gimbals'] = frame.gimbals
                        if frame.channels:
                            self.state['channels'] = frame.channels[:33]
                        while ftimes and ftimes[0] < now - 1:
                            ftimes.popleft()
                        self.state['fps'] = len(ftimes)

                        # Notify callbacks
                        for cb in self.frame_callbacks:
                            cb(frame.frame_type, self.state['gimbals'], self.state['channels'])

                        # Throttle SSE to ~12Hz
                        skip += 1
                        if skip % 2 == 0:
                            self.broadcast('frame', {
                                'g': self.state['gimbals'],
                                'ch': self.state['channels'],
                                'n': self.state['frame_count'],
                                'fps': self.state['fps'],
                            })
                except BlockingIOError:
                    time.sleep(0.005)
        except Exception as e:
            self.state['connected'] = False
            self.broadcast_log(f'Serial error: {e}')
        finally:
            os.close(fd)

    def _demo_reader(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base, 'captures', 'timed-frames.json')) as f:
            frames = json.load(f)
        decoder = UMBUSDecoder()
        self.state['connected'] = True
        self.state['demo'] = True
        self.broadcast('status', {'connected': True, 'demo': True})
        self.broadcast_log('Demo mode — replaying capture data')

        while self.running:
            for _ts, _ftype, hexstr in frames:
                if not self.running:
                    return
                raw = bytes.fromhex(hexstr)
                for frame in decoder.feed(raw):
                    if frame.frame_type not in (FrameType.CHANNEL_DATA, 0x77):
                        continue
                    self.state['frame_count'] += 1
                    if frame.gimbals:
                        self.state['gimbals'] = frame.gimbals
                    if frame.channels:
                        self.state['channels'] = frame.channels[:33]
                    self.state['fps'] = 25.0
                    self.broadcast('frame', {
                        'g': self.state['gimbals'],
                        'ch': self.state['channels'],
                        'n': self.state['frame_count'],
                        'fps': self.state['fps'],
                    })
                    for cb in self.frame_callbacks:
                        cb(frame.frame_type, self.state['gimbals'], self.state['channels'])
                time.sleep(0.04)
            decoder.reset()

    # --- Route registration ---

    def add_route(self, method, path, handler):
        """Register a custom HTTP route. handler(svc, request) -> (status, body_dict)."""
        self.custom_routes[(method.upper(), path)] = handler

    def set_html(self, html):
        self.html = html

    # --- HTTP server ---

    def _make_handler(svc_self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                if self.path == '/':
                    self._send(200, svc_self.html, 'text/html; charset=utf-8')
                elif self.path == '/stream':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    q = queue.Queue(maxsize=60)
                    with svc_self.sse_lock:
                        svc_self.sse_queues.append(q)
                    try:
                        while svc_self.running:
                            try:
                                msg = q.get(timeout=2)
                                self.wfile.write(msg)
                                self.wfile.flush()
                            except queue.Empty:
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        with svc_self.sse_lock:
                            if q in svc_self.sse_queues:
                                svc_self.sse_queues.remove(q)
                elif self.path == '/api/state':
                    self._json(svc_self.config)
                else:
                    key = ('GET', self.path)
                    if key in svc_self.custom_routes:
                        status, body = svc_self.custom_routes[key](svc_self, self)
                        self._json(body, status)
                    else:
                        self.send_error(404)

            def do_POST(self):
                key = ('POST', self.path)
                if key in svc_self.custom_routes:
                    # Read body if present
                    content_len = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_len) if content_len else b''
                    self.body_data = body
                    status, resp = svc_self.custom_routes[key](svc_self, self)
                    self._json(resp, status)
                else:
                    self.send_error(404)

            def _send(self, code, content, ctype):
                self.send_response(code)
                self.send_header('Content-Type', ctype)
                self.end_headers()
                self.wfile.write(content.encode() if isinstance(content, str) else content)

            def _json(self, data, code=200):
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

        return Handler

    # --- Run ---

    def run(self):
        if not self.demo and os.getuid() != 0:
            print("Must run as root: su 0 python3 <script>")
            print("  Add --demo to test with captured data")
            sys.exit(1)

        reader = self._demo_reader if self.demo else self._serial_reader
        t = threading.Thread(target=reader, daemon=True)
        t.start()

        class Server(ThreadingMixIn, HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        handler = self._make_handler()
        server = Server(('0.0.0.0', self.port), handler)
        print(f"UMBUS Server: http://0.0.0.0:{self.port}")
        print("Press Ctrl+C to stop\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            self.running = False
            print("\nStopped.")


# --- Standalone mode: basic live monitor ---
if __name__ == '__main__':
    demo = '--demo' in sys.argv
    svc = UMBUSService(demo=demo)
    svc.set_html("""<!DOCTYPE html><html><head><title>UMBUS Monitor</title>
<style>body{background:#0a0a0f;color:#c8ccd8;font-family:monospace;padding:20px}
pre{font-size:14px;line-height:1.6}</style></head><body>
<h2>UMBUS Live Monitor</h2><pre id="out">Connecting...</pre>
<script>
const es=new EventSource('/stream');
const $=document.getElementById('out');
es.addEventListener('frame',e=>{
  const d=JSON.parse(e.data);
  $.textContent='Frame #'+d.n+' @ '+d.fps+' Hz\\n\\n'+
    'Gimbals: '+JSON.stringify(d.g)+'\\n\\n'+
    'Channels:\\n'+d.ch.map((v,i)=>'  CH'+String(i).padStart(2,'0')+': '+v).join('\\n');
});
</script></body></html>""")
    svc.run()
