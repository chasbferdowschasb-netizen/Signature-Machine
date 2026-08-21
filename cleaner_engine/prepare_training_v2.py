#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Prepare training pairs for Signature Cleaner V2.

Source:
    test_debug\*_candidate.png
    test_debug_v06_1\*_signature_mask.png

Output:
    cleaner_engine\training_v2\original\
    cleaner_engine\training_v2\masks\

The original candidate images and masks are COPIED, not modified.
"""

from pathlib import Path
import shutil
import sys


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CANDIDATE_DIR = PROJECT_ROOT / "test_debug"
MASK_DIR = PROJECT_ROOT / "test_debug_v06_1"

OUTPUT_DIR = PROJECT_ROOT / "cleaner_engine" / "training_v2"
ORIGINAL_OUT = OUTPUT_DIR / "original"
MASK_OUT = OUTPUT_DIR / "masks"


# ============================================================
# SUPPORTED IMAGE EXTENSIONS
# ============================================================

IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


# ============================================================
# HELPERS
# ============================================================

def get_id_from_candidate(path: Path) -> str:
    """
    Example:
        02e13d43f1407342_candidate.png
        -> 02e13d43f1407342
    """
    suffix = "_candidate"
    if path.stem.endswith(suffix):
        return path.stem[:-len(suffix)]
    return path.stem


def get_id_from_mask(path: Path) -> str:
    """
    Example:
        02e13d43f1407342_signature_mask.png
        -> 02e13d43f1407342
    """
    suffix = "_signature_mask"
    if path.stem.endswith(suffix):
        return path.stem[:-len(suffix)]
    return path.stem


def find_candidates():
    """
    Find candidate images only.
    """
    if not CANDIDATE_DIR.exists():
        raise FileNotFoundError(
            f"Candidate directory not found:\n{CANDIDATE_DIR}"
        )

    files = []

    for p in CANDIDATE_DIR.iterdir():
        if not p.is_file():
            continue

        if p.suffix.lower() not in IMAGE_EXTS:
            continue

        if p.name.lower().endswith("_candidate" + p.suffix.lower()):
            files.append(p)

    return sorted(files)


def find_masks():
    """
    Find signature masks only.
    """
    if not MASK_DIR.exists():
        raise FileNotFoundError(
            f"Mask directory not found:\n{MASK_DIR}"
        )

    files = []

    for p in MASK_DIR.iterdir():
        if not p.is_file():
            continue

        if p.suffix.lower() != ".png":
            continue

        if p.name.lower().endswith("_signature_mask.png"):
            files.append(p)

    return sorted(files)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("Signature Cleaner V2 - Training Pair Preparation")
    print("=" * 70)

    print()
    print("Project:")
    print(PROJECT_ROOT)

    print()
    print("Candidate source:")
    print(CANDIDATE_DIR)

    print()
    print("Mask source:")
    print(MASK_DIR)

    # --------------------------------------------------------
    # Find files
    # --------------------------------------------------------

    candidates = find_candidates()
    masks = find_masks()

    candidate_map = {
        get_id_from_candidate(p): p
        for p in candidates
    }

    mask_map = {
        get_id_from_mask(p): p
        for p in masks
    }

    candidate_ids = set(candidate_map)
    mask_ids = set(mask_map)

    matched_ids = sorted(candidate_ids & mask_ids)
    missing_masks = sorted(candidate_ids - mask_ids)
    missing_candidates = sorted(mask_ids - candidate_ids)

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("DISCOVERY")
    print("-" * 70)

    print(f"Candidate files : {len(candidates)}")
    print(f"Mask files      : {len(masks)}")
    print(f"Matched pairs   : {len(matched_ids)}")
    print(f"Missing masks   : {len(missing_masks)}")
    print(f"Missing images  : {len(missing_candidates)}")

    if missing_masks:
        print()
        print("Candidates without masks:")

        for item in missing_masks:
            print("  ", item)

    if missing_candidates:
        print()
        print("Masks without candidates:")

        for item in missing_candidates:
            print("  ", item)

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    if not matched_ids:
        print()
        print("ERROR: No valid training pairs found.")
        sys.exit(1)

    # --------------------------------------------------------
    # Create output directories
    # --------------------------------------------------------

    ORIGINAL_OUT.mkdir(parents=True, exist_ok=True)
    MASK_OUT.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # Copy matched pairs
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("COPYING MATCHED PAIRS")
    print("-" * 70)

    copied = 0

    for sample_id in matched_ids:

        candidate = candidate_map[sample_id]
        mask = mask_map[sample_id]

        # Trainer V2 expects:
        #
        # original/
        #   ID.png
        #
        # masks/
        #   ID_mask.png

        original_dst = ORIGINAL_OUT / f"{sample_id}.png"
        mask_dst = MASK_OUT / f"{sample_id}_mask.png"

        shutil.copy2(candidate, original_dst)
        shutil.copy2(mask, mask_dst)

        copied += 1

        print(
            f"[{copied:02d}/{len(matched_ids):02d}] "
            f"{sample_id}"
        )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("PREPARATION COMPLETE")
    print("=" * 70)

    print()
    print(f"Training pairs prepared : {copied}")

    print()
    print("Output:")
    print(f"  Original : {ORIGINAL_OUT}")
    print(f"  Masks    : {MASK_OUT}")

    print()
    print("IMPORTANT:")
    print("The original test set was NOT modified.")
    print("cleaner_test20\\input was NOT used for training.")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()