# Serial Console Access

Fluid Ardule provides a serial console as a recovery and diagnostic
interface. It is useful when Wi-Fi is unavailable or when the main
application or display does not respond normally.

## Hardware Connection

Connect the CP2102 USB-to-TTL serial converter to the Raspberry Pi as shown in the [Fluid Ardule system wiring diagram](../images/fluid-ardule-system-wiring-diagram.png).

## Windows Driver

If necessary, install the [Silicon Labs CP210x VCP
driver](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers?tab=downloads).

## Find the COM Port

Connect the CP2102 module and open PowerShell:

``` powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description
```

Example:

``` text
DeviceID  Description
--------  -----------
COM5      Silicon Labs CP210x USB to UART Bridge
```

In this example, use `COM5`.

> \[!TIP\] If several COM ports are listed, unplug and reconnect the
> CP2102. The port that disappears and reappears is the one to use.

## Connect with PuTTY

Open **PuTTY** and select **Serial**.

Set:

-   **Serial line:** the COM port found above, e.g. `COM5`
-   **Speed:** `115200`

The remaining serial settings can normally be left at their defaults.

Click **Open**. If the terminal is blank, press **Enter** once or twice
to display the login prompt.

## Recovery and Diagnostics

After logging in, the serial console behaves like a normal Linux
terminal.

Useful commands include:

``` bash
uptime
top
systemctl status fluid_ardule.service
journalctl -u fluid_ardule.service -b --no-pager
ps aux | grep -E 'fluid|python'
dmesg | tail -50
```

> \[!NOTE\] The serial console is primarily a maintenance and recovery
> interface. It provides direct access to the Raspberry Pi even when
> network-based administration is unavailable.
