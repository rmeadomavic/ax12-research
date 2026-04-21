# MT8788 Platform Research

Key findings about the MediaTek MT8788 / MT6771 platform relevant to AX12 optimization.
Cross-referenced against kernel source, device tree, and vendor documentation.

## SoC Identity

MT8788, MT6771, and Helio P60 are the same silicon — TSMC 12nm FinFET (CLN12FFC).
MT6771 is the phone SKU, MT8788 the tablet SKU. The AX12 kernel and device tree use
`mt6771` throughout. All three names map to the same die, same stepping.

| Property | Value |
|----------|-------|
| CPU | 4× Cortex-A73 (big) + 4× Cortex-A53 (LITTLE), big.LITTLE DynamIQ |
| GPU | Mali-G72 MP3 (Bifrost architecture) |
| Process | TSMC 12nm FinFET (CLN12FFC) |
| ISP | Dual-core ISP, supports dual cameras |
| Modem | Integrated Cat-7 LTE (not used on AX12 — no SIM slot) |
| APU | MediaTek APU 1.0 (VPU + MDLA, not used on AX12) |

Source: MediaTek product brief, confirmed via `/proc/cpuinfo` and device tree.

## Display Pipeline

The MT6771 display subsystem has two operating modes, configured via
`CONFIG_MTK_DISPLAY_DECOUPLE_SUPPORT` and runtime mode selection:

### DIRECT_LINK (mode 1)
```
OVL → COLOR → CCORR → AAL → GAMMA → DITHER → DSI
```
Single-pass pipeline. The OVL (overlay) engine composites layers and feeds directly
to the DSI encoder. **Lowest latency** — no intermediate buffer. Requires the
display clock and GPU render to be synchronous.

### DECOUPLE (mode 2)
```
OVL → WDMA → (framebuffer) → RDMA → COLOR → ... → DSI
```
The OVL writes to a framebuffer via WDMA, then RDMA reads it out to the display
pipeline asynchronously. **Adds one frame of latency** (~14ms at 720p/60Hz) but
decouples the render clock from the display refresh.

The AX12 runs **DECOUPLE mode by default**. This is the safer mode for Android
SurfaceFlinger but contributes to the overall ~140ms HDMI input latency measured
by MadsTech. Switching to DIRECT_LINK would save ~14ms but requires kernel
configuration changes and stability testing.

Source: `drivers/misc/mediatek/video/mt6771/dispsys/` in MT6771 BSP kernel.

## Camera ISP: CAMSV Raw DMA

The MT6771 ISP includes `camsv` (camera server) blocks that provide raw sensor data
via DMA, **bypassing all ISP processing** (debayer, NR, tone mapping, etc.).

This is relevant for the HDMI input path — the RN6752M video decoder presents as a
camera sensor on MIPI CSI-2. Using camsv could provide lower-latency raw frame
access compared to the full ISP pipeline.

Configuration sequence:
1. Link seninf (sensor interface) pad to camsv via `media-ctl`
2. Set pixel format on the camsv V4L2 device node
3. Capture frames via standard V4L2 (VIDIOC_DQBUF)

Requires `CONFIG_VIDEO_MEDIATEK_ISP_CAMSV` or equivalent in the kernel. The AX12
stock kernel may not expose camsv device nodes — needs verification.

Source: `drivers/media/platform/mtk-isp/camsv/` in MT6771 BSP.

## USB Controller

| Block | Base Address | Function |
|-------|-------------|----------|
| MUSB-HDRC (Mentor) | 0x11200000 | USB 2.0 OTG controller |
| XHCI | 0x11200000 + offset | USB 3.0 host controller |

The silicon supports OTG (host + device mode), but the AX12 kernel has USB host
disabled:

- `CONFIG_USB_MTK_OTG` — **not set**
- `CONFIG_SSUSB_DRV` — **not set**
- `CONFIG_SSUSB_MTK_XHCI` — **not set**

The device tree node needs `dr_mode = "otg"` (currently device-only). Enabling USB
host mode requires a custom kernel with the MTK SSUSB driver compiled in.

Source: AX12 kernel `.config`, device tree `usb` node.

## Competitor Latency Comparison

Measured end-to-end video latency (camera sensor to display pixels), not
vendor-advertised figures:

| System | Advertised | Measured | Source |
|--------|-----------|----------|--------|
| Herelink | 80–110ms | 250–280ms | Independent testing (Oscar Liang, MadsTech) |
| SIYI MK15 | 110ms | ~180ms | Community testing |
| AX12 (HDMI in) | — | ~140ms | MadsTech (HDZero baseline subtracted) |

The AX12 at ~140ms is competitive with dedicated ground station systems costing
2–3× more. The latency is dominated by the HDMI→analog→MIPI conversion chain and
DECOUPLE display mode, not SoC processing — there is headroom for optimization.

Note: AX12 latency figure is for HDMI input only. Total system latency includes
the air link (varies by VTX system).

## Kernel Source Repositories

No official MediaTek kernel source for the AX12. The closest matches for
driver reference and modification:

| Repository | Match Quality | Notes |
|------------|--------------|-------|
| [Hadenix/android_kernel_alps-4.4](https://github.com/Hadenix/android_kernel_alps-4.4) | **Exact** — 4.4.146, mt6771 | Best reference. Same kernel version, same platform. |
| OrangePi 4G-IOT BSP | Good — complete MT6737/MT6771 driver tree | Useful for driver cross-reference. Different SoC but shared MediaTek driver framework. |
| [nokia-dev/android_kernel_nokia_mt6771](https://github.com/AylaAsia-ZhiqinChen/MT8365_Q0_Ayla) | Good — MT6771 specific | Nokia 3.1 Plus used the same SoC. Display and ISP drivers match. |

For AX12-specific work, start with Hadenix — it matches the exact kernel version
and SoC variant.

## Prior Art

As of April 2026, no public documentation exists for:
- The UMBUS protocol (RadioMaster's internal SoC↔MCU bus)
- AX12 hardware teardown or component identification
- AT32 MCU firmware analysis
- Flyshark app internals or class hierarchy

This repository ([ax12-research](https://github.com/rmeadomavic/ax12-research))
is the only public source for this information.

## References

- [Hardware Map](hardware-map.md) — Full AX12 peripheral inventory
- [Device Tree Analysis](device-tree.md) — SoC node-by-node breakdown
- [System Audit](system-audit.md) — Runtime system state
- [UMBUS Protocol](../protocol/umbus-protocol.md) — Complete protocol specification
