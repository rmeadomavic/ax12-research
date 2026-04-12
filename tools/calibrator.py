#!/usr/bin/env python3
"""
AX12 Calibrator — 3-phase control surface calibration & mapping.

Phase 1: Center — capture neutral position (3 sec, automatic)
Phase 2: Range  — capture min/max for all controls (user-driven)
Phase 3: Map    — identify each control one at a time (guided wizard)

Usage:
    su 0 python3 tools/calibrator.py          # live serial
    su 0 python3 tools/calibrator.py --demo   # replay captures
    Then open http://<device-ip>:8081 in a browser.
"""

import os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus_server import UMBUSService

# --- Control definitions ---
MAP_STEPS = [
    {"id": "yaw",   "label": "Yaw (Left X)",      "prompt": "Push LEFT STICK fully LEFT and hold",     "detect": "gimbal"},
    {"id": "thr",   "label": "Throttle (Left Y)",  "prompt": "Push LEFT STICK fully DOWN and hold",     "detect": "gimbal"},
    {"id": "roll",  "label": "Roll (Right X)",     "prompt": "Push RIGHT STICK fully RIGHT and hold",   "detect": "gimbal"},
    {"id": "pitch", "label": "Pitch (Right Y)",    "prompt": "Push RIGHT STICK fully UP and hold",      "detect": "gimbal"},
    {"id": "sa",    "label": "SA (2-pos latch)",   "prompt": "Flip SA — upper-left, latching",          "detect": "channel"},
    {"id": "sd",    "label": "SD (2-pos latch)",   "prompt": "Flip SD — upper-right, latching",         "detect": "channel"},
    {"id": "sb",    "label": "SB (3-pos)",         "prompt": "Flip SB to DOWN — upper-left 3-position", "detect": "channel"},
    {"id": "sc",    "label": "SC (3-pos)",         "prompt": "Flip SC to DOWN — upper-right 3-position","detect": "channel"},
    {"id": "se",    "label": "SE (3-pos)",         "prompt": "Flip SE to DOWN — left shoulder trigger",  "detect": "channel"},
    {"id": "sf",    "label": "SF (3-pos)",         "prompt": "Flip SF to DOWN — right shoulder trigger", "detect": "channel"},
    {"id": "s1",    "label": "S1 (scroll wheel)",  "prompt": "Turn S1 scroll wheel — left shoulder",    "detect": "channel"},
    {"id": "s2",    "label": "S2 (scroll wheel)",  "prompt": "Turn S2 scroll wheel — right shoulder",   "detect": "channel"},
    {"id": "t1",    "label": "Trim T1",            "prompt": "Press T1 (skip if touchscreen-only)",     "detect": "channel", "optional": True},
    {"id": "t2",    "label": "Trim T2",            "prompt": "Press T2 (skip if touchscreen-only)",     "detect": "channel", "optional": True},
    {"id": "t3",    "label": "Trim T3",            "prompt": "Press T3 (skip if touchscreen-only)",     "detect": "channel", "optional": True},
    {"id": "t4",    "label": "Trim T4",            "prompt": "Press T4 (skip if touchscreen-only)",     "detect": "channel", "optional": True},
    {"id": "btn1",  "label": "Front Button 1",     "prompt": "Press front button 1 (leftmost) and hold","detect": "channel"},
    {"id": "btn2",  "label": "Front Button 2",     "prompt": "Press front button 2 and hold",           "detect": "channel"},
    {"id": "btn3",  "label": "Front Button 3",     "prompt": "Press front button 3 and hold",           "detect": "channel"},
    {"id": "btn4",  "label": "Front Button 4",     "prompt": "Press front button 4 and hold",           "detect": "channel"},
    {"id": "btn5",  "label": "Front Button 5",     "prompt": "Press front button 5 and hold",           "detect": "channel"},
    {"id": "btn6",  "label": "Front Button 6",     "prompt": "Press front button 6 (rightmost) and hold","detect": "channel"},
]

CENTER_FRAMES = 75  # ~3 sec at 25Hz
GIMBAL_THRESHOLD = 150
CHANNEL_THRESHOLD = 500


class Calibrator:
    def __init__(self, svc: UMBUSService):
        self.svc = svc
        # Phase state
        self.phase = svc.config.get('phase', 'none')  # none, center, range, mapping, complete
        self.center_buf_g = []
        self.center_buf_ch = []
        # Range tracking
        self.range_g_min = [99999]*4
        self.range_g_max = [-99999]*4
        self.range_ch_min = [99999]*33
        self.range_ch_max = [-99999]*33
        self.range_samples = 0
        # Mapping wizard
        self.map_step = 0
        self.map_detected = None
        # Restore state from config if resuming
        if self.phase == 'mapping':
            self.map_step = len(svc.config.get('mapping', {}))
        # Register frame callback
        svc.frame_callbacks.append(self.on_frame)

    # --- Frame callback ---
    def on_frame(self, ftype, gimbals, channels):
        if self.phase == 'center':
            self.center_buf_g.append(list(gimbals))
            self.center_buf_ch.append(list(channels))
            if len(self.center_buf_g) >= CENTER_FRAMES:
                self._finish_center()

        elif self.phase == 'range':
            self.range_samples += 1
            for i in range(4):
                if gimbals[i] < self.range_g_min[i]: self.range_g_min[i] = gimbals[i]
                if gimbals[i] > self.range_g_max[i]: self.range_g_max[i] = gimbals[i]
            for i in range(min(len(channels), 33)):
                if channels[i] < self.range_ch_min[i]: self.range_ch_min[i] = channels[i]
                if channels[i] > self.range_ch_max[i]: self.range_ch_max[i] = channels[i]
            if self.range_samples % 25 == 0:
                self.svc.broadcast('range', self._range_data())

        elif self.phase == 'mapping' and self.map_detected is None:
            self._check_mapping(gimbals, channels)

    # --- Phase 1: Center ---
    def start_center(self):
        self.phase = 'center'
        self.center_buf_g = []
        self.center_buf_ch = []
        self.svc.broadcast_log('Phase 1: Capturing center... hands off all controls.')
        self.svc.broadcast('phase', self._phase_state())

    def _finish_center(self):
        n = len(self.center_buf_g)
        avg_g = [sum(f[i] for f in self.center_buf_g) // n for i in range(4)]
        avg_ch = [sum(f[i] for f in self.center_buf_ch if i < len(f)) // n for i in range(33)]
        self.svc.config['center'] = {'gimbals': avg_g, 'channels': avg_ch}
        self.svc.config['phase'] = 'center_done'
        self.svc.save_config()
        self.phase = 'center_done'
        self.svc.broadcast_log(f'Center captured ({n} frames averaged).')
        self.svc.broadcast('phase', self._phase_state())

    # --- Phase 2: Range ---
    def start_range(self):
        self.phase = 'range'
        self.range_g_min = [99999]*4
        self.range_g_max = [-99999]*4
        self.range_ch_min = [99999]*33
        self.range_ch_max = [-99999]*33
        self.range_samples = 0
        self.svc.broadcast_log('Phase 2: Move ALL controls to full extremes. Go wild!')
        self.svc.broadcast('phase', self._phase_state())

    def stop_range(self):
        # Validate
        warnings = []
        for i in range(4):
            rng = self.range_g_max[i] - self.range_g_min[i]
            if rng < 300:
                warnings.append(f'G{i} range only {rng} — may not have been moved')
        self.svc.config['range'] = {
            'gimbals': {str(i): {'min': self.range_g_min[i], 'max': self.range_g_max[i]} for i in range(4)},
            'channels': {str(i): {'min': self.range_ch_min[i], 'max': self.range_ch_max[i]}
                         for i in range(33) if self.range_ch_min[i] != self.range_ch_max[i]},
            'samples': self.range_samples,
        }
        self.svc.config['phase'] = 'range_done'
        self.svc.save_config()
        self.phase = 'range_done'
        for w in warnings:
            self.svc.broadcast_log(f'Warning: {w}')
        self.svc.broadcast_log(f'Range captured ({self.range_samples} samples).')
        self.svc.broadcast('phase', self._phase_state())

    def _range_data(self):
        return {
            'g_min': self.range_g_min, 'g_max': self.range_g_max,
            'ch_min': self.range_ch_min[:33], 'ch_max': self.range_ch_max[:33],
            'samples': self.range_samples,
        }

    # --- Phase 3: Mapping ---
    def start_mapping(self):
        self.phase = 'mapping'
        self.map_step = 0
        self.map_detected = None
        if 'mapping' not in self.svc.config:
            self.svc.config['mapping'] = {}
        self.svc.config['phase'] = 'mapping'
        self.svc.save_config()
        self.svc.broadcast_log('Phase 3: Control mapping wizard started.')
        self.svc.broadcast('phase', self._phase_state())

    def _check_mapping(self, gimbals, channels):
        if self.map_step >= len(MAP_STEPS):
            return
        step = MAP_STEPS[self.map_step]
        center = self.svc.config.get('center', {})
        center_g = center.get('gimbals', [0]*4)
        center_ch = center.get('channels', [32768]*33)

        if step['detect'] == 'gimbal':
            best_i, best_d = None, 0
            for i in range(4):
                # Skip already-mapped gimbal indices
                mapped_indices = {v.get('index', v.get('channel')) for v in self.svc.config.get('mapping', {}).values()
                                  if v.get('type') == 'gimbal'}
                if i in mapped_indices:
                    continue
                d = abs(gimbals[i] - center_g[i])
                if d > best_d:
                    best_d = d
                    best_i = i
            if best_d > GIMBAL_THRESHOLD:
                self.map_detected = {
                    'type': 'gimbal', 'control': step['id'], 'label': step['label'],
                    'index': best_i, 'value': gimbals[best_i],
                    'delta': gimbals[best_i] - center_g[best_i],
                    'desc': f"Gimbal {best_i} (delta {gimbals[best_i]-center_g[best_i]:+d})",
                }
                self.svc.broadcast_log(f"Detected: {self.map_detected['desc']}")
                self.svc.broadcast('phase', self._phase_state())

        elif step['detect'] == 'channel':
            changes = []
            mapped_indices = {v.get('index', v.get('channel')) for v in self.svc.config.get('mapping', {}).values()
                              if v.get('type') == 'channel'}
            for i in range(min(len(center_ch), len(channels))):
                if i in mapped_indices:
                    continue
                d = abs(channels[i] - center_ch[i])
                if d > CHANNEL_THRESHOLD:
                    changes.append({'ch': i, 'from': center_ch[i], 'to': channels[i], 'delta': channels[i]-center_ch[i]})
            if changes:
                p = max(changes, key=lambda c: abs(c['delta']))
                self.map_detected = {
                    'type': 'channel', 'control': step['id'], 'label': step['label'],
                    'channel': p['ch'], 'from_val': p['from'], 'to_val': p['to'],
                    'delta': p['delta'], 'all': changes,
                    'desc': f"CH{p['ch']:02d} ({p['from']} -> {p['to']})",
                }
                self.svc.broadcast_log(f"Detected: {self.map_detected['desc']}")
                self.svc.broadcast('phase', self._phase_state())

    def confirm_mapping(self):
        if self.map_detected:
            self.svc.config.setdefault('mapping', {})[self.map_detected['control']] = {
                'type': self.map_detected['type'],
                'index': self.map_detected.get('index', self.map_detected.get('channel')),
                'label': self.map_detected['label'],
            }
            self.svc.broadcast_log(f"Confirmed: {self.map_detected['label']} = {self.map_detected['desc']}")
            self.svc.save_config()
        self._advance_mapping()

    def skip_mapping(self):
        self.svc.broadcast_log(f"Skipped: {MAP_STEPS[self.map_step]['label']}")
        self._advance_mapping()

    def retry_mapping(self):
        self.map_detected = None
        self.svc.broadcast_log('Retrying... return control to center.')
        self.svc.broadcast('phase', self._phase_state())

    def _advance_mapping(self):
        self.map_step += 1
        self.map_detected = None
        if self.map_step >= len(MAP_STEPS):
            self.phase = 'complete'
            self.svc.config['phase'] = 'complete'
            self.svc.save_config()
            self.svc.broadcast_log('Mapping complete! All data saved.')
        else:
            self.svc.broadcast_log(f"Step {self.map_step+1}/{len(MAP_STEPS)}: {MAP_STEPS[self.map_step]['prompt']}")
        self.svc.broadcast('phase', self._phase_state())

    # --- State export ---
    def _phase_state(self):
        step = MAP_STEPS[self.map_step] if self.phase == 'mapping' and self.map_step < len(MAP_STEPS) else None
        return {
            'phase': self.phase,
            'center': self.svc.config.get('center'),
            'range': self.svc.config.get('range'),
            'mapping': self.svc.config.get('mapping', {}),
            # Mapping wizard
            'map_step': self.map_step,
            'map_total': len(MAP_STEPS),
            'map_prompt': step['prompt'] if step else '',
            'map_label': step['label'] if step else '',
            'map_optional': step.get('optional', False) if step else False,
            'map_detected': self.map_detected,
            # Range live data
            'range_live': self._range_data() if self.phase == 'range' else None,
        }

    def reset(self):
        """Start over from scratch."""
        self.phase = 'none'
        self.svc.config = {'version': 1, 'device': 'RadioMaster AX12', 'phase': 'none'}
        self.svc.save_config()
        self.map_step = 0
        self.map_detected = None
        self.svc.broadcast_log('Reset. Ready to start calibration.')
        self.svc.broadcast('phase', self._phase_state())


# --- Routes ---

def handle_start_center(svc, req):
    cal.start_center()
    return 200, {'ok': True}

def handle_start_range(svc, req):
    cal.start_range()
    return 200, {'ok': True}

def handle_stop_range(svc, req):
    cal.stop_range()
    return 200, {'ok': True}

def handle_start_mapping(svc, req):
    cal.start_mapping()
    return 200, {'ok': True}

def handle_confirm(svc, req):
    cal.confirm_mapping()
    return 200, {'ok': True}

def handle_skip(svc, req):
    cal.skip_mapping()
    return 200, {'ok': True}

def handle_retry(svc, req):
    cal.retry_mapping()
    return 200, {'ok': True}

def handle_reset(svc, req):
    cal.reset()
    return 200, {'ok': True}

def handle_get_phase(svc, req):
    return 200, cal._phase_state()


# --- HTML UI ---

HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>AX12 Calibrator</title>
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
.dot.on{background:var(--grn);box-shadow:0 0 6px var(--grn)}.dot.off{background:var(--red)}
.main{padding:12px;display:flex;flex-direction:column;gap:12px;max-width:700px;margin:0 auto}
.card{background:var(--p);border:1px solid var(--bdr);border-radius:8px;padding:14px}
.card-title{font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--dim);
margin-bottom:8px;font-weight:600}
.phase-ind{display:flex;gap:4px;margin-bottom:12px}
.pi{flex:1;height:4px;border-radius:2px;background:#111420}
.pi.done{background:var(--grn)}.pi.active{background:var(--amb)}
/* Gimbal bars */
.gbar{display:flex;align-items:center;gap:6px;margin:4px 0;height:20px}
.gbar-label{width:24px;font-size:10px;color:var(--dim);flex-shrink:0}
.gbar-track{flex:1;height:10px;background:#111420;border-radius:3px;position:relative;overflow:hidden}
.gbar-fill{position:absolute;top:0;height:100%;background:var(--grn);border-radius:3px;
transition:left .04s linear,width .04s linear;opacity:.8}
.gbar-center{position:absolute;top:0;bottom:0;width:2px;background:var(--dim);opacity:.4}
.gbar-range{position:absolute;top:0;height:100%;background:rgba(0,232,123,.15);border-radius:3px}
.gbar-val{width:50px;font-size:10px;color:var(--grn);text-align:right;font-variant-numeric:tabular-nums}
.gbar-name{width:60px;font-size:9px;color:var(--amb);text-align:right;overflow:hidden}
/* Channel grid */
.chgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:2px 10px}
.chr{display:flex;align-items:center;gap:4px;height:16px}
.chr.hl{background:var(--hl);border-radius:3px;padding:0 3px;margin:0 -3px}
.chl{width:28px;font-size:9px;color:var(--dim);flex-shrink:0}
.chb-bg{flex:1;height:6px;background:#111420;border-radius:1px;position:relative;overflow:hidden}
.chb{height:100%;background:var(--grn);border-radius:1px;transition:width .04s linear;opacity:.8}
.chb.sw{background:var(--amb)}
.ch-name{width:40px;font-size:8px;color:var(--amb);text-align:right;overflow:hidden}
/* Sticks (post-mapping) */
.sticks{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sbox{aspect-ratio:1;background:#0a0c14;border:1px solid var(--bdr);border-radius:8px;
position:relative;max-height:150px}
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
/* Wizard */
.wiz-step{font-size:11px;color:var(--dim);margin-bottom:6px}
.wiz-prompt{font-size:15px;color:#fff;font-weight:600;margin-bottom:12px;line-height:1.4}
.wiz-state{font-size:12px;color:var(--amb);margin-bottom:12px}
.wiz-det{background:rgba(0,232,123,.08);border:1px solid rgba(0,232,123,.25);
border-radius:6px;padding:10px;margin-bottom:12px}
.wiz-det .wd-l{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:1px}
.wiz-det .wd-v{font-size:16px;color:var(--grn);font-weight:700}
.btns{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:8px 16px;border:1px solid var(--bdr);border-radius:6px;background:none;
color:var(--t);font-family:inherit;font-size:12px;cursor:pointer;transition:all .2s;
-webkit-tap-highlight-color:transparent}
.btn:active{transform:scale(.96)}
.btn-go{border-color:var(--grn);color:var(--grn);background:rgba(0,232,123,.08)}
.btn-skip{border-color:var(--dim);color:var(--dim)}
.btn-retry{border-color:var(--amb);color:var(--amb)}
.btn-red{border-color:var(--red);color:var(--red)}
/* Results */
.res-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;
border-bottom:1px solid var(--bdr)}.res-row:last-child{border:none}
.res-l{color:var(--dim)}.res-v{color:var(--grn);font-weight:600}
/* Log */
.log{max-height:140px;overflow-y:auto;font-size:11px;line-height:1.6;padding-top:6px}
.le{color:var(--dim)}.le .ts{color:var(--blu);margin-right:6px}.le .msg{color:var(--t)}
</style></head><body>
<div class="hdr">
<h1>AX12 <span>Calibrator</span></h1>
<div class="hdr-r"><span class="dot" id="dot"></span><span id="status">Connecting...</span></div>
</div>
<div class="main">

<!-- Phase indicator -->
<div class="phase-ind">
<div class="pi" id="pi1"></div><div class="pi" id="pi2"></div><div class="pi" id="pi3"></div>
</div>

<!-- Gimbal axes -->
<div class="card" id="gimbal-card">
<div class="card-title">Gimbal Axes</div>
<div id="gimbals"></div>
</div>

<!-- Sticks (hidden until mapping complete) -->
<div class="card" id="stick-card" style="display:none">
<div class="card-title">Control Sticks (Mode 2)</div>
<div class="sticks">
<div class="sbox"><svg class="sgrid" viewBox="0 0 100 100" preserveAspectRatio="none">
<line x1="50" y1="0" x2="50" y2="100" class="cl"/><line x1="0" y1="50" x2="100" y2="50" class="cl"/>
</svg><div class="cross" id="cl"></div><div class="slbl" id="sl-l">Yaw / Throttle</div></div>
<div class="sbox"><svg class="sgrid" viewBox="0 0 100 100" preserveAspectRatio="none">
<line x1="50" y1="0" x2="50" y2="100" class="cl"/><line x1="0" y1="50" x2="100" y2="50" class="cl"/>
</svg><div class="cross" id="cr"></div><div class="slbl" id="sl-r">Roll / Pitch</div></div>
</div>
</div>

<!-- Wizard / action card -->
<div class="card" id="wizard">
<div class="card-title" id="wiz-title">Calibration</div>
<div id="wiz-body">
<p style="color:var(--dim);margin-bottom:12px">3-phase calibration: center position, control range, then axis mapping.</p>
<div class="btns"><button class="btn btn-go" onclick="api('center')">Start Calibration</button></div>
</div>
</div>

<!-- Channels -->
<div class="card">
<div class="card-title">Output Channels</div>
<div class="chgrid" id="chgrid"></div>
</div>

<!-- Results -->
<div class="card" id="res-card" style="display:none">
<div class="card-title">Mapping Results</div>
<div id="res-body"></div>
</div>

<!-- Log -->
<div class="card">
<div class="card-title">Log</div>
<div class="log" id="log"></div>
</div>

<div style="text-align:center;padding:8px">
<button class="btn btn-red" onclick="if(confirm('Reset all calibration data?'))api('reset')">Reset All</button>
</div>
</div>

<script>
const $=id=>document.getElementById(id);
let center=null, mapping={}, rangeData=null;
const highlighted=new Set();

// Init gimbal bars
for(let i=0;i<4;i++){
  const d=document.createElement('div');d.className='gbar';d.id='gb-'+i;
  d.innerHTML=`<span class="gbar-label">G${i}</span>`+
    `<div class="gbar-track"><div class="gbar-range" id="gr-${i}"></div>`+
    `<div class="gbar-center" id="gc-${i}" style="left:50%"></div>`+
    `<div class="gbar-fill" id="gf-${i}"></div></div>`+
    `<span class="gbar-val" id="gv-${i}">0</span>`+
    `<span class="gbar-name" id="gn-${i}"></span>`;
  $('gimbals').appendChild(d);
}
// Init channels
for(let i=0;i<33;i++){
  const r=document.createElement('div');r.className='chr';r.id='chr-'+i;
  r.innerHTML=`<span class="chl">CH${String(i).padStart(2,'0')}</span>`+
    `<div class="chb-bg"><div class="chb" id="chb-${i}"></div></div>`+
    `<span class="ch-name" id="chn-${i}"></span>`;
  $('chgrid').appendChild(r);
}

// SSE
const es=new EventSource('/stream');
es.addEventListener('frame',e=>{
  const d=JSON.parse(e.data);
  const g=d.g, ch=d.ch;
  // Gimbal bars
  for(let i=0;i<4;i++){
    let mn=-600,mx=600;
    if(rangeData&&rangeData.gimbals&&rangeData.gimbals[i]){
      mn=rangeData.gimbals[i].min; mx=rangeData.gimbals[i].max;
    }
    const span=mx-mn||1;
    const pct=((g[i]-mn)/span)*100;
    const fill=$('gf-'+i);
    if(fill){fill.style.left=Math.min(pct,50)+'%';fill.style.width=Math.abs(pct-50)+'%';}
    const cv=$('gv-'+i);if(cv)cv.textContent=g[i];
    // Center marker
    if(center&&center.gimbals){
      const cp=((center.gimbals[i]-mn)/span)*100;
      const cm=$('gc-'+i);if(cm)cm.style.left=cp+'%';
    }
  }
  // Channels
  for(let i=0;i<Math.min(ch.length,33);i++){
    const bar=$('chb-'+i);const row=$('chr-'+i);
    if(!bar)continue;
    bar.style.width=(ch[i]/65535*100)+'%';
    bar.className='chb'+((ch[i]===65036||ch[i]===65436)?' sw':'');
    if(center&&center.channels){
      const delta=Math.abs(ch[i]-center.channels[i]);
      if(delta>500)highlighted.add(i);else if(delta<200)highlighted.delete(i);
      const want='chr'+(highlighted.has(i)?' hl':'');
      if(row.className!==want)row.className=want;
    }
  }
  // Sticks (post-mapping)
  if(Object.keys(mapping).length>=4&&$('stick-card').style.display!=='none'){
    const m=mapping;
    const cg=center?center.gimbals:[0,0,0,0];
    const R=800;
    if(m.yaw&&m.thr){
      const yi=m.yaw.index,ti=m.thr.index;
      $('cl').style.left=Math.max(5,Math.min(95,50+(g[yi]-cg[yi])/R*50))+'%';
      $('cl').style.top=Math.max(5,Math.min(95,50-(g[ti]-cg[ti])/R*50))+'%';
    }
    if(m.roll&&m.pitch){
      const ri=m.roll.index,pi_=m.pitch.index;
      $('cr').style.left=Math.max(5,Math.min(95,50+(g[ri]-cg[ri])/R*50))+'%';
      $('cr').style.top=Math.max(5,Math.min(95,50-(g[pi_]-cg[pi_])/R*50))+'%';
    }
  }
  $('status').textContent=d.fps+' Hz  #'+d.n;
});
es.addEventListener('status',e=>{
  const d=JSON.parse(e.data);
  $('dot').className='dot '+(d.connected?'on':'off');
});
es.addEventListener('log',e=>{
  const d=JSON.parse(e.data);
  const div=document.createElement('div');div.className='le';
  div.innerHTML=`<span class="ts">${d.ts}</span><span class="msg">${esc(d.msg)}</span>`;
  $('log').appendChild(div);$('log').scrollTop=$('log').scrollHeight;
});
es.addEventListener('phase',e=>{ updatePhase(JSON.parse(e.data)); });
es.addEventListener('range',e=>{
  const d=JSON.parse(e.data);
  // Live range bars
  for(let i=0;i<4;i++){
    const rng=$('gr-'+i);if(!rng)continue;
    const mn=d.g_min[i],mx=d.g_max[i];
    const span=Math.max(mx-mn,1);
    // Show range as background highlight
    const trkMn=Math.min(mn,center?center.gimbals[i]:-600);
    const trkMx=Math.max(mx,center?center.gimbals[i]:600);
    const fullSpan=trkMx-trkMn||1;
    rng.style.left=((mn-trkMn)/fullSpan*100)+'%';
    rng.style.width=(span/fullSpan*100)+'%';
  }
});
es.onerror=()=>{$('dot').className='dot off';$('status').textContent='Disconnected';};

// On connect, fetch current state
fetch('/api/phase').then(r=>r.json()).then(updatePhase);

function esc(s){return s.replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function updatePhase(p){
  center=p.center;
  mapping=p.mapping||{};
  if(p.range)rangeData=p.range;
  // Phase indicators
  const ph=p.phase;
  $('pi1').className='pi'+(['center','center_done','range','range_done','mapping','complete'].includes(ph)?
    (ph==='center'?' active':' done'):'');
  $('pi2').className='pi'+(['range','range_done','mapping','complete'].includes(ph)?
    (ph==='range'?' active':' done'):'');
  $('pi3').className='pi'+(['mapping','complete'].includes(ph)?
    (ph==='mapping'?' active':' done'):'');
  // Gimbal axis names from mapping
  for(const[name,info]of Object.entries(mapping)){
    if(info.type==='gimbal'){
      const el=$('gn-'+info.index);
      if(el)el.textContent=name.toUpperCase();
    }
  }
  // Channel names from mapping
  for(const[name,info]of Object.entries(mapping)){
    if(info.type==='channel'){
      const el=$('chn-'+info.index);
      if(el)el.textContent=name.toUpperCase();
    }
  }
  // Show sticks if all 4 axes mapped
  const hasSticks=mapping.yaw&&mapping.thr&&mapping.roll&&mapping.pitch;
  $('stick-card').style.display=hasSticks?'':'none';
  $('gimbal-card').style.display=hasSticks?'none':'';
  // Results
  if(Object.keys(mapping).length>0){
    $('res-card').style.display='';
    let html='';
    for(const[k,v]of Object.entries(mapping)){
      const idx=v.type==='gimbal'?`Gimbal ${v.index}`:`CH${String(v.index).padStart(2,'0')}`;
      html+=`<div class="res-row"><span class="res-l">${esc(v.label||k)}</span><span class="res-v">${idx}</span></div>`;
    }
    $('res-body').innerHTML=html;
  }
  // Wizard body
  renderWizard(p);
}

function renderWizard(p){
  const ph=p.phase;
  let html='';
  if(ph==='none'){
    $('wiz-title').textContent='Calibration';
    html=`<p style="color:var(--dim);margin-bottom:12px">3-phase calibration: center, range, then mapping.</p>
      <div class="btns"><button class="btn btn-go" onclick="api('center')">Start Calibration</button></div>`;
  }else if(ph==='center'){
    $('wiz-title').textContent='Phase 1 — Center';
    html=`<div class="wiz-prompt">Hands off all controls</div>
      <div class="wiz-state">Capturing center position...</div>`;
  }else if(ph==='center_done'){
    $('wiz-title').textContent='Phase 1 — Complete';
    html=`<p style="color:var(--grn);margin-bottom:10px">Center captured.</p>
      <div class="btns"><button class="btn btn-go" onclick="api('range')">Start Phase 2: Range</button></div>`;
  }else if(ph==='range'){
    $('wiz-title').textContent='Phase 2 — Range';
    html=`<div class="wiz-prompt">Move ALL controls to full extremes!</div>
      <div class="wiz-state">Recording min/max... go wild!</div>
      <div class="btns"><button class="btn btn-go" onclick="api('stoprange')">Done</button></div>`;
  }else if(ph==='range_done'){
    $('wiz-title').textContent='Phase 2 — Complete';
    html=`<p style="color:var(--grn);margin-bottom:10px">Range captured.</p>
      <div class="btns"><button class="btn btn-go" onclick="api('mapping')">Start Phase 3: Mapping</button></div>`;
  }else if(ph==='mapping'){
    $('wiz-title').textContent='Phase 3 — Mapping';
    html=`<div class="wiz-step">Step ${p.map_step+1} of ${p.map_total}${p.map_optional?' (optional)':''}</div>`;
    html+=`<div class="wiz-prompt">${esc(p.map_prompt)}</div>`;
    if(p.map_detected){
      html+=`<div class="wiz-det"><div class="wd-l">Detected</div><div class="wd-v">${esc(p.map_detected.desc)}</div></div>`;
      html+=`<div class="btns"><button class="btn btn-go" onclick="api('confirm')">Confirm</button>
        <button class="btn btn-retry" onclick="api('retry')">Retry</button>
        <button class="btn btn-skip" onclick="api('skip')">Skip</button></div>`;
    }else{
      html+=`<div class="wiz-state">Watching for changes... move the control now</div>`;
      if(p.map_optional) html+=`<div class="btns"><button class="btn btn-skip" onclick="api('skip')">Skip</button></div>`;
    }
  }else if(ph==='complete'){
    $('wiz-title').textContent='Complete';
    html=`<p style="color:var(--grn);font-weight:600;margin-bottom:10px">Calibration complete!</p>
      <p style="color:var(--dim);font-size:12px;margin-bottom:10px">Saved to docs/control-map.json</p>
      <div class="btns"><button class="btn btn-go" onclick="api('center')">Recalibrate</button></div>`;
  }
  $('wiz-body').innerHTML=html;
}

function api(a){fetch('/api/'+a,{method:'POST'});}
</script>
</body></html>"""


# --- Main ---
if __name__ == '__main__':
    demo = '--demo' in sys.argv
    svc = UMBUSService(port=8081, demo=demo)
    cal = Calibrator(svc)

    svc.add_route('POST', '/api/center', handle_start_center)
    svc.add_route('POST', '/api/range', handle_start_range)
    svc.add_route('POST', '/api/stoprange', handle_stop_range)
    svc.add_route('POST', '/api/mapping', handle_start_mapping)
    svc.add_route('POST', '/api/confirm', handle_confirm)
    svc.add_route('POST', '/api/skip', handle_skip)
    svc.add_route('POST', '/api/retry', handle_retry)
    svc.add_route('POST', '/api/reset', handle_reset)
    svc.add_route('GET', '/api/phase', handle_get_phase)

    svc.set_html(HTML)
    svc.run()
