# Fluid Ardule Combination System Design

Created: 2026-05-09

## Overview

This document proposes a future **Combination (Combi)** sound system for Fluid Ardule.

The goal is to extend the current User Preset system into a lightweight workstation-style performance architecture while preserving the project's existing design philosophy:

- hardware-oriented
- simple to operate
- fast to access
- musically focused
- minimal menu depth

The proposed Combination system is intentionally lightweight and avoids becoming a full DAW-like environment.

---

# 1. Definition of Combination Sound

A **Combination (Combi)** is a performance configuration consisting of multiple sound layers and/or keyboard splits.

Internally, a Combination is implemented as a collection of MIDI routing rules and User Preset references.

The Combination system includes both:

- Layered sounds
- Keyboard splits

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

# 2. Fundamental Design Principles

## 2.1 Based on Existing User Presets

A Combination does not directly contain SoundFont presets.

Instead, it references already existing:

- User Presets
- Edited User Presets

This keeps the architecture clean and modular.

Example:

```text
Combi
 ├ Piano (existing User Preset)
 ├ Warm Pad ed1 (edited User Preset)
 └ Finger Bass (existing User Preset)
```

---

## 2.2 Single SoundFont Limitation

At the current design stage, all Combination parts are assumed to belong to the same SoundFont.

This simplifies:

- engine management
- preset loading
- startup latency
- state restoration
- UI consistency

Future cross-SF2 combinations may be explored later.

---

## 2.3 Channel Duplication Architecture

The Combination engine is implemented by:

- duplicating incoming MIDI notes
- filtering notes by key range
- routing them to internal MIDI channels

Example:

```text
Input CH1 note
 → Part A → CH1
 → Part B → CH2
 → Part C → CH3
```

Each channel already maintains its own:

- Program Change
- CC state
- Reverb send
- Chorus send
- Sound Edit parameters

This makes Combination implementation relatively lightweight.

---

## 2.4 Separation of Responsibilities

The design intentionally separates:

```text
User Preset
= sound identity

Combination
= performance/routing structure
```

User Presets contain:

- SoundFont selection
- Program/Bank
- edited Sound Edit parameters
- CC settings

Combination parts contain:

- key range
- relative volume
- transpose
- routing information

This avoids state duplication and conflicting parameter ownership.

---

# 3. JSON Structure Proposal

## 3.1 Combination File

Proposed file:

```text
/home/pi/sf2/user_combis.json
```

---

## 3.2 Basic JSON Example

```json
{
  "name": "Piano + Pad Split",
  "sf2": "FluidR3_GM.sf2",
  "parts": [
    {
      "preset": "01 Grand Piano",
      "channel": 1,
      "volume": 100,
      "key_low": 21,
      "key_high": 127,
      "transpose": 0
    },
    {
      "preset": "04*Warm Pad ed1",
      "channel": 2,
      "volume": 75,
      "key_low": 48,
      "key_high": 127,
      "transpose": 0
    }
  ]
}
```

---

# 4. Combination Parameters

## 4.1 Initial Parameters

The first implementation should remain intentionally small.

Recommended parameters:

| Parameter | Description |
|---|---|
| preset | Referenced User Preset |
| channel | Internal MIDI channel |
| volume | Relative volume |
| key_low | Lowest allowed note |
| key_high | Highest allowed note |
| transpose | Semitone offset |
| mute | Temporary mute state |
| solo | Temporary solo state |

---

## 4.2 Parameters Deliberately Excluded

The following are intentionally excluded from the first design stage:

- per-part CC override
- velocity curves
- independent reverb/chorus override
- arpeggiator
- zone crossfade
- drum remap
- MIDI effects processing

These features can greatly increase state complexity.

---

# 5. Relationship with Existing Sound Edit

Combinations do not override Sound Edit values.

Instead:

```text
Combination Part
 → loads User Preset
 → User Preset restores its own CC/Sound Edit state
```

This preserves:

- edited sounds
- effect settings
- synth identity

without duplication.

---

# 6. Reverb and Chorus Behavior

Reverb and Chorus are already channel-aware in FluidSynth.

Therefore:

```text
Piano (CH1)  → low reverb
Pad   (CH2)  → high reverb
Bass  (CH3)  → dry
```

can already work naturally without additional Combination logic.

---

# 7. UI Design Philosophy

## 7.1 Avoid Exposing "Parts"

Internally, Combination uses a part-based structure.

However, the user interface should avoid overly technical wording.

Preferred UI language:

```text
Main Sound
Layer
Split
Upper
Lower
```

instead of:

```text
Part 1
Part 2
Zone A
```

The instrument should feel musical rather than engineering-oriented.

---

# 8. Proposed UI Structure

## 8.1 Top-Level Entry

```text
Sound Source
 ├ SoundFonts
 ├ User Preset
 ├ Combination
 └ Refresh Sound
```

---

## 8.2 Combination Editor

Example:

```text
Combination Edit
Main : Grand Piano
Layer: Warm Pad
Split: Finger Bass
```

---

## 8.3 Split Editing

Example:

```text
Split Point : C3
```

---

## 8.4 Detailed Editor

Internally:

```text
Main Sound
 ├ Preset
 ├ Volume
 ├ Key Low
 ├ Key High
 ├ Transpose
 ├ Mute
 └ Solo
```

---

# 9. Mute and Solo

Mute/Solo are considered essential features.

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

These states should remain runtime-only and not necessarily be saved.

---

# 10. Recommended First Implementation Scope

To avoid over-expansion, the first implementation should include only:

- Combination load/save
- 2-part combinations
- layer and split support
- relative volume
- transpose
- mute/solo
- key range editing

This is already sufficient to create useful workstation-like sounds.

---

# 11. Proposed Internal Module Separation

The Combination system is likely the first Fluid Ardule feature that meaningfully justifies partial file separation.

Recommended structure:

```text
launch_fluidardule.py
fluidardule_combi.py
```

Suggested responsibilities:

## launch_fluidardule.py

- UI
- rendering
- button handling
- menu flow

## fluidardule_combi.py

- Combination JSON
- validation
- MIDI routing
- key filtering
- channel duplication
- Combination runtime state

---

# 12. Final Notes

The proposed Combination system intentionally aims for:

- workstation-like flexibility
- lightweight implementation
- minimal runtime overhead
- simple hardware operation
- compatibility with the existing User Preset architecture

The design should remain focused on practical musical usability rather than unlimited feature expansion.
