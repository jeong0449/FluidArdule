# Installation Guide

Updated: 2026-07-10

🚧 This document is currently under construction and may contain errors or incomplete instructions.

---

## 1. Base System Setup

### 1.1 OS Installation

Fluid Ardule runs on Raspberry Pi OS. The **32-bit Lite version is strongly recommended** for maximum compatibility and stability with low-level interfaces such as I2S audio, SPI displays, and ALSA/MIDI components.

Download Raspberry Pi OS from the official website:
https://www.raspberrypi.com/software/operating-systems/

For Windows users, Raspberry Pi Imager is the recommended tool for installing Raspberry Pi OS:
https://www.raspberrypi.com/software/

> Be careful to select the correct device to avoid data loss.

#### Initial Wi-Fi and SSH Setup

It is strongly recommended to configure the initial Wi-Fi network and enable SSH using Raspberry Pi Imager before writing the OS image. This allows the Raspberry Pi to connect to the network and accept SSH connections from the first boot.

Fluid Ardule is a DIY Raspberry Pi synthesizer project rather than a consumer appliance. Basic familiarity with Raspberry Pi OS, SSH, and command-line system administration is recommended.

The Fluid Ardule runtime interface is intentionally focused on musical operation and does not provide a general-purpose text entry interface for entering new Wi-Fi credentials. Additional wireless networks can be configured later through the Raspberry Pi OS networking configuration.

This design avoids adding a complex on-device network setup system and keeps the runtime environment lightweight and predictable.

This guide assumes the default Raspberry Pi OS user account `pi`.

#### Environment (reference system)

This guide was tested on the following system (as of 2026-04-22):

```plaintext
Raspberry Pi OS (Raspbian) 13 (trixie), 32-bit
Kernel: Linux 6.12.75+rpt-rpi-v7
Architecture: armv7l
```

---

### 1.2 Initial Configuration (raspi-config)

After the first boot, configure essential system settings. This ensures required interfaces (SPI, serial) are enabled and the system is properly localized.

```bash
sudo raspi-config
```

Recommended:
- System Options → Boot → Console
- Interface Options → SPI → Yes
- Interface Options → Serial Port → Enable as needed (for example, when using UART as a console interface via PuTTY)
- Localisation Options → Choose as you want

Reboot:

```bash
sudo reboot
```

Install the required packages:

```bash
sudo apt update
sudo apt upgrade
sudo apt install fbi alsa-utils fluidsynth yoshimi python3 python3-serial python3-mido python3-rtmidi dhcpcd git
```

---

### 1.3 Network Configuration (without NetworkManager)

The initial Wi-Fi connection should already have been configured using Raspberry Pi Imager as described above. Verify that the Raspberry Pi can connect to the network and that SSH access works before changing the networking stack.

Recent Raspberry Pi OS installations use NetworkManager by default. While convenient during initial setup, NetworkManager may add significant boot time on a small embedded system.

NetworkManager should only be disabled after the replacement network configuration has been prepared and verified. Disabling NetworkManager before configuring `wpa_supplicant` may result in loss of network and SSH access.

Use the following commands to identify services that slow down the boot process:

```bash
systemd-analyze
systemd-analyze blame | head -20
```

In many cases, you will find that NetworkManager consumes a significant amount of boot time. This project avoids NetworkManager to keep the system lightweight and predictable.

Instead, it uses:

- `dhcpcd` (IP management)
- `wpa_supplicant` (Wi-Fi)

Consider disabling or removing unnecessary services to improve boot performance:

```bash
sudo systemctl stop NetworkManager.service
sudo systemctl disable NetworkManager.service

# Alternatively, use the following single command:
sudo systemctl disable --now NetworkManager.service

# Optional (for minimal/headless setups):
# After the initial Raspberry Pi Imager configuration has been applied,
# cloud-init is generally no longer needed on a dedicated appliance.
# Removing it may reduce boot-time service overhead.
sudo apt purge cloud-init -y
```

These components (dhcpcd + wpa_supplicant) must be properly configured to enable reliable automatic Wi-Fi connectivity.  

For detailed configuration and troubleshooting, see the [Networking Guide](networking-guide.md).

---

You can also review and disable other services to further optimize boot time:

```bash
sudo systemctl disable --now bluetooth
sudo systemctl disable --now avahi-daemon
sudo systemctl disable --now triggerhappy
sudo systemctl disable --now hciuart
sudo systemctl disable --now apt-daily.timer
sudo systemctl disable --now apt-daily-upgrade.timer

# Desktop version only:
sudo systemctl set-default multi-user.target
sudo systemctl disable --now lightdm
```

> Note: Some services may not be installed on your system.

Setting `gpu_mem=16` and `hdmi_force_hotplug=1` in `/boot/firmware/config.txt` can slightly reduce system overhead by minimizing GPU memory allocation and disabling unnecessary HDMI detection.

---

### 1.4 Privilege and Audio Configuration

This section configures system permissions required for safe shutdown/reboot
and improves audio performance for real-time applications.


#### Grant passwordless sudo for shutdown/reboot

To allow the system (e.g., via Arduino input) to perform shutdown or reboot
without requiring a password, update the sudoers configuration.

Edit the sudoers file using `visudo`:

```
sudo visudo
```

By default, `visudo` uses `nano`.
To use `vim` for this session:

```
sudo EDITOR=vim visudo
```

Add the following line at the end of the file:

```
pi ALL=(root) NOPASSWD: /usr/sbin/shutdown, /usr/sbin/reboot
```

Make sure the command paths are correct on your system.

---

#### Configure audio group and real-time priority

To improve audio stability and reduce latency, add the user to the `audio` group:

```
sudo usermod -aG audio $USER
```

Then edit:

```
sudo nano /etc/security/limits.conf
```

Add the following lines:

```
@audio   -  rtprio     95
@audio   -  memlock    unlimited
```

These settings allow higher thread priority and prevent memory swapping
for audio processes.

---

#### Verify audio group

The `audio` group is typically pre-existing on Debian-based systems,
including Raspberry Pi OS.

You can verify it with:

```
getent group audio
```

Example output:

```
audio:x:29:
```

A logout or reboot is required for group membership changes to take effect.

---

## 2. Hardware Interface Setup

### 2.1 SPI TFT Display (ILI9486) Setup (without LCD-show)

Vendor scripts like LCD-show are intentionally avoided because they overwrite system configurations and can break updates.

Instead, use standard device tree overlays.

Edit:

```bash
sudo nano /boot/firmware/config.txt
```

Uncomment or add the following lines:

```plaintext
dtparam=spi=on
dtoverlay=vc4-fkms-v3d
max_framebuffers=2
dtoverlay=piscreen,spi0-0,rotate=90,speed=32000000,fps=30
```

> [!NOTE]
> The `rotate=90` option changes the ILI9486 framebuffer from its native portrait orientation to the 480×320 landscape orientation used by the Fluid Ardule UI.
>
> In the reference Fluid Ardule hardware, the TFT is then physically mounted in the opposite landscape orientation to simplify connector and cable routing inside the enclosure. This makes the raw framebuffer output appear 180 degrees inverted relative to the normal viewing direction.
>
> The Fluid Ardule runtime UI compensates for this physical mounting orientation by rotating the rendered screen by 180 degrees in software. This is intentional and is separate from the `rotate=90` framebuffer setting.
>
> Linux framebuffer console output does not pass through the Fluid Ardule runtime rendering path. Therefore, when the TFT is used as a text console, the reference system also adds the following kernel parameter to `/boot/firmware/cmdline.txt`:
>
> `fbcon=rotate:2`
>
> The `cmdline.txt` file must remain a single line. Display rotation settings may need to be adjusted if a different TFT mounting direction or enclosure layout is used.

Reboot:

```bash
sudo reboot
```

Verify framebuffer:

```bash
ls /dev/spidev*
ls /dev/fb*

# Expected output:
# /dev/fb0 (HDMI)
# /dev/fb1 (TFT-LCD)
```

Test display (use [FluidArdule.png](/images/FluidArdule.png)):

```bash
sudo fbi -T 1 -d /dev/fb1 -a FluidArdule.png

# Manually clear the framebuffer (/dev/fb1)
sudo dd if=/dev/zero of=/dev/fb1
```

To completely disable output, add the following settings to /boot/firmware/config.txt:

````
hdmi_ignore_hotplug=1
disable_splash=1
boot_delay=0
````
---

### 2.2 I2S DAC Setup

Enable high-quality audio output via GPIO-based I2S.

```bash
sudo nano /boot/firmware/config.txt
```

```plaintext
dtparam=audio=off
dtoverlay=hifiberry-dac
```

Reboot:

```bash
sudo reboot
```

---

### 2.3 Verify Audio Device

Check that the DAC is detected:

```bash
aplay -l
```

---

### 2.4 Configure ALSA Default Device

Fix the default audio output to prevent device index changes.

```bash
sudo nano /etc/asound.conf
```

```plaintext
pcm.softvol {
    type softvol
    slave.pcm "hw:CARD=sndrpihifiberry,DEV=0"
    control {
        name "Master"
        card sndrpihifiberry
    }
    min_dB -50.0
    max_dB 0.0
}

pcm.!default {
    type plug
    slave.pcm "softvol"
}

ctl.!default {
    type hw
    card sndrpihifiberry
}
```
Most I2S DAC modules have no hardware volume control. 
This configuration enables software-based volume control using ALSA.

---

### 2.5 Test Audio Output

```bash
aplay /usr/share/sounds/alsa/Front_Center.wav
```

---

### 2.6 Arduino Firmware Setup

Fluid Ardule uses two Arduino Uno boards:

- **UNO-1** — UI controller (buttons, encoder, LCD)
- **(optional) UNO-2** — MIDI router

Before proceeding, make sure both boards are flashed with the correct firmware.

---

#### UNO-1 (UI controller)

UNO-1 runs the Fluid Ardule UI firmware, which handles:

- Button input (analog keypad)
- Rotary encoder
- LCD display
- Serial communication with Raspberry Pi

Refer to the firmware provided in this repository (or the appropriate UI firmware file you are using).

---

#### UNO-2

UNO-2 firmware is maintained in the NanoArdule repository:

👉 https://github.com/jeong0449/NanoArdule/tree/main/firmware/ardule_usb_midi_host

Upload the firmware (`ardule-usb-midi-host.ino`) to the Arduino Uno used as UNO-2.

This firmware enables:
- USB MIDI host input
- DIN MIDI input/output
- USB-serial MIDI forwarding to Raspberry Pi

---


## 3. Software Setup

### 3.1 Audio Playback Software

Install packages required to play common audio formats such as MP3, OGG, and WMA.

```bash
sudo apt update
sudo apt install mpv vorbis-tools mpg123
```

- `mpv` — versatile media player (supports MP3, OGG, WMA, and more)  
- `vorbis-tools` — provides `ogg123` for lightweight OGG playback  
- `mpg123` — lightweight MP3 player  

---

The media playback feature of [`launch_fluidardule.py`](../scripts/launch_fluidardule.py) scans `/home/pi/media`.  
Store audio files in this directory.

USB flash drives can be automatically mounted to `/home/pi/media/usb`.  
See the separate documentation for setup instructions.

#### Test audio playback

```bash
mpv your_file.mp3
mpv your_file.ogg
mpv your_file.wma
```

---

#### Optional: lightweight players

```bash
ogg123 your_file.ogg
mpg123 your_file.mp3
```

These tools are useful for quick testing or low-overhead playback.

---

### 3.2 FluidSynth and MIDI Test

This section verifies that FluidSynth is working correctly with the I2S DAC configured as the default ALSA device.

---

#### Run FluidSynth (using default audio device)

```bash
fluidsynth ~/sf2/your_soundfont.sf2
```

```plaintext
FluidSynth runtime version 2.4.4
Copyright (C) 2000-2025 Peter Hanappe and others.
Distributed under the LGPL license.
SoundFont(R) is a registered trademark of Creative Technology Ltd.

Type 'help' for help topics.

>
```

- Uses the default ALSA device defined in `/etc/asound.conf`

If configured correctly, audio output should be routed to the I2S DAC.

---

#### Test with a MIDI file

In another terminal:

```bash
aplaymidi -l
```

Example output:

```text
Port    Client name                      Port name
128:0   FLUID Synth                      Synth input port (128:0)
```

Then play a MIDI file:

```bash
aplaymidi -p 128:0 your_file.mid
```

You should hear audio through the DAC.

For better flexibility and consistency with real MIDI input, it is recommended to use `aplaymidi` from a separate terminal.

You can play MIDI files either by supplying them directly to FluidSynth.

```bash
fluidsynth ~/sf2/FluidR3_GM.sf2 file.mid
```

---

#### Test with a MIDI keyboard

List available MIDI input devices:

```bash
aconnect -l
```

Example output:

```text
client 20: 'USB MIDI Keyboard' [type=kernel,card=1]
    0 'USB MIDI Keyboard MIDI 1'
client 128: 'FLUID Synth' [type=user]
    0 'Synth input port (128:0)'
```

Connect the keyboard to FluidSynth:

```bash
aconnect 20:0 128:0
```

Play the keyboard — sound should be produced immediately.

---

#### Notes

> [!NOTE]
> The client and port numbers (e.g., `20:0`, `128:0`) may vary depending on your system.

> [!TIP]
> Use `aconnect -x` to disconnect all MIDI connections if needed.

---

### 3.3 Directory Structure

The Fluid Ardule system uses a simple directory layout under `/home/pi`:

```bash
mkdir -p ~/sf2
mkdir -p ~/scripts
```

Clone the repository into your home directory:

```bash
cd ~
git clone https://github.com/jeong0449/FluidArdule.git
```

Then move the required directories into place:

```bash
mv ~/FluidArdule/sf2 ~/
mv ~/FluidArdule/scripts ~/
```

- `/home/pi/sf2` — resource directory containing:
  - SoundFont (`.sf2`) files
  - preset definition JSON files (generated by [`extract_sf2_presets.py`](../sf2/extract_sf2_presets.py) and [`extract_yoshimi_patches.py`](../sf2/extract_yoshimi_patches.py))
  - UI assets such as the boot splash image ([`FluidArdule_rot.png`](sf2/FluidArdule_rot.png))

- `/home/pi/scripts` — contains:
  - main application scripts
  - supporting Python programs
  - launcher scripts

---

### 3.4 Build and Pre-test MIDI Bridge

Before relying on the compiled bridge in the main Fluid Ardule workflow, verify that UNO-2 is correctly sending MIDI data over USB serial.  
The required build tools must be installed to compile the MIDI bridge.

Build the C bridge binary:

```bash
sudo apt update
sudo apt install build-essential
cd ~/scripts
gcc -o uno_midi_bridge_sp uno_midi_bridge.c
```

---

#### Pre-test with Python diagnostic script

For a quick pre-test, use the Python diagnostic script `uno_midi_serial_dump.py`:

```bash
cd ~/scripts
python3 uno_midi_serial_dump.py
```

This script prints incoming serial data from UNO-2 in a human-readable form, allowing you to confirm that MIDI messages are being received correctly.

After starting the script, connect a MIDI source to UNO-2 and play a few notes. If communication is working correctly, MIDI-related messages should appear in the terminal.

---

#### What to check

- UNO-2 is powered and running  
- The correct serial device is detected  
- MIDI input is reaching the Raspberry Pi over USB serial  

---

#### Run the bridge

Once serial MIDI data is confirmed, run the bridge:

```bash
cd ~/scripts
./uno_midi_bridge_sp
```

This creates a virtual MIDI port that can be connected to FluidSynth using `aconnect`.
When UNO-2 is selected as the MIDI input device, the bridge binary is started automatically by `launch_fluidardule.py`.

> [!NOTE]
> The UNO MIDI bridge identifies the correct device using a stable USB device ID (`/dev/serial/by-id/`) and is **only activated when explicitly selected in the UI**.
> It is not auto-selected, ensuring that optional devices do not override the current MIDI input mode.
> See [`uno-bridge-README.md`](./uno-bridge-README.md) for details.

> [!NOTE]
> The exact build process may vary depending on your implementation of the MIDI bridge.


---

### 3.5 Pre-Service Configuration

Before enabling the main service, several device-specific settings in [`launch_fluidardule.py`](/scripts/launch_fluidardule.py) must be adjusted:

- `SERIAL_PORT`
- `SOUNDFONTS`
- `KNOWN_USB_DACS`
- `RAW_MIDI_PREFERRED_HINTS`

---
#### Identify optional USB DAC devices

Connect your USB DAC, then run:

```bash
aplay -l
```

Example output:

```text
**** List of PLAYBACK Hardware Devices ****
card 0: sndrpihifiberry [snd_rpi_hifiberry_dac], device 0: HifiBerry DAC HiFi pcm5102a-hifi-0 [HifiBerry DAC HiFi pcm5102a-hifi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: O22 [Onyx Producer 2-2], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0

```

Use the **card name** (e.g., `O22` or `Onyx Producer 2-2`) when configuring `KNOWN_USB_DACS`.

> Avoid using card index numbers (e.g., `card 1`), as they may change across reboots.

---

#### Identify MIDI devices (raw / ALSA)

Connect your MIDI device, then run:

```bash
aconnect -l
```

Example output:

```text
client 20: 'USB MIDI Keyboard' [type=kernel]
    0 'USB MIDI Keyboard MIDI 1'
```

You may also check raw MIDI devices:

```bash
amidi -l
```

Example output:

```text
Dir Device    Name
IO  hw:1,0,0  MPK Mini Mk II MIDI 1
```
---

#### Why this matters

Device indices (e.g., `hw:1,0`) are assigned dynamically by the system and may change depending on:

- USB connection order  
- Power-on timing  
- Presence of other devices  

To ensure stable operation, Fluid Ardule uses **name-based matching** instead of fixed indices.

This allows the system to:

- Automatically select the correct USB DAC  
- Prefer specific MIDI input devices  
- Remain robust across reboots and hardware changes

---

## 4. System Integration

### 4.1 TFT Splash Screen Service

Provides immediate visual feedback during boot.

```bash
sudo nano /etc/systemd/system/tft-splash.service
```

```ini
[Unit]
Description=TFT splash screen
DefaultDependencies=no
After=local-fs.target
 
[Service]
Type=oneshot
ExecStart=/home/pi/scripts/tft-splash.sh
RemainAfterExit=yes
 
[Install]
WantedBy=sysinit.target
```

Enable:

```bash
sudo systemctl enable fluidardule-splash
```

---
### 4.2 Main Service

Runs the system automatically at boot.

```bash
sudo nano /etc/systemd/system/fluid_ardule.service
```

```ini
[Unit]
Description=FluidArdule Main Service
After=multi-user.target sound.target
Wants=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/scripts
ExecStart=/usr/bin/python3 /home/pi/scripts/launch_fluidardule.py
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl enable fluid_ardule.service
```

---

### 4.3 TFT Console Mode

Fluid Ardule can temporarily hand the TFT framebuffer over to the Linux text console for system configuration and maintenance. A USB keyboard can then be used directly on the Raspberry Pi.

The Power menu `Console` action uses a small privileged helper to switch virtual console 1 to the TFT framebuffer.

Create the console helper:

```bash
sudo nano /usr/local/sbin/fluidardule-console
```

Add:

```bash
#!/bin/bash
sleep 1
/usr/bin/con2fbmap 1 1
/usr/bin/chvt 1
```

Create the return helper:

```bash
sudo nano /usr/local/sbin/fluidardule-return
```

Add:

```bash
#!/bin/bash
set -e

/usr/bin/con2fbmap 1 0
/bin/systemctl start fluid_ardule.service
```

Make both helpers executable:

```bash
sudo chmod 755 /usr/local/sbin/fluidardule-console
sudo chmod 755 /usr/local/sbin/fluidardule-return
```

The Fluid Ardule service runs as user `pi`. Allow only these console helpers to run as `root` without a password.

Edit the sudoers file using `visudo`:

```bash
sudo visudo
```

Add the following separate rule:

```text
pi ALL=(root) NOPASSWD: /usr/local/sbin/fluidardule-console, /usr/local/sbin/fluidardule-return
```

> [!NOTE]
> This rule is intentionally separate from the shutdown/reboot rule configured in Section 1.4. Both rules restrict passwordless execution to explicitly listed commands and run them as `root`.

#### Enter and leave Console mode

Select `Console` from the Fluid Ardule Power menu. The runtime exits normally and the helper maps Linux virtual console 1 to `/dev/fb1`.

To return to Fluid Ardule, run the following command from the TFT console:

```bash
sudo fluidardule-return
```

The `fbcon=rotate:2` setting described in Section 2.1 keeps the Linux text console aligned with the physical TFT orientation used by the reference Fluid Ardule hardware.

---

## 5. Logging and Debugging

### 5.1 journalctl (Primary Logging System)

Modern Raspberry Pi OS uses **systemd-journald**, not traditional syslog.

View logs:

```bash
journalctl -u fluid_ardule.service
```

Real-time:

```bash
journalctl -u fluid_ardule.service -f
```

---

### 5.2 Persistent Logs

By default, logs may not survive reboot.

Enable persistence:

```bash
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

---

### 5.3 syslog is NOT Installed by Default

Unlike traditional Linux systems, `/var/log/syslog` may not exist.

This can be confusing if you expect classic log files.

To restore traditional logging:

```bash
sudo apt update
sudo apt install rsyslog
```

After installation:

```bash
/var/log/syslog
```

will be available.

---

### 5.4 When to Use Which

- `journalctl` → primary, real-time debugging
- `syslog` → optional, text-based logs

---

## 6. Verification

- Audio works
- MIDI works
- UI works

---

## 7. Notes

- Always use card name instead of index
- I2S DAC has no hardware mixer
- journald is the default logging system
