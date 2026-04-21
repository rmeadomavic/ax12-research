"""
server.py — HTTP/SSE server for the AX12 calibration tool.

Serves the web UI, streams live channel data via SSE at ~25 Hz,
and handles wizard commands via POST endpoints.

Usage:
    python server.py --mode demo      (default, no serial port needed)
    python server.py --mode exclusive --port 8080
    python server.py --mode strace    --port 8080
"""

import argparse
import json
import math
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Calibration imports (always present)
# ---------------------------------------------------------------------------
from calibration import (
    CalibrationState,
    load_calibration,
    log_event,
    save_calibration,
    STEP_ORDER,
)

# ---------------------------------------------------------------------------
# Analyzer imports (always present)
# ---------------------------------------------------------------------------
from analyzer import classify_channels, count_positions, detect_movement

# ---------------------------------------------------------------------------
# Serial reader — optional; fall back gracefully if not yet built
# ---------------------------------------------------------------------------
try:
    from serial_reader import (  # type: ignore
        LATEST,
        _lock,
        get_latest,
        start_exclusive,
        start_strace,
    )
    _has_serial_reader = True
except ImportError:
    _has_serial_reader = False

    LATEST: dict = {
        "gimbals": [0, 0, 0, 0],
        "channels": [32768] * 33,
        "fps": 0.0,
        "crc_errors": 0,
        "connected": False,
    }
    _lock = threading.Lock()

    def get_latest() -> dict:
        with _lock:
            return dict(LATEST)

    def update_latest(gimbals: list, channels: list) -> None:
        with _lock:
            LATEST["gimbals"] = gimbals
            LATEST["channels"] = channels
            LATEST["connected"] = True

    def start_exclusive(**kw) -> None:  # noqa: ANN003
        pass

    def start_strace(**kw) -> None:  # noqa: ANN003
        pass


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
CALIBRATION_PATH = os.path.expanduser("~/ax12-research/calibration.json")
LOG_PATH = os.path.expanduser("~/ax12-research/calibration_log.jsonl")

_RESEARCH_DIR = os.path.expanduser("~/ax12-research")


def _ensure_research_dir() -> None:
    """Create ~/ax12-research/ if it does not exist."""
    os.makedirs(_RESEARCH_DIR, exist_ok=True)


def _log(event: dict) -> None:
    """log_event wrapper — silently skips if the directory cannot be written."""
    try:
        _ensure_research_dir()
        log_event(LOG_PATH, event)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Global mutable state
# ---------------------------------------------------------------------------
state = CalibrationState()
sample_buffer: list[list[int]] = []          # channel frames collected during session
_state_lock = threading.Lock()
_sample_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Demo-mode data generator
# ---------------------------------------------------------------------------

def start_demo_data() -> None:
    """Spawn a background thread that generates oscillating fake UMBUS data."""

    def _demo() -> None:
        t = 0.0
        while True:
            gimbals = [
                int(300 * math.sin(t * 0.5)),
                int(200 * math.cos(t * 0.3)),
                int(100 * math.sin(t * 0.7)),
                random.randint(-10, 10),
            ]
            channels = [32768] * 33
            channels[0] = [1020, 32768, 65036][int(t) % 3]
            channels[1] = 65036 if int(t) % 10 < 5 else 1020
            channels[2] = int(32768 + 30000 * math.sin(t * 0.2))

            update_latest(gimbals, channels)

            with _lock:
                LATEST["fps"] = 25.0
                LATEST["connected"] = True
                LATEST["crc_errors"] = 0

            t += 0.04
            time.sleep(0.04)

    threading.Thread(target=_demo, daemon=True, name="demo-data").start()


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    """Single handler for all HTTP requests."""

    # Silence the default per-request log lines (we only log errors below)
    def log_message(self, fmt, *args) -> None:  # noqa: ANN001, ANN002
        pass

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path == "/index.html":
            self._serve_index()
        elif self.path == "/stream":
            self._serve_sse()
        elif self.path == "/api/state":
            self._serve_state()
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/command":
            self._handle_command()
        elif self.path == "/api/save":
            self._handle_save()
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_OPTIONS(self) -> None:  # noqa: N802
        """Return CORS pre-flight headers."""
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # GET /
    # ------------------------------------------------------------------

    def _serve_index(self) -> None:
        index_path = os.path.join(SERVER_DIR, "index.html")
        if not os.path.exists(index_path):
            body = b"<h1>AX12 Calibration Tool</h1><p>index.html not yet built.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)
            return

        with open(index_path, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------
    # GET /stream  — Server-Sent Events at ~25 Hz
    # ------------------------------------------------------------------

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        try:
            while True:
                latest = get_latest()

                with _state_lock:
                    current_step = state.current_step
                    completed = list(state.completed_steps)

                # Buffer channel frames for later analysis
                channels = latest.get("channels", [32768] * 33)
                with _sample_lock:
                    sample_buffer.append(list(channels))
                    # Keep at most ~5 s of data (25 Hz × 5 s = 125 frames)
                    if len(sample_buffer) > 125:
                        sample_buffer.pop(0)

                payload = {
                    "gimbals": latest.get("gimbals", [0, 0, 0, 0]),
                    "channels": channels,
                    "fps": latest.get("fps", 0.0),
                    "crc_errors": latest.get("crc_errors", 0),
                    "connected": latest.get("connected", False),
                    "state": current_step,
                    "completed": completed,
                }

                line = "data: " + json.dumps(payload) + "\n\n"
                self.wfile.write(line.encode())
                self.wfile.flush()

                time.sleep(0.04)  # ~25 Hz

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    # ------------------------------------------------------------------
    # GET /api/state
    # ------------------------------------------------------------------

    def _serve_state(self) -> None:
        with _state_lock:
            data = state.to_dict()
        self._send_json(data)

    # ------------------------------------------------------------------
    # POST /api/command
    # ------------------------------------------------------------------

    def _handle_command(self) -> None:
        body = self._read_json_body()
        if body is None:
            return

        action = body.get("action")

        with _state_lock:

            if action == "complete_step":
                step = body.get("step", state.current_step)
                state.complete_step(step)
                _log({"event": "complete_step", "step": step})
                self._send_json({"ok": True, "state": state.to_dict()})

            elif action == "set_gimbal":
                state.set_gimbal(
                    label=body["label"],
                    channel=int(body["channel"]),
                    min_val=int(body["min"]),
                    center=int(body["center"]),
                    max_val=int(body["max"]),
                )
                _log({"event": "set_gimbal", "label": body["label"]})
                self._send_json({"ok": True, "state": state.to_dict()})

            elif action == "set_switch":
                state.set_switch(
                    label=body["label"],
                    channel=int(body["channel"]),
                    positions=body["positions"],
                )
                _log({"event": "set_switch", "label": body["label"]})
                self._send_json({"ok": True, "state": state.to_dict()})

            elif action == "set_roller":
                state.set_roller(
                    label=body["label"],
                    channel=int(body["channel"]),
                    min_val=int(body["min"]),
                    max_val=int(body["max"]),
                    has_detent=bool(body.get("has_detent", False)),
                )
                _log({"event": "set_roller", "label": body["label"]})
                self._send_json({"ok": True, "state": state.to_dict()})

            elif action == "set_selector":
                state.set_selector(
                    channel=int(body["channel"]),
                    values=body["values"],
                )
                _log({"event": "set_selector"})
                self._send_json({"ok": True, "state": state.to_dict()})

            elif action == "classify":
                with _sample_lock:
                    snap = list(sample_buffer)
                result = classify_channels(snap)
                # JSON keys must be strings
                self._send_json({"ok": True, "classification": {str(k): v for k, v in result.items()}})

            elif action == "detect_movement":
                baseline = body.get("baseline")
                if baseline is None:
                    self._send_json({"error": "baseline required"}, status=400)
                    return
                latest = get_latest()
                current = latest.get("channels", [32768] * 33)
                moved = detect_movement(baseline, current)
                self._send_json({"ok": True, "moved": moved})

            elif action == "back":
                current = state.current_step
                if current in STEP_ORDER:
                    idx = STEP_ORDER.index(current)
                    if idx > 0:
                        prev = STEP_ORDER[idx - 1]
                        state.current_step = prev
                        # Remove previous step from completed so it can be re-done
                        if prev in state.completed_steps:
                            state.completed_steps.remove(prev)
                _log({"event": "back", "from": current})
                self._send_json({"ok": True, "state": state.to_dict()})

            elif action == "reset":
                state.__init__()  # reinitialise in-place
                with _sample_lock:
                    sample_buffer.clear()
                _log({"event": "reset"})
                self._send_json({"ok": True, "state": state.to_dict()})

            else:
                self._send_json({"error": f"unknown action: {action!r}"}, status=400)

    # ------------------------------------------------------------------
    # POST /api/save
    # ------------------------------------------------------------------

    def _handle_save(self) -> None:
        _ensure_research_dir()
        with _state_lock:
            save_calibration(state, CALIBRATION_PATH)
            _log({"event": "save", "path": CALIBRATION_PATH})
            data = state.to_dict()
        self._send_json({"ok": True, "path": CALIBRATION_PATH, "state": data})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send_json({"error": "empty body"}, status=400)
            return None
        try:
            raw = self.rfile.read(length)
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json({"error": f"invalid JSON: {exc}"}, status=400)
            return None

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

def make_server(host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    server.socket.setsockopt(
        __import__("socket").SOL_SOCKET,
        __import__("socket").SO_REUSEADDR,
        1,
    )
    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AX12 Calibration Tool HTTP server")
    parser.add_argument(
        "--mode",
        choices=["demo", "exclusive", "strace"],
        default="demo",
        help="Data source mode (default: demo)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--serial-port",
        default=None,
        help="Serial port path (exclusive/strace modes)",
    )
    args = parser.parse_args()

    # Start the appropriate data source
    if args.mode == "demo":
        print("[server] Demo mode — generating synthetic UMBUS data")
        start_demo_data()
    elif args.mode == "exclusive":
        if not _has_serial_reader:
            print("[server] WARNING: serial_reader module not found; data will be static")
        else:
            kw = {}
            if args.serial_port is not None:
                kw["port"] = args.serial_port
            start_exclusive(**kw)
    elif args.mode == "strace":
        if not _has_serial_reader:
            print("[server] WARNING: serial_reader module not found; data will be static")
        else:
            kw = {}
            if args.serial_port is not None:
                kw["pid"] = int(args.serial_port)
            start_strace(**kw)

    server = make_server(args.host, args.port)
    print(f"[server] Listening on http://{args.host}:{args.port}  (mode={args.mode})")
    print("[server] Press Ctrl-C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
