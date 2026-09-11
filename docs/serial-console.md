# Fluid Ardule Serial Console Access

This document describes how to access the Raspberry Pi serial console
using a CP2102-based USB-to-TTL serial converter from a Windows PC.

The serial console provides a simple recovery path when Wi-Fi or other
network access is unavailable. It is also useful for inspecting boot
messages and diagnosing Fluid Ardule when the graphical display or main
application does not respond normally.

## Hardware

-   CP2102-based USB-to-TTL serial converter
-   USB cable
-   Three serial connections between the converter and Raspberry Pi:
    -   CP2102 **TX** → Raspberry Pi **RX**
    -   CP2102 **RX** → Raspberry Pi **TX**
    -   CP2102 **GND** → Raspberry Pi **GND**

> \[!CAUTION\] Use **3.3 V TTL logic** for the Raspberry Pi UART. Do not
> connect the converter's 5 V power output to the Raspberry Pi UART
> pins.

## Windows Driver

Install the Silicon Labs CP210x Virtual COM Port (VCP) driver if Windows
does not recognize the converter automatically:

https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers?tab=downloads

After installation, reconnect the CP2102 module.

## Find the COM Port with PowerShell

Connect the CP2102 module to the Windows PC and open PowerShell.

Run:

``` powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description
```

The converter should appear similar to:

``` text
DeviceID  Description
--------  -----------
COM5      Silicon Labs CP210x USB to UART Bridge
```

In this example, the serial port is `COM5`.

If several serial devices are listed, unplug the CP2102, run the command
again, then reconnect it. The COM port that disappears and reappears is
the CP2102.

## Connect with PuTTY

Open PuTTY and select **Serial** as the connection type.

Use the following settings:

  Setting        Value
  -------------- -----------------------------------
  Serial line    COM port found above, e.g. `COM5`
  Speed          `115200`
  Data bits      `8`
  Stop bits      `1`
  Parity         `None`
  Flow control   `None`

Click **Open** to start the serial terminal.

If the terminal window is blank even though the Raspberry Pi is running,
press **Enter** once or twice. A login prompt should appear if the
serial console is enabled and configured correctly.

## Using the Console for Recovery

After logging in, the serial console behaves like a normal Linux
terminal.

For example, the following commands are useful when Fluid Ardule appears
to be frozen or unresponsive:

``` bash
uptime
top
systemctl status fluid_ardule.service
journalctl -u fluid_ardule.service -b --no-pager
ps aux | grep -E 'fluid|python'
dmesg | tail -50
```

These commands can help distinguish between:

-   a graphical display problem,
-   a stopped or failed Fluid Ardule service,
-   excessive CPU or system load,
-   and a broader Raspberry Pi or operating-system problem.

> \[!NOTE\] The serial connection is intended primarily as a maintenance
> and recovery interface. Keeping it available provides access to the
> Raspberry Pi even when normal network-based administration is not
> possible.
