#!/bin/bash
# Search native library for host/trainer-related strings and symbols.
# Run on device: su 0 bash scripts/search-host-strings.sh
#
# Output goes to /sdcard/AX12LUA/host-strings-report.txt

LIB=$(echo /data/app/com.Flyshark.RadioMasterAX-*/lib/arm64/libRadioMasterAX_arm64-v8a.so)
OUT="/sdcard/AX12LUA/host-strings-report.txt"

if [ ! -f "$LIB" ]; then
  echo "ERROR: native library not found at $LIB"
  exit 1
fi

{
echo "== Host/Trainer String Search Results =="
echo "== Library: $LIB"
echo "== Date: $(date)"
echo ""

echo "==== 1. UI strings: host, trainer, pupil, master, slave, buddy, coach ===="
strings "$LIB" | grep -iE 'host|trainer|pupil|master|slave|buddy|coach' | sort -u
echo ""

echo "==== 2. STR_ constants (trainer/host) ===="
strings "$LIB" | grep -iE 'STR_(TRAINER|HOST|MASTER|SLAVE|PUPIL|BUDDY)' | sort -u
echo ""

echo "==== 3. All STR_ constants (complete list) ===="
strings "$LIB" | grep -E '^STR_' | sort -u
echo ""

echo "==== 4. Function/class names containing train/host/pupil ===="
strings "$LIB" | grep -iE '(set|get|is|has|on|update|sync)(Trainer|Host|Pupil|Master|Slave|Buddy)' | sort -u
echo ""

echo "==== 5. RcSetSystem and general settings references ===="
strings "$LIB" | grep -iE 'RcSetSystem|RcSetTrain|systemSetting|generalSetting|trainerSetting' | sort -u
echo ""

echo "==== 6. SBUS references ===="
strings "$LIB" | grep -iE 'sbus|s\.bus|s-bus' | sort -u
echo ""

echo "==== 7. Trainer-related ELF symbols ===="
if command -v readelf >/dev/null 2>&1; then
  readelf -s --wide "$LIB" 2>/dev/null | grep -iE 'train|pupil|buddy' | head -100
else
  echo "(readelf not available -- install binutils)"
fi
echo ""

echo "== Search complete =="
} > "$OUT" 2>&1

echo "Results written to $OUT"
echo "Lines: $(wc -l < "$OUT")"
