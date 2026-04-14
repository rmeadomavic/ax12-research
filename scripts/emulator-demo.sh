#!/data/data/com.termux/files/usr/bin/bash
# Emulator Demo Launcher for RadioMaster AX12
# Uses AX12 gimbals as analog sticks for retro gaming
#
# Installed emulators:
#   - mGBA (Game Boy Advance) - Pokemon, Metroid, Zelda
#   - RetroArch (multi-system) - SNES, N64, Genesis, NES
#   - Chocolate Doom - the classic FPS
#
# Usage:
#   bash scripts/emulator-demo.sh mgba <rom.gba>
#   bash scripts/emulator-demo.sh retroarch <rom>
#   bash scripts/emulator-demo.sh doom
#
# ROMs are not included. Provide your own legally obtained ROM files.
# Place ROMs in ~/roms/ on the device.

export DISPLAY=:0
PY=/data/data/com.termux/files/usr/bin/python3

case "$1" in
    mgba|gba|pokemon)
        ROM="${2:-$(ls ~/roms/*.gba 2>/dev/null | head -1)}"
        if [ -z "$ROM" ]; then
            echo "No GBA ROM found. Place .gba files in ~/roms/"
            echo "Usage: bash scripts/emulator-demo.sh mgba <path/to/rom.gba>"
            exit 1
        fi
        echo "Starting mGBA with: $ROM"
        echo "Controls: Gimbals = D-pad, Touchscreen = buttons"
        echo "  Or use the DOOM controller for gimbal-to-key mapping"
        mgba-qt "$ROM" &
        ;;
    retroarch|snes|n64|starfox|mariokart)
        echo "Starting RetroArch..."
        echo "1. Select a core (snes9x for SNES, mupen64plus for N64)"
        echo "2. Load your ROM"
        echo "Controls: Touch screen or connect a Bluetooth gamepad"
        su 0 am start -n com.retroarch.aarch64/.browser.retroactivity.RetroActivityFuture 2>/dev/null ||         su 0 am start -n com.retroarch/.browser.retroactivity.RetroActivityFuture 2>/dev/null
        ;;
    doom)
        bash ~/ax12-research/scripts/doom-demo.sh "${@:2}"
        ;;
    list)
        echo "=== Installed Emulators ==="
        echo "  mGBA        - Game Boy / Game Boy Advance"
        echo "                Pokemon, Metroid, Zelda, Fire Emblem"
        echo "  RetroArch   - Multi-system (download cores in-app)"
        echo "                SNES: Star Fox, Mario Kart, F-Zero"
        echo "                N64:  Mario 64, Star Fox 64, Zelda OOT"
        echo "                NES:  Mario Bros, Contra, Mega Man"
        echo "  Chocolate Doom - DOOM (Freedoom WAD included)"
        echo
        echo "=== Available ROMs ==="
        ls ~/roms/ 2>/dev/null || echo "  No ROMs found. Place files in ~/roms/"
        echo
        echo "The AX12 has hall-effect gimbals that make better"
        echo "analog sticks than any phone touchscreen."
        ;;
    *)
        echo "AX12 Emulator Demo"
        echo "Usage: bash scripts/emulator-demo.sh <emulator> [rom]"
        echo
        echo "Emulators: mgba, retroarch, doom, list"
        echo "Example:   bash scripts/emulator-demo.sh mgba ~/roms/pokemon.gba"
        ;;
esac
