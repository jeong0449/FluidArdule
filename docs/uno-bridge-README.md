# UNO MIDI Bridge

## Overview

The UNO MIDI Bridge is a small C program that connects an Arduino-based MIDI interface (UNO-2) to the Linux ALSA MIDI system.

It reads MIDI data from the Arduino via USB serial and exposes it as an ALSA sequencer (SEQ) port.
This allows applications such as FluidSynth or Yoshimi to receive MIDI input seamlessly.

---

## Design Philosophy

Fluid Ardule follows a strict principle:

> **Device detection does not imply automatic selection.**

Accordingly:

* The UNO-2 bridge is **optional**
* It is **never auto-selected**
* It is only activated when explicitly chosen in the UI

---

## Device Identification

### UNO-2 Detection

The bridge identifies the correct Arduino device using a **stable USB device ID path**:

```bash
/dev/serial/by-id/...
```

This ensures:

* Reliable detection across reboots
* Immunity to `/dev/ttyACM*` renumbering
* No accidental selection of other serial devices

### Why Not Auto-Scan?

The bridge does **not** select “any available serial device”.

```text
Incorrect approach:
→ pick first /dev/ttyACM*

Correct approach:
→ match a known device ID
```

This prevents conflicts with:

* UNO-1 (UI controller)
* Other USB serial devices
* Debug adapters

---

## System Architecture

```text
UNO-2 (Arduino MIDI bridge)
    ↓ USB Serial (by-id)
uno_midi_bridge (C program)
    ↓ ALSA SEQ
"UNO-bridge" virtual MIDI port
    ↓
FluidSynth / Yoshimi
```

### Important Note

The Python UI script does **not** directly access UNO-2.

Instead:

```text
Python → launches bridge
Bridge → handles serial
Python → connects to ALSA port
```

---

## Interaction with UI

The UNO-2 bridge is only used when selected:

```text
MIDI Mode:
- USB direct
- ALSA MIDI
- UNO-2 bridge   ← only here
```

Behavior:

* If not selected → bridge is not used
* If selected → bridge is launched
* If device is missing → system remains stable (no crash)

---

## ALSA Port Naming

The bridge creates a virtual MIDI port, typically named:

```text
UNO-bridge
```

The Python UI searches for this port when in UNO-2 bridge mode.

---

## Failure Handling

If UNO-2 is:

* unplugged
* powered off
* not present

then:

```text
Bridge fails silently or exits
→ UI remains functional
→ no automatic fallback occurs
```

This follows the design rule:

> **Optional devices must not disrupt the system.**

---

## Summary

```text
UNO-1 → mandatory UI controller (handled by Python)
UNO-2 → optional MIDI source (handled by bridge)
```

Key points:

* Uses `/dev/serial/by-id/` for stable identification
* Never auto-selects devices
* Integrates via ALSA SEQ
* Activated only through explicit user choice

---

## Future Considerations

Possible enhancements:

* Multiple bridge instances (multi-device support)
* Dynamic port naming
* Status feedback to UI

---

## License

Same as the main Fluid Ardule project.
