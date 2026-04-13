#!/usr/bin/env python3
"""
Live UMBUS Dashboard — web-based real-time monitor for the AX12.

Opens in Chrome on the AX12 and shows gimbal positions, channel bars,
switch states, and frame stats via Server-Sent Events.

Usage:
    su 0 python3 tools/live_dashboard.py          # live from ttyS0
    su 0 python3 tools/live_dashboard.py --demo    # replay capture
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus_server import UMBUSService

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>AX12 Live Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #07080c; --panel: #0d0f16; --border: #1a1e2e;
  --text: #c8ccd8; --dim: #555a6e; --green: #00e87b;
  --red: #ff5544; --blue: #3399ff; --orange: #ffaa22;
}
body {
  background: var(--bg); color: var(--text);
  font-family: 'SF Mono','Cascadia Code','Fira Code',monospace;
  font-size: 13px; overflow-y: auto; padding: 12px;
}
.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0 12px; border-bottom: 1px solid var(--border); margin-bottom: 12px;
}
.header h1 { font-size: 15px; letter-spacing: 1.5px; text-transform: uppercase; color: #fff; }
.header h1 span { color: var(--green); font-weight: 400; }
.status { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--dim); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
.dot.live { background: var(--green); animation: pulse 1.5s ease infinite; }
@keyframes pulse { 50% { opacity: 0.5; } }
.badge {
  padding: 2px 8px; border-radius: 3px; font-size: 10px;
  letter-spacing: 0.5px; text-transform: uppercase; font-weight: 600;
  background: rgba(255,170,34,0.15); color: var(--orange);
}
.badge.live-badge { background: rgba(0,232,123,0.15); color: var(--green); }

/* Stats bar */
.stats {
  display: flex; gap: 20px; padding: 8px 0; font-size: 11px; color: var(--dim);
  border-bottom: 1px solid var(--border); margin-bottom: 12px;
}
.stats .val { color: var(--text); font-weight: 600; }

/* Grid layout */
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
@media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }

.section-title {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--dim); margin-bottom: 8px; font-weight: 600;
}

/* Stick visualizer */
.stick-panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px;
}
.sticks-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.stick-box {
  aspect-ratio: 1; background: #0a0c14; border: 1px solid var(--border);
  border-radius: 8px; position: relative; max-height: 180px;
}
.stick-crosshair { position: absolute; inset: 0; }
.stick-crosshair .h, .stick-crosshair .v {
  position: absolute; background: #1a1e2e;
}
.stick-crosshair .h { left: 0; right: 0; top: 50%; height: 1px; }
.stick-crosshair .v { top: 0; bottom: 0; left: 50%; width: 1px; }
.stick-dot {
  position: absolute; width: 16px; height: 16px; border-radius: 50%;
  background: var(--green); transform: translate(-50%,-50%);
  left: 50%; top: 50%; box-shadow: 0 0 8px rgba(0,232,123,0.4);
  transition: left 0.04s, top 0.04s;
}
.stick-label {
  text-align: center; font-size: 10px; color: var(--dim);
  margin-top: 6px; font-variant-numeric: tabular-nums;
}
.stick-label .coord { color: var(--text); font-weight: 600; }

/* Gimbal bars */
.gimbal-bars { margin-top: 10px; }
.gbar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.gbar-label { font-size: 10px; color: var(--dim); width: 20px; text-align: right; }
.gbar-track {
  flex: 1; height: 10px; background: #111420; border-radius: 5px;
  position: relative; overflow: hidden;
}
.gbar-center {
  position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #2a2e3e;
}
.gbar-fill {
  position: absolute; height: 100%; border-radius: 5px;
  background: var(--green); transition: left 0.04s, width 0.04s;
}
.gbar-val {
  font-size: 10px; width: 48px; text-align: right;
  font-variant-numeric: tabular-nums; color: var(--text);
}

/* Channel list */
.ch-panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px;
}
.ch-scroll { max-height: 420px; overflow-y: auto; }
.ch-row {
  display: flex; align-items: center; gap: 6px; margin-bottom: 3px;
  font-size: 11px;
}
.ch-label { width: 32px; color: var(--dim); font-size: 10px; text-align: right; }
.ch-bar-bg {
  flex: 1; height: 8px; background: #111420; border-radius: 4px;
  position: relative; overflow: hidden;
}
.ch-bar {
  height: 100%; border-radius: 4px; background: var(--blue);
  transition: width 0.04s;
}
.ch-bar.active { background: var(--green); }
.ch-bar.switch-on { background: var(--orange); }
.ch-bar.switch-mid { background: var(--orange); opacity: 0.6; }
.ch-val {
  width: 44px; text-align: right; font-size: 10px;
  font-variant-numeric: tabular-nums; color: var(--text);
}

/* Switches */
.switches-panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; margin-bottom: 12px;
}
.sw-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.sw-item {
  display: flex; flex-direction: column; align-items: center;
  padding: 6px 10px; border-radius: 6px; background: #111420;
  min-width: 52px;
}
.sw-name { font-size: 9px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.5px; }
.sw-state {
  font-size: 13px; font-weight: 700; margin-top: 2px;
  font-variant-numeric: tabular-nums;
}
.sw-state.on { color: var(--green); }
.sw-state.off { color: var(--dim); }
.sw-state.mid { color: var(--orange); }

/* Log */
.log-panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; font-size: 11px;
}
.log-line { color: var(--dim); margin-bottom: 2px; }
.log-line .ts { color: var(--blue); }
</style>
</head>
<body>

<div class="header">
  <h1>AX12 <span>LIVE</span></h1>
  <div class="status">
    <div class="dot" id="status-dot"></div>
    <span id="status-text">Connecting...</span>
    <span class="badge" id="mode-badge">--</span>
  </div>
</div>

<div class="stats">
  <span>Frames: <span class="val" id="s-frames">0</span></span>
  <span>FPS: <span class="val" id="s-fps">0</span></span>
  <span>CH: <span class="val" id="s-channels">0</span></span>
</div>

<!-- Gimbals -->
<div class="grid">
  <div class="stick-panel">
    <div class="section-title">Gimbals</div>
    <div class="sticks-row">
      <div>
        <div class="stick-box">
          <div class="stick-crosshair"><div class="h"></div><div class="v"></div></div>
          <div class="stick-dot" id="stick-l"></div>
        </div>
        <div class="stick-label">L: <span class="coord" id="sl-val">0, 0</span></div>
      </div>
      <div>
        <div class="stick-box">
          <div class="stick-crosshair"><div class="h"></div><div class="v"></div></div>
          <div class="stick-dot" id="stick-r"></div>
        </div>
        <div class="stick-label">R: <span class="coord" id="sr-val">0, 0</span></div>
      </div>
    </div>
    <div class="gimbal-bars" id="gimbal-bars"></div>
  </div>

  <!-- Channels -->
  <div class="ch-panel">
    <div class="section-title">Channels</div>
    <div class="ch-scroll" id="channels"></div>
  </div>
</div>

<!-- Switches -->
<div class="switches-panel">
  <div class="section-title">Switches</div>
  <div class="sw-grid" id="switches"></div>
</div>

<!-- Log -->
<div class="log-panel">
  <div class="section-title">Log</div>
  <div id="log"></div>
</div>

<script>
const CENTER = 32768;
const SWITCH_HIGH = 65036;
const SWITCH_MID_LO = 48000;
const SWITCH_MID_HI = 50000;
const GIMBAL_RANGE = 600;

// Gimbal bar labels
const gNames = ['LX','LY','RX','RY'];
const $gimbals = [];
const $gbarFills = [];
const $gbarVals = [];

// Init gimbal bars
const gbContainer = document.getElementById('gimbal-bars');
for (let i = 0; i < 4; i++) {
  const row = document.createElement('div');
  row.className = 'gbar-row';
  row.innerHTML = `<span class="gbar-label">${gNames[i]}</span>`
    + `<div class="gbar-track"><div class="gbar-center"></div><div class="gbar-fill" id="gf-${i}"></div></div>`
    + `<span class="gbar-val" id="gv-${i}">0</span>`;
  gbContainer.appendChild(row);
}
for (let i = 0; i < 4; i++) {
  $gbarFills.push(document.getElementById('gf-' + i));
  $gbarVals.push(document.getElementById('gv-' + i));
}

// Init channel rows
const chContainer = document.getElementById('channels');
const $chBars = [];
const $chVals = [];
for (let i = 0; i < 16; i++) {
  const row = document.createElement('div');
  row.className = 'ch-row';
  row.innerHTML = `<span class="ch-label">CH${String(i).padStart(2,'0')}</span>`
    + `<div class="ch-bar-bg"><div class="ch-bar" id="cb-${i}"></div></div>`
    + `<span class="ch-val" id="cv-${i}">--</span>`;
  chContainer.appendChild(row);
  $chBars.push(null); // filled after DOM
  $chVals.push(null);
}
// Get refs after DOM insertion
for (let i = 0; i < 16; i++) {
  $chBars[i] = document.getElementById('cb-' + i);
  $chVals[i] = document.getElementById('cv-' + i);
}

// Switch detection
const switchChannels = [4,5,6,7,8,9,10,11]; // typical switch channels
const swContainer = document.getElementById('switches');
const $swStates = [];
for (let i = 0; i < switchChannels.length; i++) {
  const ch = switchChannels[i];
  const item = document.createElement('div');
  item.className = 'sw-item';
  item.innerHTML = `<span class="sw-name">CH${String(ch).padStart(2,'0')}</span>`
    + `<span class="sw-state off" id="sw-${ch}">--</span>`;
  swContainer.appendChild(item);
  $swStates.push(document.getElementById('sw-' + ch));
}

const $stickL = document.getElementById('stick-l');
const $stickR = document.getElementById('stick-r');
const $slVal = document.getElementById('sl-val');
const $srVal = document.getElementById('sr-val');
const $frames = document.getElementById('s-frames');
const $fps = document.getElementById('s-fps');
const $nch = document.getElementById('s-channels');
const $dot = document.getElementById('status-dot');
const $statusText = document.getElementById('status-text');
const $badge = document.getElementById('mode-badge');
const $log = document.getElementById('log');

function addLog(msg) {
  const ts = new Date().toLocaleTimeString();
  const div = document.createElement('div');
  div.className = 'log-line';
  div.innerHTML = `<span class="ts">${ts}</span> ${msg}`;
  $log.prepend(div);
  while ($log.children.length > 20) $log.removeChild($log.lastChild);
}

function classifySwitch(val) {
  if (val >= SWITCH_HIGH - 500) return { text: 'ON', cls: 'on' };
  if (val >= SWITCH_MID_LO && val <= SWITCH_MID_HI) return { text: 'MID', cls: 'mid' };
  if (val <= CENTER + 500 && val >= CENTER - 500) return { text: 'OFF', cls: 'off' };
  // Proportional
  return { text: String(val), cls: val > CENTER ? 'on' : 'off' };
}

// SSE connection
const es = new EventSource('/stream');

es.addEventListener('frame', function(e) {
  const d = JSON.parse(e.data);
  const g = d.g || [0,0,0,0];
  const ch = d.ch || [];

  // Stats
  $frames.textContent = d.n;
  $fps.textContent = Math.round(d.fps);
  $nch.textContent = ch.length;

  // Stick positions
  const lx = 50 + (g[0] / GIMBAL_RANGE * 45);
  const ly = 50 - (g[1] / GIMBAL_RANGE * 45);
  const rx = 50 + (g[2] / GIMBAL_RANGE * 45);
  const ry = 50 - (g[3] / GIMBAL_RANGE * 45);
  $stickL.style.left = Math.max(5, Math.min(95, lx)) + '%';
  $stickL.style.top = Math.max(5, Math.min(95, ly)) + '%';
  $stickR.style.left = Math.max(5, Math.min(95, rx)) + '%';
  $stickR.style.top = Math.max(5, Math.min(95, ry)) + '%';
  $slVal.textContent = g[0] + ', ' + g[1];
  $srVal.textContent = g[2] + ', ' + g[3];

  // Gimbal bars (centered, bidirectional)
  for (let i = 0; i < 4; i++) {
    const v = g[i];
    const pct = Math.abs(v) / GIMBAL_RANGE * 50;
    if (v >= 0) {
      $gbarFills[i].style.left = '50%';
      $gbarFills[i].style.width = Math.min(pct, 50) + '%';
    } else {
      const w = Math.min(pct, 50);
      $gbarFills[i].style.left = (50 - w) + '%';
      $gbarFills[i].style.width = w + '%';
    }
    $gbarVals[i].textContent = v > 0 ? '+' + v : v;
  }

  // Channels
  const showN = Math.min(ch.length, 16);
  for (let i = 0; i < showN; i++) {
    const val = ch[i];
    const pct = val / 65535 * 100;
    $chBars[i].style.width = pct + '%';
    $chVals[i].textContent = val;

    // Color by type
    const sw = classifySwitch(val);
    if (val >= SWITCH_HIGH - 500 || (val <= CENTER + 500 && val >= CENTER - 500)) {
      $chBars[i].className = 'ch-bar' + (val >= SWITCH_HIGH - 500 ? ' switch-on' : '');
    } else if (Math.abs(val - CENTER) > 1000) {
      $chBars[i].className = 'ch-bar active';
    } else {
      $chBars[i].className = 'ch-bar';
    }
  }

  // Switches
  for (let si = 0; si < switchChannels.length; si++) {
    const ci = switchChannels[si];
    if (ci < ch.length) {
      const sw = classifySwitch(ch[ci]);
      $swStates[si].textContent = sw.text;
      $swStates[si].className = 'sw-state ' + sw.cls;
    }
  }
});

es.addEventListener('status', function(e) {
  const d = JSON.parse(e.data);
  if (d.connected) {
    $dot.className = 'dot live';
    $statusText.textContent = d.demo ? 'Demo mode' : 'Connected';
    $badge.textContent = d.demo ? 'DEMO' : 'LIVE';
    $badge.className = d.demo ? 'badge' : 'badge live-badge';
    addLog(d.demo ? 'Demo mode active' : 'Connected to ttyS0');
  }
});

es.addEventListener('log', function(e) {
  const d = JSON.parse(e.data);
  addLog(d.msg);
});

es.onerror = function() {
  $dot.className = 'dot';
  $statusText.textContent = 'Reconnecting...';
  addLog('Connection lost, retrying...');
};

es.onopen = function() {
  addLog('SSE stream connected');
};
</script>
</body>
</html>"""

if __name__ == '__main__':
    demo = '--demo' in sys.argv
    svc = UMBUSService(demo=demo)
    svc.set_html(DASHBOARD_HTML)
    svc.run()
