# -*- coding: utf-8 -*-

"""
Signature Machine
Motion Learning Builder v0.1

Purpose:
    Build motion_style_state.json from the existing immutable
    trajectory.json files.

Source:
    online_training_data/reference_learning/samples/<sample_id>/trajectory.json

Target:
    online_training_data/motion_learning/motion_style_state.json

Rules:
    - Existing reference samples are read-only.
    - No changes are made to strokes.json.
    - No changes are made to trajectory.json.
    - No dependency on library/.
    - Every reference sample has equal weight.
    - The builder is deterministic.
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

SCHEMA_VERSION = "motion_style_state_v0.1"


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


def aggregate_vector(values: list[list[float]]) -> dict:
    if not values:
        return {
            "count": 0,
            "length": 0,
            "mean": [],
            "std": [],
        }

    max_length = max(len(vector) for vector in values)

    if max_length == 0:
        return {
            "count": len(values),
            "length": 0,
            "mean": [],
            "std": [],
        }

    normalized = []

    for vector in values:
        if len(vector) == max_length:
            normalized.append(vector)
            continue

        if len(vector) == 1:
            normalized.append(
                [vector[0]] * max_length
            )
            continue

        result = []

        for index in range(max_length):
            position = (
                index
                * (len(vector) - 1)
                / (max_length - 1)
            )

            left = int(math.floor(position))
            right = min(
                left + 1,
                len(vector) - 1,
            )

            fraction = position - left

            value = (
                vector[left]
                * (1.0 - fraction)
                + vector[right]
                * fraction
            )

            result.append(value)

        normalized.append(result)

    columns = list(zip(*normalized))

    return {
        "count": len(values),
        "length": max_length,
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

    return samples, total_strokes


def build_state(
    samples: list[dict],
    total_strokes: int,
) -> dict:

    profile_values = {
        name: []
        for name in PROFILE_NAMES
    }

    stroke_counts = []
    point_counts = []

    for sample in samples:
        strokes = sample["strokes"]

        stroke_counts.append(len(strokes))

        for stroke in strokes:
            if not isinstance(stroke, dict):
                continue

            trajectory = stroke.get(
                "normalized_trajectory",
                [],
            )

            if isinstance(trajectory, list):
                point_counts.append(
                    len(trajectory)
                )

            for profile_name in PROFILE_NAMES:
                profile = stroke.get(
                    profile_name,
                    [],
                )

                if not isinstance(profile, list):
                    continue

                vector = [
                    safe_float(value)
                    for value in profile
                ]

                if vector:
                    profile_values[
                        profile_name
                    ].append(vector)

    profile_statistics = {
        name: aggregate_vector(values)
        for name, values in profile_values.items()
    }

    state = {
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
                "operation": "initial_trajectory_migration",
                "sample_count": len(samples),
                "trajectory_files": len(samples),
                "total_strokes": total_strokes,
                "schema_version": SCHEMA_VERSION,
            }
        ],
    }

    return state


def main() -> None:
    print("=" * 60)
    print("SIGNATURE MACHINE")
    print("MOTION LEARNING BUILDER")
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

    state = build_state(
        samples,
        total_strokes,
    )

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

    temporary_file.replace(
        OUTPUT_FILE
    )

    print()
    print(f"Samples learned: {state['sample_count']}")
    print(f"Output:          {OUTPUT_FILE}")

    print()
    print("PROFILE COUNTS:")

    for name in PROFILE_NAMES:
        count = state[
            "feature_statistics"
        ][
            "profiles"
        ][
            name
        ][
            "count"
        ]

        print(
            f"  {name:<20} {count}"
        )

    print()
    print("MOTION LEARNING COMPLETE")


if __name__ == "__main__":
    main()