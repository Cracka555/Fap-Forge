#!/usr/bin/env bash
# Build Linux executable with PyInstaller
# Requires: pip install pyinstaller pillow

set -euo pipefail
echo "Building FapForge for Linux..."
pyinstaller --onefile --console --name FapForge fap_builder.py
echo "Done! Executable at: dist/FapForge"
