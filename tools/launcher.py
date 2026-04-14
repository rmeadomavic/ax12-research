#!/data/data/com.termux/files/usr/bin/python3
"""AX12 Control Center - Full-featured web launcher for the AX12 touchscreen.

Serves on port 8090. Designed for 720x1280 portrait Android 9 WebView.
All tool commands run via subprocess with 30s timeout.
Features: tool launcher, app launch/kill, activity log, status bar, PWA support.
"""

import http.server
import json
import subprocess
import threading
import html
import os
import sys
import time
import urllib.parse
from datetime import datetime

PORT = 8090
TOOLS_DIR = os.path.expanduser("~/ax12-research/tools")
SCRIPTS_DIR = os.path.expanduser("~/ax12-research/scripts")
PYTHON3 = "/data/data/com.termux/files/usr/bin/python3"
BASH = "/data/data/com.termux/files/usr/bin/bash"
LOG_FILE = os.path.expanduser("~/ax12-research/tools/.launcher_log.json")
MAX_LOG_ENTRIES = 20

# --- Activity Log ---
_log_lock = threading.Lock()

def load_log():
    """Load activity log from disk."""
    try:
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_log(entries):
    """Save activity log to disk."""
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(entries[-MAX_LOG_ENTRIES:], f)
    except Exception:
        pass

def log_entry(label, returncode, elapsed):
    """Add a log entry."""
    with _log_lock:
        entries = load_log()
        entries.append({
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "label": label,
            "rc": returncode,
            "elapsed": elapsed,
        })
        save_log(entries)

# --- Command definitions ---
CATEGORIES = [
    {
        "name": "STATUS",
        "color": "#2ecc71",
        "color_dark": "#1a7a42",
        "buttons": [
            ("System Test", f"su 0 {PYTHON3} {TOOLS_DIR}/system_test.py", 30),
            ("Device Health", f"su 0 {PYTHON3} {TOOLS_DIR}/device_health.py", 30),
            ("GPS Position", f"su 0 {PYTHON3} {TOOLS_DIR}/gps_tool.py position", 30),
        ],
    },
    {
        "name": "DEMOS",
        "color": "#3498db",
        "color_dark": "#1a5276",
        "buttons": [
            ("Start DOOM", f"su 0 {BASH} {SCRIPTS_DIR}/doom-demo.sh", 30),
            ("MAVLink Test", f"su 0 {PYTHON3} {TOOLS_DIR}/mavlink_bridge.py test --duration 30", 30),
            ("Hydra Demo", f"su 0 {PYTHON3} {TOOLS_DIR}/hydra_display.py demo", 30),
            ("CoT Bridge Test", f"su 0 {PYTHON3} {TOOLS_DIR}/cot_bridge.py --test", 10),
        ],
    },
    {
        "name": "TOOLS",
        "color": "#e67e22",
        "color_dark": "#7d4511",
        "buttons": [
            ("WiFi Scan", f"su 0 {PYTHON3} {TOOLS_DIR}/wifi_scanner.py scan", 30),
            ("FM Radio Info", f"su 0 {PYTHON3} {TOOLS_DIR}/fm_radio.py info", 30),
            ("Model List", f"su 0 {PYTHON3} {TOOLS_DIR}/model_tool.py list", 30),
            ("Airspace Brief", f"su 0 {PYTHON3} {TOOLS_DIR}/airspace_check.py brief", 30),
        ],
    },
    {
        "name": "HARDWARE",
        "color": "#9b59b6",
        "color_dark": "#5b2c6f",
        "buttons": [
            ("USB Gamepad Status", f"su 0 {PYTHON3} {TOOLS_DIR}/usb_gamepad.py status", 30),
            ("Payload Drop Calc", f"su 0 {PYTHON3} {TOOLS_DIR}/payload_drop.py calc --alt 50 --speed 10", 30),
            ("Betaflight Status", f"su 0 {PYTHON3} {TOOLS_DIR}/msp_client.py status --demo", 30),
        ],
    },
]

# App definitions: (label, package_name)
APPS = [
    ("RadioMaster OS", "com.Flyshark.RadioMasterAX"),
    ("Meshtastic", "com.geeksville.mesh"),
    ("YGPS", "com.mediatek.ygps"),
    ("Chrome", "com.android.chrome"),
    ("RetroArch", "com.retroarch.aarch64"),
    ("Camera", "com.mediatek.camera"),
    ("FM Radio", "com.android.fmradio"),
    ("Settings", "com.android.settings"),
]

# Build a flat lookup for API calls
COMMAND_MAP = {}
LABEL_MAP = {}
for cat in CATEGORIES:
    for label, cmd, timeout in cat["buttons"]:
        key = label.lower().replace(" ", "_")
        COMMAND_MAP[key] = (cmd, timeout)
        LABEL_MAP[key] = label

# Build app lookup
APP_MAP = {}
for label, pkg in APPS:
    key = "app_" + label.lower().replace(" ", "_")
    APP_MAP[key] = (label, pkg)

# --- HTML Page ---
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#1a1a2e">
<link rel="manifest" href="/manifest.json">
<title>AX12 Control Center</title>
<style>
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-tap-highlight-color: transparent;
}
html, body {
    width: 100%;
    height: 100%;
    overflow-x: hidden;
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
    font-size: 18px;
    touch-action: manipulation;
}
.header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: #16213e;
    padding: 12px 20px;
    text-align: center;
    border-bottom: 2px solid #0f3460;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
}
.header h1 {
    font-size: 26px;
    font-weight: 700;
    color: #e94560;
    letter-spacing: 2px;
}
.header .subtitle {
    font-size: 13px;
    color: #888;
    margin-top: 2px;
}

/* Status bar */
.status-bar {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 12px;
    padding: 8px 16px;
    background: #0d1117;
    border-bottom: 1px solid #21262d;
    font-size: 13px;
    color: #8b949e;
}
.status-bar .stat {
    display: flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
}
.status-bar .stat-val {
    color: #58a6ff;
    font-weight: 600;
}
.status-bar .stat-icon {
    font-size: 14px;
}

/* PWA banner */
.pwa-banner {
    background: linear-gradient(135deg, #0f3460, #16213e);
    border: 1px solid #e94560;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 12px 16px 0 16px;
    cursor: pointer;
    text-align: center;
}
.pwa-banner .pwa-title {
    font-size: 16px;
    font-weight: 700;
    color: #e94560;
}
.pwa-banner .pwa-hint {
    font-size: 12px;
    color: #888;
    margin-top: 4px;
}
.pwa-instructions {
    display: none;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 8px 16px 0 16px;
    font-size: 14px;
    line-height: 1.6;
    color: #c9d1d9;
}
.pwa-instructions ol {
    padding-left: 20px;
}
.pwa-instructions .step-highlight {
    color: #e94560;
    font-weight: 600;
}

.content {
    padding: 12px 16px 80px 16px;
    overflow-y: auto;
}
.category {
    margin-bottom: 20px;
}
.category-label {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    padding: 8px 12px;
    margin-bottom: 8px;
    border-radius: 6px;
    background: rgba(255,255,255,0.05);
}
.btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    min-height: 80px;
    padding: 16px 20px;
    margin-bottom: 8px;
    border: none;
    border-radius: 12px;
    font-size: 20px;
    font-weight: 600;
    color: #fff;
    cursor: pointer;
    transition: transform 0.1s, opacity 0.1s;
    text-shadow: 0 1px 3px rgba(0,0,0,0.4);
    position: relative;
    overflow: hidden;
}
.btn:active {
    transform: scale(0.97);
    opacity: 0.85;
}
.btn .spinner {
    display: none;
    width: 24px;
    height: 24px;
    border: 3px solid rgba(255,255,255,0.3);
    border-top: 3px solid #fff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 12px;
}
.btn.loading .spinner {
    display: inline-block;
}
.btn.loading .btn-label {
    opacity: 0.7;
}
@keyframes spin {
    to { transform: rotate(360deg); }
}

/* App row: launch button + kill button */
.app-row {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
}
.app-row .btn {
    margin-bottom: 0;
    flex: 1;
    min-height: 70px;
    font-size: 18px;
}
.app-row .kill-btn {
    flex: 0 0 70px;
    min-height: 70px;
    min-width: 70px;
    background: linear-gradient(135deg, #c0392b, #7b241c) !important;
    font-size: 24px;
    font-weight: 700;
    border: none;
    border-radius: 12px;
    color: #fff;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.1s, opacity 0.1s;
}
.app-row .kill-btn:active {
    transform: scale(0.95);
    opacity: 0.8;
}

/* Activity log */
.log-section {
    margin-top: 20px;
    border-top: 1px solid #30363d;
    padding-top: 12px;
}
.log-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    background: rgba(255,255,255,0.05);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #8b949e;
    text-transform: uppercase;
    user-select: none;
}
.log-toggle .arrow {
    transition: transform 0.2s;
    font-size: 18px;
}
.log-toggle.open .arrow {
    transform: rotate(180deg);
}
.log-entries {
    display: none;
    margin-top: 8px;
}
.log-entries.visible {
    display: block;
}
.log-entry {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    font-size: 13px;
    border-bottom: 1px solid #21262d;
    font-family: 'Courier New', monospace;
}
.log-entry .log-ts {
    color: #484f58;
    flex-shrink: 0;
    margin-right: 8px;
    font-size: 11px;
}
.log-entry .log-label {
    flex: 1;
    color: #c9d1d9;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.log-entry .log-rc {
    flex-shrink: 0;
    margin-left: 8px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
}
.log-rc.ok { background: #1a7a42; color: #2ecc71; }
.log-rc.fail { background: #7b241c; color: #e94560; }
.log-rc.timeout { background: #7d4511; color: #e67e22; }

/* Overlay */
.overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    z-index: 100;
    background: rgba(0,0,0,0.85);
    flex-direction: column;
}
.overlay.visible {
    display: flex;
}
.overlay-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: #16213e;
    border-bottom: 2px solid #0f3460;
    flex-shrink: 0;
}
.overlay-title {
    font-size: 20px;
    font-weight: 700;
    color: #e94560;
}
.overlay-status {
    font-size: 14px;
    color: #888;
    margin-top: 2px;
}
.close-btn {
    min-width: 100px;
    min-height: 56px;
    padding: 12px 24px;
    background: #e94560;
    color: #fff;
    border: none;
    border-radius: 10px;
    font-size: 18px;
    font-weight: 700;
    cursor: pointer;
    flex-shrink: 0;
}
.close-btn:active {
    opacity: 0.8;
}
.overlay-body {
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 16px;
}
.output-box {
    font-family: 'Courier New', monospace;
    font-size: 14px;
    line-height: 1.5;
    color: #c0c0c0;
    white-space: pre-wrap;
    word-break: break-word;
    background: #0d1117;
    padding: 16px;
    border-radius: 8px;
    min-height: 200px;
}
.output-box .error {
    color: #e94560;
}
.output-box .success {
    color: #2ecc71;
}
.overlay-spinner {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
}
.overlay-spinner .big-spinner {
    width: 48px;
    height: 48px;
    border: 4px solid rgba(233,69,96,0.2);
    border-top: 4px solid #e94560;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 16px;
}
.overlay-spinner .spin-text {
    font-size: 16px;
    color: #888;
}
</style>
</head>
<body>

<div class="header">
    <h1>AX12 CONTROL CENTER</h1>
    <div class="subtitle" id="clock"></div>
</div>

<div class="status-bar" id="status-bar">
    <div class="stat"><span class="stat-icon">&#x1F50B;</span> <span class="stat-val" id="sb-batt">--</span></div>
    <div class="stat"><span class="stat-icon">&#x1F4F6;</span> <span class="stat-val" id="sb-wifi">--</span></div>
    <div class="stat"><span class="stat-icon">&#x1F310;</span> <span class="stat-val" id="sb-ts">--</span></div>
    <div class="stat"><span class="stat-icon">&#x23F1;</span> <span class="stat-val" id="sb-uptime">--</span></div>
</div>

<div class="content" id="content">
    <!-- PWA banner -->
    <div class="pwa-banner" id="pwa-banner" onclick="togglePwa()">
        <div class="pwa-title">+ Add to Home Screen</div>
        <div class="pwa-hint">Tap for instructions</div>
    </div>
    <div class="pwa-instructions" id="pwa-instructions">
        <ol>
            <li>Open this page in <span class="step-highlight">Chrome</span></li>
            <li>Tap the <span class="step-highlight">menu (3 dots)</span> at top-right</li>
            <li>Tap <span class="step-highlight">"Add to Home screen"</span></li>
            <li>Tap <span class="step-highlight">"Add"</span></li>
        </ol>
        <div style="margin-top:8px;color:#8b949e;font-size:12px;">URL: http://localhost:8090</div>
    </div>

    <div id="buttons-container"></div>

    <!-- Activity Log -->
    <div class="log-section">
        <div class="log-toggle" id="log-toggle" onclick="toggleLog()">
            <span>Activity Log</span>
            <span class="arrow">&#9660;</span>
        </div>
        <div class="log-entries" id="log-entries"></div>
    </div>
</div>

<div class="overlay" id="overlay">
    <div class="overlay-header">
        <div>
            <div class="overlay-title" id="overlay-title">Output</div>
            <div class="overlay-status" id="overlay-status"></div>
        </div>
        <button class="close-btn" onclick="closeOverlay()">CLOSE</button>
    </div>
    <div class="overlay-body" id="overlay-body">
        <div class="output-box" id="output-box"></div>
    </div>
</div>

<script>
var CATEGORIES = __CATEGORIES_JSON__;
var APPS = __APPS_JSON__;

// --- Clock ---
function updateClock() {
    var d = new Date();
    var h = d.getHours(), m = d.getMinutes();
    document.getElementById('clock').textContent =
        (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m + ' local';
}
updateClock();
setInterval(updateClock, 15000);

// --- Status bar ---
function updateStatus() {
    fetch('/status').then(function(r){return r.json()}).then(function(d){
        document.getElementById('sb-batt').textContent = d.battery || '--';
        document.getElementById('sb-wifi').textContent = d.wifi || '--';
        document.getElementById('sb-ts').textContent = d.tailscale || '--';
        document.getElementById('sb-uptime').textContent = d.uptime || '--';
    }).catch(function(){});
}
updateStatus();
setInterval(updateStatus, 30000);

// --- PWA banner ---
function togglePwa() {
    var el = document.getElementById('pwa-instructions');
    el.style.display = el.style.display === 'block' ? 'none' : 'block';
}

// --- Build UI ---
function buildUI() {
    var h = '';
    // Tool categories
    for (var i = 0; i < CATEGORIES.length; i++) {
        var cat = CATEGORIES[i];
        h += '<div class="category">';
        h += '<div class="category-label" style="color:' + cat.color + ';border-left:4px solid ' + cat.color + '">' + cat.name + '</div>';
        for (var j = 0; j < cat.buttons.length; j++) {
            var label = cat.buttons[j][0];
            var key = cat.buttons[j][1];
            h += '<button class="btn" id="btn-' + key + '" style="background:linear-gradient(135deg,' + cat.color + ',' + cat.color_dark + ')" onclick="runTool(\'' + key + '\',\'' + esc(label) + '\')">';
            h += '<span class="spinner"></span>';
            h += '<span class="btn-label">' + label + '</span>';
            h += '</button>';
        }
        h += '</div>';
    }
    // Apps category
    h += '<div class="category">';
    h += '<div class="category-label" style="color:#00bcd4;border-left:4px solid #00bcd4">APPS</div>';
    for (var i = 0; i < APPS.length; i++) {
        var app = APPS[i];
        var akey = app[0];
        var alabel = app[1];
        h += '<div class="app-row">';
        h += '<button class="btn" id="btn-' + akey + '" style="background:linear-gradient(135deg,#00bcd4,#006064)" onclick="launchApp(\'' + akey + '\',\'' + esc(alabel) + '\')">';
        h += '<span class="spinner"></span>';
        h += '<span class="btn-label">' + alabel + '</span>';
        h += '</button>';
        h += '<button class="kill-btn" title="Force stop ' + alabel + '" onclick="killApp(\'' + akey + '\',\'' + esc(alabel) + '\')">X</button>';
        h += '</div>';
    }
    h += '</div>';
    document.getElementById('buttons-container').innerHTML = h;
}

function esc(s) { return s.replace(/'/g, "\\'"); }

buildUI();

// --- Tool execution ---
var currentXhr = null;

function runTool(key, label) {
    var btn = document.getElementById('btn-' + key);
    if (btn && btn.classList.contains('loading')) return;
    if (btn) btn.classList.add('loading');

    showOverlay(label, 'Running...');

    var xhr = new XMLHttpRequest();
    currentXhr = xhr;
    xhr.open('POST', '/run', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 35000;
    xhr.onload = function() {
        if (btn) btn.classList.remove('loading');
        handleResult(xhr, label);
        refreshLog();
    };
    xhr.onerror = function() {
        if (btn) btn.classList.remove('loading');
        setOverlayError('Network error', 'Could not reach server');
    };
    xhr.ontimeout = function() {
        if (btn) btn.classList.remove('loading');
        setOverlayError('Request timeout', 'Browser request timed out');
    };
    xhr.send(JSON.stringify({key: key}));
}

// --- App launch/kill ---
function launchApp(akey, label) {
    var btn = document.getElementById('btn-' + akey);
    if (btn && btn.classList.contains('loading')) return;
    if (btn) btn.classList.add('loading');

    showOverlay(label, 'Launching...');

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/app/launch', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 15000;
    xhr.onload = function() {
        if (btn) btn.classList.remove('loading');
        handleResult(xhr, label);
        refreshLog();
    };
    xhr.onerror = function() {
        if (btn) btn.classList.remove('loading');
        setOverlayError('Network error', 'Could not reach server');
    };
    xhr.ontimeout = function() {
        if (btn) btn.classList.remove('loading');
        setOverlayError('Timeout', 'Launch timed out');
    };
    xhr.send(JSON.stringify({key: akey}));
}

function killApp(akey, label) {
    showOverlay(label, 'Force stopping...');

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/app/kill', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 15000;
    xhr.onload = function() {
        handleResult(xhr, label + ' (kill)');
        refreshLog();
    };
    xhr.onerror = function() {
        setOverlayError('Network error', 'Could not reach server');
    };
    xhr.send(JSON.stringify({key: akey}));
}

// --- Overlay helpers ---
function showOverlay(label, statusText) {
    var overlay = document.getElementById('overlay');
    var outputBox = document.getElementById('output-box');
    var title = document.getElementById('overlay-title');
    var status = document.getElementById('overlay-status');

    title.textContent = label;
    status.textContent = statusText;
    outputBox.innerHTML = '<div class="overlay-spinner"><div class="big-spinner"></div><div class="spin-text">Executing ' + escapeHtml(label) + '...</div></div>';
    overlay.classList.add('visible');
}

function handleResult(xhr, label) {
    var status = document.getElementById('overlay-status');
    var outputBox = document.getElementById('output-box');
    if (xhr.status === 200) {
        var data = JSON.parse(xhr.responseText);
        var out = escapeHtml(data.output || '(no output)');
        if (data.returncode === 0) {
            status.textContent = 'Completed (' + data.elapsed + 's)';
            outputBox.innerHTML = '<span class="success">' + out + '</span>';
        } else if (data.returncode === -1) {
            status.textContent = 'TIMEOUT (' + data.elapsed + 's)';
            outputBox.innerHTML = '<span class="error">TIMEOUT after ' + data.elapsed + 's\n\n</span>' + out;
        } else {
            status.textContent = 'Exit code: ' + data.returncode + ' (' + data.elapsed + 's)';
            outputBox.innerHTML = '<span class="error">' + out + '</span>';
        }
    } else {
        setOverlayError('Server error', 'HTTP ' + xhr.status);
    }
}

function setOverlayError(statusText, body) {
    document.getElementById('overlay-status').textContent = statusText;
    document.getElementById('output-box').innerHTML = '<span class="error">' + escapeHtml(body) + '</span>';
}

function closeOverlay() {
    document.getElementById('overlay').classList.remove('visible');
}

function escapeHtml(s) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
}

// --- Activity Log ---
var logOpen = false;
function toggleLog() {
    logOpen = !logOpen;
    var el = document.getElementById('log-entries');
    var tog = document.getElementById('log-toggle');
    if (logOpen) {
        el.classList.add('visible');
        tog.classList.add('open');
        refreshLog();
    } else {
        el.classList.remove('visible');
        tog.classList.remove('open');
    }
}

function refreshLog() {
    fetch('/log').then(function(r){return r.json()}).then(function(entries){
        var el = document.getElementById('log-entries');
        if (!entries.length) {
            el.innerHTML = '<div style="padding:12px;color:#484f58;font-size:13px;text-align:center;">No activity yet</div>';
            return;
        }
        var h = '';
        for (var i = entries.length - 1; i >= 0; i--) {
            var e = entries[i];
            var rcClass = e.rc === 0 ? 'ok' : (e.rc === -1 ? 'timeout' : 'fail');
            var rcText = e.rc === 0 ? 'OK' : (e.rc === -1 ? 'T/O' : 'rc:' + e.rc);
            h += '<div class="log-entry">';
            h += '<span class="log-ts">' + escapeHtml(e.ts.substring(5)) + '</span>';
            h += '<span class="log-label">' + escapeHtml(e.label) + '</span>';
            h += '<span class="log-rc ' + rcClass + '">' + rcText + ' ' + e.elapsed + 's</span>';
            h += '</div>';
        }
        el.innerHTML = h;
    }).catch(function(){});
}

// Initial log load
refreshLog();
</script>
</body>
</html>"""


def get_categories_json():
    """Build JSON for tool categories (for the frontend)."""
    return json.dumps([
        {
            "name": cat["name"],
            "color": cat["color"],
            "color_dark": cat["color_dark"],
            "buttons": [
                (label, label.lower().replace(" ", "_"))
                for label, cmd, timeout in cat["buttons"]
            ],
        }
        for cat in CATEGORIES
    ])


def get_apps_json():
    """Build JSON for apps (for the frontend)."""
    return json.dumps([
        ("app_" + label.lower().replace(" ", "_"), label)
        for label, pkg in APPS
    ])


def get_manifest():
    """Return a PWA manifest JSON."""
    return json.dumps({
        "name": "AX12 Control Center",
        "short_name": "AX12",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1a1a2e",
        "theme_color": "#1a1a2e",
        "description": "AX12 Radio Control Center",
    })


def build_page():
    """Build the full HTML page with injected data."""
    page = HTML_PAGE
    page = page.replace("__CATEGORIES_JSON__", get_categories_json())
    page = page.replace("__APPS_JSON__", get_apps_json())
    return page


def get_system_status():
    """Gather battery, WiFi, Tailscale IP, and uptime."""
    result = {}
    try:
        # Battery
        out = subprocess.check_output(
            "su 0 dumpsys battery", shell=True, text=True, timeout=5
        )
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("level:"):
                result["battery"] = line.split(":", 1)[1].strip() + "%"
            elif line.startswith("status:"):
                code = line.split(":", 1)[1].strip()
                if code == "2":
                    result["battery"] = result.get("battery", "?%") + " CHG"
    except Exception:
        result["battery"] = "--"

    try:
        # WiFi SSID
        out = subprocess.check_output(
            "su 0 dumpsys wifi", shell=True, text=True, timeout=5
        )
        for line in out.splitlines():
            if "mWifiInfo" in line and "SSID:" in line:
                ssid = line.split("SSID:")[1].split(",")[0].strip().strip('"')
                result["wifi"] = ssid
                break
        if "wifi" not in result:
            result["wifi"] = "N/A"
    except Exception:
        result["wifi"] = "--"

    try:
        # Tailscale IP (tun0)
        out = subprocess.check_output(
            "su 0 ifconfig tun0", shell=True, text=True, timeout=5
        )
        for line in out.splitlines():
            if "inet addr:" in line:
                addr = line.split("inet addr:")[1].split()[0]
                result["tailscale"] = addr
                break
        if "tailscale" not in result:
            result["tailscale"] = "down"
    except Exception:
        result["tailscale"] = "down"

    try:
        # Uptime
        with open("/proc/uptime", "r") as f:
            secs = float(f.read().split()[0])
        hrs = int(secs // 3600)
        mins = int((secs % 3600) // 60)
        result["uptime"] = f"{hrs}h{mins}m"
    except Exception:
        result["uptime"] = "--"

    return result


class LauncherHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the launcher UI and command execution."""

    def log_message(self, format, *args):
        """Suppress default logging to stderr."""
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            content = build_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)

        elif self.path == "/manifest.json":
            content = get_manifest().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif self.path == "/status":
            data = get_system_status()
            resp = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/log":
            entries = load_log()
            resp = json.dumps(entries).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/health":
            resp = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                key = data.get("key", "")
            except (json.JSONDecodeError, AttributeError):
                self.send_error(400, "Bad JSON")
                return

            if key not in COMMAND_MAP:
                self.send_error(404, "Unknown command")
                return

            cmd, timeout = COMMAND_MAP[key]
            label = LABEL_MAP.get(key, key)
            result = run_command(cmd, timeout)
            log_entry(label, result["returncode"], result["elapsed"])

            resp = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/app/launch":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                key = data.get("key", "")
            except (json.JSONDecodeError, AttributeError):
                self.send_error(400, "Bad JSON")
                return

            if key not in APP_MAP:
                self.send_error(404, "Unknown app")
                return

            label, pkg = APP_MAP[key]
            result = launch_app(pkg)
            log_entry(f"Launch {label}", result["returncode"], result["elapsed"])

            resp = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/app/kill":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                key = data.get("key", "")
            except (json.JSONDecodeError, AttributeError):
                self.send_error(400, "Bad JSON")
                return

            if key not in APP_MAP:
                self.send_error(404, "Unknown app")
                return

            label, pkg = APP_MAP[key]
            result = kill_app(pkg)
            log_entry(f"Kill {label}", result["returncode"], result["elapsed"])

            resp = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(resp)

        else:
            self.send_error(404)


def run_command(cmd, timeout_sec):
    """Execute a shell command and return structured result."""
    env = os.environ.copy()
    env["PATH"] = "/data/data/com.termux/files/usr/bin:" + env.get("PATH", "")
    env["HOME"] = os.path.expanduser("~")
    env["TERM"] = "dumb"

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
            cwd=TOOLS_DIR,
        )
        elapsed = round(time.time() - start, 1)
        output = proc.stdout
        if proc.stderr:
            output += ("\n--- stderr ---\n" + proc.stderr) if output else proc.stderr
        return {
            "returncode": proc.returncode,
            "output": output.strip(),
            "elapsed": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 1)
        return {
            "returncode": -1,
            "output": f"Command timed out after {timeout_sec}s",
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {
            "returncode": -2,
            "output": f"Error: {e}",
            "elapsed": elapsed,
        }


def launch_app(package):
    """Launch an Android app by package name using monkey."""
    start = time.time()
    try:
        # Use monkey to launch -- works for any app without needing activity name
        proc = subprocess.run(
            f"su 0 monkey -p {package} -c android.intent.category.LAUNCHER 1",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        elapsed = round(time.time() - start, 1)
        output = proc.stdout.strip()
        if proc.stderr:
            output += ("\n" + proc.stderr.strip()) if output else proc.stderr.strip()
        # monkey returns 0 even if it works, check output for success
        if "Events injected: 1" in (proc.stdout + proc.stderr):
            return {"returncode": 0, "output": f"Launched {package}", "elapsed": elapsed}
        return {"returncode": proc.returncode, "output": output or f"Launched {package}", "elapsed": elapsed}
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {"returncode": -2, "output": f"Error: {e}", "elapsed": elapsed}


def kill_app(package):
    """Force-stop an Android app by package name."""
    start = time.time()
    try:
        proc = subprocess.run(
            f"su 0 am force-stop {package}",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        elapsed = round(time.time() - start, 1)
        output = proc.stdout.strip()
        if proc.stderr:
            output += ("\n" + proc.stderr.strip()) if output else proc.stderr.strip()
        return {
            "returncode": proc.returncode,
            "output": output or f"Force-stopped {package}",
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {"returncode": -2, "output": f"Error: {e}", "elapsed": elapsed}


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), LauncherHandler)
    print(f"AX12 Control Center running on http://0.0.0.0:{PORT}")
    print(f"Tools dir: {TOOLS_DIR}")
    print(f"Tool commands: {len(COMMAND_MAP)}")
    print(f"App shortcuts: {len(APP_MAP)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
