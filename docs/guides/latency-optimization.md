# HDMI Input Latency Optimization Guide

Reducing glass-to-glass latency on the AX12's HDMI input for FPV and camera feeds.

## Current State

| Parameter | Value |
|-----------|-------|
| Measured glass-to-glass latency | ~140ms |
| Display refresh rate | 56.4Hz (17.7ms frame time) |
| HDMI input capture rate | 30fps (camera-limited) |
| Display mode | DECOUPLE (compositor decoupled from display) |
| Buffer strategy | Triple buffering (3 frames in flight) |
| Display pipeline | Camera → ISP → SurfaceFlinger → MDP → Panel |

Each buffer in the pipeline adds one frame time (~17.7ms) of latency. Triple buffering
alone accounts for ~53ms. The ISP, compositor, and display controller add the rest.

**Target: 40-55ms** — competitive with dedicated FPV receivers.

## Phase 1: Safe Runtime Tweaks

These reset on reboot. Zero risk of bricking. Test each one individually.

### 1a. Disable MDP Color Transform (CZ/DRE)

MediaTek's dynamic range enhancement adds a processing stage to every frame.

```bash
su 0 setprop persist.sys.disable_cz 1
su 0 setprop persist.sys.disable_dre 1
# Verify: su 0 getprop persist.sys.disable_cz → should return 1
```

### 1b. Zero VSync Phase Offsets

SurfaceFlinger delays composition relative to VSync to avoid jank. For latency-critical
use, we want composition to start immediately after VSync.

```bash
su 0 setprop debug.sf.phase_offset_ns 0
su 0 setprop debug.sf.early_phase_offset_ns 0
su 0 setprop debug.sf.early_gl_phase_offset_ns 0
su 0 setprop debug.sf.early_app_phase_offset_ns 0
```

Then restart SurfaceFlinger to pick up the new values:
```bash
su 0 stop && su 0 start
```

> **Warning:** `stop && start` restarts the Android runtime. The Flyshark app will
> restart. Your SSH session survives but the display goes black briefly.

### 1c. Force GPU Composition

Skip the MDP hardware overlay path (which adds a pipeline stage) and force everything
through the GPU compositor:

```bash
su 0 setprop debug.sf.hw 0
su 0 setprop debug.hwui.renderer skiagl
```

**Expected savings: ~15-20ms** (1 frame time from phase offsets + processing overhead)

**Revert:** Reboot (all `debug.*` props reset). The `persist.*` props survive reboot
but are harmless — set them back to 0 if needed.

## Phase 2: Persistent Props

Edit `/system/build.prop` to make changes survive reboot. **Back up first.**

```bash
su 0 cp /system/build.prop /sdcard/build.prop.backup
su 0 mount -o remount,rw /system
```

Add or modify these lines in `/system/build.prop`:

```properties
# Reduce buffer queue depth from 3 to 1
# Eliminates ~35ms (2 frame times) of buffering
ro.surface_flinger.max_frame_buffer_acquired_buffers=1

# Persist the CZ/DRE disables from Phase 1
persist.sys.disable_cz=1
persist.sys.disable_dre=1

# VSync phase offsets to zero
debug.sf.phase_offset_ns=0
debug.sf.early_phase_offset_ns=0
debug.sf.early_gl_phase_offset_ns=0
debug.sf.early_app_phase_offset_ns=0

# Disable content-adaptive backlight control (reduces processing)
ro.mtk_cabc_support=0
```

Then remount read-only and reboot:
```bash
su 0 mount -o remount,ro /system
su 0 reboot
```

> **Note:** With `max_frame_buffer_acquired_buffers=1`, you may see occasional tearing
> or dropped frames in non-video UI. This is the latency-vs-smoothness tradeoff.

**Expected savings: ~15-30ms** (buffer reduction is the big win here)

## Phase 3: DIRECT LINK Display Mode

MediaTek MDP supports three modes:
- **DECOUPLE** (default): Triple-buffered, compositor and display run independently
- **DIRECT LINK**: Frame goes straight from compositor to display controller, minimal buffering
- **SINGLE LAYER**: Like direct link but only one overlay layer

### Enable DIRECT LINK

```bash
# Check current mode
su 0 cat /sys/kernel/debug/mtkfb/display_mode

# Switch to direct link
su 0 sh -c 'echo 1 > /sys/kernel/debug/mtkfb/display_mode'
```

**Tradeoffs:** `screencap` may break, possible tearing, some overlay operations may
not work (Flyshark OSD). Revert by writing `0` to the same path, or reboot.

**Expected savings: ~17ms** (eliminates the decouple buffer stage)

## Phase 4: Kernel/Driver Modifications

These require building a custom kernel. The MT8788 kernel source is not public,
but can be extracted from the stock boot image and patched.

### 4a. Camera 60fps Unlock

The HDMI input is captured via the Loitium LT6911UXC bridge, which appears as a
camera sensor to the MT8788 ISP. The imgsensor driver caps it at 30fps.

**What to patch:** The sensor driver's frame rate table in the imgsensor subsystem.
Look for the LT6911 or similar bridge driver under `drivers/misc/mediatek/imgsensor/`.
Change the max framerate from 30 to 60 in the sensor info struct.

**Impact:** Doubles the capture rate, cutting one frame time (~17ms) from the pipeline.

### 4b. camsv Raw Passthrough

The MT8788 ISP has a "camsv" (camera SV) path that bypasses ISP processing entirely,
delivering raw frames directly to memory. This skips:
- Auto-exposure computation
- Color correction
- Noise reduction

**What to patch:** Configure the camsv DMA path in the cam_isp driver to route the
HDMI bridge output directly to the frame buffer, bypassing the full ISP pipeline.

**Impact:** Eliminates ISP processing latency (~16-33ms depending on pipeline depth).

**Expected savings: ~30-50ms combined** (but requires significant kernel work)

## How to Measure Latency

### Dual-Screen Timer Method

1. Run a millisecond timer on the HDMI source (any web-based ms clock works)
2. Display the HDMI feed on the AX12
3. Photograph both screens simultaneously with a third device (burst mode)
4. Read the ms difference between displays in the photo

### Tips

- Take 10+ samples and average — individual frames vary by up to 1 frame time
- Test with Flyshark running (it's the real-world use case)
- Measure after each phase to track incremental improvement
- SurfaceFlinger stats: `su 0 dumpsys SurfaceFlinger --latency`

## Competitor Comparison

| Device | Claimed Latency | Measured Latency | Display | Price |
|--------|----------------|------------------|---------|-------|
| Herelink v2 | 110ms | 250-280ms | 5.5" 1080p | ~$500 |
| SIYI MK32 | 110ms | ~180ms | 7" 1080p | ~$700 |
| AX12 (stock) | N/A | ~140ms | 5.5" 720p | ~$250 |
| **AX12 (Phase 1+2)** | — | **~90-110ms** | 5.5" 720p | $250 |
| **AX12 (Phase 1-3)** | — | **~75-95ms** | 5.5" 720p | $250 |
| **AX12 (Phase 1-4)** | — | **~40-55ms** | 5.5" 720p | $250 |

The AX12 is already competitive at stock settings. With optimization, it could beat dedicated FPV ground stations.

## Summary

| Phase | Risk | Reversible | Expected Savings | Cumulative |
|-------|------|------------|-----------------|------------|
| 1. Runtime tweaks | None | Reboot | 15-20ms | ~120ms |
| 2. Persistent props | Low | Restore backup | 15-30ms | ~90-105ms |
| 3. Direct Link mode | Moderate | Reboot | ~17ms | ~75-90ms |
| 4. Kernel patches | High | Reflash stock | 30-50ms | ~40-55ms |
