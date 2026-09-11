# Fluid Ardule Combination System Design

Created: 2026-05-09\
Updated: 2026-09-11\
Reference runtime: `launch_fluidardule.py`, version 260910u\
Combi definition format: `fluid-ardule-combi-list`, version 1\
Status: **implemented / experimental, resident-GM architecture**

## Overview

This document defines the **Combination (Combi)** sound system for Fluid
Ardule as implemented in the 2026-09-10 runtime series.

A Combi is a lightweight workstation-style performance configuration
made from multiple MIDI parts. It supports both layered sounds and
keyboard splits while preserving the project's design philosophy:

-   hardware-oriented
-   simple to operate
-   fast to access
-   musically focused
-   minimal menu depth
-   low runtime overhead

The current implementation loads Combi definitions from a single JSON
file, applies bank/program/volume settings to internal FluidSynth MIDI
channels, duplicates incoming CH1 keyboard performance data to the
required parts, filters notes by key range, supports transpose, honors
mute/solo flags, forwards performance controllers and Pitch Bend, and
preserves CH10 drum-pad input.

A major architectural change from the early v0.1 design is that **the
Combi JSON no longer contains a SoundFont filename or SoundFont-specific
preset ID**. The same Combi definition can therefore be used with any of
the supported resident GM SoundFonts selected at runtime.

The Combi system remains intentionally lightweight and avoids becoming a
full DAW-like environment.

------------------------------------------------------------------------

# 1. Definition of Combination Sound

A **Combination (Combi)** is a performance configuration consisting of
multiple sound layers and/or keyboard splits.

Internally, a Combination is implemented as a collection of MIDI routing
rules and GM-compatible bank/program references.

The Combination system includes both:

-   layered sounds
-   keyboard splits

Therefore:

``` text
Layer
= overlapping key ranges

Split
= separated key ranges

Combination
= generalized multi-part structure containing both
```

No separate "Layer Mode" or "Split Mode" is required.

------------------------------------------------------------------------

# 2. Implementation Status

## 2.1 Current implementation

The current implementation supports:

-   `/home/pi/sf2/user_combis.json`
-   `fluid-ardule-combi-list` format version 1
-   up to 4 parts per Combi
-   SoundFont-independent Combi definitions
-   runtime selection of a resident GM SoundFont for Combi playback
-   bank/program-based sound assignment
-   channel-based part assignment
-   per-part volume
-   `key_low` / `key_high` range filtering
-   transpose-aware note routing
-   Note Off tracking for stable split/transpose behavior
-   per-part `mute` and `solo` flags
-   CH1 keyboard input duplication to Combi part channels
-   CC forwarding from the input keyboard to active Combi part channels
-   Pitch Bend forwarding
-   CH10 drum-pad preservation
-   Combi browsing and audible preview
-   Combi load/confirmation workflow
-   Home-screen display of the currently loaded Combi

## 2.2 Stability notes

Current testing and implementation history indicate:

-   2-part and 3-part layers are the normal operating range.
-   Up to 4 parts are supported by the format and runtime.
-   Heavy multi-part routing increases Python-side MIDI processing load.
-   Direct ALSA MIDI routes to FluidSynth must be disconnected while the
    Python Combi router is active, otherwise unfiltered notes can bypass
    split logic.
-   Serial traffic and unnecessary TFT redraws should be kept out of
    high-frequency MIDI paths.

## 2.3 Future work

Possible future extensions include:

-   Combi save/edit UI
-   interactive per-part mute/solo controls
-   part volume editing
-   key-range editing
-   transpose editing
-   velocity curves
-   zone crossfade
-   drum remap
-   advanced MIDI effects

------------------------------------------------------------------------

# 3. Fundamental Design Principles

## 3.1 SoundFont-independent Combi definitions

The current Combi file deliberately does **not** identify a SoundFont.

A part is defined by ordinary MIDI-oriented parameters such as:

-   `bank`
-   `program`
-   `channel`
-   `volume`
-   `key_low`
-   `key_high`
-   `transpose`

The `label` field is human-readable metadata. It does not bind the part
to a particular SoundFont file.

Example:

``` json
{
  "role": "layer",
  "label": "Warm Pad",
  "bank": 0,
  "program": 89,
  "channel": 2,
  "volume": 68,
  "key_low": 21,
  "key_high": 127,
  "transpose": 0,
  "mute": false,
  "solo": false
}
```

This means that the Combi stores the **musical/routing structure**, not
a dependency on a specific SF2 file.

## 3.2 Resident GM SoundFont architecture

Fluid Ardule keeps a GM SoundFont resident in FluidSynth. The current
runtime provides the following Combi SoundFont choices:

``` text
FluidR3_GM
GeneralUser_GS
Arachno_GM
```

The selected Combi SoundFont is a **runtime choice**, not a property
stored in `user_combis.json`.

When a Combi part is applied, Fluid Ardule selects its bank/program on
the resident GM SoundFont ID. Therefore the same FCxxx Combi definition
can be auditioned using different supported GM SoundFonts without
modifying the JSON.

This design avoids embedding SoundFont filenames in every Combi and
separates two concerns:

``` text
Combi definition
= musical structure + MIDI bank/program + routing

Resident GM SoundFont
= actual sample/instrument implementation used to render it
```

## 3.3 Labels versus actual patches

A `label` such as `Yamaha Grand Piano`, `Warm Pad`, or `Fingered Bass`
documents the intended GM sound.

The authoritative selection values are `bank` and `program`. Because
different GM SoundFonts may differ slightly in timbre or naming, the
audible result can vary while the Combi structure remains unchanged.

## 3.4 Channel duplication architecture

The Combination engine treats CH1 as the main keyboard performance input
and routes notes to internal FluidSynth channels.

Example:

``` text
Input CH1 note
  → Part 1 → CH1
  → Part 2 → CH2
  → Part 3 → CH3
  → Part 4 → CH4
```

Each part can have its own:

-   bank/program
-   channel
-   volume
-   key range
-   transpose
-   mute/solo state

## 3.5 CH10 drum preservation

Some keyboard controllers send drum-pad events on CH10.

In Combi mode, CH10 is preserved separately from the CH1 layer/split
router:

``` text
CH1 keyboard notes
  → routed through Combi engine

CH10 drum-pad notes
  → passed to FluidSynth CH10
```

FluidSynth CH10 is explicitly prepared as a drum channel using the
resident GM SoundFont.

------------------------------------------------------------------------

# 4. JSON Structure

## 4.1 Combination file

Current file:

``` text
/home/pi/sf2/user_combis.json
```

Top-level structure:

``` json
{
  "format": "fluid-ardule-combi-list",
  "version": 1,
  "engine": "fluidsynth",
  "max_parts": 4,
  "input_channel": 1,
  "combinations": []
}
```

There is intentionally **no `sf2` field** at the top level or inside
individual Combi definitions.

## 4.2 Layer example

``` json
{
  "id": "FC001",
  "name": "Piano + Warm Pad",
  "description": "Basic full-range piano layer with soft pad.",
  "parts": [
    {
      "role": "base",
      "label": "Yamaha Grand Piano",
      "bank": 0,
      "program": 0,
      "channel": 1,
      "volume": 105,
      "key_low": 21,
      "key_high": 127,
      "transpose": 0,
      "mute": false,
      "solo": false
    },
    {
      "role": "layer",
      "label": "Warm Pad",
      "bank": 0,
      "program": 89,
      "channel": 2,
      "volume": 68,
      "key_low": 21,
      "key_high": 127,
      "transpose": 0,
      "mute": false,
      "solo": false
    }
  ]
}
```

## 4.3 Split example

``` json
{
  "id": "FC007",
  "name": "Bass / Piano Split",
  "description": "Lower fingered bass and upper piano.",
  "parts": [
    {
      "role": "lower",
      "label": "Fingered Bass",
      "bank": 0,
      "program": 33,
      "channel": 1,
      "volume": 105,
      "key_low": 21,
      "key_high": 47,
      "transpose": 0,
      "mute": false,
      "solo": false
    },
    {
      "role": "upper",
      "label": "Yamaha Grand Piano",
      "bank": 0,
      "program": 0,
      "channel": 2,
      "volume": 105,
      "key_low": 48,
      "key_high": 127,
      "transpose": 0,
      "mute": false,
      "solo": false
    }
  ]
}
```

------------------------------------------------------------------------

# 5. Combination Parameters

## 5.1 Top-level parameters

  Parameter         Description
  ----------------- -----------------------------------------------
  `format`          Format identifier: `fluid-ardule-combi-list`
  `version`         Combi-list format version
  `engine`          Playback engine; currently `fluidsynth`
  `max_parts`       Maximum number of parts defined by the format
  `input_channel`   Main keyboard input channel
  `combinations`    List of Combi definitions

## 5.2 Combi parameters

  Parameter       Description
  --------------- -----------------------------------------
  `id`            Stable Combi identifier such as `FC001`
  `name`          Combi name shown in the UI
  `description`   Human-readable description
  `parts`         List of Combi parts

## 5.3 Part parameters

  Parameter     Description
  ------------- -----------------------------------------------------------
  `role`        Musical/UI role such as `base`, `layer`, `upper`, `lower`
  `label`       Human-readable intended instrument name
  `bank`        MIDI bank number
  `program`     MIDI program number
  `channel`     Internal FluidSynth MIDI channel, 1-based in the JSON
  `volume`      Per-part channel volume, 0--127
  `key_low`     Lowest accepted MIDI note
  `key_high`    Highest accepted MIDI note
  `transpose`   Semitone offset
  `mute`        Exclude this part when true
  `solo`        If any part is soloed, only soloed parts remain eligible

## 5.4 Parameters deliberately not stored

The current format deliberately does not store:

-   SoundFont filename
-   SoundFont ID
-   SoundFont-specific `preset_id`
-   synth-engine process state

This keeps Combi definitions portable across the supported resident GM
SoundFonts.

------------------------------------------------------------------------

# 6. MIDI Routing Behavior

## 6.1 Notes

Incoming CH1 Note On/Off events are routed to active Combi parts
according to:

``` text
key_low <= note <= key_high
```

If the note is inside the part range:

``` text
output_note = input_note + transpose
output_channel = part.channel
```

Note Off must be sent to the same output channel and transposed note
used by the corresponding Note On. The router therefore tracks active
note mappings.

## 6.2 Mute and Solo filtering

Part eligibility is evaluated before key-range routing.

``` text
If one or more parts have solo=true:
    keep only soloed parts

Then:
    discard any part with mute=true
    apply key-range filtering
```

Thus mute/solo are part of the current data model and routing behavior,
even though a complete interactive edit UI may still be expanded later.

## 6.3 Controllers

Normal performance controllers from CH1 are forwarded to active Combi
channels as appropriate.

Examples include:

-   CC1 Modulation
-   CC64 Sustain
-   CC11 Expression
-   other keyboard performance CC messages

Per-part CC7 volume is established from the Combi definition and should
not be unintentionally overwritten by raw controller forwarding.

## 6.4 Pitch Bend

Pitch Bend from CH1 is forwarded to active Combi part channels so
layered and split sounds respond naturally to the keyboard pitch-bend
wheel.

## 6.5 CH10 drum input

CH10 is preserved for drum-pad use and is prepared as a standard GM drum
channel on the resident GM SoundFont.

------------------------------------------------------------------------

# 7. SoundFont Behavior

## 7.1 Combi does not own a SoundFont

Earlier versions of this design associated a Combi directly with a
specific SF2 file. That model is obsolete.

The current rule is:

> **A Combi definition does not select, name, or reload a SoundFont.**

`user_combis.json` contains no SoundFont filename. SoundFont selection
is handled separately by the Fluid Ardule runtime.

## 7.2 Runtime Combi SoundFont selection

The current runtime provides a set of GM SoundFont choices for Combi
playback:

``` text
FluidR3_GM
GeneralUser_GS
Arachno_GM
```

Changing this selection changes the resident GM SoundFont used to render
the same bank/program-based Combi definitions.

Conceptually:

``` text
user_combis.json
        │
        │  bank / program / channel / range
        ▼
   Combi router
        │
        ▼
selected resident GM SoundFont
        │
        ▼
    FluidSynth
```

## 7.3 Channel setup

For each part, the runtime applies:

``` text
resident GM SoundFont ID
+ bank
+ program
+ channel volume
```

A part therefore does not require a SoundFont-specific preset
identifier.

## 7.4 Why this architecture is preferred

Advantages include:

-   no SF2 filename duplication in Combi data
-   no SoundFont-specific `preset_id` dependency
-   easier comparison of GM SoundFonts using the same Combi
-   simpler Combi JSON
-   clearer separation of musical configuration from synthesis resources
-   less unnecessary SoundFont reloading during normal Combi selection

------------------------------------------------------------------------

# 8. UI Design Philosophy

## 8.1 Avoid exposing unnecessary implementation detail

Internally, Combination uses part-based routing and resident SoundFont
IDs.

The user interface should remain musical rather than
engineering-oriented. Preferred role language includes:

``` text
Base
Layer
Upper
Lower
Bass
Pad
Strings
```

rather than unnecessary technical labels such as `Zone A`.

## 8.2 SoundFont choice is separate from Combi identity

The selected Combi SoundFont may be shown in the Combi browser/runtime
UI, but it is not part of the saved Combi identity.

For example, `FC001 Piano + Warm Pad` remains FC001 whether rendered
with Arachno_GM, FluidR3_GM, or GeneralUser_GS.

------------------------------------------------------------------------

# 9. Current UI Structure

## 9.1 Top-level entry

The Sound area provides access to ordinary sounds, presets, and Combi
operation. Exact menu wording may evolve, but Combi remains a
performance-level sound configuration rather than a separate synthesis
engine.

## 9.2 Combi browser

In the current runtime, entering the Combi browser immediately previews
the highlighted Combi so the audible state matches the current
highlight. Subsequent navigation likewise allows rapid auditioning.

The browser also maintains a separate Combi SoundFont selection. Cycling
the Combi SoundFont keeps the same Combi ID highlighted where possible
and re-auditions the definition using the newly selected resident GM
SoundFont.

This differs from the early design in which `RIGHT` was proposed as an
explicit Preview command. That proposal is no longer the authoritative
behavior.

## 9.3 Load behavior

A Combi can be confirmed as the active performance configuration after
auditioning. The loaded state records the Combi identity and the runtime
SoundFont choice separately.

## 9.4 Home-screen display

When a Combi is active, the Home screen should represent the Combi as
the current performance state rather than merely displaying the last
ordinary preset.

------------------------------------------------------------------------

# 10. Relationship with Sound Edit and User Presets

The early design proposed that each Combi part would reference a User
Preset, which in turn could restore its own Sound Edit state.

The current architecture is deliberately simpler:

``` text
Combination Part
  → bank/program on resident GM SoundFont
  → channel volume
  → key range
  → transpose
  → mute/solo
```

This keeps Combi loading lightweight and independent of User Preset
files.

A future version may add richer per-part sound editing, but it should
not reintroduce unnecessary SoundFont filename coupling into the Combi
definition.

------------------------------------------------------------------------

# 11. Reverb, Chorus, and Controller State

FluidSynth is channel-aware, so different Combi channels can in
principle maintain different controller states.

The current runtime establishes a predictable controller baseline for
Combi part channels when a Combi is applied. This is important because a
channel may otherwise inherit controller values from previous use.

Future Combi editing may expose per-part effect sends or related
parameters, but such extensions should remain optional and should not
complicate the basic bank/program/range model unnecessarily.

------------------------------------------------------------------------

# 12. Mute and Solo

`mute` and `solo` are now part of the Combi JSON schema and are honored
by the routing logic.

Behavior:

``` text
Solo
= if any part is soloed, only soloed parts are considered

Mute
= a muted part is excluded from routing
```

These fields are useful for:

-   checking layers individually
-   balancing a Combi during development
-   debugging split ranges
-   preparing future runtime edit controls

A richer panel UI for changing these values interactively can be added
independently of the underlying format.

------------------------------------------------------------------------

# 13. Current Example Library

The current `user_combis.json` contains ten example definitions:

``` text
FC001  Piano + Warm Pad
FC002  Rhodes + Slow Strings
FC003  Grand + Strings + Choir
FC004  Big Layer Pad
FC005  Organ + Choir
FC006  Rock Organ + Guitar
FC007  Bass / Piano Split
FC008  Bass / EP + Pad Split
FC009  Base Piano + Bass Split
FC010  Base EP + Brass Split
```

These examples cover:

-   full-range 2-part layers
-   3-part layers
-   a 4-part layer
-   conventional lower/upper splits
-   full-range base sounds with range-limited added parts

Because the definitions contain no SoundFont filename, the same library
can be auditioned against each supported resident GM SoundFont.

------------------------------------------------------------------------

# 14. Runtime Stability Notes

The Combi router increases Python-side MIDI processing compared with a
direct ALSA MIDI connection.

Important implementation considerations include:

-   disconnect direct MIDI routes to FluidSynth before starting the
    Combi router
-   prevent bypass paths that defeat split filtering
-   keep serial writes out of high-frequency MIDI routing paths
-   limit unnecessary TFT redraw activity
-   maintain correct Note On/Note Off mapping after transpose
-   preserve CH10 drum routing
-   establish predictable controller state when applying a Combi
-   avoid unnecessary SoundFont reloads

The current runtime also throttles Combi-related background rendering to
reduce display-side overhead on Raspberry Pi 3B.

------------------------------------------------------------------------

# 15. Design Evolution

## 15.1 Early v0.1 concept

The original implementation/design assumed:

``` text
Combi
  → specific SoundFont
  → SoundFont-specific preset reference
```

and examples explicitly contained fields such as:

``` json
"sf2": "FluidR3_GM.sf2"
```

and SoundFont-specific `preset_id` values.

## 15.2 Current architecture

The 2026-09 architecture is:

``` text
Combi
  → SoundFont-independent MIDI structure
       ├ bank/program
       ├ channel
       ├ volume
       ├ key range
       ├ transpose
       └ mute/solo

Runtime
  → selects resident GM SoundFont
  → applies Combi parts to that SoundFont
```

This is a cleaner separation of concerns and better matches Fluid
Ardule's role as a lightweight hardware-oriented performance instrument.

------------------------------------------------------------------------

# 16. Recommended Development Roadmap

## 16.1 Current baseline

-   SoundFont-independent `user_combis.json`
-   10 example Combi definitions
-   resident GM SoundFont architecture
-   bank/program-based part selection
-   up to 4 parts
-   layer support
-   split support
-   CH1 Python-side routing
-   mute/solo routing semantics
-   CC forwarding
-   Pitch Bend forwarding
-   CH10 drum-pad preservation
-   audible Combi browsing/preview
-   active Combi state display

## 16.2 Near-term refinement

-   continue stability testing on Raspberry Pi 3B
-   verify 4-part behavior under sustained playing
-   minimize serial and TFT overhead during Combi routing
-   refine Combi browser UI
-   add or refine runtime mute/solo controls
-   improve router diagnostics and logging

## 16.3 Later extensions

-   Combi edit UI
-   Save As
-   part volume editing
-   key-range editing
-   transpose editing
-   optional per-part controller/effect editing

------------------------------------------------------------------------

# 17. Final Notes

The Fluid Ardule Combi system has evolved from a FluidR3_GM-specific
experiment into a more general **SoundFont-independent performance
structure**.

Its central design rule is now simple:

> **Store the musical structure in the Combi; choose the GM SoundFont at
> runtime.**

This keeps Combi data compact, portable, and easy to maintain while
allowing Fluid Ardule to compare or use different resident GM SoundFonts
without duplicating Combination definitions.

The current implementation demonstrates that Fluid Ardule can function
not only as a SoundFont/MIDI player, but also as a lightweight
performance workstation with layers, splits, resident GM sound
resources, and hardware-oriented operation on Raspberry Pi 3B.
