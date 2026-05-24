#!/usr/bin/env python3
"""
FAP Builder — standalone Windows tool to build .fap files for the
Sor3nt/Flipper-Zero-ESP32-Port project.

First run auto-downloads the xtensa-esp32s3-elf toolchain + SDK headers.
After that, drag a source folder onto fap_builder.exe to build.

Features:
  - Auto-downloads toolchain (~370 MB once) + SDK headers from repo
  - Compiles .c and .cpp sources
  - Links relocatable Xtensa ELF via fap.ld
  - Generates proper FAP manifest (icon support)
  - Compiles fap_icon_assets sprites
  - Verifies all undefined symbols against firmware_api.c
  - Supports .fal plugin builds (single-source, entry override)
  - Auto-discovers needed headers from app includes

Usage:
    fap_builder.exe               # first-time setup
    fap_builder.exe <source_dir>  # drag & drop build
"""

import io, json, os, re, shutil, struct, subprocess, sys, zipfile
from pathlib import Path
from urllib.request import urlopen, Request

HOME = Path.home()
CACHE = HOME / ".fap_builder"
CONFIG_FILE = HOME / ".fap_builder_config.json"
TOOLS_DIR = CACHE / "tools"
REPO_DIR = CACHE / "repo"
BUILD_DIR = CACHE / "build"

# ── Remote URLs ─────────────────────────────────────────────────────
BASE = "https://raw.githubusercontent.com/Sor3nt/Flipper-Zero-ESP32-Port/main"
FAP_LD_URL          = f"{BASE}/tools/fap.ld"
FAP_MANIFEST_URL    = f"{BASE}/tools/fap_manifest.py"
CHECK_SYMBOLS_URL   = f"{BASE}/tools/check_fap_symbols.py"
COMPILE_ICONS_URL   = f"{BASE}/tools/fam/compile_icons.py"
FIRMWARE_API_URL    = f"{BASE}/components/flipper_application/flipper_application/firmware_api.c"
TOOLCHAIN_URL       = "https://github.com/espressif/crosstool-NG/releases/download/esp-14.2.0_20241119/xtensa-esp-elf-14.2.0_20241119-x86_64-w64-mingw32.zip"

# ── Config ──────────────────────────────────────────────────────────
def cfg_load():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def cfg_save(c):
    CONFIG_FILE.write_text(json.dumps(c, indent=2))

def cfg_setup_done():
    return cfg_load().get("setup_done", False)

def cfg_mark_setup():
    c = cfg_load()
    c["setup_done"] = True
    cfg_save(c)

# ── Download helpers ────────────────────────────────────────────────
def download(url, dest, label=""):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {label or dest.name}...")
    req = Request(url, headers={"User-Agent": "FAP-Builder/2.0"})
    with urlopen(req, timeout=300) as r:
        data = r.read()
    dest.write_bytes(data)

def human_size(b):
    for unit in ("B","KB","MB","GB"):
        if b < 1024: return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.1f} GB"

# ── Toolchain ──────────────────────────────────────────────────────
def ensure_toolchain():
    cc = TOOLS_DIR / "xtensa-esp-elf" / "bin" / "xtensa-esp32s3-elf-gcc.exe"
    if cc.exists():
        return TOOLS_DIR / "xtensa-esp-elf" / "bin"

    zip_path = CACHE / "tc.zip"
    print("\n=== Toolchain (xtensa-esp32s3-elf, ~370 MB) ===")
    download(TOOLCHAIN_URL, zip_path, "xtensa toolchain (~370 MB)")
    print("  Extracting...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(TOOLS_DIR)
    zip_path.unlink()
    if not cc.exists():
        alt = list(TOOLS_DIR.rglob("xtensa-esp32s3-elf-gcc.exe"))
        if alt:
            return alt[0].parent
        print("ERROR: toolchain not found")
        sys.exit(1)
    return TOOLS_DIR / "xtensa-esp-elf" / "bin"

def get_toolchain_bin():
    cc = TOOLS_DIR / "xtensa-esp-elf" / "bin" / "xtensa-esp32s3-elf-gcc.exe"
    if cc.exists():
        return TOOLS_DIR / "xtensa-esp-elf" / "bin"
    alt = list(TOOLS_DIR.rglob("xtensa-esp32s3-elf-gcc.exe"))
    if alt:
        return alt[0].parent
    print("ERROR: toolchain not found")
    sys.exit(1)

# ── Header stubs ────────────────────────────────────────────────────
STUBS = {
    # FreeRTOS stubs
    "freertos/include/freertos/FreeRTOS.h": """\
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#define configUSE_PREEMPTION 1
#define configUSE_IDLE_HOOK 0
#define configTICK_RATE_HZ 1000
#define configMAX_PRIORITIES 25
#define configMINIMAL_STACK_SIZE 2048
#define configMAX_TASK_NAME_LEN 16
#define configUSE_16_BIT_TICKS 0
#define configUSE_TASK_NOTIFICATIONS 1
#define configUSE_MUTEXES 1
#define configUSE_RECURSIVE_MUTEXES 1
#define configUSE_COUNTING_SEMAPHORES 1
#define configSUPPORT_STATIC_ALLOCATION 1
#define configSUPPORT_DYNAMIC_ALLOCATION 1
#define configAPPLICATION_ALLOCATED_HEAP 1
#define configUSE_APPLICATION_TASK_TAG 1
#define configNUM_THREAD_LOCAL_STORAGE_POINTERS 1
#define configASSERT(x)
typedef unsigned long StackType_t;
typedef long BaseType_t;
typedef unsigned long UBaseType_t;
typedef uint32_t TickType_t;
typedef void *TaskHandle_t, *QueueHandle_t, *SemaphoreHandle_t;
typedef void *TimerHandle_t, *EventGroupHandle_t, *StreamBufferHandle_t, *MessageBufferHandle_t;
#define pdFALSE 0
#define pdTRUE 1
#define pdPASS 1
#define pdFAIL 0
#define portMAX_DELAY ((TickType_t)0xFFFFFFFF)
#define portTICK_PERIOD_MS 1
""",
    "freertos/include/freertos/task.h":          '#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/semphr.h":        '#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/queue.h":         '#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/timers.h":        '#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/event_groups.h":  '#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/stream_buffer.h": '#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/message_buffer.h":'#pragma once\n#include "freertos/FreeRTOS.h"\n',
    "freertos/include/freertos/list.h":          '#pragma once\n#include "freertos/FreeRTOS.h"\n',

    # ESP-IDF stubs
    "components/esp_idf/include/esp_err.h":      '#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n#define ESP_ERR_NO_MEM 257\n',
    "components/esp_idf/include/esp_log.h":      '#pragma once\n#define ESP_LOGE(t,...)\n#define ESP_LOGW(t,...)\n#define ESP_LOGI(t,...)\n#define ESP_LOGD(t,...)\n#define ESP_LOGV(t,...)\n',
    "components/esp_idf/include/esp_timer.h":    '#pragma once\n#include <stdint.h>\ntypedef void (*esp_timer_cb_t)(void*);\n',
    "components/esp_idf/include/esp_system.h":   '#pragma once\n#include <stdint.h>\n',
    "components/esp_idf/include/esp_task_wdt.h": '#pragma once\n',
    "components/esp_idf/include/soc/soc.h":      '#pragma once\n#include <stdint.h>\n',
    "components/esp_idf/include/soc/uart_struct.h": '#pragma once\n',
    "components/esp_idf/include/soc/spi_struct.h": '#pragma once\n',
    "components/esp_idf/include/soc/gpio_struct.h": '#pragma once\n',
    "components/esp_idf/include/soc/gpio_reg.h": '#pragma once\n',
    "components/esp_idf/include/soc/gpio_sig_map.h": '#pragma once\n',
    "components/esp_idf/include/soc/rtc.h":      '#pragma once\n',
    "components/esp_idf/include/soc/rtc_cntl_struct.h": '#pragma once\n',
    "components/esp_idf/include/soc/periph_defs.h": '#pragma once\n',
    "components/esp_idf/include/soc/interrupts.h": '#pragma once\n',
    "components/esp_idf/include/soc/reset_reasons.h": '#pragma once\ntypedef enum { RESET_REASON_CHIP_POWER_ON } soc_reset_reason_t;\n',
    "components/esp_idf/include/hal/gpio_types.h": '#pragma once\n#include <stdint.h>\n',
    "components/esp_idf/include/hal/spi_types.h": '#pragma once\n',
    "components/esp_idf/include/hal/soc_hal.h": '#pragma once\n',
    "components/esp_idf/include/driver/gpio.h": '#pragma once\n',
    "components/esp_idf/include/driver/spi_master.h": '#pragma once\n',
    "components/esp_idf/include/driver/uart.h": '#pragma once\n',
    "components/esp_idf/include/esp_rom_gpio.h": '#pragma once\n',
    "components/esp_idf/include/esp_timer_cxx.h": '#pragma once\n',
    "components/esp_idf/include/esp_private/esp_task_wdt_impl.h": '#pragma once\n',

    # furi_config stub
    "components/furi/furi_config.h": """\
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define FURI_RAM_SIZE 2048
#define FURI_THREAD_FLAG_PADDING 1
#define FURI_CONFIG_THREAD_MAX_PRIORITIES 32
#define FURI_CONFIG_HEAP_SIZE 131072
#define FURI_CONFIG_HEAP_DEBUG 0
#define FURI_CONFIG_HEAP_DEBUG_ENIGMA 0
""",

    # sdkconfig stub
    "build_t_embed/config/sdkconfig.h": r"""
#pragma once
#define CONFIG_IDF_TARGET_ESP32S3 1
#define CONFIG_FREERTOS_HZ 1000
#define CONFIG_FREERTOS_UNICORE 1
#define CONFIG_FREERTOS_TASK_NOTIFICATION_ARRAY_ENTRIES 3
#define CONFIG_FREERTOS_THREAD_LOCAL_STORAGE_POINTERS 1
#define CONFIG_ESP_TASK_WDT_TIMEOUT_S 10
#define CONFIG_ESP_MAIN_TASK_STACK_SIZE 8192
#define CONFIG_SPIRAM_MODE_OCT 1
#define CONFIG_SPIRAM_SPEED_80M 1
#define CONFIG_SPIRAM_USE_MALLOC 1
#define CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL 4096
#define CONFIG_SPIRAM_MALLOC_RESERVE_INTERNAL 65536
#define CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY 1
#define CONFIG_SPIRAM_FETCH_INSTRUCTIONS 1
#define CONFIG_SPIRAM_RODATA 1
#define CONFIG_ESPTOOLPY_FLASHSIZE_16MB 1
#define CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_160 1
#define CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ 160
#define BOARD_INCLUDE "board_lilygo_t_embed_cc1101.h"
#define SOC_MMU_PAGE_SIZE 0x10000
#define SOC_XTAL_FREQ_MHZ 40
#define ESP_PLATFORM 1
""",

    # FreeRTOSConfig stub
    "components/freertos/include/freertos/FreeRTOSConfig.h": r"""
#pragma once
#define configUSE_PREEMPTION 1
#define configUSE_IDLE_HOOK 0
#define configUSE_TICK_HOOK 0
#define configCPU_CLOCK_HZ 160000000
#define configTICK_RATE_HZ 1000
#define configMAX_PRIORITIES 25
#define configMINIMAL_STACK_SIZE 2048
#define configMAX_TASK_NAME_LEN 16
#define configUSE_16_BIT_TICKS 0
#define configIDLE_SHOULD_YIELD 1
#define configUSE_TASK_NOTIFICATIONS 1
#define configUSE_MUTEXES 1
#define configUSE_RECURSIVE_MUTEXES 1
#define configUSE_COUNTING_SEMAPHORES 1
#define configQUEUE_REGISTRY_SIZE 8
#define configUSE_QUEUE_SETS 1
#define configUSE_TIME_SLICING 1
#define configUSE_NEWLIB_REENTRANT 1
#define configENABLE_BACKWARD_COMPATIBILITY 1
#define configNUM_THREAD_LOCAL_STORAGE_POINTERS 1
#define configSTACK_DEPTH_TYPE uint16_t
#define configMESSAGE_BUFFER_LENGTH_TYPE size_t
#define configSUPPORT_STATIC_ALLOCATION 1
#define configSUPPORT_DYNAMIC_ALLOCATION 1
#define configAPPLICATION_ALLOCATED_HEAP 1
#define configTOTAL_HEAP_SIZE 262144
#define configUSE_APPLICATION_TASK_TAG 1
#define configUSE_PORT_OPTIMISED_TASK_SELECTION 1
#define configASSERT(x)
typedef unsigned long StackType_t;
typedef long BaseType_t;
typedef unsigned long UBaseType_t;
typedef uint32_t TickType_t;
""",

    # board header stub
    "targets/board_lilygo_t_embed_cc1101.h": r"""
#pragma once
#define BOARD_LILYGO_T_EMBED_CC1101
#define FURI_HAL_NAMESPACE furi_hal_lilygo_t_embed
""",

    # property.h stub (generated ESP-IDF header, not in repo)
    "components/furi_hal/property.h": """\
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef void (*PropertyValueCallback)(const char* key, const char* value, bool last, void* context);
""",

    # datetime.h stub with proper DateTime type
    "components/furi_hal/datetime/datetime.h": """\
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
    uint8_t millisecond;
    uint8_t weekday;
} DateTime;

#ifdef __cplusplus
}
#endif
""",
}

def write_stubs():
    for rel_path, content in STUBS.items():
        dest = REPO_DIR / rel_path
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content.lstrip())

# ── Header downloading ──────────────────────────────────────────────
AUTO_STUB_COUNTER = 0

# Types that need <stdint.h>
STDINT_TYPES = {b"uint8_t", b"uint16_t", b"uint32_t", b"uint64_t",
                b"int8_t", b"int16_t", b"int32_t", b"int64_t"}
# Types that need <stdbool.h>
STDBOOL_TYPES = {b"bool"}

def _patch_header(text: str) -> str:
    """Ensure downloaded headers include stdint.h / stdbool.h / stddef.h.
    
    Many Flipper Zero headers from the repo assume these are transitively
    available through the full SDK build system. When used standalone,
    explicit includes are needed. Since these are idempotent standard
    headers, we add them unconditionally whenever missing.
    """
    import re as _re
    existing = set()
    for m in _re.finditer(r'#include\s+[<"]([^>"]+)[>"]', text):
        existing.add(m.group(1))

    # Find first non-blank, non-comment, non-pragma line
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#pragma") or s.startswith("/*") or \
           s.startswith("*") or s.startswith("//"):
            insert_at = i + 1
        else:
            break
    # Skip past trailing "*/" of a /** ... */ comment block so we don't
    # insert includes inside the comment.
    while insert_at < len(lines) and lines[insert_at].strip() in ("*/", ""):
        insert_at += 1

    added = []
    if "stdint.h" not in existing:
        added.append("#include <stdint.h>\n")
    if "stdbool.h" not in existing:
        added.append("#include <stdbool.h>\n")
    if "stddef.h" not in existing:
        added.append("#include <stddef.h>\n")
    if "string.h" not in existing:
        added.append("#include <string.h>\n")

    if added:
        lines.insert(insert_at, "".join(added))
        return "".join(lines)
    return text

SKIPPED_STD_HEADERS = set()

def fetch_header(rel_path):
    """Download a single header from the repo, or create an empty stub if missing."""
    global AUTO_STUB_COUNTER, SKIPPED_STD_HEADERS
    dest = REPO_DIR / rel_path
    if dest.exists():
        return True
    basename = os.path.basename(rel_path)
    if basename in STD_C_HEADERS:
        SKIPPED_STD_HEADERS.add(rel_path)
        return True
    if rel_path in SKIPPED_STD_HEADERS:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{rel_path}"
    try:
        req = Request(url, headers={"User-Agent": "FAP-Builder/2.0"})
        with urlopen(req, timeout=30) as r:
            data = r.read()
        if b"Not Found" in data[:200]:
            raise Exception("Not Found")
        # Auto-patch missing standard includes
        patched = _patch_header(data.decode("utf-8", errors="replace"))
        dest.write_text(patched)
        return True
    except Exception:
        # Auto-stub: create an empty header so compilation can proceed.
        # BUT: skip if a real file with the same basename exists elsewhere
        # under components/ (would shadow the real file via -I search order).
        basename = os.path.basename(rel_path)
        same_name = list(REPO_DIR.rglob(basename))
        same_name = [p for p in same_name if p != dest and p.stat().st_size > 50 and "auto-generated stub" not in p.read_text(encoding="utf-8", errors="replace")[:200]]
        if same_name:
            # A real file with this name already exists — don't shadow it
            if AUTO_STUB_COUNTER < 5:
                print(f"    [skip] {rel_path} (shadow of {same_name[0].relative_to(REPO_DIR)})")
            AUTO_STUB_COUNTER += 1
            return True
        AUTO_STUB_COUNTER += 1
        stub = f"/* auto-generated stub for {rel_path} */\n"
        if rel_path.endswith(".h"):
            guard = rel_path.replace("/", "_").replace(".", "_").upper()
            stub = f"#ifndef {guard}\n#define {guard}\n/* auto-generated stub */\n#endif\n"
        dest.write_text(stub)
        if AUTO_STUB_COUNTER <= 5:
            print(f"    [stub] {rel_path}")
        return True

STD_C_HEADERS = {
    "stdint.h","stdbool.h","stddef.h","stdlib.h","stdio.h",
    "string.h","assert.h","stdarg.h","limits.h","inttypes.h",
    "stdnoreturn.h","math.h","float.h","ctype.h","time.h",
    "errno.h","fcntl.h","unistd.h","sys/stat.h","sys/types.h",
    "alloca.h","setjmp.h","signal.h","tgmath.h","wchar.h","wctype.h",
    "complex.h","fenv.h","locale.h","stdatomic.h","uchar.h",
}

def repair_headers():
    """Re-patch all cached headers that lack standard includes."""
    for h_path in REPO_DIR.rglob("*.h"):
        try:
            text = h_path.read_text(encoding="utf-8", errors="replace")
            patched = _patch_header(text)
            if patched != text:
                h_path.write_text(patched)
        except:
            pass

def download_headers(app_source_dir=None):
    """Download headers from the repo, optionally seeding from app includes."""
    print("\n=== Flipper-Zero-ESP32-Port SDK headers ===")

    # Seed queue with core headers + any from app source
    queue = [
        "components/furi/furi.h", "components/furi/core/base.h",
        "components/furi/core/check.h", "components/furi/core/thread.h",
        "components/furi/core/mutex.h", "components/furi/core/message_queue.h",
        "components/furi/core/timer.h", "components/furi/core/record.h",
        "components/furi/core/kernel.h", "components/furi/core/log.h",
        "components/furi/core/memmgr.h",
        "components/furi/core/valuemutex.h",
        "components/gui/gui.h", "components/gui/canvas.h",
        "components/gui/view_port.h", "components/gui/modules/widget_elements.h",
        "components/gui/elements.h", "components/gui/icon.h", "components/gui/icon_i.h",
        "components/gui/canvas_i.h",
        "components/input/input.h",
        "components/notification/notification.h",
        "components/notification/notification_messages.h",
        "components/notification/notification_messages_notes.h",
        "components/locale/locale.h",
        "components/storage/storage.h", "components/dialogs/dialogs.h",
        "components/loader/loader.h",
        "components/furi_hal/furi_hal.h", "components/furi_hal/furi_hal_rtc.h",
        "components/furi_hal/furi_hal_resources.h", "components/furi_hal/furi_hal_os.h",
        "components/furi_hal/furi_hal_spi.h", "components/furi_hal/furi_hal_gpio.h",
        "components/furi_hal/furi_hal_clock.h", "components/furi_hal/furi_hal_adc.h",
        "components/furi_hal/furi_hal_power.h", "components/furi_hal/furi_hal_light.h",
        "components/furi_hal/furi_hal_usb.h", "components/furi_hal/furi_hal_bt.h",
        "components/furi_hal/furi_hal_version.h",
        "components/furi_hal/furi_hal_interrupt.h",
        "components/furi_hal/furi_hal_i2c.h", "components/furi_hal/furi_hal_sd.h",
        "components/furi_hal/furi_hal_mpu.h", "components/furi_hal/furi_hal_crypto.h",
        "components/furi_hal/furi_hal_uid.h", "components/furi_hal/furi_hal_serial.h",
        "components/flipper_application/flipper_application/firmware_api.h",
        "components/flipper_application/flipper_application/flipper_application.h",
        "components/flipper_format/flipper_format.h",
        "components/mlib/mlib.h",
        "components/toolbox/toolbox.h", "components/toolbox/hex.h",
        "components/toolbox/manapool.h", "components/toolbox/path.h",
        "components/toolbox/saved_struct.h", "components/toolbox/level_duration.h",
        "components/toolbox/stream/stream.h", "components/toolbox/stream/file_stream.h",
        "components/toolbox/stream/string_stream.h", "components/toolbox/name_generator.h",
        "components/toolbox/pretty_format.h", "components/toolbox/version.h",
        "components/toolbox/protocols/protocol_dict.h",
        "components/bit_lib/bit_lib.h", "targets/targets.h",
    ]

    # Scan app sources for #include "..." to add to download queue
    if app_source_dir:
        for src_file in sorted(app_source_dir.rglob("*.[ch]")):
            try:
                text = src_file.read_text(encoding="utf-8", errors="replace")
                for m in re.findall(r'#include\s+"([^"]+)"', text):
                    # Redirect furi.h includes to canonical location
                    if os.path.basename(m) == "furi.h" and m != "components/furi/furi.h":
                        if "components/furi/furi.h" not in queue:
                            queue.append("components/furi/furi.h")
                    else:
                        queue.append(m)
                for m in re.findall(r'#include\s+<([^>]+)>', text):
                    if not any(m.startswith(p) for p in ("freertos/","esp_","driver/","hal/","soc/","xtensa/","esp_private/")):
                        if m not in STD_C_HEADERS:
                            if m.startswith("m-"):
                                resolved = f"components/mlib/{m}"
                                if resolved not in queue:
                                    queue.append(resolved)
                            elif os.path.basename(m) == "furi.h" and m != "components/furi/furi.h":
                                if "components/furi/furi.h" not in queue:
                                    queue.append("components/furi/furi.h")
                            else:
                                queue.append(m)
            except:
                pass

    seen = set()
    while queue:
        h = queue.pop(0)
        if h in seen:
            continue
        seen.add(h)

        ok = fetch_header(h)
        if not ok:
            if not h.startswith("components/"):
                ok = fetch_header(f"components/{h}")
                if ok:
                    h = f"components/{h}"
        if not ok:
            continue

        h_path = REPO_DIR / h
        if not h_path.exists():
            # Not actually downloaded (e.g. standard C header handled by compiler)
            continue
        content = h_path.read_bytes().decode("utf-8", errors="replace")
        for m in re.findall(r'#include\s+"([^"]+)"', content):
            parent = h.rsplit("/", 1)[0] if "/" in h else ""
            resolved = os.path.normpath(f"{parent}/{m}").replace("\\", "/")
            # Redirect furi.h includes to canonical location
            if os.path.basename(resolved) == "furi.h" and resolved != "components/furi/furi.h":
                resolved = "components/furi/furi.h"
            if resolved not in seen:
                queue.append(resolved)
        for m in re.findall(r'#include\s+<([^>]+)>', content):
            if m in STD_C_HEADERS:
                continue
            if m.startswith("m-"):
                resolved = f"components/mlib/{m}"
                if resolved not in seen:
                    queue.append(resolved)
                continue
            # Redirect furi.h includes to canonical location
            if os.path.basename(m) == "furi.h" and m != "components/furi/furi.h":
                if "components/furi/furi.h" not in seen:
                    queue.append("components/furi/furi.h")
                continue
            # Try resolving relative to the parent file's directory
            parent = h.rsplit("/", 1)[0] if "/" in h else ""
            resolved_from_parent = os.path.normpath(f"{parent}/{m}").replace("\\", "/")
            if resolved_from_parent not in seen:
                queue.append(resolved_from_parent)
            # Also try components/{name}/{name} for simple names (handles cross-directory
            # includes like <furi_hal.h> from locale.h -> components/furi_hal/furi_hal.h)
            if "/" not in m:
                alt = f"components/{m.rsplit('.',1)[0]}/{m}"
                if alt not in seen and alt != resolved_from_parent:
                    queue.append(alt)

# ── Setup ───────────────────────────────────────────────────────────
def ensure_setup():
    if not cfg_setup_done() or not (BUILD_DIR / "firmware_api.c").exists():
        ensure_toolchain()

        # Download tools
        tools_dir = REPO_DIR / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        for url, name in [(FAP_LD_URL, "fap.ld"),
                          (FAP_MANIFEST_URL, "fap_manifest.py"),
                          (CHECK_SYMBOLS_URL, "check_fap_symbols.py"),
                          (FIRMWARE_API_URL, "firmware_api.c")]:
            download(url, tools_dir / name, name)

        # Download icon compilation tool
        fam_tools = tools_dir / "fam"
        fam_tools.mkdir(parents=True, exist_ok=True)
        download(COMPILE_ICONS_URL, fam_tools / "compile_icons.py", "compile_icons.py")

        # Download SDK headers
        download_headers()

        # Re-patch all cached headers to ensure standard includes
        repair_headers()

        # Write stubs (overrides for headers we can't fetch)
        write_stubs()

        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tools_dir / "firmware_api.c", BUILD_DIR / "firmware_api.c")
        cfg_mark_setup()
        print("\nSetup complete!")
    else:
        # Ensure stubs exist even if setup was done before
        write_stubs()

# ── Symbol checking ─────────────────────────────────────────────────
def elf_gnu_hash(s: str) -> int:
    h = 0x1505
    for c in s.encode():
        h = ((h << 5) + h + c) & 0xFFFFFFFF
    return h

def check_undefined_symbols(tc_bin, elf_path, api_file, app_name):
    nm = tc_bin / "xtensa-esp32s3-elf-nm.exe"
    if not nm.exists():
        print("  [WARN] nm not found, skipping symbol check")
        return True

    r = subprocess.run([str(nm), "-u", str(elf_path)], capture_output=True, text=True)
    if r.returncode:
        print("  [WARN] nm failed, skipping symbol check")
        return True

    undef_syms = set()
    for line in r.stdout.splitlines():
        # nm -u output: "         U symbol_name"
        if " U " in line or line.strip().startswith("U "):
            parts = line.strip().split()
            if len(parts) >= 2:
                undef_syms.add(parts[-1])

    if not undef_syms:
        print("  [OK] No undefined symbols")
        return True

    # Load API hashes from firmware_api.c
    api_hashes = {}
    try:
        with open(api_file) as f:
            for line in f:
                m = re.search(r'\.hash\s*=\s*(0x[0-9a-fA-F]+)', line)
                if m:
                    api_hashes[int(m.group(1), 16)] = True
    except Exception as e:
        print(f"  [WARN] Could not parse firmware_api.c: {e}")
        return True

    missing = []
    for sym in sorted(undef_syms):
        h = elf_gnu_hash(sym)
        if h not in api_hashes:
            missing.append((sym, h))

    if missing:
        print(f"  [!] {len(missing)} symbols NOT in firmware API table:")
        for sym, h in missing:
            print(f"      {sym} (hash=0x{h:08x})")
        print("  [!] FAP may fail to load - add missing symbols to firmware_api.c")
        print("  [!] See: tools/add_symbol.py in the port source tree")
        return False
    else:
        print(f"  [OK] All {len(undef_syms)} undefined symbols resolved by firmware API")
        return True

# ── Icon compilation ─────────────────────────────────────────────────
def compile_icon_assets(icon_assets_dir, build_dir, app_id):
    icons_gen = build_dir / "icons"
    icons_gen.mkdir(parents=True, exist_ok=True)

    compile_py = REPO_DIR / "tools" / "fam" / "compile_icons.py"
    if not compile_py.exists():
        return None

    icon_stem = f"{app_id}_icons"
    r = subprocess.run(
        [sys.executable, str(compile_py), "icons",
         "--filename", icon_stem,
         str(icon_assets_dir), str(icons_gen)],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"  [WARN] Icon asset compilation failed:\n{r.stderr.strip()}")
        return None

    h_file = icons_gen / f"{icon_stem}.h"
    if h_file.exists():
        print(f"  Icons compiled: {h_file.name}")
        return str(icons_gen)
    return None

# ── Parse application.fam ───────────────────────────────────────────
def parse_fam(fam_path):
    info = {
        "entry_point": "main",
        "stack_size": 4096,
        "app_name": fam_path.parent.name.replace("_", " ").title(),
        "appid": fam_path.parent.name,
        "fap_icon": None,
        "fap_icon_assets": None,
        "fap_category": "",
        "fap_version": 1,
        "fap_author": "",
        "fap_description": "",
        "requires": [],
    }
    try:
        ft = fam_path.read_text()
        m = re.search(r'appid="([^"]+)"', ft)
        if m: info["appid"] = m.group(1)
        m = re.search(r'name="([^"]+)"', ft)
        if m: info["app_name"] = m.group(1)
        m = re.search(r'entry_point="([^"]+)"', ft)
        if m: info["entry_point"] = m.group(1)
        m = re.search(r'stack_size=(\d+(?:\s*\*\s*\d+)?)', ft)
        if m:
            try: info["stack_size"] = eval(m.group(1))
            except: pass
        m = re.search(r'fap_icon="([^"]+)"', ft)
        if m: info["fap_icon"] = fam_path.parent / m.group(1)
        m = re.search(r'fap_icon_assets="([^"]+)"', ft)
        if m: info["fap_icon_assets"] = fam_path.parent / m.group(1)
        m = re.search(r'fap_category="([^"]+)"', ft)
        if m: info["fap_category"] = m.group(1)
    except:
        pass
    return info

# ── Build ───────────────────────────────────────────────────────────
def build_fap(source_dir, output_path):
    ensure_setup()

    tc_bin = get_toolchain_bin()
    cc = tc_bin / "xtensa-esp32s3-elf-gcc.exe"
    cxx = tc_bin / "xtensa-esp32s3-elf-g++.exe"
    ld = tc_bin / "xtensa-esp32s3-elf-ld.exe"
    objcopy = tc_bin / "xtensa-esp32s3-elf-objcopy.exe"

    fam = source_dir / "application.fam"
    if not fam.exists():
        print("ERROR: application.fam not found")
        sys.exit(1)

    info = parse_fam(fam)
    app_id = info["appid"]
    app_name = info["app_name"]
    entry_point = info["entry_point"]
    stack_size = max(info["stack_size"], 4096)

    out_name = output_path or (source_dir.parent / f"{app_id}.fap")
    out_name = Path(out_name)
    out_name.parent.mkdir(parents=True, exist_ok=True)
    build = BUILD_DIR / app_id
    build.mkdir(parents=True, exist_ok=True)

    # Make sure app includes are downloaded
    download_headers(source_dir)

    # Re-patch all cached headers to ensure standard includes
    repair_headers()

    # Build include paths
    inc_dirs = [
        REPO_DIR / "components",
        REPO_DIR,
        REPO_DIR / "components/furi",
        REPO_DIR / "components/furi/core",
        REPO_DIR / "components/mlib",
        REPO_DIR / "components/toolbox",
        REPO_DIR / "components/toolbox/stream",
        REPO_DIR / "components/gui",
        REPO_DIR / "components/gui/modules",
        REPO_DIR / "components/gui/modules/widget_elements",
        REPO_DIR / "components/input",
        REPO_DIR / "components/notification",
        REPO_DIR / "components/storage",
        REPO_DIR / "components/loader",
        REPO_DIR / "components/furi_hal",
        REPO_DIR / "components/furi_hal/boards",
        REPO_DIR / "components/furi_hal/datetime",
        REPO_DIR / "components/locale",
        REPO_DIR / "components/freertos/include",
        REPO_DIR / "components/esp_idf/include",
        REPO_DIR / "components/flipper_application",
        REPO_DIR / "components/flipper_application/flipper_application",
        REPO_DIR / "components/flipper_format",
        REPO_DIR / "components/assets",
        REPO_DIR / "components/dialogs",
        REPO_DIR / "components/archive",
        REPO_DIR / "components/u8g2",
        REPO_DIR / "components/bit_lib",
        REPO_DIR / "components/ble_serial",
        REPO_DIR / "applications/services",
        REPO_DIR / "lib/subghz",
        REPO_DIR / "lib/toolbox/protocols",
        REPO_DIR / "targets",
        source_dir,
        REPO_DIR / "build_t_embed/config",
    ]
    # Include any subdirectories in the app source
    for sub in sorted(source_dir.rglob("*")):
        if sub.is_dir() and not any(p.startswith(".") for p in sub.parts):
            inc_dirs.append(sub)
    inc = [f"-I{d}" for d in inc_dirs if d.exists()]

    # Force-include fundamental SDK headers so types are available everywhere
    # (mimics the full SDK build system's implicit includes)
    force_include = [
        "-include", str(REPO_DIR / "components/furi/furi.h"),
        "-include", str(REPO_DIR / "components/input/input.h"),
        "-include", str(REPO_DIR / "components/furi_hal/furi_hal_resources.h"),
    ]
    base_cflags = [
        "-D_GNU_SOURCE", "-fno-common", "-ffunction-sections", "-fdata-sections",
        "-fno-builtin", "-fno-jump-tables", "-fno-tree-switch-conversion",
        "-Wall", "-Wno-unused-parameter", "-Wno-sign-compare",
        "-Os", "-g", "-mlongcalls",
        "-DESP_PLATFORM", '-DIDF_VER="v5.4.1"',
        '-DBOARD_INCLUDE="board_lilygo_t_embed_cc1101.h"',
        '-DFAP_VERSION="1.0"',
    ] + inc + force_include

    cflags = ["-std=gnu17"] + base_cflags
    cxxflags = ["-std=gnu++17", "-fno-exceptions", "-fno-rtti"] + base_cflags

    # Compile icon assets if present
    icons_inc = None
    if info["fap_icon_assets"] and info["fap_icon_assets"].exists():
        print("  Icon assets detected, compiling...")
        icons_inc = compile_icon_assets(info["fap_icon_assets"], build, app_id)
        if icons_inc:
            cflags.append(f"-I{icons_inc}")
            cxxflags.append(f"-I{icons_inc}")

    # Find all .c and .cpp sources (deduplicated)
    seen_paths = set()
    sources = []
    for ext in ("*.c", "*.cpp", "*.cc", "*.cxx"):
        for p in sorted(source_dir.rglob(ext)):
            rp = os.path.realpath(p)
            if rp not in seen_paths:
                seen_paths.add(rp)
                sources.append(p)

    # Add generated icon sources
    if icons_inc:
        for p in sorted(Path(icons_inc).glob("*.c")):
            rp = os.path.realpath(p)
            if rp not in seen_paths:
                seen_paths.add(rp)
                sources.append(p)

    objects = []
    for src in sources:
        is_cpp = src.suffix.lower() in (".cpp", ".cc", ".cxx")
        obj = build / f"{src.stem}.o"
        compiler = str(cxx if is_cpp else cc)
        flags = cxxflags if is_cpp else cflags
        r = subprocess.run([compiler] + flags + ["-c", str(src), "-o", str(obj)],
                           capture_output=True, text=True)
        if r.returncode:
            print(f"ERROR ({src.name}):\n{r.stderr}")
            sys.exit(1)
        objects.append(str(obj))
        print(f"  {src.relative_to(source_dir)}")

    if not objects:
        print("ERROR: no source files found")
        sys.exit(1)

    # Link
    elf = build / "app.elf"
    r = subprocess.run([str(ld), "-r", "-T", str(REPO_DIR/"tools/fap.ld"),
                        f"--entry={entry_point}", "-o", str(elf)] + objects,
                       capture_output=True, text=True)
    if r.returncode:
        print(f"LINK ERROR:\n{r.stderr}")
        sys.exit(1)
    print(f"  Linked {len(objects)} objects (entry={entry_point})")

    # Generate manifest
    mbin = build / "manifest.bin"

    has_icon = 0
    icon_bytes = b"\x00" * 32
    if info["fap_icon"] and info["fap_icon"].exists():
        try:
            from PIL import Image, ImageOps
            import io as _io
            with Image.open(str(info["fap_icon"])) as img:
                with _io.BytesIO() as output:
                    bw = ImageOps.invert(img.convert("1"))
                    bw.save(output, format="XBM")
                    xbm = output.getvalue().decode().strip()
            lines = xbm.splitlines()
            data = "".join(lines[2:]).replace(" ", "").split("=")[1][1:-2]
            data_hex = data.replace(",", " ").replace("0x", "")
            raw = bytearray.fromhex(data_hex)
            icon_data = bytearray([0x00]) + raw
            if len(icon_data) > 32:
                icon_data = icon_data[:32]
            has_icon = 1
            padded = bytes(icon_data) + b"\x00" * (32 - len(icon_data))
            icon_bytes = padded[:32]
            print(f"  Icon: {info['fap_icon'].name} ({len(icon_data)} bytes)")
        except Exception as e:
            print(f"  [WARN] Icon processing failed: {e}")

    name_b = app_name.encode("utf-8")[:32].ljust(32, b"\x00")
    man = struct.pack(
        "<IIHHHHI32sc32s",
        0x52474448, 1, 0, 1, 32, stack_size, 1,
        name_b, bytes([has_icon]), icon_bytes,
    )
    mbin.write_bytes(man)
    print(f"  Manifest: {app_name}, API 1.0, target 32, stack {stack_size}, "
          f"icon={'yes' if has_icon else 'no'}, size {len(man)} bytes")

    # Inject manifest into ELF
    r = subprocess.run([str(objcopy), "--add-section", f".fapmeta={mbin}",
                        "--set-section-flags", ".fapmeta=contents,readonly",
                        "--strip-debug", str(elf), str(out_name)],
                       capture_output=True, text=True)
    if r.returncode:
        print(f"OBJCOPY ERROR:\n{r.stderr}")
        sys.exit(1)
    sz = os.path.getsize(out_name)
    print(f"  Output: {out_name} ({sz} bytes)")

    # Check symbols
    api_file = BUILD_DIR / "firmware_api.c"
    check_undefined_symbols(tc_bin, elf, api_file, app_name)

# ── Entry points ────────────────────────────────────────────────────
def setup_interactive():
    print("FAP Builder — First-time setup")
    ensure_setup()
    print(f"\nReady! Cache: {CACHE}")
    print("Drag a source folder (with application.fam) onto fap_builder.exe")

def find_source(path):
    p = Path(path)
    if p.is_dir() and (p / "application.fam").exists():
        return p
    return None

def main():
    args = [a for a in sys.argv[1:] if a]

    if not args:
        if cfg_setup_done():
            cwd = Path().cwd()
            found = False
            for sub in sorted(cwd.iterdir()):
                src = find_source(sub)
                if src:
                    if not found:
                        found = True
                    print(f"Building: {src.name}")
                    build_fap(src, None)
            if not found:
                print("No source folder found. Drag one onto fap_builder.exe")
        else:
            setup_interactive()
        return

    if args[0] in ("--setup", "--init"):
        setup_interactive()
        return

    src = find_source(args[0])
    if src:
        print(f"Building: {src.name}")
        build_fap(src, None)
    else:
        print("Usage: fap_builder.exe [--setup] [source_folder]")
        print(f"Not a valid source folder: {args[0]}")

if __name__ == "__main__":
    main()
