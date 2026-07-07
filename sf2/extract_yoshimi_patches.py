#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
extract_yoshimi_patches.py

Scan Yoshimi/ZynAddSubFX instrument patch files, copy them into a
Fluid Ardule-owned patch repository with CLI-safe filenames, and export a
Fluid Ardule compatible JSON instrument list.

Why copy patches?
-----------------
Yoshimi can load an instrument into a running process with a CLI command like:

    load instrument /some/path/to/patch.xiz

In practice, the Yoshimi CLI is fragile when the path contains spaces.  Many
factory Yoshimi banks contain filenames such as "0039-Soft Arpeggio1.xiz".
Passing that original path directly to the CLI can therefore fail even though
the file exists.

Earlier versions of this extractor created a symbolic-link repository.  That
removed spaces from the visible link path, but it still left one more layer of
path indirection.  For a small appliance-like system such as Fluid Ardule, a
real copy with a normalized filename is simpler and more robust.

The current workflow is therefore:

    original bank file, possibly with spaces:
        /usr/share/yoshimi/banks/Arpeggios/0039-Soft Arpeggio1.xiz

    Fluid Ardule patch copy, no spaces:
        /home/pi/sf2/yoshimi_patches/Arpeggios__0039-Soft-Arpeggio1.xiz

The JSON preset's top-level "path" field points to the copied patch file, so
runtime code can simply send:

    load instrument <preset["path"]>

The original location is preserved in "original_path" and in the nested
"yoshimi" metadata for debugging and maintenance.

Primary target:
    .xiz  = individual Yoshimi/ZynAddSubFX instrument patch

Default output file:
    <bank-root>/yoshimi.patches.json

Default copied-patch directory:
    /home/pi/sf2/yoshimi_patches

Examples:
    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks

    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks \
        -o /home/pi/sf2/yoshimi.patches.json

    python3 extract_yoshimi_patches.py /usr/share/yoshimi/banks \
        --patch-dir /home/pi/sf2/yoshimi_patches --clean-patches

JSON format:
    format  = instrument-list
    version = 2
    engine  = yoshimi

The output intentionally keeps bank/program/name fields so that it can be
handled by the same UI concepts used for SF2 preset lists.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import sys
from pathlib import Path


PATCH_EXTS = {".xiz"}
CATEGORY_FALLBACK = "Yoshimi"
DEFAULT_PATCH_DIR = Path("/home/pi/sf2/yoshimi_patches")
DEFAULT_OUTPUT_BASENAME = "yoshimi.patches.json"
JSON_VERSION = 2


def clean_display_name(text: str) -> str:
    """Return a human-friendly name for UI display."""
    text = text.strip()
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip() or "Unnamed"


def safe_filename_component(text: str) -> str:
    """
    Convert bank names and patch filenames into CLI-safe filename fragments.

    The important rule is that generated paths must not contain whitespace.
    This helper is intentionally defensive:

    * any whitespace becomes "-";
    * path separators become "-";
    * repeated hyphens are collapsed;
    * characters that are awkward in shells or CLIs are replaced with "-";
    * ordinary useful characters such as letters, digits, dot, underscore,
      hyphen, plus, and parentheses are preserved.
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


def make_patch_copy_name(bank_name: str, patch_path: Path) -> str:
    """
    Create a collision-resistant, whitespace-free copied-patch filename.

    The bank name is included before a double underscore.  This prevents
    collisions when two banks contain the same patch filename.
    """
    safe_bank = safe_filename_component(bank_name)
    safe_patch_stem = safe_filename_component(patch_path.stem)
    return f"{safe_bank}__{safe_patch_stem}{patch_path.suffix.lower()}"


def copy_patch_file(original_path: Path, copy_path: Path, *, force: bool = False) -> bool:
    """
    Copy original_path to copy_path.

    Returns True when a copy was written and False when an existing copy was
    already up to date.  Existing real files are updated when their contents
    differ.  Existing symlinks are refused unless --force-patches is used,
    because the new design intentionally avoids symlinks.
    """
    original_path = original_path.resolve()
    copy_path.parent.mkdir(parents=True, exist_ok=True)

    if copy_path.exists() or copy_path.is_symlink():
        if copy_path.is_symlink():
            if not force:
                raise FileExistsError(
                    f"Refusing to overwrite symlink in patch repository: {copy_path}. "
                    "Use --force-patches only if this is intentional."
                )
            copy_path.unlink()
        elif copy_path.is_file():
            try:
                if filecmp.cmp(original_path, copy_path, shallow=False):
                    return False
            except OSError:
                pass
        elif force:
            if copy_path.is_dir():
                shutil.rmtree(copy_path)
            else:
                copy_path.unlink()
        else:
            raise FileExistsError(
                f"Refusing to overwrite non-file path: {copy_path}. "
                "Use --force-patches only if this is intentional."
            )

    shutil.copy2(original_path, copy_path)
    return True


def clean_patch_repository(patch_dir: Path) -> int:
    """
    Remove existing .xiz files in the copied-patch repository.

    This is optional and intentionally conservative: only .xiz files or .xiz
    symlinks directly inside patch_dir are removed.  Subdirectories and other
    files are left untouched.
    """
    if not patch_dir.exists():
        return 0

    removed = 0
    for p in patch_dir.iterdir():
        if (p.is_file() or p.is_symlink()) and p.suffix.lower() in PATCH_EXTS:
            p.unlink()
            removed += 1
    return removed


def scan_yoshimi_patches(root: Path, patch_dir: Path, *, force_patches: bool = False) -> tuple[list[dict], int]:
    """
    Scan bank files, create safe patch copies, and return JSON presets.

    The top-level "path" is the value the runtime should pass to Yoshimi CLI.
    The top-level "original_path" is retained for debugging, so one can always
    trace a copied patch back to the factory/user bank file.
    """
    banks = discover_bank_dirs(root)
    presets: list[dict] = []
    copied_count = 0

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
            patch_copy_name = make_patch_copy_name(bank_name, patch_path)
            patch_copy_path = (patch_dir / patch_copy_name).resolve()

            if copy_patch_file(patch_path_abs, patch_copy_path, force=force_patches):
                copied_count += 1

            presets.append(
                {
                    "id": make_instrument_id(bank_name, program, patch_name),
                    "name": patch_name,

                    # This is the important field for restart-free preview or
                    # live switching.  Runtime code should use this path when
                    # issuing: load instrument <path>
                    "path": str(patch_copy_path),

                    # Kept for diagnostics and for humans checking where the
                    # copied patch came from.
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
                        "patch_copy_file": patch_copy_name,
                        "patch_copy_path": str(patch_copy_path),
                    },
                }
            )

    presets.sort(key=lambda x: (x["bank"], x["program"], x["name"].lower()))
    return presets, copied_count


def build_output(root: Path, presets: list[dict], patch_dir: Path) -> dict:
    """Build the Fluid Ardule JSON document."""
    categories = sorted({p.get("category", CATEGORY_FALLBACK) for p in presets})

    return {
        "engine": "yoshimi",
        "source_type": "yoshimi-bank-root",
        "format": "instrument-list",
        "version": JSON_VERSION,

        "source_file": root.name,
        "source_path": str(root),
        "uses_symlink_paths": False,
        "patch_dir": str(patch_dir),
        "preset_count": len(presets),
        "melodic_preset_count": len(presets),
        "drum_preset_count": 0,
        "category_count": len(categories),
        "categories": categories,

        "presets": presets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Yoshimi .xiz patch information, copy safe patch files, and save JSON."
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
        "--patch-dir",
        default=str(DEFAULT_PATCH_DIR),
        help=f"Directory for copied, whitespace-free .xiz patches. Default: {DEFAULT_PATCH_DIR}",
    )
    parser.add_argument(
        "--clean-patches",
        action="store_true",
        help="Remove existing .xiz files in --patch-dir before creating new copies.",
    )
    parser.add_argument(
        "--force-patches",
        action="store_true",
        help="Allow replacing symlinks, directories, or unusual paths in --patch-dir. Use with care.",
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
    patch_dir = Path(args.patch_dir).expanduser().resolve()

    try:
        cleaned = clean_patch_repository(patch_dir) if args.clean_patches else 0
        presets, copied_count = scan_yoshimi_patches(root, patch_dir, force_patches=args.force_patches)
        payload = build_output(root, presets, patch_dir)
    except PermissionError as exc:
        print(f"ERROR: Permission denied: {exc}", file=sys.stderr)
        return 2
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 5
    except OSError as exc:
        print(f"ERROR: Could not create copied patch repository: {exc}", file=sys.stderr)
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
    print(f"Patch directory: {payload['patch_dir']}")
    print(f"Copied or updated .xiz files: {copied_count}")
    if args.clean_patches:
        print(f"Removed old .xiz patch copies: {cleaned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
