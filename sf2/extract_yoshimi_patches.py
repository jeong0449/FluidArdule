#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
extract_yoshimi_patches.py

Scan Yoshimi/ZynAddSubFX instrument patch files and export them to a
Fluid Ardule compatible JSON instrument list.

Primary target:
    .xiz  = individual Yoshimi/ZynAddSubFX instrument patch

Output file:
    <bank-root>/yoshimi.patches.json

Example:
    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks

Optional:
    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks -o /home/pi/sf2/yoshimi.patches.json

JSON format:
    format  = instrument-list
    version = 2
    engine  = yoshimi

The output intentionally keeps bank/program/name fields so that it can be
handled by the same UI concepts used for SF2 preset lists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PATCH_EXTS = {".xiz"}

CATEGORY_FALLBACK = "Yoshimi"


def clean_display_name(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip() or "Unnamed"


def parse_patch_filename(path: Path, fallback_index: int) -> tuple[int, str]:
    """
    Try to extract a practical program number and display name from filenames.

    Common examples:
        0001-Warm Pad.xiz      -> program 1,  name "Warm Pad"
        001_Bright Lead.xiz    -> program 1,  name "Bright Lead"
        42 Organ.xiz           -> program 42, name "Organ"
        Simple Saw.xiz         -> fallback index, name "Simple Saw"

    Program numbers are kept as the visible patch number when present.
    """
    stem = path.stem.strip()

    m = re.match(r"^\s*(\d{1,4})[\s._-]+(.+?)\s*$", stem)
    if m:
        program = int(m.group(1))
        name = clean_display_name(m.group(2))
        return program, name

    m = re.match(r"^\s*(\d{1,4})\s*$", stem)
    if m:
        program = int(m.group(1))
        return program, f"Patch {program}"

    return fallback_index, clean_display_name(stem)


def make_instrument_id(bank_name: str, program: int, patch_name: str) -> str:
    safe_bank = "-".join(clean_display_name(bank_name).split())
    safe_name = "-".join(clean_display_name(patch_name).split())
    return f"yoshimi:{safe_bank}:{int(program)}:{safe_name}"


def discover_bank_dirs(root: Path) -> list[Path]:
    """
    A bank directory is any directory below root that directly contains .xiz files.
    If root itself contains .xiz files, it is also treated as a bank.
    """
    banks: list[Path] = []

    if any(p.is_file() and p.suffix.lower() in PATCH_EXTS for p in root.iterdir()):
        banks.append(root)

    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda x: str(x).lower()):
        try:
            if any(p.is_file() and p.suffix.lower() in PATCH_EXTS for p in d.iterdir()):
                banks.append(d)
        except PermissionError:
            continue

    # Remove duplicates while preserving order.
    seen = set()
    unique = []
    for d in banks:
        resolved = d.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(d)

    return unique


def relative_bank_name(bank_dir: Path, root: Path) -> str:
    try:
        rel = bank_dir.relative_to(root)
        if str(rel) == ".":
            return bank_dir.name
        return str(rel).replace("/", " / ")
    except ValueError:
        return bank_dir.name


def scan_yoshimi_patches(root: Path) -> list[dict]:
    banks = discover_bank_dirs(root)
    presets: list[dict] = []

    for bank_number, bank_dir in enumerate(banks):
        bank_name = relative_bank_name(bank_dir, root)
        patch_files = sorted(
            [p for p in bank_dir.iterdir() if p.is_file() and p.suffix.lower() in PATCH_EXTS],
            key=lambda p: p.name.lower(),
        )

        for fallback_index, patch_path in enumerate(patch_files, start=1):
            program, patch_name = parse_patch_filename(patch_path, fallback_index)
            patch_path_abs = patch_path.resolve()
            bank_path_abs = bank_dir.resolve()

            presets.append(
                {
                    "id": make_instrument_id(bank_name, program, patch_name),
                    "name": patch_name,
                    "bank": bank_number,
                    "program": program,
                    "category": bank_name or CATEGORY_FALLBACK,
                    "is_drum": False,

                    "yoshimi": {
                        "bank_name": bank_name,
                        "bank_number": bank_number,
                        "bank_path": str(bank_path_abs),
                        "patch_file": patch_path.name,
                        "patch_path": str(patch_path_abs),
                        "patch_ext": patch_path.suffix.lower(),
                    },
                }
            )

    presets.sort(key=lambda x: (x["bank"], x["program"], x["name"].lower()))
    return presets


def build_output(root: Path, presets: list[dict]) -> dict:
    categories = sorted({p.get("category", CATEGORY_FALLBACK) for p in presets})

    return {
        "engine": "yoshimi",
        "source_type": "yoshimi-bank-root",
        "format": "instrument-list",
        "version": 2,

        "source_file": root.name,
        "source_path": str(root),
        "preset_count": len(presets),
        "melodic_preset_count": len(presets),
        "drum_preset_count": 0,
        "category_count": len(categories),
        "categories": categories,

        "presets": presets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Yoshimi .xiz patch information and save it as JSON."
    )
    parser.add_argument(
        "bank_root",
        help="Path to Yoshimi bank root directory, for example /usr/share/yoshimi/banks",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output JSON path. Default: <bank_root>/yoshimi.patches.json",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON without indentation",
    )
    args = parser.parse_args()

    root = Path(args.bank_root).expanduser().resolve()
    if not root.exists():
        print(f"ERROR: Path not found: {root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"ERROR: Not a directory: {root}", file=sys.stderr)
        return 1

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else root / "yoshimi.patches.json"
    )

    try:
        presets = scan_yoshimi_patches(root)
        payload = build_output(root, presets)
    except PermissionError as exc:
        print(f"ERROR: Permission denied: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: Unexpected failure: {exc}", file=sys.stderr)
        return 3

    if not presets:
        print(f"WARNING: No .xiz patches found under {root}", file=sys.stderr)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            if args.compact:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
    except Exception as exc:
        print(f"ERROR: Could not write output file: {exc}", file=sys.stderr)
        return 4

    print(f"Wrote {output_path}")
    print(f"Format: {payload['format']} v{payload['version']}")
    print(f"Engine: {payload['engine']}")
    print(f"Patch count: {payload['preset_count']}")
    print(f"Bank/category count: {payload['category_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
