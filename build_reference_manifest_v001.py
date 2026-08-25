# -*- coding: utf-8 -*-
"""
Signature Machine — Reference Manifest Builder v0.1
STEP 2 ONLY.

Run from project root:
    python build_reference_manifest_v001.py
"""

from __future__ import annotations
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REF = ROOT / "online_training_data" / "reference_learning"
SAMPLES = REF / "samples"
FREEZE = REF / "REFERENCE_FREEZE_v0.1.json"
MANIFEST = REF / "REFERENCE_MANIFEST_v0.1.json"

FIRST, LAST = 1, 25
KNOWN_FILES = [
    "strokes.json",
    "raw.png",
    "render.png",
    "metadata.json",
    "sample_knowledge.json",
]


def sha256(path: Path):
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    if not path.is_file():
        return None, "missing"
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), "ok"
    except UnicodeDecodeError as e:
        return None, f"utf8_error: {e}"
    except json.JSONDecodeError as e:
        return None, f"json_error: {e}"
    except OSError as e:
        return None, f"io_error: {e}"


def json_summary(name, data, status):
    out = {"present": status != "missing", "read_status": status}
    if status != "ok":
        return out

    if name == "strokes.json":
        strokes = data if isinstance(data, list) else (
            data.get("strokes") if isinstance(data, dict) else None
        )
        out["json_type"] = type(data).__name__
        out["stroke_count"] = len(strokes) if isinstance(strokes, list) else None
        points = 0
        if isinstance(strokes, list):
            for stroke in strokes:
                if isinstance(stroke, dict) and isinstance(stroke.get("points"), list):
                    points += len(stroke["points"])
        out["point_count"] = points if isinstance(strokes, list) else None

    elif name == "metadata.json":
        out["json_type"] = type(data).__name__
        if isinstance(data, dict):
            for key in (
                "sample_id", "id", "label", "name",
                "first_name", "last_name", "tier", "created_at"
            ):
                if key in data and (
                    data[key] is None or
                    isinstance(data[key], (str, int, float, bool))
                ):
                    out[key] = data[key]

    elif name == "sample_knowledge.json":
        out["json_type"] = type(data).__name__
        if isinstance(data, dict):
            out["top_level_keys"] = sorted(str(k) for k in data)
            for key in (
                "sample_id", "knowledge_version", "schema_version",
                "normalized_strokes", "stroke_features",
                "velocity_profile", "pressure_profile",
                "direction_profile", "curvature_profile",
                "inter_stroke_timing"
            ):
                if key in data:
                    value = data[key]
                    if isinstance(value, list):
                        out[key + "_count"] = len(value)
                    elif isinstance(value, dict):
                        out[key + "_keys"] = sorted(str(k) for k in value)
                    elif value is None or isinstance(value, (str, int, float, bool)):
                        out[key] = value
    return out


def inspect_file(sample_dir: Path, filename: str):
    path = sample_dir / filename
    out = {
        "present": path.is_file(),
        "relative_path": str(path.relative_to(ROOT)).replace("\\", "/"),
    }
    if not path.is_file():
        return out

    try:
        st = path.stat()
        out["size_bytes"] = st.st_size
        out["modified_ns"] = st.st_mtime_ns
    except OSError as e:
        out["stat_error"] = str(e)

    out["sha256"] = sha256(path)

    if filename.endswith(".json"):
        data, status = read_json(path)
        out["json"] = json_summary(filename, data, status)

    return out


def main():
    print("=" * 72)
    print("SIGNATURE MACHINE — REFERENCE MANIFEST v0.1")
    print("STEP 2 ONLY")
    print("=" * 72)

    if not FREEZE.is_file():
        print("[ERROR] STEP 1 freeze marker not found:")
        print(FREEZE)
        print("Run freeze_reference_v001.py first.")
        return 1

    try:
        freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    except Exception as e:
        print("[ERROR] Cannot read freeze marker:", e)
        return 2

    expected = list(range(FIRST, LAST + 1))

    if freeze.get("status") != "FROZEN":
        print("[ERROR] Freeze marker is not FROZEN.")
        return 3

    if freeze.get("reference_sample_ids") != expected:
        print("[ERROR] Freeze marker does not contain exactly 001..025.")
        return 4

    if not SAMPLES.is_dir():
        print("[ERROR] Samples directory not found:")
        print(SAMPLES)
        return 5

    if MANIFEST.exists():
        print("[ALREADY BUILT]")
        print("Manifest already exists:")
        print(MANIFEST)
        print("No files were changed.")
        print("Existing manifest was NOT overwritten.")
        return 0

    samples = []
    missing = []

    for sid in expected:
        d = SAMPLES / f"sample_{sid:06d}"
        print(f"[SCAN] sample_{sid:06d}")

        if not d.is_dir():
            missing.append(sid)
            samples.append({
                "sample_id": sid,
                "folder_present": False,
                "folder": str(d.relative_to(ROOT)).replace("\\", "/"),
                "weight": 1 / len(expected),
                "files": {},
            })
            continue

        try:
            directory_files = sorted(p.name for p in d.iterdir() if p.is_file())
        except OSError as e:
            directory_files = []
            directory_error = str(e)
        else:
            directory_error = None

        entry = {
            "sample_id": sid,
            "folder_present": True,
            "folder": str(d.relative_to(ROOT)).replace("\\", "/"),
            "weight": 1 / len(expected),
            "files": {name: inspect_file(d, name) for name in KNOWN_FILES},
            "directory_files": directory_files,
        }
        if directory_error:
            entry["directory_error"] = directory_error
        samples.append(entry)

    manifest = {
        "schema": "signature_machine.reference_manifest",
        "schema_version": "0.1",
        "cycle": "v0.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Exact inventory of frozen reference samples 001..025 before STEP 3.",
        "freeze": {
            "file": str(FREEZE.relative_to(ROOT)).replace("\\", "/"),
            "status": "FROZEN",
        },
        "reference_policy": {
            "first_sample": FIRST,
            "last_sample": LAST,
            "sample_count": len(expected),
            "equal_weight": True,
            "weight_per_sample": 1 / len(expected),
            "generated_samples_included": False,
            "sample_026_plus_included": False,
        },
        "step_policy": {
            "step": 2,
            "name": "Build exact manifest",
            "trajectory_audit_performed": False,
            "trajectory_evaluation_performed": False,
            "training_performed": False,
            "generation_performed": False,
            "source_files_modified": False,
        },
        "samples": samples,
        "summary": {
            "expected_samples": len(expected),
            "present_samples": len(expected) - len(missing),
            "missing_sample_ids": missing,
        },
        "notes": [
            "Manifest is an inventory, not a trajectory-quality audit.",
            "SHA-256 values are recorded for integrity tracking only.",
            "No source sample file is modified.",
            "Sample quality decisions belong to STEP 3.",
            "All 25 samples retain equal learning weight.",
        ],
    }

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("STEP 2 COMPLETED")
    print("=" * 72)
    print("Manifest:", MANIFEST)
    print("Expected samples:", len(expected))
    print("Present samples:", len(expected) - len(missing))
    print("Equal weight: 1/25 = 0.04")
    print("STEP 3 has NOT been performed.")
    print("No sample contents were modified.")

    if missing:
        print("[WARNING] Missing:", ", ".join(f"{x:03d}" for x in missing))
        return 6

    return 0


if __name__ == "__main__":
    sys.exit(main())
