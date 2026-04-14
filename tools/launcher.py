#!/data/data/com.termux/files/usr/bin/python3
"""AX12 Control Center - Web launcher with ANSI color rendering.

Touch-friendly web UI on port 8090. Designed for 720x1280 Android 9.
Uses ThreadingHTTPServer to prevent single-request blocking.
Converts ANSI escape codes to HTML spans for colored output.
"""

import http.server
import json
import re
import subprocess
import socketserver
import os
import sys
import time
import urllib.parse

PORT = 8090
TOOLS_DIR = os.path.expanduser("~/ax12-research/tools")
SCRIPTS_DIR = os.path.expanduser("~/ax12-research/scripts")
PYTHON3 = "/data/data/com.termux/files/usr/bin/python3"
BASH = "/data/data/com.termux/files/usr/bin/bash"

CATEGORIES = [
    {
        "name": "DIAGNOSTICS",
        "tag": "01",
        "buttons": [
            ("SYS TEST", "sys_test", f"su 0 {PYTHON3} {TOOLS_DIR}/system_test.py", 30),
            ("HEALTH", "health", f"su 0 {PYTHON3} {TOOLS_DIR}/device_health.py", 30),
            ("GPS", "gps", f"su 0 {PYTHON3} {TOOLS_DIR}/gps_tool.py position", 30),
            ("WIFI SCAN", "wifi", f"su 0 {PYTHON3} {TOOLS_DIR}/wifi_scanner.py scan", 30),
        ],
    },
    {
        "name": "DEMOS",
        "tag": "02",
        "buttons": [
            ("MAVLINK", "mavlink", f"su 0 {PYTHON3} {TOOLS_DIR}/mavlink_bridge.py test --duration 30", 35),
            ("HYDRA", "hydra", f"su 0 {PYTHON3} {TOOLS_DIR}/hydra_display.py demo", 30),
            ("COT BRIDGE", "cot", f"su 0 {PYTHON3} {TOOLS_DIR}/cot_bridge.py --test", 10),
            ("BETAFLIGHT", "bf", f"su 0 {PYTHON3} {TOOLS_DIR}/msp_client.py status --demo", 30),
        ],
    },
    {
        "name": "TOOLS",
        "tag": "03",
        "buttons": [
            ("FM RADIO", "fm", f"su 0 {PYTHON3} {TOOLS_DIR}/fm_radio.py info", 30),
            ("MODELS", "models", f"su 0 {PYTHON3} {TOOLS_DIR}/model_tool.py list", 30),
            ("AIRSPACE", "airspace", f"su 0 {PYTHON3} {TOOLS_DIR}/airspace_check.py brief", 30),
            ("ELRS TELEM", "elrs", f"su 0 {PYTHON3} {TOOLS_DIR}/elrs_decoder.py --demo", 15),
            ("PAYLOAD DROP", "payload", f"su 0 {PYTHON3} {TOOLS_DIR}/payload_drop.py calc --alt 50 --speed 10 --target-lat 35.038 --target-lon -79.525", 30),
            ("ROVER NAV", "rover", f"su 0 {PYTHON3} {TOOLS_DIR}/rover_nav.py --demo", 15),
        ],
    },
    {
        "name": "HARDWARE",
        "tag": "04",
        "buttons": [
            ("USB GAMEPAD", "gamepad", f"su 0 {PYTHON3} {TOOLS_DIR}/usb_gamepad.py status", 30),
            ("HDMI OUTPUT", "hdmi", "su 0 cat /sys/bus/i2c/devices/1-004c/name 2>/dev/null && echo 'IT66121 HDMI TX detected' || echo 'Not found'", 10),
            ("SENSOR HAL", "sensors", "su 0 dumpsys sensorservice 2>/dev/null | head -30", 10),
            ("BATTERY", "batt", "su 0 cat /sys/class/power_supply/battery/uevent 2>/dev/null", 10),
        ],
    },
    {
        "name": "APPS",
        "tag": "05",
        "buttons": [
            ("FLYSHARK", "flyshark", "su 0 am start -n com.Flyshark.RadioMasterAX/.MainActivity 2>&1 && echo 'Flyshark launched'", 10),
            ("MESHTASTIC", "mesh", "su 0 am start -n com.geeksville.mesh/com.geeksville.mesh.MainActivity 2>&1 && echo 'Meshtastic launched'", 10),
            ("RETROARCH", "retro", "su 0 am start -n com.retroarch/com.retroarch.browser.retroactivity.RetroActivityFuture 2>&1 && echo 'RetroArch launched'", 10),
            ("DOOM", "doom", f"su 0 {BASH} {SCRIPTS_DIR}/doom-demo.sh", 30),
        ],
    },
    {
        "name": "SERVICES",
        "tag": "06",
        "buttons": [
            ("CALIBRATOR", "cal", f"su 0 lsof -i :8080 2>/dev/null | grep LISTEN && echo 'Calibrator running on :8080' || echo 'Not running'", 10),
            ("TAILSCALE", "ts", "tailscale status 2>&1 | head -15", 10),
        ],
    },
]

COMMAND_MAP = {}
for cat in CATEGORIES:
    for label, key, cmd, timeout in cat["buttons"]:
        COMMAND_MAP[key] = (cmd, timeout, label)

# ANSI to HTML color map
ANSI_COLORS = {
    "30": "#0c0c0c", "31": "#c53030", "32": "#5a9c4f", "33": "#b45309",
    "34": "#3b82f6", "35": "#a855f7", "36": "#5a9c4f", "37": "#A6BC92",
    "90": "#555", "91": "#ef5350", "92": "#5a9c4f", "93": "#f59e0b",
    "94": "#60a5fa", "95": "#c084fc", "96": "#A6BC92", "97": "#D8E2D0",
}


def ansi_to_html(text):
    """Convert ANSI escape sequences to HTML spans."""
    import html as html_mod
    text = html_mod.escape(text)
    # Replace ANSI codes with spans
    result = []
    open_spans = 0
    i = 0
    # Match escaped version of ESC[...m
    parts = re.split(r'\x1b\[([0-9;]*)m', text)
    # After html.escape, \x1b becomes literal - need to handle the raw escape
    # Actually, the ANSI codes in the raw text look like \x1b[92m
    # After html.escape they become the same since \x1b is not an HTML entity
    # Let me re-approach: process raw text first, then escape non-ANSI parts

    return _convert_ansi(text)


def _convert_ansi(escaped_text):
    """Process ANSI codes in already-HTML-escaped text."""
    # The escape char \x1b survived html.escape, find it
    # Pattern: \x1b[ digits/semicolons m
    pattern = re.compile(r'\x1b\[([0-9;]*)m')
    result = []
    open_spans = 0
    last = 0

    for m in pattern.finditer(escaped_text):
        result.append(escaped_text[last:m.start()])
        codes = m.group(1).split(";") if m.group(1) else ["0"]
        last = m.end()

        for code in codes:
            if code == "0" or code == "":
                # Reset
                result.append("</span>" * open_spans)
                open_spans = 0
            elif code == "1":
                result.append('<span style="font-weight:bold">')
                open_spans += 1
            elif code == "2":
                result.append('<span style="opacity:0.5">')
                open_spans += 1
            elif code in ANSI_COLORS:
                result.append(f'<span style="color:{ANSI_COLORS[code]}">')
                open_spans += 1

    result.append(escaped_text[last:])
    result.append("</span>" * open_spans)
    return "".join(result)


def get_status_line():
    """Quick device status."""
    try:
        batt = subprocess.run(
            ["su", "0", "cat", "/sys/class/power_supply/battery/capacity"],
            capture_output=True, text=True, timeout=3
        )
        pct = batt.stdout.strip() if batt.returncode == 0 else "?"
    except Exception:
        pct = "?"
    try:
        up = subprocess.run(
            ["cat", "/proc/uptime"], capture_output=True, text=True, timeout=2
        )
        secs = int(float(up.stdout.split()[0]))
        h, m = secs // 3600, (secs % 3600) // 60
        uptime = f"{h}h{m:02d}m"
    except Exception:
        uptime = "?"
    return f"BATT {pct}% // UP {uptime}"


def build_buttons_html():
    """Server-side render all buttons."""
    html = ""
    for cat in CATEGORIES:
        html += '<div class="sec">\n'
        html += f'<div class="sec-hdr"><span class="tag">{cat["tag"]}</span>{cat["name"]}</div>\n'
        html += '<div class="grid">\n'
        for label, key, cmd, timeout in cat["buttons"]:
            html += (
                f'<button class="btn" id="b-{key}" '
                f'onclick="go(\'{key}\',\'{label}\')">'
                f'<span class="bl">{label}</span></button>\n'
            )
        html += '</div></div>\n'
    return html


def build_page():
    """Build full HTML page."""
    status = get_status_line()
    buttons = build_buttons_html()
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>AX12 CONTROL</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
html,body{{width:100%;height:100%;background:#0c0c0c;color:#e8e8e8;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px}}

.hdr{{background:linear-gradient(145deg,#1c1c1c,#1a1f18);padding:16px 20px 12px;border-bottom:1px solid #262626;position:sticky;top:0;z-index:10}}
.hdr-row{{display:flex;align-items:baseline;justify-content:space-between}}
.logo{{font-size:13px;font-weight:800;color:#e8e8e8;letter-spacing:5px}}
.logo b{{color:#5a9c4f}}
.sub{{font-size:9px;color:#555;letter-spacing:2px;margin-top:3px;font-family:monospace}}
.stat{{font-size:10px;color:#888;letter-spacing:1px;font-family:monospace;margin-top:6px;padding:4px 8px;background:#111;border:1px solid #262626;border-radius:4px;display:inline-block}}

.wrap{{padding:12px 16px 60px;max-width:800px;margin:0 auto}}
.sec{{margin-bottom:16px}}
.sec-hdr{{font-size:10px;font-weight:700;color:#5a9c4f;letter-spacing:3px;padding:5px 10px;margin-bottom:6px;border-left:2px solid #385723;background:rgba(56,87,35,0.08);font-family:monospace}}
.tag{{color:#2a4118;margin-right:8px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:5px}}

.btn{{display:flex;align-items:center;justify-content:center;min-height:52px;padding:10px 8px;background:#1c1c1c;border:1px solid #262626;border-radius:4px;color:#888;font-size:12px;font-weight:700;letter-spacing:1px;cursor:pointer;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;text-align:center;transition:all .15s;-webkit-appearance:none;appearance:none}}
.btn:hover{{background:linear-gradient(145deg,#1c1c1c,#1a1f18);border-color:#385723;color:#A6BC92;box-shadow:0 0 12px rgba(56,87,35,0.15)}}
.btn:active{{background:#2a4118;border-color:#5a9c4f;color:#D8E2D0}}
.btn.run{{background:#1a1f18;border-color:#385723;color:#5a9c4f;opacity:.7;pointer-events:none}}
.bl{{pointer-events:none}}

.pop{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;z-index:100;background:#0c0c0c;flex-direction:column}}
.pop.on{{display:flex}}
.pop-hd{{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:linear-gradient(145deg,#1c1c1c,#1a1f18);border-bottom:1px solid #262626;flex-shrink:0}}
.pop-t{{font-size:14px;font-weight:700;color:#5a9c4f;letter-spacing:1px}}
.pop-s{{font-size:10px;color:#888;margin-top:2px;font-family:monospace}}
.xb{{min-width:60px;min-height:38px;padding:6px 14px;background:#1c1c1c;color:#c53030;border:1px solid #262626;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer;-webkit-appearance:none;letter-spacing:1px;transition:all .15s}}
.xb:hover{{background:#2a1a1a;border-color:#c53030;color:#ef5350}}
.xb:active{{background:#3a2020;color:#ff6b6b}}
.pop-b{{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:12px 16px}}
.out{{font-family:'Cascadia Code','Fira Code','SF Mono',Consolas,monospace;font-size:11px;line-height:1.6;color:#A6BC92;white-space:pre-wrap;word-break:break-word;background:#111;padding:14px;border-radius:4px;border:1px solid #262626;min-height:120px}}
.ld{{display:inline-block;width:14px;height:14px;border:2px solid #262626;border-top:2px solid #5a9c4f;border-radius:50%;margin-right:6px;vertical-align:middle}}
.ld.on{{animation:sp .7s linear infinite}}
@keyframes sp{{to{{transform:rotate(360deg)}}}}

.bar{{height:2px;background:linear-gradient(90deg,#385723,#5a9c4f);position:fixed;top:0;left:0;z-index:999;transition:width .3s;opacity:.9}}
</style>
</head>
<body>
<div class="bar" id="bar" style="width:0"></div>
<div class="hdr">
<div class="hdr-row">
<div>
<div class="logo"><b>AX12</b> CONTROL</div>
<div class="sub">RADIOMASTER AX12 // MT8788 PLATFORM</div>
</div>
</div>
<div class="stat" id="st">{status}</div>
</div>
<div class="wrap">{buttons}</div>
<div class="pop" id="pop">
<div class="pop-hd">
<div>
<div class="pop-t" id="pt">OUTPUT</div>
<div class="pop-s" id="ps"></div>
</div>
<button class="xb" onclick="cl()">CLOSE</button>
</div>
<div class="pop-b">
<div class="out" id="out"></div>
</div>
</div>
<script>
function go(k,n){{
var b=document.getElementById('b-'+k);
if(b.className.indexOf('run')>=0)return;
b.className='btn run';
var p=document.getElementById('pop');
var o=document.getElementById('out');
var t=document.getElementById('pt');
var s=document.getElementById('ps');
var br=document.getElementById('bar');
t.textContent=n;
s.textContent='EXECUTING...';
o.innerHTML='<span class="ld on"></span> Running '+n+'...';
p.className='pop on';
br.style.width='30%';
var x=new XMLHttpRequest();
x.open('POST','/run',true);
x.setRequestHeader('Content-Type','application/json');
x.timeout=45000;
x.onload=function(){{
b.className='btn';
br.style.width='100%';
setTimeout(function(){{br.style.width='0'}},600);
if(x.status===200){{
var d=JSON.parse(x.responseText);
var h=d.html||d.output||'(no output)';
if(d.returncode===0){{
s.textContent='COMPLETE ('+d.elapsed+'s)';
o.innerHTML=h;
}}else if(d.returncode===-1){{
s.textContent='TIMEOUT ('+d.elapsed+'s)';
o.innerHTML='<span style="color:#e05040">TIMEOUT after '+d.elapsed+'s</span>\\n\\n'+h;
}}else{{
s.textContent='EXIT '+d.returncode+' ('+d.elapsed+'s)';
o.innerHTML=h;
}}
}}else{{
s.textContent='ERROR';
o.innerHTML='<span style="color:#e05040">HTTP '+x.status+'</span>';
}}
}};
x.onerror=function(){{
b.className='btn';
br.style.width='0';
s.textContent='NETWORK ERROR';
o.innerHTML='<span style="color:#e05040">Cannot reach server</span>';
}};
x.ontimeout=function(){{
b.className='btn';
br.style.width='0';
s.textContent='TIMEOUT';
o.innerHTML='<span style="color:#e05040">Request timed out</span>';
}};
x.send(JSON.stringify({{key:k}}));
}}
function cl(){{document.getElementById('pop').className='pop';}}
</script>
</body>
</html>"""


def run_command(cmd, timeout_sec):
    """Execute a shell command and return structured result with HTML output."""
    env = os.environ.copy()
    env["PATH"] = "/data/data/com.termux/files/usr/bin:" + env.get("PATH", "")
    env["HOME"] = os.path.expanduser("~")
    env["TERM"] = "xterm-256color"
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout_sec, env=env, cwd=TOOLS_DIR,
        )
        elapsed = round(time.time() - start, 1)
        output = proc.stdout
        if proc.stderr:
            output += ("\n--- stderr ---\n" + proc.stderr) if output else proc.stderr
        html_output = ansi_to_html(output.strip()) if output.strip() else "(no output)"
        return {
            "returncode": proc.returncode,
            "output": output.strip(),
            "html": html_output,
            "elapsed": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 1)
        return {
            "returncode": -1,
            "output": f"Timed out after {timeout_sec}s",
            "html": f"Timed out after {timeout_sec}s",
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {
            "returncode": -2,
            "output": f"Error: {e}",
            "html": f"Error: {e}",
            "elapsed": elapsed,
        }


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            page = build_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(page)
        elif self.path == "/health":
            r = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(r)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(r)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                key = data.get("key", "")
            except Exception:
                self.send_error(400, "Bad JSON")
                return
            if key not in COMMAND_MAP:
                self.send_error(404, "Unknown command")
                return
            cmd, timeout, label = COMMAND_MAP[key]
            result = run_command(cmd, timeout)
            resp = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    server = ThreadedServer(("0.0.0.0", PORT), Handler)
    print(f"AX12 Control Center on http://0.0.0.0:{PORT}")
    print(f"Tools: {len(COMMAND_MAP)} commands")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        server.shutdown()


if __name__ == "__main__":
    main()
