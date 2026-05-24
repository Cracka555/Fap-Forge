#!/usr/bin/env bash
# Build macOS executable with PyInstaller
# Requires: pip install pyinstaller pillow

set -euo pipefail
echo "Building FapForge for macOS..."
pyinstaller --onefile --console --name FapForge fap_builder.py
echo "Done! Executable at: dist/FapForge"
