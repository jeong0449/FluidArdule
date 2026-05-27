# Changelog

All notable changes to the Fluid Ardule project will be documented in this file.

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
