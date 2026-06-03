# Fluid Ardule Combination System Design

Created: 2026-05-09  
Updated: 2026-06-03  
Status: **v0.1 implemented / experimental**

## Overview

This document defines the **Combination (Combi)** sound system for Fluid Ardule.

The original goal was to extend the User Preset system into a lightweight workstation-style performance architecture while preserving the project's existing design philosophy:

- hardware-oriented
- simple to operate
- fast to access
- musically focused
- minimal menu depth

As of 2026-06-03, a first working implementation has been tested. The system can load Combi definitions from JSON, apply multiple FluidR3_GM presets to internal MIDI channels, duplicate incoming keyboard performance data, support layer/split behavior, preserve CH10 drum-pad input, and display the currently loaded Combi on the Home screen.

The Combi system remains intentionally lightweight and avoids becoming a full DAW-like environment.

---

# 1. Definition of Combination Sound

A **Combination (Combi)** is a performance configuration consisting of multiple sound layers and/or keyboard splits.

Internally, a Combination is implemented as a collection of MIDI routing rules and SoundFont preset references.

The Combination system includes both:

- layered sounds
- keyboard splits

Therefore:

```text
Layer
= overlapping key ranges

Split
= separated key ranges

Combination
= generalized multi-part structure containing both
```

No separate "Layer Mode" or "Split Mode" is required.

---

# 2. Implementation Status

## 2.1 Implemented in v0.1

The current experimental implementation supports:

- `~/sf2/user_combis.json`
- 10 sample Combi definitions
- FluidR3_GM.sf2-based Combi loading
- up to 4 parts per Combi (experimental)
- channel-based part assignment
- Program Change and volume setup per part
- CH1 keyboard input duplication to Combi part channels
- key range filtering using `key_low` and `key_high`
- transpose-aware note routing
- Note Off tracking for stable split/transpose behavior
- CC forwarding from input keyboard to Combi part channels
- Pitch Bend forwarding to Combi part channels
- CH10 drum-pad input preservation
- Combi Preview / Load workflow
- Combi Loaded information screen
- Home screen display of the currently loaded Combi name

## 2.1a Stability Notes

Current testing suggests:

- 2-part and 3-part layers are generally stable
- 4-part layers remain experimental
- Heavy 4-part layering may trigger MIDI routing or serial communication instability
- Additional optimization is required before 4-part layers can be considered production-ready

## 2.2 Still Future Work

The following are not yet implemented or should be treated as future work:

- Combi save/edit UI
- per-part mute/solo UI
- User Preset reference-based Combi parts
- cross-SoundFont Combi
- per-part Sound Edit restoration
- velocity curves
- zone crossfade
- drum remap
- advanced MIDI effects

---

# 3. Fundamental Design Principles

## 3.1 Current v0.1: Based on SoundFont Preset IDs

The original design proposed that Combinations should reference User Presets.

For the first working implementation, Combi parts directly reference FluidR3_GM preset information using:

- `preset_id`
- `bank`
- `program`
- `name`

This was chosen because `FluidR3_GM.presets.json` already provides stable preset metadata and allows immediate implementation without depending on the User Preset editor.

Example:

```json
{
  "preset_id": "sf2:FluidR3_GM.sf2:0:0:Yamaha-Grand-Piano",
  "name": "Yamaha Grand Piano",
  "bank": 0,
  "program": 0
}
```

## 3.2 Future Direction: User Preset References

The longer-term architecture should still move toward referencing User Presets or Edited User Presets.

Future example:

```text
Combi
 ├ Piano (existing User Preset)
 ├ Warm Pad ed1 (edited User Preset)
 └ Finger Bass (existing User Preset)
```

This keeps the architecture clean and modular.

## 3.3 Single SoundFont Limitation

At the current design stage, all Combination parts are assumed to belong to the same SoundFont.

The first implementation is FluidR3_GM.sf2 based.

This simplifies:

- engine management
- preset loading
- startup latency
- state restoration
- UI consistency
- debugging

Future cross-SF2 combinations may be explored later.

## 3.4 Channel Duplication Architecture

The Combination engine is implemented by:

- reading incoming MIDI performance data
- treating CH1 as the main keyboard input
- duplicating notes and controllers to internal MIDI channels
- filtering notes by key range
- routing them to each active Combi part

Example:

```text
Input CH1 note
 → Part 1 → CH1
 → Part 2 → CH2
 → Part 3 → CH3
 → Part 4 → CH4
```

Each channel maintains its own:

- Program Change
- CC state
- Reverb send
- Chorus send
- Sound Edit parameters

This makes Combination implementation relatively lightweight.

## 3.5 CH10 Drum Preservation

Some keyboard controllers send drum-pad events on CH10.

In Combi mode, CH10 should not be absorbed into the CH1 layer/split router.

Recommended behavior:

```text
CH1 keyboard notes
 → routed through Combi engine

CH10 drum pad notes
 → passed through to FluidSynth CH10
```

This preserves drum-pad usability while playing layered/split Combi sounds.

---

# 4. JSON Structure

## 4.1 Combination File

Current file:

```text
/home/pi/sf2/user_combis.json
```

## 4.2 Current v0.1 JSON Example

```json
{
  "name": "Piano + Pad",
  "sf2": "FluidR3_GM.sf2",
  "parts": [
    {
      "role": "Main",
      "preset_id": "sf2:FluidR3_GM.sf2:0:0:Yamaha-Grand-Piano",
      "name": "Yamaha Grand Piano",
      "bank": 0,
      "program": 0,
      "channel": 1,
      "volume": 100,
      "key_low": 21,
      "key_high": 127,
      "transpose": 0
    },
    {
      "role": "Layer",
      "preset_id": "sf2:FluidR3_GM.sf2:0:89:Warm-Pad",
      "name": "Warm Pad",
      "bank": 0,
      "program": 89,
      "channel": 2,
      "volume": 72,
      "key_low": 21,
      "key_high": 127,
      "transpose": 0
    }
  ]
}
```

## 4.3 Split Example

```json
{
  "name": "Bass / Piano Split",
  "sf2": "FluidR3_GM.sf2",
  "parts": [
    {
      "role": "Lower",
      "preset_id": "sf2:FluidR3_GM.sf2:0:33:Fingered-Bass",
      "name": "Fingered Bass",
      "bank": 0,
      "program": 33,
      "channel": 1,
      "volume": 100,
      "key_low": 21,
      "key_high": 47,
      "transpose": 0
    },
    {
      "role": "Upper",
      "preset_id": "sf2:FluidR3_GM.sf2:0:0:Yamaha-Grand-Piano",
      "name": "Yamaha Grand Piano",
      "bank": 0,
      "program": 0,
      "channel": 2,
      "volume": 100,
      "key_low": 48,
      "key_high": 127,
      "transpose": 0
    }
  ]
}
```

---

# 5. Combination Parameters

## 5.1 Implemented Parameters

| Parameter | Description |
|---|---|
| name | Combi name shown in the UI |
| sf2 | Required SoundFont filename |
| parts | List of Combi parts |
| role | UI-facing part role such as Main, Layer, Upper, Lower |
| preset_id | Stable preset identifier from FluidR3_GM.presets.json |
| name | Human-readable preset name |
| bank | MIDI bank number |
| program | MIDI program number |
| channel | Internal FluidSynth MIDI channel |
| volume | Per-part channel volume |
| key_low | Lowest allowed MIDI note |
| key_high | Highest allowed MIDI note |
| transpose | Semitone offset |

## 5.2 Planned Parameters

| Parameter | Description |
|---|---|
| mute | Temporarily disable a part |
| solo | Temporarily isolate a part |
| pan | Optional per-part pan |
| reverb | Optional per-part reverb send |
| chorus | Optional per-part chorus send |

## 5.3 Parameters Deliberately Excluded from v0.1

The following are intentionally excluded from the first design stage:

- velocity curves
- independent per-part Sound Edit override
- arpeggiator
- zone crossfade
- drum remap
- MIDI effects processing

These features can greatly increase state complexity.

---

# 6. MIDI Routing Behavior

## 6.1 Notes

Incoming CH1 Note On/Off events are routed to Combi parts according to:

```text
key_low <= note <= key_high
```

If the note is inside the part range:

```text
output_note = input_note + transpose
output_channel = part.channel
```

Note Off events must be sent to the same output channel and transposed note used by the original Note On.

Therefore, the router should remember active note mappings.

## 6.2 Controllers

The Combi router should forward normal performance controllers from CH1 to all active Combi part channels.

Examples:

- CC1 Modulation
- CC64 Sustain
- CC11 Expression
- CC10 Pan, if needed
- other keyboard performance CC messages

However, CC7 Volume should generally be excluded from raw forwarding because Combi part volume is defined by the Combi itself.

## 6.3 Pitch Bend

Pitch Bend should be forwarded from CH1 to all active Combi part channels.

This allows keyboard pitch bend wheels to work naturally in layered sounds.

## 6.4 CH10 Drum Input

CH10 input should be preserved and passed through to FluidSynth CH10.

This allows drum pads on keyboard controllers to keep working while Combi mode is active.

---

# 7. SoundFont Loading Behavior

Combi loading should avoid unnecessary SoundFont reloads.

Recommended behavior:

```text
Combi Load
  ↓
Check required sf2
  ↓
If required sf2 is already loaded:
    do not reload SoundFont
    apply channel programs/volumes
  ↓
If required sf2 is different:
    load required SoundFont once
    then apply channel programs/volumes
```

Important implementation note:

When switching from RAW MIDI mode to ALSA/Combi routing mode, engine/routing preparation must happen before applying Program Change and volume settings.

Correct order:

```text
Prepare engine and MIDI routing
Apply Program Change / Volume
Start or update Combi router
```

Wrong order:

```text
Apply Program Change / Volume
Restart FluidSynth
→ settings are lost
```

---

# 8. UI Design Philosophy

## 8.1 Avoid Exposing "Parts"

Internally, Combination uses part-based routing.

However, the user interface should avoid overly technical wording.

Preferred UI language:

```text
Main
Layer
Upper
Lower
Bass
Pad
Strings
```

instead of:

```text
Part 1
Part 2
Zone A
```

The instrument should feel musical rather than engineering-oriented.

---

# 9. Current UI Structure

## 9.1 Top-Level Entry

The former `Sound Source` menu should be renamed to `Sound`.

Current structure:

```text
Home
 ├ Sound
 ├ Media Player
 ├ Controls
 ├ MIDI Mode
 ├ DAC
 └ Extension
```

Recommended Sound submenu:

```text
Sound
 ├ SoundFonts
 ├ User Preset
 ├ Combi
 └ Refresh Sound
```

## 9.2 Combi List

Combi list behavior:

```text
ENC       Move highlight
RIGHT     Preview
SELECT    Load / confirm
LEFT      Exit / cancel
```

Rationale:

- `SELECT` should mean real selection/load.
- `RIGHT` is suitable for a secondary action such as Preview.
- `LEFT` should return to the Sound menu.

The Combi list should show a persistent hint line such as:

```text
R Preview   SEL Load   L Exit
```

The hint line should have a stable background strip to avoid flicker.

## 9.3 Preview Behavior

Preview is temporary.

Recommended behavior:

```text
RIGHT
 → temporarily apply highlighted Combi
 → remain in Combi list
 → show PREVIEW state
```

Preview should not automatically occur during list navigation, because Combi loading is heavier than single preset preview.

## 9.4 Load Behavior

Load is confirmed selection.

Recommended behavior:

```text
SELECT
 → load highlighted Combi
 → show Combi Loaded screen
```

## 9.5 Combi Loaded Screen

After a Combi is loaded, the UI should not immediately jump to Home.

Instead, it should show a summary of the loaded Combi:

```text
Combi Loaded

Piano + Pad

Main  : Yamaha Grand Piano
Layer : Warm Pad

L Sound   SEL List
```

The screen should show the active Combi structure and provide a natural path to later edit functions.

Future extension:

```text
L Sound
SEL List
R Edit
```

## 9.6 Home Screen Display

When a Combi is loaded, the Home screen `Sound` field should show the current Combi name rather than the last ordinary SoundFont/Preset.

Example:

```text
Sound
Combi: Piano + Pad
```

This better represents the current performance state.

---

# 10. Relationship with Existing Sound Edit

The original design stated:

```text
Combination Part
 → loads User Preset
 → User Preset restores its own CC/Sound Edit state
```

This remains the desired long-term architecture.

In the current v0.1 implementation, Combi parts directly apply bank/program/volume to channels. Sound Edit state is not yet restored per part.

Future direction:

```text
Combination Part
 → references User Preset
 → User Preset restores Program/Bank and Sound Edit
 → Combi applies key range, transpose, relative volume, mute/solo
```

This preserves edited sounds, effect settings, and synth identity without duplication.

---

# 11. Reverb and Chorus Behavior

Reverb and Chorus are already channel-aware in FluidSynth.

Therefore:

```text
Piano (CH1)  → low reverb
Pad   (CH2)  → high reverb
Bass  (CH3)  → dry
```

can work naturally without requiring a special global Combi effect engine.

In v0.1, reverb and chorus are not yet stored as explicit Combi part parameters.

---

# 12. Mute and Solo

Mute/Solo are considered essential future features.

Reasons:

- verifying layers individually
- balancing layered sounds
- debugging splits
- performance preparation

Recommended behavior:

```text
Solo
= temporarily mute all other active parts

Mute
= temporarily disable only the selected part
```

These states should remain runtime-only at first and not necessarily be saved.

Recommended future UI path:

```text
Combi Loaded
 ├ Mute/Solo
 ├ Edit
 └ Save As
```

---

# 13. Recommended Development Roadmap

## 13.1 v0.1 Completed / Experimental

- Combi JSON load
- 10 sample Combi sounds
- Preview / Load workflow
- Combi Loaded screen
- Home screen Combi name display
- layer support
- split support
- CH1 note routing
- CC forwarding
- Pitch Bend forwarding
- CH10 drum-pad preservation

## 13.2 v0.2 Recommended

- stabilize split behavior
- improve 4-part layer stability
- reduce serial write pressure during Combi routing
- add Combi part view refinements
- add mute/solo runtime controls
- improve router logging and diagnostics
- ensure no direct MIDI bypass leaks into FluidSynth during Combi mode

## 13.3 v0.3 Recommended

- Combi edit UI
- Save As
- part volume editing
- key range editing
- transpose editing
- User Preset reference support

---

# 14. Runtime Stability Notes

The Combi router increases Python-side MIDI processing load.

Observed or plausible stability issues include:

- serial write timeout during heavy routing
- excessive MIDI LED activity messages
- UI heartbeat delay
- direct MIDI connection leakage bypassing split
- engine restart losing channel settings if order is wrong

Recommended mitigation:

- limit `ACT:MIDI` serial messages during Combi mode
- keep serial writes out of high-frequency MIDI routing paths
- prepare engine/routing before applying Combi settings
- avoid automatic preview on list movement
- use explicit Preview and Load actions
- keep Split implementation conservative

---

# 15. Final Notes

The Fluid Ardule Combi system has moved from a future proposal to an experimental working feature.

The design still aims for:

- workstation-like flexibility
- lightweight implementation
- minimal runtime overhead
- simple hardware operation
- compatibility with the existing User Preset architecture

The current v0.1 implementation proves that Fluid Ardule can act not only as a SoundFont player, but also as a lightweight performance workstation with layered and split sounds.
