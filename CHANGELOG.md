# Changelog

All notable changes to the Fluid Ardule project will be documented in this file.

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
