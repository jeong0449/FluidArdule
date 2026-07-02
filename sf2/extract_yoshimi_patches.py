#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
extract_yoshimi_patches.py

Scan Yoshimi/ZynAddSubFX instrument patch files and export them to a
Fluid Ardule compatible JSON instrument list.

This version also builds a symbolic-link repository for Yoshimi live
instrument switching.

Why symbolic links?
-------------------
Yoshimi can load an instrument into a running process with a CLI command like:

    load instrument /some/path/to/patch.xiz

In practice, the Yoshimi CLI is fragile when the path contains spaces.  Many
factory Yoshimi banks contain filenames such as "0039-Soft Arpeggio1.xiz".
Passing that original path directly to the CLI can therefore fail even though
the file exists.

The workaround used here is deliberately simple:

    original bank file, possibly with spaces:
        /usr/share/yoshimi/banks/Arpeggios/0039-Soft Arpeggio1.xiz

    safe symbolic link, no spaces:
        /home/pi/sf2/yoshimi_links/Arpeggios__0039-Soft-Arpeggio1.xiz

The JSON preset's top-level "path" field points to the safe symbolic link, so
runtime code can simply send:

    load instrument <preset["path"]>

The original location is preserved in "original_path" and in the nested
"yoshimi" metadata for debugging and maintenance.

Primary target:
    .xiz  = individual Yoshimi/ZynAddSubFX instrument patch

Default output file:
    <bank-root>/yoshimi.patches.json

Default symbolic-link directory:
    /home/pi/sf2/yoshimi_links

Examples:
    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks

    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks \
        -o /home/pi/sf2/yoshimi.patches.json

    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks \
        --link-dir /home/pi/sf2/yoshimi_links --clean-links

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
import os
import re
import sys
from pathlib import Path


PATCH_EXTS = {".xiz"}
CATEGORY_FALLBACK = "Yoshimi"
DEFAULT_LINK_DIR = Path("/home/pi/sf2/yoshimi_links")
DEFAULT_OUTPUT_BASENAME = "yoshimi.patches.json"


def clean_display_name(text: str) -> str:
    """Return a human-friendly name for UI display."""
    text = text.strip()
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip() or "Unnamed"


def safe_filename_component(text: str) -> str:
    """
    Convert bank names and patch filenames into CLI-safe filename fragments.

    The design note only requires replacing spaces with hyphens, but this
    helper is a little more defensive:

    * any whitespace becomes "-";
    * path separators become "-";
    * repeated hyphens are collapsed;
    * characters that are awkward in shells or CLIs are replaced with "-";
    * ordinary useful characters such as letters, digits, dot, underscore,
      hyphen, plus, and parentheses are preserved.

    The result is still readable, while avoiding the Yoshimi CLI's path parsing
    problem caused by spaces.
    """
    text = clean_display_name(text)
    text = text.replace("/", "-").replace("\\", "-")
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^0-9A-Za-z가-힣._()+-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-._")
    return text or "Unnamed"


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
    """Build a stable Fluid Ardule instrument id."""
    safe_bank = safe_filename_component(bank_name)
    safe_name = safe_filename_component(patch_name)
    return f"yoshimi:{safe_bank}:{int(program)}:{safe_name}"


def discover_bank_dirs(root: Path) -> list[Path]:
    """
    Return every directory below root that directly contains .xiz files.

    Yoshimi banks are usually arranged as one directory per category/bank.  A
    directory is treated as a bank only when it directly contains .xiz files.
    Nested directories are discovered as separate banks if they also contain
    .xiz files.
    """
    banks: list[Path] = []

    if any(p.is_file() and p.suffix.lower() in PATCH_EXTS for p in root.iterdir()):
        banks.append(root)

    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda x: str(x).lower()):
        try:
            if any(p.is_file() and p.suffix.lower() in PATCH_EXTS for p in d.iterdir()):
                banks.append(d)
        except PermissionError:
            # Some system bank directories may not be readable.  Skipping them
            # lets the rest of the instrument list still be generated.
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
    """Return a readable bank/category name relative to the bank root."""
    try:
        rel = bank_dir.relative_to(root)
        if str(rel) == ".":
            return bank_dir.name
        return str(rel).replace("/", " / ")
    except ValueError:
        return bank_dir.name


def make_link_name(bank_name: str, patch_path: Path) -> str:
    """
    Create a collision-resistant, space-free symbolic-link filename.

    The bank name is included before a double underscore.  This follows the
    design note's example and prevents collisions when two banks contain the
    same patch filename.
    """
    safe_bank = safe_filename_component(bank_name)
    safe_patch_stem = safe_filename_component(patch_path.stem)
    return f"{safe_bank}__{safe_patch_stem}{patch_path.suffix.lower()}"


def create_or_update_symlink(original_path: Path, link_path: Path, *, force: bool = False) -> None:
    """
    Create link_path -> original_path.

    Existing correct links are left alone.  Broken or outdated symlinks are
    replaced.  Non-symlink files are never overwritten unless --force-links is
    used, because an unexpected real file in the link repository may represent
    a user mistake that deserves attention.
    """
    original_path = original_path.resolve()
    link_path.parent.mkdir(parents=True, exist_ok=True)

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink():
            try:
                current_target = link_path.resolve(strict=True)
            except FileNotFoundError:
                current_target = None

            if current_target == original_path:
                return

            link_path.unlink()
        elif force:
            link_path.unlink()
        else:
            raise FileExistsError(
                f"Refusing to overwrite non-symlink file: {link_path}. "
                "Use --force-links only if this is intentional."
            )

    os.symlink(str(original_path), str(link_path))


def clean_link_repository(link_dir: Path) -> int:
    """
    Remove existing .xiz symlinks in the link repository.

    This is optional and intentionally conservative: only symbolic links with
    a .xiz suffix directly inside link_dir are removed.  Real files and
    subdirectories are left untouched.
    """
    if not link_dir.exists():
        return 0

    removed = 0
    for p in link_dir.iterdir():
        if p.is_symlink() and p.suffix.lower() in PATCH_EXTS:
            p.unlink()
            removed += 1
    return removed


def scan_yoshimi_patches(root: Path, link_dir: Path, *, force_links: bool = False) -> list[dict]:
    """
    Scan bank files, create safe symbolic links, and return JSON presets.

    The top-level "path" is the value the runtime should pass to Yoshimi CLI.
    The top-level "original_path" is retained for debugging, so one can always
    trace a safe link back to the factory/user bank file.
    """
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
            link_name = make_link_name(bank_name, patch_path)
            link_path = (link_dir / link_name).resolve()

            create_or_update_symlink(patch_path_abs, link_path, force=force_links)

            presets.append(
                {
                    "id": make_instrument_id(bank_name, program, patch_name),
                    "name": patch_name,

                    # This is the important field for restart-free preview or
                    # live switching.  Runtime code should use this path when
                    # issuing: load instrument <path>
                    "path": str(link_path),

                    # Kept for diagnostics and for humans checking whether a
                    # symbolic link points back to the expected bank file.
                    "original_path": str(patch_path_abs),

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
                        "link_file": link_name,
                        "link_path": str(link_path),
                    },
                }
            )

    presets.sort(key=lambda x: (x["bank"], x["program"], x["name"].lower()))
    return presets


def build_output(root: Path, presets: list[dict], link_dir: Path) -> dict:
    """Build the Fluid Ardule JSON document."""
    categories = sorted({p.get("category", CATEGORY_FALLBACK) for p in presets})

    return {
        "engine": "yoshimi",
        "source_type": "yoshimi-bank-root",
        "format": "instrument-list",
        "version": 2,

        "source_file": root.name,
        "source_path": str(root),
        "uses_symlink_paths": True,
        "link_dir": str(link_dir),
        "preset_count": len(presets),
        "melodic_preset_count": len(presets),
        "drum_preset_count": 0,
        "category_count": len(categories),
        "categories": categories,

        "presets": presets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Yoshimi .xiz patch information, create safe symlinks, and save JSON."
    )
    parser.add_argument(
        "bank_root",
        help="Path to Yoshimi bank root directory, for example /usr/share/yoshimi/banks",
    )
    parser.add_argument(
        "-o",
        "--output",
        help=f"Optional output JSON path. Default: <bank_root>/{DEFAULT_OUTPUT_BASENAME}",
    )
    parser.add_argument(
        "--link-dir",
        default=str(DEFAULT_LINK_DIR),
        help=f"Directory for safe .xiz symlinks. Default: {DEFAULT_LINK_DIR}",
    )
    parser.add_argument(
        "--clean-links",
        action="store_true",
        help="Remove existing .xiz symlinks in --link-dir before creating new links.",
    )
    parser.add_argument(
        "--force-links",
        action="store_true",
        help="Allow replacing non-symlink files in --link-dir. Use with care.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON without indentation.",
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
        else root / DEFAULT_OUTPUT_BASENAME
    )
    link_dir = Path(args.link_dir).expanduser().resolve()

    try:
        cleaned = clean_link_repository(link_dir) if args.clean_links else 0
        presets = scan_yoshimi_patches(root, link_dir, force_links=args.force_links)
        payload = build_output(root, presets, link_dir)
    except PermissionError as exc:
        print(f"ERROR: Permission denied: {exc}", file=sys.stderr)
        return 2
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 5
    except OSError as exc:
        print(f"ERROR: Could not create symbolic links: {exc}", file=sys.stderr)
        return 6
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
    print(f"Symlink directory: {payload['link_dir']}")
    if args.clean_links:
        print(f"Removed old .xiz symlinks: {cleaned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
