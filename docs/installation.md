# Installation Guide

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

This guide assumes the default Raspberry Pi OS user account `pi`.

---

### 1.2 Initial Configuration (raspi-config)

After the first boot, configure essential system settings. This ensures required interfaces (SPI, serial) are enabled and the system is properly localized.

```bash
sudo raspi-config
```

Recommended:
- Interface Options → SPI → Enable
- Enable Serial (enable login shell) if you want to use UART as a console interface, for example via PuTTY.
- Set locale/timezone
- Expand filesystem

Reboot:

```bash
sudo reboot
```

Install the required packages:

```bash
sudo apt update
sudo apt upgrade
sudo apt install fbi alsa-utils fluidsynth python3 python3-serial python3-mido python3-rtmidi dhcdcd5
```

---

### 1.3 Network Configuration (without NetworkManager)

This project avoids NetworkManager to keep the system lightweight and predictable.

Instead, it uses:
- `dhcpcd` (IP management)
- `wpa_supplicant` (Wi-Fi)

Edit:

```bash
sudo systemctl stop NetworkManager.service
sudo systemctl disable NetworkManager.service
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
sudo apt purge cloud-init -y
```

Example:

```plaintext
country=KR
network={
    ssid="YOUR_SSID"
    psk="YOUR_PASSWORD"
}
```

Apply:

```bash
sudo wpa_cli -i wlan0 reconfigure
```

Use the following commands to identify services that slow down the boot process:

```bash
systemd-analyze
systemd-analyze blame | head -20
```

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
pi ALL=(ALL) NOPASSWD: /usr/sbin/shutdown, /usr/sbin/reboot
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

### 2.1 SPI TFT (ILI9486) Setup (without LCD-show)

Vendor scripts like LCD-show are intentionally avoided because they overwrite system configurations and can break updates.

Instead, use standard device tree overlays.

Enable SPI:

```bash
sudo raspi-config
```

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

Reboot:

```bash
sudo reboot
```

Verify framebuffer:

```bash
ls /dev/spidev*
ls /dev/fb*
```

Test display (use [FluidArdule.png](/images/FluidArdule.png)):

```bash
sudo apt install fbi
sudo fbi -T 1 -d /dev/fb1 -a FluidArdule.png
```

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
pcm.!default {
    type plug
    slave.pcm "hw:sndrpihifiberry"
}

ctl.!default {
    type hw
    card sndrpihifiberry
}
```

---

### 2.5 Add Software Volume Control (softvol)

Most I2S DAC modules have no hardware volume control.

```plaintext
pcm.softvol {
    type softvol
    slave.pcm "hw:sndrpihifiberry"
    control {
        name "Master"
        card sndrpihifiberry
    }
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

---

### 2.6 Test Audio Output

```bash
aplay /usr/share/sounds/alsa/Front_Center.wav
```

---

## 3. System Integration

### 3.1 TFT Splash Screen Service

Provides immediate visual feedback during boot.

```bash
sudo nano /etc/systemd/system/fluidardule-splash.service
```

```ini
[Unit]
Description=Fluid Ardule TFT Splash Screen
After=multi-user.target

[Service]
User=pi
ExecStart=/usr/bin/fbi -T 1 -d /dev/fb1 -a /home/pi/images/splash.png

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl enable fluidardule-splash
```

---

### 3.2 Main Service

Runs the system automatically at boot.

```bash
sudo nano /etc/systemd/system/fluid_ardule.service
```

```ini
[Service]
User=pi
ExecStart=/usr/bin/python3 /home/pi/scripts/launch_fluidardule.py
Restart=always
```

---

## 4. Logging and Debugging

### 4.1 journalctl (Primary Logging System)

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

### 4.2 Persistent Logs

By default, logs may not survive reboot.

Enable persistence:

```bash
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

---

### 4.3 syslog is NOT Installed by Default

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

### 4.4 When to Use Which

- `journalctl` → primary, real-time debugging
- `syslog` → optional, text-based logs

---

## 5. Verification

- Audio works
- MIDI works
- UI works

---

## 6. Notes

- Always use card name instead of index
- I2S DAC has no hardware mixer
- journald is the default logging system
