# Fluid Ardule TODO

------------------------------------------------------------------------

## High Priority

### Smooth Yoshimi Instrument Switching

Reduce audible thump/noise during Yoshimi preview and instrument
changes.

Focus areas:

-   Avoid full Yoshimi process restart when moving between Yoshimi
    instruments.
-   Investigate reliable Yoshimi control method for live `.xiz` loading.
-   Verify CLI, OSC, or alternative control paths outside the main
    runtime first.
-   Keep current UI behavior if possible: automatic preview on
    highlight.
-   Fall back safely when live switching is unreliable.

**Status:** Open / research required

**Notes:**

-   2026-06-29 experiment: sending `load instrument` through stdin
    changed UI state but did not reliably change sound.
-   Current stable behavior still restarts Yoshimi per preview item,
    causing a short audible "thump".

### Stabilize Combi Playback

-   Verify Yoshimi → Combi transition.
-   Prevent stuck notes during Combi switching.
-   Confirm stable note routing for layer and split configurations.
-   Test long-running playback with multiple active parts.

**Status:** In progress

### Fix Refresh Current Sound UI Return

-   Preserve current UI mode after refresh.
-   Avoid unwanted navigation side effects.

**Status:** Open / small bug

---

## Medium Priority

### Fine-tune Encoder Acceleration

-   Fine-tune acceleration profiles (P1/P2/P3).
-   Minimize occasional one-step overshoot.

### Encoder-Based UI Navigation

-   Keep encoder long press assigned to acceleration profile selection.
-   Keep keypad navigation for compatibility.

### Context-Based Device Refresh

-   DAC menu
-   MIDI Mode
-   File Browser
-   UP long press refresh

### Runtime FluidSynth Settings

-   Runtime Polyphony (64 / 96 / 128 / 160 / 192)
-   Future: Reverb, Chorus, Gain

### Performance-Oriented Combi Workflow

-   Improve active Combi indication.
-   Prepare for layer mute/solo.

### Bluetooth Audio Receiver

-   Add a Bluetooth audio receiver mode under Media Player.
-   Use BlueALSA with previously paired/trusted devices.
-   Start Bluetooth audio on entry and restore the previous sound engine on exit.
-   Keep device pairing and removal as manual Console operations using `bluetoothctl`.

### SoundFont Readiness Detection

Replace fixed startup delays with state-based readiness detection.

Focus areas:

- Detect when FluidSynth is ready to accept MIDI.
- Display "Loading..." and "Ready" status in the UI.
- Eliminate unnecessary fixed waits where possible.
- Investigate first-note latency with large SoundFonts (e.g. FluidGM).

Status: Planned

---

## Low Priority

### UI Rendering Optimization

-   Reduce redraw artifacts.
-   Evaluate list-region redraw strategy.

---

## Recently Completed

### 2026-06-29

-   Improved Yoshimi → FluidSynth lifecycle handling.
-   Added cleanup before returning from Yoshimi to FluidSynth.
-   Moved User Preset Manage to LEFT long press.
-   Changed DOWN long press to Refresh Current Sound.
-   Moved MIDI Panic to the Quick Menu.
-   Preserved encoder long press for acceleration selection.
-   Improved list-region redraw.
-   Investigated live Yoshimi switching without restart.
-   Confirmed Yoshimi preview thump is caused by repeated process
    restart.

### 2026-06-21

-   Delayed User Preset preview.
-   Five-line User Preset list.
-   Wi-Fi configuration caching.
-   Default FluidSynth polyphony set to 96.

### 2026-06-16

-   ISR encoder firmware.
-   Full encoder delta navigation.
