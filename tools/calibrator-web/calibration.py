"""
calibration.py — CalibrationState dataclass and JSON persistence helpers.

Tracks wizard step progress and the mapping of physical AX12 controls
to UMBUS channels. Python stdlib only — no external dependencies.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict

STEP_ORDER = [
    "discovery",
    "gimbal_id",
    "gimbal_cal",
    "switches",
    "rollers",
    "trims",
    "verify",
    "save",
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class CalibrationState:
    current_step: str = "discovery"
    completed_steps: List[str] = field(default_factory=list)
    gimbals: Dict = field(default_factory=dict)
    switches: Dict = field(default_factory=dict)
    rollers: Dict = field(default_factory=dict)
    selector_6pos: Dict = field(default_factory=dict)
    trims: Dict = field(default_factory=dict)
    buttons: Dict = field(default_factory=dict)
    serial_mode: str = "exclusive"
    created: str = field(default_factory=_now_iso)
    updated: str = field(default_factory=_now_iso)

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    def complete_step(self, step: str) -> None:
        """Mark *step* complete and advance current_step to the next one."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        if step in STEP_ORDER:
            idx = STEP_ORDER.index(step)
            if idx + 1 < len(STEP_ORDER):
                self.current_step = STEP_ORDER[idx + 1]
        self.updated = _now_iso()

    # ------------------------------------------------------------------
    # Control setters
    # ------------------------------------------------------------------

    def set_gimbal(self, label: str, channel: int, min_val: int,
                   center: int, max_val: int) -> None:
        self.gimbals[label] = {
            "channel": channel,
            "type": "gimbal",
            "min": min_val,
            "center": center,
            "max": max_val,
        }
        self.updated = _now_iso()

    def set_switch(self, label: str, channel: int, positions: list) -> None:
        n = len(positions)
        self.switches[label] = {
            "channel": channel,
            "type": f"{n}pos",
            "values": sorted(positions),
        }
        self.updated = _now_iso()

    def set_roller(self, label: str, channel: int, min_val: int,
                   max_val: int, has_detent: bool) -> None:
        self.rollers[label] = {
            "channel": channel,
            "type": "roller",
            "min": min_val,
            "max": max_val,
            "has_detent": has_detent,
        }
        self.updated = _now_iso()

    def set_selector(self, channel: int, values: list) -> None:
        self.selector_6pos = {
            "channel": channel,
            "type": "selector",
            "values": sorted(values),
        }
        self.updated = _now_iso()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "gimbals": self.gimbals,
            "switches": self.switches,
            "rollers": self.rollers,
            "selector_6pos": self.selector_6pos,
            "trims": self.trims,
            "buttons": self.buttons,
            "serial_mode": self.serial_mode,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalibrationState":
        state = cls.__new__(cls)
        state.current_step = data.get("current_step", "discovery")
        state.completed_steps = data.get("completed_steps", [])
        state.gimbals = data.get("gimbals", {})
        state.switches = data.get("switches", {})
        state.rollers = data.get("rollers", {})
        state.selector_6pos = data.get("selector_6pos", {})
        state.trims = data.get("trims", {})
        state.buttons = data.get("buttons", {})
        state.serial_mode = data.get("serial_mode", "exclusive")
        state.created = data.get("created", "")
        state.updated = data.get("updated", "")
        return state


# ------------------------------------------------------------------
# File I/O helpers
# ------------------------------------------------------------------

def save_calibration(state: CalibrationState, path: str) -> None:
    """Write *state* to *path* as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state.to_dict(), fh, indent=2)


def load_calibration(path: str) -> CalibrationState:
    """Load CalibrationState from *path*. Returns a fresh state if missing."""
    if not os.path.exists(path):
        return CalibrationState()
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return CalibrationState.from_dict(data)


def log_event(logpath: str, event: dict) -> None:
    """Append *event* (with auto-added 'ts') as a JSONL line to *logpath*."""
    record = {"ts": _now_iso(), **event}
    with open(logpath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
