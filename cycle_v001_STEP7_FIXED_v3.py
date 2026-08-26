# -*- coding: utf-8 -*-
"""
Signature Machine
Cycle v0.1

STEP 5 ONLY — Build / run the first deterministic reconstruction cycle.

Design rules
------------
- Reference samples 001..025 are frozen.
- Every sample has exactly equal weight: 1/25 = 0.04.
- No generated sample is used.
- No sample 026+ is used.
- No reference file is modified.
- No random points are introduced.
- No video is used as a learning source.
- This cycle is a reconstruction/measurement cycle, NOT MODEL v001.
- It measures how well the current trajectory representation can reconstruct
  the observed trajectories from their own learned/reference representation.

This first cycle intentionally uses a transparent, deterministic baseline.
It does not pretend that a trained neural model already exists.

Input:
    REFERENCE_FREEZE_v0.1.json
    REFERENCE_MANIFEST_v0.1.json
    TRAJECTORY_AUDIT_v0.1.json
    TRAJECTORY_EVALUATION_v0.1.json

Output:
    CYCLE_v0.1/
        cycle_report.json
        cycle_report.txt
        sample_000001_reconstruction.json
        ...
        sample_000025_reconstruction.json

The baseline is leave-one-out at the stroke-feature level:
    target sample is compared against a consensus built from the other
    24 reference samples.

This is important because simply reconstructing a sample from itself would
produce a misleading near-zero loss.

No files under sample_000001..sample_000025 are written.
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

FREEZE_FILE = REF / "REFERENCE_FREEZE_v0.1.json"
MANIFEST_FILE = REF / "REFERENCE_MANIFEST_v0.1.json"
AUDIT_FILE = REF / "TRAJECTORY_AUDIT_v0.1.json"
EVALUATION_FILE = REF / "TRAJECTORY_EVALUATION_v0.1.json"

CYCLE_DIR = REF / "CYCLE_v0.1"
REPORT_JSON = CYCLE_DIR / "cycle_report.json"
REPORT_TXT = CYCLE_DIR / "cycle_report.txt"

FIRST_SAMPLE = 1
LAST_SAMPLE = 25
WEIGHT = 1.0 / 25.0

EPS = 1e-12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    return statistics.pstdev(values)


def safe_ratio(a: float, b: float) -> float | None:
    if abs(b) <= EPS:
        return None
    return a / b


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def scalar_error(a: Any, b: Any) -> float | None:
    if not finite(a) or not finite(b):
        return None
    a = float(a)
    b = float(b)
    denom = max(abs(a), abs(b), EPS)
    return abs(a - b) / denom


def euclidean2(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return float("inf")
    if not a:
        return 0.0
    return math.sqrt(
        sum((float(x) - float(y)) ** 2 for x, y in zip(a, b))
        / len(a)
    )


def circular_distance(a: Any, b: Any) -> float | None:
    if not finite(a) or not finite(b):
        return None
    delta = (float(a) - float(b) + math.pi) % (2 * math.pi) - math.pi
    return abs(delta) / math.pi


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def safe_round(obj: Any, digits: int = 8) -> Any:
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, list):
        return [safe_round(x, digits) for x in obj]
    if isinstance(obj, dict):
        return {k: safe_round(v, digits) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Evaluation loading / validation
# ---------------------------------------------------------------------------

def get_sample_map(evaluation: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result = {}
    for sample in evaluation.get("samples", []):
        sid = sample.get("sample_id")
        if isinstance(sid, int):
            result[sid] = sample
    return result


def numeric_feature(sample: dict[str, Any], path: tuple[str, ...]) -> float | None:
    current: Any = sample
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return float(current) if finite(current) else None


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

def consensus_numeric(
    samples: list[dict[str, Any]],
    path: tuple[str, ...],
) -> float | None:
    values = []
    for sample in samples:
        value = numeric_feature(sample, path)
        if value is not None:
            values.append(value)
    return mean(values)


def consensus_vector(
    samples: list[dict[str, Any]],
    vectors_path: tuple[str, ...],
    index: int,
) -> list[float] | None:
    vectors = []

    for sample in samples:
        current: Any = sample
        for key in vectors_path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)

        if not isinstance(current, list):
            continue

        if index >= len(current):
            continue

        vector = current[index]

        if (
            isinstance(vector, list)
            and len(vector) == 2
            and all(finite(v) for v in vector)
        ):
            vectors.append([float(vector[0]), float(vector[1])])

    if not vectors:
        return None

    return [
        mean([v[0] for v in vectors]),
        mean([v[1] for v in vectors]),
    ]


# ---------------------------------------------------------------------------
# Leave-one-out reconstruction
# ---------------------------------------------------------------------------

def reconstruct_sample(
    target: dict[str, Any],
    peers: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Reconstruct a transparent baseline for one target.

    We compare target trajectory descriptors with consensus descriptors
    learned from the other 24 samples.

    Stroke sequence:
        We do NOT invent stroke points.
        Instead we estimate structural properties such as stroke count,
        average stroke length, timing, direction and normalized shape.

    Because signatures can have different stroke counts, the first cycle
    measures both:
        1. global style error
        2. sequence-compatible error for overlapping stroke positions

    This is a diagnostic baseline, not the final generator.
    """

    target_top = target.get("topology", {})
    target_geo = target.get("geometry", {})
    target_motion = target.get("motion", {})
    target_timing = target.get("timing", {})
    target_pressure = target.get("pressure", {})
    target_direction = target.get("direction", {})
    target_curvature = target.get("curvature", {})

    # ---------------------------------------------------------------
    # Global scalar descriptors
    # ---------------------------------------------------------------

    scalar_specs = [
        (
            "stroke_count",
            target_top.get("stroke_count"),
            ("topology", "stroke_count"),
        ),
        (
            "total_path_length",
            target_geo.get("total_path_length"),
            ("geometry", "total_path_length"),
        ),
        (
            "global_aspect_ratio",
            target_geo.get("global_aspect_ratio"),
            ("geometry", "global_aspect_ratio"),
        ),
        (
            "mean_stroke_straightness",
            target_geo.get("mean_stroke_straightness"),
            ("geometry", "mean_stroke_straightness"),
        ),
        (
            "mean_velocity",
            target_motion.get("mean_velocity_across_strokes"),
            ("motion", "mean_velocity_across_strokes"),
        ),
        (
            "stroke_duration_mean_ms",
            target_timing.get("stroke_duration_mean_ms"),
            ("timing", "stroke_duration_mean_ms"),
        ),
        (
            "pressure_mean",
            target_pressure.get("mean_across_strokes"),
            ("pressure", "mean_across_strokes"),
        ),
        (
            "direction_changes_total",
            target_direction.get("direction_changes_total"),
            ("direction", "direction_changes_total"),
        ),
        (
            "turn_density_mean",
            target_curvature.get("turn_density_mean"),
            ("curvature", "turn_density_mean"),
        ),
    ]

    global_errors = {}

    for name, observed, path in scalar_specs:
        consensus = consensus_numeric(peers, path)

        if name == "stroke_count":
            # Stroke count is discrete. Normalize by the larger structure.
            if finite(observed) and finite(consensus):
                denom = max(abs(float(observed)), abs(float(consensus)), 1.0)
                err = abs(float(observed) - float(consensus)) / denom
            else:
                err = None
        else:
            err = scalar_error(observed, consensus)

        global_errors[name] = {
            "observed": observed,
            "consensus": consensus,
            "normalized_error": err,
        }

    valid_global_errors = [
        item["normalized_error"]
        for item in global_errors.values()
        if finite(item["normalized_error"])
    ]

    global_loss = mean(valid_global_errors)

    # ---------------------------------------------------------------
    # Stroke sequence / normalized shape
    # ---------------------------------------------------------------

    target_strokes = target.get("strokes", [])
    peer_strokes = [
        sample.get("strokes", [])
        for sample in peers
    ]

    target_valid = [
        s for s in target_strokes
        if isinstance(s, dict)
        and isinstance(s.get("normalized_shape", {}).get("points"), list)
    ]

    overlap = 0
    shape_errors = []
    stroke_length_errors = []
    stroke_duration_errors = []
    stroke_velocity_errors = []
    stroke_direction_errors = []
    stroke_curvature_errors = []

    reconstructed_strokes = []

    max_peer_stroke_count = 0
    for strokes in peer_strokes:
        valid = [
            s for s in strokes
            if isinstance(s, dict)
        ]
        max_peer_stroke_count = max(
            max_peer_stroke_count,
            len(valid),
        )

    for index, target_stroke in enumerate(target_valid):
        if index >= max_peer_stroke_count:
            break

        peer_at_position = []

        for strokes in peer_strokes:
            if index >= len(strokes):
                continue

            candidate = strokes[index]

            if not isinstance(candidate, dict):
                continue

            peer_at_position.append(candidate)

        if not peer_at_position:
            continue

        overlap += 1

        # Normalized shape: compare the fixed 32-point representation.
        target_shape = target_stroke.get(
            "normalized_shape", {}
        ).get("points", [])

        peer_shapes = [
            s.get("normalized_shape", {}).get("points", [])
            for s in peer_at_position
        ]

        shape_points = []

        for point_index, point in enumerate(target_shape):
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not all(finite(v) for v in point)
            ):
                continue

            peer_vectors = []

            for shape in peer_shapes:
                if point_index >= len(shape):
                    continue

                peer_point = shape[point_index]

                if (
                    isinstance(peer_point, list)
                    and len(peer_point) == 2
                    and all(finite(v) for v in peer_point)
                ):
                    peer_vectors.append(peer_point)

            if not peer_vectors:
                continue

            consensus_point = [
                mean([p[0] for p in peer_vectors]),
                mean([p[1] for p in peer_vectors]),
            ]

            shape_points.append(
                euclidean2(
                    [float(point[0]), float(point[1])],
                    consensus_point,
                )
            )

        if shape_points:
            shape_errors.append(mean(shape_points))

        # Scalar stroke-level errors.
        pairs = [
            (
                "length",
                target_stroke.get("geometry", {}).get("path_length"),
                [
                    s.get("geometry", {}).get("path_length")
                    for s in peer_at_position
                ],
                stroke_length_errors,
            ),
            (
                "duration",
                target_stroke.get("motion", {}).get("duration_ms"),
                [
                    s.get("motion", {}).get("duration_ms")
                    for s in peer_at_position
                ],
                stroke_duration_errors,
            ),
            (
                "velocity",
                target_stroke.get("motion", {}).get("mean_velocity"),
                [
                    s.get("motion", {}).get("mean_velocity")
                    for s in peer_at_position
                ],
                stroke_velocity_errors,
            ),
            (
                "curvature",
                target_stroke.get("curvature_proxy", {}).get(
                    "turn_density"
                ),
                [
                    s.get("curvature_proxy", {}).get(
                        "turn_density"
                    )
                    for s in peer_at_position
                ],
                stroke_curvature_errors,
            ),
        ]

        for _, observed, peer_values, collector in pairs:
            values = [
                float(v)
                for v in peer_values
                if finite(v)
            ]

            consensus = mean(values)

            err = scalar_error(observed, consensus)

            if err is not None:
                collector.append(err)

        observed_dir = target_stroke.get(
            "direction", {}
        ).get("initial_direction_rad")

        peer_dirs = [
            s.get("direction", {}).get("initial_direction_rad")
            for s in peer_at_position
        ]

        peer_dirs = [
            float(v) for v in peer_dirs if finite(v)
        ]

        if finite(observed_dir) and peer_dirs:
            # Circular mean via vector averaging.
            sx = sum(math.cos(v) for v in peer_dirs)
            sy = sum(math.sin(v) for v in peer_dirs)
            consensus_dir = math.atan2(sy, sx)

            stroke_direction_errors.append(
                circular_distance(
                    observed_dir,
                    consensus_dir,
                )
            )

        reconstructed_strokes.append(
            {
                "stroke_index": index,
                "source": "leave_one_out_reference_consensus",
                "peer_count": len(peer_at_position),
                "normalized_shape_reconstructed": True,
            }
        )

    shape_loss = mean(shape_errors)
    stroke_length_loss = mean(stroke_length_errors)
    stroke_duration_loss = mean(stroke_duration_errors)
    stroke_velocity_loss = mean(stroke_velocity_errors)
    stroke_direction_loss = mean(stroke_direction_errors)
    stroke_curvature_loss = mean(stroke_curvature_errors)

    sequence_losses = [
        x for x in [
            shape_loss,
            stroke_length_loss,
            stroke_duration_loss,
            stroke_velocity_loss,
            stroke_direction_loss,
            stroke_curvature_loss,
        ]
        if finite(x)
    ]

    sequence_loss = mean(sequence_losses)

    # ---------------------------------------------------------------
    # Combined diagnostic loss
    # ---------------------------------------------------------------

    # The first cycle deliberately keeps weights explicit and stable.
    # Global descriptors = 40%, sequence/shape = 60%.
    # This is a baseline configuration, not a claim of optimality.
    if finite(global_loss) and finite(sequence_loss):
        total_loss = (
            0.40 * float(global_loss)
            + 0.60 * float(sequence_loss)
        )
    elif finite(global_loss):
        total_loss = float(global_loss)
    elif finite(sequence_loss):
        total_loss = float(sequence_loss)
    else:
        total_loss = None

    return {
        "target_sample_id": target.get("sample_id"),
        "target_weight": WEIGHT,
        "reconstruction_mode": "leave_one_out_reference_consensus",
        "peer_sample_count": len(peers),
        "peer_weight_each": (
            1.0 / len(peers) if peers else None
        ),

        "global_descriptor_loss": global_loss,
        "sequence_descriptor_loss": sequence_loss,
        "total_loss": total_loss,

        "loss_components": {
            "global": global_errors,
            "shape": shape_loss,
            "stroke_length": stroke_length_loss,
            "stroke_duration": stroke_duration_loss,
            "stroke_velocity": stroke_velocity_loss,
            "stroke_direction": stroke_direction_loss,
            "stroke_curvature": stroke_curvature_loss,
        },

        "sequence_alignment": {
            "target_valid_strokes": len(target_valid),
            "peer_max_strokes": max_peer_stroke_count,
            "overlapping_positions": overlap,
        },

        "reconstructed_strokes": reconstructed_strokes,

        "interpretation": (
            "Diagnostic reconstruction baseline only. "
            "This output is not MODEL v001 and must not be used "
            "as Sample 026."
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("SIGNATURE MACHINE — CYCLE v0.1")
    print("STEP 5 ONLY")
    print("=" * 72)

    expected_ids = list(range(FIRST_SAMPLE, LAST_SAMPLE + 1))

    # ---------------------------------------------------------------
    # STEP 1 verification
    # ---------------------------------------------------------------

    if not FREEZE_FILE.is_file():
        print("[ERROR] STEP 1 freeze marker missing.")
        return 1

    freeze = load_json(FREEZE_FILE)

    if freeze.get("status") != "FROZEN":
        print("[ERROR] Reference set is not frozen.")
        return 2

    if freeze.get("reference_sample_ids") != expected_ids:
        print("[ERROR] Frozen reference IDs are not exactly 001..025.")
        return 3

    print("[OK] STEP 1 freeze verified.")

    # ---------------------------------------------------------------
    # STEP 2 verification
    # ---------------------------------------------------------------

    if not MANIFEST_FILE.is_file():
        print("[ERROR] STEP 2 manifest missing.")
        return 4

    manifest = load_json(MANIFEST_FILE)
    policy = manifest.get("reference_policy", {})

    if policy.get("sample_count") != 25:
        print("[ERROR] Manifest sample count is not 25.")
        return 5

    if policy.get("equal_weight") is not True:
        print("[ERROR] Manifest equal_weight is not true.")
        return 6

    if abs(float(policy.get("weight_per_sample", -1)) - WEIGHT) > 1e-12:
        print("[ERROR] Manifest weight is not 0.04.")
        return 7

    print("[OK] STEP 2 manifest verified.")
    print("[OK] Equal weight = 0.04.")

    # ---------------------------------------------------------------
    # STEP 3 verification
    # ---------------------------------------------------------------

    if not AUDIT_FILE.is_file():
        print("[ERROR] STEP 3 audit missing.")
        return 8

    audit = load_json(AUDIT_FILE)

    if audit.get("summary", {}).get("fail", 0) != 0:
        print("[ERROR] STEP 3 contains failed samples.")
        return 9

    print("[OK] STEP 3 trajectory audit verified.")
    print("[OK] Failed samples = 0.")

    # ---------------------------------------------------------------
    # STEP 4 verification
    # ---------------------------------------------------------------

    if not EVALUATION_FILE.is_file():
        print("[ERROR] STEP 4 trajectory evaluation missing.")
        return 10

    evaluation = load_json(EVALUATION_FILE)

    if evaluation.get("reference_policy", {}).get("sample_count") != 25:
        print("[ERROR] STEP 4 does not contain 25 reference samples.")
        return 11

    evaluation_samples = get_sample_map(evaluation)

    if sorted(evaluation_samples) != expected_ids:
        print("[ERROR] STEP 4 sample IDs are not exactly 001..025.")
        return 12

    print("[OK] STEP 4 trajectory evaluation verified.")
    print("[OK] Evaluated samples = 25.")

    # ---------------------------------------------------------------
    # Existing-cycle handling
    # ---------------------------------------------------------------
    #
    # STEP 5 remains non-destructive. If CYCLE_v0.1 already exists,
    # do not rebuild or overwrite it. STEP 7 reads it as input only.

    if CYCLE_DIR.exists():
        print()
        print("[ALREADY BUILT]")
        print("CYCLE_v0.1 already exists.")
        print("No files will be overwritten.")
        print(CYCLE_DIR)
        print()
        print("[STEP 7]")
        print("Reading existing CYCLE_v0.1 for loss measurement.")

        report_candidates = [
            CYCLE_DIR / "cycle_report.json",
            CYCLE_DIR / "report.json",
        ]

        report_path = next(
            (p for p in report_candidates if p.exists()),
            None,
        )

        if report_path is None:
            print("[STEP 7 ERROR] Existing cycle report not found.")
            return 1

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                existing_report = json.load(f)
        except Exception as exc:
            print(f"[STEP 7 ERROR] Could not read cycle report: {exc}")
            return 1

        # CYCLE_v0.1 schema is confirmed:
        # results[i] contains target_sample_id, target_weight,
        # peer_sample_count, peer_weight_each and total_loss.
        #
        # STEP 7 only measures the existing results. It does not rebuild
        # reconstruction and does not modify CYCLE_v0.1.

        results = existing_report.get("results")

        if not isinstance(results, list):
            print("[STEP 7 ERROR] cycle_report.json.results is not a list.")
            return 1

        if len(results) != 25:
            print(
                "[STEP 7 ERROR] Expected exactly 25 results; "
                f"found {len(results)}."
            )
            return 1

        filtered = []

        for result in results:
            if not isinstance(result, dict):
                print("[STEP 7 ERROR] Invalid result entry.")
                return 1

            target_id = result.get("target_sample_id")
            target_weight = result.get("target_weight")
            total_loss = result.get("total_loss")

            if not isinstance(target_id, int):
                print(
                    "[STEP 7 ERROR] Invalid target_sample_id: "
                    f"{target_id!r}"
                )
                return 1

            if not 1 <= target_id <= 25:
                print(
                    "[STEP 7 ERROR] Target outside frozen reference set: "
                    f"{target_id}"
                )
                return 1

            if not isinstance(target_weight, (int, float)):
                print(
                    "[STEP 7 ERROR] Invalid target_weight for "
                    f"sample {target_id}."
                )
                return 1

            if not isinstance(total_loss, (int, float)):
                print(
                    "[STEP 7 ERROR] Invalid total_loss for "
                    f"sample {target_id}."
                )
                return 1

            filtered.append({
                "target_sample_id": target_id,
                "target_weight": float(target_weight),
                "total_loss": float(total_loss),
                "peer_sample_count": result.get("peer_sample_count"),
                "peer_weight_each": result.get("peer_weight_each"),
                "global_descriptor_loss":
                    result.get("global_descriptor_loss"),
                "sequence_descriptor_loss":
                    result.get("sequence_descriptor_loss"),
            })

        filtered.sort(key=lambda r: r["target_sample_id"])

        target_ids = [
            row["target_sample_id"]
            for row in filtered
        ]

        if target_ids != list(range(1, 26)):
            print(
                "[STEP 7 ERROR] Reference targets are not exactly "
                "001..025."
            )
            return 1

        # Project rule: all 25 references have equal weight.
        expected_weight = 1.0 / 25.0

        if any(
            abs(row["target_weight"] - expected_weight) > 1e-9
            for row in filtered
        ):
            print(
                "[STEP 7 ERROR] Target weights are not uniformly "
                "0.04 across samples 001..025."
            )
            return 1

        losses = [row["total_loss"] for row in filtered]
        weighted_mean = sum(
            row["total_loss"] * row["target_weight"]
            for row in filtered
        )

        baseline = 0.32439998436125367
        improvement = baseline - weighted_mean

        step7_report = {
            "version": "0.1",
            "step": 7,
            "reference_policy": {
                "samples": "001..025",
                "count": 25,
                "equal_weight": True,
                "weight_per_sample": 0.04,
                "priority": "none",
            },
            "consensus_policy": {
                "peer_count_per_target": 24,
                "peer_weight_each": 1.0 / 24.0,
                "note": "Peer weight belongs to reconstruction consensus and is distinct from the frozen target/reference weight of 0.04.",
            },
            "baseline": {
                "cycle": "CYCLE_v0.1",
                "mean_loss": baseline,
            },
            "measurement": {
                "evaluated_samples": 25,
                "mean_loss": sum(losses) / 25.0,
                "weighted_mean_loss": weighted_mean,
                "difference_from_baseline": weighted_mean - baseline,
                "improvement_over_baseline": improvement,
                "better_than_baseline": weighted_mean < baseline,
            },
            "safety": {
                "video_used": False,
                "random_points_used": False,
                "generated_samples_used": False,
                "model_v001_created": False,
                "sample_026_created": False,
                "reference_samples_modified": False,
            },
            "per_sample": filtered,
        }

        step7_path = CYCLE_DIR / "STEP7_LOSS_MEASUREMENT_v0.1.json"
        with open(step7_path, "w", encoding="utf-8") as f:
            json.dump(
                step7_report,
                f,
                ensure_ascii=False,
                indent=2,
            )

        print("STEP 7 COMPLETE")
        print("-" * 72)
        print("Evaluated samples:", 25)
        print("Equal weight:", 0.04)
        print("Baseline loss:", baseline)
        print("Measured mean loss:", weighted_mean)
        print("Improvement:", improvement)
        print("Better than baseline:", mean_loss < baseline)
        print("Video used: NO")
        print("Random points: NO")
        print("Sample 026 created: NO")
        print("Model v001 created: NO")
        print("Report:", step7_path)
        return 0

    CYCLE_DIR.mkdir(parents=True, exist_ok=False)

    # ---------------------------------------------------------------
    # Run leave-one-out reconstruction
    # ---------------------------------------------------------------

    print()
    print("RUNNING LEAVE-ONE-OUT RECONSTRUCTION")
    print("-" * 72)

    results = []

    for target_id in expected_ids:
        target = evaluation_samples[target_id]
        peers = [
            evaluation_samples[sid]
            for sid in expected_ids
            if sid != target_id
        ]

        print(
            f"[RECONSTRUCT] sample_{target_id:06d} "
            f"from {len(peers)} peer references"
        )

        result = reconstruct_sample(target, peers)
        results.append(result)

        sample_output = CYCLE_DIR / (
            f"sample_{target_id:06d}_reconstruction.json"
        )

        sample_output.write_text(
            json.dumps(
                safe_round(result),
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        print(
            f"               total_loss={result['total_loss']}"
        )

    # ---------------------------------------------------------------
    # Aggregate weighted loss
    # ---------------------------------------------------------------

    losses = [
        r["total_loss"]
        for r in results
        if finite(r["total_loss"])
    ]

    weighted_total_loss = (
        sum(float(r["total_loss"]) * WEIGHT for r in results
            if finite(r["total_loss"]))
        if results
        else None
    )

    mean_loss = mean([float(v) for v in losses])

    loss_distribution = {
        "count": len(losses),
        "mean": mean_loss,
        "median": median(losses),
        "std": stddev(losses),
        "min": min(losses) if losses else None,
        "max": max(losses) if losses else None,
        "p10": percentile(losses, 0.10),
        "p90": percentile(losses, 0.90),
    }

    # ---------------------------------------------------------------
    # Cycle report
    # ---------------------------------------------------------------

    report = {
        "schema": "signature_machine.cycle_report",
        "schema_version": "0.1",
        "cycle": "v0.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),

        "step": {
            "number": 5,
            "name": "Build Cycle v0.1",
            "training_model_created": False,
            "generation_performed": False,
            "sample_026_created": False,
        },

        "reference_policy": {
            "sample_range": [FIRST_SAMPLE, LAST_SAMPLE],
            "sample_count": 25,
            "equal_weight": True,
            "weight_per_sample": WEIGHT,
            "sample_priority": "none",
            "generated_data_included": False,
        },

        "reconstruction_policy": {
            "mode": "leave_one_out_reference_consensus",
            "peer_count_per_target": 24,
            "randomness": "none",
            "random_points": False,
            "video_used_as_source": False,
            "source_of_truth": "strokes.json -> trajectory evaluation",
            "global_loss_weight": 0.40,
            "sequence_loss_weight": 0.60,
        },

        "loss": {
            "weighted_total_loss": weighted_total_loss,
            "unweighted_mean_loss": mean_loss,
            "distribution": loss_distribution,
        },

        "results": results,

        "status": {
            "cycle_completed": True,
            "reference_integrity_preserved": True,
            "next_step": "STEP 6 — Run first reconstruction cycle",
            "model_v001": False,
            "sample_026": False,
        },

        "important_note": (
            "Cycle v0.1 is a transparent deterministic baseline. "
            "It measures reconstruction capability and produces loss. "
            "It is not a trained generative model and is not approved "
            "for new-name generation."
        ),
    }

    REPORT_JSON.write_text(
        json.dumps(
            safe_round(report),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    # ---------------------------------------------------------------
    # Human-readable report
    # ---------------------------------------------------------------

    txt = [
        "SIGNATURE MACHINE — CYCLE v0.1",
        "=" * 72,
        "STEP 5 ONLY",
        "",
        "REFERENCE",
        "-" * 72,
        "Samples: 001..025",
        "Count: 25",
        "Equal weight: 0.04",
        "Sample priority: none",
        "Generated data: NO",
        "Video source: NO",
        "",
        "RECONSTRUCTION",
        "-" * 72,
        "Mode: leave-one-out reference consensus",
        "Peers per target: 24",
        "Random points: NO",
        "Global loss weight: 0.40",
        "Sequence loss weight: 0.60",
        "",
        "LOSS",
        "-" * 72,
        f"Weighted total loss: {weighted_total_loss}",
        f"Unweighted mean loss: {mean_loss}",
        f"Median: {loss_distribution['median']}",
        f"Std: {loss_distribution['std']}",
        f"Min: {loss_distribution['min']}",
        f"Max: {loss_distribution['max']}",
        "",
        "PER-SAMPLE",
        "-" * 72,
    ]

    for result in results:
        txt.append(
            f"sample_{result['target_sample_id']:06d} "
            f"loss={result['total_loss']} "
            f"global={result['global_descriptor_loss']} "
            f"sequence={result['sequence_descriptor_loss']}"
        )

    txt.extend(
        [
            "",
            "=" * 72,
            "STEP 5 COMPLETE",
            "=" * 72,
            "Reference contents modified: NO",
            "Training model created: NO",
            "New signature generated: NO",
            "Sample 026 created: NO",
            "",
            "Next conceptual step: STEP 6 — Run first reconstruction cycle.",
            "",
        ]
    )

    REPORT_TXT.write_text(
        "\n".join(txt),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("STEP 5 COMPLETE")
    print("=" * 72)
    print("Targets reconstructed:", len(results))
    print("Peer references per target: 24")
    print("Equal reference weight:", WEIGHT)
    print("Random points: NO")
    print("Video used: NO")
    print("Model v001 created: NO")
    print("Sample 026 created: NO")
    print()
    print("Weighted total loss:", weighted_total_loss)
    print("Mean loss:", mean_loss)
    print()
    print("Cycle directory:", CYCLE_DIR)
    print("Report JSON:", REPORT_JSON)
    print("Report TXT :", REPORT_TXT)

    return 0


if __name__ == "__main__":
    sys.exit(main())
