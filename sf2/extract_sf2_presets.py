#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
extract_sf2_presets.py

Read preset headers (phdr) directly from an SF2 file and export them to JSON.
No third-party Python package is required.

This version writes an extended v2 "instrument-list" format while preserving
the legacy per-preset fields used by existing Fluid Ardule scripts:

    name
    bank
    program
    preset_bag_index
    library
    genre
    morphology

New v2 fields are additive:

Top-level:
    engine
    source_type
    format
    version

Per preset:
    id
    category
    is_drum
    sf2

Output file:
    <same directory>/<soundfont-stem>.presets.json

Example:
    python3 extract_sf2_presets.py /home/pi/sf2/GeneralUser_GS.sf2

Optional:
    python3 extract_sf2_presets.py /home/pi/sf2/GeneralUser_GS.sf2 -o /home/pi/sf2/GeneralUser_GS.presets.json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import BinaryIO


class SF2ParseError(Exception):
    pass


GM_CATEGORY_NAMES = [
    "Piano",
    "Chromatic Percussion",
    "Organ",
    "Guitar",
    "Bass",
    "Strings",
    "Ensemble",
    "Brass",
    "Reed",
    "Pipe",
    "Synth Lead",
    "Synth Pad",
    "Synth Effects",
    "Ethnic",
    "Percussive",
    "Sound Effects",
]


def read_exact(f: BinaryIO, size: int) -> bytes:
    data = f.read(size)
    if len(data) != size:
        raise SF2ParseError(f"Unexpected end of file while reading {size} bytes.")
    return data


def decode_c_string(raw: bytes) -> str:
    raw = raw.split(b"\x00", 1)[0]
    return raw.decode("ascii", errors="replace").strip()


def skip_pad_byte_if_needed(f: BinaryIO, size: int) -> None:
    if size % 2 == 1:
        f.seek(1, 1)


def categorize_preset(bank: int, program: int, name: str = "") -> str:
    """Return a practical GM-style category for UI grouping."""
    if int(bank) == 128:
        return "Drums"
    try:
        return GM_CATEGORY_NAMES[max(0, min(15, int(program) // 8))]
    except Exception:
        return "Other"


def make_instrument_id(source_file: str, bank: int, program: int, name: str) -> str:
    """
    Stable-enough ID for Fluid Ardule Performance references.

    The name suffix helps distinguish rare SF2 files that contain duplicate
    bank/program preset headers.
    """
    safe_name = "-".join((name or "Unnamed").strip().split())
    return f"sf2:{source_file}:{int(bank)}:{int(program)}:{safe_name}"


def find_phdr_chunk(sf2_path: Path) -> bytes:
    """
    Parse RIFF/SFBK structure just enough to locate pdta/phdr.
    """
    with sf2_path.open("rb") as f:
        riff = read_exact(f, 4)
        if riff != b"RIFF":
            raise SF2ParseError("Not a RIFF file.")

        riff_size = struct.unpack("<I", read_exact(f, 4))[0]
        form = read_exact(f, 4)
        if form != b"sfbk":
            raise SF2ParseError("RIFF form is not 'sfbk'; this does not look like a SoundFont 2 file.")

        riff_end = 8 + riff_size

        while f.tell() < riff_end:
            chunk_id = f.read(4)
            if not chunk_id:
                break
            if len(chunk_id) != 4:
                raise SF2ParseError("Corrupted chunk header.")
            chunk_size = struct.unpack("<I", read_exact(f, 4))[0]

            if chunk_id == b"LIST":
                list_type = read_exact(f, 4)
                list_data_end = f.tell() + (chunk_size - 4)

                if list_type == b"pdta":
                    while f.tell() < list_data_end:
                        sub_id = read_exact(f, 4)
                        sub_size = struct.unpack("<I", read_exact(f, 4))[0]
                        if sub_id == b"phdr":
                            data = read_exact(f, sub_size)
                            skip_pad_byte_if_needed(f, sub_size)
                            return data
                        else:
                            f.seek(sub_size, 1)
                            skip_pad_byte_if_needed(f, sub_size)
                else:
                    f.seek(chunk_size - 4, 1)
                    skip_pad_byte_if_needed(f, chunk_size)
            else:
                f.seek(chunk_size, 1)
                skip_pad_byte_if_needed(f, chunk_size)

    raise SF2ParseError("Could not find pdta/phdr chunk in the SF2 file.")


def parse_phdr_records(phdr_data: bytes, source_file: str) -> list[dict]:
    """
    phdr record size = 38 bytes

    struct sfPresetHeader:
        char     achPresetName[20]
        uint16   wPreset
        uint16   wBank
        uint16   wPresetBagNdx
        uint32   dwLibrary
        uint32   dwGenre
        uint32   dwMorphology
    """
    RECORD_SIZE = 38
    if len(phdr_data) % RECORD_SIZE != 0:
        raise SF2ParseError(
            f"phdr chunk size {len(phdr_data)} is not a multiple of {RECORD_SIZE} bytes."
        )

    records = []
    count = len(phdr_data) // RECORD_SIZE

    for i in range(count):
        rec = phdr_data[i * RECORD_SIZE : (i + 1) * RECORD_SIZE]
        name_raw, program, bank, preset_bag_index, library, genre, morphology = struct.unpack(
            "<20sHHHIII", rec
        )
        name = decode_c_string(name_raw)

        # The last record is the terminal preset header "EOP" and should be ignored.
        if name == "EOP":
            continue

        category = categorize_preset(bank, program, name)
        is_drum = bank == 128

        # Keep legacy fields at the top level for current launch_fluidardule.py compatibility.
        records.append(
            {
                "id": make_instrument_id(source_file, bank, program, name),
                "name": name,
                "bank": bank,
                "program": program,
                "category": category,
                "is_drum": is_drum,

                # Legacy SF2 fields retained.
                "preset_bag_index": preset_bag_index,
                "library": library,
                "genre": genre,
                "morphology": morphology,

                # Engine-specific detail block for future common instrument-list handling.
                "sf2": {
                    "preset_bag_index": preset_bag_index,
                    "library": library,
                    "genre": genre,
                    "morphology": morphology,
                },
            }
        )

    # Sort for stable JSON output.
    records.sort(key=lambda x: (x["bank"], x["program"], x["name"].lower()))
    return records


def build_output(sf2_path: Path, presets: list[dict]) -> dict:
    melodic_count = sum(1 for p in presets if not p.get("is_drum", False))
    drum_count = sum(1 for p in presets if p.get("is_drum", False))

    return {
        # New common metadata.
        "engine": "fluidsynth",
        "source_type": "sf2",
        "format": "instrument-list",
        "version": 2,

        # Legacy metadata retained.
        "source_file": sf2_path.name,
        "source_path": str(sf2_path),
        "preset_count": len(presets),
        "melodic_preset_count": melodic_count,
        "drum_preset_count": drum_count,

        "presets": presets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract preset information from an SF2 file and save it as JSON."
    )
    parser.add_argument("sf2_file", help="Path to the .sf2 file")
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output JSON path. Default: <sf2_file_stem>.presets.json in the same directory",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON without indentation",
    )
    args = parser.parse_args()

    sf2_path = Path(args.sf2_file).expanduser().resolve()
    if not sf2_path.exists():
        print(f"ERROR: File not found: {sf2_path}", file=sys.stderr)
        return 1
    if sf2_path.suffix.lower() != ".sf2":
        print(f"WARNING: File does not end with .sf2: {sf2_path}", file=sys.stderr)

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else sf2_path.with_suffix(".presets.json")
    )

    try:
        phdr_data = find_phdr_chunk(sf2_path)
        presets = parse_phdr_records(phdr_data, sf2_path.name)
        payload = build_output(sf2_path, presets)
    except SF2ParseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: Unexpected failure: {exc}", file=sys.stderr)
        return 3

    with output_path.open("w", encoding="utf-8") as f:
        if args.compact:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print(f"Wrote {output_path}")
    print(f"Format: {payload['format']} v{payload['version']}")
    print(f"Preset count: {payload['preset_count']}")
    print(f"Melodic presets: {payload['melodic_preset_count']}")
    print(f"Drum presets: {payload['drum_preset_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
