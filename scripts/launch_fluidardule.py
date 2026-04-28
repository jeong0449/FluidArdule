#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# =========================================================
# Fluid Ardule main UI/runtime script
# Version is defined by SCRIPT_VERSION below.
# Detailed change history is tracked in Git.
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

SCRIPT_VERSION = "v20260428e"

SERIAL_PORT = "/dev/serial/by-id/usb-Arduino__www.arduino.cc__Arduino_Uno_12724551266415469650-if00"
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 0.1
SERIAL_INPUT_IGNORE_AFTER_OPEN_SEC = 1.5

SOUNDFONTS = [
    ("/home/pi/sf2/SalC5Light2.sf2", "SalC5"),
    ("/home/pi/sf2/FluidR3_GM.sf2", "FluidR3"),
    ("/home/pi/sf2/GeneralUser_GS.sf2", "GUserGS"),
    # Yoshimi is exposed through the same SoundFont menu as a synth-engine source.
    # The JSON file should follow Fluid Ardule instrument-list v2 and contain
    # Yoshimi .xiz entries grouped by bank_name.
    ("/home/pi/sf2/yoshimi.patches.json", "Yoshimi"),
]

YOSHIMI_EXECUTABLE = "yoshimi"
YOSHIMI_DEFAULT_ROOT = "/usr/share/yoshimi/banks"
YOSHIMI_PREVIEW_DEBOUNCE_SEC = 0.35

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
YOSHIMI_LOG_PATH = f"{LOG_DIR}/yoshimi.log"
AMIXER_CONTROL = "PCM"
FIX_VOLUME_AT_100 = True
POT_VOLUME_ENABLED = True
DEVICE_POLL_INTERVAL_SEC = 3.0
MIDI_RECONNECT_STABLE_SEC = 1.5
SERIAL_HEARTBEAT_INTERVAL_SEC = 1.0
SERIAL_LINK_STALE_SEC = 3.0
LED_PULSE_COOLDOWN_SEC = 0.05
POT_LED_PULSE_INTERVAL_SEC = 0.07
POT_VOLUME_PERCENT_THRESHOLD = 3
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
MODIFIED_VALUE = (255, 220, 90)
# Minimum interval between TFT renders (in seconds).
# Frequent screen updates can interfere with real-time audio on Raspberry Pi,
# causing jitter or glitches during MIDI playback.
# Increasing this value improves audio stability at the cost of UI responsiveness.
RENDER_MIN_INTERVAL = 0.15
# During early boot, the framebuffer can be overwritten by late-starting
# splash/console components after the Python UI has already drawn Home.
# Force occasional full redraws only during this short boot window so the
# screen recovers from any external overwrite without increasing steady-state
# TFT update load.
BOOT_FULL_REDRAW_SEC = 8.0
BOOT_FULL_REDRAW_INTERVAL_SEC = 0.75
ROTATE_180 = True

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]

MAIN_MENU = [
    "Sound Source",
    "File Player",
    "Controls",
    "MIDI Mode",
    "DAC",
    "Extension",
]

QUICK_MENU_ITEMS = [
    "Resume",
    "Now Playing",
    "Home",
    "Sound Source",
    "USB Eject",
    "Power...",
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

# Sound Edit is a volatile, non-saving performance edit page.
# CC7 Volume is intentionally excluded because the hardware pot controls volume.
SOUND_EDIT_PARAMS = [
    {"label": "Expression", "name": "Expression", "cc": 11, "default": 127},
    {"label": "Modulation", "name": "Modulation", "cc": 1,  "default": 0},
    {"label": "Reverb",     "name": "Reverb",     "cc": 91, "default": 40},
    {"label": "Chorus",     "name": "Chorus",     "cc": 93, "default": 0},
    {"label": "Brightness", "name": "Brightness", "cc": 74, "default": 64},
    {"label": "Resonance",  "name": "Resonance",  "cc": 71, "default": 64},
    {"label": "Pan",        "name": "Pan",        "cc": 10, "default": 64},
    {"label": "Attack",     "name": "Attack",     "cc": 73, "default": 64},
]
SOUND_EDIT_COLS = 2
SOUND_EDIT_MIN = 0
SOUND_EDIT_MAX = 127
SOUND_EDIT_STEP = 1
# UNO-1 firmware owns low-level encoder acceleration and reports its profile via ACCEL.
# Python interprets encoder input differently depending on context:
#   - menu navigation: use direction only, always move one item per detent event
#   - Sound Edit value editing: use the signed ENC magnitude from UNO and scale it
#     non-linearly according to the current UNO acceleration profile
SOUND_EDIT_SEND_ALL_CHANNELS = True
# Keep the debug logging hooks in the code, but leave them disabled for normal use.
# Set this to True temporarily when verifying CC transmission with journalctl.
SOUND_EDIT_CC_DEBUG = False
ENCODER_ACCEL_DEFAULT_PROFILE = 2
ENCODER_ACCEL_OPTIONS = {
    1: "P1 Fine",
    2: "P2 Normal",
    3: "P3 Fast",
}
# Navigation jitter guard for the rotary encoder.
# UNO-1 can occasionally emit a single opposite-direction ENC event when the
# knob is turned slowly near a detent. For menu navigation, that one event is
# very visible as a wrong one-row jump, so Python ignores only a very short
# opposite-direction pulse. Sound Edit value editing is not filtered here.
ENC_NAV_REVERSAL_GUARD_SEC = 0.12
POT_MODE_DEFAULT = "VOL"
POT_MODE_FOOTER_HOLD_SEC = 1.2
ACCEL_FOOTER_HOLD_SEC = 1.2
# Soft takeover threshold for returning the physical pot to volume control.
# When POT mode switches back from PARAM to VOL, the volume is not updated
# until the physical pot position comes close to the current logical volume.
# This prevents abrupt volume jumps caused by the pot angle being reused for CC editing.
POT_VOLUME_PICKUP_THRESHOLD = 3


def default_sound_edit_values() -> dict[int, int]:
    return {int(item["cc"]): int(item["default"]) for item in SOUND_EDIT_PARAMS}


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
    current_engine: str = "fluidsynth"
    current_instrument_path: str | None = None

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
    force_full_redraw_until: float = 0.0
    last_forced_full_redraw_time: float = 0.0

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
    preview_restore_engine: str = "fluidsynth"
    preview_restore_instrument_path: str | None = None
    pending_yoshimi_preview_index: int | None = None
    pending_yoshimi_preview_due: float = 0.0

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

    quick_menu_index: int = 0
    quick_resume_snapshot: dict | None = None

    sound_edit_index: int = 0
    sound_edit_values: dict[int, int] = field(default_factory=default_sound_edit_values)
    sound_edit_a_values: dict[int, int] = field(default_factory=default_sound_edit_values)
    sound_edit_active_side: str = "B"
    sound_edit_modified: set[int] = field(default_factory=set)
    sound_edit_last_adjust_time: float = 0.0
    encoder_accel_profile: int = ENCODER_ACCEL_DEFAULT_PROFILE
    encoder_accel_pending_profile: int = ENCODER_ACCEL_DEFAULT_PROFILE
    last_nav_enc_dir: int = 0
    last_nav_enc_time: float = 0.0
    pot_mode: str = POT_MODE_DEFAULT
    pot_volume_captured: bool = True
    transient_footer_text: str = ""
    transient_footer_until: float = 0.0

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
yoshimi_log_handle = None
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


def show_footer_message(text: str, hold_sec: float = 1.2) -> None:
    """Temporarily show a high-priority status message in the footer.

    Used for short-lived hardware mode changes such as encoder acceleration
    profile and POT mode. After the hold time expires, the normal footer
    content automatically returns on the next render tick.
    """
    state.transient_footer_text = text
    state.transient_footer_until = time.time() + float(hold_sec)
    mark_dirty(text)


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

    # B: POT keeps volume as the default, but LEFT long can temporarily switch
    # it to PARAM mode. In PARAM mode, the full physical travel maps directly
    # to the currently highlighted Sound Edit CC value. No extra on-screen hint
    # is needed because the highlight already defines the target parameter.
    if state.pot_mode == "PARAM" and state.ui_mode == "sound_edit":
        value = clamp_cc_value(int(round(raw * SOUND_EDIT_MAX / 1023)))
        set_sound_edit_current_value_from_pot(value)
        maybe_pulse_pot_led(int(round(raw * 100 / 1023)))
        return

    percent = int(round(raw * 100 / 1023))

    # Soft takeover for volume mode. If the pot has been used as a parameter
    # controller, its physical angle may no longer match the current volume.
    # When returning to VOL mode, wait until the pot is moved near the existing
    # logical volume before applying it again. This avoids sudden volume jumps.
    if not state.pot_volume_captured:
        if abs(percent - state.volume_percent) <= POT_VOLUME_PICKUP_THRESHOLD:
            state.pot_volume_captured = True
        else:
            maybe_pulse_pot_led(percent)
            return

    if abs(percent - state.volume_percent) < POT_VOLUME_PERCENT_THRESHOLD:
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


def notify_uno_power_state(action: str) -> None:
    """Notify UNO-1 before a UI-initiated power action.

    This is intentionally used only from the Fluid Ardule power menu.
    SSH/systemd/manual poweroff paths are not treated as safe-unplug events
    on UNO-1 because they may be indistinguishable from cable removal or
    firmware-upload replug scenarios.
    """
    action = action.strip().upper()
    if action == "HALT":
        send_serial_line("PWR:SHUTDOWN")
    elif action == "REBOOT":
        send_serial_line("PWR:REBOOT")


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
            "main_value_5": self._main_menu_value(5),
            "transient_footer_text": state.transient_footer_text,
            "transient_footer_until_active": time.time() < state.transient_footer_until,
        }

    def _footer_changed(self, prev: dict | None) -> bool:
        if prev is None:
            return True
        keys = ("last_event", "cpu_load_text", "cpu_temp_text", "midi_display_text", "midi_connected", "usb_mounted", "transient_footer_text")
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
            top_y=56,
            row_h=38,
            bottom_y=self.height - 50,
            list_bbox=(12, 50, self.width - 12, self.height - 48),
            row_bbox_func=lambda vis: (20, 56 + vis * 38, self.width - 20, 104 + vis * 38 + 38),
            redraw_current_view=lambda draw: (
                draw.rounded_rectangle((12, 50, self.width - 12, self.height - 48), radius=12, fill=BOX_BG),
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
            top_y=70,
            row_h=36,
            bottom_y=self.height - 50,
            list_bbox=(12, 64, self.width - 12, self.height - 48),
            row_bbox_func=lambda vis: (20, 70 + vis * 36, self.width - 20, 118 + vis * 36 + 36),
            redraw_current_view=lambda draw: (
                draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG),
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
        # Show the Fluid Ardule identity header only on the Home/Main screen.
        # Other screens use their own contextual title to reduce visual noise.
        if state.ui_mode == "main":
            self._draw_header(draw)
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
        elif state.ui_mode == "quick_menu":
            self._draw_quick_menu(draw)
        elif state.ui_mode == "sound_edit":
            self._draw_sound_edit(draw)
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
        label = MAIN_MENU[idx] if 0 <= idx < len(MAIN_MENU) else ""
        if label == "Sound Source":
            return f"{state.sf_name}/{state.current_preset_name}"
        if label == "File Player":
            return Path(state.player_path).name if state.player_path else "Browse"
        if label == "Controls":
            return "Sound Edit"
        if label == "MIDI Mode":
            return state.midi_display_text
        if label == "DAC":
            return state.dac_name
        if label == "Extension":
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
        draw.text((16, 10), title, font=self.font_title, fill=ACCENT)
        if info:
            bbox = draw.textbbox((0, 0), info, font=self.font_small)
            draw.text(
                (self.width - 16 - (bbox[2] - bbox[0]), 18),
                info,
                font=self.font_small,
                fill=ACCENT,
            )

    def _draw_submenu_box(self, draw):
        draw.rounded_rectangle(
            (12, 50, self.width - 12, self.height - 48),
            radius=12,
            fill=BOX_BG,
        )

    def _draw_submenu_generic_rows(self, draw, options):
        self._draw_scrolled_rows(
            draw,
            options,
            state.submenu_index,
            56,
            38,
            self.height - 50,
            show_current_marks=True,
        )

    def _draw_submenu_soundfont_rows(self, draw, options):
        visible_rows = max(1, (self.height - 50 - 56) // 38)
        start_idx = max(0, state.submenu_index - visible_rows + 1) if state.submenu_index >= visible_rows else 0

        for visible_row, idx in enumerate(range(start_idx, min(len(options), start_idx + visible_rows))):
            top = 56 + visible_row * 38
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
                    # Show the navigation hint only on the highlighted row.
                    # Single-instrument sources do not need a "go deeper" hint.
                    value += " > Press Right" if idx == state.submenu_index else " >"
                value_fill = ACCENT if idx != state.submenu_index else FG
                draw_right_vcentered_text(draw, self.width - 28, top, 38, value, self.font_small, value_fill)

    def _draw_submenu(self, draw):
        title_map = {
            "soundfont": "Sound Source",
            "preset_category": "Preset Categories",
            "preset": "Select Preset",
            "dac": "Select DAC",
            "midi": "MIDI Mode",
            "controls": "Sound Edit",
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
        draw.text((16, 10), "File Player", font=self.font_title, fill=ACCENT)
        sf_text = state.sf_name
        usb_text = usb_status_text()
        right_text = f"{usb_text}  {sf_text}" if sf_text else usb_text
        sf_bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (sf_bbox[2]-sf_bbox[0]), 18), right_text, font=self.font_small, fill=ACCENT)
        draw.text((18, 42), "Select source", font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = [entry["display"] for entry in get_file_source_entries()] or ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.browser_index, 70, 40, self.height - 50)

    def _draw_file_browser(self, draw):
        draw.text((16, 10), "File Player", font=self.font_title, fill=ACCENT)
        sf_text = state.sf_name
        usb_text = usb_status_text()
        right_text = f"{usb_text}  {sf_text}" if sf_text else usb_text
        sf_bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (sf_bbox[2]-sf_bbox[0]), 18), right_text, font=self.font_small, fill=ACCENT)
        path_text = state.browser_path
        if len(path_text) > 42:
            path_text = "..." + path_text[-39:]
        draw.text((18, 42), path_text, font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = [entry["display"] for entry in state.browser_entries] or ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.browser_index, 70, 36, self.height - 50)

    def _draw_player(self, draw):
        draw.text((16, 10), "Now Playing", font=self.font_title, fill=ACCENT)
        sf_text = state.sf_name
        usb_text = usb_status_text()
        right_text = f"{usb_text}  {sf_text}" if sf_text else usb_text
        sf_bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (sf_bbox[2]-sf_bbox[0]), 18), right_text, font=self.font_small, fill=ACCENT)
        name = Path(state.player_path).name if state.player_path else "No file"
        kind = state.player_proc_kind.upper() if state.player_proc_kind else "-"
        draw.text((18, 44), f"{kind}  {state.player_status}", font=self.font_small, fill=DIM)

        draw.rounded_rectangle((12, 70, self.width - 12, 122), radius=12, fill=BOX_BG)
        one_line_name = ellipsize_text(name, self.font_menu, self.width - 48)
        draw.text((24, 83), one_line_name, font=self.font_menu, fill=FG)

        draw.rounded_rectangle((12, 132, self.width - 12, 286), radius=12, fill=BOX_BG)

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
            {"name": "LEFT",  "label": left_label, "x": 18,  "y": 164, "w": 74,  "h": 46},
            {"name": "UP",    "label": up_label,   "x": 122, "y": 138, "w": 96,  "h": 42},
            {"name": "DOWN",  "label": down_label, "x": 122, "y": 190, "w": 96,  "h": 42},
            {"name": "RIGHT", "label": right_label,"x": 248, "y": 164, "w": 74,  "h": 46},
            {"name": "SEL",   "label": sel_label,  "x": 350, "y": 156, "w": 108, "h": 62},
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

    def _draw_sound_edit(self, draw):
        draw.text((16, 10), "Sound Edit", font=self.font_title, fill=ACCENT)
        side = state.sound_edit_active_side if state.sound_edit_active_side in {"A", "B"} else "B"
        right_text = f"{side}  {state.sf_name}/{shorten_text(state.current_preset_name, 10)}"
        bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (bbox[2] - bbox[0]), 18), right_text, font=self.font_small, fill=ACCENT)

        selected_idx = clamp_index(state.sound_edit_index, len(SOUND_EDIT_PARAMS))
        current = SOUND_EDIT_PARAMS[selected_idx]
        cc = int(current["cc"])
        b_val = int(state.sound_edit_values.get(cc, current["default"]))
        a_val = int(state.sound_edit_a_values.get(cc, current["default"]))
        live_val = a_val if side == "A" else b_val
        draw.text((18, 42), f"{current['name']}  CC{cc}  {side}:{live_val}", font=self.font_small, fill=DIM)

        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)

        cell_w = (self.width - 48) // SOUND_EDIT_COLS
        cell_h = 42
        grid_x = 24
        grid_y = 72
        rows = (len(SOUND_EDIT_PARAMS) + SOUND_EDIT_COLS - 1) // SOUND_EDIT_COLS

        for logical_row in range(rows):
            y1 = grid_y + logical_row * cell_h
            y2 = y1 + cell_h - 6
            for col in range(SOUND_EDIT_COLS):
                i = logical_row * SOUND_EDIT_COLS + col
                if i >= len(SOUND_EDIT_PARAMS):
                    continue
                item = SOUND_EDIT_PARAMS[i]
                x1 = grid_x + col * cell_w
                x2 = x1 + cell_w - 10
                item_cc = int(item["cc"])
                b = int(state.sound_edit_values.get(item_cc, item["default"]))
                a = int(state.sound_edit_a_values.get(item_cc, item["default"]))
                shown = a if side == "A" and i == selected_idx else b
                selected = (i == selected_idx)
                modified = item_cc in state.sound_edit_modified
                fill = SELECT_BG if selected else (30, 36, 48)
                outline = ACCENT if modified and not selected else None
                draw.rounded_rectangle((x1, y1, x2, y2), radius=9, fill=fill, outline=outline, width=2 if outline else 1)
                label = str(item["name"])
                value_text = f"{shown:3d}"
                label_fill = FG if selected else DIM
                # A: when the highlighted parameter has been changed from its
                # default value, make only the numeric value stand out. The
                # border already marks modified non-selected cells; this keeps
                # the selected cell readable without adding another icon.
                if selected and modified:
                    value_fill = MODIFIED_VALUE
                elif selected:
                    value_fill = FG
                else:
                    value_fill = ACCENT
                draw.text((x1 + 10, y1 + 6), label, font=self.font_body, fill=label_fill)
                vb = draw.textbbox((0, 0), value_text, font=self.font_body)
                draw.text((x2 - 10 - (vb[2] - vb[0]), y1 + 6), value_text, font=self.font_body, fill=value_fill)

        hint_y = self.height - 86
        draw.text((24, hint_y), "Arrows: move   Encoder: value", font=self.font_small, fill=DIM)
        draw.text((24, hint_y + 22), "SEL: A/B   SEL long: reset   R long: Quick", font=self.font_small, fill=DIM)


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
        draw.text((16, 10), "Power Menu", font=self.font_title, fill=ACCENT)
        draw.rounded_rectangle((32, 52, self.width - 32, self.height - 50), radius=14, fill=BOX_BG)
        if state.power_confirm_action == "EXEC_HALT":
            # Option B: Halt does not use an Are-you-sure dialog, but it still
            # gives the user immediate visual feedback before systemd poweroff.
            draw.text((52, 84), "Shutting down...", font=self.font_title, fill=FG)
            draw.text((52, 126), "Please wait", font=self.font_body, fill=DIM)
            return
        if state.power_confirm_action == "EXEC_REBOOT":
            draw.text((52, 84), "Rebooting...", font=self.font_title, fill=FG)
            draw.text((52, 126), "Please wait", font=self.font_body, fill=DIM)
            return
        if state.power_confirm_action:
            draw.text((52, 70), f"{state.power_confirm_action}?", font=self.font_title, fill=FG)
            draw.text((52, 108), "Are you sure?", font=self.font_body, fill=DIM)
            labels = POWER_CONFIRM_ITEMS
            current_idx = state.power_confirm_index
            start_y = 154
            row_h = 40
        else:
            draw.text((52, 70), "Select action", font=self.font_body, fill=DIM)
            labels = POWER_MENU_ITEMS
            current_idx = state.power_menu_index
            start_y = 108
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
    def _draw_quick_menu(self, draw):
        # Quick Menu is a shortcut overlay, not a normal page.
        # Do not draw the global Fluid Ardule header here; use the full height
        # so all six quick actions are visible without scrolling.
        draw.text((16, 10), "Quick Menu", font=self.font_title, fill=ACCENT)
        ctx = quick_resume_label()
        labels = []
        for item in QUICK_MENU_ITEMS:
            if item == "Resume" and ctx:
                labels.append((f"Resume  [{ctx}]", False))
            else:
                labels.append((item, False))
        draw.rounded_rectangle((12, 52, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        self._draw_scrolled_rows(draw, labels, state.quick_menu_index, 52, 34, self.height - 50)

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

        now = time.time()
        transient_active = bool(state.transient_footer_text) and now < state.transient_footer_until
        left_text = state.transient_footer_text if transient_active else (footer_hint or event)
        draw.text((12, self.height - 34), left_text, font=self.font_small, fill=ACCENT if transient_active else DIM)

        if not footer_hint and not transient_active:
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
        low = name.lower()
        if state.current_engine == "yoshimi":
            if "yoshimi" in low:
                return item['port']
        else:
            if "FLUID Synth" in name or "FluidSynth" in name or "fluidsynth" in low:
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
        if 'fluid synth' in client_name_l or 'fluidsynth' in client_name_l or 'yoshimi' in client_name_l:
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
    """Reconnect the selected MIDI source to the currently running engine.

    FluidSynth in RAW mode binds directly to the raw MIDI device at engine start.
    Yoshimi, however, exposes an ALSA sequencer port even when launched headless,
    so it must be connected with aconnect. For Yoshimi, prefer a real ALSA SEQ
    input regardless of the current Fluid Ardule MIDI mode label.
    """
    state.fluid_dst_port = "-"

    if state.current_engine == "yoshimi":
        dst = find_fluidsynth_port()  # engine-aware: returns Yoshimi port here
        src, src_name = choose_alsa_seq_input()
        if not src or not dst:
            state.midi_connected = False
            state.midi_src_port = src or "-"
            state.midi_src_name = src_name or "No ALSA seq input"
            state.fluid_dst_port = dst or "-"
            refresh_midi_display_text()
            if force_draw:
                mark_dirty("Yoshimi MIDI waiting")
            clear_midi_reconnect_pending()
            return
        code, out = run_cmd(["aconnect", src, dst])
        already = "already" in out.lower()
        state.midi_src_port = src
        state.midi_src_name = src_name or src
        state.selected_alsa_input = src
        state.selected_alsa_input_name = src_name or src
        state.fluid_dst_port = dst
        state.midi_connected = (code == 0 or already)
        refresh_midi_display_text()
        clear_midi_reconnect_pending()
        if force_draw:
            mark_dirty("Yoshimi connected" if state.midi_connected else f"Yoshimi aconnect failed: {out[:28]}")
        return

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
# Instrument source helpers (SF2 / Yoshimi v2 JSON)
# =========================================================

def source_path_for_index(sf_index: int) -> str:
    return SOUNDFONTS[sf_index][0]


def source_name_for_index(sf_index: int) -> str:
    return SOUNDFONTS[sf_index][1]


def read_instrument_payload_for_index(sf_index: int) -> dict:
    src = Path(source_path_for_index(sf_index))
    if not src.exists() or src.suffix.lower() != ".json":
        return {}
    try:
        return json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"instrument json load failed: {src}: {exc}")
        return {}


def source_engine_for_index(sf_index: int) -> str:
    src = Path(source_path_for_index(sf_index))
    name = source_name_for_index(sf_index).lower()
    if src.suffix.lower() == ".json":
        payload = read_instrument_payload_for_index(sf_index)
        engine = str(payload.get("engine", "")).lower().strip()
        if engine:
            return engine
    if "yoshimi" in name:
        return "yoshimi"
    return "fluidsynth"


def is_yoshimi_source(sf_index: int) -> bool:
    return source_engine_for_index(sf_index) == "yoshimi"


def first_fluidsynth_sf2_path() -> str:
    for path, _name in SOUNDFONTS:
        if Path(path).suffix.lower() == ".sf2":
            return path
    return "/home/pi/sf2/FluidR3_GM.sf2"


def current_soundfont_path() -> str:
    # MIDI file playback still needs an SF2 file. If the live engine is Yoshimi,
    # fall back to the first configured SF2 for MIDI-file rendering.
    if is_yoshimi_source(state.sf_index):
        return first_fluidsynth_sf2_path()
    return source_path_for_index(state.sf_index)



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


def preset_json_path_for_source(source_path: str) -> Path:
    src = Path(source_path)
    if src.suffix.lower() == ".json":
        return src
    return src.with_suffix(".presets.json")



def first_nonempty_value(item: dict, keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def resolve_yoshimi_instrument_path(item: dict, bank_name: str = "", json_path: Path | None = None) -> str:
    """Return an absolute .xiz path from a Yoshimi v2 patch/instrument item.

    Prefer canonical nested v2 fields such as:
      item["yoshimi"]["patch_path"]
      item["yoshimi"]["bank_path"] + item["yoshimi"]["patch_file"]
    Flat legacy keys remain supported as fallback.
    """
    y = item.get("yoshimi") or {}
    if not isinstance(y, dict):
        y = {}

    for key in (
        "patch_path", "path", "source_path", "file_path", "xiz_path",
        "instrument_path", "full_path",
    ):
        value = y.get(key)
        if value:
            text = str(value).strip()
            if text:
                return text

    bank_path = str(y.get("bank_path") or "").strip()
    patch_file = str(y.get("patch_file") or y.get("file") or y.get("filename") or "").strip()
    if bank_path and patch_file:
        return str(Path(bank_path) / patch_file)

    raw = first_nonempty_value(item, [
        "patch_path", "path", "source_path", "file_path", "xiz_path", "file",
        "filepath", "filename", "file_name", "instrument_path",
        "instrument_file", "full_path", "patch_file", "basename",
    ])

    candidates: list[Path] = []
    bank_name = bank_name or str(y.get("bank_name") or item.get("bank_name") or item.get("category") or "").strip()
    bank_dir = Path(bank_path) if bank_path else (Path(YOSHIMI_DEFAULT_ROOT) / bank_name if bank_name else Path(YOSHIMI_DEFAULT_ROOT))

    def add_candidate(path_like) -> None:
        text = str(path_like).strip()
        if not text:
            return
        candidate = Path(text)
        if candidate.is_absolute():
            candidates.append(candidate)
        else:
            if bank_path:
                candidates.append(Path(bank_path) / candidate)
            if json_path is not None:
                candidates.append(json_path.parent / candidate)
            if bank_name:
                candidates.append(bank_dir / candidate)
            candidates.append(Path(YOSHIMI_DEFAULT_ROOT) / candidate)

    if raw:
        add_candidate(raw)

    name = str(item.get("name", "")).strip()
    slot_raw = item.get("slot", item.get("program", item.get("number", "")))
    slot_values: list[int] = []
    try:
        slot_values.append(int(slot_raw))
    except Exception:
        pass

    if bank_name and name:
        inferred_names = [
            f"{name}.xiz",
            f"{name.replace(' ', '_')}.xiz",
            f"{name.replace('_', ' ')}.xiz",
        ]
        for slot in slot_values:
            for n in {slot, slot - 1, slot + 1}:
                if n >= 0:
                    inferred_names.extend([
                        f"{n:04d}-{name}.xiz",
                        f"{n:04d}_{name}.xiz",
                        f"{n:04d}-{name.replace(' ', '_')}.xiz",
                        f"{n:04d}_{name.replace(' ', '_')}.xiz",
                    ])
        for filename in inferred_names:
            candidates.append(bank_dir / filename)

        for pat in [
            f"*{name}*.xiz",
            f"*{name.replace(' ', '_')}*.xiz",
            f"*{name.replace('_', ' ')}*.xiz",
        ]:
            try:
                candidates.extend(bank_dir.glob(pat))
            except Exception:
                pass

        def norm(text: str) -> str:
            text = text.lower().replace("_", " ").replace("-", " ")
            text = re.sub(r"\.xiz$", "", text)
            text = re.sub(r"^\s*\d{1,4}\s+", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text

        wanted = norm(name)
        try:
            for child in bank_dir.glob("*.xiz"):
                child_norm = norm(child.name)
                if child_norm == wanted or wanted in child_norm:
                    candidates.append(child)
        except Exception:
            pass

    seen: set[str] = set()
    for c in candidates:
        try:
            key = str(c)
            if key in seen:
                continue
            seen.add(key)
            if c.exists() and c.is_file():
                return str(c.resolve())
        except Exception:
            continue

    if candidates:
        return str(candidates[0])
    return ""

def find_current_yoshimi_preset() -> dict | None:
    presets = load_presets_for_sf2(state.sf_index)
    if not presets:
        return None
    current_path = str(state.current_instrument_path or "").strip()
    if current_path:
        for p in presets:
            if str(p.get("path", "")).strip() == current_path:
                return p
    for p in presets:
        if (
            int(p.get("bank", p.get("bank_id", -999))) == int(state.current_preset_bank)
            and int(p.get("program", p.get("slot", -999))) == int(state.current_preset_program)
            and (not state.current_preset_name or str(p.get("name", "")) == str(state.current_preset_name))
        ):
            return p
    return choose_default_preset(presets)

def load_presets_for_sf2(sf_index: int) -> list[dict]:
    source_path, _source_name = SOUNDFONTS[sf_index]
    json_path = preset_json_path_for_source(source_path)
    if not json_path.exists():
        return []
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"instrument json load failed: {json_path}: {exc}")
        return []

    source_engine = str(payload.get("engine", source_engine_for_index(sf_index))).lower().strip() or "fluidsynth"
    items = payload.get("instruments") or payload.get("patches") or payload.get("presets") or []
    cleaned: list[dict] = []

    for item in items:
        try:
            engine = str(item.get("engine", source_engine)).lower().strip() or source_engine
            name = str(item.get("name", "")).strip() or "Unnamed"

            if engine == "yoshimi":
                y = item.get("yoshimi") or {}
                if not isinstance(y, dict):
                    y = {}
                bank_id = int(y.get("bank_number", item.get("bank_id", item.get("bank", 0))))
                slot = int(item.get("slot", item.get("program", item.get("number", 0))))
                bank_name = str(y.get("bank_name", item.get("bank_name", item.get("category", "Yoshimi")))).strip() or "Yoshimi"
                xiz_path = resolve_yoshimi_instrument_path(item, bank_name, json_path)
                cleaned.append({
                    "name": name,
                    "bank": bank_id,
                    "program": slot,
                    "category": bank_name,
                    "engine": "yoshimi",
                    "bank_id": bank_id,
                    "bank_name": bank_name,
                    "slot": slot,
                    "path": xiz_path,
                    "is_drum": False,
                })
            else:
                bank = int(item.get("bank", 0))
                program = int(item.get("program", 0))
                category = str(item.get("category", "")).strip() or categorize_preset(bank, program, name)
                cleaned.append({
                    "name": name,
                    "bank": bank,
                    "program": program,
                    "category": category,
                    "engine": "fluidsynth",
                    "is_drum": bool(item.get("is_drum", bank == 128)),
                })
        except Exception:
            continue

    if source_engine == "yoshimi":
        cleaned.sort(key=lambda x: (str(x.get("bank_name", x.get("category", ""))).lower(), int(x.get("slot", x.get("program", 0))), x["name"].lower()))
    else:
        cleaned.sort(key=lambda x: (x["bank"], x["program"], x["name"].lower()))
    return cleaned


def soundfont_preset_counts(sf_index: int) -> tuple[int, int]:
    source_path, _source_name = SOUNDFONTS[sf_index]
    json_path = preset_json_path_for_source(source_path)
    if not json_path.exists():
        return 0, 0
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        total = int(payload.get("instrument_count", payload.get("preset_count", 0)))
        drums = int(payload.get("drum_count", payload.get("drum_preset_count", 0)))
        return total, drums
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
    state.category_source_name = source_name_for_index(sf_index)
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
    state.preset_source_name = source_name_for_index(sf_index)
    state.category_index = category_index
    state.ui_mode = "submenu"
    state.submenu_key = "preset"
    state.submenu_index = 0
    for i, p in enumerate(filtered):
        if (
            sf_index == state.sf_index
            and p.get("bank", p.get("bank_id", 0)) == state.current_preset_bank
            and p.get("program", p.get("slot", 0)) == state.current_preset_program
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
    state.preview_restore_engine = state.current_engine
    state.preview_restore_instrument_path = state.current_instrument_path


def preview_preset_at_index(index: int) -> None:
    if not state.preset_entries:
        return
    idx = clamp_index(index, len(state.preset_entries))
    p = state.preset_entries[idx]
    target_sf_index = state.preset_sf_index if state.preset_sf_index is not None else state.sf_index

    # Yoshimi preview is intentionally debounced. Moving through the list only
    # updates the highlight immediately; the actual .xiz load is delayed until
    # the user stops pressing UP/DOWN for a short moment. This prevents repeated
    # Yoshimi restarts while scrolling.
    if p.get("engine") == "yoshimi":
        state.sf_index = target_sf_index
        state.sf_name = source_name_for_index(target_sf_index)
        state.current_preset_bank = int(p.get("bank", p.get("bank_id", 0)))
        state.current_preset_program = int(p.get("program", p.get("slot", 0)))
        state.current_preset_name = str(p.get("name", "Yoshimi"))
        state.preview_active = True
        state.preset_index = idx
        state.submenu_index = idx
        state.pending_yoshimi_preview_index = idx
        state.pending_yoshimi_preview_due = time.time() + YOSHIMI_PREVIEW_DEBOUNCE_SEC
        mark_dirty(f'Preview queued: {p["name"]}')
        return

    if target_sf_index != state.sf_index:
        restart_engine(target_sf_index, state.dac_index)
    apply_preset(p["bank"], p["program"], p["name"])
    state.preview_active = True
    state.preset_index = idx
    state.submenu_index = idx
    drum_tag = " [DRUM]" if p.get("bank") == 128 else ""
    mark_dirty(f'Preview: {p["name"]} ({p["bank"]},{p["program"]}){drum_tag}')


def process_pending_yoshimi_preview() -> None:
    if state.pending_yoshimi_preview_index is None:
        return
    if state.ui_mode != "submenu" or state.submenu_key != "preset":
        state.pending_yoshimi_preview_index = None
        state.pending_yoshimi_preview_due = 0.0
        return
    if time.time() < state.pending_yoshimi_preview_due:
        return
    idx = state.pending_yoshimi_preview_index
    state.pending_yoshimi_preview_index = None
    state.pending_yoshimi_preview_due = 0.0
    if not state.preset_entries:
        return
    idx = clamp_index(idx, len(state.preset_entries))
    if idx != state.submenu_index:
        return
    p = state.preset_entries[idx]
    if p.get("engine") != "yoshimi":
        return
    path = str(p.get("path", "")).strip()
    state.current_instrument_path = path
    if not path:
        mark_dirty(f'Yoshimi path missing: {p.get("name", "Yoshimi")}')
        log(f"Yoshimi preview rejected: empty path for {p}")
        return
    mark_dirty(f'Preview Yoshimi: {p.get("name", "Yoshimi")}')
    start_yoshimi_instrument(path, state.audio_device)

def cancel_preset_preview_and_restore() -> None:
    state.pending_yoshimi_preview_index = None
    state.pending_yoshimi_preview_due = 0.0
    if state.preview_restore_sf_index is None:
        state.preview_active = False
        return
    restore_sf = state.preview_restore_sf_index
    restore_bank = state.preview_restore_preset_bank
    restore_program = state.preview_restore_preset_program
    restore_name = state.preview_restore_preset_name
    restore_engine = state.preview_restore_engine or "fluidsynth"
    restore_path = str(state.preview_restore_instrument_path or "").strip()

    state.sf_index = restore_sf
    state.sf_name = source_name_for_index(restore_sf)

    if restore_engine == "yoshimi" or is_yoshimi_source(restore_sf):
        if restore_path:
            apply_preset(restore_bank, restore_program, restore_name, engine="yoshimi", path=restore_path)
        else:
            mark_dirty("Yoshimi restore path missing")
    else:
        if state.current_engine == "yoshimi":
            restart_engine(restore_sf, state.dac_index)
        apply_preset(restore_bank, restore_program, restore_name, engine="fluidsynth")
    state.preview_active = False


def commit_current_preview() -> None:
    # If a Yoshimi preview is pending, load it before committing so SEL confirms
    # the item currently highlighted on the screen.
    if state.pending_yoshimi_preview_index is not None:
        state.pending_yoshimi_preview_due = 0.0
        process_pending_yoshimi_preview()
    state.preview_active = False
    state.preview_restore_sf_index = None
    state.preview_restore_preset_bank = state.current_preset_bank
    state.preview_restore_preset_program = state.current_preset_program
    state.preview_restore_preset_name = state.current_preset_name
    state.preview_restore_engine = state.current_engine
    state.preview_restore_instrument_path = state.current_instrument_path



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


def start_yoshimi_instrument(xiz_path: str, audio_device: str) -> bool:
    """Start Yoshimi headlessly and load one .xiz instrument at launch.

    Important:
    - Do not drive Yoshimi through the interactive CLI.
    - Use the command form verified on the target system:
      yoshimi -i -A -a -L /path/to/instrument.xiz
    - Keep stdin closed with DEVNULL so the prompt cannot fill the log.
    """
    global fluid_proc, yoshimi_log_handle

    xiz_path = str(xiz_path or "").strip()
    if not xiz_path:
        mark_dirty("Yoshimi path missing")
        log("Yoshimi start rejected: empty instrument path")
        return False

    xiz = Path(xiz_path)
    if not xiz.exists():
        mark_dirty(f"Yoshimi file missing: {shorten_text(xiz.name, 18)}")
        log(f"Yoshimi instrument file missing: {xiz_path}")
        return False

    # Stop the currently managed engine first. This is intentionally the same
    # process slot used by FluidSynth, because Fluid Ardule runs only one live
    # synth engine at a time.
    stop_fluidsynth()

    # Clean up any stale Yoshimi instance left by an earlier failed test run.
    # This keeps ALSA ports unambiguous for aconnect.
    run_cmd(["pkill", "-TERM", "-x", "yoshimi"])
    time.sleep(0.2)

    os.makedirs(LOG_DIR, exist_ok=True)
    if yoshimi_log_handle:
        try:
            yoshimi_log_handle.close()
        except Exception:
            pass
        yoshimi_log_handle = None

    cmd = [
        YOSHIMI_EXECUTABLE,
        "-i",
        "-A",
        "-a",
        "-L",
        xiz_path,
    ]

    log(f"Starting Yoshimi with {xiz.name} / {audio_device}")
    # Yoshimi can repeatedly emit interactive prompts such as
    # "yoshimi> @ Top" even when used as a headless engine. Keep a minimal
    # Fluid Ardule-side launch log, but do not pipe Yoshimi stdout/stderr
    # into a persistent log file.
    try:
        with open(YOSHIMI_LOG_PATH, "w", buffering=1) as yh:
            yh.write("CMD: " + " ".join(cmd) + "\n")
            yh.write("NOTE: Yoshimi stdout/stderr suppressed to avoid CLI prompt spam.\n")
    except Exception:
        pass

    try:
        fluid_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            text=True,
        )
    except FileNotFoundError:
        mark_dirty("Yoshimi missing")
        return False
    except Exception as exc:
        mark_dirty(f"Yoshimi start failed: {exc}")
        log(f"Yoshimi start exception: {exc}")
        return False

    time.sleep(1.2)
    if fluid_proc.poll() is None:
        state.fluid_pid = fluid_proc.pid
        state.current_engine = "yoshimi"
        reconnect_midi_to_fluidsynth(force_draw=True)
        return True

    rc = fluid_proc.returncode
    fluid_proc = None
    state.fluid_pid = None
    mark_dirty(f"Yoshimi failed rc={rc}")
    log(f"Yoshimi failed to start; returncode={rc}. See {YOSHIMI_LOG_PATH}")
    return False


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
        "-o", "synth.chorus.active=1",
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
        state.current_engine = "fluidsynth"
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


def apply_preset(bank: int, program: int, name: str | None = None, *, engine: str = "fluidsynth", path: str | None = None) -> None:
    state.current_preset_bank = int(bank)
    state.current_preset_program = int(program)
    if name:
        state.current_preset_name = name

    # Preset/source changes start a fresh volatile Sound Edit baseline.
    reset_sound_edit_to_defaults()

    if engine == "yoshimi":
        path = str(path or state.current_instrument_path or "").strip()
        if not path:
            mark_dirty("Yoshimi path missing")
            log(f"Yoshimi apply rejected: empty path for {state.current_preset_name}")
            return
        state.current_engine = "yoshimi"
        state.current_instrument_path = path
        ok = start_yoshimi_instrument(path, state.audio_device)
        if ok:
            mark_dirty(f"Yoshimi -> {state.current_preset_name}")
        return

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

    # Program Change does not necessarily clear MIDI controller state.
    # Re-apply the Sound Edit default CC set so every preset starts from a
    # predictable baseline instead of inheriting the previous live edits.
    defaults_ok = apply_sound_edit_defaults_to_engine(announce=False)
    ok = ok or defaults_ok

    if ok:
        mark_dirty(f"Preset -> {state.current_preset_name}")
    else:
        mark_dirty(f"Preset queued: {state.current_preset_name}")

def apply_soundfont_with_default_preset(sf_index: int) -> None:
    presets = load_presets_for_sf2(sf_index)
    default_preset = choose_default_preset(presets)

    if is_yoshimi_source(sf_index):
        state.sf_index = sf_index % len(SOUNDFONTS)
        state.sf_name = source_name_for_index(state.sf_index)
        if default_preset:
            apply_preset(
                default_preset.get("bank", default_preset.get("bank_id", 0)),
                default_preset.get("program", default_preset.get("slot", 0)),
                default_preset.get("name", "Yoshimi"),
                engine="yoshimi",
                path=default_preset.get("path"),
            )
        else:
            mark_dirty("No Yoshimi JSON")
        return

    restart_engine(sf_index, state.dac_index)
    if default_preset:
        apply_preset(default_preset["bank"], default_preset["program"], default_preset["name"], engine="fluidsynth")
    else:
        state.current_preset_bank = 0
        state.current_preset_program = 0
        state.current_preset_name = "Default"
        mark_dirty(f"SF loaded: {state.sf_name}")


def restore_current_preset_after_engine_restart() -> None:
    if is_yoshimi_source(state.sf_index) or state.current_engine == "yoshimi":
        preset = find_current_yoshimi_preset()
        path = str(state.current_instrument_path or "").strip()
        if preset and not path:
            path = str(preset.get("path", "")).strip()
        if not path:
            mark_dirty("Yoshimi path lost")
            log("Yoshimi restore failed: current instrument path is empty")
            return
        if preset:
            state.current_preset_bank = int(preset.get("bank", preset.get("bank_id", state.current_preset_bank)))
            state.current_preset_program = int(preset.get("program", preset.get("slot", state.current_preset_program)))
            state.current_preset_name = str(preset.get("name", state.current_preset_name))
        state.current_instrument_path = path
        apply_preset(
            state.current_preset_bank,
            state.current_preset_program,
            state.current_preset_name,
            engine="yoshimi",
            path=path,
        )
        return
    apply_preset(
        state.current_preset_bank,
        state.current_preset_program,
        state.current_preset_name,
        engine="fluidsynth",
    )


def restart_engine(sf_index: int, dac_index: int) -> None:
    sf_index %= len(SOUNDFONTS)
    dac_index %= len(state.dac_options)
    sf_path, sf_name = SOUNDFONTS[sf_index]
    audio_device, dac_name = state.dac_options[dac_index]
    if state.midi_mode != "uno2_bridge_seq":
        stop_bridge()

    state.sf_index = sf_index
    state.sf_name = sf_name
    state.dac_index = dac_index
    state.dac_name = dac_name
    state.audio_device = audio_device
    state.dac_preview_index = state.dac_index

    if is_yoshimi_source(sf_index):
        presets = load_presets_for_sf2(sf_index)
        target = None
        current_path = str(state.current_instrument_path or "").strip()
        if current_path:
            for p in presets:
                if str(p.get("path", "")).strip() == current_path:
                    target = p
                    break
        if target is None:
            for p in presets:
                if (
                    int(p.get("bank", p.get("bank_id", -999))) == int(state.current_preset_bank)
                    and int(p.get("program", p.get("slot", -999))) == int(state.current_preset_program)
                    and str(p.get("name", state.current_preset_name)) == str(state.current_preset_name)
                ):
                    target = p
                    break
        target = target or choose_default_preset(presets)
        if not target:
            mark_dirty("No Yoshimi JSON")
            return
        path = str(target.get("path", current_path)).strip()
        if not path:
            mark_dirty("Yoshimi path missing")
            log(f"Yoshimi restart rejected: empty path for target={target}")
            return
        mark_dirty(f"Restarting -> Yoshimi:{target.get('name','Instrument')} / DAC:{dac_name}")
        state.current_preset_bank = int(target.get("bank", target.get("bank_id", 0)))
        state.current_preset_program = int(target.get("program", target.get("slot", 0)))
        state.current_preset_name = str(target.get("name", "Yoshimi"))
        state.current_instrument_path = path
        ok = start_yoshimi_instrument(path, audio_device)
        if not ok:
            return
        mark_dirty(f"Active -> Yoshimi/{state.current_preset_name}")
        return

    mark_dirty(f"Restarting -> SF:{sf_name} / DAC:{dac_name}")
    ok = start_fluidsynth(sf_path, audio_device)
    if not ok:
        return
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
            "-o", "synth.chorus.active=1",
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
# Sound Edit helpers
# =========================================================

def clamp_cc_value(value: int) -> int:
    return max(SOUND_EDIT_MIN, min(SOUND_EDIT_MAX, int(value)))

def sound_edit_is_accel_selected() -> bool:
    # Kept for compatibility with older call sites. There is no 9th ACC/SENS row now.
    return False

def sound_edit_current_param() -> dict:
    return SOUND_EDIT_PARAMS[clamp_index(state.sound_edit_index, len(SOUND_EDIT_PARAMS))]

def set_encoder_accel_profile(profile: int) -> bool:
    # Read-only mirror of the UNO-1 encoder acceleration profile.
    profile = max(1, min(3, int(profile)))
    state.encoder_accel_profile = profile
    state.encoder_accel_pending_profile = profile
    if SOUND_EDIT_CC_DEBUG:
        log(f"SOUND_EDIT UNO accel mirror P{profile}")
    return True

def reset_sound_edit_to_defaults() -> None:
    state.sound_edit_values = default_sound_edit_values()
    state.sound_edit_a_values = default_sound_edit_values()
    state.sound_edit_active_side = "B"
    state.sound_edit_modified = set()

def apply_sound_edit_defaults_to_engine(*, announce: bool = False) -> bool:
    """Reset the volatile Sound Edit set and send its default CC values.

    Preset changes and MIDI Panic should behave as a clean sound-state reset,
    not as a continuation of the last edited CC values. FluidSynth does not
    automatically clear controller values on Program Change, so Fluid Ardule
    explicitly re-sends the eight Sound Edit defaults after applying a preset.
    """
    reset_sound_edit_to_defaults()

    if state.current_engine != "fluidsynth":
        if announce:
            mark_dirty("Sound Edit reset")
        return False

    ok = False
    for item in SOUND_EDIT_PARAMS:
        ok = send_sound_edit_cc(int(item["cc"]), int(item["default"])) or ok

    if announce:
        mark_dirty("Sound Edit reset")
    return ok

def send_sound_edit_cc(cc: int, value: int) -> bool:
    value = clamp_cc_value(value)
    cc = int(cc)
    if state.current_engine != "fluidsynth":
        mark_dirty("CC edit: FluidSynth only")
        if SOUND_EDIT_CC_DEBUG:
            log(f"SOUND_EDIT CC skipped engine={state.current_engine} cc={cc} val={value}")
        return False

    channels = range(16) if SOUND_EDIT_SEND_ALL_CHANNELS else range(1)
    ok = False
    sent = 0
    for ch in channels:
        sent_ok = send_fluidsynth_command(f"cc {ch} {cc} {value}")
        if sent_ok:
            sent += 1
        ok = sent_ok or ok

    if SOUND_EDIT_CC_DEBUG:
        target = "all" if SOUND_EDIT_SEND_ALL_CHANNELS else "0"
        log(f"SOUND_EDIT CC cc={cc} val={value} ch={target} sent={sent} ok={ok}")
    if not ok:
        mark_dirty("CC send failed")
    return ok

def sound_edit_delta_from_uno(raw_step: int) -> int:
    """Convert UNO encoder step to a Sound Edit CC delta.

    UNO-1 already detects rotation speed and sends ENC:+1/+2/+3 or ENC:-1/-2/-3.
    In Sound Edit we intentionally use that magnitude, but scale it gently by
    the current UNO acceleration profile:
      P1 Fine   : always +/-1 for precise editing
      P2 Normal : use UNO step as-is
      P3 Fast   : stronger non-linear boost, 1->1, 2->4, 3->7, capped at +/-10

    This scaling is used only for CC value editing. Normal menu navigation uses
    only the direction and therefore always moves one item at a time.
    """
    raw = int(raw_step)
    if raw == 0:
        return 0

    sign = 1 if raw > 0 else -1
    mag = abs(raw)
    profile = max(1, min(3, int(getattr(state, "encoder_accel_profile", ENCODER_ACCEL_DEFAULT_PROFILE))))

    if profile == 1:
        units = 1
    elif profile == 2:
        units = mag
    else:
        # Tuned for a faster full-range sweep: approximately 0-127 in
        # about 3.5 turns instead of about 5 turns on the current encoder.
        units = 1 + (mag - 1) * 3

    delta = sign * min(10, max(1, units)) * SOUND_EDIT_STEP

    # Debug hook kept for temporary diagnostics. Disabled by default via
    # SOUND_EDIT_CC_DEBUG to avoid journal noise during normal performance use.
    if SOUND_EDIT_CC_DEBUG and (abs(raw) > 1 or profile != 2):
        log(f"SOUND_EDIT step raw={raw} profile=P{profile} delta={delta}")
    return delta

def enter_sound_edit() -> None:
    state.ui_mode = "sound_edit"
    state.sound_edit_index = clamp_index(state.sound_edit_index, len(SOUND_EDIT_PARAMS))
    state.sound_edit_last_adjust_time = 0.0
    invalidate_full_display()
    mark_dirty("Sound Edit")

def leave_sound_edit() -> None:
    state.ui_mode = "main"
    invalidate_full_display()
    mark_dirty("Back to main")

def move_sound_edit_selection(delta_row: int = 0, delta_col: int = 0) -> None:
    idx = clamp_index(state.sound_edit_index, len(SOUND_EDIT_PARAMS))
    row = idx // SOUND_EDIT_COLS
    col = idx % SOUND_EDIT_COLS
    rows = (len(SOUND_EDIT_PARAMS) + SOUND_EDIT_COLS - 1) // SOUND_EDIT_COLS

    new_row = max(0, min(rows - 1, row + delta_row))
    new_col = max(0, min(SOUND_EDIT_COLS - 1, col + delta_col))
    new_idx = new_row * SOUND_EDIT_COLS + new_col
    if new_idx >= len(SOUND_EDIT_PARAMS):
        new_idx = len(SOUND_EDIT_PARAMS) - 1
    if new_idx == idx:
        mark_dirty("Edge")
        return
    state.sound_edit_index = new_idx
    state.sound_edit_active_side = "B"
    state.sound_edit_last_adjust_time = 0.0
    item = sound_edit_current_param()
    mark_dirty(f"{item['name']} CC{item['cc']}")

def adjust_sound_edit_value(step: int) -> None:
    if step == 0:
        return
    item = sound_edit_current_param()
    cc = int(item["cc"])
    old_b = int(state.sound_edit_values.get(cc, item["default"]))
    if cc not in state.sound_edit_modified:
        state.sound_edit_a_values[cc] = old_b
    delta = sound_edit_delta_from_uno(int(step))
    new_b = clamp_cc_value(old_b + delta)
    if new_b == old_b:
        mark_dirty(f"{item['name']} B:{new_b}")
        return
    state.sound_edit_values[cc] = new_b
    state.sound_edit_active_side = "B"
    if new_b == int(item["default"]):
        state.sound_edit_modified.discard(cc)
    else:
        state.sound_edit_modified.add(cc)
    ok = send_sound_edit_cc(cc, new_b)
    if ok:
        mark_dirty(f"{item['name']} B:{new_b}")
    else:
        mark_dirty(f"{item['name']} send failed")

def toggle_sound_edit_ab() -> None:
    item = sound_edit_current_param()
    cc = int(item["cc"])
    if state.sound_edit_active_side == "B":
        state.sound_edit_active_side = "A"
        value = int(state.sound_edit_a_values.get(cc, item["default"]))
    else:
        state.sound_edit_active_side = "B"
        value = int(state.sound_edit_values.get(cc, item["default"]))
    ok = send_sound_edit_cc(cc, value)
    mark_dirty(f"{item['name']} {state.sound_edit_active_side}:{value}" if ok else f"{item['name']} send failed")

def reset_current_sound_edit_param() -> None:
    item = sound_edit_current_param()
    cc = int(item["cc"])
    value = int(item["default"])
    state.sound_edit_values[cc] = value
    state.sound_edit_a_values[cc] = value
    state.sound_edit_active_side = "B"
    state.sound_edit_modified.discard(cc)
    ok = send_sound_edit_cc(cc, value)
    mark_dirty(f"{item['name']} reset {value}" if ok else f"{item['name']} send failed")


def set_sound_edit_current_value_from_pot(value: int) -> None:
    item = sound_edit_current_param()
    cc = int(item["cc"])
    old_b = int(state.sound_edit_values.get(cc, item["default"]))
    new_b = clamp_cc_value(value)
    if new_b == old_b:
        return
    if cc not in state.sound_edit_modified:
        state.sound_edit_a_values[cc] = old_b
    state.sound_edit_values[cc] = new_b
    state.sound_edit_active_side = "B"
    if new_b == int(item["default"]):
        state.sound_edit_modified.discard(cc)
    else:
        state.sound_edit_modified.add(cc)
    ok = send_sound_edit_cc(cc, new_b)
    if ok:
        mark_dirty(f"{item['name']} B:{new_b}")
    else:
        mark_dirty(f"{item['name']} send failed")


def toggle_pot_mode() -> None:
    state.pot_mode = "PARAM" if state.pot_mode == "VOL" else "VOL"

    if state.pot_mode == "PARAM":
        # The pot now controls the highlighted Sound Edit parameter. Mark the
        # volume side as uncaptured so returning to VOL mode requires pickup.
        state.pot_volume_captured = False
        label = "POT: PARAM"
    else:
        # Soft takeover: do not immediately apply the physical pot angle to
        # volume. Volume resumes only after the pot is moved close to the
        # current logical volume value.
        state.pot_volume_captured = False
        label = "POT: VOL"

    show_footer_message(label, POT_MODE_FOOTER_HOLD_SEC)

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
    state.pending_yoshimi_preview_index = None
    state.pending_yoshimi_preview_due = 0.0
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
                (p["name"] if p.get("engine") == "yoshimi" else f'{p["name"]} ({p["bank"]},{p["program"]})'),
                state.preset_sf_index == state.sf_index
                and p.get("bank", p.get("bank_id", 0)) == state.current_preset_bank
                and p.get("program", p.get("slot", 0)) == state.current_preset_program,
            )
            for p in state.preset_entries
        ]
    if key == "dac":
        return [(name, i == state.dac_index) for i, (_dev, name) in enumerate(state.dac_options)]
    if key == "midi":
        return [(name, mode == state.midi_mode) for mode, name in state.midi_options]
    if key == "controls":
        return [("Sound Edit", False)]
    if key == "placeholder":
        return [("Reserved", False)]
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
        if p.get("engine") == "yoshimi":
            state.sf_index = target_sf_index
            state.sf_name = source_name_for_index(target_sf_index)
            state.current_instrument_path = str(p.get("path", "")).strip()
            apply_preset(
                p.get("bank", p.get("bank_id", 0)),
                p.get("program", p.get("slot", 0)),
                p.get("name"),
                engine="yoshimi",
                path=state.current_instrument_path,
            )
        else:
            if target_sf_index != state.sf_index:
                apply_soundfont_with_default_preset(target_sf_index)
            apply_preset(p["bank"], p["program"], p["name"], engine="fluidsynth")
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
    label = MAIN_MENU[clamp_index(state.menu_index, len(MAIN_MENU))]
    if label == "Sound Source":
        enter_submenu("soundfont")
    elif label == "File Player":
        enter_file_browser()
    elif label == "Controls":
        enter_sound_edit()
    elif label == "MIDI Mode":
        enter_submenu("midi")
    elif label == "DAC":
        enter_submenu("dac")
    else:
        enter_submenu("placeholder")



# =========================================================
# Quick menu
# =========================================================

def make_quick_snapshot() -> dict:
    return {
        "ui_mode": state.ui_mode,
        "menu_index": state.menu_index,
        "submenu_index": state.submenu_index,
        "submenu_key": state.submenu_key,
        "submenu_return_mode": state.submenu_return_mode,
        "preset_index": state.preset_index,
        "preset_sf_index": state.preset_sf_index,
        "preset_source_name": state.preset_source_name,
        "category_entries": list(getattr(state, "category_entries", [])),
        "category_index": getattr(state, "category_index", 0),
        "category_source_sf_index": getattr(state, "category_source_sf_index", None),
        "category_source_name": getattr(state, "category_source_name", ""),
        "browser_root": state.browser_root,
        "browser_path": state.browser_path,
        "browser_index": state.browser_index,
        "player_path": state.player_path,
    }


def quick_resume_label() -> str:
    snap = state.quick_resume_snapshot
    if not snap:
        return ""
    mode = snap.get("ui_mode", "main")
    if mode == "main":
        return "Home"
    if mode == "file_source":
        return "File Source"
    if mode == "file_browser":
        path = str(snap.get("browser_path") or "")
        name = "USB" if normalize_path(path).startswith(normalize_path(USB_MOUNT_POINT)) else Path(path).name or "Files"
        return f"Files/{shorten_text(name, 10)}"
    if mode == "player":
        if snap.get("player_path"):
            return f"Player/{shorten_text(Path(snap['player_path']).name, 10)}"
        return "Player"
    if mode == "sound_edit":
        return "Sound Edit"
    if mode == "submenu":
        key = snap.get("submenu_key") or "Menu"
        labels = {
            "soundfont": "Sound Source",
            "preset_category": "Category",
            "preset": "Preset",
            "dac": "DAC",
            "midi": "MIDI Mode",
            "placeholder": "Extension",
            "controls": "Sound Edit",
        }
        return labels.get(key, str(key))
    return str(mode)


def enter_quick_menu() -> None:
    if state.ui_mode not in {"quick_menu", "power_menu"} and not state.usb_eject_confirm:
        state.quick_resume_snapshot = make_quick_snapshot()
    state.ui_mode = "quick_menu"
    state.quick_menu_index = 0
    invalidate_full_display()
    mark_dirty("Quick menu")


def restore_quick_snapshot() -> None:
    snap = state.quick_resume_snapshot
    if not snap:
        state.ui_mode = "main"
        invalidate_full_display()
        mark_dirty("Home")
        return

    state.ui_mode = snap.get("ui_mode", "main")
    state.menu_index = snap.get("menu_index", state.menu_index)
    state.submenu_index = snap.get("submenu_index", state.submenu_index)
    state.submenu_key = snap.get("submenu_key", state.submenu_key)
    state.submenu_return_mode = snap.get("submenu_return_mode", state.submenu_return_mode)
    state.preset_index = snap.get("preset_index", state.preset_index)
    state.preset_sf_index = snap.get("preset_sf_index", state.preset_sf_index)
    state.preset_source_name = snap.get("preset_source_name", state.preset_source_name)
    state.category_entries = list(snap.get("category_entries", getattr(state, "category_entries", [])))
    state.category_index = snap.get("category_index", getattr(state, "category_index", 0))
    state.category_source_sf_index = snap.get("category_source_sf_index", getattr(state, "category_source_sf_index", None))
    state.category_source_name = snap.get("category_source_name", getattr(state, "category_source_name", ""))
    state.browser_root = snap.get("browser_root", state.browser_root)
    state.browser_path = snap.get("browser_path", state.browser_path)
    state.browser_index = snap.get("browser_index", state.browser_index)

    if state.ui_mode == "file_browser":
        old_index = snap.get("browser_index", state.browser_index)
        refresh_browser_entries()
        state.browser_index = clamp_index(old_index, len(state.browser_entries))
    elif state.ui_mode == "file_source":
        state.browser_index = clamp_index(snap.get("browser_index", state.browser_index), len(get_file_source_entries()))

    invalidate_full_display()
    mark_dirty("Resume")


def enter_home() -> None:
    state.ui_mode = "main"
    state.menu_index = 0
    invalidate_full_display()
    mark_dirty("Home")


def enter_now_playing() -> None:
    if not state.player_path:
        mark_dirty("No file loaded")
        return
    state.ui_mode = "player"
    invalidate_full_display()
    mark_dirty("Now Playing")


def quick_menu_select() -> None:
    item = QUICK_MENU_ITEMS[clamp_index(state.quick_menu_index, len(QUICK_MENU_ITEMS))]
    if item == "Resume":
        restore_quick_snapshot()
        return
    if item == "Now Playing":
        enter_now_playing()
        return
    if item == "Home":
        enter_home()
        return
    if item == "Sound Source":
        enter_submenu("soundfont")
        mark_dirty("Sound Source")
        return
    if item == "USB Eject":
        request_usb_eject()
        return
    if item == "Power...":
        enter_power_menu()
        return
    mark_dirty("Not implemented yet")

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


def execute_power_action(action: str | None = None) -> None:
    action = action or state.power_confirm_action
    if not action:
        cancel_power_menu()
        return

    try:
        if action == "Halt":
            state.power_confirm_action = "EXEC_HALT"
            state.power_confirm_index = 0
            invalidate_full_display()
            mark_dirty("Shutting down...")
            maybe_render(force=True)
            notify_uno_power_state(action)
            time.sleep(1.0)
            subprocess.Popen(["sudo", "systemctl", "poweroff"])
        elif action == "Reboot":
            state.power_confirm_action = "EXEC_REBOOT"
            state.power_confirm_index = 0
            invalidate_full_display()
            mark_dirty("Rebooting...")
            maybe_render(force=True)
            notify_uno_power_state(action)
            time.sleep(1.0)
            subprocess.Popen(["sudo", "systemctl", "reboot"])
    except Exception as exc:
        state.power_confirm_action = None
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

    if state.ui_mode == "sound_edit":
        # Sound Edit has its own input handler, so global long-press actions
        # that must remain available are handled first and explicitly.
        if btn == "RIGHT_LP":
            pulse_button_activity(); enter_quick_menu(); return
        if btn == "DOWN_LP":
            pulse_button_activity(); midi_panic(); return
        if btn == "LEFT_LP":
            pulse_button_activity(); toggle_pot_mode(); return
        if btn == "SEL_LP":
            pulse_button_activity(); reset_current_sound_edit_param(); return
        if btn == "UP_LP":
            pulse_button_activity(); apply_sound_edit_defaults_to_engine(announce=True); return

        if btn == "UP":
            pulse_button_activity(); move_sound_edit_selection(delta_row=-1); return
        if btn == "DOWN":
            pulse_button_activity(); move_sound_edit_selection(delta_row=+1); return
        if btn == "RIGHT":
            pulse_button_activity(); move_sound_edit_selection(delta_col=+1); return
        if btn == "LEFT":
            pulse_button_activity()
            if state.sound_edit_index % SOUND_EDIT_COLS == 0:
                leave_sound_edit()
            else:
                move_sound_edit_selection(delta_col=-1)
            return
        if btn == "SEL":
            pulse_button_activity(); toggle_sound_edit_ab(); return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if btn == "RIGHT_LP" and state.ui_mode != "power_menu":
        pulse_button_activity()
        enter_quick_menu()
        return

    if btn == "SEL_LP":
        pulse_button_activity()
        enter_power_menu()
        return

    # Panic remains the only direct emergency long-press action.
    if btn == "DOWN_LP" and state.ui_mode != "power_menu":
        pulse_button_activity()
        midi_panic()
        return

    if state.ui_mode == "quick_menu":
        if btn == "UP":
            pulse_button_activity()
            if state.quick_menu_index > 0:
                state.quick_menu_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.quick_menu_index < len(QUICK_MENU_ITEMS) - 1:
                state.quick_menu_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last item")
            return
        if btn == "LEFT":
            pulse_button_activity()
            restore_quick_snapshot()
            return
        if btn == "SEL":
            pulse_button_activity()
            quick_menu_select()
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    # LEFT long is repurposed from USB eject to POT mode toggle.
    # USB eject remains available from the Quick Menu.
    if btn == "LEFT_LP":
        pulse_button_activity()
        toggle_pot_mode()
        return

    # UP_LP is intentionally left unused globally.
    if btn == "UP_LP":
        pulse_button_activity()
        mark_dirty("UP long unused")
        return

    if state.ui_mode == "power_menu":
        if state.power_confirm_action in {"EXEC_HALT", "EXEC_REBOOT"}:
            mark_dirty("Power action running")
            return
        if state.power_confirm_action:
            if btn == "UP":
                if state.power_confirm_index > 0:
                    state.power_confirm_index -= 1
                    mark_dirty(None)
                else:
                    mark_dirty("First item")
                return
            if btn == "DOWN":
                if state.power_confirm_index < len(POWER_CONFIRM_ITEMS) - 1:
                    state.power_confirm_index += 1
                    mark_dirty(None)
                else:
                    mark_dirty("Last item")
                return
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
            if state.power_menu_index > 0:
                state.power_menu_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.power_menu_index < len(POWER_MENU_ITEMS) - 1:
                state.power_menu_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last item")
            return
        if btn == "LEFT":
            pulse_button_activity()
            cancel_power_menu(); return
        if btn == "SEL":
            pulse_button_activity()
            item = POWER_MENU_ITEMS[state.power_menu_index]
            if item == "Cancel":
                cancel_power_menu()
            elif item == "Halt":
                # Halt is entered from a long-press-only power menu, so skip
                # the extra Are-you-sure dialog and show a short feedback page.
                execute_power_action("Halt")
            elif item == "Reboot":
                # Reboot uses the same single-step UX as Halt: show a short
                # feedback page, notify UNO-1, then call systemd reboot.
                execute_power_action("Reboot")
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
            if state.submenu_index > 0:
                state.submenu_index -= 1
                total, drums = soundfont_preset_counts(state.submenu_index)
                sf_name = source_name_for_index(state.submenu_index)
                mark_dirty(f"{sf_name}: {total} presets, {drums} drums" if total else sf_name)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.submenu_index < len(options) - 1:
                state.submenu_index += 1
                total, drums = soundfont_preset_counts(state.submenu_index)
                sf_name = source_name_for_index(state.submenu_index)
                mark_dirty(f"{sf_name}: {total} presets, {drums} drums" if total else sf_name)
            else:
                mark_dirty("Last item")
            return
        if btn == "SEL":
            pulse_button_activity()
            # Leaf selection: apply the highlighted Sound Source, then return
            # immediately to the previous menu context. This uses the common
            # submenu apply path so MIDI-file return/resume behavior stays
            # consistent with other submenus.
            apply_current_submenu_selection()
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
            if state.submenu_index > 0:
                state.submenu_index -= 1
                state.category_index = state.submenu_index
                mark_dirty(state.category_entries[state.category_index] if state.category_entries else "Category")
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.submenu_index < len(options) - 1:
                state.submenu_index += 1
                state.category_index = state.submenu_index
                mark_dirty(state.category_entries[state.category_index] if state.category_entries else "Category")
            else:
                mark_dirty("Last item")
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
            if state.submenu_index > 0:
                preview_preset_at_index(state.submenu_index - 1)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.submenu_index < len(options) - 1:
                preview_preset_at_index(state.submenu_index + 1)
            else:
                mark_dirty("Last item")
            return
        if btn == "SEL":
            pulse_button_activity()
            if state.preset_entries:
                commit_current_preview()
                apply_current_submenu_selection()
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
            if state.menu_index > 0:
                state.menu_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First item")
        else:
            options = get_submenu_options()
            if state.submenu_index > 0:
                state.submenu_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First item")
        return

    if btn == "DOWN":
        pulse_button_activity()
        if state.ui_mode == "main":
            if state.menu_index < len(MAIN_MENU) - 1:
                state.menu_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last item")
        else:
            options = get_submenu_options()
            if state.submenu_index < len(options) - 1:
                state.submenu_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last item")
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
        # USB hotplug/mount is a state change only.
        # Do not force navigation to File Player during boot or runtime.
        # The user should enter File Player explicitly from the menu.
        if state.ui_mode == "file_source":
            state.browser_index = 1 if len(get_file_source_entries()) > 1 else 0
            invalidate_full_display()
        elif state.ui_mode == "file_browser":
            keep = None
            if state.browser_entries and state.browser_index < len(state.browser_entries):
                keep = state.browser_entries[state.browser_index]["name"]
            refresh_browser_entries(keep_name=keep)
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
        try:
            p = max(1, min(3, int(value)))
            state.encoder_accel_profile = p
            state.encoder_accel_pending_profile = p
            names = {1: "Fine", 2: "Normal", 3: "Fast"}
            show_footer_message(f"Accel: P{p} {names[p]}", ACCEL_FOOTER_HOLD_SEC)
        except Exception:
            show_footer_message(f"Accel: P{value}", ACCEL_FOOTER_HOLD_SEC)
        return
    mark_dirty(f"Unknown line: {line}")




def handle_encoder_value(value: str) -> None:
    global last_enc_time

    now = time.time()
    try:
        step = int(value)
    except ValueError:
        return
    if step == 0:
        return

    # In Sound Edit, do not apply the global 20 ms navigation debounce.
    # UNO-1 already sends accelerated ENC steps, so use the raw signed value.
    if state.ui_mode == "sound_edit":
        adjust_sound_edit_value(step)
        last_enc_time = now
        return

    if now - last_enc_time < 0.02:   # 20ms debounce for navigation modes
        return
    last_enc_time = now

    # Encoder rotation is mapped to UP/DOWN navigation. While a file is playing,
    # ignore it explicitly so a reconnect glitch or accidental turn cannot jump tracks.
    if state.ui_mode == "player" and state.player_status == "Playing":
        mark_dirty("Encoder ignored while playing")
        return

    # For menu/navigation contexts, ignore UNO acceleration magnitude and use
    # only the direction. This prevents fast encoder turns from skipping menu
    # items unpredictably; repeated detent events still allow quick scrolling.
    #
    # Slow mechanical rotary motion can occasionally produce one spurious
    # opposite-direction event near a detent. Ignore only a short opposite
    # pulse after a recently accepted navigation step; deliberate direction
    # changes after that short guard window still work normally.
    nav_dir = 1 if step > 0 else -1
    if (
        state.last_nav_enc_dir != 0
        and nav_dir != state.last_nav_enc_dir
        and (now - state.last_nav_enc_time) < ENC_NAV_REVERSAL_GUARD_SEC
    ):
        return

    state.last_nav_enc_dir = nav_dir
    state.last_nav_enc_time = now
    event_name = "DOWN" if nav_dir > 0 else "UP"
    handle_button_event(event_name)


def maybe_render(force: bool = False) -> None:
    now = time.time()

    # Early-boot recovery: if another boot-time component overwrites /dev/fb1
    # after the Home screen has been drawn, partial redraw alone can leave a
    # mixed screen. For a short window after startup, request a full redraw at
    # a slow fixed interval. Outside this window, normal partial redraw behavior
    # and render-rate limiting are unchanged.
    if now < state.force_full_redraw_until:
        if now - state.last_forced_full_redraw_time >= BOOT_FULL_REDRAW_INTERVAL_SEC:
            state.last_forced_full_redraw_time = now
            invalidate_full_display()
            state.dirty = True

    if state.transient_footer_text and now >= state.transient_footer_until:
        state.transient_footer_text = ""
        state.dirty = True

    if not state.dirty:
        return
    if force:
        display.render()
        return
    if now - state.last_render_time < RENDER_MIN_INTERVAL:
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

    # Keep full-screen redraw recovery active only during the vulnerable
    # boot-settling window. This expires quickly and does not change normal
    # runtime render behavior.
    state.force_full_redraw_until = time.time() + BOOT_FULL_REDRAW_SEC
    state.last_forced_full_redraw_time = 0.0

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
            process_pending_yoshimi_preview()
            maybe_render()
    finally:
        stop_player_only()
        stop_midi_activity_monitor()
        stop_fluidsynth()
        stop_bridge()
        global fluid_log_handle, yoshimi_log_handle, player_log_handle
        if fluid_log_handle:
            try:
                fluid_log_handle.close()
            except Exception:
                pass
        if yoshimi_log_handle:
            try:
                yoshimi_log_handle.close()
            except Exception:
                pass
        if player_log_handle:
            try:
                player_log_handle.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
