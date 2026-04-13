#!/usr/bin/env python3
"""
HDMI Latency Test — Measure input latency of the AX12 HDMI pipeline.

Serves an HTML page displaying a high-precision millisecond counter that
updates every frame via requestAnimationFrame. To measure latency:

  1. Open http://<laptop-ip>:8080 in Chrome on a laptop
  2. Connect laptop HDMI out → AX12 Mini HDMI In
  3. Photograph both screens simultaneously with a phone camera
  4. The time difference between the two displays = pipeline latency

Features:
  - HH:MM:SS.mmm counter at 200px, white on black
  - Frame counter and measured FPS
  - Green flash every 5 seconds (visual sync point for video analysis)
  - Optional WebSocket bridge for automated measurement (experimental)

Usage:
    python3 tools/latency-test.py              # serve on port 8080
    python3 tools/latency-test.py --port 9090  # custom port
    python3 tools/latency-test.py --ws-port 8081  # enable WebSocket relay

Stdlib only — no external dependencies.
"""

import argparse
import hashlib
import json
import struct
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ---------------------------------------------------------------------------
# HTML page — the core latency measurement display
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HDMI Latency Test</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #000;
    color: #fff;
    font-family: 'Courier New', monospace;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    overflow: hidden;
    user-select: none;
  }
  #clock {
    font-size: 200px;
    font-weight: bold;
    line-height: 1;
    letter-spacing: -4px;
  }
  #stats {
    font-size: 36px;
    color: #888;
    margin-top: 20px;
  }
  #flash-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #00ff00;
    pointer-events: none;
    opacity: 0;
    z-index: 100;
  }
  #ws-status {
    position: fixed;
    bottom: 20px;
    right: 20px;
    font-size: 14px;
    color: #555;
  }
  #instructions {
    position: fixed;
    bottom: 20px;
    left: 20px;
    font-size: 14px;
    color: #444;
    max-width: 400px;
  }
  /* Responsive — shrink clock on smaller screens */
  @media (max-width: 1200px) {
    #clock { font-size: 120px; }
  }
  @media (max-width: 700px) {
    #clock { font-size: 60px; }
    #stats { font-size: 20px; }
  }
</style>
</head>
<body>
<div id="flash-overlay"></div>
<div id="clock">00:00:00.000</div>
<div id="stats">Frame: 0 | FPS: --</div>
<div id="ws-status"></div>
<div id="instructions">
  Photograph both screens simultaneously.<br>
  Time difference = HDMI pipeline latency.<br>
  Green flash every 5s for video sync.
</div>

<script>
(function() {
  'use strict';

  const clockEl = document.getElementById('clock');
  const statsEl = document.getElementById('stats');
  const flashEl = document.getElementById('flash-overlay');
  const wsStatusEl = document.getElementById('ws-status');

  let frameCount = 0;
  let fpsFrames = 0;
  let lastFpsTime = performance.now();
  let currentFps = 0;

  // Flash state
  const FLASH_INTERVAL = 5000;  // ms between flashes
  const FLASH_DURATION = 100;   // ms flash lasts
  let lastFlashTime = 0;
  let flashing = false;

  function pad2(n) { return n < 10 ? '0' + n : '' + n; }
  function pad3(n) {
    if (n < 10) return '00' + n;
    if (n < 100) return '0' + n;
    return '' + n;
  }

  function formatTime(now) {
    const h = pad2(now.getHours());
    const m = pad2(now.getMinutes());
    const s = pad2(now.getSeconds());
    const ms = pad3(now.getMilliseconds());
    return h + ':' + m + ':' + s + '.' + ms;
  }

  function tick(timestamp) {
    const now = new Date();
    frameCount++;
    fpsFrames++;

    // Update clock
    clockEl.textContent = formatTime(now);

    // Calculate FPS every second
    const fpsDelta = timestamp - lastFpsTime;
    if (fpsDelta >= 1000) {
      currentFps = Math.round((fpsFrames * 1000) / fpsDelta);
      fpsFrames = 0;
      lastFpsTime = timestamp;
    }

    // Update stats
    statsEl.textContent = 'Frame: ' + frameCount + ' | FPS: ' + currentFps;

    // Flash logic — green flash every 5 seconds
    const elapsed = now.getTime();
    const sinceLastFlash = elapsed - lastFlashTime;
    if (sinceLastFlash >= FLASH_INTERVAL && !flashing) {
      flashing = true;
      lastFlashTime = elapsed;
      flashEl.style.opacity = '1';
      setTimeout(function() {
        flashEl.style.opacity = '0';
        flashing = false;
      }, FLASH_DURATION);
    }

    // Send timestamp via WebSocket if connected
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'timestamp',
        time: now.toISOString(),
        epoch_ms: now.getTime(),
        frame: frameCount
      }));
    }

    requestAnimationFrame(tick);
  }

  // Start the animation loop
  requestAnimationFrame(tick);

  // --- WebSocket connection (optional, for automated measurement) ---
  var ws = null;
  const WS_PORT = /*WS_PORT_PLACEHOLDER*/0;

  if (WS_PORT > 0) {
    function connectWs() {
      const host = window.location.hostname || 'localhost';
      const url = 'ws://' + host + ':' + WS_PORT;
      wsStatusEl.textContent = 'WS: connecting to ' + url + '...';

      ws = new WebSocket(url);

      ws.onopen = function() {
        wsStatusEl.textContent = 'WS: connected to ' + url;
        wsStatusEl.style.color = '#0f0';
      };

      ws.onmessage = function(evt) {
        // AX12 can send back its received timestamp for comparison
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'ax12_timestamp') {
            // Could overlay AX12's view of the timestamp for comparison
            console.log('AX12 received at:', msg.received_ms, 'source was:', msg.source_ms,
                        'delta:', msg.received_ms - msg.source_ms, 'ms');
          }
        } catch(e) {}
      };

      ws.onclose = function() {
        wsStatusEl.textContent = 'WS: disconnected (reconnecting...)';
        wsStatusEl.style.color = '#f00';
        ws = null;
        setTimeout(connectWs, 3000);
      };

      ws.onerror = function() {
        ws.close();
      };
    }

    connectWs();
  } else {
    wsStatusEl.textContent = 'WS: disabled (use --ws-port to enable)';
  }

})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server — serves the latency test page
# ---------------------------------------------------------------------------

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class LatencyHandler(BaseHTTPRequestHandler):
    """Serves the latency test HTML page."""

    html = ''  # Set by main() before server starts

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            content = self.html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        # Quieter logging — just show requests
        sys.stderr.write('[HTTP] %s %s\n' % (self.client_address[0], args[0] if args else ''))


# ---------------------------------------------------------------------------
# WebSocket server — minimal RFC 6455 implementation (stdlib only)
# ---------------------------------------------------------------------------

class WebSocketServer:
    """Bare-bones WebSocket server for timestamp relay. Stdlib only."""

    def __init__(self, port):
        self.port = port
        self.clients = []
        self.lock = threading.Lock()
        self.running = True

    def start(self):
        import socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(1.0)
        self.sock.bind(('0.0.0.0', self.port))
        self.sock.listen(5)

        thread = threading.Thread(target=self._accept_loop, daemon=True)
        thread.start()
        print(f'[WS] WebSocket server on ws://0.0.0.0:{self.port}')

    def _accept_loop(self):
        import socket
        while self.running:
            try:
                conn, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            thread = threading.Thread(target=self._handle_client, daemon=True,
                                     args=(conn, addr))
            thread.start()

    def _handle_client(self, conn, addr):
        """Handle WebSocket handshake and message loop."""
        try:
            data = conn.recv(4096).decode('utf-8', errors='replace')
            if 'Upgrade: websocket' not in data:
                conn.close()
                return

            # Extract Sec-WebSocket-Key
            key = None
            for line in data.split('\r\n'):
                if line.lower().startswith('sec-websocket-key:'):
                    key = line.split(':', 1)[1].strip()
                    break
            if not key:
                conn.close()
                return

            # Compute accept key
            import base64
            MAGIC = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
            accept = base64.b64encode(
                hashlib.sha1((key + MAGIC).encode()).digest()
            ).decode()

            # Send handshake response
            response = (
                'HTTP/1.1 101 Switching Protocols\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Accept: {accept}\r\n'
                '\r\n'
            )
            conn.sendall(response.encode())

            with self.lock:
                self.clients.append(conn)
            print(f'[WS] Client connected: {addr[0]}:{addr[1]}')

            # Read loop — receive timestamps from the browser
            while self.running:
                frame_data = self._read_frame(conn)
                if frame_data is None:
                    break
                # Process incoming timestamp, echo back with AX12 receive time
                try:
                    msg = json.loads(frame_data)
                    if msg.get('type') == 'timestamp':
                        reply = json.dumps({
                            'type': 'ax12_timestamp',
                            'source_ms': msg['epoch_ms'],
                            'received_ms': int(time.time() * 1000),
                            'frame': msg.get('frame', 0)
                        })
                        self._send_frame(conn, reply)
                except (json.JSONDecodeError, KeyError):
                    pass

        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            with self.lock:
                if conn in self.clients:
                    self.clients.remove(conn)
            try:
                conn.close()
            except OSError:
                pass
            print(f'[WS] Client disconnected: {addr[0]}:{addr[1]}')

    def _read_frame(self, conn):
        """Read one WebSocket frame. Returns decoded payload or None on close."""
        try:
            header = self._recv_exact(conn, 2)
            if not header:
                return None

            opcode = header[0] & 0x0F
            if opcode == 0x8:  # Close frame
                return None

            masked = bool(header[1] & 0x80)
            length = header[1] & 0x7F

            if length == 126:
                ext = self._recv_exact(conn, 2)
                if not ext:
                    return None
                length = struct.unpack('!H', ext)[0]
            elif length == 127:
                ext = self._recv_exact(conn, 8)
                if not ext:
                    return None
                length = struct.unpack('!Q', ext)[0]

            if masked:
                mask_key = self._recv_exact(conn, 4)
                if not mask_key:
                    return None

            payload = self._recv_exact(conn, length)
            if not payload:
                return None

            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            return payload.decode('utf-8')
        except (OSError, struct.error):
            return None

    def _send_frame(self, conn, text):
        """Send a WebSocket text frame (unmasked, server→client)."""
        payload = text.encode('utf-8')
        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode

        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack('!H', length))
        else:
            frame.append(127)
            frame.extend(struct.pack('!Q', length))

        frame.extend(payload)
        try:
            conn.sendall(bytes(frame))
        except OSError:
            pass

    def _recv_exact(self, conn, n):
        """Receive exactly n bytes."""
        data = bytearray()
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def stop(self):
        self.running = False
        with self.lock:
            for c in self.clients:
                try:
                    c.close()
                except OSError:
                    pass
            self.clients.clear()
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='HDMI Latency Test — serve a millisecond counter for latency measurement')
    parser.add_argument('--port', type=int, default=8080,
                        help='HTTP server port (default: 8080)')
    parser.add_argument('--ws-port', type=int, default=0,
                        help='WebSocket port for automated measurement (0 = disabled)')
    args = parser.parse_args()

    # Inject WebSocket port into HTML
    html = HTML_PAGE.replace('/*WS_PORT_PLACEHOLDER*/0', str(args.ws_port))
    LatencyHandler.html = html

    # Start WebSocket server if requested
    ws_server = None
    if args.ws_port > 0:
        ws_server = WebSocketServer(args.ws_port)
        ws_server.start()

    # Start HTTP server
    server = ThreadedHTTPServer(('0.0.0.0', args.port), LatencyHandler)
    print(f'[HTTP] Latency test page: http://0.0.0.0:{args.port}/')
    print(f'[HTTP] Open in Chrome on the laptop, HDMI out → AX12 Mini HDMI In')
    print(f'[HTTP] Photograph both screens to measure latency')
    if args.ws_port > 0:
        print(f'[WS] Automated measurement relay on port {args.ws_port}')
    print()
    print('Press Ctrl+C to stop.')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        server.shutdown()
        if ws_server:
            ws_server.stop()


if __name__ == '__main__':
    main()
