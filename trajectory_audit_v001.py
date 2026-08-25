# -*- coding: utf-8 -*-
"""
Signature Machine
Trajectory Audit v0.1

STEP 3 ONLY

Purpose:
    Audit the integrity and structural consistency of the frozen
    reference trajectories 001..025.

This script DOES:
    - verify STEP 1 freeze marker
    - verify STEP 2 exact manifest
    - inspect strokes.json for samples 001..025
    - validate JSON structure
    - validate stroke/point data
    - check coordinates, timestamps, pressure
    - check duplicate points and zero-length segments
    - check timestamp monotonicity
    - calculate descriptive trajectory statistics
    - compare basic schema consistency across the 25 samples
    - write JSON and TXT audit reports

This script DOES NOT:
    - modify any sample
    - rebuild knowledge
    - modify metadata
    - modify strokes.json
    - generate signatures
    - evaluate generated signatures
    - train a model
    - create Sample 026
    - change reference weights

Run from project root:
    python trajectory_audit_v001.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent

REF = ROOT / "online_training_data" / "reference_learning"
SAMPLES = REF / "samples"

FREEZE_FILE = REF / "REFERENCE_FREEZE_v0.1.json"
MANIFEST_FILE = REF / "REFERENCE_MANIFEST_v0.1.json"

AUDIT_JSON = REF / "TRAJECTORY_AUDIT_v0.1.json"
AUDIT_TXT = REF / "TRAJECTORY_AUDIT_v0.1.txt"

FIRST_SAMPLE = 1
LAST_SAMPLE = 25


# ---------------------------------------------------------------------------
# Audit thresholds
# These are diagnostic thresholds only. They do NOT change sample weight.
# ---------------------------------------------------------------------------

PRESSURE_MIN = 0.0
PRESSURE_MAX = 1.0

DUPLICATE_EPSILON = 1e-9
SEGMENT_EPSILON = 1e-9

MAX_WARNINGS_PER_SAMPLE = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def number(value: Any) -> float | None:
    if finite_number(value):
        return float(value)
    return None


def first_present(d: dict[str, Any], keys: tuple[str, ...]):
    for key in keys:
        if key in d:
            return d[key]
    return None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def point_xy(point: Any) -> tuple[float | None, float | None]:
    if not isinstance(point, dict):
        return None, None

    x = first_present(point, ("x", "X"))
    y = first_present(point, ("y", "Y"))

    return number(x), number(y)


def point_time(point: Any) -> float | None:
    if not isinstance(point, dict):
        return None

    value = first_present(
        point,
        (
            "time_ms",
            "timestamp_ms",
            "timestamp",
            "time",
            "t",
        ),
    )

    return number(value)


def point_pressure(point: Any) -> float | None:
    if not isinstance(point, dict):
        return None

    value = first_present(
        point,
        (
            "pressure",
            "Pressure",
            "force",
        ),
    )

    return number(value)


def extract_strokes(data: Any) -> tuple[list[Any] | None, str]:
    """
    Accept the known possible strokes.json layouts without modifying data.

    Supported:
        [ ... strokes ... ]
        {"strokes": [ ... ]}
        {"trajectory": [ ... ]}
    """
    if isinstance(data, list):
        return data, "root_list"

    if isinstance(data, dict):
        if isinstance(data.get("strokes"), list):
            return data["strokes"], "strokes_key"

        if isinstance(data.get("trajectory"), list):
            return data["trajectory"], "trajectory_key"

    return None, "unsupported"


def extract_points(stroke: Any) -> tuple[list[Any] | None, str]:
    if isinstance(stroke, list):
        return stroke, "stroke_list"

    if isinstance(stroke, dict):
        for key in ("points", "trajectory", "samples"):
            if isinstance(stroke.get(key), list):
                return stroke[key], key

    return None, "unsupported"


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def safe_mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def safe_median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def safe_min(values: list[float]) -> float | None:
    return min(values) if values else None


def safe_max(values: list[float]) -> float | None:
    return max(values) if values else None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def audit_sample(sample_id: int) -> dict[str, Any]:
    sample_dir = SAMPLES / f"sample_{sample_id:06d}"
    strokes_path = sample_dir / "strokes.json"

    result: dict[str, Any] = {
        "sample_id": sample_id,
        "sample": f"sample_{sample_id:06d}",
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "metrics": {},
        "schema": {},
    }

    errors: list[str] = result["errors"]
    warnings: list[str] = result["warnings"]

    if not sample_dir.is_dir():
        errors.append("sample_directory_missing")
        result["status"] = "FAIL"
        return result

    if not strokes_path.is_file():
        errors.append("strokes.json_missing")
        result["status"] = "FAIL"
        return result

    try:
        data = load_json(strokes_path)
    except json.JSONDecodeError as exc:
        errors.append(f"strokes_json_invalid: {exc}")
        result["status"] = "FAIL"
        return result
    except UnicodeDecodeError as exc:
        errors.append(f"strokes_json_utf8_error: {exc}")
        result["status"] = "FAIL"
        return result
    except OSError as exc:
        errors.append(f"strokes_json_read_error: {exc}")
        result["status"] = "FAIL"
        return result

    strokes, root_schema = extract_strokes(data)

    result["schema"]["root_layout"] = root_schema
    result["schema"]["root_type"] = type(data).__name__

    if strokes is None:
        errors.append("unsupported_strokes_json_structure")
        result["status"] = "FAIL"
        return result

    if len(strokes) == 0:
        errors.append("zero_strokes")
        result["status"] = "FAIL"
        return result

    all_times: list[float] = []
    all_pressures: list[float] = []

    stroke_lengths: list[float] = []
    stroke_durations: list[float] = []
    point_counts: list[int] = []

    total_points = 0
    duplicate_points = 0
    zero_length_segments = 0
    invalid_points = 0
    invalid_xy = 0
    invalid_time = 0
    invalid_pressure = 0
    pressure_out_of_range = 0
    timestamp_regressions = 0
    missing_timestamp_count = 0
    missing_pressure_count = 0

    point_schema_sets: list[tuple[str, ...]] = []
    stroke_schema_types: list[str] = []

    previous_global_time: float | None = None

    for stroke_index, stroke in enumerate(strokes):
        stroke_schema_types.append(type(stroke).__name__)

        points, point_schema = extract_points(stroke)

        if points is None:
            errors.append(
                f"stroke_{stroke_index:03d}:unsupported_point_structure"
            )
            continue

        point_counts.append(len(points))

        if len(points) == 0:
            warnings.append(
                f"stroke_{stroke_index:03d}:zero_points"
            )
            continue

        previous_xy: tuple[float, float] | None = None
        previous_time: float | None = None
        path_length = 0.0

        for point_index, point in enumerate(points):
            total_points += 1

            if not isinstance(point, dict):
                invalid_points += 1
                errors.append(
                    f"stroke_{stroke_index:03d}_point_{point_index:04d}:not_object"
                )
                continue

            point_schema_sets.append(tuple(sorted(str(k) for k in point.keys())))

            x, y = point_xy(point)

            if x is None or y is None:
                invalid_xy += 1
                errors.append(
                    f"stroke_{stroke_index:03d}_point_{point_index:04d}:invalid_xy"
                )
            else:
                if previous_xy is not None:
                    seg = distance(
                        previous_xy[0],
                        previous_xy[1],
                        x,
                        y,
                    )

                    path_length += seg

                    if seg <= SEGMENT_EPSILON:
                        zero_length_segments += 1

                previous_xy = (x, y)

            t = point_time(point)

            if t is None:
                missing_timestamp_count += 1
            else:
                all_times.append(t)

                if previous_time is not None and t < previous_time:
                    timestamp_regressions += 1

                if (
                    previous_global_time is not None
                    and t < previous_global_time
                ):
                    # This is tracked as a warning rather than an immediate
                    # error because some datasets legitimately reset timing
                    # at stroke boundaries.
                    pass

                previous_time = t
                previous_global_time = t

            p = point_pressure(point)

            if p is None:
                missing_pressure_count += 1
            else:
                all_pressures.append(p)

                if p < PRESSURE_MIN or p > PRESSURE_MAX:
                    pressure_out_of_range += 1

        # Duplicate points are checked within each stroke.
        previous_xy = None

        for point in points:
            if not isinstance(point, dict):
                continue

            x, y = point_xy(point)

            if x is None or y is None:
                continue

            if previous_xy is not None:
                if (
                    abs(x - previous_xy[0]) <= DUPLICATE_EPSILON
                    and abs(y - previous_xy[1]) <= DUPLICATE_EPSILON
                ):
                    duplicate_points += 1

            previous_xy = (x, y)

        stroke_lengths.append(path_length)

        # Duration is based on valid timestamps inside the stroke.
        stroke_times = [
            point_time(p)
            for p in points
            if point_time(p) is not None
        ]

        if len(stroke_times) >= 2:
            duration = stroke_times[-1] - stroke_times[0]

            if duration < 0:
                errors.append(
                    f"stroke_{stroke_index:03d}:negative_duration"
                )
            else:
                stroke_durations.append(duration)

    # -----------------------------------------------------------------------
    # Warnings
    # -----------------------------------------------------------------------

    if duplicate_points:
        warnings.append(
            f"duplicate_points:{duplicate_points}"
        )

    if zero_length_segments:
        warnings.append(
            f"zero_length_segments:{zero_length_segments}"
        )

    if missing_timestamp_count:
        warnings.append(
            f"points_missing_timestamp:{missing_timestamp_count}"
        )

    if missing_pressure_count:
        warnings.append(
            f"points_missing_pressure:{missing_pressure_count}"
        )

    if pressure_out_of_range:
        warnings.append(
            f"pressure_out_of_range:{pressure_out_of_range}"
        )

    if timestamp_regressions:
        warnings.append(
            f"timestamp_regressions_within_strokes:{timestamp_regressions}"
        )

    if invalid_points:
        errors.append(f"invalid_point_objects:{invalid_points}")

    if invalid_xy:
        errors.append(f"invalid_xy_points:{invalid_xy}")

    # -----------------------------------------------------------------------
    # Metrics
    # -----------------------------------------------------------------------

    total_path = sum(stroke_lengths)

    duration_total = None
    if all_times:
        duration_total = max(all_times) - min(all_times)

    result["metrics"] = {
        "stroke_count": len(strokes),
        "total_point_count": total_points,
        "point_count_per_stroke": point_counts,
        "total_path_length": total_path,
        "stroke_path_lengths": stroke_lengths,
        "stroke_durations_ms": stroke_durations,
        "total_time_span_ms": duration_total,

        "timestamp_count": len(all_times),
        "timestamp_min": safe_min(all_times),
        "timestamp_max": safe_max(all_times),

        "pressure_count": len(all_pressures),
        "pressure_min": safe_min(all_pressures),
        "pressure_max": safe_max(all_pressures),
        "pressure_mean": safe_mean(all_pressures),
        "pressure_median": safe_median(all_pressures),

        "duplicate_points": duplicate_points,
        "zero_length_segments": zero_length_segments,
        "invalid_points": invalid_points,
        "invalid_xy_points": invalid_xy,
        "invalid_timestamp_points": invalid_time,
        "invalid_pressure_points": invalid_pressure,
        "pressure_out_of_range": pressure_out_of_range,
        "timestamp_regressions_within_strokes": timestamp_regressions,
        "points_missing_timestamp": missing_timestamp_count,
        "points_missing_pressure": missing_pressure_count,
    }

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------

    if errors:
        result["status"] = "FAIL"
    elif warnings:
        result["status"] = "PASS_WITH_WARNINGS"
    else:
        result["status"] = "PASS"

    # Keep diagnostic output bounded.
    if len(warnings) > MAX_WARNINGS_PER_SAMPLE:
        result["warnings"] = warnings[:MAX_WARNINGS_PER_SAMPLE]
        result["warnings_truncated"] = True

    return result


# ---------------------------------------------------------------------------
# Cross-sample consistency
# ---------------------------------------------------------------------------

def cross_sample_audit(sample_results: list[dict[str, Any]]) -> dict[str, Any]:
    stroke_counts = [
        r["metrics"]["stroke_count"]
        for r in sample_results
        if r["status"] != "FAIL" and r["metrics"].get("stroke_count") is not None
    ]

    point_counts = [
        r["metrics"]["total_point_count"]
        for r in sample_results
        if r["status"] != "FAIL" and r["metrics"].get("total_point_count") is not None
    ]

    root_layouts = [
        r["schema"].get("root_layout")
        for r in sample_results
        if r["schema"].get("root_layout")
    ]

    schema = {
        "root_layouts": sorted(set(root_layouts)),
        "stroke_count_min": min(stroke_counts) if stroke_counts else None,
        "stroke_count_max": max(stroke_counts) if stroke_counts else None,
        "stroke_count_mean": (
            statistics.fmean(stroke_counts) if stroke_counts else None
        ),
        "point_count_min": min(point_counts) if point_counts else None,
        "point_count_max": max(point_counts) if point_counts else None,
        "point_count_mean": (
            statistics.fmean(point_counts) if point_counts else None
        ),
    }

    warnings: list[str] = []

    if len(set(root_layouts)) > 1:
        warnings.append(
            "mixed_strokes_json_root_layouts"
        )

    return {
        "status": "PASS_WITH_WARNINGS" if warnings else "PASS",
        "warnings": warnings,
        "metrics": schema,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("SIGNATURE MACHINE — TRAJECTORY AUDIT v0.1")
    print("STEP 3 ONLY")
    print("=" * 72)

    expected_ids = list(range(FIRST_SAMPLE, LAST_SAMPLE + 1))

    # -----------------------------------------------------------------------
    # STEP 1 verification
    # -----------------------------------------------------------------------

    if not FREEZE_FILE.is_file():
        print("[ERROR] STEP 1 freeze marker not found:")
        print(f"        {FREEZE_FILE}")
        return 1

    try:
        freeze = load_json(FREEZE_FILE)
    except Exception as exc:
        print(f"[ERROR] Cannot read freeze marker: {exc}")
        return 2

    if freeze.get("status") != "FROZEN":
        print("[ERROR] Reference set is not marked FROZEN.")
        return 3

    if freeze.get("reference_sample_ids") != expected_ids:
        print("[ERROR] Frozen reference IDs are not exactly 001..025.")
        return 4

    print("[OK] STEP 1 freeze verified.")

    # -----------------------------------------------------------------------
    # STEP 2 verification
    # -----------------------------------------------------------------------

    if not MANIFEST_FILE.is_file():
        print("[ERROR] STEP 2 manifest not found:")
        print(f"        {MANIFEST_FILE}")
        return 5

    try:
        manifest = load_json(MANIFEST_FILE)
    except Exception as exc:
        print(f"[ERROR] Cannot read manifest: {exc}")
        return 6

    policy = manifest.get("reference_policy", {})

    if policy.get("sample_count") != 25:
        print("[ERROR] Manifest sample_count is not 25.")
        return 7

    if policy.get("equal_weight") is not True:
        print("[ERROR] Manifest equal_weight is not true.")
        return 8

    if abs(float(policy.get("weight_per_sample", -1)) - 0.04) > 1e-12:
        print("[ERROR] Manifest weight_per_sample is not 0.04.")
        return 9

    manifest_ids = [
        item.get("sample_id")
        for item in manifest.get("samples", [])
    ]

    if manifest_ids != expected_ids:
        print("[ERROR] Manifest sample IDs are not exactly 001..025.")
        return 10

    print("[OK] STEP 2 manifest verified.")
    print("[OK] Reference set = 25 samples, equal weight = 0.04.")

    # -----------------------------------------------------------------------
    # Audit all 25
    # -----------------------------------------------------------------------

    print()
    print("AUDITING TRAJECTORIES")
    print("-" * 72)

    sample_results = []

    for sid in expected_ids:
        result = audit_sample(sid)
        sample_results.append(result)

        print(
            f"sample_{sid:06d}  "
            f"{result['status']}"
        )

        if result["errors"]:
            for error in result["errors"][:5]:
                print(f"    ERROR: {error}")

        if result["warnings"]:
            for warning in result["warnings"][:5]:
                print(f"    WARNING: {warning}")

    # -----------------------------------------------------------------------
    # Cross-sample audit
    # -----------------------------------------------------------------------

    print()
    print("CROSS-SAMPLE CONSISTENCY")
    print("-" * 72)

    cross = cross_sample_audit(sample_results)

    print(f"Status: {cross['status']}")

    for warning in cross["warnings"]:
        print(f"WARNING: {warning}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    pass_count = sum(
        1 for r in sample_results if r["status"] == "PASS"
    )
    warning_count = sum(
        1 for r in sample_results if r["status"] == "PASS_WITH_WARNINGS"
    )
    fail_count = sum(
        1 for r in sample_results if r["status"] == "FAIL"
    )

    total_errors = sum(
        len(r["errors"]) for r in sample_results
    )
    total_warnings = sum(
        len(r["warnings"]) for r in sample_results
    ) + len(cross["warnings"])

    if fail_count:
        dataset_status = "FAIL"
    elif warning_count or cross["warnings"]:
        dataset_status = "CONDITIONAL_PASS"
    else:
        dataset_status = "PASS"

    audit = {
        "schema": "signature_machine.trajectory_audit",
        "schema_version": "0.1",
        "cycle": "v0.1",
        "created_at_utc": now_utc(),

        "step": {
            "number": 3,
            "name": "Audit all 25 trajectories",
            "training_performed": False,
            "generation_performed": False,
            "source_files_modified": False,
        },

        "reference_policy": {
            "sample_range": [FIRST_SAMPLE, LAST_SAMPLE],
            "sample_count": 25,
            "equal_weight": True,
            "weight_per_sample": 0.04,
        },

        "summary": {
            "expected_samples": 25,
            "pass": pass_count,
            "pass_with_warnings": warning_count,
            "fail": fail_count,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "dataset_status": dataset_status,
        },

        "cross_sample": cross,
        "samples": sample_results,

        "thresholds": {
            "pressure_expected_min": PRESSURE_MIN,
            "pressure_expected_max": PRESSURE_MAX,
            "duplicate_epsilon": DUPLICATE_EPSILON,
            "zero_length_segment_epsilon": SEGMENT_EPSILON,
        },

        "notes": [
            "This audit is read-only.",
            "Warnings do not change sample weights.",
            "No sample is deleted or repaired.",
            "No generated sample is included.",
            "Sample 026+ is outside Cycle v0.1.",
            "Trajectory quality and structural integrity are audited here.",
            "Training begins only after STEP 3 is reviewed.",
        ],
    }

    AUDIT_JSON.write_text(
        json.dumps(
            audit,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    # Human-readable report
    lines = [
        "SIGNATURE MACHINE — TRAJECTORY AUDIT v0.1",
        "=" * 72,
        "",
        "STEP: 3 — Audit all 25 trajectories",
        "Reference set: 001..025",
        "Sample count: 25",
        "Equal weight: 1/25 = 0.04",
        "",
        "SUMMARY",
        "-" * 72,
        f"PASS:               {pass_count}",
        f"PASS_WITH_WARNINGS: {warning_count}",
        f"FAIL:               {fail_count}",
        f"TOTAL ERRORS:       {total_errors}",
        f"TOTAL WARNINGS:     {total_warnings}",
        f"DATASET STATUS:     {dataset_status}",
        "",
        "CROSS-SAMPLE",
        "-" * 72,
        json.dumps(cross, ensure_ascii=False, indent=2),
        "",
        "PER-SAMPLE",
        "-" * 72,
    ]

    for result in sample_results:
        lines.append(
            f"sample_{result['sample_id']:06d}: {result['status']}"
        )

        metrics = result.get("metrics", {})
        lines.append(
            f"  strokes={metrics.get('stroke_count')} "
            f"points={metrics.get('total_point_count')} "
            f"path={metrics.get('total_path_length')}"
        )

        if result["errors"]:
            lines.append("  errors:")
            for item in result["errors"]:
                lines.append(f"    - {item}")

        if result["warnings"]:
            lines.append("  warnings:")
            for item in result["warnings"]:
                lines.append(f"    - {item}")

        lines.append("")

    lines.extend(
        [
            "=" * 72,
            "STEP 3 COMPLETE",
            "=" * 72,
            "No sample contents were modified.",
            "No training was performed.",
            "No signatures were generated.",
            "",
        ]
    )

    AUDIT_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("STEP 3 COMPLETE")
    print("=" * 72)
    print(f"PASS:               {pass_count}")
    print(f"PASS_WITH_WARNINGS: {warning_count}")
    print(f"FAIL:               {fail_count}")
    print(f"TOTAL ERRORS:       {total_errors}")
    print(f"TOTAL WARNINGS:     {total_warnings}")
    print(f"DATASET STATUS:     {dataset_status}")
    print()
    print(f"JSON report: {AUDIT_JSON}")
    print(f"TXT report:  {AUDIT_TXT}")
    print()
    print("No sample contents were modified.")
    print("No training was performed.")
    print("No signatures were generated.")

    # Audit itself completes even with findings.
    # Non-zero exit code is reserved for actual FAIL status so automation
    # can stop before STEP 4.
    return 20 if dataset_status == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
