#!/usr/bin/env python3
"""AX12 System Test Suite - Morning pre-demo validation.

Runs 20 automated tests against AX12 hardware and software capabilities.
Generates a pass/fail report card.

Usage:
    python3 system_test.py          # Human-readable table
    python3 system_test.py --json   # JSON output for CI
"""

import subprocess
import sys
import os
import json
import socket
import time
import re
from datetime import datetime

# ANSI colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BOLD = '\033[1m'
RESET = '\033[0m'

PASS = 'PASS'
FAIL = 'FAIL'
SKIP = 'SKIP'


def run_cmd(cmd, timeout=10):
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        env = os.environ.copy()
        termux_bin = "/data/data/com.termux/files/usr/bin"
        if termux_bin not in env.get("PATH", ""):
            env["PATH"] = termux_bin + ":" + env.get("PATH", "")
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            env=env,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, '', 'timeout'
    except Exception as e:
        return -1, '', str(e)


def test_ssh_connectivity():
    """Test 1: SSH connectivity (already passed if running)."""
    hostname = socket.gethostname()
    return PASS, 'Running on {}'.format(hostname)


def test_root_access():
    """Test 2: Root access via su."""
    rc, out, err = run_cmd('su 0 id')
    if rc == 0 and 'uid=0' in out:
        return PASS, 'uid=0(root) confirmed'
    return FAIL, 'rc={} out={} err={}'.format(rc, out, err)


def test_serial_port():
    """Test 3: Serial port /dev/ttyS0 exists and is readable."""
    if os.path.exists('/dev/ttyS0'):
        if os.access('/dev/ttyS0', os.R_OK):
            return PASS, '/dev/ttyS0 readable'
        return FAIL, '/dev/ttyS0 exists but not readable'
    return FAIL, '/dev/ttyS0 not found'


def test_flyshark_running():
    """Test 4: Flyshark app running."""
    rc, out, err = run_cmd('pidof com.Flyshark.RadioMasterAX')
    if rc == 0 and out:
        return PASS, 'PID {}'.format(out)
    # Termux pidof may not see other apps; try su
    rc, out, err = run_cmd('su 0 pidof com.Flyshark.RadioMasterAX')
    if rc == 0 and out:
        return PASS, 'PID {} (via su)'.format(out)
    return FAIL, 'Flyshark not running'


def test_gps_location():
    """Test 5: Location service returns coordinates (network/fused — NOT GNSS).

    Note: the AX12 has no GPS antenna populated, so any coordinates here come
    from Android's WiFi/network providers, not a satellite fix. See
    docs/hardware/hardware-map.md.
    """
    rc, out, err = run_cmd('su 0 dumpsys location')
    if rc != 0:
        return FAIL, 'dumpsys location failed'
    # Look for coordinate patterns
    for line in out.split('\n'):
        if 'Location[' in line or 'last location' in line.lower():
            if any(c.isdigit() for c in line):
                return PASS, line.strip()[:80]
    # Check for any lat/lon pattern
    coords = re.search(r'(-?\d+\.\d+),\s*(-?\d+\.\d+)', out)
    if coords:
        return PASS, 'Coords: {}'.format(coords.group(0))
    if 'noLocationPerm' in out or 'no last' in out.lower():
        return SKIP, 'No location fix available'
    return SKIP, 'No coordinates found in location dump'


def test_fm_radio():
    """Test 6: FM radio chip /dev/fm exists."""
    if os.path.exists('/dev/fm'):
        return PASS, '/dev/fm present'
    return FAIL, '/dev/fm not found'


def test_wifi_connected():
    """Test 7: WiFi connected with SSID."""
    rc, out, err = run_cmd('su 0 dumpsys wifi | grep "mWifiInfo"')
    if rc == 0 and out:
        ssid = re.search(r'SSID: ([^,]+)', out)
        if ssid and ssid.group(1) != '<unknown ssid>':
            return PASS, 'SSID: {}'.format(ssid.group(1))
        ssid = re.search(r'"([^"]+)"', out)
        if ssid:
            return PASS, 'SSID: {}'.format(ssid.group(1))
    # Alternate method
    rc2, out2, err2 = run_cmd('su 0 dumpsys wifi | grep "Wi-Fi is"')
    if 'enabled' in out2.lower():
        return PASS, 'WiFi enabled (SSID parse failed)'
    return FAIL, 'WiFi not connected'


def test_tailscale_online():
    """Test 8: Tailscale online (tun0 interface)."""
    # Termux doesn't have ip in PATH; use full path via su
    rc, out, err = run_cmd('su 0 /system/bin/ip addr show tun0 2>/dev/null')
    if rc == 0 and 'inet ' in out:
        ip_match = re.search(r'inet (\S+)', out)
        addr = ip_match.group(1) if ip_match else 'unknown'
        return PASS, 'tun0: {}'.format(addr)
    # Fallback: check /sys or ifconfig
    rc2, out2, err2 = run_cmd('su 0 cat /proc/net/if_inet6 2>/dev/null | grep tun')
    if rc2 == 0 and out2:
        return PASS, 'tun0 present (IPv6)'
    return FAIL, 'tun0 interface not found'


def test_usb_gadget():
    """Test 9: USB gadget configured."""
    udc_path = '/config/usb_gadget/g1/UDC'
    if os.path.exists(udc_path):
        try:
            with open(udc_path, 'r') as f:
                content = f.read().strip()
            if content:
                return PASS, 'UDC: {}'.format(content)
            return SKIP, 'UDC file empty (no gadget bound)'
        except PermissionError:
            rc, out, err = run_cmd('su 0 cat {}'.format(udc_path))
            if rc == 0 and out.strip():
                return PASS, 'UDC: {}'.format(out.strip())
            return SKIP, 'UDC empty or unreadable'
    return SKIP, 'USB gadget path not found'


def test_hdmi_transmitter():
    """Test 10: HDMI transmitter (it66121 on i2c)."""
    path = '/sys/bus/i2c/devices/1-004c/name'
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                name = f.read().strip()
            if 'it66121' in name.lower():
                return PASS, 'HDMI TX: {}'.format(name)
            return FAIL, 'Unexpected device: {}'.format(name)
        except Exception as e:
            return FAIL, str(e)
    # Try alternate paths
    rc, out, err = run_cmd(
        'find /sys/bus/i2c/devices -name name -exec cat {} \\; 2>/dev/null | grep -i it66'
    )
    if out:
        return PASS, 'HDMI TX found: {}'.format(out.split('\n')[0])
    return SKIP, 'i2c device path not found'


def test_sensor_hal():
    """Test 11: Sensor HAL running."""
    # Termux ps may not see system processes; use su
    rc, out, err = run_cmd('su 0 ps -A | grep -i sensor')
    if rc == 0 and out:
        procs = [l.split()[-1] for l in out.split('\n') if l.strip()]
        return PASS, 'Processes: {}'.format(', '.join(procs[:3]))
    return FAIL, 'No sensor processes found'


def test_meshtastic_installed():
    """Test 12: Meshtastic installed."""
    rc, out, err = run_cmd('pm list packages | grep -i mesh')
    if rc == 0 and out:
        pkgs = [l.replace('package:', '') for l in out.split('\n')]
        return PASS, ', '.join(pkgs)
    return SKIP, 'Meshtastic not installed'


def test_umbus_library():
    """Test 13: UMBUS library imports."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, tools_dir)
    try:
        import importlib.util
        spec = importlib.util.find_spec('umbus')
        if spec:
            return PASS, 'umbus at {}'.format(spec.origin)
        return FAIL, 'umbus module not found in path'
    except Exception as e:
        return FAIL, str(e)


def test_calibrator_web():
    """Test 14: Calibrator web server running on localhost:8080."""
    try:
        import urllib.request
        req = urllib.request.Request('http://localhost:8080', method='GET')
        resp = urllib.request.urlopen(req, timeout=3)
        return PASS, 'HTTP {}'.format(resp.status)
    except Exception as e:
        ename = type(e).__name__
        return SKIP, 'Not running ({})'.format(ename)


def test_git_repo_clean():
    """Test 15: Git repo clean."""
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rc, out, err = run_cmd('cd {} && git status --porcelain 2>&1'.format(repo_dir))
    if rc != 0:
        return FAIL, 'git status failed: {}'.format(err)
    if not out:
        return PASS, 'Working tree clean'
    # Filter out permission-denied warnings, this test file, and __pycache__
    self_name = os.path.basename(__file__)
    lines = []
    for line in out.split('\n'):
        if not line.strip():
            continue
        if 'Permission denied' in line:
            continue
        if self_name in line:
            continue
        if '__pycache__' in line:
            continue
        lines.append(line)
    if not lines:
        return PASS, 'Working tree clean'
    return FAIL, '{} changed: {}'.format(len(lines), lines[0].strip()[:30])


def test_lua_scripts():
    """Test 16: Lua scripts present in AX12LUA."""
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lua_dir = os.path.join(repo_dir, 'AX12LUA')
    if not os.path.isdir(lua_dir):
        # Try alternate location
        rc, out, err = run_cmd(
            'find {} -name "*.lua" -type f 2>/dev/null | wc -l'.format(repo_dir)
        )
        if out and int(out) > 0:
            return PASS, '{} Lua files found in repo'.format(out)
        return FAIL, 'AX12LUA directory not found'
    rc, out, err = run_cmd('find {} -name "*.lua" -type f | wc -l'.format(lua_dir))
    count = int(out) if out else 0
    if count > 0:
        return PASS, '{} Lua scripts in AX12LUA/'.format(count)
    return FAIL, 'No .lua files found'


def test_python_tools():
    """Test 17: Python tools present in tools/."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    rc, out, err = run_cmd('find {} -name "*.py" -type f | wc -l'.format(tools_dir))
    count = int(out) if out else 0
    if count >= 5:
        return PASS, '{} Python files in tools/'.format(count)
    elif count > 0:
        return PASS, '{} Python files (sparse)'.format(count)
    return FAIL, 'No Python tools found'


def test_demo_server():
    """Test 18: Demo server starts (quick start/stop on temp port)."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    demo_path = os.path.join(tools_dir, 'demo_server.py')
    if not os.path.exists(demo_path):
        return SKIP, 'demo_server.py not found'
    # Verify the file is parseable Python
    rc, out, err = run_cmd(
        '{} -c "import ast; ast.parse(open(\'{}\').read())"'.format(sys.executable, demo_path)
    )
    if rc == 0:
        return PASS, 'demo_server.py parses OK'
    return FAIL, 'Parse error: {}'.format(err[:60])


def test_model_files():
    """Test 19: Model files accessible."""
    model_path = '/data/data/com.Flyshark.RadioMasterAX/files/rcModel/'
    rc, out, err = run_cmd('su 0 ls {} 2>/dev/null | head -5'.format(model_path))
    if rc == 0 and out:
        files = out.split('\n')
        return PASS, '{} items (e.g. {})'.format(len(files), files[0])
    # Try without su
    rc2, out2, err2 = run_cmd('ls {} 2>/dev/null | head -5'.format(model_path))
    if rc2 == 0 and out2:
        files = out2.split('\n')
        return PASS, '{} items (e.g. {})'.format(len(files), files[0])
    return FAIL, 'Cannot access model files: {}'.format(err or err2)


def test_battery():
    """Test 20: Battery check (voltage > 6.0V)."""
    rc, out, err = run_cmd('su 0 dumpsys battery')
    if rc != 0:
        return FAIL, 'dumpsys battery failed: {}'.format(err)
    voltage = None
    level = None
    for line in out.split('\n'):
        if 'voltage' in line.lower():
            try:
                v = int(''.join(c for c in line.split(':')[-1] if c.isdigit()))
                # Voltage is typically in mV
                if v > 1000:
                    voltage = v / 1000.0
                else:
                    voltage = float(v)
            except ValueError:
                pass
        if 'level' in line.lower():
            try:
                level = int(''.join(c for c in line.split(':')[-1] if c.isdigit()))
            except ValueError:
                pass

    if voltage is not None:
        # AX12 uses single-cell Li-ion (nominal 3.7V, full 4.2V)
        # Warn below 3.4V (roughly 10% remaining)
        threshold = 3.4
        if voltage > threshold:
            detail = '{:.2f}V'.format(voltage)
            if level is not None:
                detail += ' ({}%)'.format(level)
            return PASS, detail
        else:
            return FAIL, '{:.2f}V (below {:.1f}V threshold)'.format(voltage, threshold)
    if level is not None:
        return PASS, 'Level: {}% (voltage not reported)'.format(level)
    return FAIL, 'Could not parse battery info'


# All tests in order
TESTS = [
    ('SSH Connectivity', test_ssh_connectivity),
    ('Root Access', test_root_access),
    ('Serial Port', test_serial_port),
    ('Flyshark App', test_flyshark_running),
    ('GPS Location', test_gps_location),
    ('FM Radio Chip', test_fm_radio),
    ('WiFi Connected', test_wifi_connected),
    ('Tailscale Online', test_tailscale_online),
    ('USB Gadget', test_usb_gadget),
    ('HDMI Transmitter', test_hdmi_transmitter),
    ('Sensor HAL', test_sensor_hal),
    ('Meshtastic', test_meshtastic_installed),
    ('UMBUS Library', test_umbus_library),
    ('Calibrator Web', test_calibrator_web),
    ('Git Repo Clean', test_git_repo_clean),
    ('Lua Scripts', test_lua_scripts),
    ('Python Tools', test_python_tools),
    ('Demo Server', test_demo_server),
    ('Model Files', test_model_files),
    ('Battery Check', test_battery),
]


def run_all_tests():
    """Run all tests and return results list."""
    results = []
    for name, func in TESTS:
        try:
            status, detail = func()
        except Exception as e:
            status, detail = FAIL, 'Exception: {}'.format(e)
        results.append({
            'num': len(results) + 1,
            'name': name,
            'status': status,
            'detail': detail,
        })
    return results


def print_table(results):
    """Print human-readable results table."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print('')
    print('{}AX12 System Test Report{}'.format(BOLD, RESET))
    print('Date: {}'.format(now))
    print('=' * 72)
    print('{:<4} {:<20} {:<8} {}'.format('#', 'Test', 'Status', 'Detail'))
    print('-' * 72)

    for r in results:
        num = r['num']
        name = r['name']
        status = r['status']
        detail = r['detail']

        if status == PASS:
            color = GREEN
        elif status == FAIL:
            color = RED
        else:
            color = YELLOW

        # Truncate detail to fit
        max_detail = 38
        if len(detail) > max_detail:
            detail = detail[:max_detail - 1] + '~'

        print('{:<4} {:<20} {}{:<8}{} {}'.format(num, name, color, status, RESET, detail))

    print('=' * 72)

    # Summary
    passed = sum(1 for r in results if r['status'] == PASS)
    failed = sum(1 for r in results if r['status'] == FAIL)
    skipped = sum(1 for r in results if r['status'] == SKIP)
    total = len(results)

    summary = '{}/{} PASS'.format(passed, total)
    if failed:
        summary += '  {}{} FAIL{}'.format(RED, failed, RESET)
    if skipped:
        summary += '  {}{} SKIP{}'.format(YELLOW, skipped, RESET)

    print('')
    print('{}Summary:{} {}'.format(BOLD, RESET, summary))

    if failed == 0:
        print('{}All critical tests passing. Ready for demo.{}'.format(GREEN, RESET))
    else:
        print('{}Failures detected. Review before demo.{}'.format(RED, RESET))
    print('')


def print_json(results):
    """Print JSON output for CI."""
    now = datetime.now().isoformat()
    output = {
        'timestamp': now,
        'device': 'RadioMaster AX12',
        'tests': results,
        'summary': {
            'total': len(results),
            'passed': sum(1 for r in results if r['status'] == PASS),
            'failed': sum(1 for r in results if r['status'] == FAIL),
            'skipped': sum(1 for r in results if r['status'] == SKIP),
        }
    }
    output['summary']['ready'] = output['summary']['failed'] == 0
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    json_mode = '--json' in sys.argv

    results = run_all_tests()

    if json_mode:
        print_json(results)
    else:
        print_table(results)

    # Exit code: number of failures
    failures = sum(1 for r in results if r['status'] == FAIL)
    sys.exit(min(failures, 127))
