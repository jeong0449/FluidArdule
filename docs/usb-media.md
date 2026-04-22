# USB Media Auto-Mount

This document describes how to configure automatic USB media mounting and proper filename encoding (including Korean) on Raspberry Pi OS.

The configuration uses:

- `udev` (device detection)
- `systemd` template service (trigger execution)
- `systemd-mount` (mount management)

---

## Overview

When a USB storage device is inserted:

1. udev detects the device  
2. systemd triggers a template service  
3. a custom script runs  
4. systemd-mount creates and manages the mount  

---

## 1. Create Mount Point

```bash
mkdir -p /home/pi/media/usb
```

---

## 2. Create systemd Template Service

```bash
sudo nano /etc/systemd/system/fluidardule-usb-mount@.service
```

```ini
[Unit]
Description=Mount USB filesystem for Fluid Ardule (%I)
After=dev-%i.device
BindsTo=dev-%i.device

[Service]
Type=oneshot
ExecStart=/usr/local/bin/fluidardule-usb-mount.sh %I
RemainAfterExit=yes
```

---

## 3. Create Mount Script

```bash
sudo nano /usr/local/bin/fluidardule-usb-mount.sh
sudo chmod +x /usr/local/bin/fluidardule-usb-mount.sh
```

```bash
#!/bin/bash
set -euo pipefail

DEV="/dev/$1"
MNT="/home/pi/media/usb"
USER_UID="1000"
USER_GID="1000"

PARENT_NAME="$(lsblk -no PKNAME "$DEV" 2>/dev/null || true)"
PARENT_DEV=""

if [ -n "$PARENT_NAME" ]; then
    PARENT_DEV="/dev/$PARENT_NAME"
fi

if [ -z "$PARENT_DEV" ]; then
    exit 0
fi

if [ "$(lsblk -no TRAN "$PARENT_DEV" 2>/dev/null || true)" != "usb" ]; then
    exit 0
fi

mkdir -p "$MNT"

FSTYPE="$(blkid -o value -s TYPE "$DEV" 2>/dev/null || true)"

case "${FSTYPE,,}" in
    vfat|fat|msdos)
        exec systemd-mount \
            --no-block --collect --owner=pi \
            -o uid=${USER_UID},gid=${USER_GID},iocharset=utf8,codepage=949,fmask=0133,dmask=0022 \
            "$DEV" "$MNT"
        ;;
    exfat)
        exec systemd-mount \
            --no-block --collect --owner=pi \
            -o uid=${USER_UID},gid=${USER_GID},umask=022 \
            "$DEV" "$MNT"
        ;;
    ntfs|ntfs3)
        exec systemd-mount \
            --no-block --collect --owner=pi \
            -o uid=${USER_UID},gid=${USER_GID},umask=022 \
            "$DEV" "$MNT"
        ;;
    *)
        exec systemd-mount \
            --no-block --collect --owner=pi \
            "$DEV" "$MNT"
        ;;
esac
```

---

## 4. Create udev Rule

```bash
sudo nano /etc/udev/rules.d/99-fluidardule-usb.rules
```

```udev
ACTION=="add", SUBSYSTEM=="block", KERNEL=="sd[a-z][0-9]", \
ENV{ID_BUS}=="usb", ENV{ID_FS_USAGE}=="filesystem", \
TAG+="systemd", ENV{SYSTEMD_WANTS}+="fluidardule-usb-mount@%k.service"
```

---

## 5. Apply Changes

```bash
sudo udevadm control --reload
sudo udevadm trigger
```

---

## 6. Verify Operation

Insert a USB device, then check:

```bash
findmnt /home/pi/media/usb
```

Or:

```bash
systemctl list-units --type=mount
```

---

## 7. Filename Encoding

For FAT-based filesystems (vfat), the following options are critical:

- `iocharset=utf8`
- `codepage=949`

These ensure proper display of filenames created on Windows systems using Korean encoding.

---

## Summary

This configuration provides:

- Automatic USB mounting via udev and systemd  
- Stable mount handling using systemd-mount  
- Reliable filename encoding support (including Korean)  
- No dependency on desktop auto-mount tools (e.g., udisks)  
- Minimal user interaction and robust behavior  
