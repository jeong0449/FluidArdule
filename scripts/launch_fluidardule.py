#!/usr/bin/env python3
# -*- coding: utf-8 -*-

SCRIPT_VERSION = "260707h"

# =========================================================
# Fluid Ardule main UI/runtime script
# Version is defined by SCRIPT_VERSION below.
# Detailed change history is tracked in Git.
# =========================================================

import os
import sys
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

SERIAL_PORT = "/dev/serial/by-id/usb-Arduino__www.arduino.cc__Arduino_Uno_12724551266415469650-if00"
# Optional exact UNO-2 identifier.  If set, MIDI Mode shows
# "UNO-2 bridge (SEQ)" only when this by-id symlink exists.  Leave empty to
# fall back to detecting any additional Arduino/Uno serial device other than
# UNO-1.
UNO2_SERIAL_PORT = "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_75834353930351211140-if00"
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 0.1
SERIAL_INPUT_IGNORE_AFTER_OPEN_SEC = 1.5
SERIAL_OUTPUT_HOLDOFF_AFTER_OPEN_SEC = 2.0

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
YOSHIMI_PREVIEW_DEBOUNCE_SEC = 0.15
# Experimental restart-free Yoshimi instrument switching.
# When Yoshimi is already running, Fluid Ardule tries to keep the process alive
# and sends "load instrument <path>" through Yoshimi stdin.  The Yoshimi JSON
# should use space-free symlink paths because the Yoshimi CLI is fragile with
# filenames containing spaces.  If live loading is unavailable, the code falls
# back to the previous reliable restart-with -L path.
YOSHIMI_LIVE_LOAD_ENABLED = True
YOSHIMI_LIVE_LOAD_FALLBACK_RESTART = True
YOSHIMI_LIVE_LOAD_TRACE = False

# Yoshimi factory "Arpeggios" patches are not MIDI arpeggiators.
# Arpeggio1-like patches get their apparent repeat speed mainly from
# Part 1 / Effect 2 / Echo Delay.  The user-facing number below is calibrated
# to feel close to real BPM, then converted to Yoshimi Echo Delay.
ARP_BPM_DEFAULT = 120
ARP_BPM_MIN = 60
ARP_BPM_MAX = 240
ARP_BPM_STEP = 1
ARP_BPM_FINE_STEP = 1
ARP_CAL_SLOPE = 0.797
ARP_CAL_INTERCEPT = 5.13
ARP_DELAY_NUMERATOR = 6000


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

# External USB MIDI interface selection.
# Match by device/client name instead of ALSA client number because client IDs
# can change across reboots or USB hotplug order changes.
EXTERNAL_MIDI_NAME_HINTS = [
    "USB Midi Cable",
    "SC-D70",
    "SCD70",
    "Roland SC-D70",
]

# Some external sound modules expose ALSA sequencer ports in both aconnect -i
# and aconnect -o. For MIDI Mode, keep only ports that can be meaningful
# performance inputs. USB MIDI cables remain visible because their DIN IN side
# can carry keyboard input; for SC-D70, show only the generic "SC-D70 MIDI"
# port and hide Part A/B, which are sound-module destinations.
SEQ_INPUT_ALLOW_EXTERNAL_HINTS = [
    "USB Midi Cable",
]
SEQ_INPUT_EXCLUDE_EXTERNAL_HINTS = [
    "SC-D70",
    "SCD70",
    "Roland SC-D70",
]
EXTERNAL_MIDI_OUT_MODES = [
    ("off", "Off"),
    ("mirror", "Mirror"),
]
EXTERNAL_MIDI_PC_PREVIEW_DEBOUNCE_SEC = 0.15

# General MIDI program names. Displayed as 001-128, sent as MIDI PC 0-127.
GM_PROGRAM_NAMES = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavi",
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
    "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
    "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)", "Electric Guitar (clean)",
    "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar", "Guitar harmonics",
    "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
    "Violin", "Viola", "Cello", "Contrabass",
    "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
    "String Ensemble 1", "String Ensemble 2", "SynthStrings 1", "SynthStrings 2",
    "Choir Aahs", "Voice Oohs", "Synth Voice", "Orchestra Hit",
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
    "French Horn", "Brass Section", "SynthBrass 1", "SynthBrass 2",
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet",
    "Piccolo", "Flute", "Recorder", "Pan Flute",
    "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
    "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass + lead)",
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
    "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
    "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
    "Sitar", "Banjo", "Shamisen", "Koto",
    "Kalimba", "Bag pipe", "Fiddle", "Shanai",
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
    "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]

def gm_program_label(index: int) -> str:
    index = max(0, min(127, int(index)))
    return f"{index + 1:03d} {GM_PROGRAM_NAMES[index]}"


def gm_category_index_for_program(index: int) -> int:
    return max(0, min(15, int(index) // 8))


def gm_category_base(category_index: int) -> int:
    return max(0, min(15, int(category_index))) * 8


def gm_current_category_name() -> str:
    return GM_CATEGORY_NAMES[gm_category_index_for_program(state.external_midi_pc_index)]


def gm_current_category_program_indices() -> list[int]:
    base = gm_category_base(gm_category_index_for_program(state.external_midi_pc_index))
    return list(range(base, min(base + 8, len(GM_PROGRAM_NAMES))))
BRIDGE_EXECUTABLE = "/home/pi/bin/uno_midi_bridge_sp"
BRIDGE_PORT_HINT = "UNO-bridge"
BRIDGE_AUTOSTART = False
FIXED_MIDI_SRC = None
LOG_DIR = "/home/pi/log/fluidardule"
FLUID_LOG_PATH = f"{LOG_DIR}/fluidsynth.log"
PLAYER_LOG_PATH = f"{LOG_DIR}/player.log"
YOSHIMI_LOG_PATH = f"{LOG_DIR}/yoshimi.log"
AMIXER_CONTROL = "PCM"
# Do not force ALSA mixer to 100% at service start.
# The first POT report from UNO-1, or the last saved pot-derived volume, owns startup volume.
FIX_VOLUME_AT_100 = False
POT_VOLUME_ENABLED = True
VOLUME_STATE_PATH = "/tmp/fluidardule_last_volume_percent"
DEFAULT_STARTUP_VOLUME_PERCENT = 85
# At startup the saved/default volume is only a temporary safety value.
# The physical POT position should own the real startup volume as soon as
# UNO-1 is ready.  Some firmware builds report POT only on movement, so the
# Pi asks for a short POT snapshot window after serial connection.
POT_STARTUP_SNAPSHOT_REQUEST_SEC = 5.0
POT_STARTUP_SNAPSHOT_REQUEST_INTERVAL_SEC = 0.5
DEVICE_POLL_INTERVAL_SEC = 3.0
MIDI_RECONNECT_STABLE_SEC = 1.5
SERIAL_HEARTBEAT_INTERVAL_SEC = 1.0
SERIAL_UI_STATUS_INTERVAL_SEC = 1.0
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
RENDER_MIN_INTERVAL = 0.10
# Diagnostic result 2026-06-20: continuous TFT rendering on Raspberry Pi 3B
# can disturb Yoshimi real-time audio. Keep normal UI responsiveness for
# FluidSynth/media, but throttle background redraws while Yoshimi is active.
YOSHIMI_RENDER_MIN_INTERVAL = 1.00
COMBI_RENDER_MIN_INTERVAL = 1.00
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

# Rename editor only: fixed-width text keeps the cursor aligned with characters.
MONO_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
]

MAIN_MENU = [
    "Sound",
    "Media Player",
    "Controls",
    "MIDI Mode",
    "DAC",
    "Extension",
]

QUICK_MENU_ITEMS = [
    "MIDI Panic",
    "Home",
    "Now Playing",
    "Sound",
    "USB Eject",
    "Save User Preset",
    "Arpeggio Speed",
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

USER_PRESET_PATH = "/home/pi/sf2/user_presets.json"
USER_COMBI_PATH = "/home/pi/sf2/user_combis.json"
COMBI_INPUT_CHANNEL = 1
COMBI_PREVIEW_FOOTER_HOLD_SEC = 1.5
USER_PRESET_PREVIEW_ON_HIGHLIGHT = True
# Delay User Preset preview while scrolling so only the final highlighted item loads.
USER_PRESET_PREVIEW_DEBOUNCE_SEC = 0.45
# Larger SF2 files need a little more settling time after FluidSynth starts.
FLUIDSYNTH_STARTUP_SETTLE_DEFAULT_SEC = 1.2
FLUIDSYNTH_STARTUP_SETTLE_LARGE_SEC = 2.4
FLUIDSYNTH_LARGE_SF2_NAMES = {"FluidR3_GM.sf2", "GeneralUser_GS.sf2"}

RADIO_STATIONS_PATH = "/home/pi/sf2/radio_stations.json"
RADIO_FAVORITES_PATH = "/home/pi/sf2/radio_favorites.json"

WIFI_INTERFACE = "wlan0"
WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
WPA_SUPPLICANT_CONF_FALLBACK = "/etc/wpa_supplicant/wpa_supplicant.conf"
WIFI_SELECTED_PRIORITY = 50
WIFI_OTHER_PRIORITY = 10
# Cache Wi-Fi status/config reads to avoid repeated sudo cat during UI redraws.
WIFI_STATUS_CACHE_SEC = 10.0
WIFI_KNOWN_SSIDS_CACHE_SEC = 180.0


DEFAULT_RADIO_STATIONS = [
    {"id": "somafm_groovesalad", "name": "SomaFM Groove Salad", "url": "https://ice2.somafm.com/groovesalad-128-mp3"},
    {"id": "somafm_dronezone", "name": "SomaFM Drone Zone", "url": "https://ice2.somafm.com/dronezone-128-mp3"},
    {"id": "somafm_defcon", "name": "SomaFM DEF CON", "url": "https://ice2.somafm.com/defcon-128-mp3"},
    {"id": "jazz24", "name": "Jazz24", "url": "https://live.wostreaming.net/direct/ppm-jazz24mp3-ibc1"},
    {"id": "somafm_secretagent", "name": "SomaFM Secret Agent", "url": "https://ice2.somafm.com/secretagent-128-mp3"},
    {"id": "somafm_lush", "name": "SomaFM Lush", "url": "https://ice2.somafm.com/lush-128-mp3"},
    {"id": "somafm_u80s", "name": "SomaFM Underground 80s", "url": "https://ice2.somafm.com/u80s-128-mp3"},
    {"id": "somafm_beatblender", "name": "SomaFM Beat Blender", "url": "https://ice2.somafm.com/beatblender-128-mp3"},
    {"id": "somafm_illstreet", "name": "SomaFM Illinois Street Lounge", "url": "https://ice2.somafm.com/illstreet-128-mp3"},
    {"id": "somafm_cliqhop", "name": "SomaFM Cliqhop", "url": "https://ice2.somafm.com/cliqhop-128-mp3"},
    {"id": "somafm_folkfwd", "name": "SomaFM Folk Forward", "url": "https://ice2.somafm.com/folkfwd-128-mp3"},
    {"id": "somafm_metal", "name": "SomaFM Metal Detector", "url": "https://ice2.somafm.com/metal-128-mp3"},
]
USER_PRESET_RENAME_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.,()"
USER_PRESET_RENAME_MAX_LEN = 32

POWER_MENU_ITEMS = ["Cancel", "Halt", "Restart Software", "Reboot"]
POWER_CONFIRM_ITEMS = ["No", "Yes"]
FLUID_ARDULE_SERVICE = "fluid_ardule.service"
RESTART_SOFTWARE_MARKER = "/tmp/fluidardule_restart_software_pending"

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
#   - menu/list navigation: use the signed ENC magnitude from UNO as row delta
#   - Sound Edit value editing: use the signed ENC magnitude from UNO and scale it
#     non-linearly according to the current UNO acceleration profile
SOUND_EDIT_SEND_ALL_CHANNELS = True
# Keep the debug logging hooks in the code, but leave them disabled for normal use.
# Set this to True temporarily when verifying CC transmission with journalctl.
SOUND_EDIT_CC_DEBUG = False
# Encoder trace diagnostics. Enable this temporarily while running the script
# from a terminal (not as a systemd service) to see every ENC event received
# from UNO-1 and the resulting UI/value movement. Keep False for normal use.
ENCODER_TRACE = False
# Encoder acceleration profile sync diagnostics. Enable temporarily to see
# Pi -> UNO ACCELSET:n decisions when UI context changes or serial reconnects.
ACCEL_PROFILE_TRACE = False
# If True, ACCEL:n reports from UNO-1 also produce a short TFT footer message.
# Keep False for normal context-specific profile switching because UNO LCD
# already shows the active P0/P1/P2/P3 profile.
ACCEL_PROFILE_TFT_FEEDBACK = False
ENCODER_ACCEL_DEFAULT_PROFILE = 0
ENCODER_ACCEL_OPTIONS = {
    0: "P0 Precise",
    1: "P1 Fine",
    2: "P2 Normal",
    3: "P3 Fast",
}
# Pi-side default acceleration policy. UNO-1 still applies the acceleration,
# but Raspberry Pi selects the suitable profile for the current UI context.
# Long-list navigation gets P1; precise top-level/menu screens get P0;
# continuous/value editing gets P2. Unknown contexts fall back to P0.
UI_ACCEL_PROFILE_DEFAULT = 0
UI_ACCEL_PROFILE_BY_CONTEXT = {
    "main": 0,
    "file_source": 0,
    "file_browser": 1,
    "radio_browser": 1,
    "quick_menu": 0,
    "player": 0,
    "power_menu": 0,
    "restart_wait": 0,
    "sound_edit": 2,
    "submenu:preset": 1,
    "submenu:preset_category": 1,
    "submenu:user_preset_load": 1,
    "submenu:combi_load": 1,
    "submenu:combi_detail": 1,
    "submenu:external_midi_pc": 1,
    "submenu:arp_speed": 2,
    "submenu:user_preset_rename": 0,
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
FOOTER_ALT_INTERVAL_SEC = 2.0
VOLUME_FOOTER_HOLD_SEC = 1.8
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
    ])
    bridge_proc: subprocess.Popen | None = None
    bridge_running: bool = False
    bridge_port_name: str = BRIDGE_PORT_HINT
    midi_display_text: str = "RAW"
    selected_alsa_input: str | None = None
    selected_alsa_input_name: str | None = None
    preferred_seq_port: str | None = None
    preferred_seq_name: str | None = None

    external_midi_out_mode: str = "off"
    external_midi_present: bool = False
    external_midi_port: str | None = None
    external_midi_name: str | None = None
    preferred_external_midi_port: str | None = None
    preferred_external_midi_name: str | None = None
    external_midi_connected: bool = False
    external_midi_pc_index: int = 0
    external_midi_pc_channel: int = 1
    arp_bpm: int = ARP_BPM_DEFAULT
    pending_external_midi_pc_index: int | None = None
    pending_external_midi_pc_due: float = 0.0

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
    last_yoshimi_render_time: float = 0.0

    ui_mode: str = "main"      # main / submenu / file_source / file_browser / player
    menu_index: int = 0
    submenu_index: int = 0
    submenu_key: str | None = None
    preset_entries: list[dict] = field(default_factory=list)
    preset_index: int = 0
    preset_sf_index: int | None = None
    preset_source_name: str = ""
    category_entries: list[str] = field(default_factory=list)
    category_index: int = 0
    category_source_sf_index: int | None = None
    category_source_name: str = ""
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
    radio_entries: list[dict] = field(default_factory=list)
    radio_index: int = 0
    radio_view_mode: str = "all"   # all / favorites

    wifi_enabled: bool = True
    wifi_current_ssid: str = ""
    wifi_scan_results: list[str] = field(default_factory=list)
    wifi_known_ssids: list[str] = field(default_factory=list)


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
    last_volume_display_time: float = 0.0
    last_footer_alt_slot: int = -1
    last_pot_raw: int = -1
    initial_pot_volume_applied: bool = False
    pot_startup_request_until: float = 0.0
    last_pot_startup_request_time: float = 0.0
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
    player_return_mode: str | None = None  # file_browser / radio_browser
    player_radio_station_id: str | None = None
    player_notice_text: str = ""
    player_notice_until: float = 0.0

    pending_resume_after_sf_apply: bool = False

    user_preset_entries: list[dict] = field(default_factory=list)
    user_preset_target_index: int = 0
    pending_user_preset_preview_index: int | None = None
    pending_user_preset_preview_due: float = 0.0
    previewed_user_preset_index: int | None = None
    user_preset_rename_text: str = ""
    user_preset_rename_cursor: int = 0
    current_user_preset_name: str | None = None
    current_user_preset_kind: str | None = None
    combi_entries: list[dict] = field(default_factory=list)
    current_combi_name: str | None = None
    combi_active: bool = False
    combi_parts: list[dict] = field(default_factory=list)
    combi_input_channel: int = COMBI_INPUT_CHANNEL
    combi_router_signature: str = ""
    combi_preview_active: bool = False
    combi_browse_snapshot: dict | None = None
    previewed_combi_index: int | None = None
    modal_message: str = ""
    modal_submessage: str = ""
    modal_until: float = 0.0

    # Lightweight UI caches. Sound Source rendering should not repeatedly read
    # preset JSON files on every draw; cache counts and invalidate only when the
    # underlying User Preset list is changed.
    soundfont_count_cache: dict[int, tuple[int, int]] = field(default_factory=dict)
    user_preset_count_cache: int | None = None
    sound_source_cache_preload_started: bool = False
    sound_source_cache_preload_done: bool = False

    # Ignore short burst of stale/noisy UI events after UNO-1 serial reconnect/reset.
    serial_input_ignore_until: float = 0.0


state = RuntimeState(sf_index=0, sf_name=SOUNDFONTS[0][1])
event_q: queue.Queue[str] = queue.Queue()
fluid_proc = None
fluid_log_handle = None
yoshimi_log_handle = None
player_proc = None
player_ext_midi_proc = None
player_log_handle = None
serial_handle = None
last_enc_time = 0.0
serial_lock = threading.Lock()
last_serial_hb_time = 0.0
last_serial_ui_status_time = 0.0
last_serial_ui_status_sent = ""
serial_write_error_count = 0
serial_read_error_count = 0
midi_activity_proc = None
midi_activity_signature = ""
midi_activity_thread_handle = None
combi_router_proc = None
combi_router_thread_handle = None
combi_router_generation = 0
_wifi_status_cache_until = 0.0
_wifi_known_ssids_cache_until = 0.0
_wifi_known_ssids_cache: list[str] = []
last_accel_context_key: str | None = None
last_sent_accel_profile: int | None = None



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


def show_player_notice(text: str, hold_sec: float = 1.5) -> None:
    """Temporarily show a centered notice on the Now Playing screen."""
    state.player_notice_text = str(text or "")
    state.player_notice_until = time.time() + float(hold_sec)
    mark_dirty(state.player_notice_text)


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


def refresh_status_once(event: str = "Status refreshed") -> None:
    """Refresh slow-changing system/device status only on explicit user request.

    Fluid Ardule is now event-driven: normal button/encoder/POT events redraw the
    current screen, but they do not poll slow status values. UP long-press calls
    this function to update Load/Temp, MIDI/DAC/USB/Wi-Fi state, then redraw once.
    A short timed modal confirms the manual refresh using the existing popup style.
    """
    state.last_system_status_poll_time = time.time()
    state.cpu_load_text = get_cpu_load_text()
    state.cpu_temp_text = get_cpu_temp_text()
    periodic_device_poll(force=True)
    periodic_usb_poll(force=True)
    refresh_wifi_status(force=True)
    refresh_midi_display_text()
    mark_dirty(event)
    show_timed_modal_message(event, hold_sec=0.8, subtext=" ")


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
            # Keep volume visible in the footer while the physical pot is being moved.
            state.last_volume_display_time = time.time()
            mark_dirty(f"Volume {percent}%")
    except Exception as exc:
        if announce:
            mark_dirty(f"Volume set failed: {exc}")


def save_volume_state(percent: int) -> None:
    try:
        Path(VOLUME_STATE_PATH).write_text(str(max(0, min(100, int(percent)))), encoding="utf-8")
    except Exception:
        pass


def load_saved_volume_state(default: int = 60) -> int:
    try:
        value = int(Path(VOLUME_STATE_PATH).read_text(encoding="utf-8").strip())
        return max(0, min(100, value))
    except Exception:
        return max(0, min(100, int(default)))


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

    # Startup volume policy 260627c:
    # Start from a fixed safe line-level value, then use soft takeover.
    # Do not let the first POT report jump the volume to an unrelated physical
    # knob position.  Volume resumes only after the pot enters the pickup range.
    if not state.initial_pot_volume_applied:
        state.initial_pot_volume_applied = True
        state.pot_startup_request_until = 0.0
        state.pot_volume_captured = False

    # Soft takeover for volume mode. If the pot has been used as a parameter
    # controller, its physical angle may no longer match the current volume.
    # When returning to VOL mode, wait until the pot is moved near the existing
    # logical volume before applying it again. This avoids sudden volume jumps.
    if not state.pot_volume_captured:
        if abs(percent - state.volume_percent) <= POT_VOLUME_PICKUP_THRESHOLD:
            state.pot_volume_captured = True
            show_timed_modal_message("Volume Active", hold_sec=0.8, subtext="Knob synchronized")
        else:
            maybe_pulse_pot_led(percent)
            return

    if abs(percent - state.volume_percent) < POT_VOLUME_PERCENT_THRESHOLD:
        return
    set_output_volume(percent, announce=True)
    save_volume_state(percent)
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
    entries.append({"type": "source", "name": "radio", "display": "Internet radio"})
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
    if item["name"] == "radio":
        enter_radio_browser()
        return
    state.browser_path = USB_MOUNT_POINT if item["name"] == "usb" else resolve_file_root()
    refresh_browser_entries()
    state.browser_index = 0
    state.ui_mode = "file_browser"
    invalidate_full_display()
    mark_dirty(item["display"])


def ensure_radio_files_on_demand() -> None:
    """Create radio JSON files only when the Radio screen is used.

    This keeps startup/main-loop/UNO timing identical to the stable script.
    """
    sf2_dir = Path("/home/pi/sf2")
    sf2_dir.mkdir(parents=True, exist_ok=True)
    stations_path = Path(RADIO_STATIONS_PATH)
    favorites_path = Path(RADIO_FAVORITES_PATH)
    if not stations_path.exists():
        stations_path.write_text(json.dumps(DEFAULT_RADIO_STATIONS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not favorites_path.exists():
        favorites_path.write_text("[]\n", encoding="utf-8")


def load_radio_stations() -> list[dict]:
    ensure_radio_files_on_demand()
    try:
        data = json.loads(Path(RADIO_STATIONS_PATH).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception as exc:
        log(f"radio_stations.json load failed: {exc}")
        data = []

    by_id: dict[str, dict] = {}
    for item in data + DEFAULT_RADIO_STATIONS:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or item.get("name") or "").strip()
        name = str(item.get("name") or sid).strip()
        url = str(item.get("url") or "").strip()
        if not sid or not name or not url:
            continue
        if sid not in by_id:
            by_id[sid] = {"id": sid, "name": name, "url": url}
    return list(by_id.values())


def load_radio_favorites() -> set[str]:
    ensure_radio_files_on_demand()
    try:
        data = json.loads(Path(RADIO_FAVORITES_PATH).read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}
    except Exception as exc:
        log(f"radio_favorites.json load failed: {exc}")
    return set()


def save_radio_favorites(favorites: set[str]) -> None:
    ensure_radio_files_on_demand()
    Path(RADIO_FAVORITES_PATH).write_text(json.dumps(sorted(favorites), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_radio_entries_for_view(view_mode: str) -> list[dict]:
    stations = load_radio_stations()
    if view_mode == "favorites":
        favorites = load_radio_favorites()
        return [s for s in stations if str(s.get("id", "")).strip() in favorites]
    return stations


def enter_radio_browser(view_mode: str = "all", *, keep_index: bool = False) -> None:
    if view_mode not in {"all", "favorites"}:
        view_mode = "all"
    old_index = state.radio_index
    state.radio_view_mode = view_mode
    state.radio_entries = load_radio_entries_for_view(view_mode)
    state.radio_index = clamp_index(old_index if keep_index else 0, len(state.radio_entries))
    state.ui_mode = "radio_browser"
    invalidate_full_display()
    if view_mode == "favorites":
        mark_dirty(f"Radio favorites: {len(state.radio_entries)}")
    else:
        mark_dirty(f"Radio: {len(state.radio_entries)} stations")


def current_radio_station() -> dict | None:
    if radio_index_is_favorites_entry():
        return None
    if not state.radio_entries:
        return None
    return state.radio_entries[clamp_index(radio_station_index(), len(state.radio_entries))]


def radio_display_labels() -> list[str]:
    favorites = load_radio_favorites()
    labels = []
    if state.radio_view_mode == "all":
        labels.append("★ Favorites")
    for station in state.radio_entries:
        star = "★ " if str(station.get("id", "")) in favorites else "  "
        labels.append(star + str(station.get("name", "Radio")))
    return labels


def radio_index_is_favorites_entry() -> bool:
    return state.radio_view_mode == "all" and state.radio_index == 0


def radio_station_index() -> int:
    return state.radio_index - 1 if state.radio_view_mode == "all" else state.radio_index


def find_radio_station_by_id(station_id: str | None) -> dict | None:
    sid = str(station_id or "").strip()
    if not sid:
        return None
    for station in load_radio_stations():
        if str(station.get("id", "")).strip() == sid:
            return station
    return None


def toggle_current_radio_favorite() -> None:
    station = current_radio_station()
    if not station:
        mark_dirty("No station")
        return
    sid = str(station.get("id", "")).strip()
    if not sid:
        mark_dirty("No station id")
        return
    favorites = load_radio_favorites()
    if sid in favorites:
        favorites.remove(sid)
        msg = "Favorite removed"
    else:
        favorites.add(sid)
        msg = "Favorite added"
    save_radio_favorites(favorites)
    if state.radio_view_mode == "favorites":
        old_index = state.radio_index
        state.radio_entries = load_radio_entries_for_view("favorites")
        state.radio_index = clamp_index(old_index, len(state.radio_entries))
    invalidate_full_display()
    mark_dirty(msg)

def toggle_radio_favorite_by_id(station_id: str | None, station_name: str | None = None) -> None:
    """Toggle favorite for the currently playing radio station.

    Player mode does not necessarily have a valid radio_browser selection, so
    do not rely on current_radio_station() here.
    This is used by the RIGHT/Favorite button while Internet radio is playing.
    """
    sid = str(station_id or "").strip()
    if not sid:
        mark_dirty("No station id")
        return

    # Resolve a human-readable name only for status text.  Do not require the
    # station list to be available; the station id is the authoritative key.
    name = str(station_name or "").strip()
    if not name:
        station = find_radio_station_by_id(sid)
        if station:
            name = str(station.get("name", "")).strip()

    favorites = load_radio_favorites()
    if sid in favorites:
        favorites.remove(sid)
        msg = "Favorite removed"
    else:
        favorites.add(sid)
        msg = "Favorite added"
    save_radio_favorites(favorites)

    # Keep the favorites view coherent if the user returns there immediately.
    if state.radio_view_mode == "favorites":
        old_index = state.radio_index
        state.radio_entries = load_radio_entries_for_view("favorites")
        state.radio_index = clamp_index(old_index, len(state.radio_entries))

    invalidate_full_display()
    if name:
        mark_dirty(f"{msg}: {shorten_text(name, 18)}")
    else:
        mark_dirty(msg)



def play_adjacent_radio_station(delta: int) -> None:
    """Move to the previous/next station while Internet radio is playing.

    This mirrors file playback's adjacent-item behavior, but uses the active
    radio view (all/favorites) and does not wrap at either end.
    """
    if state.player_proc_kind != "radio" and state.player_return_mode != "radio_browser":
        mark_dirty("Radio not active")
        return

    if not state.radio_entries:
        state.radio_entries = load_radio_entries_for_view(state.radio_view_mode)
    if not state.radio_entries:
        show_player_notice("No stations")
        return

    current_id = str(state.player_radio_station_id or "").strip()
    current_pos = None
    if current_id:
        for i, station in enumerate(state.radio_entries):
            if str(station.get("id", "")).strip() == current_id:
                current_pos = i
                break

    if current_pos is None:
        # Fall back to the browser selection.  In the all-stations view the
        # first display row is "Favorites", so convert the display index back
        # to a station index.
        current_pos = radio_station_index() if state.radio_view_mode == "all" else state.radio_index
        current_pos = clamp_index(current_pos, len(state.radio_entries))

    next_pos = current_pos + int(delta)
    if next_pos < 0:
        show_player_notice("First station")
        return
    if next_pos >= len(state.radio_entries):
        show_player_notice("Last station")
        return

    state.radio_index = next_pos + (1 if state.radio_view_mode == "all" else 0)
    station = state.radio_entries[next_pos]
    log(f"RADIO adjacent delta={delta} next={station.get('name','Radio')}")
    start_radio_station(station)

def start_radio_station(station: dict) -> None:
    url = str(station.get("url", "")).strip()
    name = str(station.get("name", "Radio")).strip() or "Radio"
    if not url:
        mark_dirty("No radio URL")
        return

    send_ui_status("BUSY", force=True)
    global player_proc
    stop_player_only()
    stop_fluidsynth()

    audio = state.audio_device
    mpv_audio = "alsa/default" if audio == "default" else f"alsa/{audio}"
    cmd = [
        "mpv",
        "--no-video",
        "--really-quiet",
        "--no-terminal",
        "--idle=no",
        f"--audio-device={mpv_audio}",
        url,
    ]

    show_modal_message("Connecting radio...", shorten_text(name, 24))
    log(f"RADIO cmd={' '.join(cmd)}")
    log_handle = open_player_log()
    try:
        player_proc = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, preexec_fn=os.setsid, text=True)
    except FileNotFoundError:
        restart_engine(state.sf_index, state.dac_index, manage_modal=False)
        clear_modal_message()
        mark_dirty("mpv missing")
        send_ui_status("READY", force=True)
        return
    except Exception as exc:
        restart_engine(state.sf_index, state.dac_index)
        clear_modal_message()
        mark_dirty(f"Radio failed: {exc}")
        send_ui_status("READY", force=True)
        return

    state.player_path = name
    state.player_proc_kind = "radio"
    state.player_paused = False
    state.player_status = "Playing"
    state.player_stop_requested = False
    state.player_origin_dir = None
    state.player_return_mode = "radio_browser"
    state.player_radio_station_id = str(station.get("id", "")).strip() or None
    state.ui_mode = "player"
    invalidate_full_display()
    set_play_led("ON")
    clear_modal_message()
    mark_dirty(f"Radio: {name}")
    send_ui_status("READY", force=True)



# =========================================================
# Wi-Fi helpers
# =========================================================

def wifi_conf_paths() -> list[str]:
    """Return existing wpa_supplicant config paths, wlan0-specific first.

    Raspberry Pi OS may run wpa_supplicant@wlan0 with
    /etc/wpa_supplicant/wpa_supplicant-wlan0.conf, while older setups use
    /etc/wpa_supplicant/wpa_supplicant.conf.  Keep both in sync when both
    exist, but prefer the wlan0-specific file for reading.
    """
    paths: list[str] = []
    for p in (WPA_SUPPLICANT_CONF, WPA_SUPPLICANT_CONF_FALLBACK):
        if p and p not in paths and Path(p).exists():
            paths.append(p)
    if not paths:
        paths.append(WPA_SUPPLICANT_CONF)
    return paths


def read_wifi_conf_text(path: str) -> str:
    """Read a root-protected wpa_supplicant config safely.

    The config is normally 600 root:root. Fluid Ardule usually runs as the
    pi user, so direct open() may fail even though systemd can use the file.
    Try normal read first, then fall back to sudo cat with non-interactive
    sudo. This keeps the main Python process non-root.
    """
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except PermissionError:
        code, out = run_cmd(["sudo", "-n", "cat", path])
        if code == 0:
            return out
        log(f"Wi-Fi config sudo read failed ({path}): {out}")
        return ""
    except Exception as exc:
        log(f"Wi-Fi config read failed ({path}): {exc}")
        return ""


def parse_wpa_supplicant_networks(conf_path: str | None = None, *, force: bool = False) -> list[str]:
    """Return SSIDs listed in the active wpa_supplicant config.

    The config is root-protected on this image, so a read may fall back to
    sudo cat.  Cache the common no-argument path because UI redraws can ask
    for Wi-Fi labels frequently, and configured SSIDs rarely change during
    normal performance.  Explicit Wi-Fi actions pass force=True.
    """
    global _wifi_known_ssids_cache_until, _wifi_known_ssids_cache
    now = time.time()
    if conf_path is None and not force and now < _wifi_known_ssids_cache_until:
        return list(_wifi_known_ssids_cache)

    paths = [conf_path] if conf_path else wifi_conf_paths()
    text = ""
    for path in paths:
        text = read_wifi_conf_text(path)
        if text:
            break
    if not text:
        if conf_path is None:
            _wifi_known_ssids_cache = []
            _wifi_known_ssids_cache_until = now + WIFI_KNOWN_SSIDS_CACHE_SEC
        return []

    ssids: list[str] = []
    for block in re.findall(r'network\s*=\s*\{(.*?)\}', text, flags=re.S):
        m = re.search(r'^\s*ssid\s*=\s*"((?:\\.|[^"\\])*)"', block, flags=re.M)
        if not m:
            continue
        ssid = bytes(m.group(1), "utf-8").decode("unicode_escape", errors="ignore")
        if ssid and ssid not in ssids:
            ssids.append(ssid)

    if conf_path is None:
        _wifi_known_ssids_cache = list(ssids)
        _wifi_known_ssids_cache_until = now + WIFI_KNOWN_SSIDS_CACHE_SEC
    return ssids


def wifi_is_enabled() -> bool:
    code, out = run_cmd(["rfkill", "list", "wifi"])
    if code == 0 and out:
        return "Soft blocked: yes" not in out
    return Path(f"/sys/class/net/{WIFI_INTERFACE}").exists()


def wifi_current_ssid() -> str:
    code, out = run_cmd(["iwgetid", WIFI_INTERFACE, "-r"])
    if code == 0 and out.strip():
        return out.strip()
    # Do not depend on wpa_cli here. Some interface-specific wpa_supplicant
    # setups connect normally but do not expose the default control socket.
    return ""


def refresh_wifi_status(*, force: bool = False) -> None:
    """Refresh Wi-Fi status with a short cache for UI redraw safety."""
    global _wifi_status_cache_until
    now = time.time()
    if not force and now < _wifi_status_cache_until:
        return
    state.wifi_enabled = wifi_is_enabled()
    state.wifi_current_ssid = wifi_current_ssid() if state.wifi_enabled else ""
    state.wifi_known_ssids = parse_wpa_supplicant_networks(force=force)
    _wifi_status_cache_until = now + WIFI_STATUS_CACHE_SEC


def wifi_status_label(*, short: bool = False) -> str:
    refresh_wifi_status()
    if not state.wifi_enabled:
        return "Off"
    if state.wifi_current_ssid:
        return state.wifi_current_ssid if short else f"Connected: {state.wifi_current_ssid}"
    return "On" if short else "On / not connected"


def restart_wifi_services() -> bool:
    """Restart OS-managed Wi-Fi services and let priority choose the AP."""
    ok = True
    commands = [
        ["sudo", "-n", "systemctl", "restart", f"wpa_supplicant@{WIFI_INTERFACE}"],
        ["sudo", "-n", "systemctl", "restart", "dhcpcd"],
    ]
    for cmd in commands:
        code, out = run_cmd(cmd)
        if code != 0:
            ok = False
            log(f"Wi-Fi service command failed: {' '.join(cmd)} :: {out}")
    return ok


def set_wifi_enabled(enabled: bool) -> bool:
    if enabled:
        run_cmd(["sudo", "-n", "rfkill", "unblock", "wifi"])
        run_cmd(["sudo", "-n", "ip", "link", "set", WIFI_INTERFACE, "up"])
        restart_wifi_services()
    else:
        run_cmd(["sudo", "-n", "rfkill", "block", "wifi"])
    refresh_wifi_status(force=True)
    return state.wifi_enabled == enabled


def scan_wifi_ssids() -> list[str]:
    """Show configured SSIDs that are currently visible on the air.

    Prefer iw/iwlist because this project should not depend on wpa_cli control
    sockets; automatic OS connection already works through systemd.
    """
    known = parse_wpa_supplicant_networks(force=True)
    state.wifi_known_ssids = known
    if not wifi_is_enabled():
        state.wifi_scan_results = []
        refresh_wifi_status(force=True)
        return []

    detected: set[str] = set()

    code, out = run_cmd(["sudo", "-n", "iw", "dev", WIFI_INTERFACE, "scan"])
    if code == 0 and out:
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("SSID: "):
                ssid = line.split("SSID: ", 1)[1].strip()
                if ssid:
                    detected.add(ssid)

    if not detected:
        code, out = run_cmd(["sudo", "-n", "iwlist", WIFI_INTERFACE, "scan"])
        if code == 0:
            for ssid in re.findall(r'ESSID:"(.*?)"', out):
                if ssid:
                    detected.add(ssid)

    visible_known = [ssid for ssid in known if ssid in detected]
    state.wifi_scan_results = visible_known
    refresh_wifi_status(force=True)
    return visible_known


def update_priorities_in_wpa_text(text: str, selected_ssid: str) -> tuple[str, bool]:
    """Return config text with selected_ssid priority raised."""
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        block = match.group(0)
        body = match.group(1)
        m = re.search(r'^\s*ssid\s*=\s*"((?:\\.|[^"\\])*)"', body, flags=re.M)
        if not m:
            return block
        ssid = bytes(m.group(1), "utf-8").decode("unicode_escape", errors="ignore")
        if not ssid:
            return block
        priority = WIFI_SELECTED_PRIORITY if ssid == selected_ssid else WIFI_OTHER_PRIORITY
        new_line = f"        priority={priority}"
        if re.search(r'^\s*priority\s*=.*$', body, flags=re.M):
            new_body = re.sub(r'^\s*priority\s*=.*$', new_line, body, count=1, flags=re.M)
        else:
            # Insert before the closing brace while preserving the existing block.
            new_body = body.rstrip() + "\n" + new_line + "\n"
        new_block = "network={" + new_body + "}"
        if new_block != block:
            changed = True
        return new_block

    new_text = re.sub(r'network\s*=\s*\{(.*?)\}', repl, text, flags=re.S)
    return new_text, changed


def write_text_with_sudo(path: str, text: str) -> bool:
    tmp = f"/tmp/fluidardule-{Path(path).name}"
    try:
        Path(tmp).write_text(text, encoding="utf-8")
    except Exception as exc:
        log(f"Wi-Fi temp config write failed: {exc}")
        return False
    code, out = run_cmd(["sudo", "-n", "install", "-m", "600", "-o", "root", "-g", "root", tmp, path])
    try:
        Path(tmp).unlink(missing_ok=True)
    except Exception:
        pass
    if code != 0:
        log(f"Wi-Fi config install failed ({path}): {out}")
        return False
    return True


def set_wifi_priority_for_ssid(ssid: str) -> bool:
    """Raise selected SSID priority in existing config files."""
    ok_any = False
    for path in wifi_conf_paths():
        text = read_wifi_conf_text(path)
        if not text:
            continue
        new_text, changed = update_priorities_in_wpa_text(text, ssid)
        if not changed:
            ok_any = True
            continue
        if write_text_with_sudo(path, new_text):
            ok_any = True
            # Config changed; force the next read to see the new priorities.
            global _wifi_known_ssids_cache_until, _wifi_status_cache_until
            _wifi_known_ssids_cache_until = 0.0
            _wifi_status_cache_until = 0.0
    return ok_any


def wait_for_wifi_connection(ssid: str, timeout_sec: float = 15.0) -> bool:
    """Wait until the selected SSID becomes the active association."""
    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        refresh_wifi_status(force=True)
        if state.wifi_current_ssid == ssid:
            return True
        time.sleep(0.75)
    refresh_wifi_status(force=True)
    return state.wifi_current_ssid == ssid


def connect_wifi_ssid(ssid: str) -> bool:
    """Select Wi-Fi by rewriting priority and restarting OS Wi-Fi services.

    This intentionally avoids wpa_cli select_network because this Fluid Ardule
    image already connects reliably at boot using wpa_supplicant priority, even
    when the wpa_cli control socket is unavailable.
    """
    ssid = str(ssid or "").strip()
    if not ssid:
        return False
    if ssid not in parse_wpa_supplicant_networks(force=True):
        mark_dirty("Wi-Fi network not configured")
        return False

    # Hotfix 2026-05-27:
    # If the selected SSID is already connected, do not rewrite priority or
    # restart Wi-Fi services. A service restart can briefly disturb USB/serial
    # timing on the Raspberry Pi and may make UNO-1 appear disconnected.
    refresh_wifi_status(force=True)
    if state.wifi_enabled and state.wifi_current_ssid == ssid:
        mark_dirty(f"Already connected: {ssid}")
        return True

    if not wifi_is_enabled():
        set_wifi_enabled(True)
        refresh_wifi_status(force=True)
        if state.wifi_enabled and state.wifi_current_ssid == ssid:
            mark_dirty(f"Already connected: {ssid}")
            return True

    if not set_wifi_priority_for_ssid(ssid):
        mark_dirty("Wi-Fi config update failed")
        return False

    show_modal_message("Switching Wi-Fi...", shorten_text(ssid, 24))
    send_ui_status("BUSY", force=True)
    services_ok = restart_wifi_services()
    ok = wait_for_wifi_connection(ssid, timeout_sec=15.0)
    clear_modal_message()
    send_ui_status("READY", force=True)
    if not ok:
        log(f"Wi-Fi priority switch timeout for {ssid}; current={state.wifi_current_ssid or '-'}; services_ok={services_ok}")
    return ok


def wifi_menu_options() -> list[tuple[str, bool]]:
    refresh_wifi_status()
    rows = [(f"Wi-Fi: {'On' if state.wifi_enabled else 'Off'}", state.wifi_enabled)]
    rows.append(("Scan known networks", False))
    if state.wifi_scan_results:
        rows.extend((ssid, ssid == state.wifi_current_ssid) for ssid in state.wifi_scan_results)
    else:
        rows.append(("No configured network found", False))
    return rows

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


def list_raw_midi_outputs() -> list[tuple[str, str]]:
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
        if "O" not in direction:
            continue
        entries.append((port, name))
    return entries


def find_external_midi_raw_output() -> tuple[str | None, str | None]:
    for port, name in list_raw_midi_outputs():
        text = f"{port} {name}".lower()
        if any(hint.lower() in text for hint in EXTERNAL_MIDI_NAME_HINTS):
            return port, name
    return None, None


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


def current_ui_link_status() -> str:
    # LINK/HB means the Pi process is alive. UI status means the main loop is
    # intentionally able to accept UNO control events. Keep playback itself
    # READY; reserve BUSY for modal/system operations where input should not be
    # trusted or may be delayed.
    if state.ui_mode == "restart_wait":
        return "BUSY"
    if state.ui_mode == "power_menu" and state.power_confirm_action in {"EXEC_HALT", "EXEC_REBOOT", "EXEC_RESTART_SOFTWARE"}:
        return "BUSY"
    if state.usb_eject_confirm:
        return "BUSY"
    return "READY"


def send_ui_status(status: str, *, force: bool = False) -> bool:
    global last_serial_ui_status_time, last_serial_ui_status_sent
    status = status.strip().upper()
    if status not in {"READY", "BUSY"}:
        status = "READY"
    now = time.time()
    if (not force) and status == last_serial_ui_status_sent and (now - last_serial_ui_status_time) < SERIAL_UI_STATUS_INTERVAL_SEC:
        return False
    if send_serial_line(f"UI:{status}"):
        last_serial_ui_status_sent = status
        last_serial_ui_status_time = now
        return True
    return False


def periodic_serial_ui_status() -> None:
    send_ui_status(current_ui_link_status())


def encoder_accel_context_key() -> str:
    """Return a compact key for Pi-selected encoder acceleration policy."""
    if state.ui_mode == "submenu":
        return f"submenu:{state.submenu_key or ''}"
    return str(state.ui_mode or "main")


def desired_encoder_accel_profile() -> int:
    """Choose the default encoder acceleration profile for the current UI."""
    key = encoder_accel_context_key()
    profile = UI_ACCEL_PROFILE_BY_CONTEXT.get(key, UI_ACCEL_PROFILE_DEFAULT)
    try:
        return max(0, min(3, int(profile)))
    except Exception:
        return UI_ACCEL_PROFILE_DEFAULT


def sync_encoder_accel_profile(*, force: bool = False, reason: str = "") -> None:
    """Send the UI-context-specific acceleration profile to UNO-1.

    UNO-1 owns the low-level encoder acceleration and displays the active
    P0/P1/P2/P3 profile on its LCD.  The Pi only selects the desired profile
    for the current UI context and sends ACCELSET:n when the context changes
    or after serial reconnect.
    """
    global last_accel_context_key, last_sent_accel_profile
    if serial_handle is None:
        return
    key = encoder_accel_context_key()
    profile = desired_encoder_accel_profile()
    if (not force) and key == last_accel_context_key and profile == last_sent_accel_profile:
        return
    if send_serial_line(f"ACCELSET:{profile}"):
        last_accel_context_key = key
        last_sent_accel_profile = profile
        state.encoder_accel_profile = profile
        state.encoder_accel_pending_profile = profile
        if ACCEL_PROFILE_TRACE:
            suffix = f" reason={reason}" if reason else ""
            log(f"ACCEL_PROFILE ui={key} -> P{profile}{suffix}")


def request_startup_pot_snapshot_window() -> None:
    """Ask UNO-1 to report the physical POT position soon after serial opens.

    This keeps startup volume owned by the knob, not by the saved/default
    fallback.  Older UNO firmware may ignore REQ:POT; in that case this is
    harmless, and normal POT movement still works.
    """
    now = time.time()
    state.pot_startup_request_until = now + POT_STARTUP_SNAPSHOT_REQUEST_SEC
    state.last_pot_startup_request_time = 0.0


def periodic_startup_pot_snapshot_request() -> None:
    if state.initial_pot_volume_applied:
        return
    now = time.time()
    if now > state.pot_startup_request_until:
        return
    if now - state.last_pot_startup_request_time < POT_STARTUP_SNAPSHOT_REQUEST_INTERVAL_SEC:
        return
    state.last_pot_startup_request_time = now
    send_serial_line("REQ:POT")


def ack_uno_event(kind: str) -> None:
    kind = kind.strip().upper()
    if kind in {"BTN", "ENC"}:
        send_serial_line(f"ACK:{kind}")


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
    if state.midi_mode in {"alsa_midi", "uno2_bridge_seq", "external_midi_seq"}:
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
        self.font_rename_mono = self._load_mono_font(22)
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

    def _load_mono_font(self, size: int):
        for path in MONO_FONT_CANDIDATES:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return self._load_font(size)

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
            "player_notice_text": state.player_notice_text,
            "player_notice_until_active": time.time() < state.player_notice_until,
            "footer_alt_slot": self._footer_alt_slot(),
            "volume_percent": state.volume_percent,
            "last_volume_display_active": time.time() - state.last_volume_display_time < VOLUME_FOOTER_HOLD_SEC,
            "uno_footer_text": self._uno_footer_text(),
            "modal_message": state.modal_message,
            "modal_until_active": time.time() < state.modal_until,
            "modal_submessage": state.modal_submessage,
            "wifi_enabled": state.wifi_enabled,
            "wifi_current_ssid": state.wifi_current_ssid,
            "header_version_label": self._display_script_version(),
            "header_wifi_label": self._header_wifi_text(),
            "wifi_scan_results": tuple(state.wifi_scan_results),
        }

    def _footer_changed(self, prev: dict | None) -> bool:
        if prev is None:
            return True
        state_keys = ("last_event", "cpu_load_text", "cpu_temp_text", "midi_display_text", "midi_connected", "usb_mounted", "transient_footer_text", "volume_percent")
        if any(prev.get(k) != getattr(state, k) for k in state_keys):
            return True
        current_snapshot_keys = {
            "footer_alt_slot": self._footer_alt_slot(),
            "last_volume_display_active": time.time() - state.last_volume_display_time < VOLUME_FOOTER_HOLD_SEC,
            "uno_footer_text": self._uno_footer_text(),
        }
        return any(prev.get(k) != v for k, v in current_snapshot_keys.items())

    def _main_values_changed(self, prev: dict | None) -> bool:
        if prev is None:
            return True
        current = [self._main_menu_value(i) for i in range(len(MAIN_MENU))]
        previous = [prev.get(f"main_value_{i}") for i in range(len(MAIN_MENU))]
        return current != previous


    def _list_uses_page_windows(self) -> bool:
        """Use page-style windows for content browsing lists.

        Sound/program/file browsing feels better as discrete pages: when the
        cursor crosses the visible boundary, the next page opens with the
        highlighted item at the top.  Keep ordinary setting/navigation menus
        on the previous continuous-scroll model.
        """
        if state.ui_mode in {"file_browser", "radio_browser"}:
            return True
        if state.ui_mode == "submenu" and state.submenu_key in {
            "preset",
            "preset_category",
            "user_preset_load",
            "combi_load",
            "external_midi_pc",
        }:
            return True
        return False

    def _list_window_state(self, index: int, items_len: int, top_y: int, row_h: int, bottom_y: int, *, page_windows: bool | None = None):
        max_rows = max(1, (bottom_y - top_y) // row_h)
        if items_len <= 0:
            return 0, max_rows, 0
        index = max(0, min(items_len - 1, int(index)))
        if page_windows is None:
            page_windows = self._list_uses_page_windows()
        if page_windows:
            start_idx = (index // max_rows) * max_rows
        else:
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

        # 260629e:
        # Redraw the whole list box for list-style incremental updates.
        # Updating only the previous/current rows was fast, but on the physical
        # SPI TFT it could leave small stale fragments around rounded highlight
        # rectangles or long text.  This is still cheaper than a full-screen
        # redraw and keeps engine/MIDI behavior untouched.
        boxes = [list_bbox]

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
        header_changed = (
            prev_snapshot.get("header_version_label") != self._display_script_version()
            or prev_snapshot.get("header_wifi_label") != self._header_wifi_text()
        )
        footer_changed = self._footer_changed(prev_snapshot)

        if self._main_values_changed(prev_snapshot) or header_changed:
            image = self.prev_image.copy()
            draw = ImageDraw.Draw(image)
            if header_changed:
                self._draw_header(draw)
                self._write_partial_image(image, (0, 0, self.width, 46))
            draw.rounded_rectangle((12, 52, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
            self._draw_main(draw)
            self._draw_footer(draw)
            self._write_partial_image(image, (12, 52, self.width - 12, self.height - 48))
            self._write_partial_image(image, (0, self.height - 40, self.width, self.height))
            self.prev_image = image.copy()
            self.prev_snapshot = self._snapshot_state()
            return True

        # The compact six-row Home layout uses tighter spacing than the older
        # five-row layout.  Updating only the previous/current row can leave
        # small stale rounded-rectangle fragments on the physical framebuffer,
        # especially while the highlight moves quickly.  Home is small enough
        # that redrawing the whole list area is safer and still inexpensive.
        image = self.prev_image.copy()
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((12, 52, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        self._draw_main(draw)
        if footer_changed:
            self._draw_footer(draw)
        self._write_partial_image(image, (12, 52, self.width - 12, self.height - 48))
        if footer_changed:
            self._write_partial_image(image, (0, self.height - 40, self.width, self.height))
        self.prev_image = image.copy()
        self.prev_snapshot = self._snapshot_state()
        return True

    def _render_submenu_incremental(self, prev_snapshot: dict) -> bool:
        if self.prev_image is None or prev_snapshot.get("submenu_key") != state.submenu_key:
            return False

        # Combi list/detail screens use a custom local layout: the list box is
        # shorter than the normal submenu box and a Preview/Load legend lives
        # above the global footer.  The generic two-row partial updater assumes
        # normal submenu geometry, which can leave stale highlight fragments or
        # update the wrong rectangle while scrolling.  Redraw the full Combi
        # submenu body instead; this is visually safer and still cheap on a
        # 480x320 TFT.
        if state.submenu_key in {"combi_load", "combi_detail"}:
            footer_changed = self._footer_changed(prev_snapshot)
            prev_index = prev_snapshot.get("submenu_index")
            prev_preview = prev_snapshot.get("combi_preview_active")
            prev_combi_name = prev_snapshot.get("current_combi_name")
            if (
                prev_index == state.submenu_index
                and not footer_changed
                and prev_preview == state.combi_preview_active
                and prev_combi_name == state.current_combi_name
            ):
                return False

            image = self.prev_image.copy()
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, self.width, self.height - 40), fill=BACKGROUND)
            self._draw_submenu(draw)
            self._write_partial_image(image, (0, 0, self.width, self.height - 40))
            if footer_changed:
                self._draw_footer(draw)
                self._write_partial_image(image, (0, self.height - 40, self.width, self.height))
            self.prev_image = image.copy()
            self.prev_snapshot = self._snapshot_state()
            return True

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
        if state.modal_message:
            prev_snapshot = None
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
        elif state.ui_mode == "radio_browser":
            self._draw_radio_browser(draw)
        elif state.ui_mode == "player":
            self._draw_player(draw)
        elif state.ui_mode == "power_menu":
            self._draw_power_menu(draw)
        elif state.ui_mode == "restart_wait":
            self._draw_restart_wait(draw)
        elif state.ui_mode == "quick_menu":
            self._draw_quick_menu(draw)
        elif state.ui_mode == "sound_edit":
            self._draw_sound_edit(draw)
        if state.usb_eject_confirm:
            self._draw_usb_eject_confirm(draw)
        if state.modal_message:
            self._draw_modal_message(draw)
        self._draw_footer(draw)
        self._write_image(image)
        self.prev_snapshot = self._snapshot_state()
        state.last_render_time = time.time()
        state.dirty = False

    def _display_script_version(self) -> str:
        # Show only the compact prefix, e.g. "260530a" from
        # "260530a_titlebar-wifi".  This keeps the title bar narrow enough
        # for the two-row status area on the right.
        return str(SCRIPT_VERSION).split("_", 1)[0]

    def _header_wifi_text(self) -> str:
        # Use cached Wi-Fi state here; _main_menu_value(Extension) and the
        # Wi-Fi menu refresh it through wifi_status_label()/refresh_wifi_status().
        # Avoid running shell commands directly from the header drawing path.
        if not state.wifi_enabled:
            return "Wi-Fi Off"
        if state.wifi_current_ssid:
            return state.wifi_current_ssid
        return "No Network"

    def _fit_text_to_width(self, draw, text: str, font, max_width: int) -> str:
        text = str(text or "").strip()
        if max_width <= 0 or not text:
            return ""
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
        ellipsis = "..."
        if draw.textbbox((0, 0), ellipsis, font=font)[2] > max_width:
            return ""
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate = text[:mid].rstrip() + ellipsis
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + ellipsis

    def _draw_header(self, draw):
        header_h = 44
        draw.rectangle((0, 0, self.width, header_h), fill=(22, 28, 40))

        title = "Fluid Ardule"
        title_x = 12
        title_bbox0 = draw.textbbox((0, 0), title, font=self.font_title)
        title_h = title_bbox0[3] - title_bbox0[1]
        # Vertically center the one-line title inside the title bar.
        title_y = max(0, (header_h - title_h) // 2 - title_bbox0[1])
        draw.text((title_x, title_y), title, font=self.font_title, fill=FG)

        # Keep the right-side status block compact.  A fixed-width block at
        # the far right prevents the title bar from looking too empty while
        # still leaving a clear separation from the Fluid Ardule title.
        status_margin_r = 12
        status_w = min(156, max(120, self.width // 3))
        right_x = self.width - status_margin_r - status_w
        right_w = status_w
        if right_x < title_x + 120:
            return

        build_label = "Build "
        ssid_label = "SSID "
        build_value = self._display_script_version()
        ssid_value = self._header_wifi_text()

        # Keep labels visible and trim only the variable values when the SSID
        # is too long.  Draw labels dimmer than values for a cleaner status
        # panel look.
        build_label_w = draw.textbbox((0, 0), build_label, font=self.font_small)[2]
        ssid_label_w = draw.textbbox((0, 0), ssid_label, font=self.font_small)[2]
        build_value = self._fit_text_to_width(draw, build_value, self.font_small, right_w - build_label_w)
        ssid_value = self._fit_text_to_width(draw, ssid_value, self.font_small, right_w - ssid_label_w)

        build_full = build_label + build_value
        ssid_full = ssid_label + ssid_value
        b_bbox = draw.textbbox((0, 0), build_full, font=self.font_small)
        s_bbox = draw.textbbox((0, 0), ssid_full, font=self.font_small)
        b_h = b_bbox[3] - b_bbox[1]
        s_h = s_bbox[3] - s_bbox[1]
        row_gap = 5
        block_h = b_h + row_gap + s_h
        block_y = max(0, (header_h - block_h) // 2)
        build_y = block_y - b_bbox[1]
        ssid_y = block_y + b_h + row_gap - s_bbox[1]

        draw.text((right_x, build_y), build_label, font=self.font_small, fill=DIM)
        draw.text((right_x + build_label_w, build_y), build_value, font=self.font_small, fill=FG)
        draw.text((right_x, ssid_y), ssid_label, font=self.font_small, fill=DIM)
        draw.text((right_x + ssid_label_w, ssid_y), ssid_value, font=self.font_small, fill=FG)

    def _main_menu_value(self, idx: int) -> str:
        label = MAIN_MENU[idx] if 0 <= idx < len(MAIN_MENU) else ""
        if label == "Sound":
            if file_player_active():
                return "Media active"
            # A loaded Combi is the current performance state.  Show it before
            # the underlying SoundFont/Preset so Home does not misleadingly
            # display the pre-combi single preset.
            if state.combi_active and state.current_combi_name:
                return "Combi:" + shorten_text(str(state.current_combi_name), 18)
            if state.current_user_preset_name and state.current_user_preset_kind == "edited":
                presets = load_user_presets()
                current_name = str(state.current_user_preset_name).strip()
                for i, item in enumerate(presets):
                    if user_preset_is_edited(item) and str(item.get("name", "")).strip() == current_name:
                        return user_preset_display_label(i, item, main=True)
                return "*" + shorten_text(current_name, 18)
            return f"{state.sf_name}/{state.current_preset_name}"
        if label == "Media Player":
            return media_player_home_label()
        if label == "Controls":
            return "Sound Edit"
        if label == "MIDI Mode":
            return state.midi_display_text
        if label == "DAC":
            return state.dac_name
        if label == "Extension":
            return "SEL to Expand"
        return ""

    def _draw_overflow_hints(self, draw, *, current_idx: int, items_len: int, top_y: int, row_h: int, bottom_y: int) -> None:
        """Draw tiny up/down indicators when a list has hidden rows."""
        try:
            items_len = int(items_len)
            current_idx = int(current_idx)
        except Exception:
            return
        if items_len <= 0:
            return
        start_idx, max_rows, _visible_row = self._list_window_state(current_idx, items_len, top_y, row_h, bottom_y)
        end_idx = min(items_len, start_idx + max_rows)
        x = self.width - 18
        if start_idx > 0:
            draw.text((x, top_y - 2), "▲", font=self.font_small, fill=DIM)
        if end_idx < items_len:
            draw.text((x, bottom_y - 24), "▼", font=self.font_small, fill=DIM)

    def _row_symbol_for_current_context(self, idx: int) -> str:
        """Return a stable row glyph: submenu rows use ▶, leaf/action rows use •.

        The highlighted row is already indicated by the selection background, so
        the glyph should describe the row's behavior rather than the cursor.
        """
        if state.ui_mode == "main":
            return "▶"
        if state.ui_mode == "file_source":
            return "▶"
        if state.ui_mode == "file_browser":
            try:
                item = state.browser_entries[idx]
                return "▶" if item.get("type") == "dir" else "•"
            except Exception:
                return "•"
        if state.ui_mode == "radio_browser":
            return "▶" if state.radio_view_mode == "all" and idx == 0 else "•"
        if state.ui_mode != "submenu":
            return "•"

        key = state.submenu_key
        if key == "soundfont":
            return "▶" if idx <= len(SOUNDFONTS) + 1 else "•"
        if key in {"preset_category", "extension", "controls", "external_midi_device"}:
            return "▶"
        if key == "user_preset_save":
            return "•" if idx == 0 else "▶"
        if key == "user_preset_manage":
            return "▶" if idx in {0, 2} else "•"
        return "•"

    def _draw_scrolled_rows(self, draw, labels, current_idx, top_y, row_h, bottom_y, show_current_marks=False):
        total_count = len(labels)
        start_idx, max_rows, _visible_row = self._list_window_state(current_idx, total_count, top_y, row_h, bottom_y)
        end_idx = min(len(labels), start_idx + max_rows)
        row_margin = 3
        for visible_row, idx in enumerate(range(start_idx, end_idx)):
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
            else:
                fill = FG if (show_current_marks and is_current) else DIM
            # Keep row-type glyphs quiet: show them only on the highlighted row.
            # Non-highlighted rows remain visually calm while the current row still
            # tells whether SELECT executes a leaf or RIGHT enters a child list.
            prefix = f"{self._row_symbol_for_current_context(idx)} " if idx == current_idx else "  "
            suffix = " *" if (show_current_marks and is_current) else ""
            row_text = f"{prefix}{index_prefix}{text}{suffix}"
            draw_left_vcentered_text_list(draw, 28, top, row_h, row_text, self.font_body, fill)
        self._draw_overflow_hints(draw, current_idx=current_idx, items_len=total_count, top_y=top_y, row_h=row_h, bottom_y=bottom_y)

        self._draw_scroll_hints(draw, start_idx, end_idx, total_count, top_y, bottom_y)

    def _draw_scroll_hints(self, draw, start_idx: int, end_idx: int, total_count: int, top_y: int, bottom_y: int) -> None:
        """Draw tiny overflow hints for scrollable list areas.

        Use simple arrows instead of a full scrollbar to keep the UI musical
        and low-noise.  The footer remains untouched.
        """
        if total_count <= max(1, end_idx - start_idx):
            return
        x = self.width - 18
        if start_idx > 0:
            draw.text((x, top_y - 2), "▲", font=self.font_small, fill=DIM)
        if end_idx < total_count:
            draw.text((x, bottom_y - 24), "▼", font=self.font_small, fill=DIM)

    def _draw_main(self, draw):
        # Home has exactly six top-level items.  Use a compact Home-only row
        # layout so all items are visible without scrolling, while keeping the
        # submenu/list screens at their existing, more relaxed spacing.
        y = 56
        row_h = 36
        row_margin = 3
        list_bottom = self.height - 48
        draw.rounded_rectangle((12, y - 4, self.width - 12, list_bottom), radius=12, fill=BOX_BG)

        visible_rows = max(1, (list_bottom - y) // row_h)
        start_idx = max(0, state.menu_index - visible_rows + 1) if state.menu_index >= visible_rows else 0
        for visible_row, idx in enumerate(range(start_idx, min(len(MAIN_MENU), start_idx + visible_rows))):
            top = y + visible_row * row_h
            label = MAIN_MENU[idx]
            value = self._main_menu_value(idx)
            sound_blocked = label == "Sound" and file_player_active()
            box_top = top + row_margin
            box_bottom = top + row_h - row_margin

            if idx == state.menu_index:
                draw.rounded_rectangle((20, box_top, self.width - 20, box_bottom), radius=8, fill=SELECT_BG)
                fill = DIM if sound_blocked else FG
                value_fill = DIM if sound_blocked else FG
            else:
                fill = DIM
                value_fill = DIM if sound_blocked else (ACCENT if value else DIM)

            # Home remains a calm launcher: show the enter glyph only on the
            # highlighted row instead of repeating it on every line.
            label_prefix = "▶ " if idx == state.menu_index else "  "
            label_text = f"{label_prefix}{label}"
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
        self._draw_overflow_hints(draw, current_idx=state.menu_index, items_len=len(MAIN_MENU), top_y=y, row_h=row_h, bottom_y=list_bottom)


    def _draw_submenu_title(self, draw, title: str, info: str = ""):
        draw.text((16, 6), title, font=self.font_title, fill=ACCENT)
        if info:
            info = self._fit_text_to_width(draw, str(info), self.font_small, self.width - 240)
            bbox = draw.textbbox((0, 0), info, font=self.font_small)
            draw.text(
                (self.width - 16 - (bbox[2] - bbox[0]), 16),
                info,
                font=self.font_small,
                fill=ACCENT,
            )

    def _browser_source_label(self) -> str:
        path = str(state.browser_path or "")
        try:
            if is_under_root(path, USB_MOUNT_POINT):
                return "USB"
        except Exception:
            pass
        return "Local"

    def _player_source_label(self) -> str:
        if state.player_proc_kind == "radio":
            return "Radio"
        path = str(state.player_path or "")
        try:
            if path and is_under_root(path, USB_MOUNT_POINT):
                return "USB"
        except Exception:
            pass
        if path:
            return "Local"
        return ""

    def _draw_submenu_box(self, draw):
        draw.rounded_rectangle(
            (12, 50, self.width - 12, self.height - 48),
            radius=12,
            fill=BOX_BG,
        )

    def _draw_combi_load_rows(self, draw, options):
        # Combi has its own local legend above the global footer.
        # Keep the list box shorter than normal so the legend never collides
        # with the bottom status line.  Use the normal 38 px row pitch to keep
        # highlight rectangles aligned with text rows, especially around rows
        # 03/04 where the previous 34 px pitch looked visibly off.
        top_y = 58
        row_h = 38
        hint_y = self.height - 92
        box_bottom = hint_y - 10
        draw.rounded_rectangle((12, 50, self.width - 12, box_bottom), radius=12, fill=BOX_BG)
        self._draw_scrolled_rows(
            draw,
            options,
            state.submenu_index,
            top_y,
            row_h,
            box_bottom - 6,
            show_current_marks=True,
        )
        # Paint the whole Combi legend strip every frame.  Without this, the
        # partial framebuffer update can leave alternating BOX_BG/BACKGROUND
        # pixels behind the hint text when preview state changes, making the
        # legend background appear to flicker in and out.
        legend_top = hint_y - 10
        legend_bottom = self.height - 50
        draw.rectangle((12, legend_top, self.width - 12, legend_bottom), fill=BACKGROUND)
        draw.rounded_rectangle((18, legend_top, self.width - 18, legend_bottom), radius=8, fill=BOX_BG)
        draw.line((28, hint_y - 6, self.width - 28, hint_y - 6), fill=(42, 48, 62), width=1)
        if state.combi_preview_active and state.current_combi_name:
            hint = "PREVIEW   SEL:Load   L:Cancel"
            fill = ACCENT
        else:
            hint = "R:Preview   SEL:Load   L:Exit"
            fill = DIM
        draw.text((30, hint_y), hint, font=self.font_small, fill=fill)
        draw.text((30, hint_y + 22), "Layer only / Split off", font=self.font_small, fill=DIM)

    def _draw_combi_detail_rows(self, draw, options):
        # Loaded Combi information screen.  This is intentionally not a
        # transient toast: after SELECT loads a Combi, stay here so the user
        # can see which presets/layers are active.
        top_y = 60
        row_h = 36
        hint_y = self.height - 82
        box_bottom = hint_y - 10
        draw.rounded_rectangle((12, 50, self.width - 12, box_bottom), radius=12, fill=BOX_BG)
        self._draw_scrolled_rows(
            draw,
            options,
            0,
            top_y,
            row_h,
            box_bottom - 6,
            show_current_marks=False,
        )
        legend_top = hint_y - 10
        legend_bottom = self.height - 50
        draw.rectangle((12, legend_top, self.width - 12, legend_bottom), fill=BACKGROUND)
        draw.rounded_rectangle((18, legend_top, self.width - 18, legend_bottom), radius=8, fill=BOX_BG)
        draw.line((28, hint_y - 6, self.width - 28, hint_y - 6), fill=(42, 48, 62), width=1)
        draw.text((30, hint_y), "Combi loaded", font=self.font_small, fill=ACCENT)
        draw.text((30, hint_y + 22), "L:Back   SEL:Combi List", font=self.font_small, fill=DIM)

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
        start_idx, visible_rows, _visible_row = self._list_window_state(
            state.submenu_index,
            len(options),
            56,
            38,
            self.height - 50,
            page_windows=False,
        )

        for visible_row, idx in enumerate(range(start_idx, min(len(options), start_idx + visible_rows))):
            top = 56 + visible_row * 38
            text, is_current = options[idx]

            if idx == state.submenu_index:
                draw.rounded_rectangle((20, top, self.width - 20, top + 32), radius=8, fill=SELECT_BG)
                fill = FG
            else:
                fill = FG if is_current else DIM

            # Keep Sound Source visually calm as well: show the row-type glyph
            # only on the highlighted row.  Non-highlighted rows should not all
            # display triangles, because this screen is frequently used during
            # performance and the full glyph column is visually noisy.
            prefix = f"{self._row_symbol_for_current_context(idx)} " if idx == state.submenu_index else "  "
            suffix = " *" if is_current else ""
            row_text = f"{prefix}{text}{suffix}"
            draw_left_vcentered_text_list(draw, 28, top, 38, row_text, self.font_body, fill)

            if idx < len(SOUNDFONTS):
                total, _drums = soundfont_preset_counts_cached(idx)
                if total:
                    value = str(total)
                    if total > 1:
                        value += " Presets" if idx == state.submenu_index else " >"
                    value_fill = ACCENT if idx != state.submenu_index else FG
                    draw_right_vcentered_text(draw, self.width - 28, top, 38, value, self.font_small, value_fill)
            elif idx == len(SOUNDFONTS):
                count = user_preset_count_cached()
                if count:
                    value = f"{count} Presets" if idx == state.submenu_index else f"{count} >"
                else:
                    value = "0"
                value_fill = ACCENT if idx != state.submenu_index else FG
                draw_right_vcentered_text(draw, self.width - 28, top, 38, value, self.font_small, value_fill)
            elif idx == len(SOUNDFONTS) + 1:
                count = user_combi_count_cached()
                if count:
                    value = f"{count} Combis" if idx == state.submenu_index else f"{count} >"
                else:
                    value = "0"
                value_fill = ACCENT if idx != state.submenu_index else FG
                draw_right_vcentered_text(draw, self.width - 28, top, 38, value, self.font_small, value_fill)
            else:
                value = "SELECT" if idx == state.submenu_index else ""
                if value:
                    draw_right_vcentered_text(draw, self.width - 28, top, 38, value, self.font_small, FG)

        self._draw_overflow_hints(draw, current_idx=state.submenu_index, items_len=len(options), top_y=56, row_h=38, bottom_y=self.height - 50)


    def _draw_submenu_external_midi_pc_rows(self, draw, options):
        cat = gm_current_category_name()
        hint = "RIGHT: next category"
        draw.text((18, 40), f"{cat}   {hint}", font=self.font_small, fill=DIM)
        # Clear and redraw a slightly lower list area so the category/hint line
        # is always visible above the eight GM programs.
        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        self._draw_scrolled_rows(
            draw,
            options,
            state.submenu_index,
            70,
            32,
            self.height - 50,
            show_current_marks=True,
        )

    def _draw_user_preset_load_rows(self, draw, options):
        # User Preset has a compact, local-only layout so five preset rows fit
        # above the Manage hint without changing the common list renderer used
        # by SoundFont, DAC, MIDI, Wi-Fi, Browser, Radio, etc.
        hint_y = self.height - 82
        self._draw_scrolled_rows(
            draw,
            options,
            state.submenu_index,
            56,
            34,
            hint_y - 4,
            show_current_marks=False,
        )
        draw.line((24, hint_y - 6, self.width - 24, hint_y - 6), fill=(42, 48, 62), width=1)
        draw.text((28, hint_y), "Hold LEFT: Manage", font=self.font_small, fill=DIM)

    def _draw_user_preset_rename(self, draw):
        self._draw_submenu_title(draw, "Rename Preset")
        draw.rounded_rectangle((12, 50, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)

        text = state.user_preset_rename_text or " "
        cursor = max(0, min(len(text) - 1, state.user_preset_rename_cursor))

        # Keep only the editable name line and cursor line fixed-width.
        # The rest of the UI continues to use the normal proportional fonts.
        mono = self.font_rename_mono
        max_text_width = self.width - 70
        char_w = max(1, draw.textbbox((0, 0), "M", font=mono)[2])
        max_chars = max(1, max_text_width // char_w)
        if len(text) <= max_chars:
            view_start = 0
        else:
            view_start = max(0, min(cursor - max_chars // 2, len(text) - max_chars))
        visible_text = text[view_start:view_start + max_chars]
        visible_cursor = max(0, min(cursor - view_start, len(visible_text) - 1))

        draw.text((28, 78), visible_text, font=mono, fill=FG)

        cursor_line = " " * visible_cursor + "^"
        draw.text((28, 108), cursor_line, font=mono, fill=ACCENT)

        current_char = text[cursor] if text and cursor < len(text) else " "
        draw.text((28, 136), f"Char: {repr(current_char)[1:-1] or 'space'}", font=self.font_body, fill=ACCENT)
        draw.text((28, 184), "Encoder: char   LEFT/RIGHT: move", font=self.font_small, fill=DIM)
        draw.text((28, 208), "UP: insert space   DOWN: delete", font=self.font_small, fill=DIM)
        draw.text((28, 232), "SELECT: save   SEL long: cancel", font=self.font_small, fill=DIM)

    def _draw_submenu(self, draw):
        title_map = {
            "soundfont": "Sound",
            "preset_category": "Preset Categories",
            "preset": "Select Preset",
            "dac": "Select DAC",
            "midi": "MIDI Mode",
            "controls": "Sound Edit",
            "extension": "Extension",
            "wifi": "Wi-Fi",
            "arp_speed": "Arpeggio Speed",
            "external_midi_device": "External MIDI Device",
            "external_midi_out": "External MIDI OUT",
            "external_midi_pc": "External MIDI PC Send",
            "user_preset_load": "User Preset",
            "combi_load": "Combi",
            "combi_detail": "Combi Loaded",
            "user_preset_save": "Save User Preset",
            "user_preset_overwrite": "Overwrite Preset?",
            "user_preset_manage": "Manage Preset",
            "user_preset_delete": "Delete Preset?",
            "user_preset_rename": "Rename Preset",
            "placeholder": "Coming Soon",
        }

        title = title_map.get(state.submenu_key or "", "Menu")
        info = ""

        if state.submenu_key == "soundfont":
            info = state.sf_name
        elif state.submenu_key in ("preset_category", "preset"):
            info = state.category_source_name if state.submenu_key == "preset_category" else state.preset_source_name
            if state.submenu_key == "preset" and state.category_entries:
                cat = state.category_entries[clamp_index(state.category_index, len(state.category_entries))]
                info = f"{info} / {cat}" if info else cat
        elif state.submenu_key == "dac":
            info = state.dac_name
        elif state.submenu_key == "midi":
            info = state.midi_display_text
        elif state.submenu_key == "extension":
            info = "Ext"
        elif state.submenu_key == "external_midi_device":
            info = external_midi_display_name()
        elif state.submenu_key == "external_midi_out":
            info = state.external_midi_out_mode.upper()
        elif state.submenu_key == "external_midi_pc":
            info = gm_current_category_name()
        elif state.submenu_key in {"user_preset_load", "user_preset_save", "user_preset_manage", "user_preset_delete", "user_preset_rename", "user_preset_overwrite"}:
            info = "User"
        elif state.submenu_key == "combi_load":
            info = "Combi"
        elif state.submenu_key == "combi_detail":
            info = shorten_text(state.current_combi_name or "Combi", 18)
        elif state.submenu_key == "wifi":
            info = wifi_status_label(short=False)
        elif state.submenu_key == "arp_speed":
            info = f"{state.arp_bpm}"

        self._draw_submenu_title(draw, title, info)

        options = get_submenu_options()

        if state.submenu_key == "external_midi_pc":
            self._draw_submenu_external_midi_pc_rows(draw, options)
        elif state.submenu_key == "user_preset_rename":
            self._draw_user_preset_rename(draw)
        else:
            if state.submenu_key == "combi_load":
                self._draw_combi_load_rows(draw, options)
            elif state.submenu_key == "combi_detail":
                self._draw_combi_detail_rows(draw, options)
            else:
                self._draw_submenu_box(draw)
                if state.submenu_key == "soundfont":
                    self._draw_submenu_soundfont_rows(draw, options)
                elif state.submenu_key == "user_preset_load":
                    self._draw_user_preset_load_rows(draw, options)
                else:
                    self._draw_submenu_generic_rows(draw, options)
                    if state.submenu_key == "arp_speed":
                        hint = "Rotate Encoder to adjust"
                        bbox = draw.textbbox((0, 0), hint, font=self.font_small)
                        hint_w = bbox[2] - bbox[0]
                        draw.text(
                            (self.width - 24 - hint_w, 112),
                            hint,
                            font=self.font_small,
                            fill=DIM,
                        )

    def _draw_file_source(self, draw):
        self._draw_submenu_title(draw, "Media Player", usb_status_text())
        draw.text((18, 40), "Select source", font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = [entry["display"] for entry in get_file_source_entries()] or ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.browser_index, 70, 40, self.height - 50)

    def _draw_radio_browser(self, draw):
        title = "Radio Favorites" if state.radio_view_mode == "favorites" else "Internet Radio"
        scope = "Fav" if state.radio_view_mode == "favorites" else "All"
        self._draw_submenu_title(draw, title, f"{scope}:{len(state.radio_entries)}")
        hint = "SELECT: enter/play  RIGHT: favorite  LEFT: back"
        draw.text((18, 40), hint, font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = radio_display_labels() if state.radio_entries else ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.radio_index, 70, 36, self.height - 50)

    def _draw_file_browser(self, draw):
        self._draw_submenu_title(draw, "Media Player", self._browser_source_label())
        path_text = state.browser_path
        if len(path_text) > 42:
            path_text = "..." + path_text[-39:]
        draw.text((18, 40), path_text, font=self.font_small, fill=DIM)
        draw.rounded_rectangle((12, 64, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        labels = [entry["display"] for entry in state.browser_entries] or ["(empty)"]
        self._draw_scrolled_rows(draw, labels, state.browser_index, 70, 36, self.height - 50)

    def _draw_player(self, draw):
        self._draw_submenu_title(draw, "Now Playing", self._player_source_label())
        name = state.player_path if state.player_proc_kind == "radio" else (Path(state.player_path).name if state.player_path else "No file")
        kind = "RADIO" if state.player_proc_kind == "radio" else (state.player_proc_kind.upper() if state.player_proc_kind else "-")
        draw.text((18, 42), f"{kind}  {state.player_status}", font=self.font_small, fill=DIM)

        left_label = "LIST" if state.player_status == "Stopped" else "STOP"
        if state.player_proc_kind == "radio":
            # 260703b: Radio now supports adjacent-station switching in
            # Now Playing mode, so show the same PREV/NEXT labels that the
            # buttons actually perform.  RIGHT remains Favorite toggle.
            up_label = "PREV"
            down_label = "NEXT"
            try:
                is_fav = bool(state.player_radio_station_id and state.player_radio_station_id in load_radio_favorites())
            except Exception:
                is_fav = False
            # The favorite marker belongs to the station name, not to the
            # hardware button label.  RIGHT always means "toggle favorite".
            if is_fav and name:
                name = "★ " + name
            right_label = "FAV"
        else:
            up_label = "PREV"
            down_label = "NEXT"
            right_label = "-"

        draw.rounded_rectangle((12, 70, self.width - 12, 122), radius=12, fill=BOX_BG)
        one_line_name = ellipsize_text(name, self.font_menu, self.width - 48)
        draw.text((24, 83), one_line_name, font=self.font_menu, fill=FG)

        draw.rounded_rectangle((12, 132, self.width - 12, 286), radius=12, fill=BOX_BG)
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

        notice_active = bool(state.player_notice_text) and time.time() < state.player_notice_until
        if notice_active:
            notice = ellipsize_text(state.player_notice_text, self.font_body, self.width - 96)
            nb = draw.textbbox((0, 0), notice, font=self.font_body)
            nw = nb[2] - nb[0]
            nh = nb[3] - nb[1]
            nx1 = max(24, (self.width - nw) // 2 - 22)
            ny1 = 232
            nx2 = min(self.width - 24, (self.width + nw) // 2 + 22)
            ny2 = ny1 + nh + 24
            draw.rounded_rectangle((nx1, ny1, nx2, ny2), radius=10, fill=SELECT_BG)
            draw.text(((self.width - nw) // 2, ny1 + 10), notice, font=self.font_body, fill=FG)

        for btn in buttons:
            x = btn["x"]
            y = btn["y"]
            w = btn["w"]
            h = btn["h"]
            fill = base_fill
            draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=fill)
            # Use the normal button font whenever it fits.  This keeps RESUME
            # visually consistent with PLAY/PAUSE while still allowing a safe
            # fallback for unusually long labels.
            font = self.font_body
            bbox = draw.textbbox((0, 0), btn["label"], font=font)
            if (bbox[2] - bbox[0]) > (w - 10):
                font = self.font_small
                bbox = draw.textbbox((0, 0), btn["label"], font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            tx = x + (w - text_w) / 2 - bbox[0]
            ty = y + (h - text_h) / 2 - bbox[1]
            draw.text((tx, ty), btn["label"], font=font, fill=FG)

    def _draw_sound_edit(self, draw):
        draw.text((16, 6), "Sound Edit", font=self.font_title, fill=ACCENT)
        side = state.sound_edit_active_side if state.sound_edit_active_side in {"A", "B"} else "B"
        right_text = f"{side}  {state.sf_name}/{shorten_text(state.current_preset_name, 10)}"
        bbox = draw.textbbox((0, 0), right_text, font=self.font_small)
        draw.text((self.width - 16 - (bbox[2] - bbox[0]), 16), right_text, font=self.font_small, fill=ACCENT)

        selected_idx = clamp_index(state.sound_edit_index, len(SOUND_EDIT_PARAMS))
        current = SOUND_EDIT_PARAMS[selected_idx]
        cc = int(current["cc"])
        b_val = int(state.sound_edit_values.get(cc, current["default"]))
        a_val = int(state.sound_edit_a_values.get(cc, current["default"]))
        live_val = a_val if side == "A" else b_val
        draw.text((18, 40), f"{current['name']}  CC{cc}  {side}:{live_val}", font=self.font_small, fill=DIM)

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


    def _draw_restart_wait(self, draw):
        # Dedicated full-screen wait page for Restart Software.
        # Do not reuse _draw_power_menu(), because that keeps the Power Menu
        # title/background visible and can look like the menu briefly returned.
        title = "Restarting software..."
        sub = "Please wait"
        box_left = 32
        box_top = 82
        box_right = self.width - 32
        box_bottom = self.height - 82
        draw.rounded_rectangle((box_left, box_top, box_right, box_bottom), radius=16, fill=BOX_BG)
        try:
            tb = draw.textbbox((0, 0), title, font=self.font_title)
            sb = draw.textbbox((0, 0), sub, font=self.font_body)
            title_w = tb[2] - tb[0]
            title_h = tb[3] - tb[1]
            sub_w = sb[2] - sb[0]
            sub_h = sb[3] - sb[1]
        except Exception:
            title_w, title_h = 280, 34
            sub_w, sub_h = 120, 26
        gap = 14
        block_h = title_h + gap + sub_h
        y = box_top + ((box_bottom - box_top - block_h) // 2)
        draw.text(((self.width - title_w) // 2, y), title, font=self.font_title, fill=FG)
        draw.text(((self.width - sub_w) // 2, y + title_h + gap), sub, font=self.font_body, fill=DIM)

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
        if state.power_confirm_action == "EXEC_RESTART_SOFTWARE":
            draw.text((52, 84), "Restarting software...", font=self.font_title, fill=FG)
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
            row_h = 40
            rows_height = len(labels) * row_h
            rows_top = 104
            rows_bottom = self.height - 62
            start_y = rows_top + max(0, (rows_bottom - rows_top - rows_height) // 2)
        for i, label in enumerate(labels):
            top = start_y + i * row_h
            if i == current_idx:
                draw.rounded_rectangle((52, top, self.width - 52, top + 32), radius=8, fill=SELECT_BG)
                fill = FG
                prefix = "▶ "
            else:
                fill = DIM
                prefix = "  "
            draw.text((64, top), f"{prefix}{label}", font=self.font_body, fill=fill)
    def _draw_quick_menu(self, draw):
        # Quick Menu is a shortcut overlay, not a normal page.
        # Do not draw the global Fluid Ardule header here; use the full height
        # so all six quick actions are visible without scrolling.
        draw.text((16, 10), "Quick Menu", font=self.font_title, fill=ACCENT)
        labels = [(item, False) for item in QUICK_MENU_ITEMS]
        draw.rounded_rectangle((12, 52, self.width - 12, self.height - 48), radius=12, fill=BOX_BG)
        self._draw_scrolled_rows(draw, labels, state.quick_menu_index, 52, 34, self.height - 50)

    def _draw_modal_message(self, draw):
        x1, y1 = 70, 96
        x2, y2 = self.width - 70, self.height - 92
        draw.rounded_rectangle((x1, y1, x2, y2), radius=16, fill=(28, 34, 48), outline=ACCENT, width=2)
        title = state.modal_message or "Loading..."
        subtitle = state.modal_submessage or "Please wait"
        tb = draw.textbbox((0, 0), title, font=self.font_title)
        sb = draw.textbbox((0, 0), subtitle, font=self.font_body)
        tx = x1 + ((x2 - x1) - (tb[2] - tb[0])) // 2
        sx = x1 + ((x2 - x1) - (sb[2] - sb[0])) // 2
        draw.text((tx, y1 + 38), title, font=self.font_title, fill=FG)
        draw.text((sx, y1 + 86), subtitle, font=self.font_body, fill=DIM)

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

    def _footer_alt_slot(self, now: float | None = None) -> int:
        if now is None:
            now = time.time()
        interval = max(0.5, float(FOOTER_ALT_INTERVAL_SEC))
        return int(now // interval)

    def _uno_footer_text(self) -> str:
        with serial_lock:
            connected = serial_handle is not None
        return "UNO READY" if connected else "UNO ---"

    def _volume_footer_text(self) -> str:
        return f"VOL {int(state.volume_percent):02d}%"

    def _normal_footer_left_text(self, now: float) -> str:
        if now - state.last_volume_display_time < VOLUME_FOOTER_HOLD_SEC:
            return self._volume_footer_text()
        if self._footer_alt_slot(now) % 2 == 0:
            return self._uno_footer_text()
        return self._volume_footer_text()

    def _draw_footer(self, draw):
        draw.rectangle((0, self.height - 40, self.width, self.height), fill=(22, 28, 40))
        event = state.last_event[-20:] if state.last_event else "-"
        footer_hint = None
        if state.ui_mode == "submenu" and state.submenu_key == "soundfont":
            try:
                # Keep Sound Source hints consistent:
                #   SELECT applies a leaf/default action.
                #   RIGHT enters a browser/submenu when one exists.
                if state.submenu_index < len(SOUNDFONTS):
                    footer_hint = "SEL: Default   ▶: Presets"
                elif state.submenu_index == len(SOUNDFONTS):
                    footer_hint = "SEL: Default   ▶: User"
                elif state.submenu_index == len(SOUNDFONTS) + 1:
                    footer_hint = "SEL: Hint   ▶: Combi"
                elif state.submenu_index == len(SOUNDFONTS) + 2:
                    footer_hint = "SEL: Reload"
            except Exception:
                pass

        now = time.time()
        transient_active = bool(state.transient_footer_text) and now < state.transient_footer_until
        left_text = state.transient_footer_text if transient_active else (footer_hint or self._normal_footer_left_text(now))
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
    ty = y + max(0, (h - th) // 2) - bbox[1]
    draw.text((x, ty), text, font=font, fill=fill)
    return draw.textbbox((x, ty), text, font=font)


def draw_right_vcentered_text(draw, right_x: int, y: int, h: int, text: str, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = right_x - tw
    ty = y + max(0, (h - th) // 2) - bbox[1]
    draw.text((tx, ty), text, font=font, fill=fill)
    return draw.textbbox((tx, ty), text, font=font)


def draw_left_vcentered_text_list(draw, x: int, y: int, h: int, text: str, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    th = bbox[3] - bbox[1]
    ty = y + max(0, (h - th) // 2) - bbox[1]
    draw.text((x, ty), text, font=font, fill=fill)
    return draw.textbbox((x, ty), text, font=font)

display = TFTDisplay(FRAMEBUFFER_DEVICE, FRAMEBUFFER_SYS_DIR)


def invalidate_full_display() -> None:
    display.prev_image = None


def show_modal_message(text: str = "Loading...", subtext: str = "Please wait") -> None:
    state.modal_message = text
    state.modal_submessage = subtext
    state.modal_until = 0.0
    invalidate_full_display()
    mark_dirty(text)
    try:
        display.render()
    except Exception as exc:
        log(f"modal render failed: {exc}")


def clear_modal_message() -> None:
    if state.modal_message or state.modal_submessage:
        state.modal_message = ""
        state.modal_submessage = ""
        state.modal_until = 0.0
        invalidate_full_display()
        state.dirty = True




def show_timed_modal_message(text: str, hold_sec: float = 0.8, subtext: str = " ") -> None:
    """Show the existing centered modal style briefly, then auto-clear."""
    show_modal_message(text, subtext)
    state.modal_until = time.time() + float(hold_sec)

def file_player_active() -> bool:
    return state.player_status in {"Playing", "Paused"} or (player_proc is not None and player_proc.poll() is None)


def media_player_home_label() -> str:
    if file_player_active() and state.player_path:
        name = Path(state.player_path).name
        if state.player_paused or state.player_status == "Paused":
            return f"({name})"
        return name
    return "Browse"


def block_sound_change_while_playing() -> bool:
    if file_player_active():
        mark_dirty("Stop file first")
        return True
    return False


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


def list_uno2_serial_candidates() -> list[str]:
    """Return the configured UNO-2 serial device when available.

    UNO-2 should be identified by its stable /dev/serial/by-id symlink, just
    like UNO-1.  If UNO2_SERIAL_PORT is configured, use that exact identifier
    only.  If it is left empty, fall back to the previous safe heuristic: any
    additional Arduino/Uno USB-serial device under /dev/serial/by-id except the
    configured UNO-1 control port.
    """
    configured = str(globals().get("UNO2_SERIAL_PORT", "") or "").strip()
    if configured:
        return [configured] if Path(configured).exists() else []

    by_id = Path("/dev/serial/by-id")
    if not by_id.exists():
        return []

    try:
        uno1_real = os.path.realpath(SERIAL_PORT)
    except Exception:
        uno1_real = ""

    candidates: list[str] = []
    for path in sorted(by_id.glob("*")):
        name_l = path.name.lower()
        if not ("arduino" in name_l or "uno" in name_l):
            continue
        path_s = str(path)
        try:
            real = os.path.realpath(path_s)
        except Exception:
            real = ""
        if path_s == SERIAL_PORT or (uno1_real and real == uno1_real):
            continue
        candidates.append(path_s)
    return candidates


def uno2_bridge_available() -> bool:
    """Return True only when UNO-2/bridge appears physically available."""
    if state.bridge_proc is not None and state.bridge_proc.poll() is None:
        return True
    if find_bridge_port():
        return True
    return bool(list_uno2_serial_candidates())


def is_external_midi_item(item: dict) -> bool:
    text = f"{item.get('client_name', '')} {item.get('port_name', '')}".lower()
    return any(hint.lower() in text for hint in EXTERNAL_MIDI_NAME_HINTS)


def external_midi_label(item: dict) -> str:
    return f"{item['client_name']} / {item['port_name']}"


def external_midi_display_name(label: str | None = None) -> str:
    """Return a short user-facing name for an external MIDI target.

    SC-D70 exposes three ALSA sequencer ports under the same client name:
      - SC-D70 Part A
      - SC-D70 Part B
      - SC-D70 MIDI

    If we only show the matched device hint ("SC-D70"), the Extension
    device picker becomes ambiguous.  Keep USB MIDI Cable compact, but include
    the SC-D70 port role for Roland modules.
    """
    label = label or state.external_midi_name or "External MIDI"
    cleaned = label.replace(" MIDI 1", "").strip()

    left = cleaned
    right = ""
    if " / " in cleaned:
        left, right = cleaned.split(" / ", 1)

    low = cleaned.lower()
    right_low = right.lower()

    if "sc-d70" in low or "scd70" in low:
        if "part a" in right_low:
            return "SC-D70 Part A"
        if "part b" in right_low:
            return "SC-D70 Part B"
        if "midi" in right_low:
            return "SC-D70 MIDI"
        return "SC-D70"

    if "usb midi cable" in low:
        return "USB Midi Cable"

    for hint in EXTERNAL_MIDI_NAME_HINTS:
        if hint.lower() in low:
            return hint

    if right:
        cleaned = right if right and right.lower() not in left.lower() else left
    return shorten_text(cleaned, 18)


def list_external_midi_seq_ports() -> list[tuple[str, str]]:
    ports = []
    seen = set()
    for item in parse_aconnect_ports():
        if not is_external_midi_item(item):
            continue
        port = item['port']
        label = external_midi_label(item)
        if port in seen:
            continue
        seen.add(port)
        ports.append((port, label))
    return ports


def find_external_midi_seq_port() -> tuple[str | None, str | None]:
    ports = list_external_midi_seq_ports()
    if not ports:
        return None, None

    # Prefer the user-selected external MIDI target if it is still present.
    if state.preferred_external_midi_port:
        for port, label in ports:
            if port == state.preferred_external_midi_port:
                return port, label
    if state.preferred_external_midi_name:
        pref = state.preferred_external_midi_name.lower()
        for port, label in ports:
            if label.lower() == pref or pref in label.lower():
                return port, label

    # Otherwise follow the hint order. This makes USB MIDI Cable win over
    # SC-D70 when both are present until the user explicitly selects another.
    for hint in EXTERNAL_MIDI_NAME_HINTS:
        hint_l = hint.lower()
        for port, label in ports:
            if hint_l in label.lower():
                return port, label

    return ports[0]


def refresh_external_midi_state(quiet: bool = False) -> bool:
    old_present = state.external_midi_present
    old_mode = state.external_midi_out_mode
    old_port = state.external_midi_port
    port, label = find_external_midi_seq_port()
    state.external_midi_present = bool(port)
    state.external_midi_port = port
    state.external_midi_name = label
    if not port:
        state.external_midi_connected = False
        if state.external_midi_out_mode != "off":
            state.external_midi_out_mode = "off"
    changed = (old_present != state.external_midi_present) or (old_mode != state.external_midi_out_mode) or (old_port != state.external_midi_port)
    if changed and not quiet:
        mark_dirty("External MIDI detected" if state.external_midi_present else "External MIDI removed")
    return changed


def external_midi_out_available() -> bool:
    # External MIDI OUT is an output option, not an input-mode option.
    # Show it whenever the configured USB MIDI cable is present.
    # Live RAW keyboard input is not mirrored because FluidSynth owns the raw
    # device directly, but MIDI file playback can still be mirrored and SEQ
    # inputs are mirrored via aconnect.
    return state.external_midi_present


def enforce_external_midi_out_policy() -> None:
    # Keep the selected External MIDI OUT mode across input-mode changes.
    # RAW live input cannot be mirrored, but the menu should remain available
    # when the USB MIDI cable is connected because MIDI file mirror still works.
    return


def connect_external_midi_mirror(src_port: str | None = None) -> bool:
    refresh_external_midi_state(quiet=True)
    enforce_external_midi_out_policy()
    if state.external_midi_out_mode != "mirror" or not state.external_midi_port:
        state.external_midi_connected = False
        return False
    src = src_port or state.midi_src_port
    dst = state.external_midi_port
    if not src or src in {"-", "", "seq"}:
        state.external_midi_connected = False
        return False
    # Allow src == dst for a bidirectional USB MIDI cable.
    # Physically this is often the intended soft-thru use case:
    #   DIN keyboard -> USB MIDI Cable IN -> Pi/FluidSynth
    #   Pi mirror    -> USB MIDI Cable OUT -> external module
    # A real loop is possible only if the cable OUT is physically routed back
    # into its own IN, so do not block same-port soft-thru in software.
    code, out = run_cmd(["aconnect", src, dst])
    already = "already" in out.lower()
    state.external_midi_connected = (code == 0 or already)
    if not state.external_midi_connected:
        mark_dirty(f"Ext MIDI OUT failed: {out[:32]}")
    return state.external_midi_connected


def list_alsa_seq_input_ports() -> list[tuple[str, str]]:
    options = []
    for item in parse_aconnect_ports():
        client_name = item['client_name']
        port_name = item['port_name']
        client_name_l = client_name.lower()
        port_name_l = port_name.lower()
        full_text_l = f"{client_name} {port_name}".lower()

        # Hide ALSA/system/debug ports from the user-facing MIDI input menu.
        # They may appear while Fluid Ardule is monitoring MIDI activity, but
        # they are not real performance input devices.
        if client_name in {'System', 'Midi Through'}:
            continue
        if (
            'aseqdump' in client_name_l
            or 'aseqdump' in port_name_l
            or 'aconnect' in client_name_l
            or 'aconnect' in port_name_l
            or 'client-' in client_name_l
        ):
            continue
        if 'fluid synth' in client_name_l or 'fluidsynth' in client_name_l or 'yoshimi' in client_name_l:
            continue
        if BRIDGE_PORT_HINT.lower() in client_name_l or 'uno-midi-bridge' in client_name_l:
            continue
        if 'announce' in port_name_l or 'timer' in port_name_l:
            continue

        # SC-D70 exposes Part A/B/MIDI as ALSA-sequencer-capable ports.
        # In Fluid Ardule's MIDI Mode, Part A/B are sound-module destinations
        # and should not appear as performance inputs. Keep only the generic
        # SC-D70 MIDI port visible. USB MIDI cables remain visible because
        # their DIN IN side can be used as a real keyboard input.
        is_sc_d70 = ("sc-d70" in full_text_l) or ("scd70" in full_text_l) or ("roland sc-d70" in full_text_l)
        if is_sc_d70 and "midi" not in port_name_l:
            continue

        allowed_external_input = any(h.lower() in full_text_l for h in SEQ_INPUT_ALLOW_EXTERNAL_HINTS)
        excluded_external_input = any(h.lower() in full_text_l for h in SEQ_INPUT_EXCLUDE_EXTERNAL_HINTS)
        if excluded_external_input and not allowed_external_input and not (is_sc_d70 and "midi" in port_name_l):
            continue

        label = f"{client_name} / {port_name}"
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

    # 4) If the user explicitly chose an ALSA input and it disappeared,
    # stay in waiting mode instead of silently falling back to another device
    # such as the External MIDI cable.
    if state.preferred_seq_port or state.preferred_seq_name:
        state.selected_alsa_input = None
        state.selected_alsa_input_name = None
        return None, None

    # 5) Otherwise use first available.
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


def choose_external_midi_seq_input() -> tuple[str | None, str | None]:
    port, label = find_external_midi_seq_port()
    state.selected_alsa_input = port
    state.selected_alsa_input_name = label
    return port, label


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
        if state.external_midi_out_mode == "mirror":
            connect_external_midi_mirror(src)
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
        if state.external_midi_out_mode == "mirror":
            connect_external_midi_mirror(src)
        if code == 0:
            mark_dirty(f'ALSA seq connected {src}->{dst}')
        return True
    state.midi_connected = False
    state.midi_src_port = src
    state.midi_src_name = src_name or src
    refresh_midi_display_text()
    mark_dirty(f'ALSA seq aconnect failed: {out[:40]}')
    return False

def connect_external_midi_to_fluidsynth() -> bool:
    src, src_name = choose_external_midi_seq_input()
    dst = find_fluidsynth_port()
    if not src:
        state.midi_connected = False
        state.midi_src_port = '-'
        state.midi_src_name = 'No External MIDI'
        refresh_midi_display_text()
        mark_dirty('External MIDI missing')
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
    state.midi_src_port = src
    state.midi_src_name = src_name or src
    state.selected_alsa_input = src
    state.selected_alsa_input_name = src_name or src
    state.fluid_dst_port = dst
    state.midi_connected = (code == 0 or already)
    refresh_midi_display_text()
    if state.midi_connected and state.external_midi_out_mode == "mirror":
        connect_external_midi_mirror(src)
    if state.midi_connected:
        if code == 0:
            mark_dirty(f'External MIDI connected {src}->{dst}')
        return True
    mark_dirty(f'External MIDI aconnect failed: {out[:40]}')
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
        "external_midi_seq": "External MIDI (SEQ)",
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
    elif state.midi_mode == "external_midi_seq":
        if not state.external_midi_present:
            state.midi_display_text = "EXT:waiting"
        else:
            ext_label = shorten_text((state.external_midi_name or "External MIDI").replace(" MIDI 1", ""), 10)
            state.midi_display_text = f"EXT:{ext_label}"
    else:
        if not state.selected_alsa_input and not state.selected_alsa_input_name:
            state.midi_display_text = "SEQ:waiting"
        else:
            alsa_label = shorten_text((state.selected_alsa_input_name or state.midi_src_name or 'ALSA').replace(' MIDI 1', ''), 10)
            state.midi_display_text = f"SEQ:{alsa_label}" if alsa_label else "SEQ:waiting"


def seq_menu_label(label: str) -> str:
    # Keep MIDI Mode flat and readable on the TFT: show the actual currently
    # plugged ALSA sequencer input as a direct selectable row.
    # Example: "iCON ... / iCON ... MIDI 1" -> "SEQ:iCON ...".
    text = (label or "ALSA MIDI").replace(" MIDI 1", "").strip()
    if " / " in text:
        left, right = text.split(" / ", 1)
        # Prefer the more specific side, but avoid needless duplication.
        if right and right.lower() not in left.lower():
            text = right
        else:
            text = left
    text = re.sub(r"\s+", " ", text).strip()
    return "SEQ:" + shorten_text(text, 24)


def build_midi_input_options() -> list[tuple[str, str]]:
    # Base RAW mode is always shown. UNO-2 bridge is shown only when its
    # hardware/bridge is actually available, keeping the MIDI Mode menu
    # device-driven and avoiding unusable entries.
    options = list(state.midi_mode_options)
    if uno2_bridge_available():
        options.append(("uno2_bridge_seq", "UNO-2 bridge (SEQ)"))

    # ALSA SEQ inputs are added at menu-entry time as direct selectable items,
    # so there is no second-level selector.
    for port, label in list_alsa_seq_input_ports():
        options.append((f"alsa_seq:{port}", seq_menu_label(label)))
    return options


def refresh_midi_options(quiet: bool = False) -> bool:
    old = list(state.midi_options)
    state.midi_options = build_midi_input_options()
    if state.midi_mode == "uno2_bridge_seq" and not any(mode == "uno2_bridge_seq" for mode, _name in state.midi_options):
        stop_bridge()
        state.bridge_running = False
        state.midi_mode = "usb_direct_raw"
        state.midi_src_port = "-"
        state.midi_src_name = "No raw MIDI"
        if not quiet:
            mark_dirty("UNO-2 removed")
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
    elif state.midi_mode == "external_midi_seq":
        refresh_external_midi_state(quiet=True)
        selected_port, selected_name = choose_external_midi_seq_input()
        state.midi_src_name = selected_name or 'No External MIDI'
        state.midi_src_port = selected_port or '-'
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
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
    elif state.midi_mode == "external_midi_seq":
        refresh_external_midi_state(quiet=True)
        connect_external_midi_to_fluidsynth()
    else:
        selected_port, selected_name = choose_alsa_seq_input()
        state.midi_src_port = selected_port or "-"
        state.midi_src_name = selected_name or "alsa sequencer"
        state.selected_alsa_input = selected_port
        state.selected_alsa_input_name = selected_name
        refresh_midi_display_text()
        if state.combi_active:
            # In Combi mode the Python router owns MIDI delivery.  Do not also
            # aconnect the keyboard directly to FluidSynth, or split filtering
            # is bypassed and the base CH1 sound leaks through all key ranges.
            dst = find_fluidsynth_port()
            if dst:
                state.fluid_dst_port = dst
            _disconnect_all_midi_routes_to_fluidsynth()
            state.midi_connected = bool(selected_port and dst)
            clear_midi_reconnect_pending()
        else:
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
                # Preserve a space-free symlink path for Yoshimi live-load.
                # Path.resolve() follows the symlink back into the factory bank,
                # where filenames may contain spaces and Yoshimi CLI parsing fails.
                # absolute() makes the path absolute without dereferencing it.
                return str(c.absolute())
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


def soundfont_preset_counts_cached(sf_index: int) -> tuple[int, int]:
    """Return cached Sound Source preset counts for fast menu rendering."""
    try:
        sf_index = int(sf_index)
    except Exception:
        return 0, 0
    if sf_index in state.soundfont_count_cache:
        return state.soundfont_count_cache.get(sf_index, (0, 0))

    # During background preload, do not block the UI by reading JSON on demand.
    # The row can briefly show no count; it will update when preload finishes.
    if state.sound_source_cache_preload_started and not state.sound_source_cache_preload_done:
        return 0, 0

    state.soundfont_count_cache[sf_index] = soundfont_preset_counts(sf_index)
    return state.soundfont_count_cache.get(sf_index, (0, 0))



def user_preset_count_cached() -> int:
    """Return cached User Preset count for Sound Source display."""
    if state.user_preset_count_cache is not None:
        return int(state.user_preset_count_cache)

    # During background preload, avoid blocking Sound Source entry.
    if state.sound_source_cache_preload_started and not state.sound_source_cache_preload_done:
        return 0

    state.user_preset_count_cache = len(load_user_presets())
    return int(state.user_preset_count_cache)



def invalidate_user_preset_cache() -> None:
    state.user_preset_count_cache = None


def preload_sound_source_count_cache() -> None:
    """Preload Sound Source counts in the background.

    The Sound Source menu shows preset counts, which are useful but can make
    the first entry feel slow if JSON files are read on demand.  Preload them
    in a background worker and make the renderer return temporary zero counts
    while the worker is still running, so entering Sound Source does not block.
    """
    if state.sound_source_cache_preload_started:
        return
    state.sound_source_cache_preload_started = True

    def worker() -> None:
        try:
            # Give the initial UI/audio startup only a tiny head start.
            # The worker is background-only, so Sound Source entry should not block.
            time.sleep(0.1)
            for i in range(len(SOUNDFONTS)):
                if not state.running:
                    return
                if i not in state.soundfont_count_cache:
                    state.soundfont_count_cache[i] = soundfont_preset_counts(i)
            if state.user_preset_count_cache is None:
                state.user_preset_count_cache = len(load_user_presets())
            state.sound_source_cache_preload_done = True
            mark_dirty("Sound cache ready")
        except Exception as exc:
            log(f"sound source cache preload failed: {exc}")

    try:
        t = threading.Thread(target=worker, name="sound-source-cache-preload", daemon=True)
        t.start()
    except Exception as exc:
        log(f"sound source cache preload start failed: {exc}")



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
    category_sf = getattr(state, "category_source_sf_index", None)
    state.submenu_index = category_sf if category_sf is not None else (
        state.preset_sf_index if state.preset_sf_index is not None else state.sf_index
    )
    invalidate_full_display()
    mark_dirty("Back to SF2")


def return_to_sound_submenu(event: str = "Sound", index: int | None = None) -> None:
    """Return to the top-level Sound submenu safely.

    This is used by Combi cancel/exit.  Do not call
    return_to_soundfont_submenu() from Combi pages because that helper is for
    returning from preset category/list pages and may use category state.
    """
    state.ui_mode = "submenu"
    state.submenu_key = "soundfont"
    if index is None:
        index = len(SOUNDFONTS) + 1  # Sound > Combi row
    state.submenu_index = clamp_index(int(index), len(get_submenu_options()))
    state.submenu_return_mode = None
    invalidate_full_display()
    mark_dirty(event)


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
    load_or_start_yoshimi_instrument(path, state.audio_device)

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
    if combi_locked():
        warn_combi_quick_blocked()
        return
    enter_file_source(default_usb=state.usb_mounted)


def browser_go_parent() -> None:
    root = resolve_file_root()
    current = normalize_path(state.browser_path)

    if os.path.abspath(current) == os.path.abspath(root) or os.path.abspath(current) == os.path.abspath(USB_MOUNT_POINT):
        enter_file_source(default_usb=state.usb_mounted and os.path.abspath(current) == os.path.abspath(USB_MOUNT_POINT))
        mark_dirty("Back to source")
        return

    # Remember the folder we are leaving so the parent list can highlight it.
    # This preserves browser context when returning from a child directory
    # instead of jumping back to the first item.
    previous_folder_name = os.path.basename(current)

    parent = normalize_path(os.path.dirname(current))
    if not is_under_root(parent, root):
        parent = root

    state.browser_path = parent
    refresh_browser_entries(keep_name=previous_folder_name)
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
        show_timed_modal_message("Beginning of list", 0.8)
        return
    if next_pos >= len(playable):
        show_timed_modal_message("End of list", 0.8)
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
    stop_combi_router()
    if fluid_proc is None:
        return
    try:
        if fluid_proc.poll() is None:
            os.killpg(os.getpgid(fluid_proc.pid), signal.SIGTERM)
            # Yoshimi writes user configuration during normal shutdown. Give it
            # a little more time before SIGKILL to reduce the risk of a truncated
            # ~/.config/yoshimi/config/yoshimi.config file.
            deadline = time.time() + (2.0 if state.current_engine == "yoshimi" else 0.5)
            while fluid_proc.poll() is None and time.time() < deadline:
                time.sleep(0.05)
            if fluid_proc.poll() is None:
                os.killpg(os.getpgid(fluid_proc.pid), signal.SIGKILL)
                time.sleep(0.2)
    except Exception as exc:
        log(f"stop_fluidsynth exception: {exc}")
    fluid_proc = None
    state.fluid_pid = None
    state.fluid_dst_port = "-"
    state.midi_connected = False


def ensure_yoshimi_stopped(reason: str = "") -> None:
    """State-driven cleanup for stale Yoshimi processes.

    FluidSynth normally owns the RAW MIDI device directly, while Yoshimi is
    reached through ALSA sequencer ports.  Before returning to FluidSynth, make
    sure a previous Yoshimi process has actually disappeared so ALSA/MIDI state
    cannot remain half-transitioned.  This is intentionally narrow: it only
    targets the Yoshimi executable and does not restart Fluid Ardule itself.
    """
    code, out = run_cmd(["pgrep", "-x", "yoshimi"])
    if code != 0 or not out.strip():
        return

    suffix = f" ({reason})" if reason else ""
    log(f"stale Yoshimi detected{suffix}: {out.strip()}")
    run_cmd(["pkill", "-TERM", "-x", "yoshimi"])

    deadline = time.time() + 2.0
    while time.time() < deadline:
        code, out = run_cmd(["pgrep", "-x", "yoshimi"])
        if code != 0 or not out.strip():
            log(f"stale Yoshimi cleared{suffix}")
            return
        time.sleep(0.05)

    code, out = run_cmd(["pgrep", "-x", "yoshimi"])
    if code == 0 and out.strip():
        log(f"stale Yoshimi still alive; sending SIGKILL{suffix}: {out.strip()}")
        run_cmd(["pkill", "-KILL", "-x", "yoshimi"])


def start_yoshimi_instrument(xiz_path: str, audio_device: str) -> bool:
    """Start Yoshimi headlessly and load one .xiz instrument at launch.

    This is still the reliable cold-start path:
        yoshimi -i -A -a -L /path/to/instrument.xiz

    Unlike earlier versions, stdin is kept open so later patch changes can be
    sent with:
        load instrument /space/free/symlink.xiz
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

    # Mute only the output level around the Yoshimi transition.  This is an
    # experimental anti-thump strategy: avoid aplaymidi/CC123, keep the proven
    # restart-with -L path, and hide the short audio artifact while the engine
    # is stopped and recreated.

    # Stop the currently managed engine first. This is intentionally the same
    # process slot used by FluidSynth, because Fluid Ardule runs only one live
    # synth engine at a time.
    stop_fluidsynth()

    # Clean up any stale Yoshimi instance left by an earlier failed test run.
    # This keeps ALSA ports unambiguous for aconnect.
    ensure_yoshimi_stopped("before Yoshimi start")

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
    # "yoshimi> @ Top" even when used as a headless engine. Keep stdout/stderr
    # suppressed, but keep stdin open for restart-free live instrument loading.
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
            stdin=subprocess.PIPE,
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


def yoshimi_process_alive() -> bool:
    return (
        state.current_engine == "yoshimi"
        and fluid_proc is not None
        and fluid_proc.poll() is None
    )


def send_yoshimi_cli_command(command: str) -> bool:
    """Send one command to the running Yoshimi CLI through stdin."""
    if not yoshimi_process_alive():
        return False
    if fluid_proc is None or fluid_proc.stdin is None:
        log("Yoshimi CLI unavailable: stdin is not open")
        return False
    try:
        if YOSHIMI_LIVE_LOAD_TRACE:
            log(f"Yoshimi CLI >>> {command}")
        fluid_proc.stdin.write(command.rstrip("\n") + "\n")
        fluid_proc.stdin.flush()
        return True
    except BrokenPipeError:
        log("Yoshimi CLI write failed: broken pipe")
        return False
    except Exception as exc:
        log(f"Yoshimi CLI write failed: {exc}")
        return False


def clamp_arp_bpm(value: int) -> int:
    try:
        value = int(value)
    except Exception:
        value = ARP_BPM_DEFAULT
    return max(ARP_BPM_MIN, min(ARP_BPM_MAX, value))


def arp_display_bpm_to_raw_speed(display_bpm: int) -> int:
    display_bpm = clamp_arp_bpm(display_bpm)
    raw_speed = round((display_bpm - ARP_CAL_INTERCEPT) / ARP_CAL_SLOPE)
    return max(1, int(raw_speed))


def arp_bpm_to_echo_delay(display_bpm: int) -> int:
    raw_speed = arp_display_bpm_to_raw_speed(display_bpm)
    return max(1, min(127, round(ARP_DELAY_NUMERATOR / raw_speed)))


def current_yoshimi_patch_is_arpeggio() -> bool:
    if state.current_engine != "yoshimi":
        return False
    name = str(state.current_preset_name or "").lower()
    path = str(state.current_instrument_path or "").lower()
    return "arpeggio" in name or "arpeggios" in path


def send_yoshimi_cli_block(commands: list[str]) -> bool:
    ok = True
    for command in commands:
        ok = send_yoshimi_cli_command(command) and ok
    return ok


def apply_yoshimi_arpeggio_speed(announce: bool = True) -> bool:
    state.arp_bpm = clamp_arp_bpm(state.arp_bpm)
    if not yoshimi_process_alive():
        if announce:
            mark_dirty("Yoshimi not running")
        return False
    if not current_yoshimi_patch_is_arpeggio():
        if announce:
            mark_dirty("Arpeggio Speed: Yoshimi Arpeggio only")
        return False
    delay = arp_bpm_to_echo_delay(state.arp_bpm)
    ok = send_yoshimi_cli_block([
        "/",
        "set part 1",
        "set effect 2 echo",
        f"set delay {delay}",
    ])
    if announce:
        mark_dirty(f"Arpeggio Speed {state.arp_bpm} -> D{delay}" if ok else "Arpeggio Speed failed")
    return ok


def adjust_arp_speed(delta: int, *, announce: bool = True) -> None:
    try:
        delta = int(delta)
    except Exception:
        delta = 0
    if delta == 0:
        return
    old = state.arp_bpm
    state.arp_bpm = clamp_arp_bpm(old + delta)
    if state.arp_bpm == old:
        mark_dirty("Max speed" if delta > 0 else "Min speed")
        return
    apply_yoshimi_arpeggio_speed(announce=announce)
    state.dirty = True


def live_load_yoshimi_instrument(xiz_path: str) -> bool:
    """Try to change the running Yoshimi instrument without restarting it."""
    if not YOSHIMI_LIVE_LOAD_ENABLED:
        return False

    xiz_path = str(xiz_path or "").strip()
    if not xiz_path:
        return False
    xiz = Path(xiz_path)
    if not xiz.exists():
        log(f"Yoshimi live load rejected; file missing: {xiz_path}")
        return False

    # The Yoshimi CLI does not parse paths with spaces reliably.  The symlink
    # JSON should provide a space-free path.  If a path with spaces is seen,
    # skip live loading so the fallback -L start path can still work.
    if " " in xiz_path:
        log(f"Yoshimi live load skipped; path contains spaces: {xiz_path}")
        return False

    if not send_yoshimi_cli_command(f"load instrument {xiz_path}"):
        return False

    # There is no simple synchronous OK response here because stdout/stderr are
    # suppressed to avoid CLI prompt spam.  Treat a still-alive process shortly
    # after the command as a successful live load.
    time.sleep(0.05)
    if not yoshimi_process_alive():
        log("Yoshimi live load failed; process exited after command")
        return False

    state.current_engine = "yoshimi"
    state.current_instrument_path = xiz_path
    state.fluid_pid = fluid_proc.pid if fluid_proc is not None else None
    if YOSHIMI_LIVE_LOAD_TRACE:
        log(f"Yoshimi live load OK: {xiz.name}")
    return True


def load_or_start_yoshimi_instrument(xiz_path: str, audio_device: str) -> bool:
    """Prefer live Yoshimi instrument loading, with restart fallback."""
    xiz_path = str(xiz_path or "").strip()
    if yoshimi_process_alive() and live_load_yoshimi_instrument(xiz_path):
        return True

    if not YOSHIMI_LIVE_LOAD_FALLBACK_RESTART and yoshimi_process_alive():
        return False

    return start_yoshimi_instrument(xiz_path, audio_device)



def fluidsynth_startup_settle_sec(sf_path: str) -> float:
    """Return a conservative post-start settling delay for the selected SF2."""
    try:
        name = Path(str(sf_path or "")).name
    except Exception:
        name = ""
    if name in FLUIDSYNTH_LARGE_SF2_NAMES:
        return FLUIDSYNTH_STARTUP_SETTLE_LARGE_SEC
    return FLUIDSYNTH_STARTUP_SETTLE_DEFAULT_SEC

def start_fluidsynth(sf_path: str, audio_device: str) -> bool:
    global fluid_proc
    stop_fluidsynth()
    ensure_yoshimi_stopped("before FluidSynth start")
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
        "-o", "synth.polyphony=96",
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
    time.sleep(fluidsynth_startup_settle_sec(sf_path))
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


# =========================================================
# Combination (Combi) support v1
# =========================================================


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _combi_source_file() -> str:
    try:
        return Path(source_path_for_index(state.sf_index)).name
    except Exception:
        return ""




def find_soundfont_index_by_basename(filename: str) -> int | None:
    """Return SOUNDFONTS index whose path basename matches filename."""
    target = Path(str(filename or "")).name
    if not target:
        return None
    for i, (path, _label) in enumerate(SOUNDFONTS):
        try:
            if Path(path).name == target:
                return i
        except Exception:
            continue
    return None


def ensure_combi_soundfont_loaded(required_sf2: str, *, manage_modal: bool = True, force_restart: bool = False) -> bool:
    """Load the Combi-required SF2 only when the current source differs.

    This keeps Combi selection fast when FluidR3_GM.sf2 is already active, but
    automatically switches to the required SF2 when the device is currently on
    another SoundFont such as SalC5Light2.sf2.
    """
    required = Path(str(required_sf2 or "")).name
    if not required:
        return True
    current = _combi_source_file()
    if (
        not force_restart
        and current == required
        and state.current_engine == "fluidsynth"
        and fluid_proc is not None
        and fluid_proc.poll() is None
    ):
        return True

    target_index = find_soundfont_index_by_basename(required)
    if target_index is None:
        log(f"Combi required SF2 not found in SOUNDFONTS: {required}")
        mark_dirty(f"SF2 missing: {required}")
        return False

    log(f"Combi loading required SoundFont: {required} (current={current or '-'})")
    if manage_modal:
        show_modal_message("Loading Combi SF2...", required)
    restart_engine(target_index, state.dac_index, manage_modal=manage_modal)
    if manage_modal:
        clear_modal_message()
    ok = (state.current_engine == "fluidsynth" and fluid_proc is not None and fluid_proc.poll() is None)
    if not ok:
        log("Combi SF2 load failed: FluidSynth is not running after restart_engine")
        mark_dirty("Combi SF2 load failed")
        return False
    return True

def _extract_bank_program_from_preset_id(preset_id: str) -> tuple[int | None, int | None]:
    """Parse ids such as sf2:FluidR3_GM.sf2:0:89:Warm-Pad."""
    parts = str(preset_id or "").split(":")
    if len(parts) >= 5:
        try:
            return int(parts[2]), int(parts[3])
        except Exception:
            return None, None
    return None, None


def normalize_combi_part(part: dict, fallback_channel: int = 1) -> dict | None:
    if not isinstance(part, dict):
        return None
    bank = part.get("bank")
    program = part.get("program")
    if bank is None or program is None:
        b, prg = _extract_bank_program_from_preset_id(str(part.get("preset_id", "")))
        if bank is None:
            bank = b
        if program is None:
            program = prg
    if bank is None or program is None:
        return None

    channel = _safe_int(part.get("channel", fallback_channel), fallback_channel)
    channel = max(1, min(16, channel))
    key_low = max(0, min(127, _safe_int(part.get("key_low", 0), 0)))
    key_high = max(0, min(127, _safe_int(part.get("key_high", 127), 127)))
    if key_low > key_high:
        key_low, key_high = key_high, key_low

    return {
        "role": str(part.get("role", "layer")),
        "label": str(part.get("label") or part.get("name") or f"{int(bank)}:{int(program)}"),
        "preset_id": str(part.get("preset_id", "")),
        "bank": int(bank),
        "program": int(program),
        "channel": channel,
        "volume": max(0, min(127, _safe_int(part.get("volume", 100), 100))),
        "key_low": key_low,
        "key_high": key_high,
        "transpose": max(-48, min(48, _safe_int(part.get("transpose", 0), 0))),
        "mute": bool(part.get("mute", False)),
        "solo": bool(part.get("solo", False)),
    }


def normalize_combi(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    parts_in = item.get("parts") or []
    if not isinstance(parts_in, list):
        return None
    parts: list[dict] = []
    for i, part in enumerate(parts_in[:4]):
        norm = normalize_combi_part(part, fallback_channel=i + 1)
        if norm:
            parts.append(norm)
    if not parts:
        return None
    name = str(item.get("name") or item.get("id") or "Combi")
    return {
        "id": str(item.get("id") or name),
        "name": name,
        "description": str(item.get("description") or ""),
        "sf2": str(item.get("sf2") or item.get("source_file") or "FluidR3_GM.sf2"),
        "input_channel": max(1, min(16, _safe_int(item.get("input_channel", COMBI_INPUT_CHANNEL), COMBI_INPUT_CHANNEL))),
        "parts": parts,
    }


def load_user_combis() -> list[dict]:
    path = Path(USER_COMBI_PATH)
    if not path.exists():
        log(f"user_combis.json missing: {path}")
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"user_combis.json load failed: {exc}")
        return []

    if isinstance(payload, dict):
        default_sf2 = str(payload.get("source_file") or payload.get("sf2") or "FluidR3_GM.sf2")
        default_input = _safe_int(payload.get("input_channel", COMBI_INPUT_CHANNEL), COMBI_INPUT_CHANNEL)
        items = payload.get("combinations") or payload.get("combis") or []
        if isinstance(items, list):
            raw_items = []
            for item in items:
                if isinstance(item, dict):
                    merged = dict(item)
                    merged.setdefault("sf2", default_sf2)
                    merged.setdefault("input_channel", default_input)
                    raw_items.append(merged)
        else:
            raw_items = []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []

    combis = []
    for item in raw_items:
        norm = normalize_combi(item)
        if norm:
            combis.append(norm)
    state.combi_entries = combis
    return combis


def user_combi_count_cached() -> int:
    if state.combi_entries:
        return len(state.combi_entries)
    return len(load_user_combis())


def combi_label(index: int, item: dict) -> str:
    name = str(item.get("name") or f"Combi {index + 1}")
    return f"{index + 1:02d} {name}"


def enter_combi_load_menu(return_mode: str | None = None) -> None:
    state.combi_entries = load_user_combis()
    state.ui_mode = "submenu"
    state.submenu_key = "combi_load"
    state.submenu_return_mode = return_mode or "main"

    # Combi browser must not inherit submenu_index from Home/Sound menu.
    # Prefer the currently loaded Combi when available; otherwise start at 0.
    target_index = 0
    current_name = str(state.current_combi_name or "").strip()
    if current_name:
        for i, item in enumerate(state.combi_entries):
            if str(item.get("name") or "").strip() == current_name:
                target_index = i
                break
    state.submenu_index = clamp_index(target_index, len(state.combi_entries))
    begin_combi_browse_session()

    invalidate_full_display()
    mark_dirty(f"Combi: {len(state.combi_entries)} saved")


def _send_channel_setup_for_part(part: dict) -> bool:
    ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
    bank = _safe_int(part.get("bank", 0), 0)
    program = _safe_int(part.get("program", 0), 0)
    volume = max(0, min(127, _safe_int(part.get("volume", 100), 100)))
    label = str(part.get("label") or part.get("name") or part.get("preset_id") or f"{bank}:{program}")
    is_drum = bank == 128 or ch == 9
    log(f"Combi part setup: CH{ch + 1} bank={bank} program={program} volume={volume} label={label}")
    ok = False
    ok = send_fluidsynth_command(f"drums {ch} {'on' if is_drum else 'off'}") or ok
    ok = send_fluidsynth_command(f"bank {ch} {bank}") or ok
    ok = send_fluidsynth_command(f"prog {ch} {program}") or ok
    ok = send_fluidsynth_command(f"select {ch} 0 {bank} {program}") or ok
    ok = send_fluidsynth_command(f"cc {ch} 7 {volume}") or ok
    if not ok:
        log("Combi part setup warning: no FluidSynth shell command succeeded")
    return ok


def _active_combi_parts_for_note(note: int) -> list[dict]:
    """Return active Combi parts for a note, honoring split/key ranges.

    A Combi part is active only when:
      - it is not muted,
      - it survives Solo filtering, and
      - the incoming CH1 note is inside key_low..key_high.

    Layer = multiple parts with overlapping ranges.
    Split = parts with separated ranges.
    """
    note = max(0, min(127, int(note)))
    parts = list(state.combi_parts or [])
    if any(bool(p.get("solo")) for p in parts):
        parts = [p for p in parts if bool(p.get("solo"))]
    out = []
    for p in parts:
        if bool(p.get("mute")):
            continue
        low = max(0, min(127, _safe_int(p.get("key_low", 0), 0)))
        high = max(0, min(127, _safe_int(p.get("key_high", 127), 127)))
        if low > high:
            low, high = high, low
        if low <= note <= high:
            out.append(p)
    return out


def _disconnect_direct_midi_route() -> None:
    src = state.selected_alsa_input or state.midi_src_port
    dst = state.fluid_dst_port or find_fluidsynth_port()
    if src and dst and src not in {"-", "seq"} and dst != "-":
        run_cmd(["aconnect", "-d", src, dst])


def _disconnect_all_midi_routes_to_fluidsynth() -> None:
    """Disconnect all ALSA SEQ inputs from FluidSynth in Combi mode.

    Split only works if CH1 keyboard notes do not also reach FluidSynth
    directly.  A previous MIDI reconnect or manual aconnect can leave extra
    keyboard->FluidSynth routes alive, so remove every non-FluidSynth source
    connection to the FluidSynth destination before the Python Combi router
    starts forwarding filtered notes.
    """
    dst = state.fluid_dst_port or find_fluidsynth_port()
    if not dst or dst == "-":
        return
    for item in parse_aconnect_ports():
        src = item.get("port")
        if not src or src == dst:
            continue
        client_name = str(item.get("client_name", "")).lower()
        if "fluidsynth" in client_name or "fluid synth" in client_name:
            continue
        run_cmd(["aconnect", "-d", src, dst])


def _parse_aseqdump_note_or_cc(line: str) -> tuple[str, int, int, int] | None:
    """Parse aseqdump output and return (kind, channel_1based, a, b).

    aseqdump usually prints the MIDI channel in the table column as 0-15, e.g.:
        24:0   Note on                 0, note 60, velocity 96
        24:0   Controller              0, controller 64, value 127

    Some builds/messages may include "channel N" text instead.  Normalize both
    forms to 1-based channel numbers so COMBI_INPUT_CHANNEL=1 means MIDI CH1.
    """
    text = (line or "").strip()
    low = text.lower()
    if not low:
        return None

    def _parse_channel_1based() -> int | None:
        m = re.search(r'channel\s+(\d+)', low)
        if m:
            ch_raw = int(m.group(1))
        else:
            # Table-column format: event name followed by "0," or "3,".
            m = re.search(r'\b(?:note\s+on|note\s+off|controller|control(?:\s+change)?|pitch\s+bend)\b\s+(-?\d+)\s*,', low)
            if not m:
                return None
            ch_raw = int(m.group(1))
        # aseqdump channels are normally 0-based.  If a future format prints
        # 1-16, values 1-15 are ambiguous; Fluid Ardule treats COMBI input as
        # user-facing 1-based, so 0 is definitely CH1 and other values are
        # converted from the common 0-based table convention.
        if 0 <= ch_raw <= 15:
            return ch_raw + 1
        if 1 <= ch_raw <= 16:
            return ch_raw
        return None

    if "note on" in low or "note off" in low:
        ch = _parse_channel_1based()
        m_note = re.search(r'note\s+(\d+)', low)
        m_vel = re.search(r'velocity\s+(\d+)', low)
        if ch is None or not m_note:
            return None
        note = int(m_note.group(1))
        vel = int(m_vel.group(1)) if m_vel else 0
        kind = "noteon" if "note on" in low and vel > 0 else "noteoff"
        return kind, ch, note, vel

    if "controller" in low or "control" in low:
        ch = _parse_channel_1based()
        # aseqdump commonly prints:
        #   Controller              0, controller 64, value 127
        # The first number after the event name is the MIDI channel, not the
        # controller number.  Therefore prefer the controller number after the
        # comma.  The previous parser accidentally treated the channel number
        # as the CC number, so CC1/CC64 appeared to do nothing.
        m_ctrl = re.search(r',\s*(?:controller|control(?:\s+change)?)\s+(\d+)', low)
        if not m_ctrl:
            m_ctrl = re.search(r'(?:controller|control(?:\s+change)?)\s+(\d+)\s*,\s*value', low)
        m_val = re.search(r'value\s+(-?\d+)', low)
        if ch is None or not (m_ctrl and m_val):
            return None
        return "cc", ch, int(m_ctrl.group(1)), int(m_val.group(1))

    if "pitch bend" in low:
        ch = _parse_channel_1based()
        m_val = re.search(r'value\s+(-?\d+)', low)
        if ch is None or not m_val:
            return None
        return "pitch", ch, int(m_val.group(1)), 0

    return None

def _normalize_pitch_bend_value(value: int) -> int:
    """Return FluidSynth-compatible 14-bit pitch-bend value, center=8192."""
    value = int(value)
    # aseqdump commonly prints either 0..16383 or -8192..8191 depending on
    # ALSA/tool version.  FluidSynth shell pitch_bend expects 0..16383.
    if -8192 <= value <= 8191:
        value += 8192
    return max(0, min(16383, value))


def _send_pitch_bend_to_channel(channel_0based: int, value: int) -> bool:
    ch = max(0, min(15, int(channel_0based)))
    bend = _normalize_pitch_bend_value(value)
    return send_fluidsynth_command(f"pitch_bend {ch} {bend}")


def _audible_combi_parts_for_controller() -> list[dict]:
    """Return parts that should receive channel-wide controllers."""
    parts = list(state.combi_parts or [])
    if any(bool(p.get("solo")) for p in parts):
        parts = [p for p in parts if bool(p.get("solo"))]
    return [p for p in parts if not bool(p.get("mute"))]


def _forward_combi_event_to_channel(kind: str, channel_0based: int, a: int, b: int, *, protect_volume: bool = False) -> bool:
    """Forward a parsed MIDI event to one FluidSynth channel.

    Used for CH10 drum-pad pass-through and for shared controller forwarding.
    """
    ch = max(0, min(15, int(channel_0based)))
    if kind == "noteon":
        return send_fluidsynth_command(f"noteon {ch} {max(0, min(127, int(a)))} {max(0, min(127, int(b)))}")
    if kind == "noteoff":
        return send_fluidsynth_command(f"noteoff {ch} {max(0, min(127, int(a)))}")
    if kind == "cc":
        cc = max(0, min(127, int(a)))
        val = max(0, min(127, int(b)))
        if protect_volume and cc == 7:
            return False
        return send_fluidsynth_command(f"cc {ch} {cc} {val}")
    if kind == "pitch":
        return _send_pitch_bend_to_channel(ch, int(a))
    return False


def _combi_router_thread(generation: int) -> None:
    global combi_router_proc, combi_router_generation
    while state.running and state.combi_active and generation == combi_router_generation:
        src = state.selected_alsa_input or state.midi_src_port
        if not src or src in {"-", "seq"}:
            time.sleep(0.2)
            continue
        signature = f"{src}|{state.current_combi_name}|{len(state.combi_parts)}"
        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                ["aseqdump", "-p", src],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid,
            )
            combi_router_proc = proc
            state.combi_router_signature = signature
            log(f"Combi router started: {src}")
            # Remember exactly which routed notes were started, so Note Off
            # follows the same target channels/notes even in split setups.
            # Key: (input_channel_1based, input_note)
            # Value: [(output_channel_0based, output_note), ...]
            active_note_targets: dict[tuple[int, int], list[tuple[int, int]]] = {}
            while state.running and state.combi_active and generation == combi_router_generation and proc.poll() is None:
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.02)
                    continue
                parsed = _parse_aseqdump_note_or_cc(line)
                if not parsed:
                    continue
                kind, in_ch, a, b = parsed

                # Preserve keyboard drum pads. Many compact controllers send pads
                # on MIDI CH10 while keys send CH1.  Since Combi mode disconnects
                # the direct keyboard->FluidSynth route, explicitly pass CH10
                # through to FluidSynth CH10 unchanged.
                if int(in_ch) == 10:
                    if _forward_combi_event_to_channel(kind, 9, a, b, protect_volume=False):
                        maybe_pulse_led()
                    continue

                if int(in_ch) != int(state.combi_input_channel):
                    continue

                if kind in {"noteon", "noteoff"}:
                    note = max(0, min(127, a))
                    velocity = max(0, min(127, b))
                    note_key = (int(in_ch), note)

                    if kind == "noteon":
                        targets: list[tuple[int, int]] = []
                        for part in _active_combi_parts_for_note(note):
                            out_note = note + _safe_int(part.get("transpose", 0), 0)
                            if out_note < 0 or out_note > 127:
                                continue
                            out_ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
                            targets.append((out_ch, out_note))
                        active_note_targets[note_key] = targets
                        for out_ch, out_note in targets:
                            send_fluidsynth_command(f"noteon {out_ch} {out_note} {velocity}")
                            maybe_pulse_led()
                    else:
                        targets = active_note_targets.pop(note_key, [])
                        # Fallback: if a Note Off arrives without a remembered
                        # Note On (for example after router restart), calculate
                        # targets from the current split ranges.
                        if not targets:
                            for part in _active_combi_parts_for_note(note):
                                out_note = note + _safe_int(part.get("transpose", 0), 0)
                                if out_note < 0 or out_note > 127:
                                    continue
                                out_ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
                                targets.append((out_ch, out_note))
                        for out_ch, out_note in targets:
                            send_fluidsynth_command(f"noteoff {out_ch} {out_note}")
                            maybe_pulse_led()

                elif kind == "cc":
                    cc = max(0, min(127, a))
                    val = max(0, min(127, b))
                    # Forward performance controllers from the input keyboard to
                    # all audible Combi parts: modulation(CC1), sustain(CC64),
                    # expression(CC11), pan(CC10), reverb(CC91), chorus(CC93), etc.
                    # CC7 volume remains owned by the Combi part definition so a
                    # keyboard volume slider does not flatten carefully balanced layers.
                    if cc == 7:
                        continue
                    sent_channels: set[int] = set()
                    for part in _audible_combi_parts_for_controller():
                        out_ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
                        if out_ch in sent_channels:
                            continue
                        sent_channels.add(out_ch)
                        send_fluidsynth_command(f"cc {out_ch} {cc} {val}")

                elif kind == "pitch":
                    # Pitch bend is channel-wide, so send it to all audible Combi
                    # part channels. It is intentionally not key-range filtered.
                    sent_channels: set[int] = set()
                    for part in _audible_combi_parts_for_controller():
                        out_ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
                        if out_ch in sent_channels:
                            continue
                        sent_channels.add(out_ch)
                        _send_pitch_bend_to_channel(out_ch, a)
        except FileNotFoundError:
            log("Combi router failed: aseqdump not found")
            state.combi_active = False
            mark_dirty("aseqdump missing")
            break
        except Exception as exc:
            log(f"Combi router exception: {exc}")
            time.sleep(0.5)
        finally:
            rc = proc.poll() if proc is not None else None
            if proc is not None and state.running and state.combi_active and generation == combi_router_generation:
                log(f"Combi router exited: rc={rc}; restarting")
            if generation == combi_router_generation and combi_router_proc is proc:
                combi_router_proc = None
                state.combi_router_signature = ""
            if proc is not None:
                try:
                    if proc.poll() is None:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    pass
    log("Combi router stopped")


def stop_combi_router() -> None:
    global combi_router_proc, combi_router_thread_handle, combi_router_generation
    combi_router_generation += 1
    proc = combi_router_proc
    combi_router_proc = None
    if proc is not None:
        try:
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(0.1)
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    state.combi_router_signature = ""
    combi_router_thread_handle = None


def start_combi_router() -> bool:
    global combi_router_thread_handle, combi_router_proc, combi_router_generation
    if not state.combi_active or not state.combi_parts:
        return False
    if state.current_engine != "fluidsynth":
        mark_dirty("Combi needs FluidSynth")
        return False
    if state.midi_mode == "usb_direct_raw":
        # apply_combi() normally performs this transition before channel setup.
        # Keep this fallback for direct/internal calls, but do not rely on it
        # during normal Load because a restart here would erase the just-sent
        # Program/CC setup.
        state.midi_mode = "alsa_midi"
        state.midi_selected_name = midi_mode_to_label("alsa_midi")
        refresh_midi_options(quiet=True)
        restart_engine(state.sf_index, state.dac_index)
    else:
        reconnect_midi_to_fluidsynth(force_draw=False)

    src, src_name = choose_alsa_seq_input()
    if not src:
        mark_dirty("Combi: no ALSA MIDI input")
        return False
    state.selected_alsa_input = src
    state.selected_alsa_input_name = src_name or src
    state.midi_src_port = src
    state.midi_src_name = src_name or src
    dst = find_fluidsynth_port()
    if dst:
        state.fluid_dst_port = dst
    signature = f"{src}|{state.current_combi_name}|{len(state.combi_parts)}"
    if (
        combi_router_proc is not None
        and combi_router_proc.poll() is None
        and state.combi_router_signature == signature
        and combi_router_thread_handle is not None
        and combi_router_thread_handle.is_alive()
    ):
        state.midi_connected = True
        refresh_midi_display_text()
        return True
    _disconnect_all_midi_routes_to_fluidsynth()
    stop_combi_router()
    combi_router_generation += 1
    generation = combi_router_generation
    combi_router_thread_handle = threading.Thread(target=_combi_router_thread, args=(generation,), daemon=True)
    combi_router_thread_handle.start()
    state.midi_connected = True
    refresh_midi_display_text()
    return True


def make_combi_browse_snapshot() -> dict:
    return {
        "sf_index": state.sf_index,
        "sf_name": state.sf_name,
        "current_engine": state.current_engine,
        "current_preset_bank": state.current_preset_bank,
        "current_preset_program": state.current_preset_program,
        "current_preset_name": state.current_preset_name,
        "current_instrument_path": state.current_instrument_path,
        "current_combi_name": state.current_combi_name,
        "combi_active": state.combi_active,
        "combi_parts": list(state.combi_parts or []),
        "combi_input_channel": state.combi_input_channel,
        "midi_mode": state.midi_mode,
    }


def begin_combi_browse_session() -> None:
    if state.combi_browse_snapshot is None:
        state.combi_browse_snapshot = make_combi_browse_snapshot()
    state.combi_preview_active = False
    state.previewed_combi_index = None


def restore_combi_browse_snapshot() -> None:
    snap = state.combi_browse_snapshot
    if not snap:
        return
    stop_combi_router()
    state.combi_active = bool(snap.get("combi_active", False))
    state.combi_parts = list(snap.get("combi_parts") or [])
    state.current_combi_name = snap.get("current_combi_name")
    state.combi_input_channel = _safe_int(snap.get("combi_input_channel", COMBI_INPUT_CHANNEL), COMBI_INPUT_CHANNEL)
    state.midi_mode = str(snap.get("midi_mode") or state.midi_mode)

    old_sf_index = _safe_int(snap.get("sf_index", state.sf_index), state.sf_index)
    if 0 <= old_sf_index < len(SOUNDFONTS) and old_sf_index != state.sf_index:
        show_modal_message("Restoring sound...", SOUNDFONTS[old_sf_index][1])
        restart_engine(old_sf_index, state.dac_index)
        clear_modal_message()
    else:
        state.sf_index = old_sf_index
        state.sf_name = str(snap.get("sf_name") or state.sf_name)

    if state.combi_active and state.combi_parts:
        for part in state.combi_parts:
            _send_channel_setup_for_part(part)
        start_combi_router()
    else:
        state.current_preset_bank = _safe_int(snap.get("current_preset_bank", 0), 0)
        state.current_preset_program = _safe_int(snap.get("current_preset_program", 0), 0)
        state.current_preset_name = str(snap.get("current_preset_name") or state.current_preset_name)
        apply_preset(
            state.current_preset_bank,
            state.current_preset_program,
            state.current_preset_name,
            engine=str(snap.get("current_engine") or "fluidsynth"),
            path=snap.get("current_instrument_path"),
        )
    state.combi_preview_active = False


def finish_combi_browse_session() -> None:
    state.combi_browse_snapshot = None
    state.combi_preview_active = False
    state.previewed_combi_index = None


def enter_combi_detail_screen(event: str = "Combi loaded") -> None:
    state.ui_mode = "submenu"
    state.submenu_key = "combi_detail"
    state.submenu_index = 0
    state.submenu_return_mode = "sound"
    invalidate_full_display()
    mark_dirty(event)


def apply_default_combi() -> None:
    combis = load_user_combis()
    if combis:
        apply_combi(combis[0])
    else:
        mark_dirty("No combis")


def apply_combi(item: dict, *, leave_after: bool = True, preview: bool = False) -> None:
    t0 = time.perf_counter()
    if block_sound_change_while_playing():
        return
    combi = normalize_combi(item)
    if not combi:
        mark_dirty("Invalid combi")
        return

    label_for_modal = shorten_text(str(combi.get("name") or "Combi"), 24)
    show_modal_message("Loading Combi...", label_for_modal)

    # Stop the previous Combi router as early as possible.  Otherwise the old
    # router thread may see state.combi_active=True while SoundFont/MIDI mode is
    # being changed and may restart aseqdump once or twice during the new load.
    # The new router is started once at the end after all channel setup is done.
    stop_combi_router()
    state.combi_active = False

    # Combi always runs on FluidSynth with an ALSA sequencer input owned by the
    # Python router.  Switch the MIDI backend state BEFORE loading the required
    # SF2 so a Yoshimi/RAW -> Combi transition starts FluidSynth only once,
    # directly as ALSA_SEQ.  The previous 260707a ordering could start
    # FluidSynth as ALSA_RAW and then immediately restart it as ALSA_SEQ.
    if state.current_engine != "fluidsynth":
        log(f"Combi requested while {state.current_engine}; switching to FluidSynth")

    midi_transition_to_alsa = (state.midi_mode == "usb_direct_raw")
    if midi_transition_to_alsa:
        log("Combi switching MIDI mode: USB direct RAW -> ALSA MIDI")
        state.midi_mode = "alsa_midi"
        state.midi_selected_name = midi_mode_to_label("alsa_midi")
        refresh_midi_options(quiet=True)

    required_sf2 = Path(str(combi.get("sf2") or "")).name
    if not ensure_combi_soundfont_loaded(required_sf2, manage_modal=False, force_restart=midi_transition_to_alsa):
        clear_modal_message()
        return
    t_sf = time.perf_counter()

    reconnect_midi_to_fluidsynth(force_draw=False)
    if state.current_engine != "fluidsynth" or fluid_proc is None or fluid_proc.poll() is not None:
        clear_modal_message()
        mark_dirty("Combi engine restart failed")
        return
    t_midi = time.perf_counter()

    clear_current_user_preset_state()
    reset_sound_edit_to_defaults()
    state.current_combi_name = str(combi.get("name") or "Combi")
    state.combi_parts = list(combi.get("parts") or [])
    state.combi_input_channel = _safe_int(combi.get("input_channel", COMBI_INPUT_CHANNEL), COMBI_INPUT_CHANNEL)

    ok = False
    for part in state.combi_parts:
        ok = _send_channel_setup_for_part(part) or ok

    # Keep GM drum-pad behavior alive in Combi mode.  Compact controllers often
    # send pads on MIDI CH10 while keys use CH1.  Because Combi mode disconnects
    # the direct MIDI route and handles events in Python, explicitly prepare
    # FluidSynth CH10 as a standard drum channel.
    send_fluidsynth_command("drums 9 on")
    send_fluidsynth_command("bank 9 128")
    send_fluidsynth_command("prog 9 0")
    send_fluidsynth_command("select 9 0 128 0")

    # A predictable default controller baseline for all used channels.
    for part in state.combi_parts:
        ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
        for param in SOUND_EDIT_PARAMS:
            try:
                send_fluidsynth_command(f"cc {ch} {int(param['cc'])} {int(param['default'])}")
            except Exception:
                pass

    t_setup = time.perf_counter()
    state.combi_active = True
    router_ok = start_combi_router()
    t_router = time.perf_counter()
    log(
        "Combi apply timing: "
        f"total={(t_router - t0) * 1000:.0f} ms "
        f"sf={(t_sf - t0) * 1000:.0f} ms "
        f"midi={(t_midi - t_sf) * 1000:.0f} ms "
        f"setup={(t_setup - t_midi) * 1000:.0f} ms "
        f"router={(t_router - t_setup) * 1000:.0f} ms "
        f"parts={len(state.combi_parts)} preview={bool(preview)}"
    )
    label = shorten_text(state.current_combi_name, 20)
    clear_modal_message()
    state.combi_preview_active = bool(preview)
    if leave_after:
        finish_combi_browse_session()
        # Do not jump back to Home after loading.  A Combi is a performance
        # configuration, so show the active parts/layers immediately.
        enter_combi_detail_screen(f"Combi loaded: {label}" if router_ok else (f"Combi set: {label}" if ok else "Combi setup queued"))
    else:
        # Stay on the Combi list after R/Preview, but make the successful
        # preview much more visible than the subtle "*" mark alone.
        # This reuses the existing transient footer mechanism, so the normal
        # footer automatically returns after a short hold time.
        if router_ok:
            show_footer_message(f"Preview loaded: {label}", COMBI_PREVIEW_FOOTER_HOLD_SEC)
        else:
            show_footer_message(f"Preview setup: {label}", COMBI_PREVIEW_FOOTER_HOLD_SEC)


def preview_combi_at_index(index: int) -> None:
    if not state.combi_entries:
        state.combi_entries = load_user_combis()
    if not state.combi_entries:
        mark_dirty("No combis")
        return
    idx = clamp_index(index, len(state.combi_entries))
    state.submenu_index = idx
    apply_combi(state.combi_entries[idx], leave_after=False, preview=True)
    state.previewed_combi_index = idx


def clear_combi_state_for_explicit_sound_load() -> None:
    """End the Combi performance lock only when the user explicitly loads another sound."""
    stop_combi_router()
    state.combi_active = False
    state.combi_parts = []
    state.current_combi_name = None
    state.combi_preview_active = False
    state.previewed_combi_index = None
    state.combi_browse_snapshot = None


def apply_preset(bank: int, program: int, name: str | None = None, *, engine: str = "fluidsynth", path: str | None = None) -> None:
    clear_combi_state_for_explicit_sound_load()
    clear_current_user_preset_state()
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
        ok = load_or_start_yoshimi_instrument(path, state.audio_device)
        if ok:
            state.current_engine = "yoshimi"
            state.current_instrument_path = path
            if current_yoshimi_patch_is_arpeggio():
                apply_yoshimi_arpeggio_speed(announce=False)
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
    clear_combi_state_for_explicit_sound_load()
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


def restart_engine(sf_index: int, dac_index: int, *, manage_modal: bool = True) -> bool:
    send_ui_status("BUSY", force=True)
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

    # 260706a: a compound sound transition (User Preset / Combi) may own the
    # modal around a nested engine restart.  Keep the old default behavior for
    # simple callers, but allow manage_modal=False so the outer transition does
    # not lose its loading modal halfway through the real sound apply.
    if manage_modal:
        show_modal_message("Loading Sound...", f"{sf_name} / {dac_name}")

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
            if manage_modal:
                clear_modal_message()
            mark_dirty("No Yoshimi JSON")
            send_ui_status("READY", force=True)
            return False
        path = str(target.get("path", current_path)).strip()
        if not path:
            if manage_modal:
                clear_modal_message()
            mark_dirty("Yoshimi path missing")
            log(f"Yoshimi restart rejected: empty path for target={target}")
            send_ui_status("READY", force=True)
            return False
        mark_dirty(f"Restarting -> Yoshimi:{target.get('name','Instrument')} / DAC:{dac_name}")
        state.current_preset_bank = int(target.get("bank", target.get("bank_id", 0)))
        state.current_preset_program = int(target.get("program", target.get("slot", 0)))
        state.current_preset_name = str(target.get("name", "Yoshimi"))
        state.current_instrument_path = path
        ok = start_yoshimi_instrument(path, audio_device)
        if not ok:
            if manage_modal:
                clear_modal_message()
            send_ui_status("READY", force=True)
            return False
        reconnect_midi_to_fluidsynth(force_draw=False)
        if manage_modal:
            clear_modal_message()
        if state.midi_connected:
            mark_dirty(f"Active -> Yoshimi/{state.current_preset_name}")
        else:
            show_footer_message("Sound loaded / MIDI waiting", 1.5)
        send_ui_status("READY", force=True)
        return True

    mark_dirty(f"Restarting -> SF:{sf_name} / DAC:{dac_name}")
    ok = start_fluidsynth(sf_path, audio_device)
    if not ok:
        if manage_modal:
            clear_modal_message()
        send_ui_status("READY", force=True)
        return False
    reconnect_midi_to_fluidsynth(force_draw=False)
    if manage_modal:
        clear_modal_message()
    if state.midi_connected:
        mark_dirty(f"Active -> SF:{sf_name} / DAC:{dac_name}")
    else:
        show_footer_message("Sound loaded / MIDI waiting", 1.5)
    send_ui_status("READY", force=True)
    return True

def send_current_engine_panic() -> bool:
    """Send a lightweight MIDI panic to the currently running synth engine.

    Quick Menu > MIDI Panic is an emergency silence command, not a sound
    refresh.  Do not restart FluidSynth/Yoshimi and do not reload SoundFonts or
    presets here; Down long-press owns the heavier Refresh Sound behavior.
    """
    ok = False

    # FluidSynth accepts CLI commands on stdin in both RAW and SEQ modes.
    # Send sustain off first, then All Notes Off and All Sound Off.
    if state.current_engine == "fluidsynth":
        for ch in range(16):
            ok = send_fluidsynth_command(f"cc {ch} 64 0") or ok
            ok = send_fluidsynth_command(f"cc {ch} 123 0") or ok
            ok = send_fluidsynth_command(f"cc {ch} 120 0") or ok
        return ok

    # Yoshimi is controlled through ALSA sequencer MIDI, so use the same tiny
    # SMF mechanism used for external hardware modules.
    dst = state.fluid_dst_port if state.fluid_dst_port not in {None, "", "-"} else find_fluidsynth_port()
    if dst:
        tmp_path = "/tmp/fluidardule_engine_panic.mid"
        try:
            write_external_panic_midi_file(tmp_path)
            p = subprocess.run(
                ["aplaymidi", "-p", dst, tmp_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            ok = (p.returncode == 0)
        except Exception as exc:
            log(f"Engine MIDI panic failed: {exc}")

    return ok


def midi_panic() -> None:
    send_ui_status("BUSY", force=True)
    # If a MIDI file is currently playing, stop that dedicated player first.
    # Otherwise panic can appear ineffective because the file player keeps sounding.
    if state.player_proc_kind == "midi_file":
        stop_player_only()
        time.sleep(0.05)

    ok = send_current_engine_panic()
    if state.external_midi_out_mode == "mirror" or state.external_midi_connected:
        send_external_midi_panic()

    if state.player_proc_kind is None:
        state.player_status = "Stopped"
        state.player_paused = False
        set_play_led("OFF")

    mark_dirty("MIDI Panic" if ok else "MIDI Panic sent")
    show_footer_message("MIDI Panic: notes off", 0.8)
    send_ui_status("READY", force=True)


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


def write_external_panic_midi_file(path: str) -> None:
    """Write a tiny SMF that sends panic CCs to all 16 MIDI channels."""
    def vlq(value: int) -> bytes:
        value = max(0, int(value))
        buf = [value & 0x7F]
        value >>= 7
        while value:
            buf.insert(0, (value & 0x7F) | 0x80)
            value >>= 7
        return bytes(buf)

    events = bytearray()
    first = True
    # CC64 Sustain Off, CC120 All Sound Off, CC123 All Notes Off, CC121 Reset All Controllers.
    # Send them on all channels. Delta time is zero between events.
    for ch in range(16):
        for cc in (64, 120, 123, 121):
            events.extend(vlq(0 if first else 1))
            events.extend(bytes([0xB0 | ch, cc, 0]))
            first = False
    events.extend(vlq(1))
    events.extend(b"\xFF\x2F\x00")

    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + (96).to_bytes(2, "big")
    track = b"MTrk" + len(events).to_bytes(4, "big") + bytes(events)
    Path(path).write_bytes(header + track)


def send_external_midi_panic() -> None:
    """Send All Sound Off / All Notes Off to the external USB MIDI OUT."""
    refresh_external_midi_state(quiet=True)
    if not state.external_midi_port:
        return
    tmp_path = "/tmp/fluidardule_ext_midi_panic.mid"
    try:
        write_external_panic_midi_file(tmp_path)
        subprocess.run(
            ["aplaymidi", "-p", state.external_midi_port, tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
        state.external_midi_connected = True
    except Exception as exc:
        log(f"External MIDI panic failed: {exc}")


def write_external_pc_midi_file(path: str, program_index: int, channel: int = 1) -> None:
    """Write a tiny SMF containing one Program Change event."""
    program_index = max(0, min(127, int(program_index)))
    channel = max(1, min(16, int(channel)))
    status = 0xC0 | (channel - 1)

    events = bytearray()
    # delta=0, Program Change, program number, delta=1, End of Track
    events.extend(b"\x00")
    events.extend(bytes([status, program_index]))
    events.extend(b"\x01\xFF\x2F\x00")

    header = (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + (96).to_bytes(2, "big")
    )
    track = b"MTrk" + len(events).to_bytes(4, "big") + bytes(events)
    Path(path).write_bytes(header + track)


def send_external_midi_program_change(program_index: int, channel: int = 1) -> bool:
    """Send a manual GM Program Change to the external USB MIDI OUT.

    Use a tiny temporary SMF with aplaymidi because the USB MIDI cable is
    already managed as an ALSA sequencer port elsewhere in this script.  Do not
    wait for aplaymidi here; a one-event SMF exits on its own, and waiting with
    a short timeout caused false failure messages even though the module did
    change sounds.
    """
    refresh_external_midi_state(quiet=True)
    if not state.external_midi_port:
        mark_dirty("External MIDI missing")
        return False

    program_index = max(0, min(127, int(program_index)))
    channel = max(1, min(16, int(channel)))
    tmp_path = "/tmp/fluidardule_ext_midi_pc.mid"
    try:
        write_external_pc_midi_file(tmp_path, program_index, channel)
        subprocess.Popen(
            ["aplaymidi", "-p", state.external_midi_port, tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            text=True,
        )
        state.external_midi_connected = True
        log(f"External MIDI PC CH{channel} -> {program_index + 1:03d} {GM_PROGRAM_NAMES[program_index]} via {state.external_midi_port}")
        return True
    except FileNotFoundError:
        state.external_midi_connected = False
        mark_dirty("aplaymidi missing")
        return False
    except Exception as exc:
        state.external_midi_connected = False
        log(f"External MIDI PC failed: {exc}")
        return False



def schedule_external_midi_pc_preview(program_index: int) -> None:
    program_index = max(0, min(127, int(program_index)))
    state.external_midi_pc_index = program_index
    state.pending_external_midi_pc_index = program_index
    state.pending_external_midi_pc_due = time.time() + EXTERNAL_MIDI_PC_PREVIEW_DEBOUNCE_SEC
    mark_dirty(f"PC preview: {shorten_text(gm_program_label(program_index), 20)}")


def process_pending_external_midi_pc_preview() -> None:
    if state.pending_external_midi_pc_index is None:
        return
    if state.ui_mode != "submenu" or state.submenu_key != "external_midi_pc":
        state.pending_external_midi_pc_index = None
        state.pending_external_midi_pc_due = 0.0
        return
    if time.time() < state.pending_external_midi_pc_due:
        return
    index = state.pending_external_midi_pc_index
    state.pending_external_midi_pc_index = None
    state.pending_external_midi_pc_due = 0.0
    ok = send_external_midi_program_change(index, state.external_midi_pc_channel)
    mark_dirty(f"PC sent: {shorten_text(gm_program_label(index), 20)}" if ok else "External PC preview failed")


def move_external_midi_pc_selection(delta: int) -> None:
    indices = gm_current_category_program_indices()
    if not indices:
        mark_dirty("No GM programs")
        return
    current = state.external_midi_pc_index
    try:
        pos = indices.index(current)
    except ValueError:
        pos = clamp_index(state.submenu_index, len(indices))
    new_pos = max(0, min(len(indices) - 1, pos + int(delta)))
    if new_pos == pos:
        mark_dirty("First item" if delta < 0 else "Last item")
        return
    state.submenu_index = new_pos
    schedule_external_midi_pc_preview(indices[new_pos])


def next_external_midi_pc_category() -> None:
    current_cat = gm_category_index_for_program(state.external_midi_pc_index)
    next_cat = (current_cat + 1) % 16
    new_index = gm_category_base(next_cat)
    state.submenu_index = 0

    # The GM program list changes completely when the category changes.
    # Force a full redraw so the TFT partial-update cache does not leave
    # stale rows from the previous category on screen.
    invalidate_full_display()

    schedule_external_midi_pc_preview(new_index)

def start_external_midi_file_mirror(path: str) -> None:
    """Play a MIDI file to the external USB MIDI OUT in parallel with audio playback.

    This is used only when Extension > External MIDI OUT is set to Mirror.
    Live SEQ input mirroring is handled separately with aconnect.
    """
    global player_ext_midi_proc
    if state.external_midi_out_mode != "mirror":
        return
    refresh_external_midi_state(quiet=True)
    if not state.external_midi_port:
        state.external_midi_connected = False
        return
    if Path(path).suffix.lower() not in (".mid", ".midi"):
        return
    try:
        player_ext_midi_proc = subprocess.Popen(
            ["aplaymidi", "-p", state.external_midi_port, path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            text=True,
        )
        state.external_midi_connected = True
        log(f"External MIDI file mirror -> {state.external_midi_port}: {Path(path).name}")
    except FileNotFoundError:
        state.external_midi_connected = False
        mark_dirty("aplaymidi missing")
    except Exception as exc:
        state.external_midi_connected = False
        mark_dirty(f"Ext MIDI file failed: {exc}")


def stop_external_midi_file_mirror(*, panic: bool = True) -> None:
    global player_ext_midi_proc
    proc = player_ext_midi_proc
    player_ext_midi_proc = None
    if proc is not None:
        try:
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(0.2)
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    if panic:
        # Killing aplaymidi can leave notes sounding on an external module.
        # FluidSynth is reset internally, but hardware modules need explicit MIDI panic.
        send_external_midi_panic()


def stop_player_only() -> None:
    global player_proc
    stop_external_midi_file_mirror()
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
    send_ui_status("BUSY", force=True)
    global player_proc
    cmd, kind = build_player_command(path)

    if not cmd:
        mark_dirty("Unsupported file")
        send_ui_status("READY", force=True)
        return

    show_modal_message("Loading...", shorten_text(Path(path).name, 24))

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
        clear_modal_message()
        send_ui_status("READY", force=True)
        return
    except Exception as exc:
        mark_dirty(f"Player start failed: {exc}")
        if kind == "media":
            restart_engine(state.sf_index, state.dac_index)
        clear_modal_message()
        send_ui_status("READY", force=True)
        return

    state.player_path = path
    state.player_proc_kind = kind
    if kind == "midi_file":
        start_external_midi_file_mirror(path)
    state.player_paused = False
    state.player_status = "Playing"
    state.player_stop_requested = False
    state.player_origin_dir = str(Path(path).parent)
    state.player_return_mode = "file_browser"
    state.player_radio_station_id = None
    state.ui_mode = "player"
    invalidate_full_display()
    set_play_led("ON")
    clear_modal_message()
    mark_dirty(f"Play {Path(path).name}")
    send_ui_status("READY", force=True)


def toggle_pause_player() -> None:
    global player_proc
    if player_proc is None or player_proc.poll() is not None:
        mark_dirty("No active player")
        return
    try:
        pgid = os.getpgid(player_proc.pid)
        if state.player_paused:
            os.killpg(pgid, signal.SIGCONT)
            if player_ext_midi_proc is not None and player_ext_midi_proc.poll() is None:
                try:
                    os.killpg(os.getpgid(player_ext_midi_proc.pid), signal.SIGCONT)
                except Exception:
                    pass
            state.player_paused = False
            state.player_status = "Playing"
            set_play_led("ON")
            log(f"PLAYER resume kind={state.player_proc_kind} path={state.player_path}")
            mark_dirty("Resume")
        else:
            os.killpg(pgid, signal.SIGSTOP)
            if player_ext_midi_proc is not None and player_ext_midi_proc.poll() is None:
                try:
                    os.killpg(os.getpgid(player_ext_midi_proc.pid), signal.SIGSTOP)
                except Exception:
                    pass
            # Pause freezes the external aplaymidi process as well. Send a short
            # external panic so sustained notes do not hang while paused.
            if state.player_proc_kind == "midi_file":
                send_external_midi_panic()
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
    stop_external_midi_file_mirror()
    if finished_kind == "media":
        auto_advanced = try_auto_advance_media()
        if auto_advanced:
            return

    resume_internal_sound_after_playback("Finished")

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
      P0 Precise: always +/-1 for precise editing
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
    profile = max(0, min(3, int(getattr(state, "encoder_accel_profile", ENCODER_ACCEL_DEFAULT_PROFILE))))

    if profile in (0, 1):
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
# User Preset helpers
# =========================================================

def load_user_presets() -> list[dict]:
    """Load user presets as an ordered, dynamic JSON list.

    Older slot-based files are accepted for backward compatibility, but the
    rewritten file no longer stores or enforces slot numbers.
    """
    path = Path(USER_PRESET_PATH)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"user preset load failed: {exc}")
        return []

    if isinstance(payload, dict):
        items = payload.get("presets", [])
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    presets: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cleaned = dict(item)
        cleaned.pop("slot", None)
        presets.append(cleaned)
    return presets


def save_user_presets(presets: list[dict]) -> bool:
    path = Path(USER_PRESET_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_presets = []
    for item in presets:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        entry.pop("slot", None)
        cleaned_presets.append(entry)
    payload = {
        "format": "fluidardule_user_presets_v2",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "presets": cleaned_presets,
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        invalidate_user_preset_cache()
        return True
    except Exception as exc:
        log(f"user preset save failed: {exc}")
        mark_dirty("User preset save failed")
        return False


def current_user_preset_base_name() -> str:
    source_name = source_name_for_index(state.sf_index) if 0 <= state.sf_index < len(SOUNDFONTS) else state.sf_name
    return re.sub(r"\s+", " ", f"{source_name} - {state.current_preset_name}".strip(" -")).strip() or "User Preset"


def sound_edit_has_user_changes() -> bool:
    # User Preset names get an "ed N" suffix only when the current sound has
    # actually been edited from the normal Sound Edit defaults.  Volume is not
    # part of User Preset state and is intentionally ignored here.
    return bool(state.sound_edit_modified)


def current_user_preset_kind_for_save() -> str:
    return "edited" if sound_edit_has_user_changes() else "bookmark"


def user_preset_sound_edit_has_nondefault_values(item: dict) -> bool:
    """Infer edited state from saved CC values for older User Preset JSON files.

    Newer presets explicitly store user_kind / edited / sound_edit_modified.
    Older presets may only have a full sound_edit dictionary, so compare it
    against the current Sound Edit defaults and treat any non-default CC value
    as an edited preset.
    """
    values = item.get("sound_edit") if isinstance(item, dict) else None
    if not isinstance(values, dict):
        return False

    defaults = default_sound_edit_values()
    for key, value in values.items():
        try:
            cc = int(key)
            val = int(value)
        except Exception:
            continue
        if cc in defaults and val != int(defaults[cc]):
            return True
    return False


def user_preset_is_edited(item: dict) -> bool:
    if not isinstance(item, dict):
        return False

    kind = str(item.get("user_kind", "")).lower().strip()
    if kind == "edited":
        return True
    if item.get("edited") is True:
        return True

    modified = item.get("sound_edit_modified")
    if isinstance(modified, list) and len(modified) > 0:
        return True

    if user_preset_sound_edit_has_nondefault_values(item):
        return True

    # Backward-compatible recognition for presets saved before user_kind was
    # added, because edited names were auto-suffixed as "ed N".
    name = str(item.get("name", ""))
    return bool(re.search(r"\bed\s*\d+$", name, re.IGNORECASE))


def user_preset_display_label(index: int, item: dict, *, main: bool = False) -> str:
    """Return compact display label for User Presets.

    Bookmark:
      list: 04 Power Drum 2
      main: original source/preset display, not this helper

    Edited:
      list: 04*Power Drum 2 ed1
      main: 04*Power Drum 2 ed1
    """
    name_limit = 20 if main else 23
    name = shorten_text(str(item.get("name", "User Preset")), name_limit)
    number = f"{index + 1:02d}"
    if user_preset_is_edited(item):
        return f"{number}*{name}"
    return f"{number} {name}"


def clear_current_user_preset_state() -> None:
    state.current_user_preset_name = None
    state.current_user_preset_kind = None


def user_preset_existing_names(presets: list[dict], ignore_index: int | None = None) -> set[str]:
    existing: set[str] = set()
    for i, item in enumerate(presets):
        if ignore_index is not None and i == ignore_index:
            continue
        if item and str(item.get("name", "")).strip():
            existing.add(str(item.get("name", "")).strip())
    return existing


def user_preset_unique_name(base_name: str, presets: list[dict], ignore_index: int | None = None) -> str:
    base = re.sub(r"\s+", " ", str(base_name or "User Preset")).strip() or "User Preset"
    existing = user_preset_existing_names(presets, ignore_index=ignore_index)

    if sound_edit_has_user_changes():
        n = 1
        while True:
            candidate = f"{base} ed {n}"
            if candidate not in existing:
                return candidate
            n += 1

    if base not in existing:
        return base
    n = 2
    while True:
        candidate = f"{base} ({n})"
        if candidate not in existing:
            return candidate
        n += 1


def find_matching_user_preset_index(presets: list[dict], base_name: str | None = None) -> int | None:
    base = re.sub(r"\s+", " ", str(base_name or current_user_preset_base_name())).strip()
    if not base:
        return None
    for i, item in enumerate(presets):
        if str(item.get("name", "")).strip() == base:
            return i
    return None


def build_current_user_preset(presets: list[dict], overwrite_index: int | None = None) -> dict:
    source_path = source_path_for_index(state.sf_index) if 0 <= state.sf_index < len(SOUNDFONTS) else ""
    source_name = source_name_for_index(state.sf_index) if 0 <= state.sf_index < len(SOUNDFONTS) else state.sf_name
    base_name = current_user_preset_base_name()
    name = base_name
    if overwrite_index is None:
        name = user_preset_unique_name(base_name, presets, ignore_index=None)
    elif 0 <= overwrite_index < len(presets):
        # Keep a manually renamed user preset name when overwriting it.
        name = str(presets[overwrite_index].get("name") or base_name).strip() or base_name
    sound_edit = {str(int(k)): int(v) for k, v in sorted(state.sound_edit_values.items())}
    modified_ccs = [int(k) for k in sorted(state.sound_edit_modified)]
    user_kind = "edited" if modified_ccs else "bookmark"
    return {
        "name": name,
        "user_kind": user_kind,
        "edited": user_kind == "edited",
        "sound_edit_modified": modified_ccs,
        "engine": state.current_engine,
        "source_name": source_name,
        "source_path": source_path,
        "sf_index_hint": state.sf_index,
        "bank": int(state.current_preset_bank),
        "program": int(state.current_preset_program),
        "preset_name": state.current_preset_name,
        "instrument_path": state.current_instrument_path,
        "sound_edit": sound_edit,
    }


def user_preset_label(index: int, item: dict) -> str:
    return user_preset_display_label(index, item, main=False)


def enter_user_preset_save_menu() -> None:
    presets = load_user_presets()
    state.user_preset_count_cache = len(presets)
    state.user_preset_entries = presets
    state.ui_mode = "submenu"
    state.submenu_key = "user_preset_save"
    state.submenu_return_mode = "quick_menu"
    match_index = find_matching_user_preset_index(presets)
    # Row 0 is always "Save as New". If the same auto-name already exists,
    # place the cursor on that existing preset so SELECT naturally offers
    # Overwrite? instead of silently creating another copy.
    state.submenu_index = (match_index + 1) if match_index is not None else 0
    state.user_preset_target_index = max(0, state.submenu_index - 1)
    invalidate_full_display()
    mark_dirty("Save User Preset")


def enter_user_preset_load_menu(return_mode: str | None = None) -> None:
    presets = load_user_presets()
    state.user_preset_count_cache = len(presets)
    if not presets:
        mark_dirty("No user presets")
        return
    state.user_preset_entries = presets
    state.ui_mode = "submenu"
    state.submenu_key = "user_preset_load"
    state.submenu_return_mode = return_mode or "main"
    state.submenu_index = 0
    state.previewed_user_preset_index = None
    invalidate_full_display()
    # Keep User Preset behavior consistent with SF2 preset browsing:
    # the first highlighted row should sound immediately, not only after
    # the cursor is moved once.  This is intentionally a preview, so the
    # user remains on the User Preset screen.
    preview_user_preset_at_index(0)


def save_current_user_preset_as_new() -> None:
    presets = load_user_presets()
    entry = build_current_user_preset(presets, overwrite_index=None)
    presets.append(entry)
    if save_user_presets(presets):
        state.user_preset_entries = presets
        mark_dirty(f"Saved: {shorten_text(entry['name'], 18)}")
        state.ui_mode = "quick_menu"
        state.submenu_key = None
        state.submenu_return_mode = None
        invalidate_full_display()


def overwrite_user_preset(index: int) -> None:
    presets = load_user_presets()
    if index < 0 or index >= len(presets):
        mark_dirty("Preset missing")
        return
    entry = build_current_user_preset(presets, overwrite_index=index)
    presets[index] = entry
    if save_user_presets(presets):
        state.user_preset_entries = presets
        mark_dirty(f"Saved: {shorten_text(entry['name'], 18)}")
        state.ui_mode = "quick_menu"
        state.submenu_key = None
        state.submenu_return_mode = None
        invalidate_full_display()


def delete_user_preset(index: int) -> None:
    presets = load_user_presets()
    if index < 0 or index >= len(presets):
        mark_dirty("Preset missing")
        return
    name = str(presets[index].get("name", "User Preset"))
    del presets[index]
    if save_user_presets(presets):
        state.user_preset_entries = presets
        if presets:
            state.ui_mode = "submenu"
            state.submenu_key = "user_preset_load"
            state.submenu_index = clamp_index(index, len(presets))
            invalidate_full_display()
            mark_dirty(f"Deleted: {shorten_text(name, 18)}")
        else:
            leave_submenu("No user presets")


def move_user_preset_to_top(index: int) -> None:
    """Move the selected User Preset to list position 1.

    Sound Source > User Preset uses SELECT as "load default user preset",
    so moving a favorite to the top makes it the default without adding
    another submenu level.
    """
    presets = load_user_presets()
    if index < 0 or index >= len(presets):
        mark_dirty("Preset missing")
        return
    if index == 0:
        state.user_preset_entries = presets
        state.submenu_key = "user_preset_load"
        state.submenu_index = 0
        invalidate_full_display()
        mark_dirty("Already at top")
        return

    item = presets.pop(index)
    presets.insert(0, item)

    if save_user_presets(presets):
        state.user_preset_entries = presets
        state.user_preset_count_cache = len(presets)
        state.user_preset_target_index = 0
        state.submenu_key = "user_preset_load"
        state.submenu_index = 0
        invalidate_full_display()
        mark_dirty(f"Moved top: {shorten_text(str(item.get('name', 'User Preset')), 16)}")



def enter_user_preset_manage_menu() -> None:
    presets = load_user_presets()
    if not presets:
        mark_dirty("No user presets")
        return
    state.user_preset_entries = presets
    state.user_preset_target_index = clamp_index(state.submenu_index, len(presets))
    state.submenu_key = "user_preset_manage"
    state.submenu_index = 0
    invalidate_full_display()
    mark_dirty("Manage preset")


def start_user_preset_rename(index: int) -> None:
    presets = load_user_presets()
    if index < 0 or index >= len(presets):
        mark_dirty("Preset missing")
        return
    if not user_preset_is_edited(presets[index]):
        mark_dirty("Rename edited only")
        return
    name = str(presets[index].get("name", "User Preset")).strip() or "User Preset"
    state.user_preset_entries = presets
    state.user_preset_target_index = index
    state.user_preset_rename_text = name[:USER_PRESET_RENAME_MAX_LEN] or " "
    state.user_preset_rename_cursor = clamp_index(len(state.user_preset_rename_text) - 1, len(state.user_preset_rename_text))
    state.submenu_key = "user_preset_rename"
    state.submenu_index = 0
    invalidate_full_display()
    mark_dirty("Rename preset")


def save_user_preset_rename() -> None:
    presets = load_user_presets()
    idx = state.user_preset_target_index
    if idx < 0 or idx >= len(presets):
        mark_dirty("Preset missing")
        return
    if not user_preset_is_edited(presets[idx]):
        mark_dirty("Rename edited only")
        return
    new_name = re.sub(r"\s+", " ", state.user_preset_rename_text).strip()
    if not new_name:
        mark_dirty("Name empty")
        return
    presets[idx]["name"] = new_name[:USER_PRESET_RENAME_MAX_LEN]
    if save_user_presets(presets):
        state.user_preset_entries = presets
        state.submenu_key = "user_preset_load"
        state.submenu_index = clamp_index(idx, len(presets))
        state.user_preset_rename_text = ""
        state.user_preset_rename_cursor = 0
        invalidate_full_display()
        mark_dirty(f"Renamed: {shorten_text(new_name, 18)}")


def cancel_user_preset_rename() -> None:
    state.submenu_key = "user_preset_manage"
    state.submenu_index = 0
    state.user_preset_rename_text = ""
    state.user_preset_rename_cursor = 0
    invalidate_full_display()
    mark_dirty("Rename canceled")


def rename_char_delta(delta: int) -> None:
    text = state.user_preset_rename_text or " "
    cursor = clamp_index(state.user_preset_rename_cursor, len(text))
    ch = text[cursor]
    chars = USER_PRESET_RENAME_CHARS
    try:
        pos = chars.index(ch)
    except ValueError:
        pos = 0
    new_ch = chars[(pos + int(delta)) % len(chars)]
    state.user_preset_rename_text = text[:cursor] + new_ch + text[cursor + 1:]
    state.user_preset_rename_cursor = cursor
    mark_dirty("Edit name")


def move_rename_cursor(delta: int) -> None:
    text = state.user_preset_rename_text or " "
    state.user_preset_rename_cursor = max(0, min(len(text) - 1, state.user_preset_rename_cursor + int(delta)))
    mark_dirty("Move cursor")


def insert_rename_space() -> None:
    text = state.user_preset_rename_text or " "
    if len(text) >= USER_PRESET_RENAME_MAX_LEN:
        mark_dirty("Name max length")
        return
    cursor = clamp_index(state.user_preset_rename_cursor, len(text))
    state.user_preset_rename_text = text[:cursor + 1] + " " + text[cursor + 1:]
    state.user_preset_rename_cursor = cursor + 1
    mark_dirty("Insert space")


def delete_rename_char() -> None:
    text = state.user_preset_rename_text or " "
    cursor = clamp_index(state.user_preset_rename_cursor, len(text))
    if len(text) <= 1:
        state.user_preset_rename_text = " "
        state.user_preset_rename_cursor = 0
        mark_dirty("Name empty")
        return
    state.user_preset_rename_text = text[:cursor] + text[cursor + 1:]
    state.user_preset_rename_cursor = max(0, min(cursor, len(state.user_preset_rename_text) - 1))
    mark_dirty("Delete char")


def apply_sound_edit_values_from_user_preset(item: dict) -> None:
    values = item.get("sound_edit") or {}
    if not isinstance(values, dict):
        return
    for key, value in values.items():
        try:
            cc = int(key)
            val = clamp_cc_value(int(value))
        except Exception:
            continue
        state.sound_edit_values[cc] = val
        state.sound_edit_a_values[cc] = val
        default = None
        for param in SOUND_EDIT_PARAMS:
            if int(param["cc"]) == cc:
                default = int(param["default"])
                break
        if default is not None and val != default:
            state.sound_edit_modified.add(cc)
        elif default is not None:
            state.sound_edit_modified.discard(cc)
        send_sound_edit_cc(cc, val)


def find_source_index_for_user_preset(item: dict) -> int | None:
    source_path = str(item.get("source_path", "")).strip()
    source_name = str(item.get("source_name", "")).strip()
    hint = item.get("sf_index_hint")
    try:
        hint_i = int(hint)
        if 0 <= hint_i < len(SOUNDFONTS):
            if not source_path or source_path_for_index(hint_i) == source_path:
                return hint_i
    except Exception:
        pass
    for i, (path, name) in enumerate(SOUNDFONTS):
        if source_path and path == source_path:
            return i
        if source_name and name == source_name:
            return i
    return None


def user_preset_identity(item: dict, index: int | None = None) -> tuple:
    """Stable-enough identity for preview/commit de-duplication."""
    if not isinstance(item, dict):
        return (index,)
    return (
        index,
        str(item.get("name") or ""),
        str(item.get("source_path") or ""),
        str(item.get("source_name") or ""),
        str(item.get("engine") or "fluidsynth"),
        int(item.get("bank", 0) or 0),
        int(item.get("program", 0) or 0),
        str(item.get("instrument_path") or ""),
    )


def apply_user_preset(item: dict, *, leave_after: bool = True, preview: bool = False) -> bool:
    if block_sound_change_while_playing():
        return False
    if not item:
        mark_dirty("Empty preset")
        return False

    source_index = find_source_index_for_user_preset(item)
    if source_index is None:
        mark_dirty("User preset source missing")
        return False

    old_source_index = state.sf_index
    engine = str(item.get("engine", "fluidsynth")).lower().strip() or "fluidsynth"
    name = str(item.get("preset_name") or item.get("name") or "User Preset")
    bank = int(item.get("bank", 0))
    program = int(item.get("program", 0))
    instrument_path = str(item.get("instrument_path") or "").strip()
    label = shorten_text(str(item.get('name', name)), 16)

    show_modal_message("Loading Preset...", shorten_text(str(item.get("name", name)), 24))
    ok = True
    try:
        state.sf_index = source_index
        state.sf_name = source_name_for_index(source_index)

        if engine == "yoshimi":
            if not instrument_path:
                mark_dirty("User preset path missing")
                ok = False
                return False
            apply_preset(bank, program, name, engine="yoshimi", path=instrument_path)
            reconnect_midi_to_fluidsynth(force_draw=False)
            # Yoshimi does not consume FluidSynth CC edits here, but the saved
            # values remain in the JSON for future-compatible use.
        else:
            # A User Preset must recall its stored engine/source first, not merely
            # change the bank/program on whichever engine happens to be active.
            if (
                source_index != old_source_index
                or state.current_engine != "fluidsynth"
                or fluid_proc is None
                or fluid_proc.poll() is not None
            ):
                ok = restart_engine(source_index, state.dac_index, manage_modal=False)
                if not ok:
                    return False
            apply_preset(bank, program, name, engine="fluidsynth")
            apply_sound_edit_values_from_user_preset(item)
            reconnect_midi_to_fluidsynth(force_draw=False)

        state.current_user_preset_name = str(item.get("name") or name).strip() or name
        state.current_user_preset_kind = "edited" if user_preset_is_edited(item) else "bookmark"
        return True
    finally:
        clear_modal_message()
        if ok:
            if not state.midi_connected:
                show_footer_message("Preset loaded / MIDI waiting", 1.5)
            if leave_after:
                leave_submenu(f"User Preset: {label}")
            else:
                mark_dirty(f"Preview: {label}" if preview else f"User Preset: {label}")

def preview_user_preset_at_index(index: int) -> None:
    """Queue highlighted User Preset preview without leaving the browser.

    User Presets may restart engines and reapply Sound Edit values, so repeated
    immediate loads during fast UP/DOWN scrolling feel sluggish.  Match the
    debounced preview style used by heavier preset sources: move the highlight
    now, then load only after the cursor has stopped briefly.
    """
    if not USER_PRESET_PREVIEW_ON_HIGHLIGHT:
        return
    presets = state.user_preset_entries or load_user_presets()
    if not presets:
        mark_dirty("No user presets")
        return
    idx = clamp_index(index, len(presets))
    state.user_preset_entries = presets
    if state.previewed_user_preset_index != idx:
        state.previewed_user_preset_index = None
    state.submenu_index = idx
    state.pending_user_preset_preview_index = idx
    state.pending_user_preset_preview_due = time.time() + USER_PRESET_PREVIEW_DEBOUNCE_SEC
    mark_dirty(f"Preview queued: {shorten_text(str(presets[idx].get('name', 'User Preset')), 18)}")


def process_pending_user_preset_preview() -> None:
    if state.pending_user_preset_preview_index is None:
        return
    if state.ui_mode != "submenu" or state.submenu_key != "user_preset_load":
        state.pending_user_preset_preview_index = None
        state.pending_user_preset_preview_due = 0.0
        return
    if time.time() < state.pending_user_preset_preview_due:
        return
    presets = state.user_preset_entries or load_user_presets()
    if not presets:
        state.pending_user_preset_preview_index = None
        state.pending_user_preset_preview_due = 0.0
        mark_dirty("No user presets")
        return
    idx = clamp_index(state.pending_user_preset_preview_index, len(presets))
    state.pending_user_preset_preview_index = None
    state.pending_user_preset_preview_due = 0.0
    if idx != state.submenu_index:
        return
    state.user_preset_entries = presets
    if apply_user_preset(presets[idx], leave_after=False, preview=True):
        state.previewed_user_preset_index = idx


def find_current_user_preset_item() -> dict | None:
    name = str(state.current_user_preset_name or "").strip()
    if not name:
        return None
    for item in load_user_presets():
        if str(item.get("name", "")).strip() == name:
            return item
    return None


def send_combi_notes_off() -> None:
    """Silence all FluidSynth channels without changing the active Combi state."""
    for ch in range(16):
        # Sustain off first, then All Notes Off and All Sound Off.
        # Keep this lightweight: no engine restart, no Combi state reset.
        send_fluidsynth_command(f"cc {ch} 64 0")
        send_fluidsynth_command(f"cc {ch} 123 0")
        send_fluidsynth_command(f"cc {ch} 120 0")


def refresh_current_combi() -> None:
    """Re-apply the currently active Combi without leaving Combi performance mode.

    Down long-press means Refresh Sound.  In Combi mode, the current Combi is
    the current sound, so refreshing must not fall back to a single preset or
    clear state.combi_active.  It should silence stuck notes, rebuild the
    channel setup, and restart the Python router cleanly.
    """
    if not state.combi_active or not state.combi_parts:
        mark_dirty("No active Combi")
        return

    label = shorten_text(state.current_combi_name or "Combi", 24)
    show_modal_message("Refreshing Combi...", label)
    send_ui_status("BUSY", force=True)
    try:
        stop_combi_router()
        send_combi_notes_off()

        ok = False
        for part in state.combi_parts:
            ok = _send_channel_setup_for_part(part) or ok

        # Preserve the CH10 drum-pad support used by normal Combi loading.
        send_fluidsynth_command("drums 9 on")
        send_fluidsynth_command("bank 9 128")
        send_fluidsynth_command("prog 9 0")
        send_fluidsynth_command("select 9 0 128 0")

        # Re-apply the same predictable controller baseline used by apply_combi().
        for part in state.combi_parts:
            ch = max(0, min(15, _safe_int(part.get("channel", 1), 1) - 1))
            for param in SOUND_EDIT_PARAMS:
                try:
                    send_fluidsynth_command(f"cc {ch} {int(param['cc'])} {int(param['default'])}")
                except Exception:
                    pass

        router_ok = start_combi_router()
        if router_ok:
            mark_dirty(f"Combi refreshed: {label}")
            show_footer_message(f"Combi refreshed: {label}", 1.5)
        elif ok:
            mark_dirty(f"Combi setup refreshed: {label}")
            show_footer_message(f"Combi setup refreshed: {label}", 1.5)
        else:
            mark_dirty("Combi refresh queued")
    finally:
        clear_modal_message()
        send_ui_status("READY", force=True)


def refresh_current_sound() -> None:
    """Restart/re-align the current sound without using full MIDI Panic.

    This is a musical refresh action, not an emergency stop.  It restarts the
    active engine and restores the last selected sound state, including saved
    User Preset Sound Edit values or the current volatile Sound Edit values.
    """
    if block_sound_change_while_playing():
        return

    if state.combi_active:
        refresh_current_combi()
        return

    show_modal_message("Refreshing...", shorten_text(state.current_user_preset_name or state.current_preset_name, 24))

    # If the current sound came from a User Preset, reload that exact preset so
    # its source/engine and saved Sound Edit values are restored consistently.
    user_item = find_current_user_preset_item()
    if user_item is not None:
        # DOWN long-press is a refresh in place.  Do not let User Preset reload
        # call leave_submenu(), because that unexpectedly returns to Home while
        # the user is browsing another screen.
        apply_user_preset(user_item, leave_after=False)
        clear_modal_message()
        return

    sf_index = state.sf_index
    dac_index = state.dac_index
    engine = state.current_engine
    bank = state.current_preset_bank
    program = state.current_preset_program
    name = state.current_preset_name
    path = state.current_instrument_path
    saved_sound_edit_values = dict(state.sound_edit_values)
    saved_sound_edit_modified = set(state.sound_edit_modified)

    try:
        if engine == "yoshimi":
            apply_preset(bank, program, name, engine="yoshimi", path=path)
        else:
            restart_engine(sf_index, dac_index)
            apply_preset(bank, program, name, engine="fluidsynth")
            state.sound_edit_values = dict(saved_sound_edit_values)
            state.sound_edit_a_values = dict(saved_sound_edit_values)
            state.sound_edit_modified = set(saved_sound_edit_modified)
            apply_sound_edit_values_from_user_preset({"sound_edit": {str(k): v for k, v in saved_sound_edit_values.items()}})
    finally:
        clear_modal_message()

    # DOWN long-press refresh must stay exactly where the user invoked it.
    # Do not call leave_submenu() here; returning to Home/Sound Source during a
    # refresh is a navigation side effect, not part of the musical operation.
    mark_dirty("Sound refreshed")

def apply_default_user_preset() -> None:
    presets = load_user_presets()
    if not presets:
        mark_dirty("No user presets")
        return
    apply_user_preset(presets[0])

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
        state.submenu_index = 0
        current_port = state.preferred_seq_port or state.selected_alsa_input
        for i, (mode, _name) in enumerate(state.midi_options):
            if mode == state.midi_mode:
                state.submenu_index = i
                break
            if state.midi_mode == "alsa_midi" and mode.startswith("alsa_seq:"):
                if mode.split(":", 1)[1] == current_port:
                    state.submenu_index = i
                    break
    elif key == "alsa_midi_input":
        options = list_alsa_seq_input_ports()
        state.submenu_index = 0
        current_port = state.preferred_seq_port or state.selected_alsa_input
        current_name = (state.preferred_seq_name or state.selected_alsa_input_name or "").lower()
        for i, (port, label) in enumerate(options):
            if port == current_port or (current_name and label.lower() == current_name):
                state.submenu_index = i
                break
    elif key == "extension":
        refresh_wifi_status()
        refresh_external_midi_state(quiet=True)
        state.submenu_index = 0
    elif key == "wifi":
        refresh_wifi_status()
        scan_wifi_ssids()
        state.submenu_index = 0
    elif key == "arp_speed":
        state.arp_bpm = clamp_arp_bpm(state.arp_bpm)
        state.submenu_index = 0
    elif key == "external_midi_device":
        refresh_external_midi_state(quiet=True)
        ports = list_external_midi_seq_ports()
        state.submenu_index = 0
        current = state.preferred_external_midi_port or state.external_midi_port
        for i, (port, _label) in enumerate(ports):
            if port == current:
                state.submenu_index = i
                break
    elif key == "external_midi_out":
        refresh_external_midi_state(quiet=True)
        current_modes = [mode for mode, _name in EXTERNAL_MIDI_OUT_MODES]
        try:
            state.submenu_index = current_modes.index(state.external_midi_out_mode)
        except ValueError:
            state.submenu_index = 0
    elif key == "external_midi_pc":
        refresh_external_midi_state(quiet=True)
        # Program selection is category-based. Keep the selected GM program
        # globally, but show only the eight programs in its current category.
        state.submenu_index = clamp_index(state.external_midi_pc_index % 8, 8)
    elif key == "user_preset_save":
        state.user_preset_entries = load_user_presets()
        match_index = find_matching_user_preset_index(state.user_preset_entries)
        state.submenu_index = (match_index + 1) if match_index is not None else 0
    elif key == "user_preset_load":
        state.user_preset_entries = load_user_presets()
        state.submenu_index = 0
    elif key == "user_preset_overwrite":
        state.submenu_index = 0
    elif key == "user_preset_manage":
        state.submenu_index = 0
    elif key == "user_preset_rename":
        state.submenu_index = 0
    elif key == "combi_load":
        state.combi_entries = load_user_combis()
        state.submenu_index = 0
        begin_combi_browse_session()


def leave_submenu(event: str = "Back") -> None:
    state.pending_yoshimi_preview_index = None
    state.pending_yoshimi_preview_due = 0.0
    state.pending_user_preset_preview_index = None
    state.pending_user_preset_preview_due = 0.0
    target = state.submenu_return_mode or "main"
    if state.submenu_key == "soundfont":
        state.pending_resume_after_sf_apply = False
        if combi_locked():
            warn_combi_quick_blocked()
            return_to_sound_submenu("Combi active")
            return
    if state.submenu_key == "preset":
        state.preset_entries = []
        state.preset_index = 0
        state.preset_sf_index = None
        state.preset_source_name = ""
    if state.submenu_key in {"user_preset_load", "user_preset_save", "user_preset_overwrite", "user_preset_delete", "user_preset_manage", "user_preset_rename"}:
        state.user_preset_entries = []
        state.user_preset_rename_text = ""
        state.user_preset_rename_cursor = 0
    if state.submenu_key == "combi_load":
        state.combi_entries = []
    state.ui_mode = target
    invalidate_full_display()
    state.submenu_key = None
    state.submenu_index = 0
    state.submenu_return_mode = None
    mark_dirty(event)



def return_to_extension_submenu(event: str = "Extension", index: int = 0) -> None:
    """Return from an Extension child page to the first Extension menu level."""
    state.ui_mode = "submenu"
    state.submenu_key = "extension"
    state.submenu_index = int(max(0, index))
    state.submenu_return_mode = None
    invalidate_full_display()
    mark_dirty(event)


def get_submenu_options() -> list[tuple[str, bool]]:
    key = state.submenu_key
    if key == "soundfont":
        rows = [(name, i == state.sf_index) for i, (_path, name) in enumerate(SOUNDFONTS)]
        rows.append(("User Preset", False))
        rows.append(("Combi", bool(state.combi_active)))
        return rows
    if key == "preset_category":
        active_cat = categorize_preset(state.current_preset_bank, state.current_preset_program, state.current_preset_name)
        return [(cat, state.category_source_sf_index == state.sf_index and cat == active_cat) for cat in state.category_entries]
    if key == "preset":
        rows = []
        cat = ""
        try:
            if state.category_entries:
                cat = str(state.category_entries[clamp_index(state.category_index, len(state.category_entries))])
        except Exception:
            cat = ""
        for i, p in enumerate(state.preset_entries):
            label = p["name"] if p.get("engine") == "yoshimi" else f'{p["name"]} ({p["bank"]},{p["program"]})'
            if i == 0 and p.get("engine") == "yoshimi" and "arpeggio" in cat.lower():
                label = f"{label}   Speed {state.arp_bpm}"
            rows.append((
                label,
                state.preset_sf_index == state.sf_index
                and p.get("bank", p.get("bank_id", 0)) == state.current_preset_bank
                and p.get("program", p.get("slot", 0)) == state.current_preset_program,
            ))
        return rows
    if key == "dac":
        return [(name, i == state.dac_index) for i, (_dev, name) in enumerate(state.dac_options)]
    if key == "midi":
        current_port = state.preferred_seq_port or state.selected_alsa_input
        rows = []
        for mode, name in state.midi_options:
            is_current = (mode == state.midi_mode)
            if state.midi_mode == "alsa_midi" and mode.startswith("alsa_seq:"):
                is_current = (mode.split(":", 1)[1] == current_port)
            rows.append((name, is_current))
        return rows
    if key == "alsa_midi_input":
        options = list_alsa_seq_input_ports()
        if not options:
            return [("No ALSA MIDI input", False)]
        current_port = state.preferred_seq_port or state.selected_alsa_input
        current_name = (state.preferred_seq_name or state.selected_alsa_input_name or "").lower()
        return [(label, port == current_port or (current_name and label.lower() == current_name)) for port, label in options]
    if key == "extension":
        refresh_wifi_status()
        refresh_external_midi_state(quiet=True)

        rows = [
            (f"Wi-Fi [{wifi_status_label(short=True)}]", False),
            (f"Arpeggio Speed [{state.arp_bpm}]", current_yoshimi_patch_is_arpeggio()),
        ]
        if external_midi_out_available():
            # Show current Extension status directly on the first-level menu.
            # Wi-Fi is always the first Extension item; External MIDI follows.
            out_label = "Mirror" if state.external_midi_out_mode == "mirror" else "Off"
            device_label = external_midi_display_name()
            pc_label = gm_program_label(state.external_midi_pc_index)
            rows.extend([
                (f"MIDI OUT [{device_label}]: {out_label}", False),
                (f"PC Send [{device_label}]: {pc_label}", False),
            ])
        return rows
    if key == "arp_speed":
        status = "Yoshimi Arpeggio" if current_yoshimi_patch_is_arpeggio() else "Yoshimi Arpeggio only"
        return [(f"{state.arp_bpm}  {status}", False)]
    if key == "wifi":
        return wifi_menu_options()
    if key == "controls":
        return [("Sound Edit", False)]
    if key == "external_midi_device":
        ports = list_external_midi_seq_ports()
        if not ports:
            return [("External MIDI unavailable", False)]
        current = state.preferred_external_midi_port or state.external_midi_port
        return [(external_midi_display_name(label), port == current) for port, label in ports]
    if key == "external_midi_pc":
        refresh_external_midi_state(quiet=True)
        if not external_midi_out_available():
            return [("External MIDI unavailable", False)]
        return [(gm_program_label(i), i == state.external_midi_pc_index) for i in gm_current_category_program_indices()]
    if key == "external_midi_out":
        refresh_external_midi_state(quiet=True)
        enforce_external_midi_out_policy()
        if not external_midi_out_available():
            return [("External MIDI OUT unavailable", False)]
        return [(label, mode == state.external_midi_out_mode) for mode, label in EXTERNAL_MIDI_OUT_MODES]
    if key == "user_preset_save":
        if not state.user_preset_entries:
            state.user_preset_entries = load_user_presets()
        rows = [("Save as New", False)]
        rows.extend((user_preset_label(i, item), False) for i, item in enumerate(state.user_preset_entries))
        return rows
    if key == "user_preset_load":
        if not state.user_preset_entries:
            state.user_preset_entries = load_user_presets()
        return [(user_preset_label(i, item), False) for i, item in enumerate(state.user_preset_entries)]
    if key == "user_preset_overwrite":
        return [("No", False), ("Yes", False)]
    if key == "user_preset_manage":
        label = "Rename"
        try:
            presets = state.user_preset_entries or load_user_presets()
            item = presets[clamp_index(state.user_preset_target_index, len(presets))]
            if not user_preset_is_edited(item):
                label = "Rename (edited only)"
        except Exception:
            pass
        return [(label, False), ("Move to Top", False), ("Delete", False), ("Cancel", False)]
    if key == "user_preset_delete":
        return [("No", False), ("Yes", False)]
    if key == "user_preset_rename":
        return []
    if key == "combi_load":
        if not state.combi_entries:
            state.combi_entries = load_user_combis()
        return [(combi_label(i, item), str(item.get("name", "")) == str(state.current_combi_name or "")) for i, item in enumerate(state.combi_entries)] or [("No combis", False)]
    if key == "combi_detail":
        rows = []
        for i, part in enumerate(state.combi_parts or []):
            ch = _safe_int(part.get("channel", i + 1), i + 1)
            vol = max(0, min(127, _safe_int(part.get("volume", 100), 100)))
            label = str(part.get("label") or part.get("name") or part.get("preset_id") or f'{part.get("bank", 0)}:{part.get("program", 0)}')
            rows.append((f"CH{ch} {shorten_text(label, 22)}  V{vol}", False))
        return rows or [("No active parts", False)]
    if key == "placeholder":
        return [("Reserved", False)]
    return []


def apply_current_submenu_selection() -> None:
    key = state.submenu_key
    if key == "soundfont":
        if block_sound_change_while_playing():
            return
        resume_after_apply = state.pending_resume_after_sf_apply
        state.pending_resume_after_sf_apply = False
        if state.submenu_index == len(SOUNDFONTS):
            # Keep the same convention as other Sound Sources:
            # SELECT recalls a default item, RIGHT enters the full preset list.
            apply_default_user_preset()
            if resume_after_apply:
                resume_selected_browser_file_after_sf_change()
            return
        if state.submenu_index == len(SOUNDFONTS) + 1:
            # Combi has no safe default sound.  SELECT gives an explicit hint;
            # RIGHT is used here only to distinguish browse/enter from default apply.
            show_timed_modal_message("Use RIGHT", hold_sec=0.9, subtext="Open Combi List")
            return
        if state.submenu_index == len(SOUNDFONTS) + 2:
            if combi_locked():
                warn_combi_quick_blocked()
                return
            refresh_current_sound()
            if resume_after_apply:
                resume_selected_browser_file_after_sf_change()
            return
        apply_soundfont_with_default_preset(state.submenu_index)
        leave_submenu("SoundFont applied")
        if resume_after_apply:
            resume_selected_browser_file_after_sf_change()
        return
    if key == "preset":
        if block_sound_change_while_playing():
            return
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
        if combi_locked():
            warn_combi_quick_blocked()
            return
        if block_sound_change_while_playing():
            return
        if state.submenu_index != state.dac_index:
            restart_engine(state.sf_index, state.submenu_index)
        leave_submenu("DAC applied")
        return
    if key == "midi":
        if combi_locked():
            warn_combi_quick_blocked()
            return
        if block_sound_change_while_playing():
            return
        if state.midi_options:
            selected_mode, selected_name = state.midi_options[state.submenu_index]
            previous_mode = state.midi_mode

            if selected_mode.startswith("alsa_seq:"):
                # Direct ALSA SEQ input item selected from the MIDI Mode list.
                # No extra submenu: remember this concrete port/name and use
                # the normal ALSA SEQ engine path.
                selected_port = selected_mode.split(":", 1)[1]
                label = selected_name
                for port, full_label in list_alsa_seq_input_ports():
                    if port == selected_port:
                        label = full_label
                        break
                state.midi_mode = "alsa_midi"
                state.midi_selected_name = label
                state.preferred_seq_port = selected_port
                state.preferred_seq_name = label
                state.selected_alsa_input = selected_port
                state.selected_alsa_input_name = label
            else:
                state.midi_mode = selected_mode
                state.midi_selected_name = selected_name

            if previous_mode == "uno2_bridge_seq" and state.midi_mode != "uno2_bridge_seq":
                stop_bridge()
            refresh_midi_options(quiet=True)
            restart_engine(state.sf_index, state.dac_index)
        leave_submenu(f"MIDI mode: {state.midi_display_text}")
        return
    if key == "alsa_midi_input":
        options = list_alsa_seq_input_ports()
        if not options:
            state.preferred_seq_port = None
            state.preferred_seq_name = None
            state.selected_alsa_input = None
            state.selected_alsa_input_name = None
            leave_submenu("No ALSA MIDI input")
            return
        port, label = options[clamp_index(state.submenu_index, len(options))]
        previous_mode = state.midi_mode
        state.midi_mode = "alsa_midi"
        state.midi_selected_name = midi_mode_to_label("alsa_midi")
        state.preferred_seq_port = port
        state.preferred_seq_name = label
        state.selected_alsa_input = port
        state.selected_alsa_input_name = label
        if previous_mode == "uno2_bridge_seq":
            stop_bridge()
        refresh_midi_options(quiet=True)
        restart_engine(state.sf_index, state.dac_index)
        leave_submenu(f"ALSA MIDI: {shorten_text(label.replace(' MIDI 1', ''), 18)}")
        return
    if key == "extension":
        refresh_wifi_status()
        refresh_external_midi_state(quiet=True)
        if state.submenu_index == 0:
            enter_submenu("wifi", return_mode="submenu")
            mark_dirty("Wi-Fi")
            return
        if state.submenu_index == 1:
            enter_submenu("arp_speed", return_mode="submenu")
            mark_dirty("Arpeggio Speed")
            return
        if not external_midi_out_available():
            leave_submenu("Extension")
            return
        if state.submenu_index == 2:
            if len(list_external_midi_seq_ports()) > 1:
                enter_submenu("external_midi_device")
                mark_dirty("Select External MIDI")
            else:
                enter_submenu("external_midi_out")
                mark_dirty("External MIDI OUT")
            return
        if state.submenu_index == 3:
            enter_submenu("external_midi_pc")
            mark_dirty("External MIDI PC Send")
            return
        leave_submenu("Extension")
        return
    if key == "wifi":
        if state.submenu_index == 0:
            ok = set_wifi_enabled(not state.wifi_enabled)
            invalidate_full_display()
            mark_dirty("Wi-Fi On" if state.wifi_enabled else "Wi-Fi Off" if ok else "Wi-Fi toggle failed")
            return
        if state.submenu_index == 1:
            scan_wifi_ssids()
            invalidate_full_display()
            mark_dirty(f"Wi-Fi scan: {len(state.wifi_scan_results)} found")
            return
        idx = state.submenu_index - 2
        if 0 <= idx < len(state.wifi_scan_results):
            ssid = state.wifi_scan_results[idx]
            ok = connect_wifi_ssid(ssid)
            invalidate_full_display()
            mark_dirty(f"Wi-Fi: {shorten_text(ssid, 22)}" if ok else "Wi-Fi connect failed")
        else:
            mark_dirty("No configured network")
        return
    if key == "external_midi_device":
        ports = list_external_midi_seq_ports()
        if not ports:
            return_to_extension_submenu("External MIDI unavailable", index=0)
            return
        port, label = ports[clamp_index(state.submenu_index, len(ports))]
        state.preferred_external_midi_port = port
        state.preferred_external_midi_name = label
        refresh_external_midi_state(quiet=True)
        enter_submenu("external_midi_out")
        mark_dirty(f"External MIDI: {external_midi_display_name(label)}")
        return
    if key == "external_midi_pc":
        refresh_external_midi_state(quiet=True)
        if not external_midi_out_available():
            leave_submenu("External MIDI unavailable")
            return
        indices = gm_current_category_program_indices()
        if indices:
            state.external_midi_pc_index = indices[clamp_index(state.submenu_index, len(indices))]
        # SELECT confirms immediately. Cancel any delayed preview so the same
        # Program Change is not sent twice after returning to Extension.
        state.pending_external_midi_pc_index = None
        state.pending_external_midi_pc_due = 0.0
        ok = send_external_midi_program_change(state.external_midi_pc_index, state.external_midi_pc_channel)
        label = gm_program_label(state.external_midi_pc_index)
        return_to_extension_submenu(f"PC set: {shorten_text(label, 20)}" if ok else "External PC send failed", index=3)
        return
    if key == "external_midi_out":
        refresh_external_midi_state(quiet=True)
        enforce_external_midi_out_policy()
        if not external_midi_out_available():
            state.external_midi_out_mode = "off"
            leave_submenu("External MIDI OUT unavailable")
            return
        modes = EXTERNAL_MIDI_OUT_MODES
        mode, label = modes[clamp_index(state.submenu_index, len(modes))]
        previous_mode = state.external_midi_out_mode
        state.external_midi_out_mode = mode
        if mode == "mirror":
            connect_external_midi_mirror()
            # Initialize an external sound module to a predictable GM state
            # when External MIDI OUT is enabled. Send this only on the
            # Off -> Mirror transition so normal PC Send changes are not
            # overwritten while Mirror is already active.
            if previous_mode != "mirror":
                send_external_midi_program_change(0, state.external_midi_pc_channel)
        else:
            state.external_midi_connected = False
        return_to_extension_submenu(f"{external_midi_display_name()}: {label}", index=2)
        return
    if key == "user_preset_save":
        presets = load_user_presets()
        state.user_preset_entries = presets
        if state.submenu_index <= 0:
            save_current_user_preset_as_new()
        else:
            target_index = clamp_index(state.submenu_index - 1, len(presets))
            if not presets:
                save_current_user_preset_as_new()
                return
            state.user_preset_target_index = target_index
            state.submenu_key = "user_preset_overwrite"
            state.submenu_index = 0
            invalidate_full_display()
            mark_dirty("Overwrite?")
        return
    if key == "user_preset_overwrite":
        if state.submenu_index == 1:
            overwrite_user_preset(state.user_preset_target_index)
        else:
            state.submenu_key = "user_preset_save"
            state.submenu_index = state.user_preset_target_index + 1
            invalidate_full_display()
            mark_dirty("Overwrite canceled")
        return
    if key == "user_preset_manage":
        idx = state.user_preset_target_index
        if state.submenu_index == 0:
            start_user_preset_rename(idx)
            return
        if state.submenu_index == 1:
            move_user_preset_to_top(idx)
            return
        if state.submenu_index == 2:
            state.submenu_key = "user_preset_delete"
            state.submenu_index = 0
            invalidate_full_display()
            mark_dirty("Delete preset?")
            return
        state.submenu_key = "user_preset_load"
        state.submenu_index = clamp_index(idx, len(state.user_preset_entries or load_user_presets()))
        invalidate_full_display()
        mark_dirty("Manage canceled")
        return
    if key == "user_preset_delete":
        if state.submenu_index == 1:
            delete_user_preset(state.user_preset_target_index)
        else:
            state.submenu_key = "user_preset_manage"
            state.submenu_index = 0
            invalidate_full_display()
            mark_dirty("Delete canceled")
        return
    if key == "user_preset_rename":
        save_user_preset_rename()
        return
    if key == "user_preset_load":
        # SELECT is commit, not a second load. If the current highlighted row
        # already completed preview, simply leave the browser. If preview is
        # still pending or missing, apply the current row exactly once.
        presets = load_user_presets()
        if not presets:
            leave_submenu("No user presets")
            return
        idx = clamp_index(state.submenu_index, len(presets))
        item = presets[idx]
        label = shorten_text(str(item.get("name") or item.get("preset_name") or "User Preset"), 16)
        if state.previewed_user_preset_index == idx and state.pending_user_preset_preview_index is None:
            state.previewed_user_preset_index = None
            leave_submenu(f"User Preset: {label}")
            return
        state.pending_user_preset_preview_index = None
        state.pending_user_preset_preview_due = 0.0
        if apply_user_preset(item, leave_after=True, preview=False):
            state.previewed_user_preset_index = None
        return
    if key == "combi_load":
        combis = load_user_combis()
        if not combis:
            leave_submenu("No combis")
            return
        idx = clamp_index(state.submenu_index, len(combis))
        item = combis[idx]
        if state.previewed_combi_index == idx and state.combi_active:
            label = shorten_text(str(item.get("name") or "Combi"), 20)
            finish_combi_browse_session()
            enter_combi_detail_screen(f"Combi loaded: {label}")
        else:
            apply_combi(item, leave_after=True, preview=False)
        return
    leave_submenu("Not implemented yet")


def handle_main_select() -> None:
    label = MAIN_MENU[clamp_index(state.menu_index, len(MAIN_MENU))]
    if combi_locked() and label != "Sound":
        warn_combi_quick_blocked()
        return
    if label == "Sound":
        if block_sound_change_while_playing():
            return
        preload_sound_source_count_cache()
        enter_submenu("soundfont")
    elif label == "Media Player":
        if file_player_active() and state.player_path:
            enter_now_playing()
        else:
            enter_file_browser()
    elif label == "Controls":
        enter_sound_edit()
    elif label == "MIDI Mode":
        enter_submenu("midi")
    elif label == "DAC":
        enter_submenu("dac")
    elif label == "Extension":
        refresh_wifi_status()
        refresh_external_midi_state(quiet=True)
        enforce_external_midi_out_policy()
        enter_submenu("extension")
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
        "radio_view_mode": state.radio_view_mode,
        "radio_index": state.radio_index,
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
    if mode == "radio_browser":
        return "Radio/Fav" if snap.get("radio_view_mode") == "favorites" else "Radio"
    if mode == "player":
        if snap.get("player_path"):
            return f"Player/{shorten_text(Path(snap['player_path']).name, 10)}"
        return "Player"
    if mode == "sound_edit":
        return "Sound Edit"
    if mode == "submenu":
        key = snap.get("submenu_key") or "Menu"
        labels = {
            "soundfont": "Sound",
            "preset_category": "Category",
            "preset": "Preset",
            "dac": "DAC",
            "midi": "MIDI Mode",
            "extension": "Extension",
            "wifi": "Wi-Fi",
            "arp_speed": "Arpeggio Speed",
            "external_midi_device": "External MIDI Device",
            "external_midi_out": "External MIDI OUT",
            "external_midi_pc": "External MIDI PC",
            "user_preset_load": "User Preset",
            "combi_load": "Combi",
            "combi_detail": "Combi Loaded",
            "user_preset_save": "Save User Preset",
            "user_preset_overwrite": "Overwrite Preset",
            "user_preset_delete": "Delete Preset",
            "placeholder": "Extension",
            "controls": "Sound Edit",
        }
        return labels.get(key, str(key))
    return str(mode)


def combi_workflow_active() -> bool:
    return state.ui_mode == "submenu" and state.submenu_key in {"combi_load", "combi_detail"}


def combi_locked() -> bool:
    """Global performance lock: active Combi must keep sounding until an explicit Sound load replaces it."""
    return bool(state.combi_active)


def warn_combi_quick_blocked() -> None:
    show_timed_modal_message("Combi Mode Active", hold_sec=0.8, subtext="Load another sound")


def enter_quick_menu() -> None:
    if combi_locked():
        warn_combi_quick_blocked()
        return
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
    elif state.ui_mode == "radio_browser":
        state.radio_view_mode = snap.get("radio_view_mode", state.radio_view_mode)
        state.radio_entries = load_radio_entries_for_view(state.radio_view_mode)
        state.radio_index = clamp_index(snap.get("radio_index", state.radio_index), len(radio_display_labels()))

    invalidate_full_display()
    mark_dirty("Resume")


def enter_home() -> None:
    if combi_locked():
        warn_combi_quick_blocked()
        return_to_sound_submenu("Combi active")
        return
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
    if item == "MIDI Panic":
        midi_panic()
        return
    if item == "Now Playing":
        enter_now_playing()
        return
    if item == "Home":
        enter_home()
        return
    if item == "Sound":
        enter_submenu("soundfont")
        mark_dirty("Sound")
        return
    if item == "USB Eject":
        request_usb_eject()
        return
    if item == "Save User Preset":
        enter_user_preset_save_menu()
        return
    if item == "Arpeggio Speed":
        enter_submenu("arp_speed", return_mode="quick_menu")
        mark_dirty("Arpeggio Speed")
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
        elif action == "Restart Software":
            # Software restart should restart only this Python UI/runtime,
            # not ask systemd to restart the unit from inside the same unit.
            # Calling systemctl restart on the current service from this process
            # can leave the TFT latched on the wait screen or create confusing
            # stop/start timing.  os.execv() replaces the current Python process
            # in-place, so there is no helper process, no duplicated UI process,
            # and no chance to redraw the Power Menu between stop and start.
            state.ui_mode = "restart_wait"
            state.power_confirm_action = None
            state.power_confirm_index = 0
            invalidate_full_display()
            try:
                display.prev_image = None
                display.prev_snapshot = None
            except Exception:
                pass
            mark_dirty("Restarting software...")
            maybe_render(force=True)
            time.sleep(0.25)

            try:
                Path(RESTART_SOFTWARE_MARKER).write_text(str(time.time()), encoding="utf-8")
            except Exception:
                pass

            log("Restart Software requested; exec-replacing current Python process")

            # Clean up child processes before exec so the restarted instance
            # does not compete with old fluidsynth/player/monitor processes.
            try:
                set_play_led("OFF")
            except Exception:
                pass
            try:
                stop_midi_activity_monitor()
            except Exception:
                pass
            try:
                stop_player_only()
            except Exception:
                pass
            try:
                stop_bridge()
            except Exception:
                pass
            try:
                stop_fluidsynth()
            except Exception:
                pass
            try:
                with serial_lock:
                    if serial_handle is not None:
                        serial_handle.close()
            except Exception:
                pass

            python_exe = sys.executable or "/usr/bin/python3"
            argv = [python_exe] + sys.argv
            os.execv(python_exe, argv)
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



def internal_engine_running() -> bool:
    return fluid_proc is not None and fluid_proc.poll() is None


def resume_internal_sound_after_playback(event: str = "Stopped") -> None:
    """Return from file/radio playback to live keyboard use.

    Prefer a lightweight live MIDI route restore when the engine is still alive.
    In the current RAW-MIDI playback architecture, media/radio playback usually
    stops the engine to prevent the internal sound from playing over mpv or the
    MIDI-file player; in that case a recovery restart is still required.  Keeping
    this as one helper makes the distinction explicit and prevents unrelated
    Stop code from reapplying defaults or resetting volume/gain.
    """
    if internal_engine_running():
        reconnect_midi_to_fluidsynth(force_draw=False)
        mark_dirty(event)
        return

    # Recovery path only: the live engine was intentionally stopped for playback.
    show_modal_message("Restoring sound...", shorten_text(state.current_user_preset_name or state.current_preset_name, 24))
    restart_engine(state.sf_index, state.dac_index)
    restore_current_preset_after_engine_restart()
    clear_modal_message()
    mark_dirty(event)


def stop_player_keep_player(event: str = "Stopped") -> None:
    state.player_stop_requested = True
    stop_player_only()
    resume_internal_sound_after_playback(event)
    state.ui_mode = "player"
    invalidate_full_display()
    state.player_status = "Stopped"
    state.player_paused = False
    state.player_proc_kind = None
    set_play_led("OFF")


def return_player_to_browser(event: str = "Back to list") -> None:
    if state.player_return_mode == "radio_browser":
        state.ui_mode = "radio_browser"
        state.radio_entries = load_radio_entries_for_view(state.radio_view_mode)
        state.radio_index = clamp_index(state.radio_index, len(radio_display_labels()))
    else:
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

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_rename":
        if btn == "SEL_LP":
            pulse_button_activity(); cancel_user_preset_rename(); return
        if btn == "SEL":
            pulse_button_activity(); save_user_preset_rename(); return
        if btn == "LEFT":
            pulse_button_activity(); move_rename_cursor(-1); return
        if btn == "RIGHT":
            pulse_button_activity(); move_rename_cursor(+1); return
        if btn == "UP":
            pulse_button_activity(); insert_rename_space(); return
        if btn == "DOWN":
            pulse_button_activity(); delete_rename_char(); return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "sound_edit":
        # Sound Edit has its own input handler, so global long-press actions
        # that must remain available are handled first and explicitly.
        if btn == "RIGHT_LP":
            pulse_button_activity()
            if combi_locked():
                midi_panic()
            else:
                enter_quick_menu()
            return
        if btn == "DOWN_LP":
            pulse_button_activity(); refresh_current_sound(); return
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

    if btn == "RIGHT_LP" and combi_locked():
        pulse_button_activity()
        midi_panic()
        return

    if btn == "RIGHT_LP" and state.ui_mode != "power_menu":
        pulse_button_activity()
        enter_quick_menu()
        return

    if btn == "SEL_LP":
        pulse_button_activity()
        enter_power_menu()
        return

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_load" and btn == "LEFT_LP":
        pulse_button_activity()
        enter_user_preset_manage_menu()
        return

    # DOWN long is a soft sound refresh.  MIDI Panic remains available
    # from the top of the Quick Menu for true emergency stuck-note cases.
    if btn == "DOWN_LP" and state.ui_mode != "power_menu":
        pulse_button_activity()
        refresh_current_sound()
        return

    if state.ui_mode == "quick_menu":
        if btn == "UP":
            pulse_button_activity()
            if QUICK_MENU_ITEMS:
                state.quick_menu_index = (state.quick_menu_index - 1) % len(QUICK_MENU_ITEMS)
            mark_dirty(None)
            return
        if btn == "DOWN":
            pulse_button_activity()
            if QUICK_MENU_ITEMS:
                state.quick_menu_index = (state.quick_menu_index + 1) % len(QUICK_MENU_ITEMS)
            mark_dirty(None)
            return
        if btn == "LEFT":
            pulse_button_activity()
            restore_quick_snapshot()
            return
        if btn == "SEL":
            pulse_button_activity()
            quick_menu_select()
            return
        if btn == "UP_LP":
            pulse_button_activity()
            refresh_status_once()
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    # LEFT long is repurposed from USB eject to POT mode toggle.
    # USB eject remains available from the Quick Menu.
    if btn == "LEFT_LP":
        pulse_button_activity()
        toggle_pot_mode()
        return

    # UP long refreshes slow-changing status values on demand.
    # Normal UI events redraw only; they do not poll Load/Temp/MIDI/DAC/USB/Wi-Fi.
    if state.ui_mode == "radio_browser":
        labels_len = len(radio_display_labels())
        if btn == "UP":
            pulse_button_activity()
            if labels_len and state.radio_index > 0:
                state.radio_index -= 1
                mark_dirty(None)
            else:
                mark_dirty("First station")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if labels_len and state.radio_index < labels_len - 1:
                state.radio_index += 1
                mark_dirty(None)
            else:
                mark_dirty("Last station")
            return
        if btn in {"SEL", "SELECT"}:
            pulse_button_activity()
            if radio_index_is_favorites_entry():
                enter_radio_browser("favorites")
                return
            station = current_radio_station()
            if station:
                start_radio_station(station)
            else:
                mark_dirty("No station")
            return
        if btn == "RIGHT":
            pulse_button_activity()
            if radio_index_is_favorites_entry():
                mark_dirty("SEL=Favorites")
            else:
                toggle_current_radio_favorite()
            return
        if btn == "LEFT":
            pulse_button_activity()
            if state.radio_view_mode == "favorites":
                enter_radio_browser("all")
            else:
                enter_file_source()
            return
        mark_dirty(f"Radio BTN ignored: {btn}")
        return

    if state.ui_mode == "power_menu":
        if state.power_confirm_action in {"EXEC_HALT", "EXEC_REBOOT", "EXEC_RESTART_SOFTWARE"}:
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
            elif item == "Restart Software":
                # Restart only the Fluid Ardule systemd service, not the Raspberry Pi.
                execute_power_action("Restart Software")
            elif item == "Reboot":
                # Reboot uses the same single-step UX as Halt: show a short
                # feedback page, notify UNO-1, then call systemd reboot.
                execute_power_action("Reboot")
            elif item == "Halt":
                # Halt is entered from a long-press-only power menu, so skip
                # the extra Are-you-sure dialog and show a short feedback page.
                execute_power_action("Halt")
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
                if state.player_return_mode == "radio_browser":
                    station = find_radio_station_by_id(state.player_radio_station_id)
                    if station:
                        start_radio_station(station)
                    else:
                        mark_dirty("No radio station")
                elif state.player_path:
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
        if btn == "RIGHT":
            pulse_button_activity()
            if state.player_proc_kind == "radio" or state.player_return_mode == "radio_browser":
                toggle_radio_favorite_by_id(state.player_radio_station_id, state.player_path)
            else:
                mark_dirty("RIGHT unused")
            return
        if btn == "UP":
            if state.player_proc_kind == "radio" or state.player_return_mode == "radio_browser":
                play_adjacent_radio_station(-1)
            else:
                play_adjacent(-1)
            return
        if btn == "DOWN":
            if state.player_proc_kind == "radio" or state.player_return_mode == "radio_browser":
                play_adjacent_radio_station(+1)
            else:
                play_adjacent(+1)
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
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_overwrite":
        if btn == "LEFT":
            pulse_button_activity()
            state.submenu_key = "user_preset_save"
            state.submenu_index = state.user_preset_target_index + 1
            invalidate_full_display()
            mark_dirty("Overwrite canceled")
            return

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_manage":
        if btn == "LEFT":
            pulse_button_activity()
            state.submenu_key = "user_preset_load"
            state.submenu_index = state.user_preset_target_index
            invalidate_full_display()
            mark_dirty("Manage canceled")
            return

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_delete":
        if btn == "LEFT":
            pulse_button_activity()
            state.submenu_key = "user_preset_manage"
            state.submenu_index = 0
            invalidate_full_display()
            mark_dirty("Delete canceled")
            return

    if state.ui_mode == "submenu" and state.submenu_key == "wifi":
        if btn == "LEFT":
            pulse_button_activity()
            return_to_extension_submenu("Extension", index=0)
            return

    if state.ui_mode == "submenu" and state.submenu_key == "external_midi_device":
        if btn == "LEFT":
            pulse_button_activity()
            return_to_extension_submenu("Extension", index=2)
            return

    if state.ui_mode == "submenu" and state.submenu_key == "external_midi_out":
        if btn == "LEFT":
            pulse_button_activity()
            return_to_extension_submenu("Extension", index=2)
            return

    if state.ui_mode == "submenu" and state.submenu_key == "arp_speed":
        if btn == "UP":
            pulse_button_activity(); adjust_arp_speed(+ARP_BPM_STEP); return
        if btn == "DOWN":
            pulse_button_activity(); adjust_arp_speed(-ARP_BPM_STEP); return
        if btn == "RIGHT":
            pulse_button_activity(); adjust_arp_speed(+ARP_BPM_STEP); return
        if btn == "SEL":
            pulse_button_activity(); apply_yoshimi_arpeggio_speed(announce=True); return
        if btn == "LEFT":
            pulse_button_activity()
            if state.submenu_return_mode == "quick_menu":
                state.ui_mode = "quick_menu"
                state.submenu_key = None
                state.submenu_index = 0
                state.submenu_return_mode = None
                invalidate_full_display()
                mark_dirty("Quick Menu")
            else:
                return_to_extension_submenu("Extension", index=1)
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "external_midi_pc":
        if btn == "UP":
            pulse_button_activity()
            move_external_midi_pc_selection(-1)
            return
        if btn == "DOWN":
            pulse_button_activity()
            move_external_midi_pc_selection(+1)
            return
        if btn == "RIGHT":
            pulse_button_activity()
            next_external_midi_pc_category()
            return
        if btn == "SEL":
            pulse_button_activity()
            apply_current_submenu_selection()
            return
        if btn == "LEFT":
            pulse_button_activity()
            state.pending_external_midi_pc_index = None
            state.pending_external_midi_pc_due = 0.0
            return_to_extension_submenu("External PC canceled", index=2)
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_load":
        options = get_submenu_options()
        if btn == "UP":
            pulse_button_activity()
            if state.submenu_index > 0:
                preview_user_preset_at_index(state.submenu_index - 1)
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.submenu_index < len(options) - 1:
                preview_user_preset_at_index(state.submenu_index + 1)
            else:
                mark_dirty("Last item")
            return
        if btn == "SEL":
            pulse_button_activity()
            apply_current_submenu_selection()
            return
        if btn == "LEFT":
            pulse_button_activity()
            leave_submenu("Canceled")
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "soundfont":
        options = get_submenu_options()
        if btn == "UP":
            pulse_button_activity()
            if state.submenu_index > 0:
                state.submenu_index -= 1
                if state.submenu_index < len(SOUNDFONTS):
                    total, drums = soundfont_preset_counts_cached(state.submenu_index)
                    sf_name = source_name_for_index(state.submenu_index)
                    mark_dirty(f"{sf_name}: {total} presets, {drums} drums" if total else sf_name)
                elif state.submenu_index == len(SOUNDFONTS):
                    count = user_preset_count_cached()
                    mark_dirty(f"User Preset: {count} saved")
                elif state.submenu_index == len(SOUNDFONTS) + 1:
                    count = user_combi_count_cached()
                    mark_dirty(f"Combi: {count} saved")
                else:
                    mark_dirty("Refresh current sound")
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.submenu_index < len(options) - 1:
                state.submenu_index += 1
                if state.submenu_index < len(SOUNDFONTS):
                    total, drums = soundfont_preset_counts_cached(state.submenu_index)
                    sf_name = source_name_for_index(state.submenu_index)
                    mark_dirty(f"{sf_name}: {total} presets, {drums} drums" if total else sf_name)
                elif state.submenu_index == len(SOUNDFONTS):
                    count = user_preset_count_cached()
                    mark_dirty(f"User Preset: {count} saved")
                elif state.submenu_index == len(SOUNDFONTS) + 1:
                    count = user_combi_count_cached()
                    mark_dirty(f"Combi: {count} saved")
                else:
                    mark_dirty("Refresh current sound")
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
            if state.submenu_index == len(SOUNDFONTS):
                enter_user_preset_load_menu(return_mode=state.submenu_return_mode or "main")
            elif state.submenu_index == len(SOUNDFONTS) + 1:
                enter_combi_load_menu(return_mode=state.submenu_return_mode or "main")
            elif state.submenu_index == len(SOUNDFONTS) + 2:
                mark_dirty("SEL=Reload")
            else:
                enter_preset_submenu(state.submenu_index)
            return
        if btn == "LEFT":
            pulse_button_activity()
            leave_submenu("Canceled")
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
        if btn == "SEL":
            pulse_button_activity()
            enter_preset_list_from_category(state.submenu_index)
            return
        if btn == "RIGHT":
            pulse_button_activity()
            mark_dirty("SEL=Enter")
            return
        if btn == "LEFT":
            pulse_button_activity()
            return_to_soundfont_submenu()
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "combi_load":
        options = get_submenu_options()
        if btn == "UP":
            pulse_button_activity()
            if state.submenu_index > 0:
                state.submenu_index -= 1
                if state.previewed_combi_index != state.submenu_index:
                    state.previewed_combi_index = None
                mark_dirty("Combi browse")
            else:
                mark_dirty("First item")
            return
        if btn == "DOWN":
            pulse_button_activity()
            if state.submenu_index < len(options) - 1:
                state.submenu_index += 1
                if state.previewed_combi_index != state.submenu_index:
                    state.previewed_combi_index = None
                mark_dirty("Combi browse")
            else:
                mark_dirty("Last item")
            return
        if btn == "SEL":
            pulse_button_activity()
            if state.combi_entries:
                idx = clamp_index(state.submenu_index, len(state.combi_entries))
                item = state.combi_entries[idx]
                if state.previewed_combi_index == idx and state.combi_active:
                    # SELECT commits the already playable preview.  Do not
                    # rebuild/reapply the same Combi after RIGHT already loaded it.
                    label = shorten_text(str(item.get("name") or "Combi"), 20)
                    finish_combi_browse_session()
                    enter_combi_detail_screen(f"Combi loaded: {label}")
                else:
                    apply_combi(item, leave_after=True, preview=False)
            else:
                mark_dirty("No combis")
            return
        if btn == "RIGHT":
            pulse_button_activity()
            if state.combi_entries:
                item = state.combi_entries[clamp_index(state.submenu_index, len(state.combi_entries))]
                apply_combi(item, leave_after=False, preview=True)
            else:
                mark_dirty("No combis")
            return
        if btn == "LEFT":
            pulse_button_activity()
            if state.combi_active:
                # Leaving the Combi browser is a UI exit only.  Keep the active
                # Combi/router/MIDI backend exactly as-is; another Sound load will
                # explicitly clear state.combi_active via apply_preset().
                finish_combi_browse_session()
                return_to_sound_submenu("Combi still active")
            else:
                restore_combi_browse_snapshot()
                finish_combi_browse_session()
                return_to_sound_submenu("Combi canceled")
            return
        mark_dirty(f"BTN ignored: {btn}")
        return

    if state.ui_mode == "submenu" and state.submenu_key == "combi_detail":
        if btn == "LEFT":
            pulse_button_activity()
            return_to_sound_submenu("Combi still active")
            return
        if btn == "SEL":
            pulse_button_activity()
            enter_combi_load_menu(return_mode="sound")
            return
        if btn == "RIGHT":
            pulse_button_activity()
            mark_dirty("SEL=Combi")
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
            # 260628b: Leaving a preset list should only move one UI level up.
            # Keep the last previewed sound active instead of restoring the
            # pre-browse sound.  This is especially important for Yoshimi,
            # where returning to the category list should not suddenly switch
            # back to the previous FluidSynth piano.
            commit_current_preview()
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
            if combi_locked():
                warn_combi_quick_blocked()
                return_to_sound_submenu("Combi active")
            else:
                mark_dirty("Main screen")
        return

    if btn == "RIGHT":
        pulse_button_activity()
        mark_dirty("RIGHT unused")
        return

    if btn == "UP_LP":
        pulse_button_activity()
        refresh_status_once()
        return

    mark_dirty(f"BTN ignored: {btn}")


# =========================================================
# Serial and hotplug
# =========================================================

def open_serial() -> serial.Serial:
    port_path = Path(SERIAL_PORT)
    if not port_path.exists():
        raise FileNotFoundError(f"Serial port not found: {SERIAL_PORT}")

    # Keep HUPCL disabled so closing/reopening the port is less likely to
    # toggle modem-control lines and reset UNO-1 during service restart.
    # This is best-effort; Arduino Uno auto-reset is partly hardware-driven.
    try:
        subprocess.run(["stty", "-F", SERIAL_PORT, "-hupcl"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:
        pass

    # Open the port manually instead of using serial.Serial(...) directly.
    # This lets us set DTR/RTS low before open, reducing UNO auto-reset risk.
    ser = serial.Serial()
    ser.port = SERIAL_PORT
    ser.baudrate = SERIAL_BAUD
    ser.timeout = SERIAL_TIMEOUT
    ser.write_timeout = 0.05
    ser.dtr = False
    ser.rts = False
    ser.open()

    try:
        ser.setDTR(False)
        ser.setRTS(False)
    except Exception:
        pass

    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except Exception:
        pass
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
                # After opening the serial port, wait before sending anything to UNO-1.
                # If the port open still triggered an Arduino auto-reset, this holdoff
                # lets UNO-1 finish booting and prevents early HELLO/HB/UI messages
                # from racing with LCD initialization.
                state.serial_input_ignore_until = time.time() + SERIAL_INPUT_IGNORE_AFTER_OPEN_SEC
                time.sleep(SERIAL_OUTPUT_HOLDOFF_AFTER_OPEN_SEC)
                try:
                    # Do not reset the input buffer here. UNO-1 may have already
                    # reported the physical POT position during its boot window;
                    # clearing RX at this point makes startup fall back to the
                    # saved volume until the knob is moved. The first reset in
                    # open_serial() is enough to discard stale data from the
                    # previous session.
                    ser.reset_output_buffer()
                except Exception:
                    pass

                with serial_lock:
                    serial_handle = ser
                request_startup_pot_snapshot_window()
                send_serial_line("HELLO")
                time.sleep(0.05)
                send_serial_line("HB")
                time.sleep(0.02)
                send_serial_line("PLAY:OFF")
                send_ui_status("READY", force=True)
                sync_encoder_accel_profile(force=True, reason="serial_connected")
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


def periodic_device_poll(force: bool = False) -> None:
    now = time.time()
    if (not force) and now - state.last_device_poll_time < DEVICE_POLL_INTERVAL_SEC:
        return
    state.last_device_poll_time = now
    dac_changed = refresh_dac_options(quiet=True)
    external_changed = refresh_external_midi_state(quiet=True)
    enforce_external_midi_out_policy()
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
        if state.midi_connected and state.external_midi_out_mode == "mirror":
            connect_external_midi_mirror(find_bridge_port())
    elif state.midi_mode == "external_midi_seq":
        prev_ext_connected = state.midi_connected
        prev_ext_port = state.midi_src_port
        selected_port, selected_name = choose_external_midi_seq_input()
        state.midi_src_name = selected_name or 'No External MIDI'
        state.midi_src_port = selected_port or '-'
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()
        if not selected_port:
            if prev_ext_connected:
                mark_dirty("External MIDI disconnected")
            return
        if fluid_proc is not None and fluid_proc.poll() is not None:
            pass
        elif fluid_proc is not None and fluid_proc.poll() is None and (not prev_ext_connected or prev_ext_port != selected_port):
            connect_external_midi_to_fluidsynth()
            refresh_midi_display_text()
            mark_dirty(f"MIDI {state.midi_display_text}")
            return
        if state.external_midi_out_mode == "mirror":
            connect_external_midi_mirror(selected_port)
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

        # If Combi is active, the Python router owns MIDI delivery. Keep the
        # direct keyboard->FluidSynth route disconnected so split/key-range
        # filtering is not bypassed.
        if state.combi_active:
            _disconnect_direct_midi_route()
            refresh_midi_display_text()
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
    elif external_changed:
        mark_dirty("External MIDI detected" if state.external_midi_present else "External MIDI removed")
    elif old_connected != state.midi_connected:
        mark_dirty(f"MIDI {state.midi_display_text}" if state.midi_connected else "Engine stopped")





def periodic_midi_status_poll(force: bool = False) -> bool:
    """Poll only live MIDI input status as the single background UI exception.

    Most status values (Load/Temp/DAC/USB/Wi-Fi) are refreshed only by user
    action, especially UP long-press. MIDI input availability is performance
    critical, so keyboard attach/detach is allowed to trigger one immediate
    redraw without reintroducing broad background status polling.
    """
    now = time.time()
    if (not force) and now - state.last_device_poll_time < DEVICE_POLL_INTERVAL_SEC:
        return False
    state.last_device_poll_time = now

    old_display = state.midi_display_text
    old_connected = state.midi_connected
    old_src_port = state.midi_src_port
    old_src_name = state.midi_src_name
    old_selected_alsa = state.selected_alsa_input
    old_external_present = state.external_midi_present

    if state.midi_mode == "usb_direct_raw":
        prev_raw_port = state.midi_src_port
        selected_port, selected_name = choose_raw_midi_input()
        state.midi_src_name = selected_name or "No raw MIDI"
        state.midi_src_port = selected_port or "-"
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()

        # If a RAW keyboard appears while FluidSynth owns the engine, rebuild so
        # alsa_raw can bind to the newly available device. This preserves the
        # previous behavior without polling unrelated device/status data.
        if fluid_proc is not None and fluid_proc.poll() is None and selected_port and prev_raw_port in {"-", "", None}:
            restart_engine(state.sf_index, state.dac_index)
            restore_current_preset_after_engine_restart()
            selected_port, selected_name = choose_raw_midi_input()
            state.midi_src_name = selected_name or "No raw MIDI"
            state.midi_src_port = selected_port or "-"
            state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
            refresh_midi_display_text()

    elif state.midi_mode == "uno2_bridge_seq":
        state.bridge_running = state.bridge_proc is not None and state.bridge_proc.poll() is None
        state.midi_connected = state.bridge_running and (fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()

    elif state.midi_mode == "external_midi_seq":
        refresh_external_midi_state(quiet=True)
        selected_port, selected_name = choose_external_midi_seq_input()
        state.midi_src_name = selected_name or "No External MIDI"
        state.midi_src_port = selected_port or "-"
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()
        if selected_port and (old_src_port != selected_port or not old_connected):
            connect_external_midi_to_fluidsynth()

    else:
        selected_port, selected_name = choose_alsa_seq_input()
        state.selected_alsa_input = selected_port
        state.selected_alsa_input_name = selected_name
        state.midi_src_name = selected_name or "alsa sequencer"
        state.midi_src_port = selected_port or "-"
        state.midi_connected = bool(selected_port and fluid_proc is not None and fluid_proc.poll() is None)
        refresh_midi_display_text()

        if selected_port and (old_selected_alsa != selected_port or not old_connected):
            if state.combi_active:
                _disconnect_direct_midi_route()
            else:
                connect_selected_alsa_to_fluidsynth()

    changed = (
        state.midi_display_text != old_display
        or state.midi_connected != old_connected
        or state.midi_src_port != old_src_port
        or state.midi_src_name != old_src_name
        or state.selected_alsa_input != old_selected_alsa
        or state.external_midi_present != old_external_present
    )
    if changed:
        mark_dirty(f"MIDI {state.midi_display_text}" if state.midi_connected else "MIDI disconnected")
    return changed


def periodic_usb_poll(force: bool = False) -> None:
    now = time.time()
    if (not force) and now - state.last_usb_poll_time < USB_STATUS_POLL_INTERVAL_SEC:
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
    send_ui_status("BUSY", force=True)
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
        send_ui_status("READY", force=True)
        return

    invalidate_full_display()
    if still_mounted:
        mark_dirty("USB busy / unmount failed")
    else:
        mark_dirty(f"USB eject failed: {shorten_text(out, 20)}")
    send_ui_status("READY", force=True)


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
        # During serial boot-settling, ignore controls that can trigger UI actions,
        # but still accept the first POT value so startup volume follows the
        # physical knob instead of staying at the old max-volume fallback.
        if msg_type in ("POT", "A2"):
            handle_pot_value(value)
        return

    if msg_type == "BTN":
        handle_button_event(value)
        ack_uno_event("BTN")
        return
    if msg_type in ("POT", "A2"):
        handle_pot_value(value)
        return
    if msg_type == "ENC":
        handle_encoder_value(value)
        ack_uno_event("ENC")
        return
    if msg_type == "A0":
        return
    if msg_type == "ACCEL":
        try:
            p = max(0, min(3, int(value)))
            state.encoder_accel_profile = p
            state.encoder_accel_pending_profile = p
            if ACCEL_PROFILE_TFT_FEEDBACK:
                label = ENCODER_ACCEL_OPTIONS.get(p, f"P{p}")
                show_footer_message(f"Accel: {label}", ACCEL_FOOTER_HOLD_SEC)
            elif ACCEL_PROFILE_TRACE:
                log(f"ACCEL_REPORT P{p}")
        except Exception:
            if ACCEL_PROFILE_TFT_FEEDBACK:
                show_footer_message(f"Accel: P{value}", ACCEL_FOOTER_HOLD_SEC)
        return
    mark_dirty(f"Unknown line: {line}")





def _soundfont_nav_status(index: int) -> str:
    """Return the footer/status text for the highlighted Sound Source row."""
    if index < len(SOUNDFONTS):
        total, drums = soundfont_preset_counts_cached(index)
        sf_name = source_name_for_index(index)
        return f"{sf_name}: {total} presets, {drums} drums" if total else sf_name
    if index == len(SOUNDFONTS):
        return f"User Preset: {user_preset_count_cached()} saved"
    if index == len(SOUNDFONTS) + 1:
        return f"Combi: {user_combi_count_cached()} saved"
    return "Refresh current sound"


def _move_index_by_delta(current: int, delta: int, length: int) -> tuple[int, bool]:
    """Clamp an index movement and report whether it actually moved."""
    if length <= 0:
        return 0, False
    new_index = max(0, min(length - 1, int(current) + int(delta)))
    return new_index, (new_index != int(current))



def encoder_context_label() -> str:
    """Return a compact stable label for the current encoder context."""
    if state.ui_mode == "submenu" and state.submenu_key:
        return f"submenu:{state.submenu_key}"
    if state.ui_mode == "radio_browser":
        return f"radio_browser:{state.radio_view_mode}"
    if state.ui_mode == "power_menu" and state.power_confirm_action:
        return f"power_menu:{state.power_confirm_action}"
    return str(state.ui_mode)


def encoder_position_snapshot() -> str:
    """Return the currently controlled index/value for encoder trace logs.

    The goal is not to describe the whole UI state, but to show the exact
    object that ENC:+/-N is expected to move: menu index, list index, current
    CC value, rename cursor/character, etc.  This makes it easy to compare
    hand-felt detents with the resulting logical movement.
    """
    try:
        if state.ui_mode == "main":
            label = MAIN_MENU[state.menu_index] if 0 <= state.menu_index < len(MAIN_MENU) else "-"
            return f"menu_index={state.menu_index}({label})"

        if state.ui_mode == "quick_menu":
            label = QUICK_MENU_ITEMS[state.quick_menu_index] if 0 <= state.quick_menu_index < len(QUICK_MENU_ITEMS) else "-"
            return f"quick_index={state.quick_menu_index}({label})"

        if state.ui_mode == "sound_edit":
            if SOUND_EDIT_PARAMS:
                idx = clamp_index(state.sound_edit_index, len(SOUND_EDIT_PARAMS))
                item = SOUND_EDIT_PARAMS[idx]
                cc = int(item["cc"])
                value = state.sound_edit_values.get(cc, int(item.get("default", 0)))
                return f"sound_edit_index={idx}({item['label']} CC{cc}) value={value}"
            return "sound_edit_index=0(empty)"

        if state.ui_mode == "submenu":
            key = state.submenu_key or "-"
            if key == "preset":
                label = state.preset_entries[state.submenu_index].get("name", "-") if 0 <= state.submenu_index < len(state.preset_entries) else "-"
                return f"submenu_index={state.submenu_index} preset=({shorten_text(str(label), 24)})"
            if key == "preset_category":
                label = state.category_entries[state.submenu_index] if 0 <= state.submenu_index < len(state.category_entries) else "-"
                return f"submenu_index={state.submenu_index} category=({shorten_text(str(label), 24)})"
            if key == "user_preset_load":
                label = state.user_preset_entries[state.submenu_index].get("name", "-") if 0 <= state.submenu_index < len(state.user_preset_entries) else "-"
                return f"submenu_index={state.submenu_index} user_preset=({shorten_text(str(label), 24)})"
            if key == "combi_load":
                label = state.combi_entries[state.submenu_index].get("name", "-") if 0 <= state.submenu_index < len(state.combi_entries) else "-"
                return f"submenu_index={state.submenu_index} combi=({shorten_text(str(label), 24)})"
            if key == "external_midi_pc":
                return f"external_pc_index={state.external_midi_pc_index}({gm_program_label(state.external_midi_pc_index)})"
            if key == "arp_speed":
                return f"arp_bpm={state.arp_bpm} delay={arp_bpm_to_echo_delay(state.arp_bpm)}"
            if key == "user_preset_rename":
                cursor = state.user_preset_rename_cursor
                text = state.user_preset_rename_text or ""
                ch = text[cursor] if 0 <= cursor < len(text) else ""
                return f"rename_cursor={cursor} char=({ch}) text=({shorten_text(text, 20)})"
            return f"submenu_index={state.submenu_index} key={key}"

        if state.ui_mode == "file_source":
            entries = get_file_source_entries()
            label = entries[state.browser_index].get("display", "-") if 0 <= state.browser_index < len(entries) else "-"
            return f"browser_index={state.browser_index} source=({label})"

        if state.ui_mode == "file_browser":
            label = state.browser_entries[state.browser_index].get("name", "-") if 0 <= state.browser_index < len(state.browser_entries) else "-"
            return f"browser_index={state.browser_index} file=({shorten_text(str(label), 24)})"

        if state.ui_mode == "radio_browser":
            labels = radio_display_labels()
            label = labels[state.radio_index] if 0 <= state.radio_index < len(labels) else "-"
            return f"radio_index={state.radio_index} station=({shorten_text(str(label), 24)})"

        if state.ui_mode == "player":
            return f"player_status={state.player_status} path=({shorten_text(str(state.player_path or '-'), 24)})"

        if state.ui_mode == "power_menu":
            if state.power_confirm_action:
                label = POWER_CONFIRM_ITEMS[state.power_confirm_index] if 0 <= state.power_confirm_index < len(POWER_CONFIRM_ITEMS) else "-"
                return f"power_confirm_index={state.power_confirm_index}({label}) action={state.power_confirm_action}"
            label = POWER_MENU_ITEMS[state.power_menu_index] if 0 <= state.power_menu_index < len(POWER_MENU_ITEMS) else "-"
            return f"power_menu_index={state.power_menu_index}({label})"

        return f"ui_mode={state.ui_mode} submenu_key={state.submenu_key}"
    except Exception as exc:
        return f"snapshot_error={exc}"


def encoder_trace(step: int, before: str, after: str | None = None, note: str = "") -> None:
    """Print one concise encoder diagnostic line when ENCODER_TRACE is enabled."""
    if not ENCODER_TRACE:
        return
    context = encoder_context_label()
    profile = getattr(state, "encoder_accel_profile", ENCODER_ACCEL_DEFAULT_PROFILE)
    if after is None:
        after = encoder_position_snapshot()
    suffix = f" note={note}" if note else ""
    log(f"ENC_TRACE step={int(step):+d} profile=P{profile} ui={context} before=[{before}] after=[{after}]{suffix}")

def handle_encoder_navigation_step(step: int) -> bool:
    """Apply ENC:+/-N as an N-row navigation move where it is safe.

    This intentionally updates the target selection once, rather than calling
    handle_button_event("UP"/"DOWN") repeatedly.  It keeps one LED pulse and
    one render while preserving the old edge messages and special preview paths.
    Returns True when the encoder event was consumed.
    """
    if step == 0:
        return True

    # While a file or radio stream is actually playing, keep the old safety rule:
    # do not let accidental encoder motion jump tracks or stations.
    if state.ui_mode == "player" and state.player_status == "Playing":
        mark_dirty("Encoder ignored while playing")
        return True

    # Player screen when stopped has side-effectful UP/DOWN actions; keep that
    # path conservative and let the existing button handler decide one action.
    if state.ui_mode == "player":
        handle_button_event("DOWN" if step > 0 else "UP")
        return True

    pulse_button_activity()
    direction = "DOWN" if step > 0 else "UP"
    edge_msg = "Last item" if step > 0 else "First item"

    if state.ui_mode == "quick_menu":
        if QUICK_MENU_ITEMS:
            state.quick_menu_index = (state.quick_menu_index + step) % len(QUICK_MENU_ITEMS)
        mark_dirty(None)
        return True

    if state.ui_mode == "radio_browser":
        labels_len = len(radio_display_labels())
        new_index, moved = _move_index_by_delta(state.radio_index, step, labels_len)
        state.radio_index = new_index
        mark_dirty(None if moved else ("Last station" if step > 0 else "First station"))
        return True

    if state.ui_mode == "power_menu":
        if state.power_confirm_action in {"EXEC_HALT", "EXEC_REBOOT", "EXEC_RESTART_SOFTWARE"}:
            mark_dirty("Power action running")
            return True
        if state.power_confirm_action:
            new_index, moved = _move_index_by_delta(state.power_confirm_index, step, len(POWER_CONFIRM_ITEMS))
            state.power_confirm_index = new_index
            mark_dirty(None if moved else edge_msg)
            return True
        new_index, moved = _move_index_by_delta(state.power_menu_index, step, len(POWER_MENU_ITEMS))
        state.power_menu_index = new_index
        mark_dirty(None if moved else edge_msg)
        return True

    if state.ui_mode == "file_source":
        entries = get_file_source_entries()
        new_index, moved = _move_index_by_delta(state.browser_index, step, len(entries))
        state.browser_index = new_index
        mark_dirty(None if moved else edge_msg)
        return True

    if state.ui_mode == "file_browser":
        new_index, moved = _move_index_by_delta(state.browser_index, step, len(state.browser_entries))
        state.browser_index = new_index
        mark_dirty(None if moved else edge_msg)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "arp_speed":
        adjust_arp_speed(step * ARP_BPM_STEP)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "external_midi_pc":
        move_external_midi_pc_selection(step)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "soundfont":
        options = get_submenu_options()
        new_index, moved = _move_index_by_delta(state.submenu_index, step, len(options))
        state.submenu_index = new_index
        mark_dirty(_soundfont_nav_status(new_index) if moved else edge_msg)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "preset_category":
        options = get_submenu_options()
        new_index, moved = _move_index_by_delta(state.submenu_index, step, len(options))
        state.submenu_index = new_index
        state.category_index = new_index
        if moved and state.category_entries:
            mark_dirty(state.category_entries[state.category_index])
        else:
            mark_dirty("Category" if moved else edge_msg)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "combi_load":
        options = get_submenu_options()
        new_index, moved = _move_index_by_delta(state.submenu_index, step, len(options))
        state.submenu_index = new_index
        mark_dirty("Combi browse" if moved else edge_msg)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_load":
        options = get_submenu_options()
        new_index, moved = _move_index_by_delta(state.submenu_index, step, len(options))
        if moved:
            preview_user_preset_at_index(new_index)
        else:
            mark_dirty(edge_msg)
        return True

    if state.ui_mode == "submenu" and state.submenu_key == "preset":
        options = get_submenu_options()
        new_index, moved = _move_index_by_delta(state.submenu_index, step, len(options))
        if moved:
            preview_preset_at_index(new_index)
        else:
            mark_dirty(edge_msg)
        return True

    if state.ui_mode == "main":
        new_index, moved = _move_index_by_delta(state.menu_index, step, len(MAIN_MENU))
        state.menu_index = new_index
        mark_dirty(None if moved else edge_msg)
        return True

    # Generic submenu-like screens without special preview side effects.
    if state.ui_mode == "submenu":
        options = get_submenu_options()
        new_index, moved = _move_index_by_delta(state.submenu_index, step, len(options))
        state.submenu_index = new_index
        mark_dirty(None if moved else edge_msg)
        return True

    # Unknown context: preserve previous direction-only behavior.
    handle_button_event(direction)
    return True


def handle_encoder_value(value: str) -> None:
    global last_enc_time

    now = time.time()
    try:
        step = int(value)
    except ValueError:
        return
    if step == 0:
        return

    trace_before = encoder_position_snapshot()

    if state.ui_mode == "submenu" and state.submenu_key == "user_preset_rename":
        # Character editing remains deliberately fine-grained.
        rename_char_delta(1 if step > 0 else -1)
        last_enc_time = now
        encoder_trace(step, trace_before, note="rename fine-step")
        return

    # In Sound Edit, do not apply the global 20 ms navigation debounce.
    # UNO-1 already sends accelerated ENC steps, so use the raw signed value.
    if state.ui_mode == "sound_edit":
        adjust_sound_edit_value(step)
        last_enc_time = now
        encoder_trace(step, trace_before, note="sound_edit value")
        return

    # Do not time-debounce navigation ENC lines here.
    # UNO-1/ISR already debounces and coalesces encoder motion into ENC:+/-N.
    # Dropping fast consecutive serial lines makes menu navigation feel slower
    # than Sound Edit/Controller, which intentionally consumes every raw ENC step.
    last_enc_time = now

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
        encoder_trace(step, trace_before, trace_before, note=f"ignored reversal_guard dt={now - state.last_nav_enc_time:.3f}s")
        return

    state.last_nav_enc_dir = nav_dir
    state.last_nav_enc_time = now
    handle_encoder_navigation_step(step)
    encoder_trace(step, trace_before, note="navigation")


def performance_render_limited() -> bool:
    """Background TFT redraws are disabled during normal runtime.

    Fluid Ardule behaves more like a hardware instrument than a desktop UI:
    the screen should update immediately for user/UNO events, but it should not
    continuously redraw itself in the background.  This keeps Python/TFT load
    low and improves Yoshimi/Combi real-time audio stability on Raspberry Pi 3B.
    """
    return True


def maybe_render(force: bool = False) -> None:
    now = time.time()
    expired_transient = False

    if state.transient_footer_text and now >= state.transient_footer_until:
        state.transient_footer_text = ""
        state.dirty = True
        expired_transient = True

    if state.modal_until and now >= state.modal_until:
        clear_modal_message()
        expired_transient = True

    if state.player_notice_text and now >= state.player_notice_until:
        state.player_notice_text = ""
        state.dirty = True
        expired_transient = True

    if not state.dirty:
        return

    if force:
        display.render()
        return

    # No periodic/background redraws.  The only non-user-triggered redraw left
    # is a one-shot cleanup for short-lived popup/notice messages, so they do
    # not remain stuck on the TFT.
    if expired_transient:
        display.render()
        return

    return


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

    # If the previous instance requested Restart Software, ignore possible
    # stale button/encoder events from the serial link during the fresh start.
    try:
        if Path(RESTART_SOFTWARE_MARKER).exists():
            Path(RESTART_SOFTWARE_MARKER).unlink(missing_ok=True)
            state.serial_input_ignore_until = time.time() + 3.0
    except Exception:
        pass

    # Keep full-screen redraw recovery active only during the vulnerable
    # boot-settling window. This expires quickly and does not change normal
    # runtime render behavior.
    state.force_full_redraw_until = time.time() + BOOT_FULL_REDRAW_SEC
    state.last_forced_full_redraw_time = 0.0

    state.browser_root = find_file_root()
    state.browser_path = state.browser_root
    Path(USB_MOUNT_POINT).mkdir(parents=True, exist_ok=True)
    state.usb_mounted = is_mountpoint_active(USB_MOUNT_POINT)

    # Startup volume policy 260627c:
    # Use a fixed safe line-level value.  Do not restore the last saved value,
    # because the physical POT may have been moved while Fluid Ardule was off.
    # The POT controls volume only after soft takeover captures the current
    # logical volume, preventing sudden jumps on the first knob movement.
    startup_volume = DEFAULT_STARTUP_VOLUME_PERCENT
    state.volume_percent = startup_volume
    state.initial_pot_volume_applied = True
    state.pot_volume_captured = False
    state.pot_startup_request_until = 0.0
    set_output_volume(startup_volume, announce=False)

    refresh_dac_options(quiet=True)
    refresh_external_midi_state(quiet=True)
    enforce_external_midi_out_policy()
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

    refresh_status_once("Ready")
    preload_sound_source_count_cache()
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
                periodic_serial_ui_status()
                sync_encoder_accel_profile(reason="event")
                maybe_render(force=True)
                continue

            # Event-driven UI: keep slow/heavy status/device polling on UP long.
            # Exceptions: live MIDI input and USB mount status are performance-critical
            # for plug-and-play feel, and trigger redraw only when their state changes.
            periodic_bridge_watchdog()
            midi_status_changed = periodic_midi_status_poll()
            periodic_usb_poll()
            periodic_serial_heartbeat()
            periodic_serial_ui_status()
            periodic_startup_pot_snapshot_request()
            poll_player_state()
            process_pending_yoshimi_preview()
            process_pending_user_preset_preview()
            process_pending_external_midi_pc_preview()
            sync_encoder_accel_profile(reason="idle")
            if midi_status_changed:
                maybe_render(force=True)
            else:
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
    # Clear stale ALSA sequencer routes before starting Fluid Ardule.
    # This avoids leftover aconnect links after Ctrl+C tests or systemctl restart.
    # Keep this intentionally narrow: do not kill processes here.
    stop_combi_router()
    run_cmd(["aconnect", "-x"])
    time.sleep(0.3)
    main()
