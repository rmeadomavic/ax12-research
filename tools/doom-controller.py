#!/usr/bin/env python3
"""
DOOM Controller for AX12

Maps AX12 gimbals and switches to DOOM keyboard inputs via xdotool.
Reads UMBUS channel data from /dev/ttyS0 at 25Hz, translates gimbal
positions into proportional X11 key events for Chocolate Doom.

Usage:
    python3 doom-controller.py              # run controller
    python3 doom-controller.py --calibrate  # show live values
    python3 doom-controller.py --detect     # detect switch channels

Gimbal mapping (calibrated):
    G0 = Left stick X  (Yaw)      -> strafe left/right
    G1 = Right stick Y (Pitch)    -> forward/back
    G2 = Left stick Y  (Throttle) -> run when pushed up (no spring)
    G3 = Right stick X (Roll)     -> turn left/right

Switch mapping (confirmed):
    SA = CH14 (2-pos latch) -> fire      (500=fire, 65036=off)
    SD = CH17 (2-pos latch) -> use/open  (500=active, 65036=off)
    SB = CH15 (3-pos)       -> weapon prev (500=down)
    SC = CH16 (3-pos)       -> weapon next (500=down)
"""
import os
import sys
import time
import subprocess
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import UMBUSDecoder, FrameType, CHANNEL_CENTER

SERIAL_PORT = '/dev/ttyS0'
DISPLAY = ':0'
XDOTOOL = '/data/data/com.termux/files/usr/bin/xdotool'
XDPYINFO = '/data/data/com.termux/files/usr/bin/xdpyinfo'

# Gimbal axes
AXIS_STRAFE = 0
AXIS_FORWARD = 1
AXIS_THROTTLE = 2
AXIS_TURN = 3

# Deadzone (out of ~500 range)
DEADZONE = 100

# Proportional speed: (min_deflection, max_deflection, taps_per_frame)
SPEED_TIERS = [
    (100, 250, 1),
    (250, 400, 2),
    (400, 9999, 3),
]

# Throttle run threshold (rests ~-500, pushed up = +500)
RUN_THRESHOLD = -200

# Switch channels -- hardcoded known values, not rest-relative
SA_CH = 14   # fire:    500 = fire, 65036 = off
SD_CH = 17   # use:     500 = active, 65036 = off
SB_CH = 15   # wpn prev: 500 = down
SC_CH = 16   # wpn next: 500 = down

SW_ACTIVE = 500
SW_OFF = 65036

KEYS = {
    'forward': 'Up',
    'back': 'Down',
    'turn_left': 'Left',
    'turn_right': 'Right',
    'strafe_left': 'comma',
    'strafe_right': 'period',
    'fire': 'Control_L',
    'use': 'space',
    'run': 'Shift_L',
    'wpn_prev': 'bracketleft',
    'wpn_next': 'bracketright',
}


def xdo_env():
    env = os.environ.copy()
    env['DISPLAY'] = DISPLAY
    return env


def xdo(action, key):
    subprocess.run(
        [XDOTOOL, action, '--', key],
        env=xdo_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def xdo_tap(key, count=1):
    env = xdo_env()
    for _ in range(count):
        subprocess.run(
            [XDOTOOL, 'key', '--', key],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def get_taps(value):
    mag = abs(value)
    if mag < DEADZONE:
        return 0
    for lo, hi, taps in SPEED_TIERS:
        if lo <= mag < hi:
            return taps
    return SPEED_TIERS[-1][2]


def get_screen_size():
    try:
        r = subprocess.run(
            [XDPYINFO], env=xdo_env(),
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r'dimensions:\s+(\d+)x(\d+)\s+pixels', r.stdout)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1280, 720


def fullscreen_doom():
    env = xdo_env()
    w, h = get_screen_size()
    print(f"  Screen: {w}x{h}")
    try:
        r = subprocess.run(
            [XDOTOOL, 'search', '--name', '.'],
            env=env, capture_output=True, text=True, timeout=5,
        )
        wids = [x for x in r.stdout.strip().split('\n') if x]
        if wids:
            wid = wids[0]
            print(f"  Window: {wid}")
            subprocess.run([XDOTOOL, 'windowmove', '--sync', wid, '0', '0'],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            subprocess.run([XDOTOOL, 'windowsize', '--sync', wid, str(w), str(h)],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            subprocess.run([XDOTOOL, 'windowfocus', '--sync', wid],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            print(f"  Fullscreened to {w}x{h}")
        else:
            print("  WARNING: No DOOM window found")
    except Exception as e:
        print(f"  WARNING: {e}")


def open_serial():
    subprocess.run(
        ['stty', '-F', SERIAL_PORT, '921600', 'raw', '-echo'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return os.open(SERIAL_PORT, os.O_RDONLY | os.O_NONBLOCK)


def run_controller():
    fd = open_serial()
    decoder = UMBUSDecoder()
    frame_count = 0
    held = set()

    def hold(name, active):
        key = KEYS[name]
        if active and name not in held:
            xdo('keydown', key)
            held.add(name)
        elif not active and name in held:
            xdo('keyup', key)
            held.discard(name)

    def release_all():
        for name in list(held):
            xdo('keyup', KEYS[name])
        held.clear()

    print("DOOM Controller v3")
    print(f"  Deadzone: {DEADZONE} | Tiers: {SPEED_TIERS}")
    print(f"  Right stick: forward/back + turn")
    print(f"  Left stick X: strafe | Left stick Y: run")
    print(f"  SA=fire | SD=use | SB=prev wpn | SC=next wpn")
    print(f"  Ctrl+C to stop\n")
    fullscreen_doom()
    print()

    try:
        while True:
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                time.sleep(0.005)
                continue

            for frame in decoder.feed(data):
                if frame.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
                    continue

                g = frame.gimbals
                ch = frame.channels
                if not g:
                    continue

                frame_count += 1

                fwd = g[AXIS_FORWARD]
                strafe = g[AXIS_STRAFE]
                turn = g[AXIS_TURN]
                throttle = g[AXIS_THROTTLE]

                # Proportional gimbal taps
                ft = get_taps(fwd)
                if ft > 0:
                    xdo_tap(KEYS['forward'] if fwd > 0 else KEYS['back'], ft)

                st = get_taps(strafe)
                if st > 0:
                    xdo_tap(KEYS['strafe_right'] if strafe > 0 else KEYS['strafe_left'], st)

                tt = get_taps(turn)
                if tt > 0:
                    xdo_tap(KEYS['turn_right'] if turn > 0 else KEYS['turn_left'], tt)

                # Throttle = run
                hold('run', throttle > RUN_THRESHOLD)

                # Switches -- hardcoded values
                if ch and len(ch) > max(SA_CH, SD_CH, SB_CH, SC_CH):
                    hold('fire', ch[SA_CH] == SW_ACTIVE)
                    hold('use', ch[SD_CH] == SW_ACTIVE)
                    hold('wpn_prev', ch[SB_CH] == SW_ACTIVE)
                    hold('wpn_next', ch[SC_CH] == SW_ACTIVE)

                if frame_count % 50 == 0:
                    active = set()
                    if ft: active.add(f"{'fwd' if fwd>0 else 'back'}x{ft}")
                    if st: active.add(f"{'sR' if strafe>0 else 'sL'}x{st}")
                    if tt: active.add(f"{'tR' if turn>0 else 'tL'}x{tt}")
                    active |= held
                    print(f"  #{frame_count} | fwd={fwd:+4d} str={strafe:+4d} trn={turn:+4d} thr={throttle:+4d} | {active or 'idle'}")

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        release_all()
        os.close(fd)
        print("All keys released.")


def calibrate():
    fd = open_serial()
    decoder = UMBUSDecoder()
    sys.stdout.write("\033[2J\033[?25l")
    try:
        while True:
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            for frame in decoder.feed(data):
                if frame.frame_type != FrameType.CHANNEL_DATA:
                    continue
                g = frame.gimbals
                ch = frame.channels
                if not g:
                    continue
                out = "\033[H"
                out += "  CALIBRATION MODE | Ctrl+C to stop\n\n"
                labels = {0: 'LX/Yaw  ', 1: 'RY/Pitch', 2: 'LY/Throt', 3: 'RX/Roll '}
                for i, v in enumerate(g):
                    bar_w = 20
                    norm = max(0, min(bar_w - 1, int((v + 600) / 1200 * bar_w)))
                    bar = "." * norm + "|" + "." * (bar_w - norm - 1)
                    act = " ** ACTIVE" if abs(v) > DEADZONE else ""
                    out += f"    G{i} {labels.get(i, '')} [{bar}] {v:>+6d}{act}\n"
                out += "\n  SWITCHES:\n"
                if ch:
                    sw = {14: 'SA', 15: 'SB', 16: 'SC', 17: 'SD', 18: 'SE', 19: 'SF'}
                    for ci, name in sorted(sw.items()):
                        if ci < len(ch):
                            val = ch[ci]
                            state = "ACTIVE" if val == SW_ACTIVE else "mid" if val == CHANNEL_CENTER else "off"
                            out += f"    {name} CH{ci:02d}: {val:>6d} ({state})\n"
                out += "\n  OTHER NON-CENTER:\n"
                if ch:
                    for i, v in enumerate(ch):
                        if v != CHANNEL_CENTER and i not in range(14, 20):
                            out += f"    CH{i:02d}: {v:>6d}\n"
                sys.stdout.write(out)
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\n")
        os.close(fd)


def detect():
    fd = open_serial()
    decoder = UMBUSDecoder()
    rest = None
    rest_n = 0
    print("=== SWITCH DETECTOR === Keep switches at rest for 1 sec, then flip.\n")
    try:
        while True:
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            for frame in decoder.feed(data):
                if frame.frame_type != FrameType.CHANNEL_DATA:
                    continue
                ch = frame.channels
                if not ch:
                    continue
                if rest is None:
                    rest = list(ch)
                    rest_n = 1
                    continue
                if rest_n < 15:
                    for i in range(min(len(ch), len(rest))):
                        rest[i] = (rest[i] * rest_n + ch[i]) // (rest_n + 1)
                    rest_n += 1
                    if rest_n == 15:
                        print("Rest captured. Flip switches now.\n")
                    continue
                for i in range(min(len(ch), len(rest))):
                    d = abs(ch[i] - rest[i])
                    if d > 500:
                        print(f"  CH{i:02d}: {ch[i]:>6d} (0x{ch[i]:04X}) | rest={rest[i]:>6d} | delta={ch[i]-rest[i]:>+6d}")
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        os.close(fd)


if __name__ == '__main__':
    if '--calibrate' in sys.argv:
        calibrate()
    elif '--detect' in sys.argv:
        detect()
    else:
        run_controller()
