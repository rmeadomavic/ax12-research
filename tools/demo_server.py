#!/usr/bin/env python3
"""
RadioMaster AX12 Research - Demo Status Server

Single-file HTTP dashboard showcasing AX12 reverse engineering capabilities.
Serves a beautiful dark-themed web UI at http://<device-ip>:8080

Usage:
    python3 demo_server.py [--port 8080]

No external dependencies - stdlib only.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

# --- Configuration -----------------------------------------------------------

REPO_ROOT = Path.home() / "ax12-research"
TOOLS_DIR = REPO_ROOT / "tools"
DATA_DIR = REPO_ROOT / "data"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def run_cmd(cmd, timeout=5):
    """Run a shell command, return stdout or error string."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else f"[error] {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "[timeout]"
    except Exception as e:
        return f"[exception] {e}"


def get_device_info():
    """Gather device information via Android props and /proc."""
    info = {}
    info["model"] = run_cmd("getprop ro.product.model")
    info["android_version"] = run_cmd("getprop ro.build.version.release")
    info["kernel"] = run_cmd("uname -r")
    info["build"] = run_cmd("getprop ro.build.display.id")
    info["soc"] = run_cmd("getprop ro.hardware") or "MT8788"
    info["cpu_cores"] = run_cmd("nproc")
    info["cpu_arch"] = run_cmd("uname -m")

    # RAM
    meminfo = run_cmd("cat /proc/meminfo")
    for line in meminfo.split("\n"):
        if line.startswith("MemTotal:"):
            kb = int(line.split()[1])
            info["ram_total"] = f"{kb // 1024} MB"
        elif line.startswith("MemAvailable:"):
            kb = int(line.split()[1])
            info["ram_available"] = f"{kb // 1024} MB"

    # Storage
    df_out = run_cmd("df /data | tail -1")
    if df_out and not df_out.startswith("["):
        parts = df_out.split()
        if len(parts) >= 4:
            info["storage_total"] = f"{int(parts[1]) // 1024} MB"
            info["storage_used"] = f"{int(parts[2]) // 1024} MB"
            info["storage_avail"] = f"{int(parts[3]) // 1024} MB"

    # Uptime
    info["uptime"] = run_cmd("uptime -p") or run_cmd("cat /proc/uptime").split()[0] + "s"

    return info


def get_calibration():
    """Read calibration.json if available."""
    cal_path = REPO_ROOT / "calibration.json"
    try:
        result = subprocess.run(
            ["su", "0", "cat", str(cal_path)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    # Try without root
    try:
        if cal_path.exists():
            return json.loads(cal_path.read_text())
    except Exception:
        pass
    return None


def get_model_list():
    """List model backup files."""
    try:
        for d in sorted(DATA_DIR.iterdir()):
            if d.is_dir() and "model-backup" in d.name:
                files = sorted(d.iterdir())
                return [f.name for f in files if f.suffix == ".rcm"]
    except Exception:
        pass
    return []


def check_process(name):
    """Check if a process is running."""
    result = run_cmd(f"pgrep -f '{name}'")
    return bool(result and not result.startswith("["))


# --- HTML Template -----------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RadioMaster AX12 Research</title>
<style>
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-card: #1c2128;
    --bg-hover: #262c36;
    --border: #30363d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --accent-blue: #58a6ff;
    --accent-green: #3fb950;
    --accent-orange: #d29922;
    --accent-red: #f85149;
    --accent-purple: #bc8cff;
    --accent-cyan: #39c5cf;
    --radius: 8px;
    --shadow: 0 2px 8px rgba(0,0,0,0.3);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
}

.header {
    background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
    border-bottom: 1px solid var(--border);
    padding: 1.5rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.logo {
    width: 52px;
    height: 52px;
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
    font-weight: 800;
    color: white;
    letter-spacing: -0.5px;
    font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
}

.header .subtitle {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-green);
    margin-right: 0.5rem;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 1.5rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 1.5rem;
}

.card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    box-shadow: var(--shadow);
    transition: border-color 0.2s;
}

.card:hover {
    border-color: rgba(88,166,255,0.4);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
}

.card-header h2 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
}

.card-icon {
    font-size: 1.1rem;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    background: var(--bg-secondary);
}

.info-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.4rem 1rem;
    font-size: 0.875rem;
}

.info-grid dt {
    color: var(--text-secondary);
    font-weight: 500;
}

.info-grid dd {
    color: var(--text-primary);
    font-family: 'SF Mono', 'Cascadia Code', monospace;
    font-size: 0.8rem;
}

.badge {
    display: inline-flex;
    align-items: center;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

.badge-ready { background: rgba(63,185,80,0.15); color: var(--accent-green); border: 1px solid rgba(63,185,80,0.3); }
.badge-active { background: rgba(88,166,255,0.15); color: var(--accent-blue); border: 1px solid rgba(88,166,255,0.3); }
.badge-missing { background: rgba(248,81,73,0.15); color: var(--accent-red); border: 1px solid rgba(248,81,73,0.3); }
.badge-partial { background: rgba(210,153,34,0.15); color: var(--accent-orange); border: 1px solid rgba(210,153,34,0.3); }
.badge-decoded { background: rgba(188,140,255,0.15); color: var(--accent-purple); border: 1px solid rgba(188,140,255,0.3); }

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
}

table th {
    text-align: left;
    padding: 0.5rem 0.75rem;
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border);
}

table td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(48,54,61,0.5);
    color: var(--text-primary);
}

table tr:hover td {
    background: var(--bg-hover);
}

.tool-name {
    font-family: 'SF Mono', 'Cascadia Code', monospace;
    color: var(--accent-cyan);
    font-size: 0.78rem;
}

.btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 500;
    border: 1px solid var(--border);
    background: var(--bg-secondary);
    color: var(--text-primary);
    cursor: pointer;
    transition: all 0.15s;
    text-decoration: none;
}

.btn:hover {
    background: var(--bg-hover);
    border-color: var(--accent-blue);
    color: var(--accent-blue);
}

.btn-danger:hover {
    border-color: var(--accent-red);
    color: var(--accent-red);
}

.btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.protocol-box {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.75rem;
    font-family: 'SF Mono', 'Cascadia Code', monospace;
    font-size: 0.78rem;
    color: var(--text-secondary);
    overflow-x: auto;
    line-height: 1.8;
}

.protocol-box .hl {
    color: var(--accent-blue);
    font-weight: 600;
}

.protocol-box .val {
    color: var(--accent-green);
}

.stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0;
}

.stat-row + .stat-row {
    border-top: 1px solid rgba(48,54,61,0.4);
}

.stat-label { color: var(--text-secondary); font-size: 0.8rem; }
.stat-value { color: var(--text-primary); font-weight: 600; font-size: 0.85rem; font-family: monospace; }

.cal-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
}

.cal-item {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.6rem;
    text-align: center;
}

.cal-item .name {
    font-size: 0.7rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
    font-weight: 600;
}

.cal-item .ch {
    font-size: 0.8rem;
    color: var(--accent-cyan);
    font-family: monospace;
    font-weight: 600;
}

.cal-item .range {
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-top: 0.2rem;
    font-family: monospace;
}

.about-text {
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.7;
}

.about-text a {
    color: var(--accent-blue);
    text-decoration: none;
}

.about-text a:hover {
    text-decoration: underline;
}

.arch-diagram {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem 1.25rem;
    font-family: 'SF Mono', 'Cascadia Code', 'Courier New', monospace;
    font-size: 0.72rem;
    line-height: 1.5;
    color: var(--text-secondary);
    overflow-x: auto;
    white-space: pre;
}

.arch-diagram .n { color: var(--accent-blue); }
.arch-diagram .p { color: var(--accent-orange); font-weight: 600; }
.arch-diagram .h { color: var(--accent-green); }

.footer-note {
    text-align: center;
    padding: 1.5rem;
    color: var(--text-muted);
    font-size: 0.75rem;
    border-top: 1px solid var(--border);
    margin-top: 1rem;
}

.full-width {
    grid-column: 1 / -1;
}

#action-result {
    margin-top: 1rem;
    display: none;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-family: 'SF Mono', 'Cascadia Code', monospace;
    font-size: 0.75rem;
    color: var(--accent-green);
    max-height: 200px;
    overflow-y: auto;
    white-space: pre-wrap;
}

.switch-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.5rem;
}

.switch-tag {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.15rem 0.45rem;
    font-size: 0.7rem;
    font-family: monospace;
    color: var(--accent-purple);
}

.model-item {
    font-family: monospace;
    font-size: 0.75rem;
    padding: 0.25rem 0;
    color: var(--text-primary);
    border-bottom: 1px solid rgba(48,54,61,0.3);
}

.model-item:last-child { border-bottom: none; }

@media (max-width: 840px) {
    .container {
        grid-template-columns: 1fr;
        padding: 1rem;
    }
    .header {
        padding: 1rem;
    }
    .header h1 {
        font-size: 1.2rem;
    }
    .cal-grid {
        grid-template-columns: 1fr;
    }
}
</style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <div class="logo">AX12</div>
        <div>
            <h1>RadioMaster AX12 Research</h1>
            <div class="subtitle"><span class="status-dot"></span>Live on {{DEVICE_IP}} &mdash; Reverse Engineering Dashboard</div>
        </div>
    </div>
    <div style="font-size:0.75rem; color:var(--text-muted);">
        Refreshed: <span id="refresh-time">{{TIMESTAMP}}</span>
    </div>
</div>

<div class="container">

    <!-- Device Info -->
    <div class="card">
        <div class="card-header">
            <div class="card-icon">&#x1F4F1;</div>
            <h2>Device Information</h2>
        </div>
        <dl class="info-grid">
            <dt>Model</dt><dd>{{DEV_MODEL}}</dd>
            <dt>Android</dt><dd>{{DEV_ANDROID}}</dd>
            <dt>Kernel</dt><dd>{{DEV_KERNEL}}</dd>
            <dt>SoC</dt><dd>MediaTek MT8788 (4&#215;A53 + 4&#215;A73)</dd>
            <dt>MCU</dt><dd>AT32F435 Cortex-M4F @ 288 MHz</dd>
            <dt>CPU Arch</dt><dd>{{DEV_ARCH}} ({{DEV_CORES}} cores)</dd>
            <dt>RAM</dt><dd>{{DEV_RAM_AVAIL}} free / {{DEV_RAM_TOTAL}}</dd>
            <dt>Storage</dt><dd>{{DEV_STORAGE_AVAIL}} free / {{DEV_STORAGE_TOTAL}}</dd>
            <dt>Uptime</dt><dd>{{DEV_UPTIME}}</dd>
            <dt>Build</dt><dd style="font-size:0.7rem;">{{DEV_BUILD}}</dd>
        </dl>
    </div>

    <!-- Hardware Capabilities -->
    <div class="card">
        <div class="card-header">
            <div class="card-icon">&#x1F527;</div>
            <h2>Hardware Capabilities</h2>
        </div>
        <table>
            <thead><tr><th>Peripheral</th><th>Status</th><th>Notes</th></tr></thead>
            <tbody>
                <tr><td>FM Radio (MT6631)</td><td><span class="badge badge-ready">Ready</span></td><td>87.5&ndash;108 MHz, /dev/fm</td></tr>
                <tr><td>GPS (MT6631)</td><td><span class="badge badge-missing">No fix</span></td><td>GNSS stack runs but no antenna populated &mdash; zero satellites, unusable without HW mod</td></tr>
                <tr><td>Bluetooth</td><td><span class="badge badge-ready">Ready</span></td><td>A2DP, BLE, MIDI capable</td></tr>
                <tr><td>USB OTG Host</td><td><span class="badge badge-ready">Ready</span></td><td>Sysfs toggle, VBUS power</td></tr>
                <tr><td>WiFi (MT6631)</td><td><span class="badge badge-active">Active</span></td><td>Tailscale connected</td></tr>
                <tr><td>HDMI In (RN6752M)</td><td><span class="badge badge-ready">Ready</span></td><td>Analog &#8594; MIPI CSI-2</td></tr>
                <tr><td>HDMI Out (IT66121)</td><td><span class="badge badge-ready">Ready</span></td><td>1.4 via I2C bridge</td></tr>
                <tr><td>IMU (ICM-42607)</td><td><span class="badge badge-ready">Ready</span></td><td>6-axis accel/gyro</td></tr>
                <tr><td>ELRS (LR1121)</td><td><span class="badge badge-active">Active</span></td><td>Internal + ext. module bay</td></tr>
                <tr><td>Cameras</td><td><span class="badge badge-partial">HAL Only</span></td><td>ISP pipeline, no lens</td></tr>
                <tr><td>NFC</td><td><span class="badge badge-missing">Not Present</span></td><td>SoC supports, not wired</td></tr>
                <tr><td>Cellular</td><td><span class="badge badge-missing">No SIM</span></td><td>Baseband active, unused</td></tr>
            </tbody>
        </table>
    </div>

    <!-- UMBUS Protocol -->
    <div class="card">
        <div class="card-header">
            <div class="card-icon">&#x1F4E1;</div>
            <h2>UMBUS Protocol</h2>
            <span class="badge badge-decoded" style="margin-left:auto;">Fully Decoded</span>
        </div>
        <div class="protocol-box">
<span class="hl">UART:</span>  /dev/ttyS0 @ <span class="val">921,600</span> baud (8N1)
<span class="hl">Link:</span>  ~<span class="val">2.4 KB/s</span> of 115.2 KB/s (<span class="val">2%</span> utilization)
<span class="hl">CRC:</span>   CRC-8/MAXIM poly <span class="val">0x31</span>, per-type init values
<span class="hl">Chans:</span> <span class="val">33</span> channels (CH00-CH32), 16-bit signed
        </div>
        <table>
            <thead><tr><th>Type</th><th>Dir</th><th>Rate</th><th>Purpose</th></tr></thead>
            <tbody>
                <tr><td><code style="color:var(--accent-purple)">0x57</code></td><td>MCU &#8594; App</td><td>25 Hz</td><td>Channel data (87 B)</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x08</code></td><td>Bidir</td><td>4 Hz</td><td>Heartbeat / ACK</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x15</code></td><td>MCU &#8594; App</td><td>5 Hz</td><td>ELRS RF telemetry</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x10</code></td><td>MCU &#8594; App</td><td>~3 Hz</td><td>Extended status</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x0E</code></td><td>App &#8594; MCU</td><td>2 Hz</td><td>Config / polling</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x0C</code></td><td>App &#8594; MCU</td><td>2 Hz</td><td>State command</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x07</code></td><td>App &#8594; MCU</td><td>0.5 Hz</td><td>Mode control</td></tr>
                <tr><td><code style="color:var(--accent-purple)">0x09</code></td><td>App &#8594; MCU</td><td>On demand</td><td>Config write</td></tr>
            </tbody>
        </table>
    </div>

    <!-- Architecture Diagram -->
    <div class="card full-width">
        <div class="card-header">
            <div class="card-icon">&#x1F3D7;&#xFE0F;</div>
            <h2>System Architecture</h2>
        </div>
        <div class="arch-diagram"><span class="n">&#x250C;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2510;</span>  <span class="p">UART @ 921600</span>   <span class="n">&#x250C;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2510;</span>  <span class="p">CRSF/SPI</span>  <span class="h">&#x250C;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2510;</span>
<span class="n">&#x2502;  MT8788 SoC  &#x2502;</span>&#x25C4;&#x2500;&#x2500;<span class="p">  UMBUS  </span>&#x2500;&#x2500;&#x25BA;<span class="n">&#x2502;  AT32   &#x2502;</span>&#x25C4;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x25BA;<span class="h">&#x2502; ELRS TX  &#x2502;</span>
<span class="n">&#x2502;  Android 9   &#x2502;</span>                  <span class="n">&#x2502;  F435   &#x2502;</span>          <span class="h">&#x2502; LR1121   &#x2502;</span>
<span class="n">&#x2502;  Flyshark    &#x2502;</span>                  <span class="n">&#x2502;         &#x2502;</span>          <span class="h">&#x2514;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2518;</span>
<span class="n">&#x2502;  Qt6 + Lua   &#x2502;</span>                  <span class="n">&#x2502; Gimbals &#x2502;</span>
<span class="n">&#x2514;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2518;</span>                  <span class="n">&#x2502; Switches&#x2502;</span>
       <span class="p">&#x2502;</span>                           <span class="n">&#x2502; Pots    &#x2502;</span>
       <span class="p">&#x2502;</span> WiFi / USB                <span class="n">&#x2514;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2518;</span>
       <span class="p">&#x2502;</span>
  <span class="h">&#x250C;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2510;</span>
  <span class="h">&#x2502; This Server &#x2502;</span>  &#x25C4;&#x2500;&#x2500; you are here
  <span class="h">&#x2502; Python 3.13 &#x2502;</span>
  <span class="h">&#x2514;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2500;&#x2518;</span></div>
    </div>

    <!-- Tools Inventory -->
    <div class="card full-width">
        <div class="card-header">
            <div class="card-icon">&#x1F9F0;</div>
            <h2>Tools Inventory</h2>
            <span style="margin-left:auto; font-size:0.75rem; color:var(--text-muted);">{{TOOL_COUNT}} tools &mdash; Python 3.13, stdlib only</span>
        </div>
        <table>
            <thead><tr><th>Tool</th><th>Category</th><th>Description</th><th>Status</th></tr></thead>
            <tbody>
                <tr><td class="tool-name">umbus.py</td><td>Protocol</td><td>UMBUS frame parsing, CRC validation, encoding</td><td><span class="badge badge-ready">Core Lib</span></td></tr>
                <tr><td class="tool-name">monitor.py</td><td>Live</td><td>Real-time TUI channel/gimbal viewer with delta tracking</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">calibrator.py</td><td>Hardware</td><td>3-phase interactive gimbal/switch calibration &amp; mapping</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">live_dashboard.py</td><td>Web</td><td>Real-time protocol visualization via SSE</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">umbus_server.py</td><td>Server</td><td>SSE broadcast server for live UMBUS frames</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">cot_bridge.py</td><td>Integration</td><td>MAVLink-to-Cursor-on-Target bridge for ATAK</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">doom-controller.py</td><td>Demo</td><td>Play DOOM with AX12 hall-effect gimbals &amp; switches</td><td><span class="badge badge-active">Demo</span></td></tr>
                <tr><td class="tool-name">fm_radio.py</td><td>Hardware</td><td>FM radio tuner (87.5&ndash;108 MHz) via MT6631 ioctls</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">gps_position.py</td><td>Hardware</td><td>GPS position reader via Android location API</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">usb_otg.py</td><td>Hardware</td><td>USB OTG host/device mode switcher via sysfs</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">model_tool.py</td><td>Config</td><td>Radio model file (.rcm) parser, backup, and analysis</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">capture-session.py</td><td>Research</td><td>Structured control input recording with labels</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">batch-capture.py</td><td>Research</td><td>Non-interactive timed batch capture</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">live-mapper.py</td><td>Research</td><td>Interactive real-time control-to-channel mapping</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">strace-parser.py</td><td>Research</td><td>Extract &amp; decode UMBUS frames from strace output</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">optimize.py</td><td>System</td><td>Safe performance optimizer (governor, bloatware, camera)</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">latency-test.py</td><td>Video</td><td>HDMI pipeline glass-to-glass latency measurement</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">simulator.py</td><td>Dev</td><td>Synthetic UMBUS traffic generator for offline testing</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">build-dashboard.py</td><td>Dev</td><td>Generate self-contained HTML protocol dashboard</td><td><span class="badge badge-ready">Ready</span></td></tr>
                <tr><td class="tool-name">firewall.sh</td><td>Security</td><td>iptables rules: block telemetry, restrict inbound</td><td><span class="badge badge-ready">Ready</span></td></tr>
            </tbody>
        </table>
    </div>

    <!-- Calibration Data -->
    <div class="card">
        <div class="card-header">
            <div class="card-icon">&#x1F3AF;</div>
            <h2>Calibration Data</h2>
            {{CAL_BADGE}}
        </div>
        {{CAL_CONTENT}}
    </div>

    <!-- Quick Actions -->
    <div class="card">
        <div class="card-header">
            <div class="card-icon">&#x26A1;</div>
            <h2>Quick Actions</h2>
        </div>
        <div class="btn-group">
            <a class="btn" href="/action/doom-start" onclick="doAction(this);return false;">&#x1F47E; Start DOOM</a>
            <a class="btn btn-danger" href="/action/doom-stop" onclick="doAction(this);return false;">&#x1F6D1; Stop DOOM</a>
            <a class="btn" href="/action/model-backup" onclick="doAction(this);return false;">&#x1F4BE; Backup Models</a>
            <a class="btn" href="/action/cot-test" onclick="doAction(this);return false;">&#x1F4E1; Test CoT</a>
            <a class="btn" href="/action/fm-scan" onclick="doAction(this);return false;">&#x1F4FB; FM Scan</a>
            <a class="btn" href="/action/usb-host" onclick="doAction(this);return false;">&#x1F50C; USB Host On</a>
            <a class="btn" href="/action/refresh" onclick="location.reload();return false;">&#x1F504; Refresh</a>
        </div>
        <div id="action-result"></div>
    </div>

    <!-- Model Files -->
    <div class="card">
        <div class="card-header">
            <div class="card-icon">&#x2708;&#xFE0F;</div>
            <h2>Radio Models</h2>
        </div>
        {{MODEL_CONTENT}}
    </div>

    <!-- Key Findings -->
    <div class="card full-width">
        <div class="card-header">
            <div class="card-icon">&#x1F50D;</div>
            <h2>Key Findings</h2>
        </div>
        <table>
            <thead><tr><th>Discovery</th><th>Detail</th></tr></thead>
            <tbody>
                <tr><td><strong>UMBUS Protocol</strong></td><td>8 frame types, 25 Hz channel data, CRC-8/MAXIM with per-type init values. 100% checksum validation.</td></tr>
                <tr><td><strong>33 Output Channels</strong></td><td>CH00-CH32, 16-bit signed, per-channel reverse/slow/limits/curves/dual-rates/mixing.</td></tr>
                <tr><td><strong>Factory Root</strong></td><td>SUID binary at /system/xbin/su. userdebug build, test-keys, SELinux permissive. No exploit needed.</td></tr>
                <tr><td><strong>FM Radio</strong></td><td>MT6631 combo chip, 87.5-108 MHz via /dev/fm ioctls. Headphone cable = antenna.</td></tr>
                <tr><td><strong>MCU Autonomous</strong></td><td>AT32F435 broadcasts all frame types at full rate without Flyshark app running.</td></tr>
                <tr><td><strong>Lua VM + LVGL</strong></td><td>Embedded Lua 5.3 with bitmap, etxdir, and full LVGL UI framework. EdgeTX-compatible API.</td></tr>
                <tr><td><strong>USB OTG Host</strong></td><td>Top USB-C exposes a host-mode role switch via 3 sysfs writes. Sysfs toggle responsive; host-mode untested on hardware.</td></tr>
                <tr><td><strong>HDMI Latency</strong></td><td>RN6752M routed through full ISP pipeline (22+ tuning libs). 5 CAMSV DMA engines available for bypass.</td></tr>
                <tr><td><strong>Cellular Modem</strong></td><td>MT8788 baseband runs LTE firmware. 21 interfaces exist but no SIM/antenna on PCB.</td></tr>
                <tr><td><strong>ELRS Backpack WiFi</strong></td><td>ESP chip creates WiFi AP, forwards MAVLink UDP:14550 to QGC/ATAK/Mission Planner.</td></tr>
            </tbody>
        </table>
    </div>

    <!-- About -->
    <div class="card full-width">
        <div class="card-header">
            <div class="card-icon">&#x1F4D6;</div>
            <h2>About This Project</h2>
        </div>
        <div class="about-text">
            <p>The <strong>RadioMaster AX12 Research</strong> project is a community-built technical reference for the
            RadioMaster AX12, an Android-based RC transmitter. Everything here was reverse-engineered from a stock
            device &mdash; no manufacturer documentation exists for these internals.</p>
            <br>
            <p>The AX12 runs Android 9 on a MediaTek MT8788 SoC, communicating with an AT32F435 microcontroller over
            a proprietary serial protocol called <strong>UMBUS</strong>. This project decodes the protocol, maps the
            hardware, analyzes the 25 MB native library (13,000+ symbols), and provides 20+ Python tools for passive
            monitoring and protocol analysis. All data was captured non-invasively via <code>strace</code>.</p>
            <br>
            <p>
                <a href="https://github.com/rmeadomavic/ax12-research" target="_blank">GitHub: rmeadomavic/ax12-research</a>
                &nbsp;&bull;&nbsp; MIT License &nbsp;&bull;&nbsp; Python 3.13, stdlib only &nbsp;&bull;&nbsp; Kyle Adomavicius
            </p>
        </div>
    </div>

</div>

<div class="footer-note">
    RadioMaster AX12 Research Dashboard &mdash; serving from {{DEVICE_IP}}:{{PORT}}<br>
    Built with Python stdlib &middot; No external dependencies &middot; Single-file deployment
</div>

<script>
async function doAction(el) {
    const url = el.getAttribute('href');
    const box = document.getElementById('action-result');
    box.style.display = 'block';
    box.textContent = 'Running...';
    box.style.color = 'var(--text-secondary)';
    try {
        const resp = await fetch(url);
        const data = await resp.json();
        box.textContent = data.output || data.error || 'Done';
        box.style.color = data.error ? 'var(--accent-red)' : 'var(--accent-green)';
    } catch(e) {
        box.textContent = 'Error: ' + e.message;
        box.style.color = 'var(--accent-red)';
    }
}
</script>

</body>
</html>"""


# --- HTTP Handler ------------------------------------------------------------

class DemoHandler(BaseHTTPRequestHandler):
    """Handle requests for the demo dashboard."""

    server_version = "AX12-Demo/1.0"

    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        sys.stderr.write(f"[{ts}] {args[0]}\n")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.serve_dashboard()
        elif path.startswith("/action/"):
            self.handle_action(path[8:])
        elif path == "/api/status":
            self.serve_json(get_device_info())
        elif path == "/api/calibration":
            cal = get_calibration()
            self.serve_json(cal if cal else {"error": "not available"})
        else:
            self.send_error(404)

    def serve_dashboard(self):
        html = self.render_page()
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def serve_json(self, data):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def handle_action(self, action):
        actions = {
            "doom-start": "su 0 nohup python3 {tools}/doom-controller.py > /dev/null 2>&1 & echo 'DOOM controller started (PID '$!')'",
            "doom-stop": "pkill -f doom-controller.py && echo 'Stopped' || echo 'Not running'",
            "model-backup": "python3 {tools}/model_tool.py backup 2>&1 | tail -5",
            "cot-test": "timeout 5 python3 {tools}/test_cot.py 2>&1 | tail -10",
            "fm-scan": "su 0 timeout 5 python3 {tools}/fm_radio.py --scan 2>&1 | tail -10",
            "usb-host": "su 0 python3 {tools}/usb_otg.py --enable 2>&1 | tail -5",
        }

        if action not in actions:
            self.serve_json({"error": f"Unknown action: {action}"})
            return

        cmd = actions[action].format(tools=TOOLS_DIR)
        output = run_cmd(cmd, timeout=15)
        self.serve_json({"action": action, "output": output})

    def render_page(self):
        info = get_device_info()
        cal = get_calibration()
        models = get_model_list()
        host = self.headers.get("Host", "100.87.134.108:8080")
        ip = host.split(":")[0]
        port = str(self.server.server_address[1])

        html = HTML_PAGE

        # Substitutions
        replacements = {
            "{{DEVICE_IP}}": ip,
            "{{PORT}}": port,
            "{{TIMESTAMP}}": time.strftime("%Y-%m-%d %H:%M:%S"),
            "{{DEV_MODEL}}": info.get("model", "RadioMaster AX12"),
            "{{DEV_ANDROID}}": info.get("android_version", "9"),
            "{{DEV_KERNEL}}": info.get("kernel", "4.4.146"),
            "{{DEV_ARCH}}": info.get("cpu_arch", "aarch64"),
            "{{DEV_CORES}}": info.get("cpu_cores", "8"),
            "{{DEV_RAM_TOTAL}}": info.get("ram_total", "4096 MB"),
            "{{DEV_RAM_AVAIL}}": info.get("ram_available", "N/A"),
            "{{DEV_STORAGE_TOTAL}}": info.get("storage_total", "64 GB"),
            "{{DEV_STORAGE_AVAIL}}": info.get("storage_avail", "N/A"),
            "{{DEV_UPTIME}}": info.get("uptime", "N/A"),
            "{{DEV_BUILD}}": info.get("build", "userdebug"),
        }

        for key, val in replacements.items():
            html = html.replace(key, val)

        # Tool count
        try:
            tool_count = len([f for f in TOOLS_DIR.iterdir()
                            if f.suffix in (".py", ".sh") and f.name != "__init__.py"])
        except Exception:
            tool_count = 21
        html = html.replace("{{TOOL_COUNT}}", str(tool_count))

        # Calibration section
        if cal and "gimbals" in cal:
            cal_badge = '<span class="badge badge-ready" style="margin-left:auto;">Calibrated</span>'
            gimbals = cal.get("gimbals", {})
            switches = cal.get("switches", {})
            cal_html = '<div class="cal-grid">'
            for name, data in gimbals.items():
                cal_html += (
                    f'<div class="cal-item">'
                    f'<div class="name">{name}</div>'
                    f'<div class="ch">CH{data["channel"]}</div>'
                    f'<div class="range">{data["min"]} / {data["center"]} / {data["max"]}</div>'
                    f'</div>'
                )
            cal_html += '</div>'
            if switches:
                cal_html += '<div class="switch-list" style="margin-top:0.75rem;">'
                for sw_name, sw_data in switches.items():
                    sw_type = sw_data.get("type", "?")
                    cal_html += f'<span class="switch-tag">{sw_name} ({sw_type})</span>'
                cal_html += '</div>'
            cal_html += (
                f'<div style="margin-top:0.5rem; font-size:0.7rem; color:var(--text-muted);">'
                f'Updated: {cal.get("updated", "unknown")}</div>'
            )
        else:
            cal_badge = '<span class="badge badge-partial" style="margin-left:auto;">Not Loaded</span>'
            cal_html = (
                '<p style="color:var(--text-secondary); font-size:0.85rem;">'
                'Calibration data requires root to read.<br>'
                'Run <code style="color:var(--accent-cyan)">su 0 python3 calibrator.py</code></p>'
            )

        html = html.replace("{{CAL_BADGE}}", cal_badge)
        html = html.replace("{{CAL_CONTENT}}", cal_html)

        # Model files
        if models:
            model_html = (
                f'<p style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.5rem;">'
                f'{len(models)} model file{"s" if len(models) != 1 else ""} backed up:</p>'
                f'<div style="max-height:180px; overflow-y:auto;">'
            )
            for m in models[:25]:
                model_html += f'<div class="model-item">{m}</div>'
            if len(models) > 25:
                model_html += (
                    f'<div style="color:var(--text-muted); font-size:0.7rem; padding:0.3rem 0;">'
                    f'...and {len(models) - 25} more</div>'
                )
            model_html += '</div>'
        else:
            model_html = (
                '<p style="color:var(--text-secondary); font-size:0.85rem;">'
                'No model backups found.<br>'
                'Run <code style="color:var(--accent-cyan)">python3 model_tool.py backup</code></p>'
            )

        html = html.replace("{{MODEL_CONTENT}}", model_html)

        return html


# --- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="RadioMaster AX12 Research - Demo Status Server"
    )
    parser.add_argument(
        "--port", type=int, default=8080,
        help="Port to listen on (default: 8080)"
    )
    parser.add_argument(
        "--bind", default="0.0.0.0",
        help="Address to bind (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    server = HTTPServer((args.bind, args.port), DemoHandler)
    print(f"RadioMaster AX12 Research - Demo Server")
    print(f"  Local:   http://localhost:{args.port}/")
    print(f"  Network: http://100.87.134.108:{args.port}/")
    print(f"Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
