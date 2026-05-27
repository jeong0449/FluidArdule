# Networking Guide

Updated: 2026-05-27


This document explains the networking configuration used in Fluid Ardule, focusing on a lightweight and predictable setup.

---

## 1. Overview

Fluid Ardule intentionally avoids NetworkManager in order to keep the system lightweight, deterministic, and easier to debug.

Instead, the recommended networking stack is based on:

- `dhcpcd` (IP management)
- `wpa_supplicant` (Wi-Fi management)
- systemd service control

These components provide reliable automatic Wi-Fi connectivity while remaining compatible with headless embedded operation.

> Note: `dhclient` is not used in this setup, as `dhcpcd` handles DHCP.

---

## 2. Recommended Raspberry Pi OS Approach

Recent Raspberry Pi OS installations commonly use the interface-specific systemd service:

```bash
wpa_supplicant@wlan0.service
```

In this mode, the active configuration file is typically:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

instead of the older traditional file:

```plaintext
/etc/wpa_supplicant/wpa_supplicant.conf
```

Depending on installation history and OS version, both files may exist simultaneously.

Fluid Ardule currently assumes the interface-specific systemd approach because it has proven stable and predictable in headless Raspberry Pi environments.

---

## 3. Determining the Active Wi-Fi Configuration

Check which service is actually active:

```bash
systemctl list-units | grep wpa_supplicant
```

Or:

```bash
ps -ef | grep wpa_supplicant
```

Typical output:

```text
/usr/sbin/wpa_supplicant \
   -c/etc/wpa_supplicant/wpa_supplicant-wlan0.conf \
   -iwlan0
```

This indicates that the system is using:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

as the active Wi-Fi configuration file.

---

## 4. Safe Configuration Generation

Generate network configuration using:

```bash
wpa_passphrase "SSID" "PASSWORD"
```

Copy the generated block into:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

Secure the file:

```bash
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

---

## 5. Wi-Fi Priority Example

Example configuration:

```conf
network={
    ssid="GomTaeng"
    psk=xxxxxxxx
    priority=10
}

network={
    ssid="GenoGlobe"
    psk=xxxxxxxx
    priority=20
}
```

Higher `priority=` values are preferred automatically during boot and reconnection.

This mechanism is heavily used by Fluid Ardule because it provides robust automatic fallback between known networks.

---

## 6. Fluid Ardule Wi-Fi Selector Behavior

Fluid Ardule does not directly manipulate low-level Wi-Fi hardware.

Instead, the Wi-Fi selector:

1. Modifies network priorities
2. Restarts the Wi-Fi service
3. Lets Raspberry Pi OS reconnect automatically

This design intentionally delegates network management to the operating system.

Advantages:

- simpler implementation
- reliable headless operation
- automatic recovery
- compatibility with standard Pi networking behavior

---

## 7. Manual Wi-Fi Bring-Up (Debug / Recovery)

If automatic configuration fails:

```bash
sudo ip link set wlan0 up
sudo wpa_supplicant -B -i wlan0 \
    -c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

This is intended only for:

- debugging
- recovery
- temporary testing

It is not recommended for normal operation because it may interfere with systemd-managed services.

---

## 8. dhcpcd Role

`dhcpcd` assigns IP addresses after Wi-Fi connection.

Ensure:

```bash
sudo systemctl enable dhcpcd
```

---

## 9. Diagnostics

### Quick Network Status

```bash
iwgetid
hostname -I
```

These commands display:

- current connected SSID
- current IP address

For continuously updated status:

```bash
watch -n 1 "iwgetid ; hostname -I"
```

---

### Detailed Wireless Diagnostics

```bash
iw dev wlan0 link
ip a
```

These commands provide:

- signal strength
- frequency/channel
- bitrate
- interface state
- full IP/interface information

---

### Network Scan Diagnostics

```bash
sudo iwlist wlan0 scan | grep ESSID
```

or:

```bash
sudo iw dev wlan0 scan | grep SSID
```

These commands are useful when an access point or hotspot does not appear in the Fluid Ardule Wi-Fi menu.

---

### Wi-Fi Service Status

```bash
systemctl status wpa_supplicant@wlan0
journalctl -u wpa_supplicant@wlan0
```

These commands are useful for diagnosing:

- authentication failures
- reconnection loops
- rfkill issues
- service startup problems
- configuration errors

---

### Notes About `wpa_cli`

Some Raspberry Pi OS configurations using:

```bash
wpa_supplicant@wlan0
```

may not expose a usable `wpa_cli` control socket.

In such environments:

```bash
wpa_cli -i wlan0 status
```

may fail with:

```text
Failed to connect to non-global ctrl_ifname: wlan0
```

Even in this case, Wi-Fi itself may still function normally.

For this reason, Fluid Ardule primarily relies on:

- configuration editing
- priority-based reconnection
- service restart

rather than direct `wpa_cli select_network` control.

---

## 10. Recommended Setup for Fluid Ardule

Recommended:

- `dhcpcd`
- `wpa_supplicant@wlan0`
- interface-specific configuration
- priority-based automatic reconnection

This approach has proven stable for:

- headless Raspberry Pi systems
- embedded musical instruments
- kiosk-style deployments
- automatic recovery after reboot

---

## 11. Summary

- NetworkManager is intentionally avoided
- `dhcpcd` handles IP assignment
- `wpa_supplicant` handles Wi-Fi
- Raspberry Pi OS performs automatic reconnection
- Fluid Ardule acts as a lightweight Wi-Fi front-end
- priority-based reconnect is preferred over direct low-level control
