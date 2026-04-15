#!/data/data/com.termux/files/usr/bin/python3
"""AX12 Control Center — Terminal UI launcher.

Touch-friendly curses interface for running AX12 demos and tools.
Designed for Termux on the AX12 720x1280 touchscreen.

Usage: python3 launcher_tui.py
"""

import curses
import subprocess
import os
import sys
import time

PYTHON3 = "/data/data/com.termux/files/usr/bin/python3"
BASH = "/data/data/com.termux/files/usr/bin/bash"
TOOLS = os.path.expanduser("~/ax12-research/tools")
SCRIPTS = os.path.expanduser("~/ax12-research/scripts")

CATEGORIES = [
    ("DIAGNOSTICS", [
        ("SYS TEST",    f"su 0 {PYTHON3} {TOOLS}/system_test.py", 30),
        ("HEALTH",      f"su 0 {PYTHON3} {TOOLS}/device_health.py", 30),
        ("GPS",         f"su 0 {PYTHON3} {TOOLS}/gps_tool.py position", 30),
        ("WIFI SCAN",   f"su 0 {PYTHON3} {TOOLS}/wifi_scanner.py scan", 30),
    ]),
    ("DEMOS", [
        ("BETAFLIGHT",  f"su 0 {PYTHON3} {TOOLS}/msp_client.py status --demo", 30),
    ]),
    ("TOOLS", [
        ("FM RADIO",    f"su 0 {PYTHON3} {TOOLS}/fm_radio.py info", 30),
        ("MODELS",      f"su 0 {PYTHON3} {TOOLS}/model_tool.py list", 30),
        ("ELRS TELEM",  f"su 0 {PYTHON3} {TOOLS}/elrs_decoder.py --demo", 15),
    ]),
    ("HARDWARE", [
        ("USB GAMEPAD", f"su 0 {PYTHON3} {TOOLS}/usb_gamepad.py status", 30),
        ("HDMI OUTPUT", "su 0 cat /sys/bus/i2c/devices/1-004c/name 2>/dev/null && echo 'IT66121 HDMI TX detected' || echo 'Not found'", 10),
        ("BATTERY",     "su 0 cat /sys/class/power_supply/battery/uevent 2>/dev/null", 10),
    ]),
    ("APPS", [
        ("FLYSHARK",    "su 0 am start -n com.Flyshark.RadioMasterAX/.MainActivity 2>&1 && echo 'Flyshark launched'", 10),
        ("MESHTASTIC",  "su 0 am start -n com.geeksville.mesh/com.geeksville.mesh.MainActivity 2>&1 && echo 'Meshtastic launched'", 10),
        ("RETROARCH",   "su 0 am start -n com.retroarch/com.retroarch.browser.retroactivity.RetroActivityFuture 2>&1 && echo 'RetroArch launched'", 10),
        ("DOOM",        f"su 0 {BASH} {SCRIPTS}/doom-demo.sh", 30),
    ]),
    ("SERVICES", [
        ("CALIBRATOR",  "su 0 lsof -i :8080 2>/dev/null | grep LISTEN && echo 'Calibrator running on :8080' || echo 'Not running'", 10),
        ("TAILSCALE",   "tailscale status 2>&1 | head -15", 10),
    ]),
]

# Build flat list for selection
ITEMS = []
for cat_name, buttons in CATEGORIES:
    for label, cmd, timeout in buttons:
        ITEMS.append((cat_name, label, cmd, timeout))


def get_battery():
    try:
        r = subprocess.run(
            ["su", "0", "cat", "/sys/class/power_supply/battery/capacity"],
            capture_output=True, text=True, timeout=2
        )
        return r.stdout.strip() + "%" if r.returncode == 0 else "?"
    except Exception:
        return "?"


def get_uptime():
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h}h{m:02d}m"
    except Exception:
        return "?"


def run_tool(stdscr, label, cmd, timeout_sec):
    """Run a tool and show output in a scrollable view."""
    curses.curs_set(0)
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    # Header
    stdscr.attron(curses.color_pair(2))
    header = f" RUNNING: {label} "
    stdscr.addstr(0, 0, header.ljust(w)[:w-1])
    stdscr.attroff(curses.color_pair(2))

    stdscr.attron(curses.color_pair(3))
    stdscr.addstr(1, 0, f" Timeout: {timeout_sec}s | Press any key after completion..."[:w-1])
    stdscr.attroff(curses.color_pair(3))

    # Progress indicator
    stdscr.attron(curses.color_pair(4))
    stdscr.addstr(3, 1, ">>> EXECUTING..."[:w-2])
    stdscr.attroff(curses.color_pair(4))
    stdscr.refresh()

    # Run command
    env = os.environ.copy()
    env["PATH"] = "/data/data/com.termux/files/usr/bin:" + env.get("PATH", "")
    env["HOME"] = os.path.expanduser("~")
    env["TERM"] = "dumb"

    start = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout_sec, env=env, cwd=TOOLS,
        )
        elapsed = round(time.time() - start, 1)
        output = proc.stdout
        if proc.stderr:
            output += ("\n--- stderr ---\n" + proc.stderr) if output else proc.stderr
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 1)
        output = f"TIMEOUT after {timeout_sec}s"
        rc = -1
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        output = f"Error: {e}"
        rc = -2

    # Display results
    stdscr.clear()
    if rc == 0:
        stdscr.attron(curses.color_pair(5))
        status = f" COMPLETE ({elapsed}s) "
    elif rc == -1:
        stdscr.attron(curses.color_pair(6))
        status = f" TIMEOUT ({elapsed}s) "
    else:
        stdscr.attron(curses.color_pair(6))
        status = f" EXIT {rc} ({elapsed}s) "

    stdscr.addstr(0, 0, f" {label}: {status}"[:w-1].ljust(w)[:w-1])
    if rc == 0:
        stdscr.attroff(curses.color_pair(5))
    else:
        stdscr.attroff(curses.color_pair(6))

    # Output lines
    lines = output.strip().split("\n") if output.strip() else ["(no output)"]
    scroll = 0
    view_h = h - 3  # header + status + footer

    def draw_output():
        for i in range(view_h):
            li = scroll + i
            y = 2 + i
            if y >= h - 1:
                break
            stdscr.move(y, 0)
            stdscr.clrtoeol()
            if li < len(lines):
                line = lines[li][:w-2]
                if rc == 0:
                    stdscr.attron(curses.color_pair(4))
                    stdscr.addstr(y, 1, line)
                    stdscr.attroff(curses.color_pair(4))
                else:
                    stdscr.attron(curses.color_pair(6))
                    stdscr.addstr(y, 1, line)
                    stdscr.attroff(curses.color_pair(6))

        # Footer
        stdscr.attron(curses.color_pair(3))
        footer = f" [{scroll+1}-{min(scroll+view_h, len(lines))}/{len(lines)}] PRESS ANY KEY TO RETURN "
        if h > 1:
            stdscr.addstr(h-1, 0, footer[:w-1].ljust(w)[:w-1])
        stdscr.attroff(curses.color_pair(3))
        stdscr.refresh()

    draw_output()

    # Scroll and wait
    stdscr.timeout(-1)
    while True:
        key = stdscr.getch()
        if key == curses.KEY_DOWN and scroll < max(0, len(lines) - view_h):
            scroll += 1
            draw_output()
        elif key == curses.KEY_UP and scroll > 0:
            scroll -= 1
            draw_output()
        elif key == curses.KEY_NPAGE:
            scroll = min(scroll + view_h, max(0, len(lines) - view_h))
            draw_output()
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - view_h)
            draw_output()
        else:
            break


def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    # Color pairs
    curses.init_pair(1, curses.COLOR_CYAN, -1)       # title
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)  # header bar
    curses.init_pair(3, curses.COLOR_WHITE, 235 if curses.COLORS >= 256 else curses.COLOR_BLACK)  # dim
    curses.init_pair(4, curses.COLOR_CYAN, -1)        # output text
    curses.init_pair(5, curses.COLOR_GREEN, -1)       # success
    curses.init_pair(6, curses.COLOR_RED, -1)         # error
    curses.init_pair(7, curses.COLOR_YELLOW, -1)      # selected
    curses.init_pair(8, curses.COLOR_WHITE, -1)       # normal item

    selected = 0
    batt = get_battery()
    uptime = get_uptime()

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # Title bar
        stdscr.attron(curses.color_pair(2))
        title = " AX12 CONTROL CENTER "
        status = f" BATT {batt} | UP {uptime} "
        pad = w - len(title) - len(status)
        if pad < 0:
            pad = 0
        header_line = title + " " * pad + status
        stdscr.addstr(0, 0, header_line[:w-1].ljust(w)[:w-1])
        stdscr.attroff(curses.color_pair(2))

        # Subtitle
        stdscr.attron(curses.color_pair(3))
        stdscr.addstr(1, 0, " RADIOMASTER AX12 // MT8788 // TOOLS & DEMOS"[:w-1])
        stdscr.attroff(curses.color_pair(3))

        # Items
        y = 3
        item_idx = 0
        last_cat = ""

        for cat_name, label, cmd, timeout in ITEMS:
            if y >= h - 2:
                break

            # Category header
            if cat_name != last_cat:
                if y < h - 1:
                    stdscr.attron(curses.color_pair(1))
                    hdr = f"  {cat_name}"
                    stdscr.addstr(y, 0, hdr[:w-1])
                    stdscr.attroff(curses.color_pair(1))
                    y += 1
                last_cat = cat_name

            if y >= h - 2:
                break

            # Menu item
            prefix = " >> " if item_idx == selected else "    "
            line = f"{prefix}{label}"

            if item_idx == selected:
                stdscr.attron(curses.color_pair(7) | curses.A_BOLD)
                stdscr.addstr(y, 0, line[:w-1].ljust(w-1))
                stdscr.attroff(curses.color_pair(7) | curses.A_BOLD)
            else:
                stdscr.attron(curses.color_pair(8))
                stdscr.addstr(y, 0, line[:w-1])
                stdscr.attroff(curses.color_pair(8))

            y += 1
            item_idx += 1

        # Footer
        stdscr.attron(curses.color_pair(3))
        footer = " [UP/DOWN] Select  [ENTER] Run  [Q] Quit "
        if h > 1:
            stdscr.addstr(h-1, 0, footer[:w-1].ljust(w)[:w-1])
        stdscr.attroff(curses.color_pair(3))

        stdscr.refresh()

        # Input
        key = stdscr.getch()

        if key == curses.KEY_UP or key == ord('k'):
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN or key == ord('j'):
            selected = min(len(ITEMS) - 1, selected + 1)
        elif key == curses.KEY_HOME:
            selected = 0
        elif key == curses.KEY_END:
            selected = len(ITEMS) - 1
        elif key == 10 or key == curses.KEY_ENTER:  # Enter
            cat, label, cmd, timeout = ITEMS[selected]
            run_tool(stdscr, label, cmd, timeout)
            # Refresh status after running
            batt = get_battery()
            uptime = get_uptime()
        elif key == ord('q') or key == ord('Q') or key == 27:  # q or ESC
            break
        # Number shortcuts
        elif ord('1') <= key <= ord('9'):
            idx = key - ord('1')
            if idx < len(ITEMS):
                selected = idx
                cat, label, cmd, timeout = ITEMS[selected]
                run_tool(stdscr, label, cmd, timeout)
                batt = get_battery()
                uptime = get_uptime()
        # Touch: map y position to item index
        elif key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
                # Map screen y to item index
                y_offset = 3  # start of items
                touch_idx = 0
                ty = y_offset
                last_c = ""
                for ci, (cn, lb, cm, to) in enumerate(ITEMS):
                    if cn != last_c:
                        ty += 1  # category header
                        last_c = cn
                    if my == ty:
                        selected = ci
                        if bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_RELEASED:
                            cat, label, cmd, timeout = ITEMS[ci]
                            run_tool(stdscr, label, cmd, timeout)
                            batt = get_battery()
                            uptime = get_uptime()
                        break
                    ty += 1
            except Exception:
                pass


def setup_and_run():
    """Configure terminal and run the TUI."""
    # Enable mouse support
    os.environ.setdefault("TERM", "xterm-256color")
    try:
        stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except Exception:
            pass
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    curses.wrapper(main)
