# Fluid Ardule TODO

---

## High Priority

### Encoder navigation magnitude

UNO reports ENC:+/-1..3 correctly, but Python UI navigation does not always appear to consume the full reported movement.

Status: Investigating

---

## Medium Priority

### Encoder-Based UI Navigation

Allow the rotary encoder to navigate visible menu items directly.

#### Concept

- Rotate encoder to move the menu cursor.
- Press encoder to select the highlighted item.
- Long press may be used for Back or other context-dependent actions.

#### Potential Benefits

- Faster one-handed operation.
- Reduced dependence on the 5-button keypad.
- More synthesizer-like user experience.
- Better use of the encoder when no parameter editing is active.

#### Notes

- Existing keypad navigation should remain available.
- Initial implementation may be limited to selected screens or playback mode.
- Evaluate whether encoder navigation should become the primary UI method in future versions.

#### Rationale

Current Fluid Ardule navigation relies primarily on the 5-button keypad for menu traversal. However, many hardware synthesizers allow users to browse visible menu items directly using a rotary encoder.

Providing optional encoder-based navigation could improve usability while preserving compatibility with the existing keypad-driven interface.
