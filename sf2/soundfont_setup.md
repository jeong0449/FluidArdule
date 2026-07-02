# SoundFont Setup Guide

This project uses external SoundFont files.\
For licensing and size reasons, **SoundFont files are NOT included in
this repository**.\
Please download them manually from the official sources below.

------------------------------------------------------------------------

## 🎹 Recommended SoundFonts

### 1. FluidR3 GM

-   Official source:
    https://member.keymusician.com/Member/FluidR3_GM/index.html

Download the file and place it in your `~/sf2/` directory.

Recommended filename:

``` text
FluidR3_GM.sf2
```

### 2. GeneralUser GS

-   Official source: https://schristiancollins.com/generaluser.php

Download the latest version (e.g. `GeneralUser GS v1.471.sf2`).

After downloading, rename the file:

``` text
GeneralUser GS v1.471.sf2
→ GeneralUser_GS.sf2
```

### 3. SalC5Light2 (Salamander Piano)

-   Official source:
    https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html

Alternative mirror:

-   https://github.com/urish/cinto/blob/master/media/SalC5Light2.sf2

Recommended filename:

``` text
SalC5Light2.sf2
```

------------------------------------------------------------------------

## 📂 Directory Structure

``` text
~/sf2/
├── FluidR3_GM.sf2
├── GeneralUser_GS.sf2
└── SalC5Light2.sf2
```

------------------------------------------------------------------------

## ⚠️ License Notice

Each SoundFont has its own license.

Please review the terms on the official websites before use.

Do **not** redistribute SoundFont files unless explicitly permitted.

------------------------------------------------------------------------

## 🧾 Generate SoundFont Preset JSON

``` bash
python3 extract_sf2_presets_v2.py ~/sf2/FluidR3_GM.sf2
python3 extract_sf2_presets_v2.py ~/sf2/GeneralUser_GS.sf2
python3 extract_sf2_presets_v2.py ~/sf2/SalC5Light2.sf2
```

This generates:

``` text
~/sf2/
├── FluidR3_GM.presets.json
├── GeneralUser_GS.presets.json
└── SalC5Light2.presets.json
```

The extended JSON format remains backward compatible while adding
metadata for the unified instrument model.

------------------------------------------------------------------------

## 🎛 Yoshimi Patch Setup

Fluid Ardule can also use **Yoshimi** as an alternative synthesis
engine.

Unlike SoundFonts, Yoshimi stores instruments as individual `.xiz` patch
files organized into bank directories.

Typical bank location:

``` bash
/usr/share/yoshimi/banks
```

Prepare Yoshimi for Fluid Ardule with:

``` bash
python3 extract_yoshimi_patches.py \
    /usr/share/yoshimi/banks \
    -o ~/sf2/yoshimi.patches.json
```

The extractor performs two tasks:

1.  Creates a CLI-safe symbolic-link repository in `~/sf2/yoshimi_links`
2.  Generates the Fluid Ardule patch database

Result:

``` text
~/sf2/
├── yoshimi.patches.json
└── yoshimi_links/
    ├── Pads__0001-Warm-Pad.xiz
    ├── Piano__0003-Grand-Piano.xiz
    └── ...
```

Using symbolic links avoids problems caused by spaces in original
Yoshimi filenames while preserving the original bank organization.

The generated JSON references the symbolic-link paths so Fluid Ardule
can load patches reliably during live instrument switching.

The extractor:

-   scans `.xiz` patch files
-   creates safe symbolic links
-   treats folders as banks/categories
-   extracts patch names
-   assigns `bank` and `program`
-   writes the same `instrument-list` format used by the SF2 preset JSON

Example:

``` json
{
  "id": "yoshimi:Pads:1:Warm-Pad",
  "name": "Warm Pad",
  "path": "/home/pi/sf2/yoshimi_links/Pads__0001-Warm-Pad.xiz",
  "original_path": "/usr/share/yoshimi/banks/Pads/0001-Warm Pad.xiz",
  "bank": 0,
  "program": 1,
  "category": "Pads",
  "is_drum": false
}
```

------------------------------------------------------------------------

## 🔗 Unified Instrument Model

``` text
engine + bank + program + name + id
```

Both SF2 presets and Yoshimi patches share the same logical model,
allowing common UI components for:

-   preset/patch selection
-   Part Edit
-   Performance save/load
-   future engine switching

Conceptually:

``` text
SF2 preset    → sampled instrument
Yoshimi patch → synthesized instrument
Performance   → playable state built from an instrument plus Part Edit settings
```

------------------------------------------------------------------------

## ✔ Extended Setup Summary

-   Download SoundFonts manually
-   Rename **GeneralUser GS** to `GeneralUser_GS.sf2`
-   Place all SoundFonts in `~/sf2/`
-   Run `extract_sf2_presets_v2.py` for each `.sf2`
-   Run `extract_yoshimi_patches.py` to generate both the Yoshimi patch
    database and the symbolic-link repository
-   Keep the generated JSON files together with the sound source files
