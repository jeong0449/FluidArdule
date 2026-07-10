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

Users are expected to have basic familiarity with Raspberry Pi OS, SSH, and command-line system administration. The initial Wi-Fi network may be configured using Raspberry Pi Imager so that the Raspberry Pi can be reached during the first stage of installation.

The Fluid Ardule runtime UI intentionally does not provide a general-purpose text entry system for entering arbitrary SSIDs or Wi-Fi passwords. Network configuration is treated as a system administration task rather than a musical performance function.

In the setup described in this guide, NetworkManager is disabled and the final Wi-Fi configuration is created manually for `wpa_supplicant`. Additional known networks are added by editing the `wpa_supplicant` configuration file.

Once configured, Fluid Ardule can select and prioritize known networks through its runtime interface.

This separation is intentional:

- system configuration defines known Wi-Fi networks and credentials
- `wpa_supplicant` handles Wi-Fi association and reconnection
- `dhcpcd` handles IP configuration
- Fluid Ardule manages selection among already configured networks
- the runtime UI remains focused on immediate musical operation

This approach avoids captive portals, temporary access-point modes, on-screen keyboards, and other network provisioning mechanisms that would increase system complexity and maintenance burden.

---

## 3. Current Fluid Ardule Networking Approach

Raspberry Pi OS Bookworm and later use NetworkManager as the default network manager. The Wi-Fi configuration supplied through Raspberry Pi Imager is therefore initially handled by the default Raspberry Pi OS networking stack.

Fluid Ardule replaces NetworkManager with:

- `wpa_supplicant@wlan0.service` for Wi-Fi association
- `dhcpcd.service` for IP configuration

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

Fluid Ardule originally used the traditional `wpa_supplicant.conf` during manual Wi-Fi setup. The interface-specific filename was adopted when Wi-Fi startup was moved to the `wpa_supplicant@wlan0.service` systemd service.

The current setup retains `wpa_supplicant@wlan0.service` and `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` because this arrangement is already used by the Fluid Ardule Wi-Fi management code and has proven stable in the reference system.

---

## 4. Manual NetworkManager Replacement

Before disabling NetworkManager, verify that local console access is available. Disabling the active network manager will interrupt the current Wi-Fi and SSH connection.

Install the required packages if necessary:

```bash
sudo apt update
sudo apt install dhcpcd wpasupplicant
```

Create the interface-specific Wi-Fi configuration file:

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

A minimal example is:

```conf
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=KR

network={
    ssid="YOUR_SSID"
    psk=YOUR_GENERATED_PSK
    priority=10
}
```

Generate the PSK with `wpa_passphrase` rather than manually calculating it:

```bash
wpa_passphrase "YOUR_SSID" "YOUR_PASSWORD"
```

Copy the generated `network={...}` block into `wpa_supplicant-wlan0.conf`.

Secure the configuration file:

```bash
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

Enable the replacement services:

```bash
sudo systemctl enable wpa_supplicant@wlan0.service
sudo systemctl enable dhcpcd.service
```

Then disable NetworkManager:

```bash
sudo systemctl stop NetworkManager.service
sudo systemctl disable NetworkManager.service

# Alternatively, use the following single command:
sudo systemctl disable --now NetworkManager.service
```

Reboot:

```bash
sudo reboot
```

After reboot, verify the active Wi-Fi process:

```bash
systemctl list-units | grep wpa_supplicant
```

and:

```bash
ps -ef | grep '[w]pa_supplicant'
```

Typical output should show a process started with:

```text
/usr/sbin/wpa_supplicant    -c/etc/wpa_supplicant/wpa_supplicant-wlan0.conf    -iwlan0
```

This confirms that the running `wpa_supplicant` process is using:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

For the systemd definition itself, inspect the service template:

```bash
systemctl cat wpa_supplicant@wlan0.service
```

The `ExecStart=` line determines the actual configuration filename. The file used by `wpa_supplicant` is selected by its `-c` option.

Also verify Wi-Fi association and IP configuration:

```bash
iw dev wlan0 link
hostname -I
ip route
```


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

---

## 13. Future Idea: Migrating NetworkManager Wi-Fi Profiles

The manual configuration described in this guide is simple and explicit, but entering SSIDs and passwords again can be inconvenient, especially on a small console-only system.

A possible future improvement is to use NetworkManager only during initial Wi-Fi provisioning and then migrate its saved connection information to the Fluid Ardule `wpa_supplicant` configuration.

A possible workflow is:

1. Configure the primary Wi-Fi network with Raspberry Pi Imager.
2. Boot Raspberry Pi OS with NetworkManager still active.
3. Add other required networks, such as a mobile hotspot, using `nmcli` or `nmtui`.
4. Set the desired NetworkManager autoconnect priorities.
5. Run a Fluid Ardule migration script.
6. Generate `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` from the saved NetworkManager profiles.
7. Disable NetworkManager.
8. Enable `wpa_supplicant@wlan0.service` and `dhcpcd.service`.
9. Reboot and verify Wi-Fi association and IP configuration.

Conceptually:

```text
Raspberry Pi Imager / nmcli / nmtui
                 |
                 v
NetworkManager connection profiles
                 |
                 |  migration script
                 v
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
                 |
                 v
wpa_supplicant@wlan0.service + dhcpcd.service
```

NetworkManager system connection profiles are normally stored under:

```plaintext
/etc/NetworkManager/system-connections/
```

A migration script could read the relevant Wi-Fi properties, such as:

```text
802-11-wireless.ssid
802-11-wireless-security.key-mgmt
802-11-wireless-security.psk
connection.autoconnect
connection.autoconnect-priority
```

and convert supported profiles into `wpa_supplicant` `network={...}` blocks.

For example, relative NetworkManager priorities could be preserved as `wpa_supplicant` priorities:

```conf
network={
    ssid="HomeWiFi"
    psk=...
    priority=20
}

network={
    ssid="PhoneHotspot"
    psk=...
    priority=10
}
```

Only the relative ordering of priority values is important for this use case.

### Limitations and safety considerations

Such a migration tool should initially support only simple, known configurations, such as WPA/WPA2 personal networks using a pre-shared key.

It should explicitly detect or reject unsupported configurations rather than silently generating an incorrect Wi-Fi setup. Examples include:

- enterprise authentication (802.1X / EAP)
- externally managed secrets
- unsupported WPA3-only settings
- unusual hidden-network configurations
- manually configured static IP settings

The script should also:

- back up the existing `wpa_supplicant` configuration
- write the new configuration to a temporary file first
- validate that required fields are present
- apply restrictive file permissions
- avoid disabling NetworkManager until conversion succeeds
- clearly report which profiles were migrated or skipped

This migration approach is **not currently part of the required Fluid Ardule installation procedure**. It is a possible future convenience feature intended to simplify Wi-Fi provisioning while retaining the lightweight `wpa_supplicant` and `dhcpcd` runtime stack.

