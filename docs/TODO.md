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

### Preserve Media Playback Context

When returning to Media Player after stopping playback, restore the last file or directory instead of starting from the browser root.

#### Potential Benefits

- Faster SoundFont comparison workflow
- Reduced navigation effort
- More natural return behavior after playback

#### Notes

Particularly useful when repeatedly auditioning the same MIDI file with different SoundFonts.

Current behavior remains functional and predictable.

---

## Low Priority

### Media Player Startup Latency

Media playback currently launches a new mpv process for each playback request.

Current sequence:

1. Stop existing player
2. Stop FluidSynth
3. Launch mpv
4. Initialize decoder/audio device
5. Begin playback

This can introduce noticeable startup latency on Raspberry Pi 3B.

#### Possible Improvements

- Keep mpv running in idle mode
- Control playback via IPC (`loadfile`)
- Reduce FluidSynth shutdown/startup overhead
- Add timing instrumentation to identify bottlenecks

#### Expected Benefits

- Faster media playback startup
- Improved responsiveness
- Better user experience when browsing media files

#### Notes

Current behavior is fully functional and stable.

This is considered a performance optimization rather than a bug fix.

Implementation should be deferred until higher-priority usability and stability issues are resolved.
