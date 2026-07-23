# UNO-1 ↔ Raspberry Pi Serial Protocol

*(Fluid Ardule Project)*

**Version: 20260702a (Context-specific encoder acceleration revision)**\
**Updated: 2026-07-02**

------------------------------------------------------------------------

## Revision Highlights (20260702a)

This revision introduces context-specific encoder acceleration control.

Major changes:

-   Added **P0 (Precise / No Acceleration)** encoder profile.
-   Added **ACCELSET:0--3** command (Raspberry Pi → UNO-1).
-   Raspberry Pi now selects the recommended acceleration profile
    according to the current UI context.
-   UNO-1 displays the active profile (P0--P3) on the LCD.
-   Encoder long press cycles P0→P1→P2→P3 as a temporary override until
    the next context change.
-   Protocol updated to support context-aware navigation while
    maintaining backward compatibility.

------------------------------------------------------------------------

## 1. Overview

UNO-1 and Raspberry Pi communicate via USB serial (CDC) using a simple
line-based ASCII protocol.

-   Baud rate: `115200`
-   Encoding: ASCII
-   Framing: 1 message per line, terminated by ``
-   Direction: Bidirectional
-   Primary purpose:
    -   Send hardware input events from UNO-1 to Raspberry Pi
    -   Send link, UI, playback, power, and activity state from
        Raspberry Pi to UNO-1

------------------------------------------------------------------------

## 2. Core Concept

The protocol distinguishes three different concepts that should not be
confused.

  -----------------------------------------------------------------------
  Concept                 Meaning                 Typical Message
  ----------------------- ----------------------- -----------------------
  LINK                    Serial connection is    `HELLO`, `HB`,
                          alive                   `UNO_READY`

  UI                      Raspberry Pi UI can     `UI:READY`, `UI:BUSY`
                          process input           
                          
  ACK                     Raspberry Pi has        `ACK:BTN`, `ACK:ENC`,
                          received an input event `ACK:POT`
  -----------------------------------------------------------------------

Previous limitation:

-   `LINK OK` only meant that the Pi was alive.
-   It did **not** guarantee that the UI was responsive.

Current model:

-   `LINK OK` = serial heartbeat is alive.
-   `UI OK` = Pi-side UI is ready to process inputs.
-   `UI BUSY` = Pi-side UI is temporarily unavailable or performing a
    blocking task.
-   `ACK` = Pi has received a specific input event.

------------------------------------------------------------------------

## 3. State Model

``` text
WAIT PI  = no HELLO / HB received recently
LINK OK  = HELLO / HB received
UI OK    = UI:READY received
UI BUSY  = UI:BUSY received
```

Recommended LCD display on UNO-1:

``` text
LINK OK  UI OK
LINK OK  BUSY
WAIT PI
```

The LCD message should avoid implying that the whole system is
responsive when only the serial link is alive.

------------------------------------------------------------------------

## 4. Message Format

Most messages use the following format:

``` text
TYPE:VALUE
```

Examples:

``` text
BTN:LEFT
ENC:+2
POT:512
UI:READY
ACK:BTN
```

Some messages are standalone tokens:

``` text
UNO_READY
HELLO
HB
```

All messages are ASCII text lines ending in `\n`.

------------------------------------------------------------------------

## 5. UNO-1 → Raspberry Pi Messages

### 5.1 Startup / Link

``` text
UNO_READY
```

Meaning:

-   UNO-1 has booted or is alive.
-   Pi may respond with `HELLO`.
-   UNO-1 may also send `UNO_READY` periodically while waiting for the
    Pi or during local maintenance mode.

------------------------------------------------------------------------

### 5.2 Button Events

``` text
BTN:LEFT
BTN:RIGHT
BTN:UP
BTN:DOWN
BTN:SEL
BTN:ENC_PUSH
```

Long press events:

``` text
BTN:LEFT_LP
BTN:RIGHT_LP
BTN:UP_LP
BTN:DOWN_LP
BTN:SEL_LP
BTN:ENC_PUSH_LP
```

Notes:

-   `SEL` means the SELECT key on the 5-button analog keypad.
-   `ENC_PUSH` means the rotary encoder push switch.
-   Long-press semantics are interpreted by the Pi UI, unless the event
    is reserved locally by UNO-1.

------------------------------------------------------------------------

### 5.3 Encoder Rotation

``` text
ENC:+N
ENC:-N
```

Examples:

``` text
ENC:+1
ENC:-3
```

Meaning:

-   Positive value: clockwise rotation or next item / increase value.
-   Negative value: counter-clockwise rotation or previous item /
    decrease value.
-   `N` may reflect encoder acceleration.

------------------------------------------------------------------------

### 5.4 Potentiometer

``` text
POT:0~1023
```

Examples:

``` text
POT:0
POT:512
POT:1023
```

Meaning:

-   Raw or filtered potentiometer value from UNO-1.
-   The Pi may map this to volume or another continuous parameter.
-   The Pi should not automatically override the physical pot position
    with a default maximum value after playback starts.

------------------------------------------------------------------------

### 5.5 Encoder Acceleration

``` text
ACCEL:0
ACCEL:1
ACCEL:2
ACCEL:3
```

Meaning:

-   UNO-1 has changed its encoder acceleration profile.
-   This may be used for UI feedback or diagnostics.

------------------------------------------------------------------------

### 5.6 Optional Calibration Status Messages

The current firmware may treat calibration as a local-only UNO-1
operation and may not send these messages.

If later Pi-side logging or UI indication is desired, the following
optional messages may be used:

``` text
CAL:BEGIN
CAL:SAVED
CAL:ABORT
CAL:FAIL
```

Meaning:

  Message       Meaning
  ------------- ----------------------------------------------------
  `CAL:BEGIN`   UNO-1 entered keypad self-calibration mode
  `CAL:SAVED`   Calibration values were saved to EEPROM
  `CAL:ABORT`   Calibration was cancelled or exited without saving
  `CAL:FAIL`    Calibration failed or produced invalid values

Recommendation:

-   These messages are optional.
-   Do not require the Pi to implement them unless Pi-side notification
    or logging is needed.
-   The core protocol should continue to work without them.

------------------------------------------------------------------------

## 6. Raspberry Pi → UNO-1 Messages

### 6.1 Link / Heartbeat

``` text
HELLO
HB
```

Meaning:

-   `HELLO`: Pi has detected UNO-1 and acknowledges the connection.
-   `HB`: Pi heartbeat; sent periodically while the Pi process is alive.

------------------------------------------------------------------------

### 6.2 UI State

``` text
UI:READY
UI:BUSY
```

Meaning:

  Message      Meaning
  ------------ -------------------------------------------------------
  `UI:READY`   Pi UI is ready to process input
  `UI:BUSY`    Pi UI is temporarily busy or should not receive input

Typical use:

``` text
send("UI:BUSY")
# perform heavy or blocking task
send("UI:READY")
```

Examples of `UI:BUSY` situations:

-   Loading a soundfont or sound source
-   Starting or stopping an engine
-   Scanning USB media
-   Opening a large file list
-   Performing a blocking maintenance task

------------------------------------------------------------------------

### 6.3 Input Acknowledgement

Basic ACK messages:

``` text
ACK:BTN
ACK:ENC
ACK:POT
```

Optional detailed ACK messages:

``` text
ACK:BTN:LEFT
ACK:ENC:+2
ACK:POT:512
```

Meaning:

-   Pi has received an input event.
-   ACK confirms event reception, not necessarily final UI action.
-   ACK helps distinguish "UNO sent the event" from "Pi UI actually
    acted on it."

------------------------------------------------------------------------

### 6.4 MIDI / Playback Activity

``` text
ACT:MIDI
PLAY:OFF
PLAY:ON
PLAY:BLINK
```

Meaning:

  Message        Meaning
  -------------- --------------------------------------
  `ACT:MIDI`     MIDI activity pulse indication
  `PLAY:OFF`     Playback stopped or inactive
  `PLAY:ON`      Playback active
  `PLAY:BLINK`   Playback-related blinking indication

------------------------------------------------------------------------

### 6.6 Encoder Acceleration Profile (NEW)

Raspberry Pi may automatically select an encoder acceleration profile
according to the current UI context.

``` text
ACCELSET:0
ACCELSET:1
ACCELSET:2
ACCELSET:3
```

Meaning:

  Profile   Intended use
  --------- ---------------------------
  P0        Precise (no acceleration)
  P1        Fine list navigation
  P2        Normal parameter editing
  P3        Fast continuous editing

Typical automatic mapping:

``` text
Home            -> P0
Preset/Combi    -> P1
File Browser    -> P1
Radio Browser   -> P1
CC Edit         -> P2
Tempo           -> P2
Volume          -> P2
```

UNO-1 updates its current acceleration profile immediately when
`ACCELSET:n` is received and reflects the active profile on the LCD
(P0--P3). The user may temporarily change the profile with the encoder
long-press until the next context change.

### 6.5 Power Commands

``` text
PWR:SHUTDOWN
PWR:REBOOT
```

Meaning:

-   Pi is about to shut down or reboot.
-   UNO-1 may update LCD/LED status accordingly.

------------------------------------------------------------------------

## 7. Connection Sequence

### 7.1 Normal Startup

``` mermaid
sequenceDiagram
    participant U as UNO-1
    participant P as Raspberry Pi

    U->>P: UNO_READY
    P->>U: HELLO
    P->>U: UI:READY
    loop Periodic heartbeat
        P->>U: HB
    end
```

Text form:

``` text
UNO_READY  → Pi
HELLO      → UNO-1
UI:READY   → UNO-1
HB         → UNO-1 periodically
```

------------------------------------------------------------------------

## 8. Normal Input Handling Flow

``` mermaid
sequenceDiagram
    participant U as UNO-1
    participant P as Raspberry Pi UI

    U->>P: BTN:LEFT
    P-->>U: ACK:BTN
    P->>P: Process navigation event

    U->>P: ENC:+2
    P-->>U: ACK:ENC
    P->>P: Move selection or change value

    U->>P: POT:640
    P-->>U: ACK:POT
    P->>P: Apply mapped parameter value
```

Text form:

``` text
UNO-1 → BTN:LEFT
Pi    → ACK:BTN
Pi    → process event
```

------------------------------------------------------------------------

## 9. Busy UI Flow

When the Pi UI is busy, it should announce that state before the
blocking operation begins.

``` mermaid
sequenceDiagram
    participant U as UNO-1
    participant P as Raspberry Pi UI

    P->>U: UI:BUSY
    Note over U: LCD may show LINK OK / BUSY
    P->>P: Load sound source / scan files / restart engine
    P->>U: UI:READY
    Note over U: LCD may show LINK OK / UI OK
```

Recommended behavior:

-   Pi sends `UI:BUSY` before heavy work.
-   Pi sends `UI:READY` after the UI can process input again.
-   UNO-1 may still keep link status alive, but should not claim full UI
    responsiveness unless `UI:READY` was received.

------------------------------------------------------------------------

## 10. Self-Calibration / Maintenance Mode

Keypad self-calibration is a local UNO-1 maintenance mode.

### 10.1 Purpose

The 5-button analog keypad uses a resistor-ladder design. Because button
ADC values may drift depending on modules, wiring, temperature, or power
conditions, UNO-1 may support self-calibration to store reliable button
thresholds.

### 10.2 Entry

Current recommended entry gesture:

``` text
Encoder switch + SELECT simultaneous long press
```

Rationale:

-   Calibration must remain accessible even when ordinary 5-button
    navigation is unreliable.
-   The gesture should be difficult to trigger accidentally during
    performance.
-   It should not depend solely on the analog keypad being already well
    calibrated.

### 10.3 Behavior During Calibration

During calibration mode:

-   UNO-1 handles calibration locally.
-   Runtime `BTN`, `ENC`, and `POT` messages should be suppressed or
    minimized.
-   UNO-1 may continue sending `UNO_READY` periodically to prevent
    Pi-side link monitoring from assuming the controller disappeared.
-   Calibration values are stored in UNO EEPROM.
-   Pi-side action is not required.

### 10.4 Calibration Flow

``` mermaid
flowchart TD
    A[Normal UNO-1 runtime] --> B{Encoder push + SELECT<br/>simultaneous long press?}
    B -- No --> A
    B -- Yes --> C[Enter self-calibration mode]
    C --> D[Suppress normal BTN / ENC / POT events]
    D --> E[Measure keypad ADC values]
    E --> F{Values valid?}
    F -- No --> G[Show calibration fail / retry]
    G --> E
    F -- Yes --> H[Save thresholds to EEPROM]
    H --> I[Exit calibration mode]
    I --> J[Resume normal serial input events]
    J --> A
```

### 10.5 Optional Pi Notification

If Pi-side diagnostics are later desired, UNO-1 may send:

``` text
CAL:BEGIN
CAL:SAVED
CAL:ABORT
CAL:FAIL
```

However, these are optional and should not be required for normal
operation.

------------------------------------------------------------------------

## 11. Error Handling and Robustness

### 11.1 Unknown Messages

Both sides should ignore unknown message types safely.

Recommended policy:

``` text
Unknown message → ignore and continue
```

This allows protocol evolution without breaking older firmware or
scripts.

### 11.2 Missing ACK

If UNO-1 does not receive ACK for a particular input event, it should
not necessarily resend that event automatically.

Reason:

-   Re-sending button or encoder events can cause duplicate UI actions.
-   ACK is mainly diagnostic and status feedback, not a strict transport
    guarantee.

### 11.3 Link Alive but UI Frozen

The protocol intentionally separates:

``` text
LINK OK
UI OK / UI BUSY
```

This avoids the misleading condition:

``` text
LINK OK, but the Pi UI is not responding
```

------------------------------------------------------------------------

## 12. Pi Implementation Guide

### 12.1 On Serial Connect

Recommended sequence:

``` python
send("HELLO")
send("UI:READY")
```

### 12.2 On Input Event

Recommended example:

``` python
if line.startswith("BTN:"):
    send("ACK:BTN")
    handle_button(line)

elif line.startswith("ENC:"):
    send("ACK:ENC")
    handle_encoder(line)

elif line.startswith("POT:"):
    send("ACK:POT")
    handle_pot(line)
```

### 12.3 Around Heavy Tasks

Recommended example:

``` python
send("UI:BUSY")
try:
    load_sound_source()
finally:
    send("UI:READY")
```

### 12.4 Calibration Awareness

The Pi does not need to enter a special mode when UNO-1 is calibrating.

Recommended behavior:

-   Treat repeated `UNO_READY` as a link-alive signal.
-   Ignore optional `CAL:*` messages unless logging or UI indication is
    implemented.
-   Do not assume that lack of `BTN/ENC/POT` events during calibration
    means serial failure.

------------------------------------------------------------------------

## 13. Compatibility Policy

Required core messages:

``` text
UNO_READY
HELLO
HB
BTN:...
ENC:...
POT:...
UI:READY
UI:BUSY
ACK:...
```

Optional messages:

``` text
ACCEL:...
ACCELSET:...
ACT:MIDI
PLAY:...
PWR:...
CAL:...
```

Compatibility rules:

-   Older Pi scripts should continue to work if they ignore unknown
    messages.
-   Older UNO-1 firmware should continue to work if it does not send
    `CAL:*` messages.
-   Calibration should remain primarily local to UNO-1 unless a clear
    Pi-side use case emerges.

------------------------------------------------------------------------

## 14. Summary

-   `LINK` indicates serial connection health.
-   `UI` indicates Pi-side input-processing availability.
-   `ACK` confirms that an input event was received.
-   Self-calibration is a local UNO-1 maintenance mode.
-   No mandatory serial protocol expansion is required for
    self-calibration.
-   Optional `CAL:*` messages may be added later for logging or UI
    display.
-   The restored sequence diagrams document normal startup, input
    handling, busy state, and calibration flow.

------------------------------------------------------------------------

*Fluid Ardule Project*
