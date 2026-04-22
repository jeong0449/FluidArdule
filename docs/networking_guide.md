# Networking Guide

This document explains the networking configuration used in Fluid Ardule, with a focus on a lightweight and predictable setup based on `dhcpcd` and `wpa_supplicant` instead of NetworkManager.

---

## 1. Overview

Fluid Ardule avoids NetworkManager in order to keep the system lightweight, transparent, and easier to debug in an embedded/headless environment.

Instead, it uses:

- `dhcpcd` for IP address management
- `wpa_supplicant` for Wi-Fi authentication and association

These components must be properly configured to enable reliable automatic Wi-Fi connectivity.

---

## 2. Basic Wi-Fi Configuration

Edit the main Wi-Fi configuration file:

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

A minimal example:

```plaintext
country=KR
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="YOUR_SSID"
    psk="YOUR_PASSWORD"
}
```

Apply changes without rebooting:

```bash
sudo wpa_cli -i wlan0 reconfigure
```

This command tells `wpa_supplicant` to reload its configuration and attempt reconnection using the updated settings.

---

## 3. Manual Wi-Fi Bring-Up

If automatic Wi-Fi configuration is not working as expected, you can manually bring up the interface:

```bash
sudo ip link set wlan0 up
sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
```

If `dhcpcd` is already running, an IP address will usually be assigned automatically after association.

This method is useful for testing and recovery, but it is not ideal as a long-term boot-time solution.

---

## 4. Generating wpa_supplicant.conf Safely

To avoid storing the Wi-Fi password in plain text and to reduce configuration errors, it is recommended to generate the configuration using `wpa_passphrase`.

Generate a network block:

```bash
wpa_passphrase "SSID" "PASSWORD"
```

This will output something like:

```plaintext
network={
    ssid="SSID"
    #psk="PASSWORD"
    psk=HASHED_VALUE
}
```

Copy the generated `network` block into the configuration file:

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

Example:

```plaintext
country=KR
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="SSID"
    psk=HASHED_VALUE
}
```

It is recommended to remove or comment out the plain-text `psk="PASSWORD"` line.

To protect the configuration file:

```bash
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
```

> Note: The hashed PSK is more secure than plain text, but it is not fully encrypted and should still be handled with care.

---

## 5. Manual vs systemd-based Wi-Fi Setup

There are two main ways to use `wpa_supplicant`.

### 5.1 Manual execution

You can run `wpa_supplicant` directly:

```bash
sudo ip link set wlan0 up
sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
```

Characteristics:

- Direct and explicit
- Useful for debugging
- Uses `/etc/wpa_supplicant/wpa_supplicant.conf`
- Does not automatically survive reboot unless scripted separately

### 5.2 systemd-based execution

You can also use the systemd interface-specific service:

```bash
sudo systemctl enable wpa_supplicant@wlan0
sudo systemctl start wpa_supplicant@wlan0
```

Characteristics:

- Starts automatically at boot
- Uses the `wpa_supplicant@.service` template
- Better for stable headless operation

---

## 6. Why systemd May Fail Even When Manual Start Works

A common source of confusion is that manual execution and systemd-based execution do **not** use the same configuration file name.

### Manual execution uses:

```plaintext
/etc/wpa_supplicant/wpa_supplicant.conf
```

### systemd (`wpa_supplicant@wlan0`) typically expects:

```plaintext
/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

As a result:

- manual execution may work
- `wpa_supplicant@wlan0.service` may fail

This usually appears in logs as a configuration file open/parse failure.

---

## 7. Fixing systemd Wi-Fi Startup

If manual Wi-Fi works but `wpa_supplicant@wlan0` fails, copy the default configuration to the interface-specific name:

```bash
sudo cp /etc/wpa_supplicant/wpa_supplicant.conf \
        /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

Set secure permissions:

```bash
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

Then enable and start the service:

```bash
sudo systemctl enable wpa_supplicant@wlan0
sudo systemctl start wpa_supplicant@wlan0
```

Check status:

```bash
systemctl status wpa_supplicant@wlan0
```

If successful, the service should remain active after reboot.

---

## 8. Relationship Between `wpa_supplicant`, `wpa_supplicant@wlan0`, and `dhcpcd`

These are related but have different roles.

### `wpa_supplicant`
Handles Wi-Fi authentication and association.

### `wpa_supplicant@wlan0`
A systemd-managed, interface-specific way to run `wpa_supplicant` automatically for `wlan0`.

### `dhcpcd`
Handles DHCP and IP assignment after the Wi-Fi link is established.

In short:

- `wpa_supplicant` connects to Wi-Fi
- `dhcpcd` gets the IP address

Wi-Fi association alone does **not** assign an IP address.

Ensure `dhcpcd` is enabled:

```bash
sudo systemctl enable dhcpcd
sudo systemctl start dhcpcd
```

---

## 9. Useful Diagnostic Commands

Check link state:

```bash
iw dev wlan0 link
```

Check interface addresses:

```bash
ip a show wlan0
```

Check Wi-Fi service status:

```bash
systemctl status wpa_supplicant@wlan0
```

Check logs:

```bash
journalctl -u wpa_supplicant@wlan0 -n 50
```

Check whether `dhcpcd` is running:

```bash
systemctl status dhcpcd
```

Check whether the interface got an IP address:

```bash
ip a
```

---

## 10. Recommended Practice for Fluid Ardule

For Fluid Ardule, the most stable arrangement is:

- `dhcpcd` enabled
- `wpa_supplicant@wlan0` enabled
- `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` present

This provides:

- automatic Wi-Fi connection at boot
- predictable behavior
- easy debugging through systemd and journal logs

---

## 11. Summary

- NetworkManager is intentionally avoided
- `dhcpcd` manages IP assignment
- `wpa_supplicant` manages Wi-Fi authentication
- manual execution is useful for recovery and debugging
- systemd is better for automatic boot-time connection
- when using `wpa_supplicant@wlan0`, an interface-specific configuration file may be required
- copying `wpa_supplicant.conf` to `wpa_supplicant-wlan0.conf` resolves a common startup issue
