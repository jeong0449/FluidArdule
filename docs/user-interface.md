# Fluid Ardule User Interface

Fluid Ardule is designed as a hardware-oriented standalone MIDI instrument.

Unlike typical desktop software, the system is intended to be operated primarily through dedicated hardware controls including:

- Rotary encoder
- 5-button keypad
- Potentiometer
- TFT-LCD interface
- Dedicated maintenance shortcuts

The UI emphasizes:

- Fast navigation
- Minimal latency
- Performance-oriented workflow
- Reduced dependence on keyboards or mice
- Hardware synthesizer-like operation

---

# Main Controls

## Hybrid Navigation System

Fluid Ardule combines a rotary encoder and a 5-button analog keypad to create a compact but efficient navigation system.

The rotary encoder provides smooth sequential navigation and precise parameter adjustment, while the keypad offers direct directional access and quick interaction. Together, they complement each other to provide fast operation with minimal hardware complexity.

This hybrid approach combines the tactile workflow of dedicated hardware synthesizers with the flexibility of modern menu-driven systems.

---

## Rotary Encoder

The rotary encoder is primarily used for sequential navigation and parameter adjustment.

### Rotation

- Navigate menu items
- Change parameter values
- Scroll lists

### Short Press

- Select current item
- Confirm actions
- Enter highlighted menus

### Long Press

Change encoder acceleration profile.

This adjusts how quickly values change during rapid encoder rotation.

The encoder is intentionally optimized for vertical navigation and continuous parameter editing rather than full directional control.

---

# 5-Button Keypad

The analog keypad provides direct directional control and quick-access interaction.

Buttons:

- LEFT
- RIGHT
- UP
- DOWN
- SELECT

The keypad uses an analog resistor-ladder architecture with automatic calibration support.

Compared with encoder-only navigation, the keypad allows faster directional movement and more immediate access to common UI operations.

---

# Navigation Behavior

## UP / DOWN

Move selection cursor.

These functions may be performed using either:

- keypad UP/DOWN buttons
- rotary encoder rotation

---

## LEFT

Return to previous menu or cancel.

LEFT is intended to provide predictable backward navigation similar to dedicated workstation instruments.

---

## RIGHT

Optional fast entry into submenus.

Some screens may treat RIGHT as a shortcut equivalent to menu entry.

RIGHT exists primarily as a convenience shortcut for faster workflow navigation.

---

## SELECT

Primary action button.

Depending on context:

- Enter submenu
- Execute action
- Confirm selection
- Apply preset
- Open browser

SELECT is intended to remain the safest and most predictable interaction key.

---

# Quick Menu

The Quick Menu provides fast access to frequently used actions.

### Open Quick Menu

RIGHT long press.

Typical Quick Menu actions may include:

- Resume
- Home
- Sound Source
- USB Eject
- Save User Preset

The Quick Menu supports rollover navigation.

---

# MIDI Panic

DOWN long press sends MIDI panic.

This immediately stops hanging or stuck notes.

---

# Keypad Calibration

The 5-button analog keypad supports self-calibration.

Calibration stores ADC center values in EEPROM to improve long-term stability across:

- resistor tolerance variation
- voltage fluctuation
- temperature drift
- aging

## Enter Calibration Mode

ENC + SELECT long press.

## Calibration Procedure

The system requests each button sequentially:

1. LEFT
2. UP
3. DOWN
4. RIGHT
5. SELECT

Press each requested button when prompted.

Calibration values are automatically saved to EEPROM after completion.

---

# Encoder + Button Combination Design

Some maintenance functions use button combinations instead of single-button long presses.

This avoids conflicts between:

- normal UI interaction
- maintenance operations
- performance workflow

For example:

- ENC long press:
  encoder acceleration control
- ENC + SELECT long press:
  keypad calibration

This design helps preserve predictable real-time operation while minimizing accidental entry into maintenance functions.

---

# UI Philosophy

Fluid Ardule prioritizes:

- immediate responsiveness
- hardware-like interaction
- minimal screen dependency
- predictable control behavior

The interface intentionally resembles dedicated synthesizers and workstation instruments rather than desktop software.

Display rendering is also optimized to minimize interference with real-time MIDI and audio processing.

The overall interaction model favors tactile hardware operation over pointer-based graphical interaction.

---

# Service / Diagnostic Functions

The UNO-1 auxiliary LCD may display:

- link status
- keypad states
- raw ADC values
- calibration progress
- diagnostic messages

This display functions as a low-level service and debugging interface independent of the Raspberry Pi UI.

---

# Future Directions

Potential future UI/input improvements include:

- digital GPIO-based keypad architectures
- I2C I/O expanders such as PCF8574
- expanded performance controls
- additional shortcut customization
- layered workstation-style interaction

The current resistor-ladder keypad architecture remains an intentional balance between simplicity, cost, and functionality.
