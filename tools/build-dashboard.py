#!/usr/bin/env python3
"""Generate the UMBUS Protocol Dashboard — a self-contained HTML visualizer.

Reads the timed frame data and produces a single HTML file with embedded
data, CRC-8/MAXIM decoder, and animated protocol visualization.

Usage:
    python3 tools/build-dashboard.py > dashboard.html
"""

import json
import sys
import os

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, 'captures', 'timed-frames.json')) as f:
        frames_json = f.read().strip()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UMBUS Protocol Dashboard — RadioMaster AX12</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
  --bg: #07080c;
  --panel: #0d0f16;
  --border: #1a1e2e;
  --text: #c8ccd8;
  --dim: #555a6e;
  --ch-data: #00e87b;
  --heartbeat: #ff5544;
  --elrs: #3399ff;
  --extended: #ffaa22;
  --app: #aa66ff;
  --glow-ch: rgba(0,232,123,0.15);
  --glow-hb: rgba(255,85,68,0.15);
  --glow-el: rgba(51,153,255,0.15);
  --glow-ex: rgba(255,170,34,0.15);
}}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  overflow: hidden;
  height: 100vh;
}}

.dashboard {{
  display: grid;
  grid-template-rows: auto 1fr auto auto;
  height: 100vh;
  gap: 1px;
  background: var(--border);
}}

/* Header */
.header {{
  background: var(--panel);
  padding: 12px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.header h1 {{
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: #fff;
}}
.header h1 span {{
  color: var(--ch-data);
  font-weight: 400;
}}
.header-right {{
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  color: var(--dim);
}}
.badge {{
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 10px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  font-weight: 600;
}}
.badge-live {{ background: rgba(0,232,123,0.15); color: var(--ch-data); }}
.badge-crc {{ background: rgba(51,153,255,0.15); color: var(--elrs); }}

/* Main panels */
.main {{
  display: grid;
  grid-template-columns: 1fr 340px 240px;
  gap: 1px;
  background: var(--border);
  min-height: 0;
}}

.panel {{
  background: var(--panel);
  padding: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}}
.panel-title {{
  font-size: 10px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--dim);
  margin-bottom: 10px;
  font-weight: 600;
}}

/* Hex stream */
.hex-stream {{
  flex: 1;
  overflow: hidden;
  position: relative;
}}
.hex-content {{
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
  padding: 4px;
}}
.hex-content .byte {{
  display: inline-block;
  width: 2.2ch;
  text-align: center;
  transition: opacity 0.3s;
}}
.hex-content .frame-start {{
  border-left: 2px solid;
  padding-left: 2px;
  margin-left: 2px;
}}
.hex-content .sync {{ color: #fff; font-weight: bold; }}
.hex-content .type-byte {{ font-weight: bold; }}
.hex-content .crc-byte {{ opacity: 0.7; }}
.hex-content .t-87 {{ color: var(--ch-data); }}
.hex-content .t-8 {{ color: var(--heartbeat); }}
.hex-content .t-21 {{ color: var(--elrs); }}
.hex-content .t-16 {{ color: var(--extended); }}
.hex-fade {{
  position: absolute;
  top: 0; left: 0; right: 0; height: 60px;
  background: linear-gradient(var(--panel), transparent);
  pointer-events: none;
  z-index: 1;
}}

/* Center: transmitter + channels */
.center-panel {{
  display: flex;
  flex-direction: column;
  gap: 12px;
}}

.sticks-container {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}}
.stick-box {{
  aspect-ratio: 1;
  background: #0a0c14;
  border: 1px solid var(--border);
  border-radius: 8px;
  position: relative;
  overflow: hidden;
}}
.stick-grid {{
  position: absolute;
  inset: 0;
}}
.stick-grid line {{
  stroke: #151a2a;
  stroke-width: 1;
}}
.stick-grid .center-line {{
  stroke: #1f2540;
  stroke-width: 1;
  stroke-dasharray: 4 4;
}}
.crosshair {{
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid var(--ch-data);
  box-shadow: 0 0 12px rgba(0,232,123,0.4), inset 0 0 6px rgba(0,232,123,0.15);
  transform: translate(-50%, -50%);
  transition: left 0.04s linear, top 0.04s linear;
}}
.crosshair::before, .crosshair::after {{
  content: '';
  position: absolute;
  background: var(--ch-data);
}}
.crosshair::before {{
  width: 12px; height: 1px;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
}}
.crosshair::after {{
  width: 1px; height: 12px;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
}}
.stick-label {{
  position: absolute;
  bottom: 4px;
  width: 100%;
  text-align: center;
  font-size: 9px;
  letter-spacing: 1px;
  color: var(--dim);
  text-transform: uppercase;
  z-index: 1;
}}
.stick-val {{
  position: absolute;
  top: 4px; right: 6px;
  font-size: 9px;
  color: var(--ch-data);
  opacity: 0.7;
  z-index: 1;
}}

/* Channels */
.channels-panel {{
  flex: 1;
  overflow: hidden;
}}
.channel-grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 3px 10px;
  font-size: 10px;
}}
.ch-row {{
  display: flex;
  align-items: center;
  gap: 4px;
  height: 14px;
}}
.ch-label {{
  width: 28px;
  color: var(--dim);
  font-size: 9px;
  flex-shrink: 0;
}}
.ch-bar-bg {{
  flex: 1;
  height: 6px;
  background: #111420;
  border-radius: 1px;
  overflow: hidden;
  position: relative;
}}
.ch-bar {{
  height: 100%;
  background: var(--ch-data);
  border-radius: 1px;
  transition: width 0.04s linear;
  opacity: 0.8;
}}
.ch-bar.is-switch {{
  background: var(--extended);
}}
.ch-center {{
  position: absolute;
  top: 0; bottom: 0;
  left: 50%;
  width: 1px;
  background: #2a2f44;
}}

/* Right panel: stats */
.stats-panel {{
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
.stat-block {{
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}}
.stat-block:last-child {{ border: none; }}
.stat-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  font-size: 11px;
}}
.stat-label {{ color: var(--dim); }}
.stat-value {{ color: #fff; font-weight: 600; font-variant-numeric: tabular-nums; }}
.stat-value.green {{ color: var(--ch-data); }}

.frame-type-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}}
.ft-dot {{
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.ft-dot.active {{
  box-shadow: 0 0 8px currentColor;
}}
.ft-name {{
  flex: 1;
  font-size: 10px;
  color: var(--dim);
}}
.ft-count {{
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  min-width: 30px;
  text-align: right;
}}
.ft-rate {{
  font-size: 9px;
  color: var(--dim);
  min-width: 40px;
  text-align: right;
}}

/* ELRS block */
.elrs-fields {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
}}
.elrs-field {{
  display: flex;
  flex-direction: column;
  padding: 4px 6px;
  background: #0a0c14;
  border-radius: 3px;
}}
.elrs-field .ef-label {{
  font-size: 8px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--dim);
}}
.elrs-field .ef-value {{
  font-size: 14px;
  font-weight: 600;
  color: var(--elrs);
  font-variant-numeric: tabular-nums;
}}

/* Bandwidth meter */
.bw-meter {{
  height: 6px;
  background: #111420;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 4px;
}}
.bw-fill {{
  height: 100%;
  background: linear-gradient(90deg, var(--ch-data), var(--elrs));
  border-radius: 3px;
  transition: width 0.5s;
}}

/* Dissector */
.dissector {{
  background: var(--panel);
  padding: 10px 20px;
  display: flex;
  gap: 3px;
  align-items: center;
  overflow-x: auto;
  min-height: 56px;
}}
.dissect-field {{
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2px 4px;
  border-radius: 3px;
  transition: background 0.2s;
  min-width: 0;
}}
.dissect-field .df-label {{
  font-size: 7px;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--dim);
  white-space: nowrap;
}}
.dissect-field .df-hex {{
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 1px;
}}
.dissect-field.sync .df-hex {{ color: #fff; }}
.dissect-field.type .df-hex {{ font-weight: 700; }}
.dissect-field.header .df-hex {{ opacity: 0.8; }}
.dissect-field.crc {{ }}
.dissect-field.crc.ok {{ background: rgba(0,232,123,0.1); }}
.dissect-field.crc.ok .df-hex {{ color: var(--ch-data); }}
.dissect-field.crc.bad {{ background: rgba(255,85,68,0.1); }}
.dissect-field.crc.bad .df-hex {{ color: var(--heartbeat); }}

/* Timeline / controls */
.controls {{
  background: var(--panel);
  padding: 8px 20px 12px;
  display: flex;
  align-items: center;
  gap: 16px;
}}
.play-btn {{
  width: 32px; height: 32px;
  background: none;
  border: 1.5px solid var(--dim);
  border-radius: 50%;
  color: var(--text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}}
.play-btn:hover {{ border-color: var(--ch-data); color: var(--ch-data); }}
.play-btn svg {{ width: 14px; height: 14px; fill: currentColor; }}
.timeline {{
  flex: 1;
  height: 28px;
  position: relative;
  cursor: pointer;
}}
.tl-track {{
  position: absolute;
  top: 12px;
  left: 0; right: 0;
  height: 4px;
  background: #111420;
  border-radius: 2px;
  overflow: hidden;
}}
.tl-progress {{
  height: 100%;
  background: var(--ch-data);
  border-radius: 2px;
  width: 0%;
  transition: width 0.05s linear;
}}
.tl-markers {{
  position: absolute;
  top: 4px;
  left: 0; right: 0;
  height: 6px;
}}
.tl-mark {{
  position: absolute;
  width: 2px;
  height: 100%;
  border-radius: 1px;
  opacity: 0.5;
}}
.time-display {{
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--dim);
  min-width: 80px;
  text-align: right;
  flex-shrink: 0;
}}
.speed-btns {{
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}}
.speed-btn {{
  padding: 3px 8px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--dim);
  cursor: pointer;
  font-family: inherit;
  font-size: 10px;
  transition: all 0.2s;
}}
.speed-btn:hover {{ border-color: var(--dim); color: var(--text); }}
.speed-btn.active {{
  border-color: var(--ch-data);
  color: var(--ch-data);
  background: rgba(0,232,123,0.08);
}}

/* Pulse animation for active frame type */
@keyframes pulse {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.4; }}
}}
.ft-dot.active {{
  animation: pulse 1s ease-in-out infinite;
}}

/* Responsive */
@media (max-width: 900px) {{
  .main {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="dashboard">
  <!-- Header -->
  <div class="header">
    <h1>UMBUS Protocol <span>Dashboard</span></h1>
    <div class="header-right">
      <span class="badge badge-live" id="status-badge">REPLAY</span>
      <span class="badge badge-crc" id="crc-badge">CRC-8/MAXIM</span>
      <span>RadioMaster AX12 / MT8788 + AT32 MCU / 921600 baud</span>
    </div>
  </div>

  <!-- Main -->
  <div class="main">
    <!-- Hex stream -->
    <div class="panel">
      <div class="panel-title">Protocol Stream</div>
      <div class="hex-stream">
        <div class="hex-fade"></div>
        <div class="hex-content" id="hex-stream"></div>
      </div>
    </div>

    <!-- Center: sticks + channels -->
    <div class="panel center-panel">
      <div class="panel-title">Control Surfaces</div>
      <div class="sticks-container">
        <div class="stick-box">
          <svg class="stick-grid" viewBox="0 0 100 100" preserveAspectRatio="none">
            <line x1="50" y1="0" x2="50" y2="100" class="center-line"/>
            <line x1="0" y1="50" x2="100" y2="50" class="center-line"/>
            <line x1="25" y1="0" x2="25" y2="100"/><line x1="75" y1="0" x2="75" y2="100"/>
            <line x1="0" y1="25" x2="100" y2="25"/><line x1="0" y1="75" x2="100" y2="75"/>
          </svg>
          <div class="crosshair" id="stick-l"></div>
          <div class="stick-val" id="stick-l-val">0, 0</div>
          <div class="stick-label">Left Stick</div>
        </div>
        <div class="stick-box">
          <svg class="stick-grid" viewBox="0 0 100 100" preserveAspectRatio="none">
            <line x1="50" y1="0" x2="50" y2="100" class="center-line"/>
            <line x1="0" y1="50" x2="100" y2="50" class="center-line"/>
            <line x1="25" y1="0" x2="25" y2="100"/><line x1="75" y1="0" x2="75" y2="100"/>
            <line x1="0" y1="25" x2="100" y2="25"/><line x1="0" y1="75" x2="100" y2="75"/>
          </svg>
          <div class="crosshair" id="stick-r"></div>
          <div class="stick-val" id="stick-r-val">0, 0</div>
          <div class="stick-label">Right Stick</div>
        </div>
      </div>

      <div class="panel-title" style="margin-top:4px">Output Channels</div>
      <div class="channels-panel">
        <div class="channel-grid" id="channels"></div>
      </div>
    </div>

    <!-- Stats -->
    <div class="panel stats-panel">
      <div>
        <div class="panel-title">Protocol Stats</div>
        <div class="stat-block">
          <div class="stat-row"><span class="stat-label">Frames decoded</span><span class="stat-value" id="s-frames">0</span></div>
          <div class="stat-row"><span class="stat-label">CRC verified</span><span class="stat-value green" id="s-crc-ok">0</span></div>
          <div class="stat-row"><span class="stat-label">CRC failed</span><span class="stat-value" id="s-crc-bad" style="color:var(--heartbeat)">0</span></div>
          <div class="stat-row"><span class="stat-label">Total bytes</span><span class="stat-value" id="s-bytes">0</span></div>
        </div>
      </div>

      <div>
        <div class="panel-title">Frame Types</div>
        <div id="frame-types">
          <div class="frame-type-row">
            <div class="ft-dot" id="dot-87" style="color:var(--ch-data);background:var(--ch-data)"></div>
            <span class="ft-name">0x57 Channel Data</span>
            <span class="ft-count" id="fc-87" style="color:var(--ch-data)">0</span>
            <span class="ft-rate">25 Hz</span>
          </div>
          <div class="frame-type-row">
            <div class="ft-dot" id="dot-21" style="color:var(--elrs);background:var(--elrs)"></div>
            <span class="ft-name">0x15 ELRS Telemetry</span>
            <span class="ft-count" id="fc-21" style="color:var(--elrs)">0</span>
            <span class="ft-rate">5 Hz</span>
          </div>
          <div class="frame-type-row">
            <div class="ft-dot" id="dot-8" style="color:var(--heartbeat);background:var(--heartbeat)"></div>
            <span class="ft-name">0x08 Heartbeat</span>
            <span class="ft-count" id="fc-8" style="color:var(--heartbeat)">0</span>
            <span class="ft-rate">4 Hz</span>
          </div>
          <div class="frame-type-row">
            <div class="ft-dot" id="dot-16" style="color:var(--extended);background:var(--extended)"></div>
            <span class="ft-name">0x10 Extended</span>
            <span class="ft-count" id="fc-16" style="color:var(--extended)">0</span>
            <span class="ft-rate">~3 Hz</span>
          </div>
        </div>
      </div>

      <div>
        <div class="panel-title">ELRS Link</div>
        <div class="elrs-fields">
          <div class="elrs-field"><span class="ef-label">Header</span><span class="ef-value" id="el-header">--</span></div>
          <div class="elrs-field"><span class="ef-label">Signal</span><span class="ef-value" id="el-signal">--</span></div>
          <div class="elrs-field"><span class="ef-label">Rate</span><span class="ef-value" id="el-rate">--</span></div>
          <div class="elrs-field"><span class="ef-label">Status</span><span class="ef-value" id="el-status">--</span></div>
        </div>
      </div>

      <div>
        <div class="panel-title">Bandwidth</div>
        <div class="stat-row"><span class="stat-label">Throughput</span><span class="stat-value" id="s-bw">0 B/s</span></div>
        <div class="stat-row"><span class="stat-label">Link capacity</span><span class="stat-value" style="color:var(--dim)">921,600 baud</span></div>
        <div class="bw-meter"><div class="bw-fill" id="bw-fill" style="width:0%"></div></div>
      </div>
    </div>
  </div>

  <!-- Dissector -->
  <div class="dissector" id="dissector"></div>

  <!-- Controls -->
  <div class="controls">
    <button class="play-btn" id="play-btn" title="Play/Pause">
      <svg id="play-icon" viewBox="0 0 24 24"><polygon points="6,3 20,12 6,21"/></svg>
      <svg id="pause-icon" viewBox="0 0 24 24" style="display:none"><rect x="5" y="3" width="4" height="18"/><rect x="15" y="3" width="4" height="18"/></svg>
    </button>
    <div class="timeline" id="timeline">
      <div class="tl-markers" id="tl-markers"></div>
      <div class="tl-track"><div class="tl-progress" id="tl-progress"></div></div>
    </div>
    <span class="time-display" id="time-display">0.000s / 10.000s</span>
    <div class="speed-btns">
      <button class="speed-btn" data-speed="0.5">0.5x</button>
      <button class="speed-btn active" data-speed="1">1x</button>
      <button class="speed-btn" data-speed="3">3x</button>
      <button class="speed-btn" data-speed="10">10x</button>
    </div>
  </div>
</div>

<script>
// === Embedded frame data ===
// Each entry: [timestamp_ms, frame_type, hex_string]
const FRAMES = {frames_json};

const TOTAL_DURATION = 10000; // 10 seconds
const FRAME_COLORS = {{87:'ch-data',8:'heartbeat',21:'elrs',16:'extended'}};
const FRAME_CSS = {{87:'t-87',8:'t-8',21:'t-21',16:'t-16'}};
const TYPE_NAMES = {{0x57:'CHANNEL_DATA',0x08:'HEARTBEAT',0x15:'ELRS_TELEM',0x10:'EXTENDED'}};

// CRC-8/MAXIM lookup table
const CRC8 = new Uint8Array([
  0x00,0x5E,0xBC,0xE2,0x61,0x3F,0xDD,0x83,0xC2,0x9C,0x7E,0x20,0xA3,0xFD,0x1F,0x41,
  0x9D,0xC3,0x21,0x7F,0xFC,0xA2,0x40,0x1E,0x5F,0x01,0xE3,0xBD,0x3E,0x60,0x82,0xDC,
  0x23,0x7D,0x9F,0xC1,0x42,0x1C,0xFE,0xA0,0xE1,0xBF,0x5D,0x03,0x80,0xDE,0x3C,0x62,
  0xBE,0xE0,0x02,0x5C,0xDF,0x81,0x63,0x3D,0x7C,0x22,0xC0,0x9E,0x1D,0x43,0xA1,0xFF,
  0x46,0x18,0xFA,0xA4,0x27,0x79,0x9B,0xC5,0x84,0xDA,0x38,0x66,0xE5,0xBB,0x59,0x07,
  0xDB,0x85,0x67,0x39,0xBA,0xE4,0x06,0x58,0x19,0x47,0xA5,0xFB,0x78,0x26,0xC4,0x9A,
  0x65,0x3B,0xD9,0x87,0x04,0x5A,0xB8,0xE6,0xA7,0xF9,0x1B,0x45,0xC6,0x98,0x7A,0x24,
  0xF8,0xA6,0x44,0x1A,0x99,0xC7,0x25,0x7B,0x3A,0x64,0x86,0xD8,0x5B,0x05,0xE7,0xB9,
  0x8C,0xD2,0x30,0x6E,0xED,0xB3,0x51,0x0F,0x4E,0x10,0xF2,0xAC,0x2F,0x71,0x93,0xCD,
  0x11,0x4F,0xAD,0xF3,0x70,0x2E,0xCC,0x92,0xD3,0x8D,0x6F,0x31,0xB2,0xEC,0x0E,0x50,
  0xAF,0xF1,0x13,0x4D,0xCE,0x90,0x72,0x2C,0x6D,0x33,0xD1,0x8F,0x0C,0x52,0xB0,0xEE,
  0x32,0x6C,0x8E,0xD0,0x53,0x0D,0xEF,0xB1,0xF0,0xAE,0x4C,0x12,0x91,0xCF,0x2D,0x73,
  0xCA,0x94,0x76,0x28,0xAB,0xF5,0x17,0x49,0x08,0x56,0xB4,0xEA,0x69,0x37,0xD5,0x8B,
  0x57,0x09,0xEB,0xB5,0x36,0x68,0x8A,0xD4,0x95,0xCB,0x29,0x77,0xF4,0xAA,0x48,0x16,
  0xE9,0xB7,0x55,0x0B,0x88,0xD6,0x34,0x6A,0x2B,0x75,0x97,0xC9,0x4A,0x14,0xF6,0xA8,
  0x74,0x2A,0xC8,0x96,0x15,0x4B,0xA9,0xF7,0xB6,0xE8,0x0A,0x54,0xD7,0x89,0x6B,0x35
]);
const CRC_INITS = {{0x10: 0x7F, 0x15: 0x32}};

function hexToBytes(hex) {{
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2)
    bytes[i/2] = parseInt(hex.substring(i, i+2), 16);
  return bytes;
}}

function crc8(data, init = 0) {{
  let crc = init;
  for (let i = 0; i < data.length; i++)
    crc = CRC8[data[i] ^ crc];
  return crc;
}}

function verifyCRC(bytes) {{
  if (bytes.length < 3) return false;
  if (bytes[1] === 0x08 && bytes.length === 7 && bytes[2] !== 0x35) return true;
  const init = CRC_INITS[bytes[1]] || 0;
  const computed = crc8(bytes.subarray(1, bytes.length - 1), init);
  return computed === bytes[bytes.length - 1];
}}

function readS16LE(bytes, offset) {{
  let val = bytes[offset] | (bytes[offset+1] << 8);
  if (val >= 0x8000) val -= 0x10000;
  return val;
}}

function readU16LE(bytes, offset) {{
  return bytes[offset] | (bytes[offset+1] << 8);
}}

// === State ===
let playing = false;
let speed = 1;
let currentTime = 0;
let frameIndex = 0;
let lastTimestamp = 0;
let stats = {{ frames: 0, crcOk: 0, crcBad: 0, bytes: 0, counts: {{}} }};
let hexBuffer = [];
const MAX_HEX_BYTES = 600;

// === DOM refs ===
const $hex = document.getElementById('hex-stream');
const $stickL = document.getElementById('stick-l');
const $stickR = document.getElementById('stick-r');
const $stickLVal = document.getElementById('stick-l-val');
const $stickRVal = document.getElementById('stick-r-val');
const $channels = document.getElementById('channels');
const $dissector = document.getElementById('dissector');
const $progress = document.getElementById('tl-progress');
const $timeDisplay = document.getElementById('time-display');
const $playBtn = document.getElementById('play-btn');
const $playIcon = document.getElementById('play-icon');
const $pauseIcon = document.getElementById('pause-icon');

// === Init channels ===
for (let i = 0; i < 32; i++) {{
  const row = document.createElement('div');
  row.className = 'ch-row';
  row.innerHTML = `<span class="ch-label">CH${{String(i).padStart(2,'0')}}</span>`
    + `<div class="ch-bar-bg"><div class="ch-center"></div><div class="ch-bar" id="ch-${{i}}"></div></div>`;
  $channels.appendChild(row);
}}

// === Init timeline markers ===
const $markers = document.getElementById('tl-markers');
FRAMES.forEach(([ts, type]) => {{
  const m = document.createElement('div');
  m.className = 'tl-mark';
  m.style.left = (ts / TOTAL_DURATION * 100) + '%';
  const colors = {{87:'var(--ch-data)',8:'var(--heartbeat)',21:'var(--elrs)',16:'var(--extended)'}};
  m.style.background = colors[type] || '#555';
  $markers.appendChild(m);
}});

// === Dissector ===
function dissectFrame(bytes, type) {{
  $dissector.innerHTML = '';
  const color = {{87:'var(--ch-data)',8:'var(--heartbeat)',21:'var(--elrs)',16:'var(--extended)'}}[type] || 'var(--text)';

  function addField(label, start, end, cls) {{
    const d = document.createElement('div');
    d.className = 'dissect-field ' + cls;
    const hexStr = Array.from(bytes.slice(start, end)).map(b => b.toString(16).padStart(2,'0')).join(' ');
    d.innerHTML = `<span class="df-label">${{label}}</span><span class="df-hex" style="color:${{cls==='sync'?'#fff':color}}">${{hexStr}}</span>`;
    $dissector.appendChild(d);
  }}

  addField('SYNC', 0, 1, 'sync');
  addField('TYPE', 1, 2, 'type');
  addField('HEADER', 2, 4, 'header');

  if (type === 87 || type === 0x77) {{
    addField('SUB', 4, 6, 'header');
    addField('GIMBAL 0-1', 6, 10, '');
    addField('GIMBAL 2-3', 10, 14, '');
    addField('UNK', 14, 18, '');
    addField('CHANNELS', 18, Math.min(bytes.length - 3, 50), '');
    if (bytes.length > 53) addField('...', 50, bytes.length - 3, '');
    addField('UNK', bytes.length - 3, bytes.length - 2, '');
    addField('SEQ', bytes.length - 2, bytes.length - 1, '');
  }} else if (type === 21) {{
    addField('CONST', 4, 6, '');
    addField('SIGNAL', 6, 8, '');
    addField('CONST', 8, 10, '');
    addField('CONST', 10, 13, '');
    addField('RATE', 13, 15, '');
    addField('STATUS', 15, 17, '');
    addField('SEQ', 17, 18, '');
    addField('CRC', 18, 21, '');
    return; // ELRS has multi-byte CRC region
  }} else if (type === 16) {{
    addField('DESC', 4, 5, '');
    addField('SUB-IDX', 5, 6, '');
    addField('PAYLOAD', 6, bytes.length - 1, '');
  }} else {{
    if (bytes.length > 4) addField('PAYLOAD', 4, bytes.length - 1, '');
  }}

  // CRC field
  const crcOk = verifyCRC(bytes);
  const crcDiv = document.createElement('div');
  crcDiv.className = 'dissect-field crc ' + (crcOk ? 'ok' : 'bad');
  crcDiv.innerHTML = `<span class="df-label">CRC</span><span class="df-hex">${{bytes[bytes.length-1].toString(16).padStart(2,'0')}} ${{crcOk ? '\\u2713' : '\\u2717'}}</span>`;
  $dissector.appendChild(crcDiv);
}}

// === Process frame ===
function processFrame(ts, type, hexStr) {{
  const bytes = hexToBytes(hexStr);
  const crcOk = verifyCRC(bytes);

  stats.frames++;
  stats.bytes += bytes.length;
  if (crcOk) stats.crcOk++; else stats.crcBad++;
  stats.counts[type] = (stats.counts[type] || 0) + 1;

  // Update stats display
  document.getElementById('s-frames').textContent = stats.frames;
  document.getElementById('s-crc-ok').textContent = stats.crcOk;
  document.getElementById('s-crc-bad').textContent = stats.crcBad;
  document.getElementById('s-bytes').textContent = stats.bytes.toLocaleString();

  // Frame type counts
  for (const [t, c] of Object.entries(stats.counts)) {{
    const el = document.getElementById('fc-' + t);
    if (el) el.textContent = c;
  }}

  // Activate dot
  document.querySelectorAll('.ft-dot').forEach(d => d.classList.remove('active'));
  const dot = document.getElementById('dot-' + type);
  if (dot) dot.classList.add('active');
  setTimeout(() => {{ if (dot) dot.classList.remove('active'); }}, 150);

  // Bandwidth
  const elapsed = Math.max(ts, 1) / 1000;
  const bps = Math.round(stats.bytes / elapsed);
  document.getElementById('s-bw').textContent = bps.toLocaleString() + ' B/s';
  document.getElementById('bw-fill').style.width = Math.min(bps / 115200 * 100, 100) + '%';

  // Hex stream
  const cssClass = FRAME_CSS[type] || '';
  for (let i = 0; i < bytes.length; i++) {{
    const b = bytes[i].toString(16).padStart(2, '0');
    let cls = 'byte ' + cssClass;
    if (i === 0) cls += ' frame-start sync';
    else if (i === 1) cls += ' type-byte';
    else if (i === bytes.length - 1) cls += ' crc-byte';
    hexBuffer.push(`<span class="${{cls}}">${{b}}</span>`);
  }}
  // Add space between frames
  hexBuffer.push('<span class="byte" style="opacity:0.15">|</span>');
  while (hexBuffer.length > MAX_HEX_BYTES) hexBuffer.shift();
  $hex.innerHTML = hexBuffer.join('');

  // Channel data
  if (type === 87 || type === 0x77) {{
    // Gimbals
    const g = [readS16LE(bytes,6), readS16LE(bytes,8), readS16LE(bytes,10), readS16LE(bytes,12)];
    // Map to 0-100% position (range roughly -600 to +600)
    const range = 600;
    const lx = 50 + (g[0] / range * 50);
    const ly = 50 - (g[1] / range * 50);
    const rx = 50 + (g[2] / range * 50);
    const ry = 50 - (g[3] / range * 50);
    $stickL.style.left = Math.max(5, Math.min(95, lx)) + '%';
    $stickL.style.top = Math.max(5, Math.min(95, ly)) + '%';
    $stickR.style.left = Math.max(5, Math.min(95, rx)) + '%';
    $stickR.style.top = Math.max(5, Math.min(95, ry)) + '%';
    $stickLVal.textContent = g[0] + ', ' + g[1];
    $stickRVal.textContent = g[2] + ', ' + g[3];

    // Channels
    for (let i = 0; i < 32; i++) {{
      const offset = 18 + i * 2;
      if (offset + 2 > bytes.length - 3) break;
      const val = readU16LE(bytes, offset);
      const pct = val / 65535 * 100;
      const bar = document.getElementById('ch-' + i);
      if (bar) {{
        bar.style.width = pct + '%';
        bar.className = 'ch-bar' + (val === 65036 || val === 65436 ? ' is-switch' : '');
      }}
    }}
  }}

  // ELRS telemetry
  if (type === 21) {{
    document.getElementById('el-header').textContent = bytes[2].toString(16) + ' ' + bytes[3].toString(16);
    const sig = bytes[6].toString(16) + bytes[7].toString(16);
    document.getElementById('el-signal').textContent = '0x' + sig;
    document.getElementById('el-rate').textContent = readU16LE(bytes, 13);
    const status = readU16LE(bytes, 15);
    document.getElementById('el-status').textContent = status === 0 ? 'OK' : status === 0xFFFF ? 'N/A' : '0x' + status.toString(16);
  }}

  // Dissector
  dissectFrame(bytes, type);
}}

// === Playback ===
function reset() {{
  frameIndex = 0;
  currentTime = 0;
  stats = {{ frames: 0, crcOk: 0, crcBad: 0, bytes: 0, counts: {{}} }};
  hexBuffer = [];
  $hex.innerHTML = '';
  $progress.style.width = '0%';
  $timeDisplay.textContent = '0.000s / 10.000s';
  document.getElementById('s-frames').textContent = '0';
  document.getElementById('s-crc-ok').textContent = '0';
  document.getElementById('s-crc-bad').textContent = '0';
  document.getElementById('s-bytes').textContent = '0';
  ['87','21','8','16'].forEach(t => {{
    const el = document.getElementById('fc-' + t);
    if (el) el.textContent = '0';
  }});
}}

function tick(now) {{
  if (!playing) return;

  if (!lastTimestamp) lastTimestamp = now;
  const delta = (now - lastTimestamp) * speed;
  lastTimestamp = now;
  currentTime += delta;

  // Process frames up to current time
  let processed = 0;
  while (frameIndex < FRAMES.length && FRAMES[frameIndex][0] <= currentTime) {{
    const [ts, type, hex] = FRAMES[frameIndex];
    processFrame(ts, type, hex);
    frameIndex++;
    processed++;
    if (processed > 15) break; // batch limit per frame for smooth rendering
  }}

  // Update timeline
  const pct = Math.min(currentTime / TOTAL_DURATION * 100, 100);
  $progress.style.width = pct + '%';
  $timeDisplay.textContent = (currentTime / 1000).toFixed(3) + 's / 10.000s';

  // Loop
  if (frameIndex >= FRAMES.length) {{
    playing = false;
    $playIcon.style.display = '';
    $pauseIcon.style.display = 'none';
    document.getElementById('status-badge').textContent = 'COMPLETE';
    return;
  }}

  requestAnimationFrame(tick);
}}

function togglePlay() {{
  playing = !playing;
  if (playing) {{
    if (frameIndex >= FRAMES.length) reset();
    lastTimestamp = 0;
    document.getElementById('status-badge').textContent = 'DECODING';
    $playIcon.style.display = 'none';
    $pauseIcon.style.display = '';
    requestAnimationFrame(tick);
  }} else {{
    document.getElementById('status-badge').textContent = 'PAUSED';
    $playIcon.style.display = '';
    $pauseIcon.style.display = 'none';
  }}
}}

$playBtn.addEventListener('click', togglePlay);

// Speed buttons
document.querySelectorAll('.speed-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    speed = parseFloat(btn.dataset.speed);
    document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }});
}});

// Timeline seek
document.getElementById('timeline').addEventListener('click', (e) => {{
  const rect = e.currentTarget.getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  const targetTime = pct * TOTAL_DURATION;

  // Reset and replay up to target
  reset();
  while (frameIndex < FRAMES.length && FRAMES[frameIndex][0] <= targetTime) {{
    const [ts, type, hex] = FRAMES[frameIndex];
    processFrame(ts, type, hex);
    frameIndex++;
  }}
  currentTime = targetTime;
  $progress.style.width = (pct * 100) + '%';
  $timeDisplay.textContent = (targetTime / 1000).toFixed(3) + 's / 10.000s';
  lastTimestamp = 0;
}});

// Keyboard
document.addEventListener('keydown', (e) => {{
  if (e.code === 'Space') {{ e.preventDefault(); togglePlay(); }}
}});

// Auto-play on load
window.addEventListener('load', () => {{
  setTimeout(togglePlay, 500);
}});
</script>
</body>
</html>"""

    sys.stdout.write(html)


if __name__ == '__main__':
    main()
