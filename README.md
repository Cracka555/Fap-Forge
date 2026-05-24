# FapForge

A minimalistic development utility for building Flipper Zero applications (.fap) for the [Sor3nt/Flipper-Zero-ESP32-Port](https://github.com/Sor3nt/Flipper-Zero-ESP32-Port).

Eliminates the need for a full ESP-IDF/ufbt build environment — just drag your source folder onto the exe.

## Features

- **Automatic Environment** — Downloads the xtensa-esp32s3-elf toolchain and SDK headers on first run
- **Effortless Build** — Compiles .c/.cpp sources and produces a relocatable Xtensa ELF
- **Symbol Check** — Validates all undefined symbols against firmware_api.c after linking
- **C++ & Assets** — Native C++ support, icon processing via Pillow, auto sprite generation

## Usage

```
fap_builder.exe               # first-time setup
fap_builder.exe <source_dir>  # drag & drop build
```

## Project Contents

| File | Description |
|------|-------------|
| `FapForge.exe` | Pre-built Windows executable (PyInstaller) |
| `fap_builder.py` | Full Python source code |
| `fap_builder.spec` | PyInstaller build spec (no icon) |
| `fap_builder.exe.spec` | PyInstaller build spec (with icon) |
| `fap_builder.ico` | Application icon |
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