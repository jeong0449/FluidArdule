# extract_sf2_presets.py

A small utility script that reads preset information from an SF2 file and writes it to JSON.

## Features
- No third-party Python package required
- Reads the `pdta/phdr` section directly from the SF2 file
- Exports at least `bank`, `program`, and `name`
- Writes the JSON file next to the source SF2 by default

## Recommended location in the repository
```text
tools/sf2/extract_sf2_presets.py
```

## Usage
```bash
python3 extract_sf2_presets.py /home/pi/sf2/GeneralUser_GS.sf2
```

By default, this creates:

```bash
/home/pi/sf2/GeneralUser_GS.presets.json
```

To specify the output filename manually:

```bash
python3 extract_sf2_presets.py /home/pi/sf2/GeneralUser_GS.sf2 -o /home/pi/sf2/GeneralUser_GS.custom.json
```

To write compact JSON without indentation:

```bash
python3 extract_sf2_presets.py /home/pi/sf2/GeneralUser_GS.sf2 --compact
```

## Real-world example
```bash
$ python ../extract_sf2_presets.py FluidR3_GM.sf2
Wrote /home/pi/sf2/FluidR3_GM.presets.json
Preset count: 189
Melodic presets: 158
Drum presets: 31
```

## Output structure example
```json
{
  "source_file": "GeneralUser_GS.sf2",
  "source_path": "/home/pi/sf2/GeneralUser_GS.sf2",
  "format": "sf2-preset-list",
  "version": 1,
  "preset_count": 230,
  "melodic_preset_count": 229,
  "drum_preset_count": 1,
  "presets": [
    {
      "name": "Acoustic Grand Piano",
      "bank": 0,
      "program": 0,
      "preset_bag_index": 0,
      "library": 0,
      "genre": 0,
      "morphology": 0
    }
  ]
}
```

## Notes
- Bank 128 is commonly used for drum kits in many SoundFonts.
- The terminal preset header `EOP` is excluded from the output.
- Presets are sorted by `bank`, then `program`, then `name`.

## Why JSON?
JSON is easy to:
- inspect by hand
- cache next to the `.sf2` file
- load from the main Python runtime
- extend later with categories or tags

## Intended role in Fluid Ardule
This script is meant to be an offline or setup-time utility.
The main runtime can load the generated `.presets.json` file without having to parse the SF2 file every time.
