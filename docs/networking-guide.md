# Networking Guide

Updated: 2026-07-10


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

## 2. Design Scope and User Expectations

Fluid Ardule is designed as a DIY embedded musical instrument, not as a general-purpose consumer device.

Users are expected to have basic familiarity with Raspberry Pi OS and SSH. The initial Wi-Fi network should normally be configured using Raspberry Pi Imager when the OS image is prepared.

The Fluid Ardule runtime UI intentionally does not provide a general-purpose text entry system for entering arbitrary SSIDs or Wi-Fi passwords. Network configuration is considered a system administration task rather than a musical performance function.

Additional Wi-Fi networks may initially be added while NetworkManager is still available, for example with `nmcli` or `nmtui`. Their saved connection profiles can then be migrated to the Fluid Ardule `wpa_supplicant` configuration before NetworkManager is disabled.

Once the known networks have been migrated, Fluid Ardule can select and prioritize them through its runtime interface.

This separation is intentional:

- Raspberry Pi OS handles network configuration.
- Fluid Ardule manages selection among already configured networks.
- The runtime UI remains focused on immediate musical operation.

This approach avoids captive portals, temporary access-point modes, on-screen keyboards, and other network provisioning mechanisms that would increase system complexity and maintenance burden.

---

## 3. Current Fluid Ardule Networking Approach

Raspberry Pi OS Bookworm and later use NetworkManager as the default network manager. Fluid Ardule replaces that default stack with `dhcpcd` and `wpa_supplicant` to reduce unnecessary service overhead and keep networking simple.

The current Fluid Ardule system uses the interface-specific systemd service:

```bash
wpa_supplicant@wlan0.service
```

The Debian systemd template for this service starts `wpa_supplicant` with an interface-specific configuration file. For the `wlan0` instance, the expected file is:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

The `-wlan0` filename is **not a Raspberry Pi OS release convention** and is not a newer replacement for:

```plaintext
/etc/wpa_supplicant/wpa_supplicant.conf
```

`wpa_supplicant` itself does not require one universal configuration filename. The active file is determined by the `-c` option used when the process is started.

Fluid Ardule originally used the traditional `wpa_supplicant.conf` during manual Wi-Fi setup. The interface-specific filename was adopted when Wi-Fi startup was moved to the `wpa_supplicant@wlan0.service` systemd service, whose template expects a configuration file corresponding to the interface instance.

The current setup retains `wpa_supplicant@wlan0.service` and `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` because this arrangement is already used by the Fluid Ardule Wi-Fi management code and has proven stable in the reference system. A different `wpa_supplicant` startup method could use a different configuration filename.

---

## 4. Determining the Active Wi-Fi Configuration

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

This indicates that the running `wpa_supplicant` process was explicitly started with:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

as its configuration file.

For the systemd definition itself, inspect the service template:

```bash
systemctl cat wpa_supplicant@wlan0.service
```

The `ExecStart=` line determines the actual configuration filename. The file used by `wpa_supplicant` is selected by its `-c` option; the program does not require one universal configuration filename.

---

## 5. Safe Configuration Generation

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

## 6. Wi-Fi Priority Example

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

## 7. Fluid Ardule Wi-Fi Selector Behavior

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

## 8. Manual Wi-Fi Bring-Up (Debug / Recovery)

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

## 9. dhcpcd Role

`dhcpcd` manages IPv4/IPv6 network configuration after the Wi-Fi link has been established. In the normal Fluid Ardule setup, it obtains the IP address, default route, and DNS information by DHCP.

Ensure:

```bash
sudo systemctl enable dhcpcd
```

---

## 10. Diagnostics

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

## 11. Recommended Setup for Fluid Ardule

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

## 12. Summary

- NetworkManager is intentionally avoided
- `dhcpcd` handles IP assignment
- `wpa_supplicant` handles Wi-Fi
- Raspberry Pi OS performs automatic reconnection
- Fluid Ardule acts as a lightweight Wi-Fi front-end
- priority-based reconnect is preferred over direct low-level control
