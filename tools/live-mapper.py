#!/usr/bin/env python3
"""
Live UMBUS Mapper — Interactive control surface mapping for RadioMaster AX12

Reads live UMBUS data from /dev/ttyS0, displays real-time gimbal/channel
state, and runs an interactive wizard to map physical controls to channels.

Requirements:
  - Root access (su 0)
  - RadioMaster app must NOT be running (exclusive serial access)

Usage:
  su 0 python3 tools/live-mapper.py          # live from serial
  su 0 python3 tools/live-mapper.py --demo    # replay capture data
  Then open http://<device-ip>:8081 in a browser.
"""

import os, sys, json, time, threading, queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import UMBUSDecoder, FrameType

SERIAL_PORT = '/dev/ttyS0'
HTTP_PORT = 8081

# --- Shared State ---
sse_queues = []
sse_lock = threading.Lock()

state = {
    'gimbals': [0, 0, 0, 0],
    'channels': [32768] * 33,
    'frame_count': 0,
    'fps': 0.0,
    'connected': False,
    'demo': False,
}

wizard = {
    'active': False,
    'step': 0,
    'wstate': 'idle',
    'baseline_g': None,
    'baseline_ch': None,
    'results': {},
    'detected': None,
}

STEPS = [
    # Gimbals — Mode 2: Left=Throttle/Yaw, Right=Pitch/Roll
    {"id": "yaw",  "label": "Yaw (Left X)",      "prompt": "Push LEFT STICK fully LEFT and hold",    "detect": "gimbal"},
    {"id": "thr",  "label": "Throttle (Left Y)",  "prompt": "Push LEFT STICK fully DOWN and hold",    "detect": "gimbal"},
    {"id": "roll", "label": "Roll (Right X)",     "prompt": "Push RIGHT STICK fully RIGHT and hold",  "detect": "gimbal"},
    {"id": "pitch","label": "Pitch (Right Y)",    "prompt": "Push RIGHT STICK fully UP and hold",     "detect": "gimbal"},
    # 2-pos latching switches
    {"id": "sa",  "label": "SA (2-pos latch)",   "prompt": "Flip SA — upper-left shoulder, latching", "detect": "channel"},
    {"id": "sd",  "label": "SD (2-pos latch)",   "prompt": "Flip SD — upper-right shoulder, latching","detect": "channel"},
    # 3-pos switches
    {"id": "sb",  "label": "SB (3-pos)",         "prompt": "Flip SB to DOWN — upper-left 3-position", "detect": "channel"},
    {"id": "sc",  "label": "SC (3-pos)",         "prompt": "Flip SC to DOWN — upper-right 3-position","detect": "channel"},
    {"id": "se",  "label": "SE (3-pos)",         "prompt": "Flip SE to DOWN — left shoulder trigger",  "detect": "channel"},
    {"id": "sf",  "label": "SF (3-pos)",         "prompt": "Flip SF to DOWN — right shoulder trigger", "detect": "channel"},
    # Scroll wheel pots
    {"id": "s1",  "label": "S1 (scroll wheel)",  "prompt": "Turn S1 scroll wheel — left shoulder",    "detect": "channel"},
    {"id": "s2",  "label": "S2 (scroll wheel)",  "prompt": "Turn S2 scroll wheel — right shoulder",   "detect": "channel"},
    # Trims (may be touchscreen-only — skip if no physical buttons)
    {"id": "t1",  "label": "Trim T1",            "prompt": "Press TRIM T1 in one direction (skip if touchscreen-only)", "detect": "channel", "optional": True},
    {"id": "t2",  "label": "Trim T2",            "prompt": "Press TRIM T2 in one direction (skip if touchscreen-only)", "detect": "channel", "optional": True},
    {"id": "t3",  "label": "Trim T3",            "prompt": "Press TRIM T3 in one direction (skip if touchscreen-only)", "detect": "channel", "optional": True},
    {"id": "t4",  "label": "Trim T4",            "prompt": "Press TRIM T4 in one direction (skip if touchscreen-only)", "detect": "channel", "optional": True},
    # Front buttons (may be 6-pos rotary or individual buttons)
    {"id": "btn1","label": "Front Button 1",     "prompt": "Press front button 1 (leftmost) and hold",  "detect": "channel"},
    {"id": "btn2","label": "Front Button 2",     "prompt": "Press front button 2 and hold",             "detect": "channel"},
    {"id": "btn3","label": "Front Button 3",     "prompt": "Press front button 3 and hold",             "detect": "channel"},
    {"id": "btn4","label": "Front Button 4",     "prompt": "Press front button 4 and hold",             "detect": "channel"},
    {"id": "btn5","label": "Front Button 5",     "prompt": "Press front button 5 and hold",             "detect": "channel"},
    {"id": "btn6","label": "Front Button 6",     "prompt": "Press front button 6 (rightmost) and hold", "detect": "channel"},
]

# Calibration state
cal = {
    'active': False,
    'g_min': [99999]*4, 'g_max': [-99999]*4,
    'ch_min': [99999]*33, 'ch_max': [-99999]*33,
    'samples': 0,
}


def broadcast(etype, data):
    msg = f"event: {etype}\ndata: {json.dumps(data, separators=(',',':'))}\n\n".encode()
    with sse_lock:
        dead = []
        for q in sse_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_queues.remove(q)


def broadcast_log(msg):
    broadcast('log', {'ts': time.strftime('%H:%M:%S'), 'msg': msg})


# --- Serial Reader ---
def serial_reader():
    fd = os.open(SERIAL_PORT, os.O_RDONLY | os.O_NONBLOCK)
    decoder = UMBUSDecoder()
    ftimes = deque(maxlen=100)
    state['connected'] = True
    broadcast('status', {'connected': True})
    broadcast_log(f'Connected to {SERIAL_PORT}')
    skip = 0

    try:
        while True:
            try:
                data = os.read(fd, 4096)
                for frame in decoder.feed(data):
                    if frame.frame_type not in (FrameType.CHANNEL_DATA, 0x77):
                        continue
                    now = time.time()
                    ftimes.append(now)
                    state['frame_count'] += 1
                    if frame.gimbals:
                        state['gimbals'] = frame.gimbals
                    if frame.channels:
                        state['channels'] = frame.channels[:33]
                    while ftimes and ftimes[0] < now - 1:
                        ftimes.popleft()
                    state['fps'] = len(ftimes)

                    # Throttle SSE to ~12Hz
                    skip += 1
                    if skip % 2 == 0:
                        broadcast('frame', {
                            'g': state['gimbals'],
                            'ch': state['channels'],
                            'n': state['frame_count'],
                            'fps': state['fps'],
                        })

                    if wizard['active'] and wizard['wstate'] == 'detecting':
                        check_detection()

                    # Calibration: track min/max
                    if cal['active']:
                        cal['samples'] += 1
                        for i in range(4):
                            v = state['gimbals'][i]
                            if v < cal['g_min'][i]: cal['g_min'][i] = v
                            if v > cal['g_max'][i]: cal['g_max'][i] = v
                        for i in range(min(len(state['channels']), 33)):
                            v = state['channels'][i]
                            if v < cal['ch_min'][i]: cal['ch_min'][i] = v
                            if v > cal['ch_max'][i]: cal['ch_max'][i] = v
                        if cal['samples'] % 25 == 0:
                            broadcast('cal', get_cal())
            except BlockingIOError:
                time.sleep(0.005)
    except Exception as e:
        state['connected'] = False
        broadcast_log(f'Serial error: {e}')
    finally:
        os.close(fd)


def demo_reader():
    """Replay capture data for testing without serial access."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, 'captures', 'timed-frames.json')) as f:
        frames = json.load(f)
    decoder = UMBUSDecoder()
    state['connected'] = True
    state['demo'] = True
    broadcast('status', {'connected': True, 'demo': True})
    broadcast_log('Demo mode — replaying capture data')

    while True:
        for ts, ftype, hexstr in frames:
            raw = bytes.fromhex(hexstr)
            for frame in decoder.feed(raw):
                if frame.frame_type not in (FrameType.CHANNEL_DATA, 0x77):
                    continue
                state['frame_count'] += 1
                if frame.gimbals:
                    state['gimbals'] = frame.gimbals
                if frame.channels:
                    state['channels'] = frame.channels[:33]
                state['fps'] = 25.0
                broadcast('frame', {
                    'g': state['gimbals'],
                    'ch': state['channels'],
                    'n': state['frame_count'],
                    'fps': state['fps'],
                })
                if wizard['active'] and wizard['wstate'] == 'detecting':
                    check_detection()
            time.sleep(0.04)
        decoder.reset()


# --- Wizard ---
def get_wiz():
    if not wizard['active'] and wizard['wstate'] != 'done':
        return {'active': False, 'results': wizard['results']}
    s = STEPS[wizard['step']] if wizard['step'] < len(STEPS) else None
    return {
        'active': wizard['active'],
        'step': wizard['step'],
        'total': len(STEPS),
        'wstate': wizard['wstate'],
        'prompt': s['prompt'] if s else '',
        'label': s['label'] if s else '',
        'optional': s.get('optional', False) if s else False,
        'detected': wizard['detected'],
        'results': wizard['results'],
        'baseline_g': wizard['baseline_g'],
        'baseline_ch': wizard['baseline_ch'],
    }


def start_wizard():
    wizard['active'] = True
    wizard['step'] = 0
    wizard['wstate'] = 'baseline'
    wizard['results'] = {}
    wizard['detected'] = None
    wizard['baseline_g'] = list(state['gimbals'])
    wizard['baseline_ch'] = list(state['channels'])
    broadcast_log('Wizard started. Capturing baseline... keep controls centered.')
    broadcast('wizard', get_wiz())
    threading.Timer(1.5, finish_baseline).start()


def finish_baseline():
    wizard['baseline_g'] = list(state['gimbals'])
    wizard['baseline_ch'] = list(state['channels'])
    wizard['wstate'] = 'detecting'
    s = STEPS[wizard['step']]
    broadcast_log(f"Step {wizard['step']+1}/{len(STEPS)}: {s['prompt']}")
    broadcast('wizard', get_wiz())


def check_detection():
    s = STEPS[wizard['step']]
    if s['detect'] == 'gimbal':
        bl = wizard['baseline_g']
        cur = state['gimbals']
        best_i, best_d = None, 0
        for i in range(4):
            d = abs(cur[i] - bl[i])
            if d > best_d:
                best_d = d
                best_i = i
        if best_d > 150:
            wizard['wstate'] = 'detected'
            wizard['detected'] = {
                'type': 'gimbal', 'control': s['id'], 'label': s['label'],
                'index': best_i, 'value': cur[best_i],
                'delta': cur[best_i] - bl[best_i],
                'desc': f"Gimbal axis {best_i} (delta {cur[best_i]-bl[best_i]:+d})",
            }
            broadcast_log(f"Detected: {wizard['detected']['desc']}")
            broadcast('wizard', get_wiz())

    elif s['detect'] == 'channel':
        bl = wizard['baseline_ch']
        cur = state['channels']
        changes = []
        for i in range(min(len(bl), len(cur))):
            d = abs(cur[i] - bl[i])
            if d > 500:
                changes.append({'ch': i, 'from': bl[i], 'to': cur[i], 'delta': cur[i]-bl[i]})
        if changes:
            p = max(changes, key=lambda c: abs(c['delta']))
            wizard['wstate'] = 'detected'
            wizard['detected'] = {
                'type': 'channel', 'control': s['id'], 'label': s['label'],
                'channel': p['ch'], 'from_val': p['from'], 'to_val': p['to'],
                'delta': p['delta'], 'all': changes,
                'desc': f"CH{p['ch']:02d} ({p['from']} -> {p['to']})",
            }
            broadcast_log(f"Detected: {wizard['detected']['desc']}")
            broadcast('wizard', get_wiz())


def confirm_step():
    if wizard['detected']:
        wizard['results'][wizard['detected']['control']] = wizard['detected']
        broadcast_log(f"Confirmed: {wizard['detected']['label']} = {wizard['detected']['desc']}")
    advance()


def skip_step():
    broadcast_log(f"Skipped: {STEPS[wizard['step']]['label']}")
    advance()


def retry_step():
    wizard['detected'] = None
    wizard['wstate'] = 'baseline'
    broadcast_log('Retrying... return controls to center.')
    broadcast('wizard', get_wiz())
    threading.Timer(1.0, finish_baseline).start()


def advance():
    wizard['step'] += 1
    wizard['detected'] = None
    if wizard['step'] >= len(STEPS):
        wizard['wstate'] = 'done'
        wizard['active'] = False
        broadcast_log('Mapping complete!')
        broadcast('wizard', get_wiz())
        save_results()
    else:
        wizard['wstate'] = 'baseline'
        wizard['baseline_g'] = list(state['gimbals'])
        wizard['baseline_ch'] = list(state['channels'])
        broadcast('wizard', get_wiz())
        threading.Timer(1.0, finish_baseline).start()


def save_results():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'docs', 'control-map.json')
    out = {'mapping': wizard['results']}
    if cal['samples'] > 0:
        out['calibration'] = {
            'gimbals': {f'g{i}': {'min': cal['g_min'][i], 'max': cal['g_max'][i]} for i in range(4)},
            'channels': {f'ch{i}': {'min': cal['ch_min'][i], 'max': cal['ch_max'][i]}
                         for i in range(33)
                         if cal['ch_min'][i] != cal['ch_max'][i]},
            'samples': cal['samples'],
        }
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    broadcast_log(f'Results saved to docs/control-map.json ({cal["samples"]} cal samples)')


def get_cal():
    return {
        'active': cal['active'],
        'samples': cal['samples'],
        'g_min': cal['g_min'], 'g_max': cal['g_max'],
        'ch_min': cal['ch_min'][:33], 'ch_max': cal['ch_max'][:33],
    }


def start_cal():
    cal['active'] = True
    cal['g_min'] = [99999]*4
    cal['g_max'] = [-99999]*4
    cal['ch_min'] = [99999]*33
    cal['ch_max'] = [-99999]*33
    cal['samples'] = 0
    broadcast_log('Calibration started. Move ALL sticks, switches, pots to their full range.')
    broadcast('cal', get_cal())


def stop_cal():
    cal['active'] = False
    broadcast_log(f'Calibration stopped. {cal["samples"]} samples captured.')
    broadcast('cal', get_cal())
    save_results()


# --- HTTP ---
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            q = queue.Queue(maxsize=60)
            with sse_lock:
                sse_queues.append(q)
            try:
                while True:
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
                with sse_lock:
                    if q in sse_queues:
                        sse_queues.remove(q)
        else:
            self.send_error(404)

    def do_POST(self):
        actions = {
            '/api/start': start_wizard,
            '/api/confirm': confirm_step,
            '/api/skip': skip_step,
            '/api/retry': retry_step,
            '/api/cal/start': start_cal,
            '/api/cal/stop': stop_cal,
        }
        fn = actions.get(self.path)
        if fn:
            fn()
            self._json({'ok': True})
        else:
            self.send_error(404)

    def _json(self, d):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# --- HTML ---
HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>UMBUS Live Mapper</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#07080c;--p:#0d0f16;--bdr:#1a1e2e;--t:#c8ccd8;--dim:#555a6e;
--grn:#00e87b;--red:#ff5544;--blu:#3399ff;--amb:#ffaa22;--hl:rgba(255,170,34,0.25)}
body{background:var(--bg);color:var(--t);font-family:'SF Mono','Cascadia Code',monospace;
font-size:13px;overflow-x:hidden;-webkit-user-select:none;user-select:none}
.hdr{background:var(--p);padding:10px 16px;display:flex;align-items:center;
justify-content:space-between;border-bottom:1px solid var(--bdr)}
.hdr h1{font-size:14px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#fff}
.hdr h1 span{color:var(--grn);font-weight:400}
.hdr-r{font-size:11px;color:var(--dim);display:flex;gap:12px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.on{background:var(--grn);box-shadow:0 0 6px var(--grn)}
.dot.off{background:var(--red)}

.main{padding:12px;display:flex;flex-direction:column;gap:12px}

/* Sticks */
.sticks{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sbox{aspect-ratio:1;background:#0a0c14;border:1px solid var(--bdr);border-radius:8px;
position:relative;max-height:160px}
.sgrid{position:absolute;inset:0}
.sgrid line{stroke:#151a2a;stroke-width:1}
.sgrid .cl{stroke:#1f2540;stroke-dasharray:4 4}
.cross{position:absolute;width:16px;height:16px;border-radius:50%;border:2px solid var(--grn);
box-shadow:0 0 10px rgba(0,232,123,0.4);transform:translate(-50%,-50%);
transition:left .04s linear,top .04s linear;left:50%;top:50%}
.cross::before,.cross::after{content:'';position:absolute;background:var(--grn)}
.cross::before{width:10px;height:1px;top:50%;left:50%;transform:translate(-50%,-50%)}
.cross::after{width:1px;height:10px;top:50%;left:50%;transform:translate(-50%,-50%)}
.slbl{position:absolute;bottom:3px;width:100%;text-align:center;font-size:9px;
letter-spacing:1px;color:var(--dim);text-transform:uppercase}
.sval{position:absolute;top:3px;right:5px;font-size:9px;color:var(--grn);opacity:.7}

/* Wizard */
.wiz{background:var(--p);border:1px solid var(--bdr);border-radius:8px;padding:14px}
.wiz-title{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--dim);
margin-bottom:8px;font-weight:600}
.wiz-step{font-size:11px;color:var(--dim);margin-bottom:6px}
.wiz-prompt{font-size:15px;color:#fff;font-weight:600;margin-bottom:12px;line-height:1.4}
.wiz-state{font-size:12px;color:var(--amb);margin-bottom:12px}
.wiz-detected{background:rgba(0,232,123,.08);border:1px solid rgba(0,232,123,.25);
border-radius:6px;padding:10px;margin-bottom:12px}
.wiz-detected .wd-label{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:1px}
.wiz-detected .wd-value{font-size:16px;color:var(--grn);font-weight:700}
.btns{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:8px 16px;border:1px solid var(--bdr);border-radius:6px;background:none;
color:var(--t);font-family:inherit;font-size:12px;cursor:pointer;transition:all .2s;
-webkit-tap-highlight-color:transparent}
.btn:active{transform:scale(.96)}
.btn-go{border-color:var(--grn);color:var(--grn);background:rgba(0,232,123,.08)}
.btn-skip{border-color:var(--dim);color:var(--dim)}
.btn-retry{border-color:var(--amb);color:var(--amb)}

/* Channels */
.ch-title{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--dim);
font-weight:600;margin-bottom:6px}
.chgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:2px 10px}
.chr{display:flex;align-items:center;gap:4px;height:16px}
.chr.highlight{background:var(--hl);border-radius:3px;padding:0 3px;margin:0 -3px}
.chl{width:28px;font-size:9px;color:var(--dim);flex-shrink:0}
.chb-bg{flex:1;height:6px;background:#111420;border-radius:1px;position:relative;overflow:hidden}
.chb{height:100%;background:var(--grn);border-radius:1px;transition:width .04s linear;opacity:.8}
.chb.sw{background:var(--amb)}
.chbase{position:absolute;top:0;bottom:0;width:2px;background:var(--red);opacity:.6;
transition:left .3s}

/* Results */
.results{background:var(--p);border:1px solid var(--bdr);border-radius:8px;padding:14px}
.res-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;
border-bottom:1px solid var(--bdr)}
.res-row:last-child{border:none}
.res-label{color:var(--dim)}
.res-value{color:var(--grn);font-weight:600}

/* Log */
.log{background:var(--p);border:1px solid var(--bdr);border-radius:8px;padding:10px;
max-height:160px;overflow-y:auto;font-size:11px;line-height:1.6}
.log-entry{color:var(--dim)}
.log-entry .ts{color:var(--blu);margin-right:6px}
.log-entry .msg{color:var(--t)}

@media(min-width:600px){
.top{display:grid;grid-template-columns:auto 1fr;gap:12px}
}
</style>
</head><body>
<div class="hdr">
<h1>UMBUS <span>Live Mapper</span></h1>
<div class="hdr-r"><span class="dot" id="dot"></span><span id="status">Connecting...</span></div>
</div>
<div class="main">

<div class="top">
<div class="sticks">
<div class="sbox">
<svg class="sgrid" viewBox="0 0 100 100" preserveAspectRatio="none">
<line x1="50" y1="0" x2="50" y2="100" class="cl"/><line x1="0" y1="50" x2="100" y2="50" class="cl"/>
<line x1="25" y1="0" x2="25" y2="100"/><line x1="75" y1="0" x2="75" y2="100"/>
<line x1="0" y1="25" x2="100" y2="25"/><line x1="0" y1="75" x2="100" y2="75"/>
</svg>
<div class="cross" id="cl"></div><div class="sval" id="clv">0, 0</div><div class="slbl">G0 / G1</div>
</div>
<div class="sbox">
<svg class="sgrid" viewBox="0 0 100 100" preserveAspectRatio="none">
<line x1="50" y1="0" x2="50" y2="100" class="cl"/><line x1="0" y1="50" x2="100" y2="50" class="cl"/>
<line x1="25" y1="0" x2="25" y2="100"/><line x1="75" y1="0" x2="75" y2="100"/>
<line x1="0" y1="25" x2="100" y2="25"/><line x1="0" y1="75" x2="100" y2="75"/>
</svg>
<div class="cross" id="cr"></div><div class="sval" id="crv">0, 0</div><div class="slbl">G2 / G3</div>
</div>
</div>

<div class="wiz" id="wiz">
<div class="wiz-title">Control Mapper</div>
<div id="wiz-body">
<p style="color:var(--dim);margin-bottom:12px">Map each physical control (gimbals, switches, pots) to its UMBUS channel. Stop the RadioMaster app first.</p>
<div class="btns"><button class="btn btn-go" onclick="api('start')">Start Mapping</button></div>
</div>
</div>
</div>

<div>
<div class="ch-title">Output Channels</div>
<div class="chgrid" id="chgrid"></div>
</div>

<div class="results" id="results" style="display:none">
<div class="wiz-title">Mapping Results</div>
<div id="res-body"></div>
</div>

<div class="wiz" id="cal-panel">
<div class="wiz-title">Calibration</div>
<div id="cal-body">
<p style="color:var(--dim);margin-bottom:8px;font-size:12px">Record min/max range for all controls. Move every stick, switch, and pot to full extremes.</p>
<div class="btns"><button class="btn btn-go" id="cal-btn" onclick="toggleCal()">Start Calibration</button></div>
<div id="cal-stats" style="margin-top:8px;font-size:11px;color:var(--dim);display:none">
<span id="cal-samples">0</span> samples |
Gimbals: <span id="cal-g-range" style="color:var(--grn)">--</span>
</div>
</div>
</div>

<div>
<div class="ch-title">Log</div>
<div class="log" id="log"></div>
</div>

</div>

<script>
const $cl=document.getElementById('cl'),$cr=document.getElementById('cr');
const $clv=document.getElementById('clv'),$crv=document.getElementById('crv');
const $chgrid=document.getElementById('chgrid');
const $wiz=document.getElementById('wiz-body');
const $log=document.getElementById('log');
const $dot=document.getElementById('dot');
const $status=document.getElementById('status');
const $results=document.getElementById('results');
const $resBody=document.getElementById('res-body');

let baseline_ch=null, baseline_g=null;
// Auto-baseline: capture first frame as center reference for stick display
let autoBase_g=null;
// Hysteresis: track which channels are highlighted
const highlighted=new Set();

// Init channels
for(let i=0;i<33;i++){
  const r=document.createElement('div');r.className='chr';r.id='chr-'+i;
  r.innerHTML=`<span class="chl">CH${String(i).padStart(2,'0')}</span>`+
    `<div class="chb-bg"><div class="chbase" id="chbase-${i}" style="display:none"></div>`+
    `<div class="chb" id="chb-${i}"></div></div>`;
  $chgrid.appendChild(r);
}

// SSE
const es=new EventSource('/stream');
es.addEventListener('frame',e=>{
  const d=JSON.parse(e.data);
  // Auto-capture first frame as gimbal center reference
  const g=d.g;
  if(!autoBase_g) autoBase_g=g.slice();
  // Use wizard baseline if active, else auto-baseline
  const bg=baseline_g||autoBase_g;
  const R=800;
  // Sticks: show DELTA from baseline so throttle/non-centering axes display correctly
  $cl.style.left=Math.max(5,Math.min(95,50+(g[0]-bg[0])/R*50))+'%';
  $cl.style.top=Math.max(5,Math.min(95,50-(g[1]-bg[1])/R*50))+'%';
  $cr.style.left=Math.max(5,Math.min(95,50+(g[2]-bg[2])/R*50))+'%';
  $cr.style.top=Math.max(5,Math.min(95,50-(g[3]-bg[3])/R*50))+'%';
  $clv.textContent=g[0]+', '+g[1];
  $crv.textContent=g[2]+', '+g[3];
  // Channels
  const ch=d.ch;
  for(let i=0;i<Math.min(ch.length,33);i++){
    const bar=document.getElementById('chb-'+i);
    const row=document.getElementById('chr-'+i);
    if(!bar)continue;
    const pct=ch[i]/65535*100;
    bar.style.width=pct+'%';
    bar.className='chb'+(ch[i]===65036||ch[i]===65436?' sw':'');
    // Highlight with hysteresis: >500 to activate, <200 to deactivate
    if(baseline_ch){
      const delta=Math.abs(ch[i]-baseline_ch[i]);
      if(delta>500) highlighted.add(i);
      else if(delta<200) highlighted.delete(i);
      const want='chr'+(highlighted.has(i)?' highlight':'');
      if(row.className!==want) row.className=want;
    }
  }
  // Status
  $status.textContent=d.fps+' Hz  #'+d.n;
});
es.addEventListener('status',e=>{
  const d=JSON.parse(e.data);
  $dot.className='dot '+(d.connected?'on':'off');
  if(d.demo) $status.textContent='DEMO MODE';
});
es.addEventListener('log',e=>{
  const d=JSON.parse(e.data);
  const div=document.createElement('div');div.className='log-entry';
  div.innerHTML=`<span class="ts">${d.ts}</span><span class="msg">${esc(d.msg)}</span>`;
  $log.appendChild(div);
  $log.scrollTop=$log.scrollHeight;
});
es.addEventListener('wizard',e=>{
  const w=JSON.parse(e.data);
  baseline_ch=w.baseline_ch;
  baseline_g=w.baseline_g;
  // Show baselines on channel bars
  if(baseline_ch){
    for(let i=0;i<Math.min(baseline_ch.length,33);i++){
      const m=document.getElementById('chbase-'+i);
      if(m){m.style.display='block';m.style.left=(baseline_ch[i]/65535*100)+'%';}
    }
  }
  renderWiz(w);
  renderResults(w.results);
});
es.onerror=()=>{$dot.className='dot off';$status.textContent='Disconnected';};

function esc(s){return s.replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function renderWiz(w){
  if(w.wstate==='done'){
    $wiz.innerHTML=`<p style="color:var(--grn);font-weight:600;margin-bottom:10px">Mapping Complete</p>
      <p style="color:var(--dim);font-size:12px">Results saved to docs/control-map.json</p>
      <div class="btns" style="margin-top:10px"><button class="btn btn-go" onclick="api('start')">Run Again</button></div>`;
    return;
  }
  if(!w.active){
    $wiz.innerHTML=`<p style="color:var(--dim);margin-bottom:12px">Map each physical control to its UMBUS channel.</p>
      <div class="btns"><button class="btn btn-go" onclick="api('start')">Start Mapping</button></div>`;
    return;
  }
  let html=`<div class="wiz-step">Step ${w.step+1} of ${w.total}${w.optional?' (optional)':''}</div>`;
  html+=`<div class="wiz-prompt">${esc(w.prompt)}</div>`;

  if(w.wstate==='baseline')
    html+=`<div class="wiz-state">Capturing baseline... keep controls centered</div>`;
  else if(w.wstate==='detecting')
    html+=`<div class="wiz-state">Watching for changes... move the control now</div>`;
  else if(w.wstate==='detected'&&w.detected){
    html+=`<div class="wiz-detected"><div class="wd-label">Detected</div>
      <div class="wd-value">${esc(w.detected.desc)}</div></div>`;
    html+=`<div class="btns">
      <button class="btn btn-go" onclick="api('confirm')">Confirm</button>
      <button class="btn btn-retry" onclick="api('retry')">Retry</button>
      <button class="btn btn-skip" onclick="api('skip')">Skip</button></div>`;
    $wiz.innerHTML=html;return;
  }
  html+=`<div class="btns">`;
  if(w.optional) html+=`<button class="btn btn-skip" onclick="api('skip')">Skip</button>`;
  html+=`</div>`;
  $wiz.innerHTML=html;
}

function renderResults(results){
  if(!results||Object.keys(results).length===0){$results.style.display='none';return;}
  $results.style.display='block';
  let html='';
  for(const[k,v]of Object.entries(results)){
    html+=`<div class="res-row"><span class="res-label">${esc(v.label)}</span>
      <span class="res-value">${esc(v.desc)}</span></div>`;
  }
  $resBody.innerHTML=html;
}

function api(action){fetch('/api/'+action,{method:'POST'});}

// Calibration
let calActive=false;
function toggleCal(){
  calActive=!calActive;
  api(calActive?'cal/start':'cal/stop');
  document.getElementById('cal-btn').textContent=calActive?'Stop Calibration':'Start Calibration';
  document.getElementById('cal-btn').className='btn '+(calActive?'btn-retry':'btn-go');
  document.getElementById('cal-stats').style.display=calActive?'block':'none';
}
es.addEventListener('cal',e=>{
  const c=JSON.parse(e.data);
  document.getElementById('cal-samples').textContent=c.samples;
  const gr=c.g_min.map((mn,i)=>`G${i}:[${mn},${c.g_max[i]}]`).join(' ');
  document.getElementById('cal-g-range').textContent=gr;
  if(!c.active&&calActive){
    calActive=false;
    document.getElementById('cal-btn').textContent='Start Calibration';
    document.getElementById('cal-btn').className='btn btn-go';
  }
});
</script>
</body></html>"""


# --- Main ---
def main():
    demo = '--demo' in sys.argv

    if not demo and os.getuid() != 0:
        print("Must run as root: su 0 python3 tools/live-mapper.py")
        print("  Add --demo to test with captured data instead")
        sys.exit(1)

    reader = demo_reader if demo else serial_reader
    t = threading.Thread(target=reader, daemon=True)
    t.start()

    server = Server(('0.0.0.0', HTTP_PORT), Handler)
    print(f"Live Mapper: http://0.0.0.0:{HTTP_PORT}")
    print("Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == '__main__':
    main()
