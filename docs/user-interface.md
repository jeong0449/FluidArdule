# Fluid Ardule User Interface

Fluid Ardule is designed as a hardware-oriented standalone MIDI
instrument.

Unlike typical desktop software, the system is intended to be operated
primarily through dedicated hardware controls including:

-   Rotary encoder
-   5-button keypad
-   Potentiometer
-   TFT-LCD interface
-   Dedicated maintenance shortcuts

The UI emphasizes:

-   Fast navigation
-   Minimal latency
-   Performance-oriented workflow
-   Reduced dependence on keyboards or mice
-   Hardware synthesizer-like operation

------------------------------------------------------------------------

# Main Controls

## Hybrid Navigation System

Fluid Ardule combines a rotary encoder and a 5-button analog keypad to
create a compact but efficient navigation system.

The rotary encoder provides smooth sequential navigation and precise
parameter adjustment, while the keypad offers direct directional access
and quick interaction. Together, they complement each other to provide
fast operation with minimal hardware complexity.

This hybrid approach combines the tactile workflow of dedicated hardware
synthesizers with the flexibility of modern menu-driven systems.

------------------------------------------------------------------------

## Rotary Encoder

The rotary encoder is primarily used for sequential navigation and
parameter adjustment.

### Rotation

-   Navigate menu items
-   Change parameter values
-   Scroll lists
-   Adjust live performance parameters such as Arpeggio Speed

Parameter adjustment may use the full encoder delta reported by the
controller. Slow rotation supports fine adjustment, while faster
rotation can move through a wider range more quickly.

### Short Press

-   Select current item
-   Confirm actions
-   Enter highlighted menus

### Long Press

Change encoder acceleration profile.

This adjusts how quickly values change during rapid encoder rotation.

The encoder is intentionally optimized for vertical navigation and
continuous parameter editing rather than full directional control.

------------------------------------------------------------------------

# 5-Button Keypad

The analog keypad provides direct directional control and quick-access
interaction.

Buttons:

-   LEFT
-   RIGHT
-   UP
-   DOWN
-   SELECT

The keypad uses an analog resistor-ladder architecture with automatic
calibration support.

Compared with encoder-only navigation, the keypad allows faster
directional movement and more immediate access to common UI operations.

------------------------------------------------------------------------

# Navigation Behavior

## UP / DOWN

Move selection cursor.

These functions may be performed using either:

-   keypad UP/DOWN buttons
-   rotary encoder rotation

------------------------------------------------------------------------

## LEFT

Return to previous menu or cancel.

LEFT is intended to provide predictable backward navigation similar to
dedicated workstation instruments.

------------------------------------------------------------------------

## RIGHT

Optional fast entry into submenus.

Some screens may treat RIGHT as a shortcut equivalent to menu entry.

RIGHT exists primarily as a convenience shortcut for faster workflow
navigation.

------------------------------------------------------------------------

## SELECT

Primary action button.

Depending on context:

-   Enter submenu
-   Execute action
-   Confirm selection
-   Apply preset
-   Open browser

SELECT is intended to remain the safest and most predictable interaction
key.

On expandable Home items such as Extension, the UI may explicitly
display:

``` text
SEL to Expand
```

This avoids using a `>` symbol that could be mistaken for an instruction
to press RIGHT.

------------------------------------------------------------------------

# Extension Menu

The Extension item on the Home screen opens a secondary menu for
additional system and performance functions.

Enter the Extension menu with SELECT.

The Home screen uses the hint:

``` text
SEL to Expand
```

Extension is designed as an expandable location for functions that do
not need a permanent top-level Home row.

Current functions include:

-   Wi-Fi
-   Arpeggio Speed

The existing Wi-Fi function remains available through this menu.

------------------------------------------------------------------------

# Arpeggio Speed

Arpeggio Speed provides live speed adjustment for supported Yoshimi
presets in the Arpeggios category.

It is available from:

``` text
Home
  -> Extension
     -> Arpeggio Speed
```

Arpeggio Speed is also available from the Quick Menu for faster access
during performance.

When the Arpeggio Speed screen is active, rotate the encoder to adjust
the value.

The UI displays a non-selectable hint:

``` text
Rotate Encoder to adjust
```

This hint is rendered separately from menu rows and is right-aligned on
the screen. It is not part of UP/DOWN navigation.

The adjustment step is one display unit. Slow encoder movement therefore
supports fine adjustment, while faster movement can still traverse the
range efficiently through the existing encoder delta handling.

The current Arpeggio Speed value is also shown alongside the first item
in the Yoshimi Arpeggios preset list.

Arpeggio Speed is a BPM-like, empirically calibrated performance value.
It is not MIDI-clock-synchronized BPM. Internally, Fluid Ardule converts
the displayed value to the Echo Delay parameter used by the supported
Yoshimi arpeggio preset structure.

For technical details, see:

[`Yoshimi_arpeggio_speed_control.md`](Yoshimi_arpeggio_speed_control.md)

------------------------------------------------------------------------

# Quick Menu

The Quick Menu provides fast access to frequently used actions.

### Open Quick Menu

RIGHT long press.

Typical Quick Menu actions include:

-   Resume
-   Home
-   Sound Source
-   USB Eject
-   Save User Preset
-   Arpeggio Speed

Arpeggio Speed is placed at the end of the Quick Menu so that it can be
reached quickly during Yoshimi Arpeggios performance without changing
the normal meaning of RIGHT long press.

The Quick Menu supports rollover navigation.

------------------------------------------------------------------------

# MIDI Panic and Sound Recovery

## MIDI Panic

DOWN long press sends MIDI panic.

This immediately stops hanging or stuck notes.

## Sound Recovery

UP long press performs the sound reload/refresh operation provided by
the runtime.

This function is intended as a recovery shortcut when sound output is
suspected to be unavailable after repeated sound-source or preset
changes.

------------------------------------------------------------------------

# Keypad Calibration

The 5-button analog keypad supports self-calibration.

Calibration stores ADC center values in EEPROM to improve long-term
stability across:

-   resistor tolerance variation
-   voltage fluctuation
-   temperature drift
-   aging

## Enter Calibration Mode

ENC + SELECT long press.

## Calibration Procedure

The system requests each button sequentially:

1.  LEFT
2.  UP
3.  DOWN
4.  RIGHT
5.  SELECT

Press each requested button when prompted.

Calibration values are automatically saved to EEPROM after completion.

------------------------------------------------------------------------

# Encoder + Button Combination Design

Some maintenance functions use button combinations instead of
single-button long presses.

This avoids conflicts between:

-   normal UI interaction
-   maintenance operations
-   performance workflow

For example:

-   ENC long press: encoder acceleration control
-   RIGHT long press: Quick Menu
-   DOWN long press: MIDI panic
-   UP long press: sound reload/refresh
-   ENC + SELECT long press: keypad calibration

This design helps preserve predictable real-time operation while
minimizing accidental entry into maintenance functions.

------------------------------------------------------------------------

# UI Philosophy

Fluid Ardule prioritizes:

-   immediate responsiveness
-   hardware-like interaction
-   minimal screen dependency
-   predictable control behavior

The interface intentionally resembles dedicated synthesizers and
workstation instruments rather than desktop software.

Display rendering is also optimized to minimize interference with
real-time MIDI and audio processing.

The overall interaction model favors tactile hardware operation over
pointer-based graphical interaction.

Operational hints are visually separated from selectable menu rows
whenever possible. This prevents help text such as
`Rotate Encoder to adjust` from being mistaken for an item reachable
with UP/DOWN navigation.

------------------------------------------------------------------------

# Service / Diagnostic Functions

The UNO-1 auxiliary LCD may display:

-   link status
-   keypad states
-   raw ADC values
-   calibration progress
-   diagnostic messages

This display functions as a low-level service and debugging interface
independent of the Raspberry Pi UI.

------------------------------------------------------------------------

# Future Directions

Potential future UI/input improvements include:

-   digital GPIO-based keypad architectures
-   I2C I/O expanders such as PCF8574
-   expanded performance controls
-   additional shortcut customization
-   layered workstation-style interaction

The current resistor-ladder keypad architecture remains an intentional
balance between simplicity, cost, and functionality.
