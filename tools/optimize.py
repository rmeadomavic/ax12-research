#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Tier 2 Performance Optimizer

Applies safe, persistent performance optimizations to the RadioMaster AX12.
Targets bloatware, camera post-processing, and CPU governor settings that
don't affect UMBUS communication or RF stability.

Tier 2 = safe optimizations only. Tier 3 (--tier3) adds aggressive
optimizations like buffer reduction (~35ms savings, risk of tearing).

Usage:
    su 0 python3 tools/optimize.py              # dry-run (shows changes)
    su 0 python3 tools/optimize.py --apply       # apply Tier 2 optimizations
    su 0 python3 tools/optimize.py --apply --tier3  # apply Tier 2 + Tier 3
    su 0 python3 tools/optimize.py --revert      # undo all optimizations
"""

import argparse
import logging
import os
import subprocess
import sys
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple


# --- Configuration ---

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# System properties to set at runtime (and persist in build.prop)
OPTIMIZATION_PROPS = {
    # Disable MDP camera post-processing (CZ = color zone, DRE = dynamic range)
    # MediaTek HAL checks both vendor-specific and system property paths.
    # persist.vendor.camera.mdp.*.enable — targets camera MDP pipeline
    # persist.sys.disable_* — system-level disable (confirmed Phase 1 testing)
    # Setting both ensures CZ/DRE is disabled regardless of code path.
    "persist.vendor.camera.mdp.cz.enable": ("0", "1"),   # (optimized, default)
    "persist.vendor.camera.mdp.dre.enable": ("0", "1"),
    "persist.sys.disable_cz": ("1", "0"),                 # (optimized=disabled, default=enabled)
    "persist.sys.disable_dre": ("1", "0"),
    # Zero VSync phase offsets (from default 6.6ms)
    # Confirmed effective in Phase 1 testing — composition starts immediately after VSync
    "debug.sf.phase_offset_ns": ("0", "6600000"),
    "debug.sf.early_phase_offset_ns": ("0", "6600000"),
    "debug.sf.early_gl_phase_offset_ns": ("0", "6600000"),
    "debug.sf.early_app_phase_offset_ns": ("0", "6600000"),
}

# Tier 3: Aggressive optimizations (higher risk, higher reward)
# Buffer reduction eliminates ~35ms but may cause tearing in non-video UI.
# CABC disable reduces display processing. Both require explicit --tier3 opt-in.
TIER3_PROPS = {
    "ro.surface_flinger.max_frame_buffer_acquired_buffers": ("1", "3"),
    "ro.mtk_cabc_support": ("0", "1"),
}

# Packages to disable
DISABLE_PACKAGES = [
    ("com.baidu.map.location", "Baidu location service"),
    ("com.mediatek.duraspeed", "DuraSpeed (aggressive app killing)"),
]

# GMS services that consume RAM but serve no purpose on an RC transmitter
GMS_KILL_PACKAGES = [
    "com.google.android.gms.persistent",
    "com.google.android.gms.ui",
    "com.google.android.gms.unstable",
    "com.google.process.gapps",
]

# CPU governor: big cores (A73, cores 4-7)
BIG_CORES = [4, 5, 6, 7]
GOVERNOR_PATH_TEMPLATE = "/sys/devices/system/cpu/cpu{}/cpufreq/scaling_governor"
TARGET_GOVERNOR = "performance"
DEFAULT_GOVERNOR = "schedplus"

# build.prop markers for our additions
BUILDPROP_MARKER_START = "# --- AX12 Tier 2 Optimizations (do not edit) ---"
BUILDPROP_MARKER_END = "# --- End AX12 Tier 2 Optimizations ---"
BUILDPROP_TIER3_MARKER_START = "# --- AX12 Tier 3 Aggressive Optimizations ---"
BUILDPROP_TIER3_MARKER_END = "# --- End AX12 Tier 3 Aggressive Optimizations ---"
BUILDPROP_PATH = "/system/build.prop"


class Action(Enum):
    DRY_RUN = auto()
    APPLY = auto()
    REVERT = auto()


@dataclass
class Result:
    """Outcome of a single optimization step."""
    name: str
    success: bool
    message: str
    skipped: bool = False


def run_cmd(cmd: List[str], check: bool = False) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"


def getprop(name: str) -> str:
    """Read an Android system property."""
    _, out, _ = run_cmd(["getprop", name])
    return out


def setprop(name: str, value: str, dry: bool = False) -> Result:
    """Set an Android system property."""
    current = getprop(name)
    if current == value:
        return Result(f"setprop {name}", True, f"already {value}", skipped=True)
    if dry:
        return Result(f"setprop {name}", True, f"would change {current!r} -> {value!r}")
    rc, _, err = run_cmd(["setprop", name, value])
    if rc == 0:
        return Result(f"setprop {name}", True, f"{current!r} -> {value!r}")
    return Result(f"setprop {name}", False, f"failed: {err}")


def pm_disable(package: str, label: str, dry: bool = False) -> Result:
    """Disable a package via pm."""
    rc, out, _ = run_cmd(["pm", "list", "packages", "-d"])
    already_disabled = package in out
    if already_disabled:
        return Result(f"disable {label}", True, "already disabled", skipped=True)
    if dry:
        return Result(f"disable {label}", True, f"would disable {package}")
    rc, out, err = run_cmd(["pm", "disable", package])
    if rc == 0:
        return Result(f"disable {label}", True, f"disabled {package}")
    return Result(f"disable {label}", False, f"failed: {err or out}")


def pm_enable(package: str, label: str, dry: bool = False) -> Result:
    """Re-enable a package via pm."""
    rc, out, _ = run_cmd(["pm", "list", "packages", "-d"])
    is_disabled = package in out
    if not is_disabled:
        return Result(f"enable {label}", True, "already enabled", skipped=True)
    if dry:
        return Result(f"enable {label}", True, f"would enable {package}")
    rc, out, err = run_cmd(["pm", "enable", package])
    if rc == 0:
        return Result(f"enable {label}", True, f"enabled {package}")
    return Result(f"enable {label}", False, f"failed: {err or out}")


def kill_gms(dry: bool = False) -> List[Result]:
    """Kill GMS processes that waste RAM on an RC controller."""
    results = []
    for proc_name in GMS_KILL_PACKAGES:
        if dry:
            results.append(Result(f"kill {proc_name}", True, "would kill if running"))
            continue
        rc, _, err = run_cmd(["am", "force-stop", proc_name])
        # force-stop doesn't fail even if the process isn't running
        results.append(Result(f"kill {proc_name}", True, "killed/stopped"))
    return results


def set_governor(core: int, governor: str, dry: bool = False) -> Result:
    """Set CPU scaling governor for a core."""
    path = GOVERNOR_PATH_TEMPLATE.format(core)
    name = f"cpu{core} governor"
    try:
        with open(path, "r") as f:
            current = f.read().strip()
    except (IOError, PermissionError) as e:
        return Result(name, False, f"cannot read: {e}")

    if current == governor:
        return Result(name, True, f"already {governor}", skipped=True)
    if dry:
        return Result(name, True, f"would change {current} -> {governor}")
    try:
        with open(path, "w") as f:
            f.write(governor)
        return Result(name, True, f"{current} -> {governor}")
    except (IOError, PermissionError) as e:
        return Result(name, False, f"write failed: {e}")


def mount_system_rw() -> bool:
    """Remount /system read-write. Returns True on success."""
    rc, _, _ = run_cmd(["mount", "-o", "remount,rw", "/system"])
    return rc == 0


def mount_system_ro() -> bool:
    """Remount /system read-only."""
    rc, _, _ = run_cmd(["mount", "-o", "remount,ro", "/system"])
    return rc == 0


def read_buildprop() -> str:
    """Read current build.prop contents."""
    try:
        with open(BUILDPROP_PATH, "r") as f:
            return f.read()
    except IOError as e:
        logging.error("Cannot read %s: %s", BUILDPROP_PATH, e)
        return ""


def remove_our_block(content: str, markers=None) -> str:
    """Remove optimization block(s) from build.prop content."""
    if markers is None:
        markers = [
            (BUILDPROP_MARKER_START, BUILDPROP_MARKER_END),
            (BUILDPROP_TIER3_MARKER_START, BUILDPROP_TIER3_MARKER_END),
        ]
    starts = {m[0] for m in markers}
    ends = {m[1] for m in markers}
    lines = content.splitlines(keepends=True)
    out = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped in starts:
            inside = True
            continue
        if stripped in ends:
            inside = False
            continue
        if not inside:
            out.append(line)
    return "".join(out)


def build_our_block(tier3: bool = False) -> str:
    """Build the optimization block(s) for build.prop."""
    lines = [BUILDPROP_MARKER_START]
    for prop, (opt_val, _) in OPTIMIZATION_PROPS.items():
        lines.append(f"{prop}={opt_val}")
    lines.append(BUILDPROP_MARKER_END)
    if tier3:
        lines.append(BUILDPROP_TIER3_MARKER_START)
        for prop, (opt_val, _) in TIER3_PROPS.items():
            lines.append(f"{prop}={opt_val}")
        lines.append(BUILDPROP_TIER3_MARKER_END)
    return "\n".join(lines) + "\n"


def persist_to_buildprop(dry: bool = False, tier3: bool = False) -> Result:
    """Write optimization props to /system/build.prop for boot persistence."""
    content = read_buildprop()
    if not content:
        return Result("build.prop persist", False, "cannot read build.prop")

    # Check if our block is already present and current
    all_props = dict(OPTIMIZATION_PROPS)
    if tier3:
        all_props.update(TIER3_PROPS)
    if BUILDPROP_MARKER_START in content:
        all_present = True
        for prop, (opt_val, _) in all_props.items():
            if f"{prop}={opt_val}" not in content:
                all_present = False
                break
        if all_present:
            return Result("build.prop persist", True, "already up to date", skipped=True)

    if dry:
        label = "Tier 2+3" if tier3 else "Tier 2"
        return Result("build.prop persist", True, f"would write {label} optimization block")

    # Backup
    backup_path = BUILDPROP_PATH + f".bak.{int(time.time())}"
    try:
        shutil.copy2(BUILDPROP_PATH, backup_path)
        logging.info("Backed up build.prop to %s", backup_path)
    except IOError as e:
        return Result("build.prop persist", False, f"backup failed: {e}")

    # Remove any existing blocks, then append fresh
    clean = remove_our_block(content)
    new_content = clean.rstrip("\n") + "\n\n" + build_our_block(tier3=tier3)

    if not mount_system_rw():
        return Result("build.prop persist", False, "failed to remount /system rw")

    try:
        with open(BUILDPROP_PATH, "w") as f:
            f.write(new_content)
        result = Result("build.prop persist", True, f"written (backup: {backup_path})")
    except IOError as e:
        result = Result("build.prop persist", False, f"write failed: {e}")
    finally:
        mount_system_ro()

    return result


def revert_buildprop(dry: bool = False) -> Result:
    """Remove our optimization block from build.prop."""
    content = read_buildprop()
    if not content:
        return Result("build.prop revert", False, "cannot read build.prop")

    if BUILDPROP_MARKER_START not in content:
        return Result("build.prop revert", True, "no optimization block found", skipped=True)

    if dry:
        return Result("build.prop revert", True, "would remove optimization block")

    clean = remove_our_block(content)

    if not mount_system_rw():
        return Result("build.prop revert", False, "failed to remount /system rw")

    try:
        with open(BUILDPROP_PATH, "w") as f:
            f.write(clean)
        result = Result("build.prop revert", True, "removed optimization block")
    except IOError as e:
        result = Result("build.prop revert", False, f"write failed: {e}")
    finally:
        mount_system_ro()

    return result


def apply_optimizations(action: Action, tier3: bool = False) -> List[Result]:
    """Apply or preview Tier 2 (and optionally Tier 3) optimizations."""
    dry = action == Action.DRY_RUN
    results = []

    logging.info("=== System Properties (Tier 2) ===")
    for prop, (opt_val, _) in OPTIMIZATION_PROPS.items():
        results.append(setprop(prop, opt_val, dry=dry))

    if tier3:
        logging.info("=== System Properties (Tier 3 — aggressive) ===")
        for prop, (opt_val, _) in TIER3_PROPS.items():
            results.append(setprop(prop, opt_val, dry=dry))

    logging.info("=== Package Management ===")
    for pkg, label in DISABLE_PACKAGES:
        results.append(pm_disable(pkg, label, dry=dry))

    logging.info("=== GMS Cleanup ===")
    results.extend(kill_gms(dry=dry))

    logging.info("=== CPU Governor (big cores A73) ===")
    for core in BIG_CORES:
        results.append(set_governor(core, TARGET_GOVERNOR, dry=dry))

    logging.info("=== Persistence (build.prop) ===")
    results.append(persist_to_buildprop(dry=dry, tier3=tier3))

    return results


def revert_optimizations(action: Action) -> List[Result]:
    """Revert all Tier 2 and Tier 3 optimizations."""
    dry = action == Action.DRY_RUN
    results = []

    logging.info("=== Reverting System Properties (Tier 2) ===")
    for prop, (_, default_val) in OPTIMIZATION_PROPS.items():
        results.append(setprop(prop, default_val, dry=dry))

    logging.info("=== Reverting System Properties (Tier 3) ===")
    for prop, (_, default_val) in TIER3_PROPS.items():
        results.append(setprop(prop, default_val, dry=dry))

    logging.info("=== Re-enabling Packages ===")
    for pkg, label in DISABLE_PACKAGES:
        results.append(pm_enable(pkg, label, dry=dry))

    logging.info("=== Reverting CPU Governor ===")
    for core in BIG_CORES:
        results.append(set_governor(core, DEFAULT_GOVERNOR, dry=dry))

    logging.info("=== Reverting build.prop ===")
    results.append(revert_buildprop(dry=dry))

    return results


def print_results(results: List[Result], action: Action) -> int:
    """Print results table and return exit code."""
    mode_label = {
        Action.DRY_RUN: "DRY RUN",
        Action.APPLY: "APPLIED",
        Action.REVERT: "REVERTED",
    }[action]

    print(f"\n{'─' * 60}")
    print(f"  AX12 Performance Optimization — {mode_label}")
    print(f"{'─' * 60}")

    applied = 0
    skipped = 0
    failed = 0

    for r in results:
        if r.skipped:
            icon = "·"
            skipped += 1
        elif r.success:
            icon = "+"
            applied += 1
        else:
            icon = "!"
            failed += 1
        logging.info("[%s] %-35s %s", icon, r.name, r.message)

    print(f"{'─' * 60}")
    print(f"  {applied} applied, {skipped} skipped, {failed} failed")
    if action == Action.DRY_RUN:
        print("  Run with --apply to execute these changes")
    print(f"{'─' * 60}\n")

    return 1 if failed > 0 else 0


def main():
    parser = argparse.ArgumentParser(
        description="AX12 Performance Optimizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Default mode is dry-run. Use --apply to make changes.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Apply Tier 2 optimizations")
    group.add_argument("--revert", action="store_true", help="Revert all optimizations")
    parser.add_argument("--tier3", action="store_true",
                        help="Include aggressive Tier 3 optimizations (buffer reduction, ~35ms savings, risk of tearing)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )

    # Root check
    if os.getuid() != 0:
        logging.error("This script must run as root: su 0 python3 %s", sys.argv[0])
        sys.exit(1)

    if args.apply:
        action = Action.APPLY
    elif args.revert:
        action = Action.REVERT
    elif args.tier3:
        action = Action.APPLY  # --tier3 alone implies --apply
    else:
        action = Action.DRY_RUN

    tier_label = "Tier 2+3" if args.tier3 else "Tier 2"
    logging.info("AX12 Optimizer — mode: %s (%s)", action.name, tier_label)

    if args.revert:
        results = revert_optimizations(action)
    else:
        results = apply_optimizations(action, tier3=args.tier3)

    exit_code = print_results(results, action)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
