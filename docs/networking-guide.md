# Networking Guide

This document explains the networking configuration used in Fluid Ardule, focusing on a lightweight and predictable setup.

---

## 1. Overview

Fluid Ardule avoids NetworkManager to keep the system lightweight and easier to debug.

Instead, it uses:

- `dhcpcd` (IP management)
- `wpa_supplicant` (Wi-Fi)

These components must be properly configured to enable reliable automatic Wi-Fi connectivity.

> Note: `dhclient` is not used in this setup, as `dhcpcd` handles DHCP.

---

## 2. Recommended Raspberry Pi OS Approach (Default)

The simplest and most stable configuration on Raspberry Pi OS is:

- `dhcpcd` enabled
- `/etc/wpa_supplicant/wpa_supplicant.conf` configured

In this mode:

- `dhcpcd` automatically invokes `wpa_supplicant`
- Wi-Fi connects automatically at boot

---

## 3. Manual Wi-Fi Bring-Up (Debug / Recovery)

If automatic configuration fails:

```bash
sudo ip link set wlan0 up
sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
```

- Useful for testing
- Not persistent
- May interfere with systemd services

> Warning: Avoid mixing manual execution with systemd unless debugging.

---

## 4. Safe Configuration Generation

Generate config using:

```bash
wpa_passphrase "SSID" "PASSWORD"
```

Copy output into:

```plaintext
/etc/wpa_supplicant/wpa_supplicant.conf
```

Secure it:

```bash
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
```

---

## 5. systemd-Based Wi-Fi (Alternative)

You may use:

```bash
sudo systemctl enable wpa_supplicant@wlan0
```

This requires:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

Create it if needed:

```bash
sudo cp /etc/wpa_supplicant/wpa_supplicant.conf         /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

> Note: Some systems may still work with the default config file depending on overrides.

---

## 6. dhcpcd Role

`dhcpcd` assigns IP addresses after Wi-Fi connection.

Ensure:

```bash
sudo systemctl enable dhcpcd
```

---

## 7. Diagnostics

```bash
iw dev wlan0 link
ip a
systemctl status wpa_supplicant@wlan0
journalctl -u wpa_supplicant@wlan0
```

---

## 8. Recommended Setup for Fluid Ardule

For stability:

- Use **dhcpcd + wpa_supplicant.conf** (default Pi method)

OR (advanced):

- Use **wpa_supplicant@wlan0 + wlan0-specific config**

---

## 9. Summary

- NetworkManager is avoided intentionally
- dhcpcd handles IP
- wpa_supplicant handles Wi-Fi
- manual mode = debugging
- systemd mode = automation (optional)
