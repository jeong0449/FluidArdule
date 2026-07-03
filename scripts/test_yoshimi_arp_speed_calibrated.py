#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_yoshimi_arp_speed.py

Small standalone test for Fluid Ardule / Yoshimi Arpeggios "speed" control.

What it tests
-------------
1) Start Yoshimi headlessly with an .xiz preset:
       yoshimi -i -A -a -L <preset>

2) Verify runtime preset loading through Yoshimi stdin:
       load instrument <path>

3) Change the apparent arpeggio speed by controlling Part 1 Effect 2 Echo Delay:
       /
       set part 1
       set effect 2 echo
       set delay <mapped_delay>

This follows the same headless Yoshimi strategy used by 260703b:
- keep stdin open;
- suppress stdout/stderr prompt spam;
- treat a still-alive process shortly after a command as success.

Usage on Raspberry Pi
---------------------
sudo systemctl stop fluid_ardule.service
chmod +x test_yoshimi_arp_speed.py
./test_yoshimi_arp_speed.py

Then type measured/display BPM values:
    60
    90
    120
    150
    180
    210
    240
    r
    q

Optional:
    ./test_yoshimi_arp_speed.py --preset /home/pi/sf2/yoshimi_links/Arpeggios__0039-Soft-Arpeggio1.xiz
    ./test_yoshimi_arp_speed.py --kill-stale
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path


YOSHIMI_EXECUTABLE = "yoshimi"
DEFAULT_PRESET = "/home/pi/sf2/yoshimi_links/Arpeggios__0001-Arpeggio1.xiz"
DEFAULT_AUDIO_DEVICE = "default"
LOG_PATH = "/tmp/test_yoshimi_arp_speed.log"

RAW_MIDI_PREFERRED_HINTS = [
    "MPK Mini",
    "AKAI",
    "Keyboard",
]


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_cmd(cmd: list[str] | str) -> tuple[int, str]:
    try:
        if isinstance(cmd, str):
            p = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        else:
            p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return p.returncode, p.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


# Empirical calibration from Fluid Ardule/Yoshimi Arpeggio1 listening test.
# Test program input was "BPM-like speed"; observed apparent BPM was:
#   apparent_bpm ~= 0.797 * raw_speed + 5.13
#
# To let the user type an apparent/display BPM, invert that relation:
#   raw_speed ~= (display_bpm - 5.13) / 0.797
#
# Yoshimi still receives Echo Delay, not real BPM:
#   echo_delay = round(6000 / raw_speed)
#
# This keeps the UI number close to perceived BPM while preserving the
# discovered control path: Part 1 / Effect 2 / Echo / Delay.
ARP_CAL_SLOPE = 0.797
ARP_CAL_INTERCEPT = 5.13
ARP_DISPLAY_MIN = 60
ARP_DISPLAY_MAX = 240


def display_bpm_to_raw_speed(display_bpm: int) -> int:
    display_bpm = int(display_bpm)
    raw_speed = round((display_bpm - ARP_CAL_INTERCEPT) / ARP_CAL_SLOPE)
    return max(1, int(raw_speed))


def speed_to_delay(speed: int) -> int:
    # Argument name kept as "speed" for minimal change in the test utility,
    # but it now means user-facing/display BPM.
    raw_speed = display_bpm_to_raw_speed(speed)
    return max(1, min(127, round(6000 / raw_speed)))


def ensure_no_stale_yoshimi() -> None:
    code, out = run_cmd(["pgrep", "-x", "yoshimi"])
    if code != 0 or not out.strip():
        return

    log(f"stale Yoshimi detected: {out.strip()}")
    run_cmd(["pkill", "-TERM", "-x", "yoshimi"])
    deadline = time.time() + 2.0
    while time.time() < deadline:
        code, out = run_cmd(["pgrep", "-x", "yoshimi"])
        if code != 0 or not out.strip():
            log("stale Yoshimi cleared")
            return
        time.sleep(0.05)

    code, out = run_cmd(["pgrep", "-x", "yoshimi"])
    if code == 0 and out.strip():
        log(f"stale Yoshimi still alive; SIGKILL: {out.strip()}")
        run_cmd(["pkill", "-KILL", "-x", "yoshimi"])


def parse_aconnect_ports(output: str) -> list[tuple[str, str]]:
    """Return [(client:port, label), ...] from aconnect -i/-o output."""
    ports: list[tuple[str, str]] = []
    current_client: str | None = None
    current_name: str = ""

    client_re = re.compile(r"^client\s+(\d+):\s+'([^']+)'")
    port_re = re.compile(r"^\s*(\d+)\s+'([^']+)'")

    for line in output.splitlines():
        m = client_re.match(line)
        if m:
            current_client = m.group(1)
            current_name = m.group(2)
            continue

        m = port_re.match(line)
        if m and current_client is not None:
            port = f"{current_client}:{m.group(1)}"
            label = f"{current_name} {m.group(2)}"
            ports.append((port, label))

    return ports


def list_seq_inputs() -> list[tuple[str, str]]:
    code, out = run_cmd(["aconnect", "-i"])
    if code != 0:
        return []
    return parse_aconnect_ports(out)


def list_seq_outputs() -> list[tuple[str, str]]:
    code, out = run_cmd(["aconnect", "-o"])
    if code != 0:
        return []
    return parse_aconnect_ports(out)


def choose_keyboard_seq_input() -> tuple[str | None, str | None]:
    ports = list_seq_inputs()
    if not ports:
        return None, None

    for hint in RAW_MIDI_PREFERRED_HINTS:
        h = hint.lower()
        for port, label in ports:
            if h in label.lower():
                return port, label

    # Avoid obvious system/timer ports.
    for port, label in ports:
        if "system" not in label.lower() and "timer" not in label.lower():
            return port, label

    return ports[0]


def find_yoshimi_seq_output() -> tuple[str | None, str | None]:
    ports = list_seq_outputs()
    for port, label in ports:
        if "yoshimi" in label.lower():
            return port, label
    return None, None


class YoshimiTest:
    def __init__(self, preset: str, audio_device: str = DEFAULT_AUDIO_DEVICE):
        self.preset = str(preset)
        self.audio_device = audio_device
        self.proc: subprocess.Popen | None = None
        self.log_handle = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> bool:
        path = Path(self.preset)
        if not path.exists():
            log(f"Preset missing: {path}")
            return False

        cmd = [
            YOSHIMI_EXECUTABLE,
            "-i",
            "-A",
            "-a",
            "-L",
            str(path),
        ]

        log(f"Starting Yoshimi with {path.name}")
        self.log_handle = open(LOG_PATH, "w", buffering=1)
        self.log_handle.write("CMD: " + " ".join(cmd) + "\n")
        self.log_handle.write("NOTE: stdout/stderr suppressed; stdin kept open.\n")

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.PIPE,
                preexec_fn=os.setsid,
                text=True,
            )
        except FileNotFoundError:
            log("Yoshimi executable not found")
            return False
        except Exception as exc:
            log(f"Yoshimi start failed: {exc}")
            return False

        time.sleep(1.2)
        if self.alive():
            log(f"Yoshimi started, pid={self.proc.pid}")
            return True

        rc = self.proc.returncode if self.proc else None
        log(f"Yoshimi failed, rc={rc}. See {LOG_PATH}")
        return False

    def send(self, command: str) -> bool:
        if not self.alive():
            log("Yoshimi is not running")
            return False
        if self.proc is None or self.proc.stdin is None:
            log("Yoshimi stdin unavailable")
            return False

        try:
            self.proc.stdin.write(command.rstrip("\n") + "\n")
            self.proc.stdin.flush()
            time.sleep(0.05)
            if not self.alive():
                log("Command sent, but Yoshimi exited")
                return False
            return True
        except BrokenPipeError:
            log("Yoshimi CLI write failed: broken pipe")
            return False
        except Exception as exc:
            log(f"Yoshimi CLI write failed: {exc}")
            return False

    def send_block(self, block: str) -> bool:
        ok = True
        for line in block.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            ok = self.send(line) and ok
        return ok

    def load_instrument(self, path: str) -> bool:
        path = str(path or "").strip()
        if not path:
            log("Empty instrument path")
            return False
        if not Path(path).exists():
            log(f"Instrument file missing: {path}")
            return False
        if " " in path:
            log("WARNING: path contains spaces; Yoshimi CLI may not parse it reliably")
        ok = self.send(f"load instrument {path}")
        log(f"live load {'OK' if ok else 'FAILED'}: {Path(path).name}")
        return ok

    def set_speed(self, speed: int) -> bool:
        raw_speed = display_bpm_to_raw_speed(speed)
        delay = speed_to_delay(speed)
        block = f"""
/
set part 1
set effect 2 echo
set delay {delay}
"""
        ok = self.send_block(block)
        log(
            f"Arp BPM {speed:3d} -> calibrated speed {raw_speed:3d} "
            f"-> Echo Delay {delay:3d} : {'OK' if ok else 'FAILED'}"
        )
        return ok

    def stop(self) -> None:
        if self.proc is not None:
            try:
                if self.alive():
                    log("Stopping Yoshimi")
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                    try:
                        self.proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                self.proc = None
            except Exception as exc:
                log(f"Stop failed: {exc}")
        if self.log_handle:
            try:
                self.log_handle.close()
            except Exception:
                pass
            self.log_handle = None


def connect_keyboard_to_yoshimi() -> None:
    src, src_label = choose_keyboard_seq_input()
    dst, dst_label = find_yoshimi_seq_output()

    if not src:
        log("No ALSA sequencer MIDI input found; connect manually if needed")
        return
    if not dst:
        log("No Yoshimi ALSA sequencer output port found; connect manually if needed")
        return

    code, out = run_cmd(["aconnect", src, dst])
    if code == 0:
        log(f"MIDI connected: {src} ({src_label}) -> {dst} ({dst_label})")
    else:
        log(f"MIDI connect failed: {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test calibrated Yoshimi Arpeggio BPM via Echo Delay")
    parser.add_argument("--preset", default=DEFAULT_PRESET, help="Initial .xiz preset path")
    parser.add_argument("--audio-device", default=DEFAULT_AUDIO_DEVICE, help="Reserved for future use; Yoshimi -a uses ALSA default here")
    parser.add_argument("--kill-stale", action="store_true", help="Kill stale yoshimi processes before starting")
    parser.add_argument("--no-connect-midi", action="store_true", help="Do not try aconnect MIDI keyboard to Yoshimi")
    args = parser.parse_args()

    if args.kill_stale:
        ensure_no_stale_yoshimi()

    yt = YoshimiTest(args.preset, args.audio_device)
    if not yt.start():
        return 1

    try:
        if not args.no_connect_midi:
            connect_keyboard_to_yoshimi()

        # Explicitly verify live preset loading with the same file after startup.
        # This tests the exact 'load instrument <path>' path used by Fluid Ardule.
        yt.load_instrument(args.preset)
        yt.set_speed(120)

        print()
        print("Commands:")
        print("  60..240  set calibrated Arp BPM")
        print("  r        live-reload current preset")
        print("  l PATH   live-load another .xiz preset")
        print("  q        quit")
        print()

        while True:
            value = input("Arp BPM [60-240], r, l PATH, q > ").strip()
            if not value:
                continue
            if value.lower() == "q":
                break
            if value.lower() == "r":
                yt.load_instrument(args.preset)
                yt.set_speed(120)
                continue
            if value.lower().startswith("l "):
                new_path = value[2:].strip()
                if yt.load_instrument(new_path):
                    args.preset = new_path
                    yt.preset = new_path
                    yt.set_speed(120)
                continue

            try:
                speed = int(value)
            except ValueError:
                print("Enter a number, r, l PATH, or q.")
                continue

            if not ARP_DISPLAY_MIN <= speed <= ARP_DISPLAY_MAX:
                print("Range: 60-240")
                continue

            yt.set_speed(speed)

    finally:
        yt.stop()

    print()
    print("Restart Fluid Ardule when done:")
    print("  sudo systemctl start fluid_ardule.service")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
