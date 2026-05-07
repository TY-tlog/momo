#!/usr/bin/env bash
# Convenience launcher for the desktop pet.
#   ./run.sh         # foreground (close terminal -> pet exits)
#   ./run.sh detach  # background, survives terminal close (kill via tray menu or `pkill -f pet.py`)
set -e
cd "$(dirname "$0")"

if [[ "${1:-}" == "detach" ]]; then
    nohup ./venv/bin/python pet.py >/tmp/desktop_pet.log 2>&1 &
    echo "Started in background (PID $!). Log: /tmp/desktop_pet.log"
else
    exec ./venv/bin/python pet.py
fi
