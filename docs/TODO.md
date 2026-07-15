# Fluid Ardule TODO

**Last updated:** 2026-07-15 (SCRIPT_VERSION 260714b)

---

## High Priority

### Combi Stability Validation

Perform long-term regression testing of Combi playback.

Focus areas:

- Verify repeated switching between FluidSynth, Yoshimi, and Combi.
- Validate layer/split routing under extended performance.
- Confirm stable Sustain, Pitch Bend, Modulation, and Drum (CH10) handling.
- Verify recovery after MIDI device disconnect/reconnect.
- Eliminate remaining corner cases during repeated live use.

**Status:** In progress

---

### SoundFont Readiness Detection

Replace fixed startup delays with state-based readiness detection.

Focus areas:

- Detect when FluidSynth is actually ready to receive MIDI.
- Replace unnecessary fixed startup delays.
- Preserve the current Loading / Ready UI behavior.
- Minimize first-note latency for large SoundFonts.

**Status:** Planned

---

## Medium Priority

### Context-Aware Encoder Acceleration

Continue refining automatic encoder acceleration.

Focus areas:

- Fine-tune automatic profile selection:
  - **P0** — Precise navigation
  - **P1** — List browsing
  - **P2** — Continuous parameter editing
- Preserve **P3** as manual turbo override.
- Reduce occasional one-step overshoot.
- Verify profile synchronization after UNO reconnect.

**Status:** Ongoing

---

### Runtime FluidSynth Settings

Allow selected FluidSynth parameters to be adjusted without restarting the engine.

Planned options:

- Polyphony (64 / 96 / 128 / 160 / 192)
- Reverb
- Chorus
- Gain

---

### Performance-Oriented Combi Workflow

Further improve live-performance usability.

Possible future work:

- Better active Combi indication
- Part Mute
- Part Solo

---

### Bluetooth Audio Receiver

Add Bluetooth audio receiver mode under Media Player.

Goals:

- BlueALSA playback
- Automatic restoration of previous sound engine
- Manual pairing/removal through Console (`bluetoothctl`)

---

## Low Priority

### Runtime Diagnostics Cleanup

Reduce default diagnostic output after stabilization.

Candidates:

- ACCEL_PROFILE_TRACE
- ENCODER_TRACE
- Additional optional runtime diagnostics

---

### UI Rendering Optimization

Continue optimizing TFT rendering.

Possible improvements:

- Reduce redraw artifacts
- Investigate partial list-region redraw
- Preserve event-driven rendering philosophy

---

## Recently Completed

### 260714

- Stabilized restart-free Yoshimi live loading.
- Restored reliable Yoshimi patch path selection.
- Returned Yoshimi CLI to the root context before live loading.
- Preserved restart fallback only when necessary.

---

### 260712

- Refresh Current Sound now preserves the current UI.
- Restored reliable live Yoshimi loading after regression.
- Improved path selection for copied Yoshimi patches.

---

### 260710

- Added Linux Console mode.
- Improved Power menu.
- Added privileged console helper support.

---

### 260707

- Persistent Combi performance lock.
- Faster Combi loading (~3.7 seconds).
- Lightweight MIDI Panic.
- Refresh Current Sound preserves active Combi.
- Removed redundant Quick Menu items.

---

### 260703

- Added Extension submenu.
- Added Internet Radio station switching.
- Added live Yoshimi Arpeggio Speed control.
- Improved radio playback workflow.

---

### 260702

- Implemented restart-free Yoshimi live loading architecture.
- Introduced context-aware encoder acceleration.
- Added automatic ACCELSET synchronization (P0–P3).
- Added encoder diagnostic tracing.

---

### 260701

- Refresh Current Sound now preserves the current screen.
- Unified Loading modal behavior.

---

### Earlier Milestones

- Event-driven rendering architecture
- User Preset system
- Combi playback engine
- Internet Radio
- Wi-Fi manager
- Console mode
- Sound Edit
- UNO-1 ISR encoder
- Dual-engine (FluidSynth + Yoshimi) architecture
