# FapForge

A minimalistic development utility for building Flipper Zero applications (.fap) for the [Sor3nt/Flipper-Zero-ESP32-Port](https://github.com/Sor3nt/Flipper-Zero-ESP32-Port).

Eliminates the need for a full ESP-IDF/ufbt build environment — just drag your source folder onto the executable.

## Features

- **Automatic Environment** — Downloads the xtensa-esp32s3-elf toolchain and SDK headers on first run
- **Effortless Build** — Compiles .c/.cpp sources and produces a relocatable Xtensa ELF
- **Symbol Check** — Validates all undefined symbols against firmware_api.c after linking
- **C++ & Assets** — Native C++ support, icon processing via Pillow, auto sprite generation
- **Cross-Platform** — Builds on Windows, Linux, and macOS (auto-detected toolchain)
- **Force Refresh** — `--force` flag re-downloads all headers and clears stubs

## Usage

```
fap_builder                  # first-time setup
fap_builder --force          # re-download everything from scratch
fap_builder <source_dir>     # drag & drop build
fap_builder.sh <source_dir>  # Linux/macOS convenience wrapper
```

## Downloads

Pre-built binaries are available for all platforms:

| Platform | Download |
|----------|----------|
| Windows x86_64 | `FapForge-windows-x86_64.exe` |
| Linux x86_64 | `FapForge-linux-x86_64` |
| macOS x86_64 | `FapForge-macos-x86_64` |
| Source (all platforms) | `FapForge-<version>-source.tgz` |

## Building from Source

```bash
# Install dependencies
pip install pyinstaller pillow

# Windows
pyinstaller --onefile --console --icon=FapForge.ico --name FapForge fap_builder.py

# Linux / macOS
pyinstaller --onefile --console --name FapForge fap_builder.py
```

## Project Contents

| File | Description |
|------|-------------|
| `fap_builder.py` | Full Python source code |
| `fap_builder.sh` | Convenience wrapper for Linux/macOS |
| `FapForge.ico` | Application icon |
| `build_win.bat` | Windows build script |
| `build_linux.sh` | Linux build script |
| `build_macos.sh` | macOS build script |
| `.github/workflows/release.yml` | GitHub Actions CI for releases |
| `README.md` | This file |
| `LICENSE` | GNU General Public License v3 |

## License

Copyright (C) 2025

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

The source code (`fap_builder.py`) is provided alongside the executable
so anyone can verify, modify, and rebuild it.
