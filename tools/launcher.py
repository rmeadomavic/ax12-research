#!/data/data/com.termux/files/usr/bin/python3
"""AX12 Tools - Touch-friendly web launcher for the AX12 touchscreen.

Serves on port 8090. Designed for 720x1280 portrait Android 9 WebView.
All tool commands run via subprocess with 30s timeout.
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

PORT = 8090
TOOLS_DIR = os.path.expanduser("~/ax12-research/tools")
SCRIPTS_DIR = os.path.expanduser("~/ax12-research/scripts")
PYTHON3 = "/data/data/com.termux/files/usr/bin/python3"
BASH = "/data/data/com.termux/files/usr/bin/bash"

# Command definitions: (label, command, timeout_sec)
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

# Build a flat lookup for API calls
COMMAND_MAP = {}
for cat in CATEGORIES:
    for label, cmd, timeout in cat["buttons"]:
        key = label.lower().replace(" ", "_")
        COMMAND_MAP[key] = (cmd, timeout)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>AX12 Tools</title>
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
    padding: 16px 20px;
    text-align: center;
    border-bottom: 2px solid #0f3460;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
}
.header h1 {
    font-size: 28px;
    font-weight: 700;
    color: #e94560;
    letter-spacing: 2px;
}
.header .subtitle {
    font-size: 14px;
    color: #888;
    margin-top: 4px;
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
    <h1>AX12 TOOLS</h1>
    <div class="subtitle" id="clock"></div>
</div>

<div class="content" id="content"></div>

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
var CATEGORIES = """ + json.dumps([
    {
        "name": cat["name"],
        "color": cat["color"],
        "color_dark": cat["color_dark"],
        "buttons": [(label, label.lower().replace(" ", "_")) for label, cmd, timeout in cat["buttons"]],
    }
    for cat in CATEGORIES
]) + """;

function updateClock() {
    var d = new Date();
    var h = d.getHours(), m = d.getMinutes();
    document.getElementById('clock').textContent =
        (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m + ' local';
}
updateClock();
setInterval(updateClock, 15000);

function buildUI() {
    var html = '';
    for (var i = 0; i < CATEGORIES.length; i++) {
        var cat = CATEGORIES[i];
        html += '<div class="category">';
        html += '<div class="category-label" style="color:' + cat.color + ';border-left:4px solid ' + cat.color + '">' + cat.name + '</div>';
        for (var j = 0; j < cat.buttons.length; j++) {
            var label = cat.buttons[j][0];
            var key = cat.buttons[j][1];
            html += '<button class="btn" id="btn-' + key + '" style="background:linear-gradient(135deg,' + cat.color + ',' + cat.color_dark + ')" onclick="runTool(\\'' + key + '\\',\\'' + label.replace(/'/g, "\\\\'") + '\\')">';
            html += '<span class="spinner"></span>';
            html += '<span class="btn-label">' + label + '</span>';
            html += '</button>';
        }
        html += '</div>';
    }
    document.getElementById('content').innerHTML = html;
}
buildUI();

var currentXhr = null;

function runTool(key, label) {
    var btn = document.getElementById('btn-' + key);
    if (btn.classList.contains('loading')) return;
    btn.classList.add('loading');

    var overlay = document.getElementById('overlay');
    var outputBox = document.getElementById('output-box');
    var title = document.getElementById('overlay-title');
    var status = document.getElementById('overlay-status');

    title.textContent = label;
    status.textContent = 'Running...';
    outputBox.innerHTML = '<div class="overlay-spinner"><div class="big-spinner"></div><div class="spin-text">Executing ' + label + '...</div></div>';
    overlay.classList.add('visible');

    var xhr = new XMLHttpRequest();
    currentXhr = xhr;
    xhr.open('POST', '/run', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 35000;
    xhr.onload = function() {
        btn.classList.remove('loading');
        if (xhr.status === 200) {
            var data = JSON.parse(xhr.responseText);
            var out = escapeHtml(data.output || '(no output)');
            if (data.returncode === 0) {
                status.textContent = 'Completed (' + data.elapsed + 's)';
                outputBox.innerHTML = '<span class="success">' + out + '</span>';
            } else if (data.returncode === -1) {
                status.textContent = 'TIMEOUT (' + data.elapsed + 's)';
                outputBox.innerHTML = '<span class="error">TIMEOUT after ' + data.elapsed + 's\\n\\n</span>' + out;
            } else {
                status.textContent = 'Exit code: ' + data.returncode + ' (' + data.elapsed + 's)';
                outputBox.innerHTML = '<span class="error">' + out + '</span>';
            }
        } else {
            status.textContent = 'Server error';
            outputBox.innerHTML = '<span class="error">HTTP ' + xhr.status + '</span>';
        }
    };
    xhr.onerror = function() {
        btn.classList.remove('loading');
        status.textContent = 'Network error';
        outputBox.innerHTML = '<span class="error">Could not reach server</span>';
    };
    xhr.ontimeout = function() {
        btn.classList.remove('loading');
        status.textContent = 'Request timeout';
        outputBox.innerHTML = '<span class="error">Browser request timed out</span>';
    };
    xhr.send(JSON.stringify({key: key}));
}

function closeOverlay() {
    document.getElementById('overlay').classList.remove('visible');
}

function escapeHtml(s) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
}
</script>
</body>
</html>"""


class LauncherHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the launcher UI and command execution."""

    def log_message(self, format, *args):
        """Suppress default logging to stderr."""
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            content = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
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
            result = run_command(cmd, timeout)

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


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), LauncherHandler)
    print(f"AX12 Launcher running on http://0.0.0.0:{PORT}")
    print(f"Tools dir: {TOOLS_DIR}")
    print(f"Commands registered: {len(COMMAND_MAP)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
