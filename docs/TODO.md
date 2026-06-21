# Fluid Ardule TODO

------------------------------------------------------------------------

## High Priority

### Stabilize Combi Playback

Improve reliability of Combi loading and live playback.

Focus areas:

- Ensure first Combi load works without requiring a second attempt.
- Verify Yoshimi → Combi transition.
- Verify RAW MIDI → ALSA MIDI transition.
- Prevent stuck notes during Combi switching.
- Confirm stable note routing for layer and split configurations.
- Test long-running playback with multiple active parts.

Status: In progress

### Fine-tune encoder acceleration

The encoder responsiveness has been significantly improved by the
ISR-based firmware and the Python UI update. Current behavior is
suitable for daily use.

Future work:

-   Fine-tune acceleration profiles (P1/P2/P3).
-   Evaluate encoder transition scaling for different encoder hardware.
-   Minimize occasional one-step overshoot during rapid rotation while
    preserving the current responsiveness.

Status: Ongoing optimization

------------------------------------------------------------------------

## Medium Priority

### Encoder-Based UI Navigation

The encoder is now capable of navigating menu items directly using the
full reported encoder delta (`ENC:+/-N`).

Future work:

-   Evaluate whether encoder navigation should become the primary UI
    method.
-   Keep keypad navigation available for compatibility.
-   Consider context-dependent long-press shortcuts.

Status: Implemented (core functionality completed)

### Context-Based Device Refresh

Replace remaining periodic device polling with context-based refresh.

#### Concept

Only refresh hardware status when the corresponding UI is entered.

Examples:

- DAC menu → refresh DAC list
- MIDI Mode → refresh MIDI devices
- File Browser → refresh USB status
- Wi-Fi menu → refresh Wi-Fi status
- UP long press → refresh all system status

#### Goal

Reduce unnecessary background polling while keeping hardware information current when it becomes relevant to the user.

#### Benefits

- Lower CPU usage
- Improved audio stability
- Cleaner event-driven architecture
- Better separation between UI navigation and hardware discovery

#### Notes

MIDI keyboard connection status remains the only intentional background exception because it directly affects live performance.

------------------------------------------------------------------------

## Low Priority

### UI Rendering Optimization

Current TFT rendering performance is satisfactory on Raspberry Pi 3B.

Possible future improvements:

-   Reduce redraw area further using multiple dirty rectangles.
-   Investigate adaptive render timing on faster Raspberry Pi hardware.
-   Evaluate platform-specific rendering optimizations for Raspberry Pi
    4/5.

Status: Future enhancement

------------------------------------------------------------------------

## Recently Completed

### 2026-06-16 --- Responsiveness Improvement

Completed:

-   Migrated rotary encoder handling to ISR in UNO-1 firmware.
-   Eliminated observable encoder step loss during rapid rotation.
-   Reduced button debounce latency.
-   Preserved full encoder delta (`ENC:+/-N`) in Python menu navigation.
-   Removed the legacy encoder navigation debounce filter.
-   Achieved smooth full-screen menu scrolling with significantly
    improved controller responsiveness.

See also:

-   CHANGELOG.md
-   Responsiveness_Tuning.md
