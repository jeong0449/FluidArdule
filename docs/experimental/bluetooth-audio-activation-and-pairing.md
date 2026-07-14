# Experimental Documents

# Bluetooth Audio Activation and Pairing (Raspberry Pi OS Trixie)

**First written:** 2026-07-15

> **Status:** Experimental
>
> This document summarizes the successful evaluation of Bluetooth audio reception on Fluid Ardule. The feature is **not yet integrated into the main UI**, but the underlying Bluetooth and BlueALSA infrastructure has been verified.

## Purpose

This document describes how to re-enable Bluetooth, pair an Android phone (tested with a Samsung Galaxy S23), and verify Bluetooth audio playback using BlueALSA.

## 1. Re-enable Bluetooth

Fluid Ardule may disable Bluetooth at the firmware level to reduce boot time.

Check the current configuration:

```bash
grep dtoverlay /boot/firmware/config.txt
```

If the following line exists:

```text
dtoverlay=disable-bt
```

comment it out:

```text
#dtoverlay=disable-bt
```

Then reboot:

```bash
sudo reboot
```

## 2. Enable the Bluetooth Service

```bash
sudo systemctl enable --now bluetooth
```

**Note:** On Raspberry Pi OS Trixie, `hciuart.service` is no longer present.

## 3. Verify the Bluetooth Controller

```bash
bluetoothctl list
```

Expected:

```text
Controller XX:XX:XX:XX:XX:XX Fluidule [default]
```

## 4. Pair a Mobile Device

```bash
bluetoothctl
```

Execute:

```text
power on
agent on
default-agent
pairable on
discoverable on
discoverable-timeout 0
pairable-timeout 0
```

Select **Fluidule** on the phone.

When prompted, confirm the passkey by typing:

```text
yes
```

Then:

```text
trust <device MAC>
connect <device MAC>
```

## 5. Verify the Pairing

```text
info <device MAC>
```

Expected:

```text
Paired: yes
Bonded: yes
Trusted: yes
Connected: yes
```

## 6. Pairing Database

BlueZ stores persistent pairing information in:

```text
/var/lib/bluetooth/<Adapter MAC>/<Device MAC>/info
```

## 7. Verify BlueALSA

```bash
systemctl status bluealsa
aplay -L
```

Expected PCM:

```text
bluealsa
    Bluetooth Audio
```

## 8. Test Bluetooth Audio Playback

```bash
sudo systemctl stop fluid_ardule.service
bluealsa-aplay -vv
```

Start music playback from the paired phone.

Successful playback through the HiFiBerry DAC confirms that Bluetooth audio reception is working correctly.

## Notes

- `avahi-daemon` is typically already disabled on Raspberry Pi OS Trixie.
- `hciuart.service` is no longer provided.
- Bluetooth Audio is currently an **experimental** feature.
- Planned integration: **Media Player → Bluetooth Audio**.
- Device pairing is intentionally left as a manual Console/SSH operation using `bluetoothctl`.
