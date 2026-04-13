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

**Expected savings: ~10-15ms** (CZ/DRE disable + VSync phase zeroing; GPU composition and debugfs writes ineffective — see Phase 1 Results)

**Revert:** Reboot (all `debug.*` props reset). The `persist.*` props survive reboot
but are harmless — set them back to 0 if needed.

## Phase 1 Results

Testing revealed that most Phase 1 approaches hit kernel-level barriers:

**What doesn't work:**

- **debugfs DISP_OPT writes are read-only** in this kernel build. `mtkfb_dbg_write()` logs the command but does NOT call `disp_helper_set_option()`. The debugfs interface is a diagnostic stub, not a control path.
- **Direct register writes to PQ pipeline modules** (COLOR0, CCORR0, AAL0, GAMMA0, DITHER0) take effect for a single frame but are overwritten by CMDQ at the next vsync refresh (~17.7ms later). CMDQ reprograms the entire display pipeline every frame from its stored command tables.
- **SF triple buffering** was already disabled, backpressure already off, `latch_unsignaled` already enabled. No additional gains from these.

**What does work:**

- **COLOR0 is already in relay mode** (EN=0x0) — one PQ stage is already bypassed at stock settings.
- **MDP CZ/DRE disable** (`persist.sys.disable_cz`, `persist.sys.disable_dre`) — confirmed effective via setprop.
- **VSync phase offset reduction** (all `debug.sf.*phase_offset*` props to 0) — confirmed effective via setprop.

**Measured Phase 1 savings: ~10-15ms** (CZ/DRE disable + VSync phase zeroing only).

**For deeper display pipeline optimization**, a loadable kernel module is required. The module must call `disp_helper_set_option()` (at kernel address `0xffffff80086c2fc4`) to modify CMDQ command tables for BYPASS_PQ, ANTILATENCY, DIRECT_LINK, and DELAYED_TRIGGER. This requires cross-compiling against the MT8788 kernel source tree.

**PQ pipeline register map** (for kernel module development):

| Module | Base Address |
|--------|-------------|
| COLOR0 | 0x1400e000 |
| CCORR0 | 0x1400f000 |
| AAL0 | 0x14010000 |
| GAMMA0 | 0x14011000 |
| DITHER0 | 0x14012000 |
| DSI0 | 0x14014000 |

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
| **AX12 (Phase 1+2)** | — | **~95-115ms** | 5.5" 720p | $250 |
| **AX12 (Phase 1-3)** | — | **~80-100ms** | 5.5" 720p | $250 |
| **AX12 (Phase 1-4)** | — | **~40-55ms** | 5.5" 720p | $250 |

The AX12 is already competitive at stock settings. With optimization, it could beat dedicated FPV ground stations.

## Summary

| Phase | Risk | Reversible | Expected Savings | Cumulative |
|-------|------|------------|-----------------|------------|
| 1. Runtime tweaks | None | Reboot | 10-15ms | ~125-130ms |
| 1 Results | — | — | Confirmed 10-15ms | See above |
| 2. Persistent props | Low | Restore backup | 15-30ms | ~95-115ms |
| 3. Direct Link mode¹ | Moderate | Reboot | ~17ms | ~80-100ms |
| 4. Kernel patches | High | Reflash stock | 30-50ms | ~40-55ms |

¹ Phase 3 (Direct Link) and deeper Phase 1 optimizations (BYPASS_PQ, ANTILATENCY, DELAYED_TRIGGER) require a kernel module — debugfs writes are non-functional in this build.


## Root Cause Analysis (confirmed 2026-04-13)

The HDMI input latency is caused by the video pipeline architecture:

### Video Input Path


The RN6752M is registered as a camera sensor (imgsensor) in MediaTek's HAL. This means ALL HDMI video passes through the full camera ISP stack:

- 22+ tuning libraries loaded: HDR, scene detection, face capture, 4K, 1080p
- Full 3A processing (AE/AWB/AF) applied to video that needs NONE of it
- Noise reduction, color matrix, tone mapping all active
- DECOUPLE mode adds triple buffering for compositing

### Latency Breakdown (estimated)
| Stage | Latency | Notes |
|-------|---------|-------|
| RN6752M decode | ~0.1ms | 1-3 scan lines |
| MIPI CSI-2 transfer | ~1ms | Hardware, unavoidable |
| ISP processing (3A/NR/HDR) | ~30-50ms | The big one - camera pipeline |
| DECOUPLE mode buffering | ~35-53ms | 2-3 frames at 56.4Hz |
| PQ pipeline (COLOR/CCORR/AAL) | ~10-15ms | Display post-processing |
| Display panel response | ~5-10ms | LCD response time |
| **Total** | **~80-140ms** | Matches observed 140ms |

### Optimization Vectors
1. **CAMSV raw passthrough** - Bypass ISP entirely, send raw frames to memory (documented in MediaTek Genio SDK)
2. **Disable 3A on video input** - If possible in tuning library config
3. **DIRECT_LINK display mode** - Skip DECOUPLE buffering (kernel module needed)
4. **Disable PQ pipeline** - BYPASS_PQ display option (kernel module needed)
5. **Reduce camera tuning** - Strip unnecessary .so libraries to prevent ISP stages from loading


### Display Mode is Dynamic (confirmed 2026-04-13)

The display mode (DECOUPLE vs DIRECT_LINK) is NOT static. It switches dynamically based on the Hardware Resource Table (HRT) and current layer count:

- **DIRECT_LINK mode** (lower latency): Used when layer count and bandwidth are within limits. OVL -> DSI path with minimal buffering.
- **DECOUPLE mode** (higher latency): Triggered when the compositor needs more layers than OVL can handle directly. Adds WDMA -> RDMA triple buffering path (+35-53ms at 56.4Hz).

When Flyshark is running but not displaying HDMI video overlay, the system may stay in DIRECT_LINK. When the HDMI video surface is active (more layers), HRT may force DECOUPLE.

Key property: DISP_OPT_DC_BY_HRT controls automatic DECOUPLE switching.

### Camera FPS Configuration

Available target FPS ranges for the RN6752M video input:
- [15, 15] - fixed 15fps
- [15, 20] - variable 15-20fps
- [20, 20] - fixed 20fps
- [5, 30] - variable 5-30fps
- [30, 30] - fixed 30fps (maximum)

The display runs at 56.39Hz but camera input is capped at 30fps, meaning every other display refresh shows the same frame. This contributes approximately 16-33ms of latency depending on frame timing.

Increasing camera fps above 30 would require a RN6752M driver modification or a different video decoder.


### CAMSV Hardware Available (confirmed 2026-04-13)

Five CAMSV (Camera Sensor Video) DMA engines are present on the AX12:

| Device | Address | Purpose |
|--------|---------|---------|
| camsv1 | 0x1a050000 | Raw DMA engine 1 |
| camsv2 | 0x1a051000 | Raw DMA engine 2 |
| camsv3 | 0x1a052000 | Raw DMA engine 3 |
| camsv5 | 0x1a054000 | Raw DMA engine 5 |
| camsv6 | 0x1a055000 | Raw DMA engine 6 |

CAMSV taps the MIPI CSI-2 receiver output BEFORE the ISP pipeline. A kernel module could route the RN6752M video input directly to CAMSV, bypassing the ISP entirely and eliminating the estimated 30-50ms of ISP processing latency.

No V4L2 framework is loaded (no /dev/video* or /dev/media* nodes). Using CAMSV requires either:
1. A custom kernel module that configures CAMSV DMA and exposes frames via V4L2 or direct buffer mapping
2. Direct register programming via /dev/mem (risky but possible)

This is the single highest-leverage optimization for HDMI input latency.


### Complete Display Options Register Map (56 options)

All DISP_OPT values from debugfs (current state with Flyshark running):

#### Latency-Critical Options
| # | Option | Current | Optimal | Impact |
|---|--------|---------|---------|--------|
| 22 | BYPASS_PQ | 0 (off) | 1 | Skip COLOR/CCORR/AAL/GAMMA/DITHER pipeline |
| 53 | ANTILATENCY | 0 (off) | 1 | Enable anti-latency display mode |
| 41 | DELAYED_TRIGGER | 1 (on) | 0 | Disable batched frame trigger |
| 12 | IDLEMGR_SWTCH_DECOUPLE | 1 (on) | 0 | Prevent idle DECOUPLE switch |
| 52 | ROUND_CORNER | 1 (on) | 0 | Skip round corner processing |

#### Display Mode Options
| # | Option | Value | Notes |
|---|--------|-------|-------|
| 0 | USE_CMDQ | 1 | Command Queue engine active |
| 1 | USE_M4U | 1 | Memory Management Unit for display |
| 10 | SODI_SUPPORT | 1 | Screen On Display Idle |
| 11 | IDLE_MGR | 1 | Idle manager active |
| 14 | SHARE_SRAM | 1 | SRAM sharing between display modules |
| 19 | DECOUPLE_MODE_USE_RGB565 | 0 | 32-bit color in DECOUPLE mode |
| 25 | PRESENT_FENCE | 1 | Fence-based frame presentation |
| 27 | SWITCH_DST_MODE | 0 | No destination mode switching |
| 30 | BYPASS_OVL | 0 | Overlay engine active |
| 34 | SMART_OVL | 0 | Smart overlay disabled |
| 38 | HRT | 1 | Hardware Resource Table active |
| 39 | PARTIAL_UPDATE | 1 | Partial screen update enabled |
| 44 | OVL_EXT_LAYER | 1 | Extended overlay layers |
| 46 | AOD | 1 | Always On Display capable |
| 48 | RSZ | 0 | No display resize/scaling |
| 49 | RPO | 1 | Resize Post-OVL |
| 50 | DUAL_PIPE | 0 | Single display pipe |
| 51 | SHARE_WDMA0 | 1 | Shared WDMA0 |
| 54 | DC_BY_HRT | 0 | No forced DECOUPLE by HRT |

#### DSI Configuration
- Mode: SYNC_PULSE_VDO_MODE (standard video mode)
- High Speed: enabled
- Dual DSI: disabled
- LCM Driver: xm62168_hd720_lcm_drv

#### Latency Optimization Kernel Module Requirements

To achieve minimum display latency, a kernel module must call
disp_helper_set_option() for each critical option. The function
address can be found via kallsyms:
ffffff80086c2fc4 T disp_helper_set_option
ffffff80086c3314 T disp_helper_set_option_by_name

Target changes for latency reduction:
1. BYPASS_PQ: 0 -> 1 (estimated -10-15ms)
2. ANTILATENCY: 0 -> 1 (estimated -5-10ms)
3. DELAYED_TRIGGER: 1 -> 0 (estimated -5ms)
4. IDLEMGR_SWTCH_DECOUPLE: 1 -> 0 (prevents latency spikes)
5. ROUND_CORNER: 1 -> 0 (minor, <1ms)

Combined estimated reduction: 20-30ms from display pipeline alone.
