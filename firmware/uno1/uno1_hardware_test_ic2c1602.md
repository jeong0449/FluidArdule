# UNO-1 Hardware Test Firmware Guide

## Overview
This firmware is designed to verify hardware inputs and basic functionality of the UNO-1 controller used in the Fluid Ardule system.

It focuses on:
- Keypad (analog ladder)
- Rotary encoder (A/B + push switch)
- Potentiometer
- LCD display
- Basic input event detection

---

## Hardware Mapping

| Pin | Function |
|-----|----------|
| A0  | Keypad (analog ladder) |
| A1  | Encoder switch (digital) |
| A2  | Potentiometer |
| D2  | Encoder A |
| D3  | Encoder B |

---

## LCD Layout

### Line 1: Event Display
Shows recent user actions:
- `ENC +1`, `ENC -2`
- `BTN SHORT`, `BTN LONG`
- `KEY UP`, `KEY DOWN`, etc.

### Line 2: State Display
Shows current values:
- `P:xxx` → Potentiometer value
- `E:x` → Encoder accumulated value
- `G:x` → Gain / acceleration level

---

## Encoder Behavior

- Uses **state transition decoding**
- Eliminates jitter and reverse-step glitches
- One detent = one step

### Acceleration (Gain)
- Long press encoder button
- Rotate encoder to adjust gain level

---

## Button Behavior

| Action | Result |
|--------|--------|
| Short press | `BTN SHORT` event |
| Long press | `BTN LONG` event |

---

## Test Procedure

1. Rotate encoder → check `ENC` events
2. Press encoder → check SHORT/LONG events
3. Turn potentiometer → verify `P:` changes
4. Press keypad → verify KEY events
5. Check LCD updates correctly

---

## Notes

- Line 1 = event-based (temporary)
- Line 2 = continuous state
- Designed for debugging clarity
