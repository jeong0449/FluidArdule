# SoundFont Setup Guide

This project uses external SoundFont files.  
For licensing and size reasons, **SoundFont files are NOT included in this repository**.  
Please download them manually from the official sources below.

---

## 🎹 Recommended SoundFonts

### 1. FluidR3 GM

- Official source: https://member.keymusician.com/Member/FluidR3_GM/index.html

Download the file and place it in your `~/sf2/` directory.

Recommended filename:
```
FluidR3_GM.sf2
```

---

### 2. GeneralUser GS

- Official source: https://schristiancollins.com/generaluser.php

Download the latest version (e.g. `GeneralUser GS v1.471.sf2`).

After downloading, **rename the file as follows**:

```
GeneralUser GS v1.471.sf2
→ GeneralUser_GS.sf2
```

This project assumes the simplified filename for consistency and easier handling.

---

### 3. SalC5Light2 (Salamander Piano)

- Official source: https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html

Or alternative mirror:
- https://github.com/urish/cinto/blob/master/media/SalC5Light2.sf2

Recommended filename:
```
SalC5Light2.sf2
```

---

## 📂 Directory Structure

Place all downloaded files into:

```
~/sf2/
├── FluidR3_GM.sf2
├── GeneralUser_GS.sf2
└── SalC5Light2.sf2
```

---

## ⚠️ License Notice

Each SoundFont has its own license.  
Please review the terms on the official websites before use.

Do **not** redistribute SoundFont files unless explicitly permitted.

---

## ✔ Summary

- Download SoundFonts manually
- Rename **GeneralUser GS** to `GeneralUser_GS.sf2`
- Place all files in `sf2/`

---

## 🧾 Generate SoundFont Preset JSON

Fluid Ardule uses preset metadata to show SoundFont presets in the UI and to support future Performance storage.

After placing the `.sf2` files in `~/sf2/`, generate preset JSON files using the extended extractor:

```bash
python3 extract_sf2_presets_v2.py ~/sf2/FluidR3_GM.sf2
python3 extract_sf2_presets_v2.py ~/sf2/GeneralUser_GS.sf2
python3 extract_sf2_presets_v2.py ~/sf2/SalC5Light2.sf2
```

This creates JSON files next to each SoundFont:

```
~/sf2/
├── FluidR3_GM.sf2
├── FluidR3_GM.presets.json
├── GeneralUser_GS.sf2
├── GeneralUser_GS.presets.json
├── SalC5Light2.sf2
└── SalC5Light2.presets.json
```

The extended JSON format keeps the original fields used by existing Fluid Ardule code:

```json
{
  "name": "Yamaha Grand Piano",
  "bank": 0,
  "program": 0
}
```

It also adds new metadata for a unified instrument model:

```json
{
  "engine": "fluidsynth",
  "source_type": "sf2",
  "format": "instrument-list",
  "version": 2
}
```

Each preset also receives additional fields such as:

```json
{
  "id": "sf2:FluidR3_GM.sf2:0:0:Yamaha-Grand-Piano",
  "category": "Piano",
  "is_drum": false,
  "sf2": {
    "preset_bag_index": 776,
    "library": 1,
    "genre": 0,
    "morphology": 1607008255
  }
}
```

> [!NOTE]  
> The extended format is designed to remain backward compatible.  
> Existing code that reads `name`, `bank`, and `program` can continue to work.

---

## 🎛 Yoshimi Patch Setup

Fluid Ardule may also use Yoshimi as an alternative synthesis engine.

Unlike SoundFonts, Yoshimi does not use a single `.sf2` file.  
Instead, it stores instrument patches as `.xiz` files, usually grouped into bank directories.

Typical Yoshimi bank location:

```bash
/usr/share/yoshimi/banks
```

To generate a Fluid Ardule-compatible patch list, use:

```bash
python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks -o ~/sf2/yoshimi.patches.json
```

This creates:

```
~/sf2/yoshimi.patches.json
```

The script:

- scans `.xiz` patch files
- treats folders as banks/categories
- extracts patch names from filenames
- assigns `bank` and `program` values for UI compatibility
- writes the same `instrument-list` format used by the extended SF2 preset JSON

Example Yoshimi JSON entry:

```json
{
  "id": "yoshimi:Pads:1:Warm-Pad",
  "name": "Warm Pad",
  "bank": 0,
  "program": 1,
  "category": "Pads",
  "is_drum": false,
  "yoshimi": {
    "bank_name": "Pads",
    "bank_number": 0,
    "patch_file": "0001-Warm Pad.xiz",
    "patch_path": "/usr/share/yoshimi/banks/Pads/0001-Warm Pad.xiz"
  }
}
```

---

## 🔗 Unified Instrument Model

Both SoundFont presets and Yoshimi patches are normalized into the same basic structure:

```text
engine + bank + program + name + id
```

This allows Fluid Ardule to use the same UI concepts for both engines:

- preset/patch selection
- Part Edit
- Performance save/load
- future engine switching

Conceptually:

```text
SF2 preset   → sampled instrument
Yoshimi patch → synthesized instrument
Performance → playable state built from an instrument plus Part Edit settings
```

---

## ✔ Extended Setup Summary

- Download SoundFonts manually
- Rename **GeneralUser GS** to `GeneralUser_GS.sf2`
- Place all SoundFonts in `~/sf2/`
- Run `extract_sf2_presets_v2.py` for each `.sf2`
- If using Yoshimi, run `extract_yoshimi_patches.py`
- Keep generated JSON files together with the sound source files
