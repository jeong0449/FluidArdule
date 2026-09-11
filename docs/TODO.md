# Fluid Ardule TODO

**Last updated:** 2026-09-11

------------------------------------------------------------------------

## High Priority

### Combi Stability Validation

Perform long-term regression testing of the current Combi architecture.

Focus areas:

- Verify repeated Combi-to-Combi switching during extended use.
- Test transitions between Salamander, general SoundFont, Yoshimi,
  User Preset, Combi, and MIDI playback.
- Validate layer/split routing under extended performance.
- Confirm stable Sustain, Pitch Bend, Modulation, and Drum (CH10)
  handling.
- Verify recovery after MIDI device disconnect/reconnect.
- Test both Arachno GM and FluidR3 GM as the resident general SoundFont.
- Eliminate remaining corner cases during repeated live use.

**Status:** In progress

------------------------------------------------------------------------

### SoundFont Readiness Detection

Reduce unnecessary delay when a real SoundFont or engine transition is
required.

Focus areas:

- Detect when FluidSynth is actually ready to receive MIDI.
- Replace unnecessary fixed startup delays where practical.
- Minimize first-note latency after a SoundFont change.
- Verify Yoshimi → FluidSynth transition timing.
- Avoid adding complexity to transitions that are already fast.

**Status:** Partially implemented

------------------------------------------------------------------------

## Medium Priority

### Combi Performance Features

The core Combi workflow is now SoundFont-independent and optimized for
live use.

Remaining:

- Part Mute
- Part Solo
- Additional long-session regression testing

**Status:** Core workflow completed

------------------------------------------------------------------------

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

------------------------------------------------------------------------

### Runtime FluidSynth Settings

Allow selected FluidSynth parameters to be adjusted without restarting
the engine where possible.

Planned options:

- Polyphony (64 / 96 / 128 / 160 / 192)
- Reverb
- Chorus
- Gain

**Status:** Planned

------------------------------------------------------------------------

### Wi-Fi Status Improvements

Complete the remaining Wi-Fi status and usability refinements.

Remaining:

- Show "Obtaining IP..." while DHCP is in progress.
- Further improve SSH usability where useful.

**Status:** Partially implemented

------------------------------------------------------------------------

## Low Priority

### Engine Transition Cleanup

Review only transitions that require a real engine or SoundFont change.

Focus areas:

- FluidSynth ↔ Yoshimi transitions
- SoundFont-specific User Preset changes
- Failure recovery after engine transitions
- Remove redundant restart or restoration logic if found

Design principle:

- Prefer explicit and predictable sound-state transitions.
- Avoid unnecessary automatic restoration of previous sound states.
- Do not optimize transitions that are already effectively immediate.

------------------------------------------------------------------------

### Runtime Diagnostics Cleanup

Reduce default diagnostic output after stabilization.

Candidates:

- ACCEL_PROFILE_TRACE
- ENCODER_TRACE
- Temporary performance diagnostics

**Status:** Planned

------------------------------------------------------------------------

### UI Rendering Maintenance

The major Sound-menu responsiveness problem has been resolved.

Future work:

- Preserve event-driven rendering behavior.
- Ensure every UI state transition explicitly requests redraw when needed.
- Investigate rendering performance only when a measurable problem appears.
- Consider partial-region redraw only if it provides a clear practical benefit.

**Status:** Maintenance

------------------------------------------------------------------------

## Recently Completed

### 260910u

- Redesigned resident SoundFont and engine workflow.
- Made Combi SoundFont-independent and greatly improved switching performance.
- Improved MIDI playback and Yoshimi/FluidSynth transition behavior.
- Simplified Combi navigation and persistent performance workflow.
- Fixed the major Sound-menu responsiveness problem.

------------------------------------------------------------------------

### 260722

- Added Arachno GM support.
- Improved Combi navigation and performance workflow.
- Added IPv4 display to Wi-Fi status.
- Improved Media Player / Yoshimi interaction.
- Improved Bluetooth Audio and Media Player restoration workflow.

------------------------------------------------------------------------

### 260715

- Added Bluetooth Audio receiver mode under Media Player.
- Integrated BlueALSA playback.
- Added Bluetooth device information and playback workflow.

------------------------------------------------------------------------

### 260714

- Stabilized restart-free Yoshimi live loading.
- Restored reliable Yoshimi patch path selection.
- Preserved restart fallback when necessary.

------------------------------------------------------------------------

### 260712

- Improved Refresh Current Sound behavior.
- Restored reliable live Yoshimi loading after regression.
- Improved path selection for copied Yoshimi patches.

------------------------------------------------------------------------

### 260710

- Added Linux Console mode.
- Improved Power menu.
- Added privileged console helper support.

------------------------------------------------------------------------

### 260707

- Improved Combi performance workflow.
- Added lightweight MIDI Panic.
- Improved Refresh Current Sound behavior.
- Removed redundant Quick Menu items.

------------------------------------------------------------------------

### 260703

- Added Extension submenu.
- Added Internet Radio station switching.
- Added live Yoshimi Arpeggio Speed control.
- Improved radio playback workflow.

------------------------------------------------------------------------

### 260702

- Implemented restart-free Yoshimi live loading architecture.
- Introduced context-aware encoder acceleration.
- Added automatic ACCELSET synchronization (P0–P3).
- Added encoder diagnostic tracing.

------------------------------------------------------------------------

### 260701

- Improved Refresh Current Sound behavior.
- Unified Loading modal behavior.

------------------------------------------------------------------------

### Earlier Milestones

- Event-driven rendering architecture
- User Preset system
- Combi playback engine
- Internet Radio
- Wi-Fi manager
- Console mode
- Sound Edit
- UNO-1 ISR encoder
- Dual-engine FluidSynth / Yoshimi architecture
