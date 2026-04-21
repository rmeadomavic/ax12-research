# Device Tree

Decompiled device tree source and extracted peripheral listings from the AX12's MT8788 SoC.

## Files

| File | Description |
|------|-------------|
| `ax12.dts` | Full decompiled device tree source |
| `all-nodes.txt` | Flattened list of all DT nodes |
| `compatible-nodes.txt` | Nodes with `compatible` strings (driver matches) |
| `peripherals.txt` | Summary of key peripherals and their addresses |

## How These Were Extracted

```bash
# Decompile the DTB from the boot image
su 0 dd if=/dev/block/by-name/dtbo of=/tmp/dtbo.img bs=4096
dtc -I dtb -O dts /tmp/dtbo.img > ax12.dts

# Extract node listings
grep -E '^\s+\w' ax12.dts | sort > all-nodes.txt
grep 'compatible' ax12.dts > compatible-nodes.txt
```

For analysis of what these peripherals mean for the AX12, see [docs/hardware/device-tree.md](../docs/hardware/device-tree.md).
