# UNO-1 ↔ Raspberry Pi Serial Protocol
*(Fluid Ardule Project)*

**Version: 20260429a (UI-aware extension)**  
**Updated: 2026-04-29**

---

## 1. Overview

UNO-1 and Raspberry Pi communicate via USB serial (CDC) using a line-based ASCII protocol.

- Baud rate: 115200  
- Encoding: ASCII  
- Framing: 1 message per line (`\n`)

---

## 2. Core Concept Update

Previous limitation:
- LINK OK only meant "Pi is alive"
- Did NOT guarantee UI responsiveness

### New model:

- LINK = connection alive (HELLO / HB)
- UI   = input processing availability
- ACK  = input received confirmation

---

## 3. State Model

```
LINK OK  = HELLO / HB received
UI OK    = UI:READY received
UI BUSY  = UI:BUSY received
WAIT PI  = no HELLO/HB
```

---

## 4. Message Format

```
TYPE:VALUE
```

Standalone:
```
UNO_READY
HELLO
HB
```

---

## 5. UNO → Pi Messages

```
UNO_READY

BTN:LEFT / RIGHT / UP / DOWN / SEL / ENC_PUSH
BTN:LEFT_LP / ... / SEL_LP

ENC:+N
ENC:-N

POT:0~1023

ACCEL:1~3
```

---

## 6. Pi → UNO Messages

### Existing (unchanged)

```
HELLO
HB
ACT:MIDI
PLAY:OFF
PLAY:ON
PLAY:BLINK
PWR:SHUTDOWN
PWR:REBOOT
```

---

### NEW: UI State

```
UI:READY
UI:BUSY
```

---

### NEW: ACK

```
ACK:BTN
ACK:ENC
ACK:POT
```

Optional detailed:
```
ACK:BTN:LEFT
ACK:ENC:+2
```

---

## 7. Connection Sequence

```
UNO_READY → Pi
HELLO → UNO
UI:READY → UNO
HB (periodic)
```

---

## 8. Input Handling Flow

```
UNO → BTN:LEFT
Pi  → ACK:BTN
```

---

## 9. UI Behavior

Recommended LCD:

```
LINK OK  UI OK
LINK OK  BUSY
WAIT PI
```

---

## 10. Pi Implementation Guide

Before heavy tasks:
```
send("UI:BUSY")
```

After ready:
```
send("UI:READY")
```

On input:
```
send("ACK:BTN")
```

---

## 11. Summary

- LINK = connection health
- UI = responsiveness
- ACK = reliability

This prevents the "LINK OK but unresponsive" problem.

---

*Fluid Ardule Project*
