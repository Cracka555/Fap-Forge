#!/usr/bin/env bash
# FapForge - convenience wrapper
# Drag a source folder onto this script, or run:
#   ./fap_builder.sh <source_dir>
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=""

for probe in python3 python; do
    if command -v "$probe" &>/dev/null; then
        PYTHON="$probe"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3 not found. Install it first."
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "FapForge - Flipper Zero FAP Builder"
    echo "Usage: drop a source folder onto this script, or run:"
    echo "  $0 <source_dir>"
    echo "  $0 --setup     (first-time setup)"
    echo "  $0 --force     (re-download everything)"
    exit 1
fi

exec "$PYTHON" "$DIR/fap_builder.py" "$@"
