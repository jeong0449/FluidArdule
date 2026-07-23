# Fluid Ardule TODO

**Last updated:** 2026-07-22

------------------------------------------------------------------------

## High Priority

### Combi Stability Validation

Perform long-term regression testing of Combi playback.

Focus areas:

-   Verify repeated switching between FluidSynth, Yoshimi, and Combi.
-   Validate layer/split routing under extended performance.
-   Confirm stable Sustain, Pitch Bend, Modulation, and Drum (CH10)
    handling.
-   Verify recovery after MIDI device disconnect/reconnect.
-   Eliminate remaining corner cases during repeated live use.

**Status:** In progress

------------------------------------------------------------------------

### SoundFont Readiness Detection

Replace fixed startup delays with state-based readiness detection.

Focus areas:

-   Detect when FluidSynth is actually ready to receive MIDI.
-   Replace unnecessary fixed startup delays.
-   Preserve the current Loading / Ready UI behavior.
-   Minimize first-note latency for large SoundFonts.

**Status:** Partially implemented

------------------------------------------------------------------------

### Faster Sound Menu Initialization *(2026-07-22)*

Reduce latency when entering **Home → Sound**.

Goals:

-   Eliminate unnecessary preset counting during menu construction.
-   Load preset indexes only when actually required.
-   Keep top-level Sound navigation responsive.
-   Preserve current behavior of lower-level preset browsing.

**Status:** Planned

------------------------------------------------------------------------

## Medium Priority

### Universal GM Combi Compatibility *(2026-07-22)*

Allow the same Combi presets to be shared across multiple GM-compatible
SoundFonts.

Initial targets:

-   FluidR3 GM
-   GeneralUser GS
-   Arachno GM

Goals:

-   Reuse existing Combi definitions.
-   Resolve SoundFont-specific preset IDs dynamically.
-   Preserve bank/program compatibility whenever possible.
-   Minimize changes to the current Combi format.

**Status:** Partially implemented

Completed:

-   Separate Combi definition files per SoundFont.
-   Runtime SoundFont selection from the Combi browser.
-   Active Combi/SoundFont tracking.
-   Shared Combi workflow across FluidR3 GM, GeneralUser GS, and Arachno
    GM.

Remaining:

-   Automatic preset-ID translation between SoundFonts.
-   Additional GM-compatible SoundFonts.

------------------------------------------------------------------------

### Context-Aware Encoder Acceleration

Continue refining automatic encoder acceleration.

Focus areas:

-   Fine-tune automatic profile selection:
    -   **P0** --- Precise navigation
    -   **P1** --- List browsing
    -   **P2** --- Continuous parameter editing
-   Preserve **P3** as manual turbo override.
-   Reduce occasional one-step overshoot.
-   Verify profile synchronization after UNO reconnect.

**Status:** Ongoing

------------------------------------------------------------------------

### Runtime FluidSynth Settings

Allow selected FluidSynth parameters to be adjusted without restarting
the engine.

Planned options:

-   Polyphony (64 / 96 / 128 / 160 / 192)
-   Reverb
-   Chorus
-   Gain

------------------------------------------------------------------------

### Wi-Fi Status Improvements *(2026-07-22)*

Enhance the Wi-Fi information screen.

Goals:

-   Display the assigned IPv4 address.
-   Show "Obtaining IP..." while DHCP is in progress.
-   Improve SSH accessibility without requiring Console access.

**Status:** Partially implemented

Completed:

-   Display assigned IPv4 address.

Remaining:

-   Show "Obtaining IP..."
-   Further SSH usability improvements.

------------------------------------------------------------------------

### Performance-Oriented Combi Workflow

Completed:

-   Active Combi indication.
-   Persistent Combi/SoundFont tracking.
-   LEFT returns from detail to list.
-   LEFT long press exits via Salamander C5 Lite.

Future work:

-   Part Mute
-   Part Solo

------------------------------------------------------------------------

## Low Priority

### Temporary Playback Engine Abstraction

Further unify temporary playback state handling.

Goals:

-   Share one restoration path for Bluetooth Audio, MIDI playback, and
    future playback engines.
-   Minimize duplicated engine-switch logic.
-   Simplify future maintenance.

------------------------------------------------------------------------

### Runtime Diagnostics Cleanup

Reduce default diagnostic output after stabilization.

Candidates:

-   ACCEL_PROFILE_TRACE
-   ENCODER_TRACE
-   Additional optional runtime diagnostics

------------------------------------------------------------------------

### UI Rendering Optimization

Continue optimizing TFT rendering.

Possible improvements:

-   Reduce redraw artifacts
-   Investigate partial list-region redraw
-   Preserve event-driven rendering philosophy

------------------------------------------------------------------------

## Recently Completed

### 260722

-   Added Arachno GM support.
-   Introduced SoundFont-specific Combi definition files.
-   Added runtime SoundFont selection for Combi.
-   Improved Combi navigation and exit workflow.
-   Preserved active Combi across browser and detail views.
-   Added IPv4 display to Wi-Fi status.
-   Improved Media Player / Yoshimi interaction.
-   Temporarily uses GeneralUser GS for MIDI playback while preserving
    Yoshimi.
-   Restores the previous Yoshimi patch when leaving Media Player.
-   Improved Bluetooth Audio and Media Player restoration workflow.
-   Displays the actual playback SoundFont in Now Playing.

------------------------------------------------------------------------

### 260715

-   Added Bluetooth Audio receiver mode under Media Player.
-   Integrated BlueALSA playback.
-   Restored the previous sound engine automatically on exit.
-   Displayed the connected/trusted Bluetooth device name.
-   Refined Bluetooth playback workflow.

------------------------------------------------------------------------

### 260714

-   Stabilized restart-free Yoshimi live loading.
-   Restored reliable Yoshimi patch path selection.
-   Returned Yoshimi CLI to the root context before live loading.
-   Preserved restart fallback only when necessary.

------------------------------------------------------------------------

### 260712

-   Refresh Current Sound now preserves the current UI.
-   Restored reliable live Yoshimi loading after regression.
-   Improved path selection for copied Yoshimi patches.

------------------------------------------------------------------------

### 260710

-   Added Linux Console mode.
-   Improved Power menu.
-   Added privileged console helper support.

------------------------------------------------------------------------

### 260707

-   Persistent Combi performance lock.
-   Faster Combi loading (\~3.7 seconds).
-   Lightweight MIDI Panic.
-   Refresh Current Sound preserves active Combi.
-   Removed redundant Quick Menu items.

------------------------------------------------------------------------

### 260703

-   Added Extension submenu.
-   Added Internet Radio station switching.
-   Added live Yoshimi Arpeggio Speed control.
-   Improved radio playback workflow.

------------------------------------------------------------------------

### 260702

-   Implemented restart-free Yoshimi live loading architecture.
-   Introduced context-aware encoder acceleration.
-   Added automatic ACCELSET synchronization (P0--P3).
-   Added encoder diagnostic tracing.

------------------------------------------------------------------------

### 260701

-   Refresh Current Sound now preserves the current screen.
-   Unified Loading modal behavior.

------------------------------------------------------------------------

### Earlier Milestones

-   Event-driven rendering architecture
-   User Preset system
-   Combi playback engine
-   Internet Radio
-   Wi-Fi manager
-   Console mode
-   Sound Edit
-   UNO-1 ISR encoder
-   Dual-engine (FluidSynth + Yoshimi) architecture
