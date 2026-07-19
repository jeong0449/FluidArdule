# Bluetooth Audio Activation and Pairing (Raspberry Pi OS Trixie)

**Last updated:** 2026-07-19

> This document describes Bluetooth pairing and management for Fluid Ardule after Bluetooth Audio has been enabled according to `installation.md`.

## Purpose

This document describes how to re-enable Bluetooth, pair an Android phone (tested with a Samsung Galaxy S23), and verify Bluetooth audio playback using BlueALSA.

## 1. Pair a Mobile Device

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

## 2. Verify the Pairing

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

## 3. Pairing Database

BlueZ stores persistent pairing information in:

```text
/var/lib/bluetooth/<Adapter MAC>/<Device MAC>/info
```

## 4. Verify BlueALSA

```bash
systemctl status bluealsa
aplay -L
```

Expected PCM:

```text
bluealsa
    Bluetooth Audio
```

## 5. Test Bluetooth Audio Playback

```bash
sudo systemctl stop fluid_ardule.service
bluealsa-aplay -vv
```

Start music playback from the paired phone.

Successful playback through the HiFiBerry DAC confirms that Bluetooth audio reception is working correctly.

## Notes

- `avahi-daemon` is typically already disabled on Raspberry Pi OS Trixie.
- `hciuart.service` is no longer provided.
- Bluetooth Audio is integrated into **Media Player → Bluetooth Audio**.
- Device pairing is intentionally left as a manual Console/SSH operation using `bluetoothctl`.
