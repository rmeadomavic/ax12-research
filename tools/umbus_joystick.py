#!/usr/bin/env python3
"""umbus_joystick: bridge AX12 gimbals to an Android virtual joystick.

Reads UMBUS CHANNEL_DATA (0x57) off /dev/ttyS0 and injects gimbal axes +
switch buttons to /dev/uinput so on-device sims (Velocidrone) see the
sticks as a gamepad.

Key trick: the AT32 MCU only streams channel data at ~6Hz when idle. By
replaying the App->MCU poll/heartbeat/keepalive frames (the same bytes
RadioMasterOS sends), the MCU bumps to its full ~25Hz -- with the RC app
CLOSED, so we own /dev/ttyS0 exclusively (no lock contention).

Run:
  su 0 am force-stop com.Flyshark.RadioMasterAX   # release the port
  su 0 chmod 666 /dev/uinput                       # once per boot
  cd ~/ax12-research && python3 tools/umbus_joystick.py
Legacy uinput ABI (kernel 4.4, no UI_DEV_SETUP).
"""
import os, sys, struct, fcntl, termios, signal, time, argparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from umbus.decoder import UMBUSDecoder
from umbus.frame import FrameType
from umbus.encoder import UMBUSEncoder

EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT = 0x00
BTN_JOYSTICK = 0x120
ABS_X, ABS_Y, ABS_RX, ABS_RY = 0x00, 0x01, 0x03, 0x04
AXES = [ABS_X, ABS_Y, ABS_RX, ABS_RY]    # gimbals[0..3]: LX/yaw, RY/pitch, LY/thr, RX/roll
BTN_BASE = [0x120, 0x121, 0x122, 0x123]  # SA..SD -> joystick buttons 1..4
SWITCH_CH = [14, 15, 16, 17]             # CH14..17 (active ~500 / off ~65036)
SWITCH_THRESH = 30000
BUS_USB = 0x03
ABS_CNT = 64
AXIS_MIN, AXIS_MAX = -1023, 1023         # gimbals swing ~+/-500; margin for no-clip
POLL_PERIOD = 0.1                         # 10Hz pump -> ~25Hz channel data
DEADZONE = 6                              # raw counts; snap near-center to exactly 0
CENTER_GIMBALS = (0, 1, 3)               # self-centering axes (yaw/pitch/roll); gimbal 2 is throttle


def _IOW(t, nr, size): return (1 << 30) | (size << 16) | (ord(t) << 8) | nr
def _IO(t, nr):        return (ord(t) << 8) | nr
UI_SET_EVBIT  = _IOW("U", 100, 4)
UI_SET_KEYBIT = _IOW("U", 101, 4)
UI_SET_ABSBIT = _IOW("U", 103, 4)
UI_DEV_CREATE  = _IO("U", 1)
UI_DEV_DESTROY = _IO("U", 2)


def make_uinput():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_ABS)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
    fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_JOYSTICK)
    for b in BTN_BASE:
        fcntl.ioctl(fd, UI_SET_KEYBIT, b)
    for code in AXES:
        fcntl.ioctl(fd, UI_SET_ABSBIT, code)
    absmin = [0] * ABS_CNT; absmax = [0] * ABS_CNT
    absfuzz = [0] * ABS_CNT; absflat = [0] * ABS_CNT
    for code in AXES:
        absmin[code] = AXIS_MIN; absmax[code] = AXIS_MAX
    ud = struct.pack("<80sHHHHI" + "i" * (ABS_CNT * 4),
                     b"AX12 UMBUS Gimbals", BUS_USB, 0x1209, 0xA12B, 0x0001, 0,
                     *absmax, *absmin, *absfuzz, *absflat)
    os.write(fd, ud)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(0.3)
    os.system("su 0 chmod 666 /dev/input/event* 2>/dev/null")
    return fd


def emit(fd, etype, code, value):
    os.write(fd, struct.pack("llHHi", 0, 0, etype, code, value))


def open_serial(dev):
    fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = termios.B921600; a[5] = termios.B921600
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="/dev/ttyS0")
    ap.add_argument("--debug", action="store_true", help="print gimbal/rate, no uinput")
    ap.add_argument("--daemonize", action="store_true", help="double-fork, survive parent/ssh exit")
    args = ap.parse_args()

    if args.daemonize:
        if os.fork() > 0:
            os._exit(0)
        os.setsid()
        if os.fork() > 0:
            os._exit(0)
        dn = os.open(os.devnull, os.O_RDWR); os.dup2(dn, 0)
        lf = os.open(os.path.expanduser("~/joy.log"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.dup2(lf, 1); os.dup2(lf, 2)

    ser = open_serial(args.device)
    enc = UMBUSEncoder()
    ui = None if args.debug else make_uinput()
    if ui is not None:
        print("uinput joystick live: AX12 UMBUS Gimbals (4 axes + 4 buttons) @ ~25Hz", flush=True)

        def cleanup(*_):
            try:
                fcntl.ioctl(ui, UI_DEV_DESTROY)
            except Exception:
                pass
            os._exit(0)
        signal.signal(signal.SIGINT, cleanup)
        signal.signal(signal.SIGTERM, cleanup)

    dec = UMBUSDecoder()
    center = [0, 0, 0, 0]
    if ui is not None:
        cal = [[], [], [], []]
        tcal = time.time(); lp = 0.0
        while time.time() - tcal < 1.5:
            now = time.time()
            if now - lp >= POLL_PERIOD:
                try:
                    os.write(ser, enc.poll()); os.write(ser, enc.heartbeat_app()); os.write(ser, enc.keepalive())
                except OSError:
                    pass
                lp = now
            try:
                data = os.read(ser, 4096)
            except OSError:
                data = b""
            for fr in dec.feed(data):
                if fr.frame_type in (FrameType.CHANNEL_DATA, FrameType.IDLE) and fr.gimbals:
                    for i in range(4):
                        cal[i].append(fr.gimbals[i])
            time.sleep(0.002)
        for i in CENTER_GIMBALS:
            if cal[i]:
                srt = sorted(cal[i]); center[i] = srt[len(srt) // 2]
        print("auto-center yaw/pitch/roll raw: %s (deadzone %d) -- keep sticks centered at start"
              % ([center[i] for i in CENTER_GIMBALS], DEADZONE), flush=True)

    last = [None] * 4
    btn_last = [None] * 4
    n = 0
    t0 = time.time()
    last_poll = 0.0
    while True:
        now = time.time()
        if now - last_poll >= POLL_PERIOD:
            try:
                os.write(ser, enc.poll()); os.write(ser, enc.heartbeat_app()); os.write(ser, enc.keepalive())
            except OSError:
                pass
            last_poll = now
        try:
            data = os.read(ser, 4096)
        except OSError:
            data = b""
        for fr in dec.feed(data):
            if fr.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
                continue
            g = fr.gimbals
            if g is None:
                continue
            n += 1
            if ui is not None:
                changed = False
                for i, code in enumerate(AXES):
                    v = g[i] - center[i]
                    if i in CENTER_GIMBALS and abs(v) < DEADZONE:
                        v = 0
                    v = max(AXIS_MIN, min(AXIS_MAX, v))
                    if v != last[i]:
                        emit(ui, EV_ABS, code, v); last[i] = v; changed = True
                ch = fr.channels or []
                for j, cidx in enumerate(SWITCH_CH):
                    if cidx < len(ch):
                        pressed = 1 if ch[cidx] < SWITCH_THRESH else 0
                        if btn_last[j] != pressed:
                            emit(ui, EV_KEY, BTN_BASE[j], pressed); btn_last[j] = pressed; changed = True
                if changed:
                    emit(ui, EV_SYN, SYN_REPORT, 0)
            if args.debug and now - t0 >= 1.0:
                print("G0=%+6d G1=%+6d G2=%+6d G3=%+6d | %.0f Hz"
                      % (g[0], g[1], g[2], g[3], n / (now - t0)), flush=True)
                n = 0
                t0 = now
        time.sleep(0.002)


if __name__ == "__main__":
    main()
