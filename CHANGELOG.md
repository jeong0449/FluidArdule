# Changelog

All notable changes to the Fluid Ardule project will be documented in this file.

Entries are grouped by development date (KST), which may differ from the corresponding Git commit date.

---

## 260712b — Restore reliable Yoshimi live loading path resolution

### Fixed
- Restored the path-selection logic used by stable Yoshimi live loading.
- Preferred space-free local Yoshimi instrument paths before falling back to original source paths.
- Prevented premature selection of source_path entries containing whitespace.
- Preserved restart fallback only when no suitable live-load path is available.
- Returned the Yoshimi CLI to the root context before issuing live instrument load commands.

### Notes
- Compared the Yoshimi implementation across 260702f, 260703g, 260706b, 260707h, and 260710e.
- Confirmed that the original symlink/copy preservation introduced in 260706b had not been removed.
- Identified the regression as a path-selection priority issue rather than a loss of the live-loading architecture.

### Verification
- Pending:
  - Live loading with copied Yoshimi patch paths.
  - No unnecessary Yoshimi restart during patch changes.
  - Arpeggio Speed adjustment followed by successful live patch loading.

---


## 260710d

- Added `Console` to the Power menu for switching the TFT from the Fluid Ardule UI to the Linux framebuffer console.
- Added support for the privileged `/usr/local/sbin/fluidardule-console` helper.
- Console helper execution is checked before the Fluid Ardule main loop exits, preventing silent failures in the systemd service environment.
- Added `Entering console...` and console failure feedback.
- Refined the Power menu layout to fit all actions on one screen.
- Adjusted menu spacing and vertically centered labels within the selection highlight.
- No changes were made to audio engines, MIDI routing, playback, or volume handling.

---

## 260707h — Combi state locking, faster loading, and recovery control cleanup

### Changed

- Added `SCRIPT_VERSION` near the top of `launch_fluidardule.py`.
- Adjusted Power menu highlight text vertical alignment.
- Removed redundant `Return` from Quick menu.
- Reworked Combi mode as a persistent `state.combi_active` performance-lock state.
- Blocked Home and normal Quick menu access while Combi is active.
- Preserved active Combi sound when leaving Combi browser for Sound menu.
- Released Combi only when another sound is explicitly loaded.
- Optimized Combi loading by switching to ALSA sequencer mode before loading the required SoundFont.
- Reduced observed initial Combi load time from about 8.3 s to about 3.7 s.
- Fixed duplicate Combi router startup caused by stale router threads.
- Separated `MIDI Panic` from `Refresh Sound`.
- Made `MIDI Panic` lightweight: no SoundFont reload, no engine restart.
- Made Down long press preserve and reapply the current sound or Combi.
- Added Combi-only Right long press Panic.
- Removed redundant `Refresh Sound` from Quick menu.

### Verified

- Combi lock persists correctly after returning to Sound menu.
- Explicitly loading another sound releases Combi lock.
- Duplicate `Combi router started` logs no longer appear.
- Quick menu Panic no longer reloads SoundFonts.
- Refresh Sound reapplies active Combi without exiting Combi mode.
- Copy-based `yoshimi.patches.json` works with 260707h.
- UNO-2 with AKAI USB MIDI keyboard works.
- Raspberry Pi power status remained `throttled=0x0`.

---

## 260706b

- Improved Sound selection and transition consistency across SoundFont presets, User Presets, and Combis.
- Refined preview/commit behavior to avoid unnecessary duplicate sound loading.
- Improved loading modal handling and startup settling for large SoundFonts.
- Improved smooth Yoshimi patch live loading by preserving symbolic-link paths for instrument selection.

---

## 260703g

### Improved Internet Radio Playback Controls

- Added direct station switching during internet radio playback.
  - UP: previous station
  - DOWN: next station
- Added first/last station boundary feedback.
- Improved Stop behavior so internal sound is restored immediately after radio or media playback.
- Updated the Now Playing footer to display PREV/NEXT controls consistently.

### Added Extension Submenu

- Expanded the Home `Extension` item into a submenu.
- Added `SEL to Expand` guidance to avoid confusion with RIGHT-button navigation.
- Moved the existing Wi-Fi function under Extension.
- Added Arpeggio Speed as a performance control.
- Preserved Extension as an expandable location for future functions.

### Added Live Yoshimi Arpeggio Speed Control

- Added `Arpeggio Speed` to the Extension submenu and Quick Menu.
- Added the current speed value to the Yoshimi Arpeggios preset list.
- Identified Part 1 Effect 2 Echo Delay as the effective repetition-speed control for the tested Yoshimi arpeggio preset.
- Added live Echo Delay control through the running Yoshimi CLI without restarting Yoshimi or reloading the instrument.
- Added an empirically calibrated BPM-like speed mapping:
  - `raw_speed = round((display_bpm - 5.13) / 0.797)`
  - `echo_delay = round(6000 / raw_speed)`
- Changed Arpeggio Speed adjustment from 5-unit steps to 1-unit steps for finer control.
- Added a non-selectable, right-aligned `Rotate Encoder to adjust` hint.
- Separated operational hints from selectable menu rows for clearer UI behavior.

### Documentation

- Added technical documentation for Yoshimi Arpeggio Speed investigation and calibration.
- Updated the user interface documentation for Extension, Arpeggio Speed, Quick Menu access, and long-press shortcuts.

---

## 260702f — Live Yoshimi Instrument Loading

### New

- Replaced Yoshimi restart-based instrument switching with live `load instrument` commands.
- Added persistent stdin control channel for the Yoshimi process.
- Adopted symlink-based Yoshimi instrument JSON to eliminate filename whitespace issues.
- Preserved automatic restart fallback if live loading fails.

### Improvements

- Removed obsolete transition mute workaround and temporary volume ducking.
- Simplified Yoshimi instrument loading workflow.
- Reduced latency during instrument changes.
- Eliminated unnecessary audio interruption during preset changes.

### UI

- Removed redundant "Loading Default" modal.
- Sound Source SELECT now shows only a single loading dialog during engine initialization.

### Maintenance

- Updated Yoshimi control architecture for persistent runtime control.
- Improved maintainability by removing obsolete restart-era code.

---

## 260702c — Context-specific Encoder Acceleration & Input Cleanup

### New

- Added **context-specific encoder acceleration profiles**.
- Defined default acceleration policy by UI context:
  - **P0** – Home / precise navigation
  - **P1** – Preset, Combi, File Browser, Radio Browser
  - **P2** – Continuous parameter editing (CC, Tempo, Volume)
  - **P3** – Manual high-speed override
- Added Pi → UNO-1 **ACCELSET:0–3** protocol.
- UNO-1 now updates and displays the current acceleration profile (P0–P3).
- Current UI acceleration profile is automatically resent after UNO reconnect.

### Diagnostics

- Added optional **Encoder Trace** (`ENCODER_TRACE`) for detailed encoder event logging.
- Added optional **Acceleration Profile Trace** (`ACCEL_PROFILE_TRACE`) for Pi → UNO profile synchronization.

### UI / UX

- Introduced **context-aware encoder behavior** instead of a single global acceleration setting.
- Preserved manual profile override using encoder long press.
- Reserved **P3** as a user-selectable turbo profile rather than using it automatically.

### Cleanup

- Removed obsolete long-press handlers left from previous UI designs.
- Removed unreachable menu/event branches.
- Removed duplicate global variable declarations.
- Simplified encoder and long-press logic for consistency.
- Updated serial protocol documentation for context-specific acceleration profiles.

---

### 260701j

- DOWN long-press sound refresh now keeps the current screen instead of returning to Home.
- Show a loading modal consistently whenever a SoundFont or Yoshimi sound source is reloaded.
- Reduce Yoshimi restart transition noise using brief output attenuation (20% → restart → 30 ms → restore).

---

## 2026-06-29

### Stability

- Improved Yoshimi ⇄ FluidSynth lifecycle handling.
- Added additional cleanup before returning from Yoshimi to FluidSynth.
- Repeated engine switching tests showed stable operation without reproducing the previous delayed-note / Note-Off playback issue.
- Investigated Yoshimi live instrument switching without process restart. The experimental approach was not adopted because it did not reliably update the running instrument.

### User Interface

- Changed User Preset **Manage** shortcut from **DOWN long press** to **LEFT long press**.
- Restored **DOWN long press** as a global action.
- Changed list incremental redraw to refresh the entire list region instead of only the affected rows, reducing highlight artifacts on the TFT display.

### Controls

- **DOWN long press** now performs **Refresh Current Sound** instead of MIDI Panic.
- **MIDI Panic** moved to the top of the Quick Menu as an emergency recovery function.
- Kept encoder long press assigned to encoder acceleration selection.

### Notes

- Yoshimi preview currently restarts the engine when moving between instruments.
- A process-persistent Yoshimi implementation remains a future research topic.

---

## 2026-06-28

### Changed

- Refined preset browsing behavior with page-based navigation for selection lists.
- Preserved the last previewed sound when returning to preset categories.
- Simplified button behavior by making SELECT the primary action button while reserving RIGHT for special navigation cases.
- Reduced visual clutter by displaying navigation markers only on the highlighted item.
- Improved User Preset preview responsiveness and consistency.

## 2026-06-27

### Improved

- Restored USB storage plug-and-play detection while preserving the event-driven rendering architecture. USB mount status is now monitored independently of manual status refresh, providing responsive hot-plug behavior with negligible CPU overhead.

- Refined startup volume handling for safer and more predictable operation.
  - Startup output now begins at a fixed default level (85%).
  - Physical volume control uses soft takeover (±3%) to prevent abrupt level changes when the potentiometer position differs from the startup volume.
  - When the potentiometer reaches the pickup range, a centered **"Volume Active"** popup confirms that hardware volume control has been synchronized.
 
---

## 2026-06-21

### Improved Preset and Combi Workflow

- Added delayed preview for User Presets to avoid repeated loading while scrolling.
- Improved Sound Source and User Preset footer wording.
- Expanded User Preset list display to five rows.
- Added Combi preview feedback in the footer.
- Added Wi-Fi status/config caching to reduce repeated system calls.
- Added Combi apply timing logs.
- Clarified Combi as a performance-oriented workspace rather than a simple preset selection screen.
- Recommended FluidSynth polyphony limiting for stable multi-layer Combi playback.
---

## 2026-06-20

### Event-Driven UI Architecture

This release fundamentally redesigns the Fluid Ardule rendering model.

The TFT display is no longer refreshed continuously. Instead, the UI is updated only when user interaction or specific hardware events require it, significantly reducing CPU utilization while improving real-time audio stability.

#### Rendering

- Replaced periodic TFT redraws with an event-driven rendering model.
- Eliminated unnecessary background screen updates during normal operation.
- Introduced manual system status refresh using **UP long press**.
- System information (CPU load, temperature, DAC, Wi-Fi, etc.) is now refreshed on demand.
- Live MIDI connection status remains the only continuously monitored background exception.

#### Performance

- Greatly reduced Python CPU utilization during playback and live performance.
- Reduced audio glitches caused by excessive framebuffer updates.
- Improved Yoshimi playback stability.
- Improved overall Combi playback stability through lower UI overhead.

#### User Interface

- Improved Sound Source navigation consistency by clarifying the roles of **SELECT** and **RIGHT**.
- Added boundary notifications when reaching the first or last media file.
- Unified transient popup appearance using the existing centered modal style.
- Improved Media Player button label alignment and Resume button appearance.

#### Utilities

- Added `capture_fb1.py`, a framebuffer screenshot utility for documentation, debugging, and manual creation.

#### Reliability

- Documented the Yoshimi zero-byte configuration file issue and recovery procedure.
- Improved graceful shutdown handling for Yoshimi.

----

## [2026-06-16 (KST)]

### Improved Responsiveness

This release significantly improves the responsiveness of Fluid Ardule through coordinated enhancements to both the UNO-1 controller firmware and the Raspberry Pi UI.

#### UNO-1 Firmware

- Replaced the polling-based rotary encoder with an interrupt-driven (ISR) implementation.
- Eliminated missed encoder steps during rapid rotation.
- Tuned encoder transition scaling for more consistent encoder behavior.
- Reduced button debounce time for faster response.

#### Raspberry Pi UI

- Menu navigation now preserves the full encoder delta (`ENC:+/-N`).
- Removed the legacy encoder navigation debounce filter.
- Improved high-speed menu scrolling without losing encoder movement.
- Optimized menu navigation responsiveness while maintaining TFT render throttling for audio stability.

#### Result

- Fast encoder rotation now scrolls multiple menu items naturally.
- Full-screen menu scrolling is smooth and reliable without observable missed steps.
- Overall controller and UI responsiveness have been significantly improved while preserving stable MIDI and audio performance.

---
## [2026-06-03 (KST)] — Implement Combi v0.1

### Added

- Added Combination (Combi) sound system
- Added `~/sf2/user_combis.json`
- Added `Sound → Combi` menu
- Added Combi browser with Preview and Load workflow
- Added Combi information screen after loading
- Added active Combi display on Home screen

### MIDI Routing

- Added MIDI note duplication for layered sounds
- Added keyboard split support using `key_low` / `key_high`
- Added per-part transpose support
- Added per-part volume support
- Added MIDI channel routing engine for Combi playback

### Controller Support

- Added CC forwarding to Combi parts
- Added Modulation Wheel forwarding
- Added Sustain Pedal forwarding
- Added Pitch Bend forwarding
- Preserved CH10 drum pad operation during Combi playback

### User Interface

- Added Preview / Load button hints
- Added Combi cancel and return flow
- Added active Combi status display
- Improved Combi list navigation and selection behavior
- Added Combi summary screen after successful load

### Internal Changes

- Added Combi runtime state management
- Added Combi JSON loading and validation
- Improved FluidSynth restart and Combi initialization sequence
- Fixed first-load initialization timing issues

### Known Limitations

- Mute/Solo not yet implemented
- Combi editor not yet implemented
- Combi save/rename not yet implemented
- Long-term routing stability still under evaluation

---

## [2026-06-02 (KST)]

### Changed
- Refined title-bar context information across submenus for improved UI consistency.
- Removed unrelated SoundFont labels from Media/File/Radio screens.
- Added alternating footer display between UNO link status and current volume.
- Volume value is now shown continuously while the potentiometer is being adjusted.

### Notes
- No changes to MIDI, FluidSynth, Yoshimi, playback, or serial protocol behavior.
- UI-only update focused on status presentation and visual consistency.

---

## [2026-06-01 (KST)] 

- Fixed Software Restart from Power Menu.
- Fixed startup volume regression (POT position now respected).
- Added Internet Radio favorite toggle (RIGHT button).
- Added ★ indicator for favorite stations.

---

## [2026-05-30 (KST)]
### UI

- Home screen now displays Build version and Wi-Fi status.
- Added SSID display with support for:
  - Connected network
  - No Network
  - Wi-Fi Off
- Refined title bar layout and alignment.

### Power Menu

- Added **Restart Software** command.
- Reorganized Power Menu:

  - Cancel
  - Halt
  - Restart Software
  - Reboot

### Recovery

- Fluid Ardule software can now be restarted directly from the UI without rebooting Raspberry Pi.
- Simplifies recovery from MIDI, audio, or UI-related software issues.

### Encoder improvement
Reset encoder transition accumulator on direction reversal to improve first-click responsiveness.

---

## [2026-05-29 (KST)]

- Added LCD reinitialization on first Pi HELLO link establishment.
- Added detachable RESET-GND 10µF startup stabilization capacitor.
- Confirmed that the capacitor may interfere with Arduino auto-reset during sketch upload.
- Approximately 25 consecutive service restart tests completed without LCD garbled-character events.

---

## [2026-05-28 (KST)]

### UNO-1 stability improvement

- Investigated intermittent I2C LCD corruption during Fluid Ardule service restart
- Identified Arduino UNO auto-reset during USB serial reconnect as the root cause
- Added DTR/RTS suppression and serial open holdoff in Python runtime
- Added 10 µF electrolytic capacitor between RESET and GND on UNO-1
- Significantly improved LCD stability during repeated service restart tests

Observed symptoms before the fix:

- Random LCD character corruption
- Partial LCD initialization after reconnect
- Increased instability after repeated restart attempts

---
## [2026-05-27 (KST)]

- Added Wi-Fi selector to Extension menu
- Implemented Wi-Fi ON/OFF control
- Added "Scan known networks" support
- Added selection among visible configured SSIDs
- Switched Wi-Fi selection logic from direct wpa_cli control
  to priority-based reconnect strategy
- Added automatic wpa_supplicant restart after selection
- Improved compatibility with wpa_supplicant@wlan0 systems
- Added network diagnostics documentation
- Documented interface-specific Wi-Fi configuration behavior
- Added quick SSID/IP diagnostic commands
- Documented wpa_cli control socket limitations

---

## [2026-05-26 (KST)]

### Internet Radio

- Added Internet Radio source to Media Player
- Added mpv-based streaming radio playback
- Added curated default radio station list
- Added persistent radio favorites support
- Added Favorites browser inside Internet Radio
- Added RIGHT-button favorite toggle during playback
- Fixed LEFT navigation from radio player back to radio list
- Added separate radio playback state handling
- Renamed "File Player" menu to "Media Player"
- Added lazy initialization for radio JSON files

### UNO-1 Calibration

- Fixed calibration step progression after keypad capture
- Removed EEPROM-based key validation during calibration
- Improved recovery from incorrect stored ADC values
- Reduced false key detection after encoder long-press release
- Improved ADC stabilization and multi-sample averaging
- Reduced unnecessary "Hold exact key" failures
- Improved EEPROM save flow after calibration

---

## [2026-05-24b (KST) ]

### Hotfix
- Improved keypad calibration stability.
- Fixed an issue where calibration could
  accidentally skip to the next button step
  due to ADC release noise.
  
---

## [2026-05-24 (KST) ]

### Added
- Added A0 resistor-ladder keypad calibration mode.
- Added encoder long-press entry for calibration mode.
- Added EEPROM-based storage and loading of calibrated keypad center values.
- Added LCD-guided step-by-step calibration workflow.
- Added “Hold key”, “OK”, and “Release key” feedback during calibration.
- Added LCD blink feedback while measuring keypad ADC values.
- Added release detection before advancing to the next calibration step.
- Added encoder long-press cancel during calibration.
- Added encoder long-press save/exit after successful calibration.

### Changed
- Replaced fixed ADC threshold keypad detection with calibrated nearest-center matching.
- Improved keypad ADC stability using filtered sampling.
- Prevented calibration entry during active playback.
- Added temporary LCD warning when calibration is attempted during playback.
- Suppressed runtime BTN/ENC/POT events during calibration.
- Kept serial link alive during calibration by continuing safe heartbeat/ready signaling.

### Fixed
- Reduced false keypad detection caused by ADC drift.
- Prevented the same held button from being misread as the next calibration step.
- Improved UNO-Pi relink behavior after UNO reset.
- Reduced risk of Pi watchdog/link monitor reacting incorrectly during calibration.

### Notes
- Calibration should be performed while playback is stopped.
- During each calibration step, keep the requested key pressed until the LCD shows OK / Release.
- If calibration is canceled or fails, the previous EEPROM-stored values remain unchanged.

---

## [2026-05-09 (KST)]

### Added
- Added User Preset management features
  - Rename
  - Delete
  - Move to Top
- Added `Refresh Sound`
- Added `▲/▼` overflow hints for list navigation
- Added centered Loading modal

### Changed
- Expanded User Preset from a simple save/load feature into a richer preset workflow
- Distinguished edited presets from bookmarked presets
- Improved `Sound Source > User Preset` SELECT behavior
  - SELECT now loads the first User Preset directly
- Added Sound Source count caching and preload
- Improved rename editor UI with monospaced rendering

### Improved
- Blocked sound source changes during file playback
- Improved sound-state recovery behavior
- Improved Sound Source rendering responsiveness

### Internal
- Added User Preset helper and cache logic
- Cleaned up Sound Source rendering structure

---

## [2026-05-08 (KST)]

### Added
- Added `User Preset` under `Sound Source`
- Added JSON-based user preset storage:
  - `/home/pi/sf2/user_presets.json`
- Added Quick Menu action:
  - `Save User Preset`
- Added automatic preset naming based on:
  - SoundFont/Yoshimi source
  - Original preset name
- Added automatic edit suffix generation:
  - `ed1`, `ed2`, ...
- Added support for storing:
  - engine type
  - SoundFont source
  - bank/program
  - preset name
  - Yoshimi instrument path
  - Sound Edit CC values
- Added support for storing drum presets (`bank 128`)
- Added overwrite confirmation dialog for duplicate preset names
- Added `Press Right` hint for User Preset source entry

### Changed
- Removed fixed-slot limitation for User Presets
- User Presets are now managed as a dynamic JSON list
- User Preset browsing now requires explicit `SELECT` to load
  - No preview during scrolling
  - Prevents repeated engine reloads
- Quick Menu navigation now supports rollover
  - UP on first item wraps to bottom
  - DOWN on last item wraps to top
- Removed redundant `Power` item from Quick Menu
  - Power Menu remains accessible via `SELECT long`

### UI / UX
- Preserved existing long-press muscle memory:
  - `RIGHT long` → Quick Menu
  - `DOWN long` → MIDI Panic
  - `SELECT long` → Power Menu
- Kept SoundFont browser preview behavior unchanged
- User Presets now behave as stable “loadable memories”
  rather than preview-scrolling presets

### Internal
- Added engine-aware User Preset loading
- Added automatic SoundFont/Yoshimi restoration on load
- Preserved existing menu-return consistency
- No changes to UNO-1 button protocol
- No changes to MIDI routing behavior

---

## [2026-05-03 (KST)]

### Major Features

- Added full support for **USB MIDI Cable** as both:
  - ALSA SEQ input device
  - External MIDI output (mirror mode)
- Enabled integration of **DIN keyboard + external sound module** using a single USB MIDI interface
- Introduced **External MIDI OUT (Mirror)** feature under Extension menu
  - Mirrors SEQ input and MIDI file playback to external module
  - Independent from MIDI input mode

### MIDI Mode Improvements

- Refactored MIDI Mode UI:
  - Removed submenu for ALSA device selection
  - Allow direct selection of active ALSA MIDI devices
- Display only **currently connected ALSA inputs** when entering MIDI Mode
- Filtered out non-user ALSA ports:
  - `aseqdump`
  - `Midi Through`
  - `System`
- Preserved existing modes:
  - USB Direct RAW
  - UNO-2 bridge (SEQ)

### UX / Behavior Changes

- External MIDI OUT menu:
  - Visible **only when USB MIDI Cable is connected**
  - Available regardless of input mode (RAW / SEQ)
- Mirror behavior:
  - SEQ input → mirrored
  - MIDI file playback → mirrored
  - RAW input → not mirrored (by design)

### Stability Improvements

- Clear stale ALSA connections at startup:
  - `aconnect -x`
- Prevent routing conflicts during:
  - Script restart
  - Development cycles (Ctrl+C / rerun)
- Maintain stable behavior under systemd execution

### Playback Fixes

- Fixed **stuck notes on external MIDI module** when:
  - Stopping MIDI file playback
  - Pausing playback
- Added external MIDI panic handling:
  - All Sound Off (CC120)
  - All Notes Off (CC123)
- Ensure external module properly resets on stop/pause

### Notes

- RAW mode intentionally keeps direct low-latency path (no mirror for live input)
- Mirror feature is designed as an **output option**, not an input-mode feature
- UI prioritizes stability over dynamic reconfiguration

---



## [2026-04-27 (KST)]

### Added
- Implement full Sound Edit workflow for real-time CC parameter editing
- Add POT mode toggle (VOL ↔ PARAM) via LEFT long press
- Add soft takeover (pickup) for volume control to prevent value jumps
- Add encoder long-press acceleration profile switching (P1–P3) in UNO-1 firmware
- Add temporary footer display (1.2s) for accel and POT mode changes

### Improved
- Apply encoder acceleration only to parameter editing, not menu navigation
- Improve Sound Edit usability with direct POT-based parameter control
- Refine UI consistency: “highlight = control target” principle
- Reduce log verbosity by disabling continuous CC debug output
- Simplify interaction by removing redundant visual indicators

### Changed
- Preset change now re-applies full CC set for consistent sound state
- USB eject moved away from LEFT long press (accessible via Quick Menu)

### Fixed
- Enable MIDI panic (DOWN long press) within Sound Edit context
- Prevent parameter/value jump when switching back to volume control
- Ensure stable interaction between encoder acceleration and UI navigation

---

## [2026-04-25 (KST)]

### Added
- Quick Menu (RIGHT long press)
  - Resume
  - Now Playing
  - Home
  - Sound Source
  - USB Eject
  - Power...
- Now Playing shortcut for instant access to current playback state

### Changed
- UI header policy updated:
  - "Fluid Ardule" title is now shown only on the Home screen
  - Removed from menus, player, and Quick Menu
- Layout adjusted to reclaim header space:
  - Menu content shifted upward
  - Quick Menu now displays all 6 items without scrolling
- Clear separation of concepts:
  - Resume → restores navigation context
  - Now Playing → accesses current playback state
- Long press behavior refined:
  - RIGHT long → Quick Menu
  - DOWN long → Panic (unchanged)
  - SELECT long → Power Menu (unchanged)
  - LEFT/UP long → reserved

### Fixed
- USB boot behavior:
  - Prevented automatic transition to File Player when USB is already mounted at boot

### Performance
- No increase in TFT rendering load
- Existing partial redraw and rate limiting preserved

### Notes
- No regressions in existing features or input handling
- RIGHT short behavior unchanged
- Single-script architecture maintained (modularization planned for future)

---

## [2026-04-24] Yoshimi Integration Milestone

### Added
- Integrated Yoshimi as a secondary synthesis engine alongside FluidSynth
- Added support for JSON v2 instrument format with full Yoshimi compatibility
- Implemented patch loading via `.xiz` files using `yoshimi -L`
- Added automatic engine switching between FluidSynth and Yoshimi
- Restored selected Yoshimi patch after media playback

### Changed
- Extended preset navigation system to support both SoundFont and Yoshimi instruments
- Unified UI flow for bank → instrument browsing across engines
- Displayed contextual navigation hints (e.g., `> Press Right`) on highlighted entries only

### Improved
- Introduced preview mode for Yoshimi patches during navigation
- Added debounce logic to reduce redundant Yoshimi restarts during fast scrolling
- Significantly improved responsiveness and usability of patch selection

### Fixed
- Resolved missing patch path issue by correctly handling nested `yoshimi.patch_path` fields
- Fixed Yoshimi startup behavior to prevent CLI prompt flooding (`yoshimi> @Top`)
- Ensured proper engine restoration after media playback
- Eliminated unintended fallback to FluidSynth when Yoshimi is selected

### Notes
This release marks the completion of dual-engine architecture:
- **FluidSynth** for General MIDI playback and fast preset navigation
- **Yoshimi** for real-time synthesis and advanced patch-based sound design

Fluid Ardule now operates as a hybrid MIDI sound module system combining GM playback and VA synthesis in a single integrated platform.

---

## [2026-04-23]

### Improved
- Redesigned TFT rendering strategy to improve real-time MIDI performance
- Immediate rendering on user input (force render)
- Background rendering is now rate-limited (`RENDER_MIN_INTERVAL`)

### Result
- Significantly reduced audio glitches during live MIDI playback
- Improved stability in both alsa_raw and alsa_seq modes
