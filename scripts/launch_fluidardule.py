#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# =========================================================
# Final (260419o)
# - Stable RAW/SEQ/UNO-2 MIDI input modes
# - ALSA SEQ auto-connect and quiet already-subscribed handling
# - UNO-2 bridge integrated (uno_midi_bridge)
# - Player -> engine recovery
# - Power menu via SEL_LP
# - Faster TFT-LCD partial redraw
# - Scroll-aware common list rendering rule
# - Main/submenu/file browser optimized
# - 180-degree rotation handled
# =========================================================

import os
import time
import queue
import signal
import threading
import subprocess
import re
import json
from pathlib import Path
from dataclasses import dataclass, field

import serial

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
except Exception as exc:
    raise SystemExit(f"Pillow import failed: {exc}")



# =========================================================
# User config
# =========================================================

SCRIPT_VERSION = "v2.9-stage8-260424a"

SERIAL_PORT = "/dev/serial/by-id/usb-Arduino__www.arduino.cc__Arduino_Uno_12724551266415469650-if00"
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 0.1
SERIAL_INPUT_IGNORE_AFTER_OPEN_SEC = 1.5

SOUNDFONTS = [
    ("/home/pi/sf2/SalC5Light2.sf2", "SalC5"),
    ("/home/pi/sf2/FluidR3_GM.sf2", "FluidR3"),
    ("/home/pi/sf2/GeneralUser_GS.sf2", "GUserGS"),
]

DEFAULT_DAC = ("default", "I2S default")
KNOWN_USB_DACS = [
    ("O22", "Onyx O22"),
    ("SCD70", "Roland SC-D70"),
    ("CODEC", "USB Audio CODEC"),
]

FLUID_GAIN = "0.4"

# Raw MIDI input selection
# 1) If RAW_MIDI_DEVICE is set, it is used directly.
# 2) Otherwise, if FIXED_MIDI_SRC is set, the first amidi -l entry whose name contains it is used.
# 3) Otherwise, preferred-name hints are tried, then the first usable raw MIDI input is used.
RAW_MIDI_DEVICE = None               # e.g. "hw:1,0,0"
RAW_MIDI_PREFERRED_HINTS = [
    "MPK Mini",
    "AKAI",
    "Keyboard",
]
BRIDGE_EXECUTABLE = "/home/pi/bin/uno_midi_bridge_sp"
BRIDGE_PORT_HINT = "UNO-bridge"
BRIDGE_AUTOSTART = False
FIXED_MIDI_SRC = None
LOG_DIR = "/home/pi/log/fluidardule"
FLUID_LOG_PATH = f"{LOG_DIR}/fluidsynth.log"
PLAYER_LOG_PATH = f"{LOG_DIR}/player.log"
AMIXER_CONTROL = "PCM"
FIX_VOLUME_AT_100 = True
POT_VOLUME_ENABLED = True
DEVICE_POLL_INTERVAL_SEC = 3.0
MIDI_RECONNECT_STABLE_SEC = 1.5
SERIAL_HEARTBEAT_INTERVAL_SEC = 1.0
SERIAL_LINK_STALE_SEC = 3.0
LED_PULSE_COOLDOWN_SEC = 0.05
POT_LED_PULSE_INTERVAL_SEC = 0.07
POT_LED_PERCENT_THRESHOLD = 3
SYSTEM_STATUS_POLL_INTERVAL_SEC = 10.0
BRIDGE_WATCHDOG_INTERVAL_SEC = 2.0
SERIAL_MAX_CONSEC_WRITE_ERRORS = 3
SERIAL_MAX_CONSEC_READ_ERRORS = 5
SERIAL_REOPEN_COOLDOWN_SEC = 3.0
MIDI_ACTIVITY_MONITOR_ENABLED = True
MIDI_ACTIVITY_MONITOR_POLL_SEC = 1.0


FRAMEBUFFER_DEVICE = "/dev/fb1"
FRAMEBUFFER_SYS_DIR = "/sys/class/graphics/fb1"
FALLBACK_WIDTH = 480
FALLBACK_HEIGHT = 320
BACKGROUND = (10, 12, 18)
FG = (240, 240, 240)
DIM = (160, 170, 180)
ACCENT = (100, 190, 255)
SELECT_BG = (45, 70, 110)
BOX_BG = (20, 24, 32)
STATUS_GOOD = (90, 220, 120)
STATUS_BAD = (255, 110, 110)
# Minimum interval between TFT renders (in seconds).
# Frequent screen updates can interfere with real-time audio on Raspberry Pi,
# causing jitter or glitches during MIDI playback.
# Increasing this value improves audio stability at the cost of UI responsiveness.
RENDER_MIN_INTERVAL = 0.15
ROTATE_180 = True

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]

MAIN_MENU = [
    "SoundFont",
    "DAC",
    "MIDI Mode",
    "File Player",
    "Extension",
]

FILE_ROOT_CANDIDATES = [
    "/home/pi/media",
    "/home/pi/midi",
    "/home/pi/Music",
    "/home/pi",
]

EXT_TAG = {
    ".mid": "[MID]",
    ".midi": "[MID]",
    ".wav": "[WAV]",
    ".mp3": "[MP3]",
    ".ogg": "[OGG]",
    ".wma": "[WMA]",
}

PLAYABLE_EXTS = tuple(EXT_TAG.keys())
AUDIO_FILE_EXTS = (".wav", ".mp3", ".ogg", ".wma")

FILE_MEDIA_ROOT = "/home/pi/media"
USB_MOUNT_POINT = f"{FILE_MEDIA_ROOT}/usb"
USB_STATUS_POLL_INTERVAL_SEC = 1.0
USB_EJECT_CMD = ["sudo", "-n", "/bin/umount", USB_MOUNT_POINT]
USB_LABEL = "USB"

POWER_MENU_ITEMS = ["Cancel", "Halt", "Reboot"]
POWER_CONFIRM_ITEMS = ["No", "Yes"]



# =========================================================
# Runtime state
# =========================================================

@dataclass
class RuntimeState:
    running: bool = True

    sf_index: int = 0
    sf_name: str = ""
    current_preset_bank: int = 0
    current_preset_program: int = 0
    current_preset_name: str = "Piano"

    dac_index: int = 0
    dac_name: str = DEFAULT_DAC[1]
    audio_device: str = DEFAULT_DAC[0]
    dac_options: list[tuple[str, str]] = field(default_factory=lambda: [DEFAULT_DAC])
    dac_preview_index: int = 0

    midi_mode: str = "usb_direct_raw"
    midi_mode_options: list[tuple[str, str]] = field(default_factory=lambda: [
        ("usb_direct_raw", "USB direct RAW"),
        ("uno2_bridge_seq", "UNO-2 bridge (SEQ)"),
        ("alsa_midi", "ALSA MIDI (SEQ)"),
    ])
    bridge_proc: subprocess.Popen | None = None
    bridge_running: bool = False
    bridge_port_name: str = BRIDGE_PORT_HINT
    midi_display_text: str = "RAW"
    selected_alsa_input: str | None = None
    selected_alsa_input_name: str | None = None
    preferred_seq_port: str | None = None
    preferred_seq_name: str | None = None

    midi_selected_name: str | None = None
    midi_options: list[tuple[str, str]] = field(default_factory=list)
    midi_src_name: str = "none"
    midi_src_port: str = "-"
    fluid_dst_port: str = "-"
    midi_connected: bool = False
    midi_pending_signature: str = ""
    midi_candidate_seen_since: float = 0.0

    fluid_pid: int | None = None
    last_event: str = "-"
    last_device_poll_time: float = 0.0
    last_render_time: float = 0.0
    dirty: bool = True

    ui_mode: str = "main"      # main / submenu / file_source / file_browser / player
    menu_index: int = 0
    submenu_index: int = 0
    submenu_key: str | None = None
    preset_entries: list[dict] = field(default_factory=list)
    preset_index: int = 0
    preset_sf_index: int | None = None
    preset_source_name: str = ""
    preview_active: bool = False
    preview_restore_sf_index: int | None = None
    preview_restore_preset_bank: int = 0
    preview_restore_preset_program: int = 0
    preview_restore_preset_name: str = ""

    browser_root: str = FILE_MEDIA_ROOT
    browser_path: str = FILE_MEDIA_ROOT
    browser_entries: list[dict] = field(default_factory=list)
    browser_index: int = 0

    player_proc_kind: str | None = None   # engine / media
    player_path: str | None = None
    player_paused: bool = False
    player_status: str = "Stopped"

    prev_ui_mode: str = "main"
    submenu_return_mode: str | None = None
    power_menu_index: int = 0
    power_confirm_action: str | None = None
    power_confirm_index: int = 0

    volume_percent: int = 100
    last_pot_raw: int = -1
    last_led_pulse_time: float = 0.0
    last_pot_led_pulse_time: float = 0.0
    last_pot_led_percent: int = -1

    cpu_load_text: str = "L:-"
    cpu_temp_text: str = "T:-"
    last_system_status_poll_time: float = 0.0
    last_bridge_poll_time: float = 0.0

    usb_mounted: bool = False
    last_usb_poll_time: float = 0.0
    last_usb_autoenter_time: float = 0.0
    usb_mount_path: str = USB_MOUNT_POINT
    usb_eject_confirm: bool = False

    player_stop_requested: bool = False
    player_auto_next: bool = True
    player_origin_dir: str | None = None

    pending_resume_after_sf_apply: bool = False

    # Ignore short burst of stale/noisy UI events after UNO-1 serial reconnect/reset.
    serial_input_ignore_until: float = 0.0


state = RuntimeState(sf_index=0, sf_name=SOUNDFONTS[0][1])
event_q: queue.Queue[str] = queue.Queue()
fluid_proc = None
fluid_log_handle = None
player_proc = None
player_log_handle = None
serial_handle = None
last_enc_time = 0.0
serial_lock = threading.Lock()
last_serial_hb_time = 0.0
serial_write_error_count = 0
serial_read_error_count = 0
midi_activity_proc = None
midi_activity_signature = ""
midi_activity_thread_handle = None



# =========================================================
# Common utils
# =========================================================

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def mark_dirty(event: str | None = None) -> None:
    if event is not None:
        state.last_event = event
    state.dirty = True


def clamp_index(index: int, length: int) -> int:
    if length <= 0:
        return 0
    if index < 0:
        return 0
    if index >= length:
        return length - 1
    return index


def run_cmd(cmd: list[str] | str) -> tuple[int, str]:
    try:
        if isinstance(cmd, str):
            p = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        else:
            p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return p.returncode, p.stdout.strip()
    except Exception as exc:
        return 1, str(exc)

def get_cpu_load_text() -> str:
    try:
        load1 = os.getloadavg()[0]
        return f"L:{load1:.2f}"
    except Exception:
        return "L:-"


def get_cpu_temp_text() -> str:
    degree = "\u00B0"
    try:
        code, out = run_cmd(["vcgencmd", "measure_temp"])
        if code == 0 and "temp=" in out:
            value = out.split("temp=", 1)[1].split("'", 1)[0].strip()
            return f"T:{value}{degree}C"
    except Exception:
        pass
    try:
        raw = Path('/sys/class/thermal/thermal_zone0/temp').read_text().strip()
        return f"T:{int(raw)/1000:.1f}{degree}C"
    except Exception:
        return "T:-"


def periodic_system_status_poll() -> None:
    now = time.time()
    if now - state.last_system_status_poll_time < SYSTEM_STATUS_POLL_INTERVAL_SEC:
        return
    state.last_system_status_poll_time = now
    new_load = get_cpu_load_text()
    new_temp = get_cpu_temp_text()
    if new_load != state.cpu_load_text or new_temp != state.cpu_temp_text:
        state.cpu_load_text = new_load
        state.cpu_temp_text = new_temp
        state.dirty = True


def force_volume_100() -> None:
    try:
        subprocess.run(["amixer", "sset", AMIXER_CONTROL, "100%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        state.volume_percent = 100
    except Exception:
        pass


def set_output_volume(percent: int, *, announce: bool = False) -> None:
    percent = max(0, min(100, int(percent)))
    try:
        subprocess.run(["amixer", "sset", AMIXER_CONTROL, f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if percent != state.volume_percent:
            state.volume_percent = percent
            if announce:
                mark_dirty(f"Volume {percent}%")
    except Exception as exc:
        if announce:
            mark_dirty(f"Volume set failed: {exc}")


def handle_pot_value(raw_value: str) -> None:
    if not POT_VOLUME_ENABLED:
        return
    try:
        raw = int(raw_value)
    except ValueError:
        return
    raw = max(0, min(1023, raw))
    state.last_pot_raw = raw
    percent = int(round(raw * 100 / 1023))
    if abs(percent - state.volume_percent) < POT_LED_PERCENT_THRESHOLD:
        return
    set_output_volume(percent, announce=True)
    maybe_pulse_pot_led(percent)

def normalize_path(path: str) -> str:
    return os.path.abspath(path)


def resolve_file_root() -> str:
    root = os.path.abspath(FILE_MEDIA_ROOT)
    os.makedirs(root, exist_ok=True)
    return root


def is_under_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except Exception:
        return False


def find_file_root() -> str:
    for p in FILE_ROOT_CANDIDATES:
        if Path(p).exists():
            return p
    return "/home/pi"


def shorten_text(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[:limit - 3] + "..."


def is_mountpoint_active(path: str) -> bool:
    return os.path.ismount(path)


def usb_status_text() -> str:
    return f"{USB_LABEL}:ON" if state.usb_mounted else f"{USB_LABEL}:---"


def get_file_source_entries() -> list[dict]:
    entries = [{"type": "source", "name": "local", "display": "Local files"}]
    if state.usb_mounted:
        entries.append({"type": "source", "name": "usb", "display": "USB drive"})
    return entries


def enter_file_source(default_usb: bool = False) -> None:
    entries = get_file_source_entries()
    state.ui_mode = "file_source"
    state.browser_index = 1 if (default_usb and len(entries) > 1) else 0
    invalidate_full_display()
    mark_dirty("File source")


def file_source_select() -> None:
    entries = get_file_source_entries()
    if not entries:
        mark_dirty("No source")
        return
    item = entries[clamp_index(state.browser_index, len(entries))]
    state.browser_path = USB_MOUNT_POINT if item["name"] == "usb" else resolve_file_root()
    refresh_browser_entries()
    state.browser_index = 0
    state.ui_mode = "file_browser"
    invalidate_full_display()
    mark_dirty(item["display"])


# =========================================================
# Raw MIDI discovery
# =========================================================

_RAW_AMIDI_RE = re.compile(r'^(?P<dir>[IO]{1,2})\s+(?P<port>hw:\d+,\d+,\d+)\s+(?P<name>.+?)\s*$')


def list_raw_midi_inputs() -> list[tuple[str, str]]:
    code, out = run_cmd(["amidi", "-l"])
    if code != 0 or not out:
        return []

    entries: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("dir"):
            continue
        m = _RAW_AMIDI_RE.match(line)
        if not m:
            continue
        direction = m.group("dir")
        port = m.group("port")
        name = m.group("name").strip()
        if "I" not in direction:
            continue
        entries.append((port, name))
    return entries


def choose_raw_midi_input() -> tuple[str | None, str | None]:
    entries = list_raw_midi_inputs()
    if not entries:
        return None, None

    if RAW_MIDI_DEVICE:
        for port, name in entries:
            if port == RAW_MIDI_DEVICE:
                return port, name
        return RAW_MIDI_DEVICE, RAW_MIDI_DEVICE

    preferred_terms: list[str] = []
    if FIXED_MIDI_SRC:
        preferred_terms.append(FIXED_MIDI_SRC)
    preferred_terms.extend(RAW_MIDI_PREFERRED_HINTS)

    for term in preferred_terms:
        term_lower = term.lower()
        for port, name in entries:
            if term_lower in name.lower() or term_lower in port.lower():
                return port, name

    return entries[0]


# =========================================================
# Serial tx helpers
# =========================================================


def send_serial_line(line: str) -> bool:
    global serial_handle, serial_write_error_count
    data = (line.rstrip("\n") + "\n").encode("ascii", errors="ignore")
    with serial_lock:
        if serial_handle is None:
            return False
        try:
            serial_handle.write(data)
            serial_handle.flush()
            serial_write_error_count = 0
            return True
        except Exception as exc:
            serial_write_error_count += 1
            log(f"serial write failed ({serial_write_error_count}/{SERIAL_MAX_CONSEC_WRITE_ERRORS}): {exc}")
            if serial_write_error_count >= SERIAL_MAX_CONSEC_WRITE_ERRORS:
                log("serial write error threshold reached; forcing reconnect")
                try:
                    serial_handle.close()
                except Exception:
                    pass
                serial_handle = None
                serial_write_error_count = 0
            return False


def periodic_serial_heartbeat() -> None:
    global last_serial_hb_time
    now = time.time()
    if now - last_serial_hb_time < SERIAL_HEARTBEAT_INTERVAL_SEC:
        return
    if send_serial_line("HB"):
        last_serial_hb_time = now


def pulse_midi_led() -> None:
    send_serial_line("ACT:MIDI")


def maybe_pulse_led(min_interval_sec: float = LED_PULSE_COOLDOWN_SEC, *, force: bool = False) -> None:
    now = time.time()
    if (not force) and (now - state.last_led_pulse_time) < min_interval_sec:
        return
    state.last_led_pulse_time = now
    pulse_midi_led()


def maybe_pulse_pot_led(current_percent: int) -> None:
    now = time.time()
    if state.last_pot_led_percent < 0:
        state.last_pot_led_percent = current_percent
        return
    if abs(current_percent - state.last_pot_led_percent) < POT_LED_PERCENT_THRESHOLD:
        return
    if (now - state.last_pot_led_pulse_time) < POT_LED_PULSE_INTERVAL_SEC:
        return
    state.last_pot_led_pulse_time = now
    state.last_pot_led_percent = current_percent


def set_play_led(mode: str) -> None:
    mode = mode.strip().upper()
    if mode not in {"OFF", "ON", "BLINK"}:
        return
    send_serial_line(f"PLAY:{mode}")


def pulse_button_activity() -> None:
    # MIDI LED is reserved for actual incoming MIDI note activity.
    return



# =========================================================
# MIDI activity monitor (actual incoming note events)
# =========================================================

def get_midi_activity_monitor_spec() -> tuple[list[str] | None, str]:
    if not MIDI_ACTIVITY_MONITOR_ENABLED:
        return None, ""
    # Keep MIDI activity LED only for SEQ-style sources.
    if state.midi_mode in {"alsa_midi", "uno2_bridge_seq"}:
        port = state.midi_src_port
        if port and port not in {"-", "", "seq"}:
            return ["aseqdump", "-p", port], f"seq:{port}"
        return None, ""
    return None, ""


def stop_midi_activity_monitor() -> None:
    global midi_activity_proc, midi_activity_signature
    proc = midi_activity_proc
    midi_activity_proc = None
    midi_activity_signature = ""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.2)
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass


def start_midi_activity_monitor_if_needed() -> None:
    global midi_activity_proc, midi_activity_signature
    cmd, signature = get_midi_activity_monitor_spec()

    if not cmd:
        if midi_activity_proc is not None:
            stop_midi_activity_monitor()
        return

    if midi_activity_proc is not None and midi_activity_signature == signature and midi_activity_proc.poll() is None:
        return

    stop_midi_activity_monitor()
    try:
        midi_activity_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
        )
        midi_activity_signature = signature
    except Exception as exc:
        midi_activity_proc = None
        midi_activity_signature = ""


def midi_activity_line_has_note_on(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False

    low = s.lower()
    # aseqdump output
    if "note on" in low:
        if "velocity 0" in low:
            return False
        return True

    # amidi -d style hexadecimal byte dump
    tokens = re.findall(r'\b[0-9A-Fa-f]{2}\b', s)
    if len(tokens) < 3:
        return False
    try:
        data = [int(tok, 16) for tok in tokens]
    except Exception:
        return False

    i = 0
    running_status = None
    while i < len(data):
        b = data[i]
        if b & 0x80:
            running_status = b
            i += 1
            if 0x80 <= b <= 0xEF:
                status_nibble = b & 0xF0
                needed = 1 if status_nibble in (0xC0, 0xD0) else 2
                if i + needed - 1 >= len(data):
                    break
                d1 = data[i]
                d2 = data[i + 1] if needed > 1 else 0
                if status_nibble == 0x90 and d2 > 0:
                    return True
                i += needed
            else:
                continue
        else:
            if running_status is None:
                i += 1
                continue
            status_nibble = running_status & 0xF0
            needed = 1 if status_nibble in (0xC0, 0xD0) else 2
            if i + needed - 1 >= len(data):
                break
            d1 = data[i]
            d2 = data[i + 1] if needed > 1 else 0
            if status_nibble == 0x90 and d2 > 0:
                return True
            i += needed

    return False


def midi_activity_monitor_thread() -> None:
    global midi_activity_proc, midi_activity_signature
    while state.running:
        try:
            start_midi_activity_monitor_if_needed()
            proc = midi_activity_proc
            if proc is None or proc.stdout is None:
                time.sleep(MIDI_ACTIVITY_MONITOR_POLL_SEC)
                continue

            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    midi_activity_proc = None
                    midi_activity_signature = ""
                time.sleep(0.05)
                continue

            if midi_activity_line_has_note_on(line):
                maybe_pulse_led()

        except Exception as exc:
            stop_midi_activity_monitor()
            time.sleep(MIDI_ACTIVITY_MONITOR_POLL_SEC)

# =========================================================
# TFT display
# =========================================================

class TFTDisplay:
    def __init__(self, fb_path: str, sys_dir: str):
        self.fb_path = fb_path
        self.sys_dir = Path(sys_dir)
        self.width, self.height = self._detect_size()
        self.bpp = self._detect_bpp()
        self.font_small = self._load_font(18)
        self.font_body = self._load_font(24)
        self.font_value = self._load_font(24)
        self.font_title = self._load_font(30)
        self.font_menu = self._load_font(26)
        self.prev_image = None
        self.prev_snapshot = None

    def _detect_size(self) -> tuple[int, int]:
        try:
            text = (self.sys_dir / "virtual_size").read_text().strip()
            w, h = text.split(",")
            return int(w), int(h)
        except Exception:
            return FALLBACK_WIDTH, FALLBACK_HEIGHT

    def _detect_bpp(self) -> int:
        try:
            return int((self.sys_dir / "bits_per_pixel").read_text().strip())
        except Exception:
            return 16

    def _load_font(self, size: int):
        for path in FONT_CANDIDATES:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _encode_region(self, rgb: Image.Image) -> bytes:
        pixels = rgb.load()
        width, height = rgb.size
        if self.bpp == 16:
            buf = bytearray(width * height * 2)
            off = 0
            for y in range(height):
                for x in range(width):
                    r, g, b = pixels[x, y]
                    value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                    buf[off] = value & 0xFF
                    buf[off + 1] = (value >> 8) & 0xFF
                    off += 2
            return bytes(buf)
        return rgb.convert("RGBA").tobytes()

    def _write_full_image(self, img: Image.Image) -> None:
        out = img.rotate(180) if ROTATE_180 else img
        rgb = out.convert("RGB") if self.bpp == 16 else out.convert("RGBA")
        with open(self.fb_path, "wb", buffering=0) as fb:
            fb.write(self._encode_region(rgb if self.bpp == 16 else out))

    def _write_partial_image(self, img: Image.Image, bbox: tuple[int, int, int, int]) -> None:
        if not bbox:
            return
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            return

        region = img.crop((x1, y1, x2, y2))
        if ROTATE_180:
            region = region.rotate(180)
            x1, y1, x2, y2 = self.width - x2, self.height - y2, self.width - x1, self.height - y1

        rgb = region.convert("RGB") if self.bpp == 16 else region.convert("RGBA")
        bytes_per_pixel = 2 if self.bpp == 16 else 4
        row_stride = self.width * bytes_per_pixel
        region_stride = (x2 - x1) * bytes_per_pixel
        data = self._encode_region(rgb if self.bpp == 16 else region)
        with open(self.fb_path, "r+b", buffering=0) as fb:
            for row in range(y2 - y1):
                start = row * region_stride
                end = start + region_stride
                fb.seek((y1 + row) * row_stride + x1 * bytes_per_pixel)
                fb.write(data[start:end])

    def _write_image(self, image: Image.Image) -> None:
        img = image.resize((self.width, self.height))

        if self.prev_image is None or self.prev_image.size != img.size or self.bpp not in (16, 32):
            self._write_full_image(img)
            self.prev_image = img.copy()
            return

        diff = ImageChops.difference(img, self.prev_image)
        bbox = diff.getbbox()
        if bbox is None:
            return

        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - 2)
        y1 = max(0, y1 - 2)
        x2 = min(self.width, x2 + 2)
        y2 = min(self.height, y2 + 2)
        self._write_partial_image(img, (x1, y1, x2, y2))
        self.prev_image = img.copy()

    def _snapshot_state(self) -> dict:
        browser_displays = tuple(entry.get("display", "") for entry in state.browser_entries)
        return {
            "ui_mode": state.ui_mode,
            "menu_index": state.menu_index,
            "submenu_index": state.submenu_index,
            "submenu_key": state.submenu_key,
            "browser_index": state.browser_index,
            "browser_path": state.browser_path,
            "browser_entries_display": browser_displays,
            "last_event": state.last_event,
            "cpu_load_text": state.cpu_load_text,
            "cpu_temp_text": state.cpu_temp_text,
            "midi_display_text": state.midi_display_text,
            "midi_connected": state.midi_connected,
            "usb_mounted": state.usb_mounted,
            "main_value_0": self._main_menu_value(0),
            "main_value_1": self._main_menu_value(1),
            "main_value_2": self._main_menu_value(2),
            "main_value_3": self._main_menu_value(3),
            "main_value_4": self._main_menu_value(4),
        }

    def _footer_changed(self, prev: dict | None) -> bool:
        if prev is None:
            return True
        keys = ("last_event", "cpu_load_text", "cpu_temp_text", "midi_display_text", "midi_connected", "usb_mounted")
        return any(prev.get(k) != getattr(state, k) for k in keys)

    def _main_values_changed(self, prev: dict | None) -> bool:
        if prev is None:
            return True
        current = [self._main_menu_value(i) for i in range(len(MAIN_MENU))]
        previous = [prev.get(f"main_value_{i}") for i in range(len(MAIN_MENU))]
        return current != previous


    def _list_window_state(self, index: int, items_len: int, top_y: int, row_h: int, bottom_y: int):
        max_rows = max(1, (bottom_y - top_y) // row_h)
        if items_len <= 0:
            return 0, max_rows, 0
        start_idx = max(0, index - max_rows + 1) if index >= max_rows else 0
        if index < start_idx or index >= min(items_len, start_idx + max_rows):
            visible_row = None
        else:
            visible_row = index - start_idx
        return start_idx, max_rows, visible_row

    def _render_list_incremental_common(
        self,
        *,
        prev_snapshot: dict,
        prev_index: int | None,
        curr_index: int,
        items_len: int,
        top_y: int,
        row_h: int,
        bottom_y: int,
        list_bbox: tuple[int, int, int, int],
        row_bbox_func,
        redraw_current_view,
    ) -> bool:
        if self.prev_image is None:
            return False

        footer_changed = self._footer_changed(prev_snapshot)
        if prev_index == curr_index and not footer_changed:
            return False

        prev_start, _prev_max_rows, prev_vis = self._list_window_state(
            prev_index if prev_index is not None else 0, items_len, top_y, row_h, bottom_y
        )
        curr_start, _curr_max_rows, curr_vis = self._list_window_state(
            curr_index, items_len, top_y, row_h, bottom_y
        )

        if curr_vis is None:
            return False
        if prev_index is not None and prev_vis is None:
            return False

        image = self.prev_image.copy()
        draw = ImageDraw.Draw(image)
        redraw_current_view(draw)

        boxes = []
        if prev_index is None or prev_start != curr_start:
            boxes.append(list_bbox)
        else:
            rows = {v for v in (prev_vis, curr_vis) if v is not None}
            for vis in rows:
                boxes.append(row_bbox_func(vis))

        if footer_changed:
            self._draw_footer(draw)
            boxes.append((0, self.height - 40, self.width, self.height))

        for bbox in boxes:
            self._write_partial_image(image, bbox)

        self.prev_image = image.copy()
        self.prev_snapshot = self._snapshot_state()
        return True

    def _render_main_incremental(self, prev_snapshot: dict) -> bool:
        prev_index = prev_snapshot.get("menu_index")
        if self.prev_image is None:
            return False

        # If any right-side value changed (for example RAW device name recovery),
        # redraw the whole main list area rather than only the selected row.
        if self._main_values_changed(prev_snapshot):
            image = self.prev_image.copy()
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((12, 52, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
            self._draw_main(draw)
            self._draw_footer(draw)
            self._write_partial_image(image, (12, 52, self.width - 12, self.height - 48))
            self._write_partial_image(image, (0, self.height - 40, self.width, self.height))
            self.prev_image = image.copy()
            self.prev_snapshot = self._snapshot_state()
            return True

        return self._render_list_incremental_common(
            prev_snapshot=prev_snapshot,
            prev_index=prev_index,
            curr_index=state.menu_index,
            items_len=len(MAIN_MENU),
            top_y=56,
            row_h=42,
            bottom_y=self.height - 48,
            list_bbox=(12, 52, self.width - 12, self.height - 48),
            row_bbox_func=lambda vis: (20, 56 + vis * 42, self.width - 20, 56 + vis * 42 + 42),
            redraw_current_view=lambda draw: (
                draw.rounded_rectangle((12, 52, self.width - 12, self.height - 48), radius=12, fill=BOX_BG),
                self._draw_main(draw)
            ),
        )

    def _render_submenu_incremental(self, prev_snapshot: dict) -> bool:
        if self.prev_image is None or prev_snapshot.get("submenu_key") != state.submenu_key:
            return False
        options = get_submenu_options()
        prev_index = prev_snapshot.get("submenu_index")
        return self._render_list_incremental_common(
            prev_snapshot=prev_snapshot,
            prev_index=prev_index,
            curr_index=state.submenu_index,
            items_len=len(options),
            top_y=104,
            row_h=38,
            bottom_y=self.height - 50,
            list_bbox=(12, 98, self.width - 12, self.height - 48),
            row_bbox_func=lambda vis: (20, 104 + vis * 38, self.width - 20, 104 + vis * 38 + 38),
            redraw_current_view=lambda draw: (
                draw.rounded_rectangle((12, 98, self.width - 12, self.height - 48), radius=12, fill=BOX_BG),
                self._draw_submenu(draw)
            ),
        )

    def _render_file_browser_incremental(self, prev_snapshot: dict) -> bool:
        if self.prev_image is None:
            return False
        if prev_snapshot.get("browser_path") != state.browser_path:
            return False
        if prev_snapshot.get("browser_entries_display") != tuple(entry.get("display", "") for entry in state.browser_entries):
            return False

        prev_index = prev_snapshot.get("browser_index")
        entries_len = len(state.browser_entries) if state.browser_entries else 1
        return self._render_list_incremental_common(
            prev_snapshot=prev_snapshot,
            prev_index=prev_index,
            curr_index=state.browser_index,
            items_len=entries_len,
            top_y=118,
            row_h=36,
            bottom_y=self.height - 50,
            list_bbox=(12, 112, self.width - 12, self.height - 48),
            row_bbox_func=lambda vis: (20, 118 + vis * 36, self.width - 20, 118 + vis * 36 + 36),
            redraw_current_view=lambda draw: (
                draw.rounded_rectangle((12, 112, self.width - 12, self.height - 48), radius=12, fill=BOX_BG),
                self._draw_file_browser(draw)
            ),
        )

    def render(self) -> None:
        prev_snapshot = self.prev_snapshot
        if prev_snapshot and prev_snapshot.get("ui_mode") == state.ui_mode:
            if state.ui_mode == "main" and self._render_main_incremental(prev_snapshot):
                state.last_render_time = time.time()
                state.dirty = False
                return
            if state.ui_mode == "submenu" and self._render_submenu_incremental(prev_snapshot):
                state.last_render_time = time.time()
                state.dirty = False
                return
            if state.ui_mode == "file_browser" and self._render_file_browser_incremental(prev_snapshot):
                state.last_render_time = time.time()
                state.dirty = False
                return

        image = Image.new("RGB", (self.width, self.height), BACKGROUND)
        draw = ImageDraw.Draw(image)
        self._draw_header(draw)
        if state.ui_mode == "main":
            self._draw_main(draw)
        elif state.ui_mode == "submenu":
            self._draw_submenu(draw)
        elif state.ui_mode == "file_source":
            self._draw_file_source(draw)
        elif state.ui_mode == "file_browser":
            self._draw_file_browser(draw)
        elif state.ui_mode == "player":
            self._draw_player(draw)
        elif state.ui_mode == "power_menu":
            self._draw_power_menu(draw)
        if state.usb_eject_confirm:
            self._draw_usb_eject_confirm(draw)
        self._draw_footer(draw)
        self._write_image(image)
        self.prev_snapshot = self._snapshot_state()
        state.last_render_time = time.time()
        state.dirty = False

    def _draw_header(self, draw):
        draw.rectangle((0, 0, self.width, 44), fill=(22, 28, 40))
        draw.text((12, 8), f"Fluid Ardule  {SCRIPT_VERSION}", font=self.font_title, fill=FG)

    def _main_menu_value(self, idx: int) -> str:
        if idx == 0:
            return f"{state.sf_name}/{state.current_preset_name}"
        if idx == 1:
            return state.dac_name
        if idx == 2:
            return state.midi_display_text
        if idx == 3:
            return Path(state.player_path).name if state.player_path else "Browse"
        if idx == 4:
            return "Reserved"
        return ""

    def _draw_scrolled_rows(self, draw, labels, current_idx, top_y, row_h, bottom_y, show_current_marks=False):
        max_rows = max(1, (bottom_y - top_y) // row_h)
        total_count = len(labels)
        start_idx = max(0, current_idx - max_rows + 1) if current_idx >= max_rows else 0
        row_margin = 3
        for visible_row, idx in enumerate(range(start_idx, min(len(labels), start_idx + max_rows))):
            top = top_y + visible_row * row_h
            label = labels[idx]
            if isinstance(label, tuple):
                text, is_current = label
            else:
                text, is_current = label, False

            index_prefix = ""
            if state.ui_mode == "submenu" and state.submenu_key in ("preset_category", "preset"):
                index_prefix = f"[{idx + 1}/{total_count}] "

            if idx == current_idx:
                draw.rounded_rectangle(
                    (20, top + row_margin, self.width - 20, top + row_h - row_margin),
                    radius=8,
                    fill=SELECT_BG,
                )
                fill = FG
                prefix = "▶ "
            else:
                fill = FG if (show_current_marks and is_current) else DIM
                prefix = "  "
            suffix = " *" if (show_current_marks and is_current) else ""
            row_text = f"{prefix}{index_prefix}{text}{suffix}"
            draw_left_vcentered_text_list(draw, 28, top, row_h, row_text, self.font_body, fill)

    def _draw_main(self, draw):
        y = 56
        row_h = 42
        row_margin = 4
        list_bottom = self.height - 48
        draw.rounded_rectangle((12, y - 4, self.width - 12, list_bottom), radius=12, fill=BOX_BG)

        visible_rows = max(1, (list_bottom - y) // row_h)
        start_idx = max(0, state.menu_index - visible_rows + 1) if state.menu_index >= visible_rows else 0
        for visible_row, idx in enumerate(range(start_idx, min(len(MAIN_MENU), start_idx + visible_rows))):
            top = y + visible_row * row_h
            label = MAIN_MENU[idx]
            value = self._main_menu_value(idx)
            box_top = top + row_margin
            box_bottom = top + row_h - row_margin

            if idx == state.menu_index:
                draw.rounded_rectangle((20, box_top, self.width - 20, box_bottom), radius=8, fill=SELECT_BG)
                fill = FG
                value_fill = FG
                prefix = "▶ "
            else:
                fill = DIM
                value_fill = ACCENT if value else DIM
                prefix = "  "

            label_text = f"{prefix}{label}"
            label_bbox = draw_left_vcentered_text(draw, 28, top, row_h, label_text, self.font_menu, fill)

            if value:
                label_right = label_bbox[2]
                reserved_gap = 20
                value_min_x = label_right + reserved_gap
                value_right_x = self.width - 28
                max_width = max(60, value_right_x - value_min_x)
                value_text = ellipsize_text(value, self.font_value, max_width)
                bbox = draw.textbbox((0, 0), value_text, font=self.font_value)
                value_x = max(value_min_x, value_right_x - (bbox[2] - bbox[0]))
                draw_left_vcentered_text(draw, value_x, top, row_h, value_text, self.font_value, value_fill)

    def _draw_submenu_title(self, draw, title: str, info: str = ""):
        draw.text((16, 58), title, font=self.font_title, fill=ACCENT)
        if info:
            bbox = draw.textbbox((0, 0), info, font=self.font_small)
            draw.text(
                (self.width - 16 - (bbox[2] - bbox[0]), 66),
                info,
                font=self.font_small,
                fill=ACCENT,
            )

    def _draw_submenu_box(self, draw):
        draw.rounded_rectangle(
            (12, 98, self.width - 12, self.height - 48),
            radius=12,
            fill=BOX_BG,
        )

    def _draw_submenu_generic_rows(self, draw, options):
        self._draw_scrolled_rows(
            draw,
            options,
            state.submenu_index,
            104,
            38,
            self.height - 50,
            show_current_marks=True,
        )

    def _draw_submenu_soundfont_rows(self, draw, options):
        visible_rows = max(1, (self.height - 50 - 104) // 38)
        start_idx = max(0, state.submenu_index - visible_rows + 1) if state.submenu_index >= visible_rows else 0

        for visible_row, idx in enumerate(range(start_idx, min(len(options), start_idx + visible_rows))):
            top = 104 + visible_row * 38
            text, is_current = options[idx]

            if idx == state.submenu_index:
                draw.rounded_rectangle((20, top, self.width - 20, top + 32), radius=8, fill=SELECT_BG)
                fill = FG
                prefix = "▶ "
            else:
                fill = FG if is_current else DIM
                prefix = "  "

            suffix = " *" if is_current else ""
            row_text = f"{prefix}{text}{suffix}"
            draw_left_vcentered_text_list(draw, 28, top, 38, row_text, self.font_body, fill)

            total, _drums = soundfont_preset_counts(idx)
            if total:
                value = str(total)
                if total > 1:
                    value += " >"
                value_fill = ACCENT if idx != state.submenu_index else FG
                draw_right_vcentered_text(draw, self.width - 28, top, 38, value, self.font_small, value_fill)

    def _draw_submenu(self, draw):
        title_map = {
            "soundfont": "Select SoundFont",
            "preset_category": "Preset Categories",
            "preset": "Select Preset",
            "dac": "Select DAC",
            "midi": "MIDI Mode",
            "placeholder": "Coming Soon",
        }

        title = title_map.get(state.submenu_key or "", "Menu")
        info = ""

        if state.submenu_key in ("preset_category", "preset"):
            info = state.category_source_name if state.submenu_key == "preset_category" else state.preset_source_name
            if state.submenu_key == "preset" and state.category_entries:
                cat = state.category_entries[clamp_index(state.category_index, len(state.category_entries))]
                info = f"{info} / {cat}" if info else cat

        self._draw_submenu_title(draw, title, info)
        self._draw_submenu_box(draw)

        options = get_submenu_options()

        if state.submenu_key == "soundfont":
            self._draw_submenu_soundfont_rows(draw, options)
        else:
            self._draw_submenu_generic_rows(draw, options)

    def _draw_file_source(self, draw):
        draw.text((16, 58), "File Player", font=self.font_title, fill=ACCENT)
        sf_text = state.sf_name
        usb_text = usb_status_text()
        right_text = f"{usb_text}  {sf_text}" if sf_text else usb_text
        sf_bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (sf_bbox[2]-sf_bbox[0]), 66), right_text, font=self.font_small, fill=ACCENT)
        draw.text((18, 90), "Select source", font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 112, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = [entry["display"] for entry in get_file_source_entries()] or ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.browser_index, 118, 40, self.height - 50)

    def _draw_file_browser(self, draw):
        draw.text((16, 58), "File Player", font=self.font_title, fill=ACCENT)
        sf_text = state.sf_name
        usb_text = usb_status_text()
        right_text = f"{usb_text}  {sf_text}" if sf_text else usb_text
        sf_bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (sf_bbox[2]-sf_bbox[0]), 66), right_text, font=self.font_small, fill=ACCENT)
        path_text = state.browser_path
        if len(path_text) > 42:
            path_text = "..." + path_text[-39:]
        draw.text((18, 90), path_text, font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 112, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = [entry["display"] for entry in state.browser_entries] or ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.browser_index, 118, 36, self.height - 50)

    def _draw_player(self, draw):
        draw.text((16, 58), "Now Playing", font=self.font_title, fill=ACCENT)
        sf_text = state.sf_name
        usb_text = usb_status_text()
        right_text = f"{usb_text}  {sf_text}" if sf_text else usb_text
        sf_bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (sf_bbox[2]-sf_bbox[0]), 66), right_text, font=self.font_small, fill=ACCENT)
        name = Path(state.player_path).name if state.player_path else "No file"
        kind = state.player_proc_kind.upper() if state.player_proc_kind else "-"
        draw.text((18, 92), f"{kind}  {state.player_status}", font=self.font_small, fill=DIM)

        draw.rounded_rectangle((12, 116, self.width - 12, 168), radius=12, fill=BOX_BG)
        one_line_name = ellipsize_text(name, self.font_menu, self.width - 48)
        draw.text((24, 129), one_line_name, font=self.font_menu, fill=FG)

        draw.rounded_rectangle((12, 178, self.width - 12, 286), radius=12, fill=BOX_BG)

        left_label = "LIST" if state.player_status == "Stopped" else "STOP"
        up_label = "PREV"
        down_label = "NEXT"
        right_label = "-"
        if state.player_status == "Stopped":
            sel_label = "PLAY"
        else:
            if state.player_proc_kind == "midi":
                sel_label = "REPLAY"
            else:
                sel_label = "RESUME" if state.player_paused else "PAUSE"

        base_fill = (58, 95, 168)

        buttons = [
            {"name": "LEFT",  "label": left_label, "x": 18,  "y": 210, "w": 74,  "h": 46},
            {"name": "UP",    "label": up_label,   "x": 122, "y": 184, "w": 96,  "h": 42},
            {"name": "DOWN",  "label": down_label, "x": 122, "y": 236, "w": 96,  "h": 42},
            {"name": "RIGHT", "label": right_label,"x": 248, "y": 210, "w": 74,  "h": 46},
            {"name": "SEL",   "label": sel_label,  "x": 350, "y": 202, "w": 108, "h": 62},
        ]

        for btn in buttons:
            x = btn["x"]
            y = btn["y"]
            w = btn["w"]
            h = btn["h"]
            fill = base_fill
            draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=fill)
            font = self.font_small if len(btn["label"]) >= 6 else self.font_body
            bbox = draw.textbbox((0, 0), btn["label"], font=font)
            tx = x + (w - (bbox[2] - bbox[0])) / 2
            ty = y + (h - (bbox[3] - bbox[1])) / 2 - 2
            draw.text((tx, ty), btn["label"], font=font, fill=FG)

    
    def _draw_power_title(self, draw):
        draw.text((20, 60), "Power", font=self.font_title, fill=ACCENT)

    def _draw_power_options(self, draw):
        options = ["> Halt", "> Reboot"]
        self._draw_scrolled_rows(
            draw,
            options,
            state.power_index,
            110,
            38,
            self.height - 60,
            show_current_marks=False,
        )

    def _draw_power_confirm(self, draw):
        draw.text((20, self.height - 40), "SELECT to confirm", font=self.font_small, fill=DIM)

    def _draw_power_menu(self, draw):
        draw.text((16, 58), "Power Menu", font=self.font_title, fill=ACCENT)
        draw.rounded_rectangle((32, 100, self.width - 32, self.height - 60), radius=14, fill=BOX_BG)
        if state.power_confirm_action:
            draw.text((52, 118), f"{state.power_confirm_action}?", font=self.font_title, fill=FG)
            draw.text((52, 156), "Are you sure?", font=self.font_body, fill=DIM)
            labels = POWER_CONFIRM_ITEMS
            current_idx = state.power_confirm_index
            start_y = 202
            row_h = 40
        else:
            draw.text((52, 118), "Select action", font=self.font_body, fill=DIM)
            labels = POWER_MENU_ITEMS
            current_idx = state.power_menu_index
            start_y = 156
            row_h = 40
        for i, label in enumerate(labels):
            top = start_y + i * row_h
            if i == current_idx:
                draw.rounded_rectangle((52, top, self.width - 52, top + 32), radius=8, fill=SELECT_BG)
                fill = FG
                prefix = "▶ "
            else:
                fill = DIM
                prefix = "  "
            draw.text((64, top + 3), f"{prefix}{label}", font=self.font_body, fill=fill)
    def _draw_usb_eject_confirm(self, draw):
        draw.rounded_rectangle((70, 92, self.width - 70, self.height - 78), radius=14, fill=(28, 34, 48), outline=ACCENT, width=2)
        title = "Eject USB?"
        draw.text((96, 112), title, font=self.font_title, fill=FG)
        draw.text((96, 156), "Safely remove mounted USB media", font=self.font_small, fill=DIM)

        # buttons
        left_x1, left_y1, left_x2, left_y2 = 92, 198, 212, 266
        sel_x1, sel_y1, sel_x2, sel_y2 = self.width - 212, 198, self.width - 92, 266
        draw.rounded_rectangle((left_x1, left_y1, left_x2, left_y2), radius=10, fill=(58, 68, 86))
        draw.rounded_rectangle((sel_x1, sel_y1, sel_x2, sel_y2), radius=10, fill=SELECT_BG)

        def draw_centered_button(x1, y1, x2, y2, top_text, bottom_text):
            top_bbox = draw.textbbox((0, 0), top_text, font=self.font_body)
            bottom_bbox = draw.textbbox((0, 0), bottom_text, font=self.font_small)
            top_h = top_bbox[3] - top_bbox[1]
            bottom_h = bottom_bbox[3] - bottom_bbox[1]
            gap = 2
            total_h = top_h + gap + bottom_h
            start_y = y1 + ((y2 - y1) - total_h) // 2 - 1

            top_w = top_bbox[2] - top_bbox[0]
            bottom_w = bottom_bbox[2] - bottom_bbox[0]

            top_x = x1 + ((x2 - x1) - top_w) // 2
            bottom_x = x1 + ((x2 - x1) - bottom_w) // 2

            draw.text((top_x, start_y), top_text, font=self.font_body, fill=FG)
            draw.text((bottom_x, start_y + top_h + gap), bottom_text, font=self.font_small, fill=FG)

        draw_centered_button(left_x1, left_y1, left_x2, left_y2, "LEFT", "Cancel")
        draw_centered_button(sel_x1, sel_y1, sel_x2, sel_y2, "SEL", "Eject")

    def _draw_footer(self, draw):
        draw.rectangle((0, self.height - 40, self.width, self.height), fill=(22, 28, 40))
        event = state.last_event[-20:] if state.last_event else "-"
        footer_hint = None
        if state.ui_mode == "submenu" and state.submenu_key == "soundfont":
            try:
                total, _drums = soundfont_preset_counts(state.submenu_index)
                if total > 1:
                    footer_hint = "Press > for presets"
            except Exception:
                pass

        left_text = footer_hint or event
        draw.text((12, self.height - 34), left_text, font=self.font_small, fill=DIM)

        if not footer_hint:
            metrics = f"{state.cpu_temp_text} {state.cpu_load_text}"
            metrics_bbox = draw.textbbox((0, 0), metrics, font=self.font_small)
            metrics_x = max(140, (self.width - (metrics_bbox[2] - metrics_bbox[0])) // 2)
            draw.text((metrics_x, self.height - 34), metrics, font=self.font_small, fill=DIM)

        right = state.midi_display_text
        color = STATUS_GOOD if state.midi_connected else STATUS_BAD
        bbox = draw.textbbox((0, 0), right, font=self.font_small)
        draw.text((self.width - 12 - (bbox[2]-bbox[0]), self.height - 34), right, font=self.font_small, fill=color)




def ellipsize_text(text: str, font, max_width: int) -> str:
    if not text:
        return ""
    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text
    ell = "..."
    for i in range(len(text), 0, -1):
        candidate = text[:i].rstrip() + ell
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return candidate
    return ell

def wrap_text(text: str, font, max_width: int) -> list[str]:
    if not text:
        return [""]
    words = text.replace("_", " ").split(" ")
    lines = []
    current = ""
    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    for word in words:
        test = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
                current = word
            else:
                lines.append(word)
                current = ""
    if current:
        lines.append(current)
    return lines or [text]



def draw_left_vcentered_text(draw, x: int, y: int, h: int, text: str, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    ty = y + max(0, (h - th) // 2) - bbox[1] - 1
    draw.text((x, ty), text, font=font, fill=fill)
    return draw.textbbox((x, ty), text, font=font)


def draw_right_vcentered_text(draw, right_x: int, y: int, h: int, text: str, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = right_x - tw
    ty = y + max(0, (h - th) // 2) - bbox[1] - 1
    draw.text((tx, ty), text, font=font, fill=fill)
    return draw.textbbox((tx, ty), text, font=font)


def draw_left_vcentered_text_list(draw, x: int, y: int, h: int, text: str, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    ty = y + max(0, (h - th) // 2) - bbox[1] - 1
    draw.text((x, ty), text, font=font, fill=fill)
    return draw.textbbox((x, ty), text, font=font)

display = TFTDisplay(FRAMEBUFFER_DEVICE, FRAMEBUFFER_SYS_DIR)


def invalidate_full_display() -> None:
    display.prev_image = None


# =========================================================
# DAC and MIDI discovery
# =========================================================

# =========================================================
# Bridge helpers
# =========================================================

def start_bridge() -> bool:
    if state.bridge_proc and state.bridge_proc.poll() is None:
        state.bridge_running = True
        return True
    if not Path(BRIDGE_EXECUTABLE).exists():
        mark_dirty(f"Bridge missing: {BRIDGE_EXECUTABLE}")
        state.bridge_running = False
        return False
    try:
        log(f"Starting bridge: {BRIDGE_EXECUTABLE}")
        state.bridge_proc = subprocess.Popen(
            [BRIDGE_EXECUTABLE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            text=True,
        )
        time.sleep(1.0)
        state.bridge_running = state.bridge_proc.poll() is None
        if state.bridge_running:
            mark_dirty("Bridge started")
            return True
        mark_dirty("Bridge failed")
        return False
    except Exception as exc:
        state.bridge_proc = None
        state.bridge_running = False
        mark_dirty(f"Bridge start failed: {exc}")
        return False


def stop_bridge() -> None:
    proc = state.bridge_proc
    if proc is None:
        state.bridge_running = False
        return
    try:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.3)
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception as exc:
        log(f"stop_bridge exception: {exc}")
    state.bridge_proc = None
    state.bridge_running = False


def ensure_bridge_running() -> bool:
    if state.midi_mode != "uno2_bridge_seq":
        return True
    if state.bridge_proc and state.bridge_proc.poll() is None:
        state.bridge_running = True
        return True
    return start_bridge()


def parse_aconnect_ports() -> list[dict]:
    code, out = run_cmd(["aconnect", "-l"])
    if code != 0:
        return []
    ports = []
    current_client_id = None
    current_client_name = None
    for line in out.splitlines():
        if line.startswith("client ") and ": '" in line:
            try:
                current_client_id = line.split()[1].rstrip(":")
                current_client_name = line.split("'", 2)[1]
            except Exception:
                current_client_id = None
                current_client_name = None
            continue
        s = line.strip()
        if current_client_id is None or current_client_name is None:
            continue
        if not s or s.startswith('Connecting'):
            continue
        if " '" not in s:
            continue
        try:
            port_id = s.split()[0]
            port_name = s.split("'", 2)[1]
            ports.append({
                'client_id': current_client_id,
                'client_name': current_client_name,
                'port_id': port_id,
                'port_name': port_name,
                'port': f"{current_client_id}:{port_id}",
            })
        except Exception:
            continue
    return ports


def parse_aconnect_clients() -> list[tuple[str, str]]:
    seen = []
    seen_ids = set()
    for item in parse_aconnect_ports():
        if item['client_id'] in seen_ids:
            continue
        seen_ids.add(item['client_id'])
        seen.append((item['client_id'], item['client_name']))
    return seen


def find_fluidsynth_port() -> str | None:
    for item in parse_aconnect_ports():
        name = item['client_name']
        if "FLUID Synth" in name or "FluidSynth" in name or "fluidsynth" in name:
            return item['port']
    return None


def find_bridge_port() -> str | None:
    for item in parse_aconnect_ports():
        name = item['client_name']
        if BRIDGE_PORT_HINT.lower() in name.lower() or "uno" in name.lower():
            state.bridge_port_name = name
            return item['port']
    return None


def list_alsa_seq_input_ports() -> list[tuple[str, str]]:
    options = []
    for item in parse_aconnect_ports():
        client_name = item['client_name']
        client_name_l = client_name.lower()
        if client_name in {'System', 'Midi Through'}:
            continue
        if 'fluid synth' in client_name_l or 'fluidsynth' in client_name_l:
            continue
        if BRIDGE_PORT_HINT.lower() in client_name_l or 'uno-midi-bridge' in client_name_l:
            continue
        if 'announce' in item['port_name'].lower() or 'timer' in item['port_name'].lower():
            continue
        label = f"{client_name} / {item['port_name']}"
        options.append((item['port'], label))
    return options


def choose_alsa_seq_input() -> tuple[str | None, str | None]:
    options = list_alsa_seq_input_ports()
    if not options:
        state.selected_alsa_input = None
        state.selected_alsa_input_name = None
        return None, None

    # 1) Exact previously remembered port wins.
    if state.preferred_seq_port:
        for port, label in options:
            if port == state.preferred_seq_port:
                state.selected_alsa_input = port
                state.selected_alsa_input_name = label
                return port, label

    # 2) If port numbers changed, fall back to remembered label/name.
    if state.preferred_seq_name:
        pref = state.preferred_seq_name.lower()
        for port, label in options:
            if label.lower() == pref or pref in label.lower():
                state.selected_alsa_input = port
                state.selected_alsa_input_name = label
                return port, label

    # 3) Current selected port still valid.
    if state.selected_alsa_input:
        for port, label in options:
            if state.selected_alsa_input == port or state.selected_alsa_input == label:
                state.selected_alsa_input = port
                state.selected_alsa_input_name = label
                return port, label

    # 4) Otherwise use first available.
    state.selected_alsa_input, state.selected_alsa_input_name = options[0]
    return options[0]

    if state.selected_alsa_input:
        for port, label in options:
            if state.selected_alsa_input == port or state.selected_alsa_input == label:
                state.selected_alsa_input = port
                state.selected_alsa_input_name = label
                return port, label

    state.selected_alsa_input, state.selected_alsa_input_name = options[0]
    return options[0]


def connect_bridge_to_fluidsynth() -> bool:
    src = find_bridge_port()
    dst = find_fluidsynth_port()
    if not src or not dst:
        state.midi_connected = False
        mark_dirty("SEQ ports not ready")
        return False
    code, out = run_cmd(["aconnect", src, dst])
    already = "already" in out.lower()
    if code == 0 or already:
        state.midi_src_port = src
        state.fluid_dst_port = dst
        state.midi_src_name = state.bridge_port_name
        state.midi_connected = True
        refresh_midi_display_text()
        if code == 0:
            mark_dirty(f"Bridge connected {src}->{dst}")
        return True
    state.midi_connected = False
    mark_dirty(f"aconnect failed: {out[:40]}")
    return False


def connect_selected_alsa_to_fluidsynth() -> bool:
    src, src_name = choose_alsa_seq_input()
    dst = find_fluidsynth_port()
    if not src:
        state.midi_connected = False
        state.midi_src_port = '-'
        state.midi_src_name = 'No ALSA seq input'
        refresh_midi_display_text()
        mark_dirty('ALSA seq input missing')
        return False
    if not dst:
        state.midi_connected = False
        state.midi_src_port = src
        state.midi_src_name = src_name or src
        refresh_midi_display_text()
        mark_dirty('FluidSynth port missing')
        return False
    code, out = run_cmd(["aconnect", src, dst])
    already = "already" in out.lower()
    if code == 0 or already:
        state.midi_src_port = src
        state.midi_src_name = src_name or src
        state.selected_alsa_input = src
        state.selected_alsa_input_name = src_name or src
        state.preferred_seq_port = src
        state.preferred_seq_name = src_name or src
        state.fluid_dst_port = dst
        state.midi_connected = True
        refresh_midi_display_text()
        if code == 0:
            mark_dirty(f'ALSA seq connected {src}->{dst}')
        return True
    state.midi_connected = False
    state.midi_src_port = src
    state.midi_src_name = src_name or src
    refresh_midi_display_text()
    mark_dirty(f'ALSA seq aconnect failed: {out[:40]}')
    return False

def build_available_dac_options() -> list[tuple[str, str]]:
    options = [DEFAULT_DAC]
    code, out = run_cmd(["aplay", "-l"])
    if code != 0:
        return options
    for card_id, display_name in KNOWN_USB_DACS:
        found = False
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("card ") and (f"[{card_id}]" in line or f" {card_id} [" in line):
                found = True
                break
        if found:
            options.append((f"plughw:CARD={card_id},DEV=0", display_name))
    return options


def refresh_dac_options(quiet: bool = False) -> bool:
    old = list(state.dac_options)
    current_device = state.audio_device
    state.dac_options = build_available_dac_options()
    found_index = 0
    for i, (dev, _name) in enumerate(state.dac_options):
        if dev == current_device:
            found_index = i
            break
    state.dac_index = found_index
    state.dac_name = state.dac_options[found_index][1]
    state.dac_preview_index = clamp_index(state.dac_preview_index, len(state.dac_options))
    changed = old != state.dac_options
    if changed and not quiet:
        mark_dirty("DAC list updated")
    return changed


def midi_mode_to_label(mode: str) -> str:
    labels = {
        "usb_direct_raw": "USB direct RAW",
        "uno2_bridge_seq": "UNO-2 bridge (SEQ)",
        "alsa_midi": "ALSA MIDI (SEQ)",
    }
    return labels.get(mode, mode)


def midi_mode_to_driver(mode: str) -> str:
    return "alsa_raw" if mode == "usb_direct_raw" else "alsa_seq"


def refresh_midi_display_text() -> None:
    if state.midi_mode == "usb_direct_raw":
        raw_label = shorten_text((state.midi_src_name or "RAW").replace(" MIDI 1", ""), 10)
        state.midi_display_text = f"RAW:{raw_label}" if raw_label and raw_label != "RAW" else "RAW"
    elif state.midi_mode == "uno2_bridge_seq":
        state.midi_display_text = "UNO2/SEQ" if state.bridge_running else "UNO2/OFF"
    else:
        if not state.selected_alsa_input and not state.selected_alsa_input_name:
            state.midi_display_text = "SEQ:waiting"
        else:
            alsa_label = shorten_text((state.selected_alsa_input_name or state.midi_src_name or 'ALSA').replace(' MIDI 1', ''), 10)
            state.midi_display_text = f"SEQ:{alsa_label}" if alsa_label else "SEQ:waiting"


def build_midi_input_options() -> list[tuple[str, str]]:
    return list(state.midi_mode_options)


def refresh_midi_options(quiet: bool = False) -> bool:
    old = list(state.midi_options)
    state.midi_options = build_midi_input_options()
    state.midi_selected_name = midi_mode_to_label(state.midi_mode)
    if state.midi_mode == "usb_direct_raw":
        prev_raw_port = state.midi_src_port
        selected_port, selected_name = choose_raw_midi_input()
        state.midi_src_name = selected_name or "No raw MIDI"
        state.midi_src_port = selected_port or "-"
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()
        if fluid_proc is not None and fluid_proc.poll() is None and selected_port and prev_raw_port in {"-", "", None}:
            restart_engine(state.sf_index, state.dac_index)
            restore_current_preset_after_engine_restart()
            selected_port, selected_name = choose_raw_midi_input()
            state.midi_src_name = selected_name or "No raw MIDI"
            state.midi_src_port = selected_port or "-"
            state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
            refresh_midi_display_text()
            mark_dirty(f"MIDI {state.midi_display_text}")
            return
    elif state.midi_mode == "uno2_bridge_seq":
        state.midi_src_name = state.bridge_port_name
        state.midi_src_port = "seq"
    else:
        selected_port, selected_name = choose_alsa_seq_input()
        state.selected_alsa_input = selected_port
        state.selected_alsa_input_name = selected_name
        state.midi_src_name = selected_name or 'alsa sequencer'
        state.midi_src_port = selected_port or '-'
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
    refresh_midi_display_text()
    changed = old != state.midi_options
    if changed and not quiet:
        mark_dirty(f"MIDI mode: {state.midi_display_text}")
    return changed


def get_selected_midi_source() -> tuple[str | None, str | None]:
    selected_mode = None
    selected_name = None
    if state.midi_selected_name:
        for mode, name in state.midi_options:
            if name == state.midi_selected_name:
                selected_mode = mode
                selected_name = name
                break
    if selected_mode is None and state.midi_options:
        selected_mode, selected_name = state.midi_options[0]
        state.midi_selected_name = selected_name
    return selected_mode, selected_name


def clear_midi_reconnect_pending() -> None:
    state.midi_pending_signature = ""
    state.midi_candidate_seen_since = 0.0


def schedule_midi_reconnect(now: float, signature: str) -> None:
    state.midi_pending_signature = signature
    state.midi_candidate_seen_since = now


def resolve_client_name_from_port(port: str) -> str:
    return port


def reconnect_midi_to_fluidsynth(force_draw: bool = True) -> None:
    state.fluid_dst_port = "-"
    if state.midi_mode == "usb_direct_raw":
        selected_port, selected_name = choose_raw_midi_input()
        state.midi_src_port = selected_port or '-'
        state.midi_src_name = selected_name or 'No raw MIDI'
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()
    elif state.midi_mode == "uno2_bridge_seq":
        refresh_midi_display_text()
        if ensure_bridge_running():
            connect_bridge_to_fluidsynth()
        else:
            state.midi_connected = False
    else:
        selected_port, selected_name = choose_alsa_seq_input()
        state.midi_src_port = selected_port or "-"
        state.midi_src_name = selected_name or "alsa sequencer"
        state.selected_alsa_input = selected_port
        state.selected_alsa_input_name = selected_name
        refresh_midi_display_text()
        connect_selected_alsa_to_fluidsynth()
    clear_midi_reconnect_pending()
    if force_draw:
        mark_dirty(f"MIDI mode: {state.midi_display_text}")


# =========================================================
# File browser helpers
# =========================================================

def current_soundfont_path() -> str:
    return SOUNDFONTS[state.sf_index][0]



GM_CATEGORY_NAMES = [
    "Piano", "Chromatic", "Organ", "Guitar",
    "Bass", "Strings", "Ensemble", "Brass",
    "Reed", "Pipe", "Lead", "Pad",
    "FX", "Ethnic", "Percussive", "SFX",
]


def categorize_preset(bank: int, program: int, name: str = "") -> str:
    if int(bank) == 128:
        return "Drums"
    try:
        return GM_CATEGORY_NAMES[max(0, min(15, int(program) // 8))]
    except Exception:
        return "Other"


def preset_json_path_for_sf2(sf2_path: str) -> Path:
    return Path(sf2_path).with_suffix(".presets.json")


def load_presets_for_sf2(sf_index: int) -> list[dict]:
    sf2_path, _sf_name = SOUNDFONTS[sf_index]
    json_path = preset_json_path_for_sf2(sf2_path)
    if not json_path.exists():
        return []
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"preset json load failed: {exc}")
        return []

    presets = payload.get("presets", [])
    cleaned: list[dict] = []
    for item in presets:
        try:
            bank = int(item.get("bank", 0))
            program = int(item.get("program", 0))
            name = str(item.get("name", "")).strip() or "Unnamed"
            cleaned.append({
                "name": name,
                "bank": bank,
                "program": program,
                "category": categorize_preset(bank, program, name),
            })
        except Exception:
            continue
    cleaned.sort(key=lambda x: (x["bank"], x["program"], x["name"].lower()))
    return cleaned


def soundfont_preset_counts(sf_index: int) -> tuple[int, int]:
    sf2_path, _sf_name = SOUNDFONTS[sf_index]
    json_path = preset_json_path_for_sf2(sf2_path)
    if not json_path.exists():
        return 0, 0
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        return int(payload.get("preset_count", 0)), int(payload.get("drum_preset_count", 0))
    except Exception:
        return 0, 0


def choose_default_preset(presets: list[dict]) -> dict | None:
    if not presets:
        return None
    for p in presets:
        if p.get("bank") == 0 and p.get("program") == 0:
            return p
    for p in presets:
        if p.get("bank") != 128:
            return p
    return presets[0]



def enter_preset_submenu(sf_index: int) -> None:
    presets = load_presets_for_sf2(sf_index)
    if not presets:
        mark_dirty("No preset JSON")
        return
    cats = []
    seen = set()
    for p in presets:
        cat = p.get("category") or categorize_preset(p.get("bank", 0), p.get("program", 0), p.get("name", ""))
        if cat not in seen:
            seen.add(cat)
            cats.append(cat)
    state.category_entries = cats
    state.category_source_sf_index = sf_index
    state.category_source_name = SOUNDFONTS[sf_index][1]
    state.ui_mode = "submenu"
    state.submenu_key = "preset_category"
    state.category_index = 0
    state.submenu_index = 0
    invalidate_full_display()
    total, drums = soundfont_preset_counts(sf_index)
    if total:
        mark_dirty(f"{state.category_source_name}: {total} presets, {drums} drums")
    else:
        mark_dirty(f"Categories: {state.category_source_name}")


def enter_preset_list_from_category(category_index: int) -> None:
    sf_index = state.category_source_sf_index if state.category_source_sf_index is not None else state.sf_index
    presets = load_presets_for_sf2(sf_index)
    if not presets:
        mark_dirty("No preset JSON")
        return
    if not state.category_entries:
        mark_dirty("No categories")
        return
    category_index = clamp_index(category_index, len(state.category_entries))
    category = state.category_entries[category_index]
    filtered = [p for p in presets if (p.get("category") or categorize_preset(p.get("bank",0), p.get("program",0), p.get("name",""))) == category]
    if not filtered:
        mark_dirty("No preset in category")
        return
    state.preset_entries = filtered
    state.preset_sf_index = sf_index
    state.preset_source_name = SOUNDFONTS[sf_index][1]
    state.category_index = category_index
    state.ui_mode = "submenu"
    state.submenu_key = "preset"
    state.submenu_index = 0
    for i, p in enumerate(filtered):
        if (
            sf_index == state.sf_index
            and p.get("bank") == state.current_preset_bank
            and p.get("program") == state.current_preset_program
        ):
            state.submenu_index = i
            break
    state.preset_index = state.submenu_index
    begin_preset_preview_session()
    preview_preset_at_index(state.submenu_index)
    invalidate_full_display()
    mark_dirty(f"{category}: {len(filtered)} presets")


def return_to_soundfont_submenu() -> None:
    state.ui_mode = "submenu"
    state.submenu_key = "soundfont"
    state.submenu_index = state.category_source_sf_index if state.category_source_sf_index is not None else (
        state.preset_sf_index if state.preset_sf_index is not None else state.sf_index
    )
    invalidate_full_display()
    mark_dirty("Back to SF2")


def return_to_category_submenu() -> None:
    state.ui_mode = "submenu"
    state.submenu_key = "preset_category"
    state.submenu_index = clamp_index(state.category_index, len(state.category_entries))
    invalidate_full_display()
    mark_dirty("Back to category")


def begin_preset_preview_session() -> None:
    state.preview_active = False
    state.preview_restore_sf_index = state.sf_index
    state.preview_restore_preset_bank = state.current_preset_bank
    state.preview_restore_preset_program = state.current_preset_program
    state.preview_restore_preset_name = state.current_preset_name


def preview_preset_at_index(index: int) -> None:
    if not state.preset_entries:
        return
    idx = clamp_index(index, len(state.preset_entries))
    p = state.preset_entries[idx]
    target_sf_index = state.preset_sf_index if state.preset_sf_index is not None else state.sf_index
    if target_sf_index != state.sf_index:
        restart_engine(target_sf_index, state.dac_index)
    apply_preset(p["bank"], p["program"], p["name"])
    state.preview_active = True
    state.preset_index = idx
    state.submenu_index = idx
    drum_tag = " [DRUM]" if p.get("bank") == 128 else ""
    mark_dirty(f'Preview: {p["name"]} ({p["bank"]},{p["program"]}){drum_tag}')


def cancel_preset_preview_and_restore() -> None:
    if state.preview_restore_sf_index is None:
        state.preview_active = False
        return
    restore_sf = state.preview_restore_sf_index
    restore_bank = state.preview_restore_preset_bank
    restore_program = state.preview_restore_preset_program
    restore_name = state.preview_restore_preset_name
    if restore_sf != state.sf_index:
        restart_engine(restore_sf, state.dac_index)
    apply_preset(restore_bank, restore_program, restore_name)
    state.preview_active = False


def commit_current_preview() -> None:
    state.preview_active = False
    state.preview_restore_sf_index = None
    state.preview_restore_preset_bank = state.current_preset_bank
    state.preview_restore_preset_program = state.current_preset_program
    state.preview_restore_preset_name = state.current_preset_name



def list_browser_entries(path: str) -> list[dict]:
    entries = []
    try:
        names = os.listdir(path)
    except Exception:
        return []

    dirs = []
    files = []
    path_norm = normalize_path(path)
    root_norm = normalize_path(FILE_MEDIA_ROOT)
    for name in names:
        # hide dotfiles / dot-directories and common system clutter
        if name.startswith(".") or name.lower() in {"system volume information", "thumbs.db", "desktop.ini"}:
            continue
        full = os.path.join(path, name)
        if path_norm == root_norm and name == "usb":
            continue
        if os.path.isdir(full):
            dirs.append({"type": "dir", "name": name, "path": full, "display": f"{name}/"})
        elif os.path.isfile(full):
            ext = Path(name).suffix.lower()
            if ext in EXT_TAG:
                files.append({"type": "file", "name": name, "path": full, "ext": ext, "display": f"{EXT_TAG[ext]} {name}"})
    dirs.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())
    entries.extend(dirs)
    entries.extend(files)
    return entries


def refresh_browser_entries(keep_name: str | None = None) -> None:
    entries = list_browser_entries(state.browser_path)
    state.browser_entries = entries
    if keep_name:
        for i, e in enumerate(entries):
            if e["name"] == keep_name:
                state.browser_index = i
                break
        else:
            state.browser_index = clamp_index(state.browser_index, len(entries))
    else:
        state.browser_index = clamp_index(state.browser_index, len(entries))


def enter_file_browser() -> None:
    enter_file_source(default_usb=state.usb_mounted)


def browser_go_parent() -> None:
    root = resolve_file_root()
    current = normalize_path(state.browser_path)

    if os.path.abspath(current) == os.path.abspath(root) or os.path.abspath(current) == os.path.abspath(USB_MOUNT_POINT):
        enter_file_source(default_usb=state.usb_mounted and os.path.abspath(current) == os.path.abspath(USB_MOUNT_POINT))
        mark_dirty("Back to source")
        return

    parent = normalize_path(os.path.dirname(current))
    if not is_under_root(parent, root):
        parent = root

    state.browser_path = parent
    state.browser_entries = list_browser_entries(state.browser_path)
    state.browser_index = 0
    mark_dirty("Parent folder")


def browser_select() -> None:
    if not state.browser_entries:
        mark_dirty("Empty folder")
        return

    item = state.browser_entries[clamp_index(state.browser_index, len(state.browser_entries))]

    if item["type"] == "dir":
        root = resolve_file_root()
        new_path = normalize_path(item["path"])
        if not is_under_root(new_path, root):
            mark_dirty("Blocked")
            return
        state.browser_path = new_path
        state.browser_entries = list_browser_entries(state.browser_path)
        state.browser_index = 0
        mark_dirty("Open folder")
        return

    play_browser_file(item)




def play_browser_file(item: dict) -> None:
    path = item.get("path")
    if not path:
        mark_dirty("Invalid file")
        return
    state.player_path = path
    start_player(path)

def browser_current_playable_indices() -> list[int]:
    return [i for i, e in enumerate(state.browser_entries) if e.get("type") == "file"]


def replay_current_file() -> None:
    if not state.player_path:
        mark_dirty("No current file")
        return

    log(f"PLAYER replay path={state.player_path}")

    state.player_stop_requested = False
    stop_player_only()

    # MIDI replay needs a hard panic before restarting, otherwise old notes
    # can survive long enough to overlap the next run.
    send_all_notes_off()
    time.sleep(0.03)
    send_all_notes_off()
    time.sleep(0.05)

    start_player(state.player_path)


def resume_selected_browser_file_after_sf_change() -> None:
    if state.ui_mode != "file_browser":
        return
    if not state.browser_entries:
        state.browser_entries = list_browser_entries(state.browser_path)
    if not state.browser_entries:
        mark_dirty("No file to resume")
        return
    idx = clamp_index(state.browser_index, len(state.browser_entries))
    item = state.browser_entries[idx]
    if item.get("type") != "file":
        mark_dirty("Select a file")
        return
    play_browser_file(item)


def play_adjacent(delta: int) -> None:
    if state.ui_mode != "player" or not state.player_path:
        mark_dirty("Player not active")
        return

    # If browser entries are stale or empty, rebuild from current browser path.
    if not state.browser_entries:
        state.browser_entries = list_browser_entries(state.browser_path)

    playable = browser_current_playable_indices()
    if not playable:
        mark_dirty("No playable files")
        return

    current_index = None
    current_abs = normalize_path(state.player_path)
    for i in playable:
        try:
            if normalize_path(state.browser_entries[i]["path"]) == current_abs:
                current_index = i
                break
        except Exception:
            pass

    if current_index is None:
        # If current file is not in the current visible list, start from first/last depending on direction.
        current_index = playable[0 if delta >= 0 else -1]

    pos = playable.index(current_index)
    next_pos = pos + delta

    # Do not wrap around at the beginning/end of the folder.
    if next_pos < 0:
        mark_dirty("First file")
        return
    if next_pos >= len(playable):
        mark_dirty("Last file")
        return

    next_idx = playable[next_pos]
    state.browser_index = next_idx
    next_path = state.browser_entries[next_idx]["path"]
    state.player_stop_requested = False
    log(f"PLAYER adjacent delta={delta} next={next_path}")
    start_player(next_path)




def try_auto_advance_media() -> bool:
    if not state.player_auto_next:
        return False
    if state.player_proc_kind != "media":
        return False
    if state.player_stop_requested:
        return False
    if not state.player_path or not state.player_origin_dir:
        return False
    if normalize_path(str(Path(state.player_path).parent)) != normalize_path(state.player_origin_dir):
        return False

    if normalize_path(state.browser_path) != normalize_path(state.player_origin_dir):
        state.browser_path = state.player_origin_dir
        refresh_browser_entries()

    playable = browser_current_playable_indices()
    if not playable:
        return False

    current_abs = normalize_path(state.player_path)
    for pos, entry_idx in enumerate(playable):
        if normalize_path(state.browser_entries[entry_idx]["path"]) == current_abs:
            # Stop at the end of the current folder instead of wrapping to the first file.
            if pos >= len(playable) - 1:
                log("PLAYER auto-next: end of folder")
                return False
            next_idx = playable[pos + 1]
            state.browser_index = next_idx
            next_path = state.browser_entries[next_idx]["path"]
            log(f"PLAYER auto-next -> {next_path}")
            start_player(next_path)
            return True
    return False

# =========================================================
# Fluidsynth engine control
# =========================================================

def open_fluid_log():
    global fluid_log_handle
    os.makedirs(LOG_DIR, exist_ok=True)
    if fluid_log_handle:
        try:
            fluid_log_handle.close()
        except Exception:
            pass
    fluid_log_handle = open(FLUID_LOG_PATH, "w", buffering=1)
    return fluid_log_handle


def stop_fluidsynth() -> None:
    global fluid_proc
    if fluid_proc is None:
        return
    try:
        if fluid_proc.poll() is None:
            os.killpg(os.getpgid(fluid_proc.pid), signal.SIGTERM)
            time.sleep(0.5)
            if fluid_proc.poll() is None:
                os.killpg(os.getpgid(fluid_proc.pid), signal.SIGKILL)
                time.sleep(0.2)
    except Exception as exc:
        log(f"stop_fluidsynth exception: {exc}")
    fluid_proc = None
    state.fluid_pid = None
    state.fluid_dst_port = "-"
    state.midi_connected = False


def start_fluidsynth(sf_path: str, audio_device: str) -> bool:
    global fluid_proc
    stop_fluidsynth()
    log_handle = open_fluid_log()
    midi_driver = midi_mode_to_driver(state.midi_mode)
    selected_port = None
    selected_name = None
    if state.midi_mode == "usb_direct_raw":
        selected_port, selected_name = choose_raw_midi_input()
        if not selected_port:
            log("start_fluidsynth: no raw MIDI input found at startup; engine will start and wait for later reconnect")
    cmd = [
        "fluidsynth", "-a", "alsa", "-m", midi_driver,
        "-o", f"audio.alsa.device={audio_device}",
        *( ["-o", f"midi.alsa.device={selected_port}"] if selected_port else [] ),
        "-o", "synth.sample-rate=48000",
        "-o", "audio.period-size=256",
        "-o", "audio.periods=4",
        "-o", f"synth.gain={FLUID_GAIN}",
        "-o", "synth.cpu-cores=1",
        "-o", "synth.reverb.active=1",
        "-o", "synth.reverb.room-size=0.48",
        "-o", "synth.reverb.damp=0.22",
        "-o", "synth.reverb.width=0.75",
        "-o", "synth.reverb.level=0.30",
        "-o", "synth.chorus.active=0",
        sf_path,
    ]
    raw_suffix = f" / {selected_port} ({selected_name})" if selected_port else ""
    log(f"Starting fluidsynth {midi_driver.upper()} with {Path(sf_path).name} / {audio_device}{raw_suffix}")
    try:
        fluid_proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, stdin=subprocess.PIPE, preexec_fn=os.setsid, text=True)
    except Exception as exc:
        mark_dirty(f"fluidsynth start failed: {exc}")
        return False
    time.sleep(1.2)
    if fluid_proc.poll() is None:
        state.fluid_pid = fluid_proc.pid
        state.player_proc_kind = None
        reconnect_midi_to_fluidsynth(force_draw=False)
        return True
    mark_dirty("fluidsynth failed to start")
    return False



def send_fluidsynth_command(command: str) -> bool:
    global fluid_proc
    if fluid_proc is None or fluid_proc.poll() is not None or fluid_proc.stdin is None:
        return False
    try:
        fluid_proc.stdin.write(command.rstrip("\n") + "\n")
        fluid_proc.stdin.flush()
        return True
    except Exception as exc:
        log(f"fluidsynth command failed: {exc}")
        return False


def apply_preset(bank: int, program: int, name: str | None = None) -> None:
    state.current_preset_bank = int(bank)
    state.current_preset_program = int(program)
    if name:
        state.current_preset_name = name

    is_drum = (state.current_preset_bank == 128)
    ok = False
    ok = send_fluidsynth_command(f"drums 0 {'on' if is_drum else 'off'}") or ok
    ok = send_fluidsynth_command(f"bank 0 {state.current_preset_bank}") or ok
    ok = send_fluidsynth_command(f"prog 0 {state.current_preset_program}") or ok
    ok = send_fluidsynth_command(f"select 0 0 {state.current_preset_bank} {state.current_preset_program}") or ok
    if is_drum:
        ok = send_fluidsynth_command("drums 9 on") or ok
        ok = send_fluidsynth_command(f"bank 9 {state.current_preset_bank}") or ok
        ok = send_fluidsynth_command(f"prog 9 {state.current_preset_program}") or ok
        ok = send_fluidsynth_command(f"select 9 0 {state.current_preset_bank} {state.current_preset_program}") or ok
    else:
        ok = send_fluidsynth_command("drums 9 off") or ok

    if ok:
        mark_dirty(f"Preset -> {state.current_preset_name}")
    else:
        mark_dirty(f"Preset queued: {state.current_preset_name}")

def apply_soundfont_with_default_preset(sf_index: int) -> None:
    restart_engine(sf_index, state.dac_index)
    presets = load_presets_for_sf2(sf_index)
    default_preset = choose_default_preset(presets)
    if default_preset:
        apply_preset(default_preset["bank"], default_preset["program"], default_preset["name"])
    else:
        state.current_preset_bank = 0
        state.current_preset_program = 0
        state.current_preset_name = "Default"
        mark_dirty(f"SF loaded: {state.sf_name}")


def restore_current_preset_after_engine_restart() -> None:
    apply_preset(
        state.current_preset_bank,
        state.current_preset_program,
        state.current_preset_name,
    )


def restart_engine(sf_index: int, dac_index: int) -> None:
    sf_index %= len(SOUNDFONTS)
    dac_index %= len(state.dac_options)
    sf_path, sf_name = SOUNDFONTS[sf_index]
    audio_device, dac_name = state.dac_options[dac_index]
    if state.midi_mode != "uno2_bridge_seq":
        stop_bridge()
    mark_dirty(f"Restarting -> SF:{sf_name} / DAC:{dac_name}")
    ok = start_fluidsynth(sf_path, audio_device)
    if not ok:
        return
    state.sf_index = sf_index
    state.sf_name = sf_name
    state.dac_index = dac_index
    state.dac_name = dac_name
    state.audio_device = audio_device
    state.dac_preview_index = state.dac_index
    reconnect_midi_to_fluidsynth(force_draw=False)
    mark_dirty(f"Active -> SF:{sf_name} / DAC:{dac_name}")


def midi_panic() -> None:
    # If a MIDI file is currently playing, stop that dedicated player first.
    # Otherwise panic can appear ineffective because the file player keeps sounding.
    if state.player_proc_kind == "midi_file":
        stop_player_only()
        time.sleep(0.05)
    restart_engine(state.sf_index, state.dac_index)
    restore_current_preset_after_engine_restart()
    if state.player_proc_kind is None:
        state.player_status = "Stopped"
        state.player_paused = False
        set_play_led("OFF")
    mark_dirty(f"MIDI Panic -> {state.current_preset_name}")


# =========================================================
# Player control
# =========================================================

def open_player_log():
    global player_log_handle
    os.makedirs(LOG_DIR, exist_ok=True)
    if player_log_handle:
        try:
            player_log_handle.close()
        except Exception:
            pass
    player_log_handle = open(PLAYER_LOG_PATH, "w", buffering=1)
    return player_log_handle


def stop_player_only() -> None:
    global player_proc
    if player_proc is None:
        return
    try:
        if player_proc.poll() is None:
            os.killpg(os.getpgid(player_proc.pid), signal.SIGTERM)
            time.sleep(0.3)
            if player_proc.poll() is None:
                os.killpg(os.getpgid(player_proc.pid), signal.SIGKILL)
    except Exception as exc:
        log(f"stop_player_only exception: {exc}")
    player_proc = None
    state.player_paused = False
    state.player_status = "Stopped"
    state.player_proc_kind = None
    state.player_origin_dir = None


def build_player_command(path: str) -> tuple[list[str] | None, str | None]:
    ext = Path(path).suffix.lower()
    audio = state.audio_device
    if ext in (".mid", ".midi"):
        sf_path = current_soundfont_path()
        return ([
            "fluidsynth", "-a", "alsa", "-i", "-n",
            "-o", f"audio.alsa.device={audio}",
            "-o", "synth.sample-rate=48000",
            "-o", "audio.period-size=256",
            "-o", "audio.periods=4",
            "-o", f"synth.gain={FLUID_GAIN}",
            "-o", "synth.cpu-cores=1",
            "-o", "synth.reverb.active=1",
            "-o", "synth.reverb.room-size=0.48",
            "-o", "synth.reverb.damp=0.22",
            "-o", "synth.reverb.width=0.75",
            "-o", "synth.reverb.level=0.30",
            "-o", "synth.chorus.active=0",
            sf_path,
            path,
        ], "midi_file")
    if ext in AUDIO_FILE_EXTS:
        mpv_audio = "alsa/default" if audio == "default" else f"alsa/{audio}"
        return ([
            "mpv",
            "--no-video",
            "--really-quiet",
            "--no-terminal",
            "--idle=no",
            f"--audio-device={mpv_audio}",
            path,
        ], "media")
    return None, None


def start_player(path: str) -> None:
    global player_proc
    cmd, kind = build_player_command(path)

    if not cmd:
        mark_dirty("Unsupported file")
        return

    stop_player_only()

    # Media and MIDI-file playback both take exclusive control of the audio device.
    stop_fluidsynth()

    log(f"PLAYER kind={kind} cmd={' '.join(cmd)}")
    log_handle = open_player_log()
    try:
        player_proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, preexec_fn=os.setsid, text=True)
    except FileNotFoundError:
        mark_dirty(f"Player missing: {cmd[0]}")
        if kind == "media":
            restart_engine(state.sf_index, state.dac_index)
        return
    except Exception as exc:
        mark_dirty(f"Player start failed: {exc}")
        if kind == "media":
            restart_engine(state.sf_index, state.dac_index)
        return

    state.player_path = path
    state.player_proc_kind = kind
    state.player_paused = False
    state.player_status = "Playing"
    state.player_stop_requested = False
    state.player_origin_dir = str(Path(path).parent)
    state.ui_mode = "player"
    invalidate_full_display()
    set_play_led("ON")
    mark_dirty(f"Play {Path(path).name}")


def toggle_pause_player() -> None:
    global player_proc
    if player_proc is None or player_proc.poll() is not None:
        mark_dirty("No active player")
        return
    try:
        pgid = os.getpgid(player_proc.pid)
        if state.player_paused:
            os.killpg(pgid, signal.SIGCONT)
            state.player_paused = False
            state.player_status = "Playing"
            set_play_led("ON")
            log(f"PLAYER resume kind={state.player_proc_kind} path={state.player_path}")
            mark_dirty("Resume")
        else:
            os.killpg(pgid, signal.SIGSTOP)
            state.player_paused = True
            state.player_status = "Paused"
            set_play_led("BLINK")
            log(f"PLAYER pause kind={state.player_proc_kind} path={state.player_path}")
            mark_dirty("Pause")
    except ProcessLookupError:
        mark_dirty("Player exited")
    except Exception as exc:
        mark_dirty(f"Pause failed: {exc}")


def poll_player_state() -> None:
    global player_proc
    if player_proc is None:
        return
    if player_proc.poll() is None:
        return

    finished_kind = state.player_proc_kind
    finished_path = state.player_path
    auto_advanced = False

    player_proc = None
    if finished_kind == "media":
        auto_advanced = try_auto_advance_media()
        if auto_advanced:
            return

    restart_engine(state.sf_index, state.dac_index)
    restore_current_preset_after_engine_restart()

    state.ui_mode = "player"
    invalidate_full_display()
    state.player_proc_kind = None
    state.player_paused = False
    state.player_status = "Stopped"
    state.player_origin_dir = str(Path(finished_path).parent) if finished_path else None
    set_play_led("OFF")
    finished_name = Path(finished_path).name if finished_path else "file"
    mark_dirty(f"Finished: {finished_name}")


# =========================================================
# Menu helpers
# =========================================================

def enter_submenu(key: str, return_mode: str | None = None) -> None:
    state.ui_mode = "submenu"
    invalidate_full_display()
    state.submenu_key = key
    state.submenu_return_mode = return_mode
    state.submenu_index = 0
    if key == "soundfont":
        state.submenu_index = state.sf_index
    elif key == "preset":
        state.submenu_index = state.preset_index
    elif key == "dac":
        refresh_dac_options(quiet=True)
        state.submenu_index = state.dac_index
    elif key == "midi":
        refresh_midi_options(quiet=True)
        current_modes = [mode for mode, _name in state.midi_options]
        try:
            state.submenu_index = current_modes.index(state.midi_mode)
        except ValueError:
            state.submenu_index = 0


def leave_submenu(event: str = "Back") -> None:
    target = state.submenu_return_mode or "main"
    if state.submenu_key == "soundfont":
        state.pending_resume_after_sf_apply = False
    if state.submenu_key == "preset":
        state.preset_entries = []
        state.preset_index = 0
        state.preset_sf_index = None
        state.preset_source_name = ""
    state.ui_mode = target
    invalidate_full_display()
    state.submenu_key = None
    state.submenu_index = 0
    state.submenu_return_mode = None
    mark_dirty(event)


def get_submenu_options() -> list[tuple[str, bool]]:
    key = state.submenu_key
    if key == "soundfont":
        return [(name, i == state.sf_index) for i, (_path, name) in enumerate(SOUNDFONTS)]
    if key == "preset_category":
        active_cat = categorize_preset(state.current_preset_bank, state.current_preset_program, state.current_preset_name)
        return [(cat, state.category_source_sf_index == state.sf_index and cat == active_cat) for cat in state.category_entries]
    if key == "preset":
        return [
            (
                f'{p["name"]} ({p["bank"]},{p["program"]})',
                state.preset_sf_index == state.sf_index
                and p["bank"] == state.current_preset_bank
                and p["program"] == state.current_preset_program,
            )
            for p in state.preset_entries
        ]
    if key == "dac":
        return [(name, i == state.dac_index) for i, (_dev, name) in enumerate(state.dac_options)]
    if key == "midi":
        return [(name, mode == state.midi_mode) for mode, name in state.midi_options]
    if key == "placeholder":
        return [("Not implemented yet", False)]
    return []


def apply_current_submenu_selection() -> None:
    key = state.submenu_key
    if key == "soundfont":
        resume_after_apply = state.pending_resume_after_sf_apply
        state.pending_resume_after_sf_apply = False
        apply_soundfont_with_default_preset(state.submenu_index)
        leave_submenu("SoundFont applied")
        if resume_after_apply:
            resume_selected_browser_file_after_sf_change()
        return
    if key == "preset":
        if not state.preset_entries:
            leave_submenu("No preset")
            return
        p = state.preset_entries[clamp_index(state.submenu_index, len(state.preset_entries))]
        target_sf_index = state.preset_sf_index if state.preset_sf_index is not None else state.sf_index
        if target_sf_index != state.sf_index:
            apply_soundfont_with_default_preset(target_sf_index)
        apply_preset(p["bank"], p["program"], p["name"])
        leave_submenu(f'Preset: {p["name"]}')
        return
    if key == "dac":
        if state.submenu_index != state.dac_index:
            restart_engine(state.sf_index, state.submenu_index)
        leave_submenu("DAC applied")
        return
    if key == "midi":
        if state.midi_options:
            selected_mode, selected_name = state.midi_options[state.submenu_index]
            previous_mode = state.midi_mode
            state.midi_mode = selected_mode
            state.midi_selected_name = selected_name
            if previous_mode == "uno2_bridge_seq" and selected_mode != "uno2_bridge_seq":
                stop_bridge()
            if selected_mode == "alsa_midi":
                # Keep remembering the user's chosen SEQ source for later reconnects.
                state.preferred_seq_port = state.selected_alsa_input
                state.preferred_seq_name = state.selected_alsa_input_name
            refresh_midi_options(quiet=True)
            restart_engine(state.sf_index, state.dac_index)
        leave_submenu(f"MIDI mode: {state.midi_display_text}")
        return
    leave_submenu("Not implemented yet")


def handle_main_select() -> None:
    if state.menu_index == 0:
        enter_submenu("soundfont")
    elif state.menu_index == 1:
        enter_submenu("dac")
    elif state.menu_index == 2:
        enter_submenu("midi")
    elif state.menu_index == 3:
        enter_file_browser()
    else:
        enter_submenu("placeholder")



# =========================================================
# Power menu
# =========================================================

def enter_power_menu() -> None:
    state.prev_ui_mode = state.ui_mode
    state.ui_mode = "power_menu"
    invalidate_full_display()
    state.power_menu_index = 0
    state.power_confirm_action = None
    state.power_confirm_index = 0
    mark_dirty("Power menu")


def cancel_power_menu() -> None:
    state.ui_mode = state.prev_ui_mode if state.prev_ui_mode else "main"
    invalidate_full_display()
    state.power_confirm_action = None
    state.power_confirm_index = 0
    mark_dirty("Power menu canceled")


def confirm_power_action(action: str) -> None:
    state.power_confirm_action = action
    state.power_confirm_index = 0
    mark_dirty(f"Confirm {action}")


def execute_power_action() -> None:
    action = state.power_confirm_action
    if not action:
        cancel_power_menu()
        return
    mark_dirty(f"{action} requested")
    try:
        if action == "Halt":
            subprocess.Popen(["sudo", "systemctl", "poweroff"])
        elif action == "Reboot":
            subprocess.Popen(["sudo", "systemctl", "reboot"])
    except Exception as exc:
        mark_dirty(f"Power action failed: {exc}")


# =========================================================
# Input handling
# =========================================================




def find_fluidsynth_mido_port_name() -> str | None:
    return find_fluidsynth_port()


def send_all_notes_off() -> None:
    restart_engine(state.sf_index, state.dac_index)
    restore_current_preset_after_engine_restart()


def stop_player_keep_player(event: str = "Stopped") -> None:
    state.player_stop_requested = True
    stop_player_only()
    restart_engine(state.sf_index, state.dac_index)
    restore_current_preset_after_engine_restart()
    state.ui_mode = "player"
    invalidate_full_display()
    state.player_status = "Stopped"
    state.player_paused = False
    state.player_proc_kind = None
    set_play_led("OFF")
    mark_dirty(event)


def return_player_to_browser(event: str = "Back to list") -> None:
    state.ui_mode = "file_browser"
    invalidate_full_display()
    state.player_status = "Stopped"
    state.player_paused = False
    state.player_proc_kind = None
    set_play_led("OFF")
    mark_dirty(event)


def handle_button_event(btn_value: str) -> None:
    btn = btn_value.strip().upper()
    if btn == "ENC_PUSH":
        btn = "SEL"

    if btn.endswith("_LP"):
        mark_dirty(btn.replace("_LP", " long"))

    # USB eject confirmation is global so it works regardless of where the
    # confirmation overlay was opened from.
    if state.usb_eject_confirm and state.ui_mode != "power_menu":
        if btn == "LEFT":
            state.usb_eject_confirm = False
            invalidate_full_display()
            mark_dirty("Eject canceled")
            return
        if btn == "SEL":
            pulse_button_activity()
            confirm_usb_eject()
            return
        mark_dirty("Confirm USB eject")
        return

    if btn == "SEL_LP":
        pulse_button_activity()
        enter_power_menu()
        return

    # Global LEFT long-press USB eject. It is allowed from any normal UI level,
    # but request_usb_eject() refuses while playback is actually running.
    if btn == "LEFT_LP" and state.ui_mode != "power_menu":
        pulse_button_activity()
        request_usb_eject()
        return

    # Global hidden panic button: keep SEL_LP reserved for power menu.
    # LEFT_LP is reserved for USB eject/unmount when playback is not running.
    if btn == "DOWN_LP" and state.ui_mode != "power_menu":
        pulse_button_activity()
        midi_panic()
        return

    if state.ui_mode == "power_menu":
        if state.power_confirm_action:
            if btn == "UP":
                state.power_confirm_index = (state.power_confirm_index - 1) % len(POWER_CONFIRM_ITEMS)
                mark_dirty(None); return
            if btn == "DOWN":
                state.power_confirm_index = (state.power_confirm_index + 1) % len(POWER_CONFIRM_ITEMS)
                mark_dirty(None); return
            if btn == "LEFT":
                state.power_confirm_action = None
                state.power_confirm_index = 0
                mark_dirty("Power confirm canceled"); return
            if btn == "SEL":
                pulse_button_activity()
                if POWER_CONFIRM_ITEMS[state.power_confirm_index] == "Yes":
                    execute_power_action()
                else:
                    state.power_confirm_action = None
                    state.power_confirm_index = 0
                    mark_dirty("Power confirm canceled")
                return
            mark_dirty(f"BTN ignored: {btn}")
            return

        if btn == "UP":
            pulse_button_activity()
            state.power_menu_index = (state.power_menu_index - 1) % len(POWER_MENU_ITEMS)
            mark_dirty(None); return
        if btn == "DOWN":
            pulse_button_activity()
            state.power_menu_index = (state.power_menu_index + 1) % len(POWER_MENU_ITEMS)
            mark_dirty(None); return
        if btn == "LEFT":
            pulse_button_activity()
            cancel_power_menu(); return
        if btn == "SEL":
            pulse_button_activity()
            item = POWER_MENU_ITEMS[state.power_menu_index]
            if item == "Cancel":
                cancel_power_menu()
            else:
                confirm_power_action(item)
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "player":
        log(f"PLAYER BTN={btn} kind={state.player_proc_kind} path={state.player_path}")
        if state.usb_eject_confirm:
            if btn == "LEFT":
                state.usb_eject_confirm = False
                invalidate_full_display()
                mark_dirty("Eject canceled")
                return
            if btn == "SEL":
                confirm_usb_eject()
                return
        if btn == "SEL":
            if state.player_status != "Stopped":
                if state.player_proc_kind == "midi":
                    replay_current_file()
                else:
                    toggle_pause_player()
            else:
                if state.player_path:
                    start_player(state.player_path)
                else:
                    mark_dirty("No file")
            return
        if btn == "LEFT":
            if state.player_status == "Stopped":
                return_player_to_browser("Back to list")
            else:
                stop_player_keep_player("Stopped")
            return
        if btn == "UP":
            play_adjacent(-1); return
        if btn == "DOWN":
            play_adjacent(+1); return
        if btn == "LEFT_LP":
            pulse_button_activity()
            request_usb_eject(); return
        if btn == "UP_LP":
            pulse_button_activity()
            if state.player_status == "Stopped" and state.player_path and Path(state.player_path).suffix.lower() in (".mid", ".midi"):
                return_player_to_browser("Back to list")
                state.pending_resume_after_sf_apply = True
                enter_submenu("soundfont", return_mode="file_browser")
                mark_dirty("SoundFont menu")
            else:
                mark_dirty("UP long only from stopped MIDI list state")
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "file_source":
        entries = get_file_source_entries()
        if state.usb_eject_confirm:
            if btn == "LEFT":
                state.usb_eject_confirm = False
                invalidate_full_display()
                mark_dirty("Eject canceled")
                return
            if btn == "SEL":
                confirm_usb_eject()
                return
        if btn == "UP":
            pulse_button_activity()
            if state.browser_index > 0:
                state.browser_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.browser_index < len(entries) - 1:
                state.browser_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last item")
            return
        if btn == "SEL":
            pulse_button_activity()
            file_source_select(); return
        if btn == "LEFT":
            pulse_button_activity()
            state.ui_mode = "main"
            state.browser_index = 0
            invalidate_full_display()
            mark_dirty("Back to main"); return
        if btn == "LEFT_LP":
            pulse_button_activity()
            request_usb_eject(); return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "file_browser":
        if state.usb_eject_confirm:
            if btn == "LEFT":
                state.usb_eject_confirm = False
                invalidate_full_display()
                mark_dirty("Eject canceled"); return
            if btn == "SEL":
                confirm_usb_eject(); return
        if btn == "UP":
            pulse_button_activity()
            if state.browser_entries and state.browser_index > 0:
                state.browser_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.browser_entries and state.browser_index < len(state.browser_entries) - 1:
                state.browser_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last item")
            return
        if btn == "SEL":
            pulse_button_activity()
            browser_select(); return
        if btn == "LEFT":
            pulse_button_activity()
            browser_go_parent(); return
        if btn == "LEFT_LP":
            pulse_button_activity()
            request_usb_eject(); return
        if btn == "UP_LP":
            pulse_button_activity()
            if state.browser_entries:
                idx = clamp_index(state.browser_index, len(state.browser_entries))
                item = state.browser_entries[idx]
                if item.get("type") == "file" and Path(item.get("path", "")).suffix.lower() in (".mid", ".midi"):
                    state.pending_resume_after_sf_apply = True
                    enter_submenu("soundfont", return_mode="file_browser")
                    mark_dirty("SoundFont menu")
                else:
                    mark_dirty("UP long only for selected MIDI file")
            else:
                mark_dirty("UP long unavailable here")
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "soundfont":
        options = get_submenu_options()
        if btn == "UP":
            pulse_button_activity()
            state.submenu_index = (state.submenu_index - 1) % max(1, len(options))
            total, drums = soundfont_preset_counts(state.submenu_index)
            sf_name = SOUNDFONTS[state.submenu_index][1]
            mark_dirty(f"{sf_name}: {total} presets, {drums} drums" if total else sf_name)
            return
        if btn == "DOWN":
            pulse_button_activity()
            state.submenu_index = (state.submenu_index + 1) % max(1, len(options))
            total, drums = soundfont_preset_counts(state.submenu_index)
            sf_name = SOUNDFONTS[state.submenu_index][1]
            mark_dirty(f"{sf_name}: {total} presets, {drums} drums" if total else sf_name)
            return
        if btn == "SEL":
            pulse_button_activity()
            apply_soundfont_with_default_preset(state.submenu_index)
            mark_dirty(f"Active -> {state.sf_name}/{state.current_preset_name}")
            return
        if btn == "RIGHT":
            pulse_button_activity()
            enter_preset_submenu(state.submenu_index)
            return
        if btn == "LEFT":
            pulse_button_activity()
            leave_submenu("Canceled")
            return
        if btn == "UP_LP":
            pulse_button_activity()
            mark_dirty("UP long unavailable here")
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "preset_category":
        options = get_submenu_options()
        if btn == "UP":
            pulse_button_activity()
            state.submenu_index = (state.submenu_index - 1) % max(1, len(options))
            state.category_index = state.submenu_index
            mark_dirty(state.category_entries[state.category_index] if state.category_entries else "Category")
            return
        if btn == "DOWN":
            pulse_button_activity()
            state.submenu_index = (state.submenu_index + 1) % max(1, len(options))
            state.category_index = state.submenu_index
            mark_dirty(state.category_entries[state.category_index] if state.category_entries else "Category")
            return
        if btn in {"SEL", "RIGHT"}:
            pulse_button_activity()
            enter_preset_list_from_category(state.submenu_index)
            return
        if btn == "LEFT":
            pulse_button_activity()
            return_to_soundfont_submenu()
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "preset":
        options = get_submenu_options()
        if btn == "UP":
            pulse_button_activity()
            preview_preset_at_index((state.submenu_index - 1) % max(1, len(options)))
            return
        if btn == "DOWN":
            pulse_button_activity()
            preview_preset_at_index((state.submenu_index + 1) % max(1, len(options)))
            return
        if btn == "SEL":
            pulse_button_activity()
            if state.preset_entries:
                commit_current_preview()
                p = state.preset_entries[clamp_index(state.submenu_index, len(state.preset_entries))]
                leave_submenu(f'Preset: {p["name"]}')
            else:
                mark_dirty("No preset")
            return
        if btn == "LEFT":
            pulse_button_activity()
            cancel_preset_preview_and_restore()
            return_to_category_submenu()
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if btn == "UP":
        pulse_button_activity()
        if state.ui_mode == "main":
            state.menu_index = (state.menu_index - 1) % len(MAIN_MENU)
            mark_dirty(None)
        else:
            options = get_submenu_options()
            state.submenu_index = (state.submenu_index - 1) % max(1, len(options))
            mark_dirty(None)
        return

    if btn == "DOWN":
        pulse_button_activity()
        if state.ui_mode == "main":
            state.menu_index = (state.menu_index + 1) % len(MAIN_MENU)
            mark_dirty(None)
        else:
            options = get_submenu_options()
            state.submenu_index = (state.submenu_index + 1) % max(1, len(options))
            mark_dirty(None)
        return

    if btn == "SEL":
        pulse_button_activity()
        if state.ui_mode == "main":
            handle_main_select()
        else:
            apply_current_submenu_selection()
        return

    if btn == "LEFT":
        pulse_button_activity()
        if state.ui_mode == "submenu":
            leave_submenu("Canceled")
        else:
            mark_dirty("Main screen")
        return

    if btn == "RIGHT":
        pulse_button_activity()
        if state.ui_mode == "main":
            handle_main_select()
        else:
            mark_dirty("RIGHT unused")
        return

    if btn == "UP_LP":
        pulse_button_activity()
        mark_dirty("UP long unavailable here")
        return

    mark_dirty(f"BTN ignored: {btn}")


# =========================================================
# Serial and hotplug
# =========================================================

def open_serial() -> serial.Serial:
    port_path = Path(SERIAL_PORT)
    if not port_path.exists():
        raise FileNotFoundError(f"Serial port not found: {SERIAL_PORT}")
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=SERIAL_TIMEOUT)
    time.sleep(2.0)
    ser.reset_input_buffer()
    return ser


def serial_reader() -> None:
    global serial_handle, last_serial_hb_time, serial_read_error_count, serial_write_error_count
    ser = None
    while state.running:
        try:
            if ser is None:
                log(f"Opening serial: {SERIAL_PORT}")
                ser = open_serial()
                serial_read_error_count = 0
                serial_write_error_count = 0
                with serial_lock:
                    serial_handle = ser
                send_serial_line("HELLO")
                time.sleep(0.05)
                send_serial_line("HB")
                time.sleep(0.02)
                send_serial_line("PLAY:OFF")
                last_serial_hb_time = time.time()
                state.serial_input_ignore_until = time.time() + SERIAL_INPUT_IGNORE_AFTER_OPEN_SEC
                mark_dirty("Serial connected")

            raw = ser.readline()

            # A successful read call, even with timeout/empty bytes, should reset the
            # consecutive read error counter. Timeout is normal and must not cause reconnect.
            serial_read_error_count = 0

            if not raw:
                continue
            try:
                line = raw.decode(errors="ignore").strip()
            except Exception:
                continue
            if line:
                event_q.put(line)

        except Exception as exc:
            serial_read_error_count += 1
            mark_dirty(f"Serial err {serial_read_error_count}/{SERIAL_MAX_CONSEC_READ_ERRORS}")
            log(f"serial read failed ({serial_read_error_count}/{SERIAL_MAX_CONSEC_READ_ERRORS}): {exc}")

            if serial_read_error_count >= SERIAL_MAX_CONSEC_READ_ERRORS:
                log("serial read error threshold reached; forcing reconnect")
                try:
                    if ser:
                        ser.close()
                except Exception:
                    pass
                with serial_lock:
                    if serial_handle is ser:
                        serial_handle = None
                ser = None
                serial_read_error_count = 0
                serial_write_error_count = 0
                time.sleep(SERIAL_REOPEN_COOLDOWN_SEC)
            else:
                time.sleep(0.2)


def periodic_bridge_watchdog() -> None:
    now = time.time()
    if now - state.last_bridge_poll_time < BRIDGE_WATCHDOG_INTERVAL_SEC:
        return
    state.last_bridge_poll_time = now
    if state.midi_mode != "uno2_bridge_seq":
        return
    was_running = state.bridge_running
    state.bridge_running = state.bridge_proc is not None and state.bridge_proc.poll() is None
    if not state.bridge_running:
        if start_bridge():
            time.sleep(0.5)
            reconnect_midi_to_fluidsynth(force_draw=False)
            mark_dirty("Bridge restarted")
        elif was_running:
            mark_dirty("Bridge stopped")


def periodic_device_poll() -> None:
    now = time.time()
    if now - state.last_device_poll_time < DEVICE_POLL_INTERVAL_SEC:
        return
    state.last_device_poll_time = now
    dac_changed = refresh_dac_options(quiet=True)
    old_connected = state.midi_connected
    if state.midi_mode == "usb_direct_raw":
        prev_raw_port = state.midi_src_port
        prev_raw_name = state.midi_src_name
        prev_display = state.midi_display_text
        selected_port, selected_name = choose_raw_midi_input()
        state.midi_src_name = selected_name or "No raw MIDI"
        state.midi_src_port = selected_port or "-"
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()

        # If a keyboard appeared after startup, rebuild the engine so alsa_raw binds to it.
        if fluid_proc is not None and fluid_proc.poll() is None and selected_port and prev_raw_port in {"-", "", None}:
            mark_dirty(f"RAW MIDI detected: {selected_name or selected_port}")
            restart_engine(state.sf_index, state.dac_index)
            restore_current_preset_after_engine_restart()
            selected_port, selected_name = choose_raw_midi_input()
            state.midi_src_name = selected_name or "No raw MIDI"
            state.midi_src_port = selected_port or "-"
            state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
            refresh_midi_display_text()
            mark_dirty(f"MIDI {state.midi_display_text}")
            return

        if (
            state.midi_src_port != prev_raw_port
            or state.midi_src_name != prev_raw_name
            or state.midi_display_text != prev_display
        ):
            mark_dirty(f"MIDI {state.midi_display_text}")
    elif state.midi_mode == "uno2_bridge_seq":
        state.bridge_running = state.bridge_proc is not None and state.bridge_proc.poll() is None
        state.midi_connected = state.bridge_running and (fluid_proc is not None and fluid_proc.poll() is None)
        if state.midi_connected and state.fluid_dst_port == "-":
            reconnect_midi_to_fluidsynth(force_draw=False)
    else:
        prev_seq_connected = state.midi_connected
        prev_seq_port = state.selected_alsa_input
        selected_port, selected_name = choose_alsa_seq_input()
        state.selected_alsa_input = selected_port
        state.selected_alsa_input_name = selected_name
        state.midi_src_name = selected_name or 'alsa sequencer'
        state.midi_src_port = selected_port or '-'
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)

        # If user chose SEQ mode before and the remembered/selected port disappeared,
        # stay in waiting mode rather than silently switching behavior.
        if not selected_port:
            refresh_midi_display_text()
            if prev_seq_connected:
                mark_dirty("SEQ disconnected")
            return

        # If the SEQ source reappeared after being absent, try reconnect immediately.
        if fluid_proc is not None and fluid_proc.poll() is None and (not prev_seq_connected or prev_seq_port != selected_port):
            connect_selected_alsa_to_fluidsynth()
            refresh_midi_display_text()
            mark_dirty(f"MIDI {state.midi_display_text}")
            return
    if state.ui_mode == "submenu" and state.submenu_key == "dac":
        state.submenu_index = clamp_index(state.submenu_index, len(state.dac_options))
    if state.ui_mode == "file_browser":
        keep = None
        if state.browser_entries and state.browser_index < len(state.browser_entries):
            keep = state.browser_entries[state.browser_index]["name"]
        refresh_browser_entries(keep_name=keep)
    if dac_changed:
        mark_dirty("DAC list updated")
    elif old_connected != state.midi_connected:
        mark_dirty(f"MIDI {state.midi_display_text}" if state.midi_connected else "Engine stopped")




def periodic_usb_poll() -> None:
    now = time.time()
    if now - state.last_usb_poll_time < USB_STATUS_POLL_INTERVAL_SEC:
        return
    state.last_usb_poll_time = now

    mounted_now = is_mountpoint_active(USB_MOUNT_POINT)
    if mounted_now == state.usb_mounted:
        return

    state.usb_mounted = mounted_now

    if state.ui_mode == "file_browser":
        keep = None
        if state.browser_entries and state.browser_index < len(state.browser_entries):
            keep = state.browser_entries[state.browser_index]["name"]
        refresh_browser_entries(keep_name=keep)

    if mounted_now:
        state.browser_root = find_file_root()
        if state.ui_mode != "player":
            enter_file_source(default_usb=True)
        mark_dirty("USB mounted")
    else:
        if normalize_path(state.browser_path).startswith(normalize_path(USB_MOUNT_POINT)):
            enter_file_source(default_usb=False)
        elif state.ui_mode == "file_source":
            state.browser_index = 0
            invalidate_full_display()
        mark_dirty("USB removed")


def request_usb_eject() -> None:
    if state.player_status == "Playing":
        mark_dirty("Stop or pause first")
        return
    if not state.usb_mounted:
        state.usb_eject_confirm = False
        mark_dirty("USB not mounted")
        return
    state.usb_eject_confirm = True
    invalidate_full_display()
    mark_dirty("USB eject confirm")


def confirm_usb_eject() -> None:
    if not state.usb_mounted:
        state.usb_eject_confirm = False
        invalidate_full_display()
        mark_dirty("USB not mounted")
        return

    if state.player_status in ("Playing", "Paused"):
        stop_player_only()
        restart_engine(state.sf_index, state.dac_index)
        restore_current_preset_after_engine_restart()
        state.player_status = "Stopped"
        state.player_paused = False
        state.player_proc_kind = None
        set_play_led("OFF")

    run_cmd(["sudo", "-n", "/usr/bin/sync"])
    time.sleep(0.2)

    code, out = run_cmd(USB_EJECT_CMD)
    time.sleep(0.3)
    still_mounted = is_mountpoint_active(USB_MOUNT_POINT)

    state.usb_eject_confirm = False

    if code == 0 and not still_mounted:
        state.usb_mounted = False

        if normalize_path(state.browser_path).startswith(normalize_path(USB_MOUNT_POINT)):
            state.browser_path = resolve_file_root()

        refresh_browser_entries()
        state.browser_index = 0

        state.ui_mode = "main"
        state.player_path = None
        state.player_origin_dir = None
        state.player_status = "Stopped"
        state.player_paused = False
        state.player_proc_kind = None

        invalidate_full_display()
        mark_dirty("USB ejected")
        return

    invalidate_full_display()
    if still_mounted:
        mark_dirty("USB busy / unmount failed")
    else:
        mark_dirty(f"USB eject failed: {shorten_text(out, 20)}")


# =========================================================
# Event parsing and render helpers
# =========================================================

def handle_serial_line(line: str) -> None:
    if line == "UNO_READY":
        mark_dirty("UNO Ready")
        return
    if ":" not in line:
        mark_dirty(f"Unknown RAW: {line}")
        return
    msg_type, value = line.split(":", 1)
    msg_type = msg_type.strip().upper()
    value = value.strip()

    # UNO-1 can emit transient analog-keypad/encoder states while resetting or
    # immediately after USB serial reconnect. Treat that short window as a
    # boot-settling period so playback is not accidentally changed.
    if time.time() < state.serial_input_ignore_until and msg_type in {"BTN", "ENC", "POT", "A2", "A0", "ACCEL"}:
        return

    if msg_type == "BTN":
        handle_button_event(value)
        return
    if msg_type in ("POT", "A2"):
        handle_pot_value(value)
        return
    if msg_type == "ENC":
        handle_encoder_value(value)
        return
    if msg_type == "A0":
        return
    if msg_type == "ACCEL":
        mark_dirty(f"Accel -> P{value}")
        return
    mark_dirty(f"Unknown line: {line}")




def handle_encoder_value(value: str) -> None:
    global last_enc_time

    now = time.time()
    if now - last_enc_time < 0.02:   # 20ms debounce
        return
    last_enc_time = now

    try:
        step = int(value)
    except ValueError:
        return
    if step == 0:
        return

    # Encoder rotation is mapped to UP/DOWN navigation. While a file is playing,
    # ignore it explicitly so a reconnect glitch or accidental turn cannot jump tracks.
    if state.ui_mode == "player" and state.player_status == "Playing":
        mark_dirty("Encoder ignored while playing")
        return

    event_name = "DOWN" if step > 0 else "UP"
    for _ in range(abs(step)):
        handle_button_event(event_name)


def maybe_render(force: bool = False) -> None:
    if not state.dirty:
        return
    if force:
        display.render()
        return
    if time.time() - state.last_render_time < RENDER_MIN_INTERVAL:
        return
    display.render()


def request_exit(signum=None, frame=None) -> None:
    set_play_led("OFF")
    state.running = False
    mark_dirty("Exit")


# =========================================================
# Main
# =========================================================

def main() -> None:
    signal.signal(signal.SIGINT, request_exit)
    signal.signal(signal.SIGTERM, request_exit)

    os.makedirs(LOG_DIR, exist_ok=True)

    state.browser_root = find_file_root()
    state.browser_path = state.browser_root
    Path(USB_MOUNT_POINT).mkdir(parents=True, exist_ok=True)
    state.usb_mounted = is_mountpoint_active(USB_MOUNT_POINT)

    if FIX_VOLUME_AT_100:
        force_volume_100()
    else:
        state.volume_percent = 100

    refresh_dac_options(quiet=True)
    refresh_midi_options(quiet=True)

    sf_path, sf_name = SOUNDFONTS[state.sf_index]
    state.sf_name = sf_name
    state.audio_device = DEFAULT_DAC[0]

    initial_presets = load_presets_for_sf2(state.sf_index)
    initial_default_preset = choose_default_preset(initial_presets)
    if initial_default_preset:
        state.current_preset_bank = initial_default_preset["bank"]
        state.current_preset_program = initial_default_preset["program"]
        state.current_preset_name = initial_default_preset["name"]

    ok = start_fluidsynth(sf_path, state.audio_device)
    if ok:
        refresh_midi_options(quiet=True)
        state.midi_connected = True
        apply_preset(state.current_preset_bank, state.current_preset_program, state.current_preset_name)
    else:
        mark_dirty("Audio engine start failed")

    periodic_system_status_poll()
    mark_dirty("Ready")
    maybe_render(force=True)

    th = threading.Thread(target=serial_reader, daemon=True)
    th.start()

    global midi_activity_thread_handle
    midi_activity_thread_handle = threading.Thread(target=midi_activity_monitor_thread, daemon=True)
    midi_activity_thread_handle.start()

    try:
        while state.running:
            did_event = False

            try:
                line = event_q.get(timeout=0.01)
                handle_serial_line(line)
                did_event = True
            except queue.Empty:
                pass

            if did_event:
                while True:
                    try:
                        line = event_q.get_nowait()
                        handle_serial_line(line)
                    except queue.Empty:
                        break
                periodic_serial_heartbeat()
                maybe_render(force=True)
                continue

            periodic_device_poll()
            periodic_usb_poll()
            periodic_bridge_watchdog()
            periodic_system_status_poll()
            periodic_serial_heartbeat()
            poll_player_state()
            maybe_render()
    finally:
        stop_player_only()
        stop_midi_activity_monitor()
        stop_fluidsynth()
        stop_bridge()
        global fluid_log_handle, player_log_handle
        if fluid_log_handle:
            try:
                fluid_log_handle.close()
            except Exception:
                pass
        if player_log_handle:
            try:
                player_log_handle.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
