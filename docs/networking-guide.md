# Networking Guide

Updated: 2026-07-10


This document explains the networking configuration used in Fluid Ardule, focusing on a lightweight and predictable setup.

> **Quick setup:** If you only want to replace NetworkManager with the simplified Fluid Ardule networking stack and do not need the background explanation, skip directly to [Section 4. Manual NetworkManager Replacement](#4-manual-networkmanager-replacement). Sections 1–3 explain the design rationale, the networking state of a fresh Raspberry Pi OS installation, and why Fluid Ardule uses `wpa_supplicant@wlan0.service`.

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

## 3. From a Fresh Raspberry Pi OS Installation to the Fluid Ardule Stack

### 3.1 Fresh installation state

Raspberry Pi OS Bookworm and later use NetworkManager as the default network manager. When the initial Wi-Fi network is configured with Raspberry Pi Imager, a freshly installed system may show the following state:

```bash
systemctl is-active NetworkManager
```

Example:

```text
active
```

The active `wpa_supplicant` unit may appear as:

```bash
systemctl list-units | grep wpa_supplicant
```

Example:

```text
wpa_supplicant.service    loaded active running    WPA supplicant
```

The running process may look like:

```text
/usr/sbin/wpa_supplicant -u -s -O DIR=/run/wpa_supplicant GROUP=netdev
```

This process has neither `-i wlan0` nor a `-c` configuration-file option. It is the global D-Bus-enabled `wpa_supplicant` daemon used by NetworkManager, not an interface-specific `wpa_supplicant@wlan0.service` instance.

The NetworkManager view can be checked with:

```bash
nmcli device status
```

On a reference fresh installation configured by Raspberry Pi Imager, the Wi-Fi connection appeared as:

```text
DEVICE         TYPE      STATE                   CONNECTION
wlan0          wifi      connected               netplan-wlan0-GomTaeng
lo             loopback  connected (externally)  lo
p2p-dev-wlan0  wifi-p2p  disconnected            --
eth0           ethernet  unavailable             --
```

The connection name `netplan-wlan0-GomTaeng` shows that the initial Wi-Fi configuration has entered the default Raspberry Pi OS networking stack and is being managed by NetworkManager.

Conceptually, the fresh installation is:

```text
Raspberry Pi Imager
        |
        v
initial network configuration
        |
        v
NetworkManager
        |
        | D-Bus
        v
wpa_supplicant.service
        |
        v
      wlan0
```

At this stage, neither:

```plaintext
/etc/wpa_supplicant/wpa_supplicant.conf
```

nor:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

should be assumed to be the active Wi-Fi configuration merely because the file exists. The running `wpa_supplicant` process has no `-c` option selecting either file.

### 3.2 Why Fluid Ardule moved to `wpa_supplicant@wlan0.service`

Fluid Ardule intentionally replaces the default NetworkManager-based arrangement with a smaller and more explicit runtime stack.

The present design originated from a practical bring-up sequence. After moving away from NetworkManager, Wi-Fi association could be established manually with an explicit command of the following form:

```bash
sudo wpa_supplicant -B -i wlan0 \
    -c /etc/wpa_supplicant/wpa_supplicant.conf
```

This demonstrated that:

* the wireless interface `wlan0` was usable
* `wpa_supplicant` itself was working
* the Wi-Fi configuration was valid
* the remaining problem was automatic startup and service management

The next requirement was therefore to reproduce the successful interface-specific manual command automatically during boot.

For this purpose, Fluid Ardule adopted the systemd instance service:

```bash
wpa_supplicant@wlan0.service
```

The relationship between the service instance, the wireless interface, and the configuration filename can be verified directly by inspecting the service template:

```bash
systemctl cat wpa_supplicant@wlan0.service
```

The relevant part of the systemd unit is:

```ini
# NetworkManager users will probably want the dbus version instead.

[Service]
Type=simple
ExecStart=/usr/sbin/wpa_supplicant -c/etc/wpa_supplicant/wpa_supplicant-%I.conf -i%I
ExecReload=/bin/kill -HUP $MAINPID
```

In a systemd template unit, `%I` is replaced by the instance name. Therefore, starting:

```bash
wpa_supplicant@wlan0.service
```

causes the `ExecStart` command to resolve effectively to:

```bash
/usr/sbin/wpa_supplicant \
    -c/etc/wpa_supplicant/wpa_supplicant-wlan0.conf \
    -iwlan0
```

This closely matches the manually verified Wi-Fi setup: `wpa_supplicant` is started explicitly for `wlan0` and is given an explicit configuration file.

The `wlan0` instance was therefore selected because the successful manual command had already established that Wi-Fi association worked when `wpa_supplicant` operated directly on:

```text
-i wlan0
```

Once `wpa_supplicant@wlan0.service` was selected, the interface-specific configuration filename followed directly from the systemd service template:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

Conceptually:

```text
successful manual test
wpa_supplicant -i wlan0 -c wpa_supplicant.conf
                    |
                    v
need automatic startup at boot
                    |
                    v
choose interface-specific systemd service
                    |
                    v
wpa_supplicant@wlan0.service
                    |
                    |  %I = wlan0
                    v
-iwlan0
-c/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

The service template also explicitly notes that NetworkManager users will normally want the D-Bus version of `wpa_supplicant`. This is consistent with the freshly installed Raspberry Pi OS system described in the previous section, where NetworkManager uses the global `wpa_supplicant.service` process started with the `-u` option.

Therefore, the `-wlan0` filename was not chosen because Raspberry Pi OS introduced a newer configuration-file convention. It appeared as a direct consequence of choosing the interface-specific `wpa_supplicant@wlan0.service` that matched the previously verified manual `-i wlan0` setup.

`wpa_supplicant` itself does not require one universal configuration filename. The active file is determined by the `-c` option used when the process is started.


### 3.3 Current Fluid Ardule target stack

Fluid Ardule replaces NetworkManager with:

- `wpa_supplicant@wlan0.service` for Wi-Fi association
- `dhcpcd.service` for IP configuration

The resulting arrangement is:

```text
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
                    |
                    v
wpa_supplicant@wlan0.service
                    |
                    v
                  wlan0
                    |
                    v
              dhcpcd.service
                    |
                    v
          IP address / route / DNS
```

The current setup retains `wpa_supplicant@wlan0.service` and `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` because this arrangement is already used by the Fluid Ardule Wi-Fi management code and has proven stable in the reference system.


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

The fresh Raspberry Pi OS installation may already have the global D-Bus-managed `wpa_supplicant.service` active under NetworkManager. The target Fluid Ardule configuration instead uses the interface-specific `wpa_supplicant@wlan0.service`.

Before changing services, remember that disabling NetworkManager will interrupt the current Wi-Fi and SSH connection.

Disable NetworkManager and the global `wpa_supplicant` service:

```bash
sudo systemctl disable --now NetworkManager.service
sudo systemctl disable --now wpa_supplicant.service
```

Then enable the Fluid Ardule replacement services:

```bash
sudo systemctl enable wpa_supplicant@wlan0.service
sudo systemctl enable dhcpcd.service
```

The explicit disabling of `wpa_supplicant.service` avoids leaving the global D-Bus-managed daemon active alongside the interface-specific `wpa_supplicant@wlan0.service`.

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

`dhcpcd.service` is enabled as part of the NetworkManager replacement procedure described in Section 4.

Its current state can be verified with:

```bash
systemctl is-enabled dhcpcd.service
systemctl is-active dhcpcd.service
```

---

## 10. Network Diagnostics

### Quick Connection Check

Check the currently connected Wi-Fi network and assigned IP address:

```bash
iwgetid
hostname -I
```

Example:

```text
wlan0    ESSID:"GomTaeng"
192.168.0.123
```

This confirms that `wlan0` is associated with a Wi-Fi network and has received an IP address.

### Detailed Network Status

For more detailed wireless and routing information:

```bash
iw dev wlan0 link
ip route
```

Example:

```text
Connected to aa:bb:cc:dd:ee:ff (on wlan0)
        SSID: GomTaeng
        freq: 5180
        signal: -42 dBm

default via 192.168.0.1 dev wlan0
192.168.0.0/24 dev wlan0 scope link
```

The important points are the connected SSID, signal level, and the presence of a default route through `wlan0`.

### Scan for Nearby Wi-Fi Networks

To check whether a wireless network is visible:

```bash
sudo iw dev wlan0 scan | grep SSID
```

Example:

```text
SSID: GomTaeng
SSID: GenoGlobe
SSID: PhoneHotspot
```

This is useful when an expected network does not appear in the Fluid Ardule Wi-Fi menu.

### Wi-Fi Service Status and Logs

Check the interface-specific `wpa_supplicant` service:

```bash
systemctl status wpa_supplicant@wlan0.service
```

A normally running service should include:

```text
Active: active (running)
```

For startup or reconnection problems, inspect the service log:

```bash
journalctl -u wpa_supplicant@wlan0.service
```

These commands are usually sufficient to determine whether a problem is related to Wi-Fi association, IP configuration, or service startup.


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

- A fresh Raspberry Pi OS installation uses NetworkManager and the global D-Bus-enabled `wpa_supplicant.service`
- Raspberry Pi Imager Wi-Fi configuration may appear in NetworkManager as a `netplan-wlan0-...` connection
- Fluid Ardule intentionally replaces the default NetworkManager-based stack
- `wpa_supplicant@wlan0.service` was chosen to automate a manually verified `wpa_supplicant -i wlan0` Wi-Fi setup
- `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` follows from the interface-specific systemd service template
- `dhcpcd` handles IP assignment
- Fluid Ardule acts as a lightweight front-end for selecting among already configured Wi-Fi networks
- priority-based reconnection is preferred over direct low-level control

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

