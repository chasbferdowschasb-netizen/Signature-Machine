# -*- coding: utf-8 -*-

"""
Signature Machine
Motion Learning Builder v0.2

Purpose:
    Build and incrementally update motion_style_state.json from immutable
    trajectory.json files.

Rules:
    - Existing reference samples are read-only.
    - No changes are made to strokes.json or trajectory.json.
    - No dependency on library/.
    - Every reference sample has equal weight.
    - Motion profiles are normalized to the canonical length of 32.
    - Incremental updates preserve the existing learned statistics.
    - The builder is deterministic; no random sampling or noise is introduced.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, pstdev


PROJECT_ROOT = Path(__file__).resolve().parent

SAMPLES_DIR = (
    PROJECT_ROOT
    / "online_training_data"
    / "reference_learning"
    / "samples"
)

MOTION_DIR = (
    PROJECT_ROOT
    / "online_training_data"
    / "motion_learning"
)

OUTPUT_FILE = MOTION_DIR / "motion_style_state.json"

SCHEMA_VERSION = "motion_style_state_v0.2"
LEGACY_SCHEMA_VERSIONS = {"motion_style_state_v0.1"}
PROFILE_LENGTH = 32

PROFILE_NAMES = (
    "speed_profile",
    "pressure_profile",
    "direction_profile",
    "curvature_profile",
    "tilt_x_profile",
    "tilt_y_profile",
    "twist_profile",
)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(f"Invalid JSON object: {path}")

    return payload


def safe_float(value) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(value):
        return 0.0

    return value


def resample_vector(
    values: list[float],
    count: int = PROFILE_LENGTH,
) -> list[float]:
    """Deterministically resample one profile to the canonical length."""
    cleaned = [safe_float(value) for value in values]

    if not cleaned:
        return []

    if count <= 1:
        return [cleaned[0]]

    if len(cleaned) == 1:
        return [cleaned[0]] * count

    if len(cleaned) == count:
        return cleaned

    result = []
    source_last = len(cleaned) - 1
    target_last = count - 1

    for index in range(count):
        position = index * source_last / target_last
        left = int(math.floor(position))
        right = min(left + 1, source_last)
        fraction = position - left

        result.append(
            cleaned[left] * (1.0 - fraction)
            + cleaned[right] * fraction
        )

    return result


def average_vectors(vectors: list[list[float]]) -> list[float]:
    """
    Reduce all valid stroke profiles belonging to ONE sample to one vector.

    This is the key equal-sample-weight step: a sample contributes exactly
    one vector to the global profile statistics, regardless of stroke count.
    """
    if not vectors:
        return []

    columns = zip(*vectors)
    return [
        mean(column)
        for column in columns
    ]


def profile_statistics_from_vectors(
    vectors: list[list[float]],
) -> dict:
    """Create deterministic per-position sufficient statistics."""
    if not vectors:
        return {
            "count": 0,
            "length": PROFILE_LENGTH,
            "mean": [],
            "std": [],
        }

    columns = list(zip(*vectors))

    return {
        "count": len(vectors),
        "length": PROFILE_LENGTH,
        "mean": [
            mean(column)
            for column in columns
        ],
        "std": [
            pstdev(column)
            if len(column) > 1
            else 0.0
            for column in columns
        ],
    }


def merge_profile_statistics(
    previous: dict,
    incoming_vectors: list[list[float]],
) -> dict:
    """
    Merge new equal-weight sample vectors into persisted statistics.

    The persisted mean/std are converted to per-position sufficient
    statistics and merged with the incoming observations using the
    parallel-variance identity. No old samples are re-read.
    """
    if not incoming_vectors:
        return previous

    old_count = int(previous.get("count", 0) or 0)
    old_mean = [
        safe_float(value)
        for value in previous.get("mean", [])
    ]
    old_std = [
        safe_float(value)
        for value in previous.get("std", [])
    ]

    if (
        old_count <= 0
        or len(old_mean) != PROFILE_LENGTH
    ):
        return profile_statistics_from_vectors(
            incoming_vectors
        )

    if len(old_std) != PROFILE_LENGTH:
        old_std = [0.0] * PROFILE_LENGTH

    new_count = len(incoming_vectors)
    new_columns = list(zip(*incoming_vectors))
    new_means = [
        mean(column)
        for column in new_columns
    ]
    new_m2 = [
        sum(
            (value - new_mean) ** 2
            for value in column
        )
        for column, new_mean in zip(
            new_columns,
            new_means,
        )
    ]

    old_m2 = [
        (old_std[index] ** 2) * old_count
        for index in range(PROFILE_LENGTH)
    ]

    total_count = old_count + new_count
    merged_mean = []
    merged_std = []

    for index in range(PROFILE_LENGTH):
        delta = new_means[index] - old_mean[index]

        combined_mean = (
            old_mean[index]
            + delta * new_count / total_count
        )

        combined_m2 = (
            old_m2[index]
            + new_m2[index]
            + (
                delta ** 2
                * old_count
                * new_count
                / total_count
            )
        )

        merged_mean.append(combined_mean)
        merged_std.append(
            math.sqrt(
                max(combined_m2 / total_count, 0.0)
            )
        )

    return {
        "count": total_count,
        "length": PROFILE_LENGTH,
        "mean": merged_mean,
        "std": merged_std,
    }


def merge_scalar_statistics(
    previous: dict,
    incoming_values: list[float],
) -> dict:
    """Incrementally merge scalar observations without re-reading old samples."""
    values = [safe_float(value) for value in incoming_values]
    if not values:
        return previous

    old_count = int(previous.get("count", 0) or 0)
    old_mean = safe_float(previous.get("mean", 0.0))
    old_std = safe_float(previous.get("std", 0.0))

    new_count = len(values)
    new_mean = mean(values)
    new_m2 = sum((value - new_mean) ** 2 for value in values)

    if old_count <= 0:
        merged_mean = new_mean
        merged_std = math.sqrt(max(new_m2 / new_count, 0.0))
        old_min = None
        old_max = None
    else:
        old_m2 = (old_std ** 2) * old_count
        total_count = old_count + new_count
        delta = new_mean - old_mean
        merged_mean = old_mean + delta * new_count / total_count
        merged_m2 = (
            old_m2
            + new_m2
            + delta ** 2 * old_count * new_count / total_count
        )
        merged_std = math.sqrt(max(merged_m2 / total_count, 0.0))
        old_min = previous.get("min")
        old_max = previous.get("max")

    result = dict(previous)
    result["count"] = old_count + new_count
    result["mean"] = merged_mean
    result["std"] = merged_std

    incoming_min = min(values)
    incoming_max = max(values)
    if old_min is None:
        result["min"] = incoming_min
    else:
        result["min"] = min(old_min, incoming_min)
    if old_max is None:
        result["max"] = incoming_max
    else:
        result["max"] = max(old_max, incoming_max)

    return result


def collect_trajectories() -> tuple[list[dict], int]:
    if not SAMPLES_DIR.is_dir():
        raise FileNotFoundError(
            f"Reference samples directory not found:\n{SAMPLES_DIR}"
        )

    samples = []
    total_strokes = 0

    sample_dirs = sorted(
        path
        for path in SAMPLES_DIR.iterdir()
        if path.is_dir()
    )

    for sample_dir in sample_dirs:
        trajectory_file = sample_dir / "trajectory.json"

        if not trajectory_file.is_file():
            continue

        payload = load_json(trajectory_file)

        strokes = payload.get("strokes")

        if not isinstance(strokes, list):
            continue

        sample_id = str(
            payload.get(
                "sample_id",
                sample_dir.name,
            )
        )

        samples.append(
            {
                "sample_id": sample_id,
                "trajectory_file": str(
                    trajectory_file.relative_to(PROJECT_ROOT)
                ),
                "strokes": strokes,
            }
        )

        total_strokes += len(strokes)

    samples.sort(key=lambda sample: sample["sample_id"])
    return samples, total_strokes


def collect_sample_profile_vectors(
    sample: dict,
) -> dict[str, list[float]]:
    """
    Produce exactly one canonical 32-point vector per profile per sample.
    """
    profile_strokes = {
        name: []
        for name in PROFILE_NAMES
    }

    for stroke in sample["strokes"]:
        if not isinstance(stroke, dict):
            continue

        for profile_name in PROFILE_NAMES:
            profile = stroke.get(profile_name, [])

            if not isinstance(profile, list) or not profile:
                continue

            vector = resample_vector(profile)

            if vector:
                profile_strokes[profile_name].append(vector)

    return {
        name: average_vectors(vectors)
        for name, vectors in profile_strokes.items()
    }


def build_sample_profile_vectors(
    samples: list[dict],
) -> dict[str, list[list[float]]]:
    result = {
        name: []
        for name in PROFILE_NAMES
    }

    for sample in samples:
        sample_vectors = collect_sample_profile_vectors(sample)

        for profile_name in PROFILE_NAMES:
            vector = sample_vectors[profile_name]

            if vector:
                result[profile_name].append(vector)

    return result


def is_valid_incremental_state(state: dict) -> bool:
    if state.get("schema_version") != SCHEMA_VERSION:
        return False

    sample_ids = state.get("sample_ids")
    profiles = (
        state.get("feature_statistics", {})
        .get("profiles", {})
    )

    if not isinstance(sample_ids, list):
        return False

    if not isinstance(profiles, dict):
        return False

    for profile_name in PROFILE_NAMES:
        profile = profiles.get(profile_name)

        if not isinstance(profile, dict):
            return False

        if int(profile.get("count", 0) or 0) != len(
            [
                sample_id
                for sample_id in sample_ids
                if sample_id
            ]
        ):
            return False

        if profile.get("length") != PROFILE_LENGTH:
            return False

        if (
            len(profile.get("mean", [])) != PROFILE_LENGTH
            or len(profile.get("std", [])) != PROFILE_LENGTH
        ):
            return False

    return True


def load_previous_state() -> dict | None:
    if not OUTPUT_FILE.is_file():
        return None

    try:
        state = load_json(OUTPUT_FILE)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    if not is_valid_incremental_state(state):
        return None

    return state


def make_initial_state(
    samples: list[dict],
    total_strokes: int,
    profile_vectors: dict[str, list[list[float]]],
    operation: str,
) -> dict:
    profile_statistics = {
        name: profile_statistics_from_vectors(
            profile_vectors[name]
        )
        for name in PROFILE_NAMES
    }

    stroke_counts = [
        len(sample["strokes"])
        for sample in samples
    ]

    point_counts = []

    for sample in samples:
        for stroke in sample["strokes"]:
            if not isinstance(stroke, dict):
                continue

            trajectory = stroke.get(
                "normalized_trajectory",
                [],
            )

            if isinstance(trajectory, list):
                point_counts.append(len(trajectory))

    return {
        "schema_version": SCHEMA_VERSION,
        "learning_mode": "incremental",

        "source": {
            "dataset": (
                "online_training_data/"
                "reference_learning/samples"
            ),
            "trajectory_files": len(samples),
            "total_strokes": total_strokes,
            "library_dependency": False,
        },

        "sample_count": len(samples),

        "sample_ids": [
            sample["sample_id"]
            for sample in samples
        ],

        "feature_statistics": {
            "stroke_count": {
                "count": len(stroke_counts),
                "mean": (
                    mean(stroke_counts)
                    if stroke_counts
                    else 0.0
                ),
                "std": (
                    pstdev(stroke_counts)
                    if len(stroke_counts) > 1
                    else 0.0
                ),
                "min": (
                    min(stroke_counts)
                    if stroke_counts
                    else 0
                ),
                "max": (
                    max(stroke_counts)
                    if stroke_counts
                    else 0
                ),
            },

            "point_count_per_stroke": {
                "count": len(point_counts),
                "mean": (
                    mean(point_counts)
                    if point_counts
                    else 0.0
                ),
                "std": (
                    pstdev(point_counts)
                    if len(point_counts) > 1
                    else 0.0
                ),
            },

            "profiles": profile_statistics,
        },

        "feature_weights": {
            "trajectory_geometry": 1.0,
            "speed_profile": 1.0,
            "pressure_profile": 1.0,
            "direction_profile": 1.0,
            "curvature_profile": 1.0,
            "tilt_x_profile": 1.0,
            "tilt_y_profile": 1.0,
            "twist_profile": 1.0,
        },

        "learned_rules": {
            "whole_signature_trajectory": True,
            "strokes_processed_independently": True,
            "touch_points_are_valid_content": True,
            "no_synthetic_cross_stroke_paths": True,
            "equal_sample_weight": True,
            "reference_samples_immutable": True,
            "incremental_learning": True,
        },

        "learning_history": [
            {
                "operation": operation,
                "sample_count": len(samples),
                "trajectory_files": len(samples),
                "total_strokes": total_strokes,
                "schema_version": SCHEMA_VERSION,
            }
        ],
    }


def update_incrementally(
    previous: dict,
    new_samples: list[dict],
    total_sample_count: int,
    total_strokes: int,
) -> dict:
    if not new_samples:
        return previous

    new_vectors = build_sample_profile_vectors(new_samples)
    feature_statistics = previous["feature_statistics"]
    profiles = feature_statistics["profiles"]

    for profile_name in PROFILE_NAMES:
        profiles[profile_name] = merge_profile_statistics(
            profiles[profile_name],
            new_vectors[profile_name],
        )

    # Non-profile statistics are also merged incrementally.
    # stroke_count is one observation per sample; point_count_per_stroke is
    # one observation per stroke. Neither requires re-reading old samples.
    new_stroke_counts = [len(sample["strokes"]) for sample in new_samples]
    new_point_counts = []
    for sample in new_samples:
        for stroke in sample["strokes"]:
            if not isinstance(stroke, dict):
                continue
            trajectory = stroke.get("normalized_trajectory", [])
            if isinstance(trajectory, list):
                new_point_counts.append(len(trajectory))

    feature_statistics["stroke_count"] = merge_scalar_statistics(
        feature_statistics["stroke_count"],
        new_stroke_counts,
    )
    feature_statistics["point_count_per_stroke"] = merge_scalar_statistics(
        feature_statistics["point_count_per_stroke"],
        new_point_counts,
    )

    previous["sample_count"] = total_sample_count
    previous["source"]["trajectory_files"] = total_sample_count
    previous["source"]["total_strokes"] = total_strokes
    previous["sample_ids"] = sorted(
        set(previous["sample_ids"])
        | {
            sample["sample_id"]
            for sample in new_samples
        }
    )

    previous["learning_history"].append(
        {
            "operation": "incremental_trajectory_update",
            "added_sample_count": len(new_samples),
            "sample_count": total_sample_count,
            "trajectory_files": total_sample_count,
            "total_strokes": total_strokes,
            "schema_version": SCHEMA_VERSION,
        }
    )

    return previous


def main() -> None:
    print("=" * 60)
    print("SIGNATURE MACHINE")
    print("MOTION LEARNING BUILDER v0.2")
    print("=" * 60)

    print()
    print("Source:")
    print(SAMPLES_DIR)

    print()
    print("Target:")
    print(OUTPUT_FILE)

    samples, total_strokes = collect_trajectories()

    print()
    print(f"Trajectory files: {len(samples)}")
    print(f"Total strokes:    {total_strokes}")

    if not samples:
        raise RuntimeError(
            "No trajectory.json files were found."
        )

    previous = load_previous_state()

    if previous is None:
        profile_vectors = build_sample_profile_vectors(samples)

        state = make_initial_state(
            samples,
            total_strokes,
            profile_vectors,
            "initial_equal_sample_weighted_build",
        )

        print()
        print("Mode:              initial rebuild")
    else:
        known_ids = set(previous["sample_ids"])

        new_samples = [
            sample
            for sample in samples
            if sample["sample_id"] not in known_ids
        ]

        state = update_incrementally(
            previous,
            new_samples,
            len(samples),
            total_strokes,
        )

        print()
        print("Mode:              incremental")
        print(f"New samples:       {len(new_samples)}")

    MOTION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = OUTPUT_FILE.with_suffix(
        ".json.tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")

    temporary_file.replace(OUTPUT_FILE)

    print()
    print(f"Samples learned: {state['sample_count']}")
    print(f"Output:          {OUTPUT_FILE}")

    print()
    print("PROFILE COUNTS:")

    for name in PROFILE_NAMES:
        profile = state[
            "feature_statistics"
        ][
            "profiles"
        ][
            name
        ]

        print(
            f"  {name:<20} "
            f"count={profile['count']:<4} "
            f"length={profile['length']}"
        )

    print()
    print("MOTION LEARNING COMPLETE")


if __name__ == "__main__":
    main()
