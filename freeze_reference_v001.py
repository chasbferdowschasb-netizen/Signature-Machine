# -*- coding: utf-8 -*-
"""
Signature Machine
Reference Freeze v0.1

STEP 1 ONLY:
Freeze reference samples 001..025 logically.

This script does NOT:
- audit trajectories
- build the exact manifest
- rebuild knowledge
- modify any sample files
- create training data
- generate signatures

It only verifies that sample_000001 .. sample_000025 exist and
creates a logical freeze marker for Cycle v0.1.

Run from the project root:
    python freeze_reference_v001.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

REFERENCE_DIR = (
    PROJECT_ROOT
    / "online_training_data"
    / "reference_learning"
)

SAMPLES_DIR = REFERENCE_DIR / "samples"

FREEZE_FILE = REFERENCE_DIR / "REFERENCE_FREEZE_v0.1.json"

FIRST_SAMPLE = 1
LAST_SAMPLE = 25


def sample_dir(sample_id: int) -> Path:
    return SAMPLES_DIR / f"sample_{sample_id:06d}"


def main() -> int:
    print("=" * 70)
    print("SIGNATURE MACHINE — REFERENCE FREEZE v0.1")
    print("STEP 1 ONLY")
    print("=" * 70)

    if not SAMPLES_DIR.exists():
        print(f"[ERROR] Reference samples directory not found:")
        print(f"        {SAMPLES_DIR}")
        return 1

    missing = []

    for sample_id in range(FIRST_SAMPLE, LAST_SAMPLE + 1):
        path = sample_dir(sample_id)

        if not path.is_dir():
            missing.append(sample_id)
            print(f"[MISSING] sample_{sample_id:06d}")
        else:
            print(f"[OK]      sample_{sample_id:06d}")

    if missing:
        print()
        print("[ABORTED]")
        print(
            "All reference samples 001..025 must exist before "
            "the freeze is created."
        )
        print("Missing:", ", ".join(f"{x:03d}" for x in missing))
        return 2

    if FREEZE_FILE.exists():
        try:
            existing = json.loads(
                FREEZE_FILE.read_text(encoding="utf-8")
            )
        except Exception as exc:
            print(f"[ERROR] Existing freeze file is unreadable: {exc}")
            return 3

        if existing.get("status") == "FROZEN":
            existing_ids = existing.get("reference_sample_ids", [])
            expected_ids = list(range(FIRST_SAMPLE, LAST_SAMPLE + 1))

            if existing_ids == expected_ids:
                print()
                print("[ALREADY FROZEN]")
                print(f"Freeze file: {FREEZE_FILE}")
                print("No sample files were modified.")
                return 0

            print("[ERROR] Existing freeze file has an unexpected sample set.")
            print("No changes made.")
            return 4

        print("[ERROR] Freeze file already exists but is not marked FROZEN.")
        print("No changes made.")
        return 5

    payload = {
        "schema": "signature_machine.reference_freeze",
        "schema_version": "0.1",
        "cycle": "v0.1",
        "status": "FROZEN",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_policy": {
            "sample_range": [FIRST_SAMPLE, LAST_SAMPLE],
            "sample_count": LAST_SAMPLE - FIRST_SAMPLE + 1,
            "equal_weight": True,
            "weight_per_sample": 1 / (LAST_SAMPLE - FIRST_SAMPLE + 1),
            "sample_priority": "none",
            "generated_samples_allowed": False,
            "future_samples_allowed": False,
            "sample_files_modified_by_this_script": False,
        },
        "reference_sample_ids": list(
            range(FIRST_SAMPLE, LAST_SAMPLE + 1)
        ),
        "notes": [
            "Samples 001..025 are the fixed reference set for Cycle v0.1.",
            "All reference samples have equal learning weight.",
            "No generated sample may enter this reference set.",
            "Sample 026+ is outside Cycle v0.1.",
            "This file is a logical freeze marker only.",
            "Exact manifest generation is STEP 2 and is intentionally not performed here.",
            "Trajectory audit is STEP 3 and is intentionally not performed here.",
        ],
    }

    FREEZE_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print()
    print("[FROZEN]")
    print(f"Reference set: 001..025")
    print(f"Sample count: 25")
    print(f"Equal weight: {payload['reference_policy']['weight_per_sample']}")
    print(f"Freeze marker: {FREEZE_FILE}")
    print()
    print("STEP 1 completed successfully.")
    print("STEP 2 has NOT been performed.")
    print("STEP 3 has NOT been performed.")
    print("No sample contents were modified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
