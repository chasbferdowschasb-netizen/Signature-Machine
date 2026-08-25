# -*- coding: utf-8 -*-
"""
Signature Machine
Trajectory Evaluator v0.1

STEP 4 ONLY

Purpose
-------
Build a deterministic trajectory feature representation from the frozen
reference samples 001..025.

This is NOT a trainer and NOT a generator.

It reads:
    REFERENCE_FREEZE_v0.1.json
    REFERENCE_MANIFEST_v0.1.json
    sample_000001..sample_000025/strokes.json

It writes:
    TRAJECTORY_EVALUATION_v0.1.json
    TRAJECTORY_EVALUATION_v0.1.txt

It does NOT modify any reference sample.

Important design rule
---------------------
All 25 reference samples have equal weight = 1/25 = 0.04.

The evaluator extracts motion/trajectory information that can later be
used by Cycle v0.1. It intentionally does not average raw coordinates into
a single signature and does not train a generative model.

Feature families:
    - topology
    - geometry
    - motion
    - pressure
    - timing
    - direction
    - curvature
    - stroke relationships

The evaluator is designed to tolerate the known strokes.json layouts used
by the current project.

Run from project root:
    python trajectory_evaluator_v001.py
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
AUDIT_FILE = REF / "TRAJECTORY_AUDIT_v0.1.json"

OUTPUT_JSON = REF / "TRAJECTORY_EVALUATION_v0.1.json"
OUTPUT_TXT = REF / "TRAJECTORY_EVALUATION_v0.1.txt"

FIRST_SAMPLE = 1
LAST_SAMPLE = 25


# ---------------------------------------------------------------------------
# Numerical helpers
# ---------------------------------------------------------------------------

EPS = 1e-12


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def f(value: Any) -> float | None:
    return float(value) if finite(value) else None


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def minimum(values: list[float]) -> float | None:
    return min(values) if values else None


def maximum(values: list[float]) -> float | None:
    return max(values) if values else None


def stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    return statistics.pstdev(values)


def safe_ratio(a: float, b: float) -> float | None:
    if abs(b) <= EPS:
        return None
    return a / b


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None

    if len(values) == 1:
        return values[0]

    xs = sorted(values)
    position = (len(xs) - 1) * p
    lo = int(math.floor(position))
    hi = int(math.ceil(position))

    if lo == hi:
        return xs[lo]

    fraction = position - lo
    return xs[lo] + (xs[hi] - xs[lo]) * fraction


def angle_delta(a: float, b: float) -> float:
    """
    Smallest signed angular difference in radians.
    """
    return (b - a + math.pi) % (2.0 * math.pi) - math.pi


def safe_round(value: Any, digits: int = 8):
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [safe_round(v, digits) for v in value]
    if isinstance(value, dict):
        return {k: safe_round(v, digits) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# JSON / strokes parsing
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_strokes(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if isinstance(data.get("strokes"), list):
            return data["strokes"]

        if isinstance(data.get("trajectory"), list):
            return data["trajectory"]

    return None


def extract_points(stroke: Any) -> list[Any] | None:
    if isinstance(stroke, list):
        return stroke

    if isinstance(stroke, dict):
        for key in ("points", "trajectory", "samples"):
            if isinstance(stroke.get(key), list):
                return stroke[key]

    return None


def get_xy(point: Any) -> tuple[float | None, float | None]:
    if not isinstance(point, dict):
        return None, None

    x = point.get("x", point.get("X"))
    y = point.get("y", point.get("Y"))

    return f(x), f(y)


def get_time(point: Any) -> float | None:
    if not isinstance(point, dict):
        return None

    for key in (
        "time_ms",
        "timestamp_ms",
        "timestamp",
        "time",
        "t",
    ):
        if key in point:
            return f(point[key])

    return None


def get_pressure(point: Any) -> float | None:
    if not isinstance(point, dict):
        return None

    for key in (
        "pressure",
        "Pressure",
        "force",
    ):
        if key in point:
            return f(point[key])

    return None


# ---------------------------------------------------------------------------
# Point / stroke geometry
# ---------------------------------------------------------------------------

def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def direction(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def extract_valid_points(points: list[Any]) -> list[dict[str, Any]]:
    result = []

    for index, point in enumerate(points):
        x, y = get_xy(point)

        if x is None or y is None:
            continue

        result.append(
            {
                "index": index,
                "x": x,
                "y": y,
                "t": get_time(point),
                "pressure": get_pressure(point),
            }
        )

    return result


def bbox(points: list[dict[str, Any]]) -> dict[str, float | None]:
    if not points:
        return {
            "min_x": None,
            "max_x": None,
            "min_y": None,
            "max_y": None,
            "width": None,
            "height": None,
        }

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    return {
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "width": max_x - min_x,
        "height": max_y - min_y,
    }


def resample_polyline(
    points: list[tuple[float, float]],
    count: int = 32,
) -> list[tuple[float, float]]:
    """
    Arc-length resampling for a single stroke.

    This is a feature representation only.
    Original points remain untouched.
    """
    if not points:
        return []

    if len(points) == 1:
        return [points[0]] * count

    cumulative = [0.0]
    for i in range(1, len(points)):
        cumulative.append(
            cumulative[-1] + distance(points[i - 1], points[i])
        )

    total = cumulative[-1]

    if total <= EPS:
        return [points[0]] * count

    output = []

    for k in range(count):
        target = total * (k / (count - 1))

        hi = 1
        while hi < len(cumulative) and cumulative[hi] < target:
            hi += 1

        if hi >= len(cumulative):
            output.append(points[-1])
            continue

        lo = hi - 1

        segment = cumulative[hi] - cumulative[lo]

        if segment <= EPS:
            output.append(points[lo])
            continue

        ratio = (target - cumulative[lo]) / segment

        x = (
            points[lo][0]
            + ratio * (points[hi][0] - points[lo][0])
        )
        y = (
            points[lo][1]
            + ratio * (points[hi][1] - points[lo][1])
        )

        output.append((x, y))

    return output


# ---------------------------------------------------------------------------
# Per-stroke feature extraction
# ---------------------------------------------------------------------------

def evaluate_stroke(points_raw: list[Any], stroke_index: int) -> dict[str, Any]:
    points = extract_valid_points(points_raw)

    if not points:
        return {
            "stroke_index": stroke_index,
            "point_count": 0,
            "valid_point_count": 0,
            "status": "EMPTY_OR_INVALID",
        }

    coords = [(p["x"], p["y"]) for p in points]

    box = bbox(points)

    segment_lengths = []
    segment_angles = []
    segment_dt = []
    velocities = []
    accelerations = []

    pressure_values = [
        p["pressure"]
        for p in points
        if p["pressure"] is not None
    ]

    times = [
        p["t"]
        for p in points
        if p["t"] is not None
    ]

    duplicate_segments = 0
    zero_dt = 0

    for i in range(1, len(coords)):
        seg_len = distance(coords[i - 1], coords[i])
        segment_lengths.append(seg_len)

        if seg_len <= EPS:
            duplicate_segments += 1
        else:
            segment_angles.append(
                direction(coords[i - 1], coords[i])
            )

        t1 = points[i - 1]["t"]
        t2 = points[i]["t"]

        if t1 is not None and t2 is not None:
            dt = t2 - t1
            segment_dt.append(dt)

            if dt <= EPS:
                zero_dt += 1
            else:
                velocities.append(seg_len / dt)

    for i in range(1, len(velocities)):
        accelerations.append(
            velocities[i] - velocities[i - 1]
        )

    turns = []

    for i in range(1, len(segment_angles)):
        turns.append(
            angle_delta(
                segment_angles[i - 1],
                segment_angles[i],
            )
        )

    absolute_turns = [abs(v) for v in turns]

    direction_changes = sum(
        1
        for value in turns
        if abs(value) > math.radians(10.0)
    )

    signed_turn_sum = sum(turns)
    absolute_turn_sum = sum(absolute_turns)

    path_length = sum(segment_lengths)

    displacement = distance(coords[0], coords[-1])

    duration = None
    if len(times) >= 2:
        duration = max(times) - min(times)

    mean_velocity = mean(velocities)

    straightness = safe_ratio(displacement, path_length)

    resampled = resample_polyline(coords, 32)

    normalized_resampled = []
    width = box["width"]
    height = box["height"]

    scale = max(
        float(width) if width is not None else 0.0,
        float(height) if height is not None else 0.0,
    )

    if scale <= EPS:
        scale = 1.0

    origin_x = box["min_x"] if box["min_x"] is not None else 0.0
    origin_y = box["min_y"] if box["min_y"] is not None else 0.0

    for x, y in resampled:
        normalized_resampled.append(
            [
                (x - origin_x) / scale,
                (y - origin_y) / scale,
            ]
        )

    feature = {
        "stroke_index": stroke_index,
        "point_count": len(points_raw),
        "valid_point_count": len(points),

        "geometry": {
            "bbox": box,
            "path_length": path_length,
            "displacement": displacement,
            "straightness": straightness,
            "width_height_ratio": safe_ratio(
                float(width) if width is not None else 0.0,
                float(height) if height is not None else 0.0,
            ),
            "start": [coords[0][0], coords[0][1]],
            "end": [coords[-1][0], coords[-1][1]],
        },

        "direction": {
            "segment_count": len(segment_angles),
            "direction_changes": direction_changes,
            "signed_turn_sum_rad": signed_turn_sum,
            "absolute_turn_sum_rad": absolute_turn_sum,
            "turn_mean_abs_rad": mean(absolute_turns),
            "turn_median_abs_rad": median(absolute_turns),
            "turn_max_abs_rad": maximum(absolute_turns),
            "initial_direction_rad": (
                segment_angles[0] if segment_angles else None
            ),
            "final_direction_rad": (
                segment_angles[-1] if segment_angles else None
            ),
        },

        "curvature_proxy": {
            "turn_count": len(turns),
            "turn_density": safe_ratio(
                len(turns),
                max(1, len(segment_angles)),
            ),
            "absolute_turn_per_path_length": safe_ratio(
                absolute_turn_sum,
                path_length,
            ),
        },

        "motion": {
            "duration_ms": duration,
            "mean_velocity": mean_velocity,
            "median_velocity": median(velocities),
            "velocity_min": minimum(velocities),
            "velocity_max": maximum(velocities),
            "velocity_std": stddev(velocities),
            "acceleration_mean": mean(accelerations),
            "acceleration_std": stddev(accelerations),
            "acceleration_abs_mean": (
                mean([abs(v) for v in accelerations])
                if accelerations
                else None
            ),
            "zero_dt_segments": zero_dt,
        },

        "pressure": {
            "count": len(pressure_values),
            "min": minimum(pressure_values),
            "max": maximum(pressure_values),
            "mean": mean(pressure_values),
            "median": median(pressure_values),
            "std": stddev(pressure_values),
            "p10": percentile(pressure_values, 0.10),
            "p90": percentile(pressure_values, 0.90),
        },

        "normalized_shape": {
            "resample_count": len(normalized_resampled),
            "points": normalized_resampled,
        },

        "integrity": {
            "duplicate_segments": duplicate_segments,
        },
    }

    return safe_round(feature)


# ---------------------------------------------------------------------------
# Per-sample evaluation
# ---------------------------------------------------------------------------

def evaluate_sample(sample_id: int) -> dict[str, Any]:
    sample_dir = SAMPLES / f"sample_{sample_id:06d}"
    strokes_file = sample_dir / "strokes.json"

    result: dict[str, Any] = {
        "sample_id": sample_id,
        "sample": f"sample_{sample_id:06d}",
        "weight": 0.04,
        "status": "PASS",
        "errors": [],
        "topology": {},
        "geometry": {},
        "motion": {},
        "timing": {},
        "pressure": {},
        "direction": {},
        "curvature": {},
        "strokes": [],
    }

    if not strokes_file.is_file():
        result["status"] = "FAIL"
        result["errors"].append("strokes.json_missing")
        return result

    try:
        data = load_json(strokes_file)
    except Exception as exc:
        result["status"] = "FAIL"
        result["errors"].append(f"strokes_json_read_error:{exc}")
        return result

    strokes = extract_strokes(data)

    if strokes is None:
        result["status"] = "FAIL"
        result["errors"].append("unsupported_strokes_json_structure")
        return result

    stroke_features = []

    for index, stroke in enumerate(strokes):
        points = extract_points(stroke)

        if points is None:
            stroke_features.append(
                {
                    "stroke_index": index,
                    "status": "INVALID_STRUCTURE",
                }
            )
            continue

        stroke_features.append(
            evaluate_stroke(points, index)
        )

    valid_strokes = [
        s for s in stroke_features
        if s.get("status") not in (
            "EMPTY_OR_INVALID",
            "INVALID_STRUCTURE",
        )
    ]

    result["strokes"] = stroke_features

    # -----------------------------------------------------------------------
    # Topology
    # -----------------------------------------------------------------------

    stroke_lengths = [
        s.get("geometry", {}).get("path_length")
        for s in valid_strokes
        if s.get("geometry", {}).get("path_length") is not None
    ]

    durations = [
        s.get("motion", {}).get("duration_ms")
        for s in valid_strokes
        if s.get("motion", {}).get("duration_ms") is not None
    ]

    path_lengths = stroke_lengths

    result["topology"] = {
        "stroke_count": len(strokes),
        "valid_stroke_count": len(valid_strokes),
        "invalid_stroke_count": len(strokes) - len(valid_strokes),
        "points_per_stroke": [
            s.get("valid_point_count", 0)
            for s in stroke_features
        ],
        "stroke_length_mean": mean(stroke_lengths),
        "stroke_length_median": median(stroke_lengths),
        "stroke_length_min": minimum(stroke_lengths),
        "stroke_length_max": maximum(stroke_lengths),
    }

    # -----------------------------------------------------------------------
    # Geometry
    # -----------------------------------------------------------------------

    all_stroke_boxes = [
        s.get("geometry", {}).get("bbox")
        for s in valid_strokes
        if s.get("geometry", {}).get("bbox")
    ]

    if all_stroke_boxes:
        min_x = min(b["min_x"] for b in all_stroke_boxes)
        max_x = max(b["max_x"] for b in all_stroke_boxes)
        min_y = min(b["min_y"] for b in all_stroke_boxes)
        max_y = max(b["max_y"] for b in all_stroke_boxes)

        width = max_x - min_x
        height = max_y - min_y
    else:
        min_x = max_x = min_y = max_y = width = height = None

    straightness = [
        s.get("geometry", {}).get("straightness")
        for s in valid_strokes
        if s.get("geometry", {}).get("straightness") is not None
    ]

    result["geometry"] = {
        "global_bbox": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "width": width,
            "height": height,
        },
        "global_aspect_ratio": safe_ratio(
            width if width is not None else 0.0,
            height if height is not None else 0.0,
        ),
        "total_path_length": sum(path_lengths),
        "mean_stroke_straightness": mean(straightness),
        "median_stroke_straightness": median(straightness),
    }

    # -----------------------------------------------------------------------
    # Motion
    # -----------------------------------------------------------------------

    mean_velocities = [
        s.get("motion", {}).get("mean_velocity")
        for s in valid_strokes
        if s.get("motion", {}).get("mean_velocity") is not None
    ]

    max_velocities = [
        s.get("motion", {}).get("velocity_max")
        for s in valid_strokes
        if s.get("motion", {}).get("velocity_max") is not None
    ]

    acceleration_abs = [
        s.get("motion", {}).get("acceleration_abs_mean")
        for s in valid_strokes
        if s.get("motion", {}).get("acceleration_abs_mean") is not None
    ]

    result["motion"] = {
        "mean_velocity_across_strokes": mean(mean_velocities),
        "median_velocity_across_strokes": median(mean_velocities),
        "max_velocity_mean": mean(max_velocities),
        "velocity_std_across_strokes": stddev(mean_velocities),
        "acceleration_abs_mean": mean(acceleration_abs),
        "total_path_length": sum(path_lengths),
    }

    # -----------------------------------------------------------------------
    # Timing
    # -----------------------------------------------------------------------

    result["timing"] = {
        "stroke_duration_total_ms": sum(durations),
        "stroke_duration_mean_ms": mean(durations),
        "stroke_duration_median_ms": median(durations),
        "stroke_duration_min_ms": minimum(durations),
        "stroke_duration_max_ms": maximum(durations),
        "stroke_duration_std_ms": stddev(durations),
    }

    # -----------------------------------------------------------------------
    # Pressure
    # -----------------------------------------------------------------------

    pressure_means = []
    pressure_medians = []
    pressure_stds = []
    pressure_mins = []
    pressure_maxs = []

    for stroke in valid_strokes:
        pressure = stroke.get("pressure", {})

        if pressure.get("mean") is not None:
            pressure_means.append(pressure["mean"])

        if pressure.get("median") is not None:
            pressure_medians.append(pressure["median"])

        if pressure.get("std") is not None:
            pressure_stds.append(pressure["std"])

        if pressure.get("min") is not None:
            pressure_mins.append(pressure["min"])

        if pressure.get("max") is not None:
            pressure_maxs.append(pressure["max"])

    result["pressure"] = {
        "mean_across_strokes": mean(pressure_means),
        "median_across_strokes": median(pressure_medians),
        "std_mean_across_strokes": mean(pressure_stds),
        "global_min": minimum(pressure_mins),
        "global_max": maximum(pressure_maxs),
    }

    # -----------------------------------------------------------------------
    # Direction / curvature
    # -----------------------------------------------------------------------

    direction_change_counts = [
        s.get("direction", {}).get("direction_changes")
        for s in valid_strokes
        if s.get("direction", {}).get("direction_changes") is not None
    ]

    turn_densities = [
        s.get("curvature_proxy", {}).get("turn_density")
        for s in valid_strokes
        if s.get("curvature_proxy", {}).get("turn_density") is not None
    ]

    absolute_turn_sums = [
        s.get("direction", {}).get("absolute_turn_sum_rad")
        for s in valid_strokes
        if s.get("direction", {}).get("absolute_turn_sum_rad") is not None
    ]

    result["direction"] = {
        "direction_changes_total": sum(direction_change_counts),
        "direction_changes_mean": mean(direction_change_counts),
        "direction_changes_per_stroke": direction_change_counts,
    }

    result["curvature"] = {
        "turn_density_mean": mean(turn_densities),
        "absolute_turn_sum_mean_rad": mean(absolute_turn_sums),
        "absolute_turn_sum_total_rad": sum(absolute_turn_sums),
    }

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------

    if result["errors"]:
        result["status"] = "FAIL"

    return safe_round(result)


# ---------------------------------------------------------------------------
# Cross-sample reference statistics
# ---------------------------------------------------------------------------

def collect_sample_metric(
    samples: list[dict[str, Any]],
    path: tuple[str, ...],
) -> list[float]:
    values = []

    for sample in samples:
        current: Any = sample

        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)

        if finite(current):
            values.append(float(current))

    return values


def aggregate_reference_statistics(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    metric_paths = {
        "stroke_count": ("topology", "stroke_count"),
        "point_count": (
            "topology",
            "points_per_stroke",
        ),
        "total_path_length": (
            "geometry",
            "total_path_length",
        ),
        "global_aspect_ratio": (
            "geometry",
            "global_aspect_ratio",
        ),
        "mean_stroke_straightness": (
            "geometry",
            "mean_stroke_straightness",
        ),
        "mean_velocity": (
            "motion",
            "mean_velocity_across_strokes",
        ),
        "stroke_duration_mean_ms": (
            "timing",
            "stroke_duration_mean_ms",
        ),
        "pressure_mean": (
            "pressure",
            "mean_across_strokes",
        ),
        "direction_changes_total": (
            "direction",
            "direction_changes_total",
        ),
        "turn_density_mean": (
            "curvature",
            "turn_density_mean",
        ),
    }

    result = {}

    for name, path in metric_paths.items():
        values = collect_sample_metric(samples, path)

        result[name] = {
            "sample_count": len(values),
            "mean": mean(values),
            "median": median(values),
            "std": stddev(values),
            "min": minimum(values),
            "max": maximum(values),
        }

    # Point count is nested by stroke, so flatten it explicitly.
    point_values = []

    for sample in samples:
        for value in sample.get("topology", {}).get(
            "points_per_stroke",
            [],
        ):
            if finite(value):
                point_values.append(float(value))

    result["points_per_stroke"] = {
        "sample_count": len(point_values),
        "mean": mean(point_values),
        "median": median(point_values),
        "std": stddev(point_values),
        "min": minimum(point_values),
        "max": maximum(point_values),
    }

    return safe_round(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("SIGNATURE MACHINE — TRAJECTORY EVALUATOR v0.1")
    print("STEP 4 ONLY")
    print("=" * 72)

    expected_ids = list(range(FIRST_SAMPLE, LAST_SAMPLE + 1))

    # -----------------------------------------------------------------------
    # Verify STEP 1
    # -----------------------------------------------------------------------

    if not FREEZE_FILE.is_file():
        print("[ERROR] STEP 1 freeze marker not found.")
        print(FREEZE_FILE)
        return 1

    try:
        freeze = load_json(FREEZE_FILE)
    except Exception as exc:
        print("[ERROR] Cannot read freeze marker:", exc)
        return 2

    if freeze.get("status") != "FROZEN":
        print("[ERROR] Reference set is not FROZEN.")
        return 3

    if freeze.get("reference_sample_ids") != expected_ids:
        print("[ERROR] Frozen IDs are not exactly 001..025.")
        return 4

    print("[OK] STEP 1 freeze verified.")

    # -----------------------------------------------------------------------
    # Verify STEP 2
    # -----------------------------------------------------------------------

    if not MANIFEST_FILE.is_file():
        print("[ERROR] STEP 2 manifest not found.")
        print(MANIFEST_FILE)
        return 5

    try:
        manifest = load_json(MANIFEST_FILE)
    except Exception as exc:
        print("[ERROR] Cannot read manifest:", exc)
        return 6

    policy = manifest.get("reference_policy", {})

    if policy.get("sample_count") != 25:
        print("[ERROR] Manifest does not contain 25 samples.")
        return 7

    if policy.get("equal_weight") is not True:
        print("[ERROR] Manifest equal_weight is not true.")
        return 8

    weight = float(policy.get("weight_per_sample", -1))

    if abs(weight - 0.04) > 1e-12:
        print("[ERROR] Manifest weight is not 0.04.")
        return 9

    ids = [
        item.get("sample_id")
        for item in manifest.get("samples", [])
    ]

    if ids != expected_ids:
        print("[ERROR] Manifest IDs are not exactly 001..025.")
        return 10

    print("[OK] STEP 2 manifest verified.")
    print("[OK] Equal weight = 0.04.")

    # -----------------------------------------------------------------------
    # Verify STEP 3
    # -----------------------------------------------------------------------

    if not AUDIT_FILE.is_file():
        print("[ERROR] STEP 3 trajectory audit report not found.")
        print(AUDIT_FILE)
        return 11

    try:
        audit = load_json(AUDIT_FILE)
    except Exception as exc:
        print("[ERROR] Cannot read trajectory audit:", exc)
        return 12

    audit_summary = audit.get("summary", {})

    if audit_summary.get("fail", 0) != 0:
        print(
            "[ERROR] STEP 3 contains failed samples. "
            "Evaluator will not continue."
        )
        return 13

    print("[OK] STEP 3 trajectory audit verified.")
    print("[OK] Failed samples = 0.")

    # -----------------------------------------------------------------------
    # Prevent accidental overwrite
    # -----------------------------------------------------------------------

    if OUTPUT_JSON.exists() or OUTPUT_TXT.exists():
        print()
        print("[ALREADY BUILT]")
        print("Evaluation output already exists.")
        print("No files were overwritten.")
        print("Existing evaluation artifacts:")
        print(OUTPUT_JSON)
        print(OUTPUT_TXT)
        return 0

    # -----------------------------------------------------------------------
    # Evaluate all 25
    # -----------------------------------------------------------------------

    print()
    print("EVALUATING 25 REFERENCE TRAJECTORIES")
    print("-" * 72)

    samples = []

    for sample_id in expected_ids:
        print(f"[EVALUATE] sample_{sample_id:06d}")

        result = evaluate_sample(sample_id)
        samples.append(result)

        print(
            f"           status={result['status']} "
            f"strokes={result.get('topology', {}).get('stroke_count')} "
            f"path={result.get('geometry', {}).get('total_path_length')}"
        )

    fail_count = sum(
        1 for item in samples if item["status"] == "FAIL"
    )

    if fail_count:
        print()
        print(
            f"[ERROR] {fail_count} sample(s) failed during evaluation."
        )
        print("No training artifacts will be created.")
        return 14

    reference_statistics = aggregate_reference_statistics(samples)

    # -----------------------------------------------------------------------
    # Knowledge representation
    # -----------------------------------------------------------------------

    knowledge = {
        "schema": "signature_machine.trajectory_knowledge",
        "schema_version": "0.1",
        "cycle": "v0.1",

        "source_policy": {
            "source_type": "reference_trajectories",
            "sample_range": [FIRST_SAMPLE, LAST_SAMPLE],
            "sample_count": 25,
            "equal_weight": True,
            "weight_per_sample": 0.04,
            "sample_priority": "none",
            "generated_samples_included": False,
            "sample_026_plus_included": False,
        },

        "feature_families": [
            "topology",
            "geometry",
            "motion",
            "timing",
            "pressure",
            "direction",
            "curvature",
            "normalized_shape",
            "stroke_relationships",
        ],

        "important_boundary": (
            "This artifact is a deterministic feature representation, "
            "not a trained generative model."
        ),

        "reference_statistics": reference_statistics,
    }

    # -----------------------------------------------------------------------
    # Final output
    # -----------------------------------------------------------------------

    evaluation = {
        "schema": "signature_machine.trajectory_evaluation",
        "schema_version": "0.1",
        "cycle": "v0.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),

        "step": {
            "number": 4,
            "name": "Build trajectory evaluator",
            "training_performed": False,
            "generation_performed": False,
            "source_files_modified": False,
        },

        "reference_policy": {
            "sample_range": [FIRST_SAMPLE, LAST_SAMPLE],
            "sample_count": 25,
            "equal_weight": True,
            "weight_per_sample": 0.04,
            "sample_priority": "none",
        },

        "feature_definition": {
            "topology": (
                "stroke count, valid stroke count, points per stroke, "
                "stroke length statistics"
            ),
            "geometry": (
                "bounding box, aspect ratio, path length, displacement, "
                "straightness"
            ),
            "motion": (
                "velocity, acceleration and temporal movement statistics"
            ),
            "timing": (
                "stroke duration and duration distribution"
            ),
            "pressure": (
                "pressure distribution where pressure exists"
            ),
            "direction": (
                "direction changes, turn angles and directional endpoints"
            ),
            "curvature": (
                "turn-density and curvature proxy statistics"
            ),
            "normalized_shape": (
                "arc-length normalized stroke representation used as "
                "a structural feature, not a final signature"
            ),
            "stroke_relationships": (
                "stroke ordering and per-stroke feature sequence"
            ),
        },

        "knowledge": knowledge,

        "samples": samples,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            safe_round(evaluation),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    # Human-readable report
    lines = [
        "SIGNATURE MACHINE — TRAJECTORY EVALUATION v0.1",
        "=" * 72,
        "",
        "STEP: 4 — Build trajectory evaluator",
        "Reference set: 001..025",
        "Sample count: 25",
        "Equal weight: 1/25 = 0.04",
        "",
        "IMPORTANT",
        "-" * 72,
        "This is a deterministic trajectory feature representation.",
        "It is NOT a trained generative model.",
        "No generated sample was used.",
        "No source sample was modified.",
        "",
        "FEATURE FAMILIES",
        "-" * 72,
    ]

    for family in evaluation["feature_definition"]:
        lines.append(
            f"- {family}: {evaluation['feature_definition'][family]}"
        )

    lines.extend(
        [
            "",
            "REFERENCE STATISTICS",
            "-" * 72,
            json.dumps(
                reference_statistics,
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "PER-SAMPLE SUMMARY",
            "-" * 72,
        ]
    )

    for item in samples:
        topo = item.get("topology", {})
        geom = item.get("geometry", {})
        motion = item.get("motion", {})

        lines.append(
            f"sample_{item['sample_id']:06d}: "
            f"status={item['status']} "
            f"strokes={topo.get('stroke_count')} "
            f"points={sum(topo.get('points_per_stroke', []))} "
            f"path={geom.get('total_path_length')} "
            f"mean_velocity={motion.get('mean_velocity_across_strokes')}"
        )

    lines.extend(
        [
            "",
            "=" * 72,
            "STEP 4 COMPLETE",
            "=" * 72,
            "No sample contents were modified.",
            "No training was performed.",
            "No signatures were generated.",
            "",
        ]
    )

    OUTPUT_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("STEP 4 COMPLETE")
    print("=" * 72)
    print("Evaluated samples:", len(samples))
    print("Failed samples:", fail_count)
    print("Equal weight: 1/25 = 0.04")
    print()
    print("Trajectory feature representation created.")
    print("Training performed: NO")
    print("Generation performed: NO")
    print("Source files modified: NO")
    print()
    print("JSON:", OUTPUT_JSON)
    print("TXT :", OUTPUT_TXT)

    return 0


if __name__ == "__main__":
    sys.exit(main())
