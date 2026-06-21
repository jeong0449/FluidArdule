# Fluid Ardule TODO

------------------------------------------------------------------------

## High Priority

### Stabilize Combi Playback

Improve reliability of Combi loading and live playback.

Focus areas:

-   Verify Yoshimi → Combi transition.
-   Prevent stuck notes during Combi switching.
-   Confirm stable note routing for layer and split configurations.
-   Test long-running playback with multiple active parts.

Status: In progress

### Fine-tune Encoder Acceleration

-   Fine-tune acceleration profiles (P1/P2/P3).
-   Evaluate encoder transition scaling.
-   Minimize occasional one-step overshoot.

Status: Ongoing optimization

------------------------------------------------------------------------

## Medium Priority

### Encoder-Based UI Navigation

Status: Core implementation completed.

-   Evaluate encoder navigation as the primary UI method.
-   Keep keypad navigation for compatibility.
-   Consider context-dependent long-press shortcuts.

### Context-Based Device Refresh

Remaining targets:

-   DAC menu
-   MIDI Mode
-   File Browser
-   UP long press refresh

Notes:

-   Wi-Fi now uses cached context-based refresh.
-   MIDI keyboard monitoring remains a background task.

### Runtime FluidSynth Settings

-   Runtime Polyphony (64 / 96 / 128 / 160 / 192)
-   Future: Reverb, Chorus, Gain
-   Use FluidSynth stdin `set` commands.
-   Current default polyphony: 96.

### Performance-Oriented Combi Workflow

-   Improve active Combi indication.
-   Keep users within the Combi screen.
-   Prepare for layer mute/solo.
-   Separate SoundFont loading feedback from Combi preview.

------------------------------------------------------------------------

## Low Priority

### UI Rendering Optimization

-   Reduce redraw area.
-   Investigate Pi 4/5 optimizations.

Status: Future enhancement.

------------------------------------------------------------------------

## Recently Completed

### 2026-06-21

-   Delayed User Preset preview.
-   Five-line User Preset list.
-   Improved footer wording.
-   Combi preview feedback.
-   Combi timing logs.
-   Wi-Fi configuration caching.
-   Sound cache improvements.
-   Stabilized first Combi preview/load.
-   Verified RAW MIDI → ALSA MIDI transition.
-   Default FluidSynth polyphony set to 96.

### 2026-06-16

-   ISR encoder firmware.
-   Full encoder delta navigation.
-   Faster menu responsiveness.
