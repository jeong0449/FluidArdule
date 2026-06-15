# Power Distribution and Undervoltage Troubleshooting

## Background

During development of Fluid Ardule on Raspberry Pi 3B, occasional

```text
Undervoltage detected!
```

warnings were observed when multiple USB peripherals were connected simultaneously.

Typical USB peripherals include:

- USB DAC
- USB MIDI interfaces
- USB flash drives
- Wi‑Fi networking devices

While the system remained operational, the warning indicated that the Raspberry Pi power rail was occasionally dropping below the recommended voltage.

---

## USB Peripheral Power Injection Adapter

To reduce current flowing through the Raspberry Pi USB power path, a simple USB power injection adapter was developed.

The adapter preserves:

- D+
- D-
- GND

while VBUS is supplied directly from the system's Mean Well LRS-50-5 5V power supply.

### USB Peripheral Power Injection Adapter

![USB Peripheral Power Injection Adapter](images/2026-06-15-usb-power-injection-adapter.png)

**Upper:** Electrical concept of the adapter. VBUS from the Raspberry Pi USB port is disconnected, while D+, D−, and GND remain connected. A regulated 5V supply from the system Mean Well LRS-50-5 SMPS is injected directly into the USB peripheral side.

**Lower:** Actual adapter used in Fluid Ardule. The adapter provides two externally powered USB device connections. One branch is permanently connected to the UNO-1 hardware controller, while the second branch is available for additional peripherals such as USB DACs, MIDI interfaces, or USB storage devices.

---

## Principle of Operation

The Raspberry Pi continues to function as the USB host.

Only the peripheral-side VBUS connection is powered externally.

```text
Raspberry Pi USB Host
        │
   D+, D-, GND
        │
        ▼
   USB Peripheral

VBUS supplied directly from
Mean Well LRS-50-5
```

This arrangement reduces current flowing through the Raspberry Pi USB power path while preserving normal USB communication.

---

## Results

Observed results:

- Reduced USB bus loading
- Improved stability when multiple USB peripherals are attached
- Reduced frequency of undervoltage warnings

However:

- Undervoltage warnings have not been completely eliminated
- Remaining voltage drops may originate from power wiring, connectors, transient loads, or other parts of the system

Therefore this adapter should be viewed as a mitigation measure rather than a complete solution.

---

## Diagnosing Undervoltage Events

Raspberry Pi provides a built-in diagnostic command:

```bash
vcgencmd get_throttled
```

Typical output:

```text
throttled=0x0
```

means that no undervoltage or thermal throttling events have occurred.

Common values include:

```text
0x0      No issues detected
0x1      Undervoltage currently active
0x50000  Undervoltage occurred in the past
```

To clear the history, reboot the Raspberry Pi and repeat the test.

This command is useful when evaluating:

- Power wiring changes
- USB peripheral additions
- SMPS voltage adjustments
- New hardware configurations

---

## Limitations

This adapter is intended only for USB peripherals connected to the Raspberry Pi host.

It is not intended for:

- Connection to PCs
- General-purpose USB power sharing
- Unknown power topologies

Use only when the complete system power distribution is understood.

---

## Future Investigation

Potential remaining sources of undervoltage warnings include:

- Raspberry Pi power wiring resistance
- Connector contact resistance
- Peak transient current demand
- SMPS output voltage adjustment
- Ground return path losses
