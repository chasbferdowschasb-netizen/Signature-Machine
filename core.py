# -*- coding: utf-8 -*-

"""
Signature Machine
Core v0.4

Generation Engine: v0.4 trajectory-based synthesis
Trajectory Knowledge Layer: v0.1

Architecture:
- library/ remains available for the legacy Dataset Audit.
- online_training_data/reference_learning/samples/ is the ONLY source
  used by the normal learning path.
- Reference Knowledge is incremental and all samples have equal weight.
- Existing reference samples are never modified.
- If the Knowledge schema changes, the existing reference samples are
  rebuilt once using the new schema.
- Future runs add only genuinely new samples.

Important:
- Touch points are valid signature content and are NOT treated as noise.
- Strokes are always processed independently.
- No synthetic path is created between separate strokes.
"""

from __future__ import annotations
import random
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent

# ============================================================
# PATHS
# ============================================================

# Legacy dataset audit
LIBRARY_DIR = PROJECT_ROOT / "library"
REPORT_FILE = PROJECT_ROOT / "dataset_report.json"

# Online reference learning
REFERENCE_LEARNING_DIR = (
    PROJECT_ROOT
    / "online_training_data"
    / "reference_learning"
)

REFERENCE_SAMPLES_DIR = (
    REFERENCE_LEARNING_DIR
    / "samples"
)

REFERENCE_KNOWLEDGE_FILE = (
    REFERENCE_LEARNING_DIR
    / "reference_knowledge.json"
)

# ============================================================
# VERSION / CONFIG
# ============================================================

REFERENCE_KNOWLEDGE_VERSION = "0.4"
KNOWLEDGE_STORAGE_VERSION = "1.0"
TRAJECTORY_SCHEMA_VERSION = "0.1"

RESAMPLE_POINTS = 32
GENERATION_VERSION = "0.4"

GENERATION_DEFAULT_CANDIDATES = 3

GENERATION_RANDOM_SEED = 20260824

GENERATION_MARGIN = 80

GENERATION_CANVAS_WIDTH = 1600
GENERATION_CANVAS_HEIGHT = 700

GENERATION_STROKE_WIDTH = 3

GENERATION_VARIATION_SCALE = 0.035
GENERATION_VARIATION_TRANSLATION = 0.025
GENERATION_VARIATION_ROTATION_DEGREES = 2.5
GENERATION_VARIATION_PRESSURE = 0.04

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}



class SignatureCore:
    """
    Central project Core.

    The legacy Dataset Audit and Online Reference Learning remain
    separate responsibilities inside the same Core.

    Normal execution:
        python core.py

    NEVER scans library/ for learning.
    """

    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
    ) -> None:

        self.project_root = Path(
            project_root
        )

        # Legacy dataset
        self.library_dir = (
            self.project_root / "library"
        )

        self.report_file = (
            self.project_root
            / "dataset_report.json"
        )

        # Online learning
        self.reference_learning_dir = (
            self.project_root
            / "online_training_data"
            / "reference_learning"
        )

        self.reference_samples_dir = (
            self.reference_learning_dir
            / "samples"
        )

        # Distributed Knowledge Store.
        # Each reference sample owns its immutable sample_knowledge.json.
        # The central files are lightweight index/aggregate artifacts only.
        self.reference_knowledge_dir = (
            self.reference_learning_dir
            / "knowledge"
        )

        self.reference_knowledge_index_file = (
            self.reference_knowledge_dir
            / "index.json"
        )

        self.reference_knowledge_aggregate_file = (
            self.reference_knowledge_dir
            / "aggregate.json"
        )

        # Legacy monolithic Knowledge file.
        # Read-only migration source; never used as the new source of truth.
        self.reference_knowledge_file = (
            self.reference_learning_dir
            / "reference_knowledge.json"
        )

    # ========================================================
    # GENERAL UTILITIES
    # ========================================================

    @staticmethod
    def calculate_hash(
        path: Path,
    ) -> str:

        sha256 = hashlib.sha256()

        with path.open(
            "rb"
        ) as file:

            for chunk in iter(
                lambda: file.read(
                    1024 * 1024
                ),
                b"",
            ):
                sha256.update(chunk)

        return sha256.hexdigest()

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _angle_delta(
        a: float,
        b: float,
    ) -> float:

        return abs(
            (
                b - a + math.pi
            )
            % (
                2 * math.pi
            )
            - math.pi
        )

    @staticmethod
    def _stats_update(
        state: dict[str, Any],
        value: float,
    ) -> None:

        count = int(
            state.get(
                "count",
                0,
            )
        ) + 1

        mean = float(
            state.get(
                "mean",
                0.0,
            )
        )

        m2 = float(
            state.get(
                "m2",
                0.0,
            )
        )

        delta = value - mean

        mean += (
            delta / count
        )

        delta2 = value - mean

        m2 += (
            delta * delta2
        )

        if count == 1:

            minimum = value
            maximum = value

        else:

            minimum = min(
                value,
                float(
                    state.get(
                        "min",
                        value,
                    )
                ),
            )

            maximum = max(
                value,
                float(
                    state.get(
                        "max",
                        value,
                    )
                ),
            )

        state.update(
            {
                "count": count,
                "mean": mean,
                "m2": m2,
                "min": minimum,
                "max": maximum,
            }
        )

    @staticmethod
    def _stats_finalize(
        state: dict[str, Any],
    ) -> dict[str, Any]:

        count = int(
            state.get(
                "count",
                0,
            )
        )

        variance = (
            float(
                state.get(
                    "m2",
                    0.0,
                )
            )
            / (
                count - 1
            )
            if count > 1
            else 0.0
        )

        return {
            "count": count,
            "mean": float(
                state.get(
                    "mean",
                    0.0,
                )
            ),
            "variance": variance,
            "min": state.get(
                "min"
            ),
            "max": state.get(
                "max"
            ),
        }

    @staticmethod
    def _resample_profile(
        values: list[float],
        count: int = RESAMPLE_POINTS,
    ) -> list[float]:

        """
        Resample a one-dimensional profile to a fixed length.

        This is used only for scalar stroke profiles such as:
        velocity, pressure, direction and curvature.

        The original profile is never modified.
        Separate strokes remain separate.
        """

        cleaned = []

        for value in values:

            try:
                cleaned.append(
                    float(value)
                )

            except (
                TypeError,
                ValueError,
            ):

                continue

        if not cleaned:
            return [
                0.0
                for _ in range(count)
            ]

        if count <= 1:
            return [
                cleaned[0]
            ]

        if len(cleaned) == 1:
            return [
                cleaned[0]
                for _ in range(count)
            ]

        if len(cleaned) == count:
            return cleaned

        result = []

        source_last = (
            len(cleaned) - 1
        )

        target_last = (
            count - 1
        )

        for i in range(count):

            position = (
                i
                * source_last
                / target_last
            )

            left_index = int(
                math.floor(position)
            )

            right_index = min(
                left_index + 1,
                source_last,
            )

            alpha = (
                position
                - left_index
            )

            left_value = (
                cleaned[
                    left_index
                ]
            )

            right_value = (
                cleaned[
                    right_index
                ]
            )

            result.append(
                left_value
                + (
                    right_value
                    - left_value
                )
                * alpha
            )

        return result

    @staticmethod
    def _welford_update(
        state: dict[str, Any],
        values: list[float],
    ) -> None:

        count = int(
            state.get(
                "count",
                0,
            )
        ) + 1

        mean = state.get(
            "mean",
            [0.0] * len(values),
        )

        m2 = state.get(
            "m2",
            [0.0] * len(values),
        )

        if len(mean) != len(values):

             raise ValueError(
             "Profile vector length mismatch: "
             f"existing={len(mean)}, "
             f"incoming={len(values)}"
        )


        for i, value in enumerate(
            values
        ):

            delta = (
                value
                - mean[i]
            )

            mean[i] += (
                delta / count
            )

            delta2 = (
                value
                - mean[i]
            )

            m2[i] += (
                delta * delta2
            )

        state["count"] = count
        state["mean"] = mean
        state["m2"] = m2

    # ========================================================
    # LEGACY DATASET AUDIT
    # ========================================================

    def validate_project(
        self,
    ) -> None:

        if not self.library_dir.exists():

            raise FileNotFoundError(
                f"Library not found: "
                f"{self.library_dir}"
            )

        if not self.library_dir.is_dir():

            raise NotADirectoryError(
                f"Library is not a directory: "
                f"{self.library_dir}"
            )

    def discover_images(
        self,
    ) -> list[Path]:

        files: list[Path] = []

        for path in self.library_dir.rglob(
            "*"
        ):

            if (
                path.is_file()
                and path.suffix.lower()
                in SUPPORTED_EXTENSIONS
            ):

                files.append(path)

        return sorted(
            files
        )

    @staticmethod
    def analyze_image(
        path: Path,
    ) -> dict[str, Any]:

        result = {
            "filename": path.name,
            "relative_path": str(
                path
            ),
            "extension": path.suffix.lower(),
            "valid": False,
            "width": None,
            "height": None,
            "mode": None,
            "has_alpha": False,
            "error": None,
        }

        try:

            with Image.open(
                path
            ) as image:

                result["valid"] = True

                result["width"] = (
                    image.width
                )

                result["height"] = (
                    image.height
                )

                result["mode"] = (
                    image.mode
                )

                result["has_alpha"] = (
                    "A"
                    in image.getbands()
                )

        except Exception as exc:

            result["error"] = str(
                exc
            )

        return result

    def audit_dataset(
        self,
    ) -> dict[str, Any]:

        self.validate_project()

        images = (
            self.discover_images()
        )

        print("=" * 60)
        print(
            "SIGNATURE MACHINE"
        )
        print(
            "CORE v0.3 — DATASET AUDIT"
        )
        print("=" * 60)

        print(
            f"Project: "
            f"{self.project_root}"
        )

        print(
            f"Library: "
            f"{self.library_dir}"
        )

        print(
            f"Image files found: "
            f"{len(images)}"
        )

        extensions = Counter()
        modes = Counter()

        valid_count = 0
        invalid_count = 0
        alpha_count = 0

        width_values = []
        height_values = []

        file_records = []

        for index, path in enumerate(
            images,
            start=1,
        ):

            result = (
                self.analyze_image(
                    path
                )
            )

            file_records.append(
                result
            )

            extensions[
                result["extension"]
            ] += 1

            if result["valid"]:

                valid_count += 1

                modes[
                    result["mode"]
                ] += 1

                width_values.append(
                    result["width"]
                )

                height_values.append(
                    result["height"]
                )

                if result[
                    "has_alpha"
                ]:

                    alpha_count += 1

            else:

                invalid_count += 1

            if (
                index == 1
                or index % 250 == 0
                or index == len(images)
            ):

                print(
                    f"Analyzed: "
                    f"{index}/{len(images)}"
                )

        dimensions = {
            "min_width": (
                min(width_values)
                if width_values
                else None
            ),
            "max_width": (
                max(width_values)
                if width_values
                else None
            ),
            "min_height": (
                min(height_values)
                if height_values
                else None
            ),
            "max_height": (
                max(height_values)
                if height_values
                else None
            ),
        }

        hash_map = {}

        for index, path in enumerate(
            images,
            start=1,
        ):

            try:

                file_hash = (
                    self.calculate_hash(
                        path
                    )
                )

                hash_map.setdefault(
                    file_hash,
                    [],
                ).append(
                    str(
                        path.relative_to(
                            self.project_root
                        )
                    )
                )

            except Exception:
                continue

            if (
                index % 500 == 0
                or index == len(images)
            ):

                print(
                    f"Hashed: "
                    f"{index}/{len(images)}"
                )

        duplicate_groups = [
            paths
            for paths in hash_map.values()
            if len(paths) > 1
        ]

        duplicate_file_count = sum(
            len(group)
            for group in duplicate_groups
        )

        report = {
            "report_version": "0.3",
            "project": {
                "root": str(
                    self.project_root
                ),
                "library": str(
                    self.library_dir
                ),
            },
            "dataset": {
                "total_files": len(
                    images
                ),
                "valid_images": valid_count,
                "invalid_images": invalid_count,
            },
            "formats": dict(
                extensions
            ),
            "image_modes": dict(
                modes
            ),
            "transparency": {
                "images_with_alpha": (
                    alpha_count
                ),
                "images_without_alpha": (
                    valid_count
                    - alpha_count
                ),
            },
            "dimensions": dimensions,
            "duplicates": {
                "duplicate_groups": (
                    len(
                        duplicate_groups
                    )
                ),
                "duplicate_files": (
                    duplicate_file_count
                ),
            },
            "files": file_records,
        }

        with self.report_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print(
            "DATASET AUDIT COMPLETE"
        )

        return report

    # ========================================================
    # STROKE RESAMPLING
    # ========================================================

    @staticmethod
    def _distance(
        a: dict[str, float],
        b: dict[str, float],
    ) -> float:

        return math.hypot(
            a["x"] - b["x"],
            a["y"] - b["y"],
        )

    @classmethod
    def _resample_stroke(
        cls,
        points: list[
            dict[str, Any]
        ],
        count: int = RESAMPLE_POINTS,
    ) -> list[
        dict[str, float]
    ]:

        """
        Arc-length resampling of ONE stroke.

        IMPORTANT:
        Separate strokes are never connected.
        """

        cleaned = []

        for point in points:

            try:

                cleaned.append(
                    {
                        "x": float(
                            point["x"]
                        ),
                        "y": float(
                            point["y"]
                        ),
                        "pressure": float(
                            point.get(
                                "pressure",
                                0.0,
                            )
                        ),
                    }
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                continue

        if not cleaned:
            return []

        if len(cleaned) == 1:

            p = cleaned[0]

            return [
                {
                    **p,
                    "u": (
                        i
                        / max(
                            count - 1,
                            1,
                        )
                    ),
                }
                for i in range(
                    count
                )
            ]

        cumulative = [
            0.0
        ]

        for left, right in zip(
            cleaned,
            cleaned[1:],
        ):

            cumulative.append(
                cumulative[-1]
                + cls._distance(
                    left,
                    right,
                )
            )

        total = cumulative[-1]

        if total <= 1e-12:

            p = cleaned[0]

            return [
                {
                    **p,
                    "u": (
                        i
                        / max(
                            count - 1,
                            1,
                        )
                    ),
                }
                for i in range(
                    count
                )
            ]

        result = []

        for i in range(
            count
        ):

            target = (
                total
                * i
                / (
                    count - 1
                )
            )

            j = 1

            while (
                j < len(cumulative)
                and cumulative[j]
                < target
            ):

                j += 1

            j = min(
                j,
                len(cumulative) - 1,
            )

            left = cleaned[
                j - 1
            ]

            right = cleaned[
                j
            ]

            span = (
                cumulative[j]
                - cumulative[j - 1]
            )

            if span <= 1e-12:

                alpha = 0.0

            else:

                alpha = (
                    target
                    - cumulative[
                        j - 1
                    ]
                ) / span

            result.append(
                {
                    "x": (
                        left["x"]
                        + (
                            right["x"]
                            - left["x"]
                        )
                        * alpha
                    ),
                    "y": (
                        left["y"]
                        + (
                            right["y"]
                            - left["y"]
                        )
                        * alpha
                    ),
                    "pressure": (
                        left[
                            "pressure"
                        ]
                        + (
                            right[
                                "pressure"
                            ]
                            - left[
                                "pressure"
                            ]
                        )
                        * alpha
                    ),
                    "u": (
                        i
                        / (
                            count - 1
                        )
                    ),
                }
            )

        return result

    # ========================================================
    # MOTION FEATURES
    # ========================================================

    @classmethod
    def _stroke_motion_features(
        cls,
        stroke: list[
            dict[str, Any]
        ],
    ) -> dict[str, Any]:

        """
        Extract motion features from ONE stroke.

        Touch points remain valid points.
        """

        points = []

        for p in stroke:

            try:

                points.append(
                    {
                        "x": float(
                            p["x"]
                        ),
                        "y": float(
                            p["y"]
                        ),
                        "time_ms": float(
                            p.get(
                                "time_ms",
                                0.0,
                            )
                        ),
                        "pressure": float(
                            p.get(
                                "pressure",
                                0.0,
                            )
                        ),
                        "pointer_type": str(
                            p.get(
                                "pointer_type",
                                "unknown",
                            )
                        ),
                        "tilt_x": float(
                            p.get(
                                "tilt_x",
                                0.0,
                            )
                        ),
                        "tilt_y": float(
                            p.get(
                                "tilt_y",
                                0.0,
                            )
                        ),
                        "twist": float(
                            p.get(
                                "twist",
                                0.0,
                            )
                        ),
                    }
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                continue

        if not points:

            return {
                "point_count": 0,
                "duration_ms": 0.0,
                "path_length": 0.0,
                "mean_speed": 0.0,
                "speed_profile": [],
                "pressure_profile": [],
                "direction_profile": [],
                "curvature_profile": [],
                "tilt_x_profile": [],
                "tilt_y_profile": [],
                "twist_profile": [],
            }

        duration_ms = 0.0

        if len(points) >= 2:

            duration_ms = max(
                0.0,
                (
                    points[-1]["time_ms"]
                    - points[0]["time_ms"]
                ),
            )

        path_length = 0.0

        speeds = []
        headings = []

        for a, b in zip(
            points,
            points[1:],
        ):

            dx = (
                b["x"]
                - a["x"]
            )

            dy = (
                b["y"]
                - a["y"]
            )

            distance = math.hypot(
                dx,
                dy,
            )

            path_length += distance

            dt = (
                b["time_ms"]
                - a["time_ms"]
            ) / 1000.0

            if dt > 1e-6:

                speeds.append(
                    distance / dt
                )

            if distance > 1e-9:

                headings.append(
                    math.atan2(
                        dy,
                        dx,
                    )
                )

        direction_profile = []

        for a, b in zip(
            headings,
            headings[1:],
        ):

            direction_profile.append(
                cls._angle_delta(
                    a,
                    b,
                )
            )

        curvature_profile = []

        for i in range(
            min(
                len(
                    direction_profile
                ),
                len(points) - 2,
            )
        ):

            a = points[i]
            b = points[i + 1]

            segment = math.hypot(
                b["x"] - a["x"],
                b["y"] - a["y"],
            )

            if segment > 1e-9:

                curvature_profile.append(
                    direction_profile[i]
                    / segment
                )

            else:

                curvature_profile.append(
                    0.0
                )

        return {
            "point_count": len(
                points
            ),
            "duration_ms": duration_ms,
            "path_length": path_length,
            "mean_speed": (
                sum(speeds)
                / len(speeds)
                if speeds
                else 0.0
            ),
            "speed_profile": speeds,
            "pressure_profile": [
                p["pressure"]
                for p in points
            ],
            "direction_profile": (
                direction_profile
            ),
            "curvature_profile": (
                curvature_profile
            ),
            "tilt_x_profile": [
                p["tilt_x"]
                for p in points
            ],
            "tilt_y_profile": [
                p["tilt_y"]
                for p in points
            ],
            "twist_profile": [
                p["twist"]
                for p in points
            ],
        }

    # ========================================================
    # FEATURE EXTRACTION
    # ========================================================

    @classmethod
    def _extract_reference_features(
        cls,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        strokes = payload.get(
            "strokes",
            [],
        )

        valid_strokes = []

        for stroke in strokes:

            points = stroke.get(
                "points",
                [],
            )

            if points:

                valid_strokes.append(
                    points
                )

        all_points = [
            point
            for stroke in valid_strokes
            for point in stroke
        ]

        if not all_points:

            raise ValueError(
                "strokes.json contains "
                "no valid points."
            )

        xs = [
            cls._safe_float(
                p.get("x")
            )
            for p in all_points
        ]

        ys = [
            cls._safe_float(
                p.get("y")
            )
            for p in all_points
        ]

        min_x = min(xs)
        max_x = max(xs)

        min_y = min(ys)
        max_y = max(ys)

        scale = max(
            max_x - min_x,
            max_y - min_y,
            1e-9,
        )

        normalized_strokes = []
        stroke_features = []

        total_path_length = 0.0
        active_time_ms = 0.0

        touch_point_count = 0

        pressure_values = []

        stroke_start_times = []
        stroke_end_times = []

        all_speeds = []
        all_direction_changes = []

        # ----------------------------------------------------
        # Each stroke independently
        # ----------------------------------------------------

        for stroke_index, stroke in enumerate(
            valid_strokes
        ):

            resampled = (
                cls._resample_stroke(
                    stroke
                )
            )

            normalized = []

            for p in resampled:

                normalized.append(
                    {
                        "x": (
                            p["x"]
                            - min_x
                        ) / scale,
                        "y": (
                            p["y"]
                            - min_y
                        ) / scale,
                        "pressure": (
                            p["pressure"]
                        ),
                        "u": p["u"],
                    }
                )

            normalized_strokes.append(
                normalized
            )

            motion = (
                cls._stroke_motion_features(
                    stroke
                )
            )

            stroke_features.append(
                {
                    "stroke_index": (
                        stroke_index
                    ),
                    "point_count": (
                        motion[
                            "point_count"
                        ]
                    ),
                    "duration_ms": (
                        motion[
                            "duration_ms"
                        ]
                    ),
                    "path_length": (
                        motion[
                            "path_length"
                        ]
                    ),
                    "mean_speed": (
                        motion[
                            "mean_speed"
                        ]
                    ),
                    "speed_profile": (
                        motion[
                            "speed_profile"
                        ]
                    ),
                    "pressure_profile": (
                        motion[
                            "pressure_profile"
                        ]
                    ),
                    "direction_profile": (
                        motion[
                            "direction_profile"
                        ]
                    ),
                    "curvature_profile": (
                        motion[
                            "curvature_profile"
                        ]
                    ),
                    "tilt_x_profile": (
                        motion[
                            "tilt_x_profile"
                        ]
                    ),
                    "tilt_y_profile": (
                        motion[
                            "tilt_y_profile"
                        ]
                    ),
                    "twist_profile": (
                        motion[
                            "twist_profile"
                        ]
                    ),
                    "normalized_trajectory": (
                        normalized
                    ),
                }
            )

            total_path_length += (
                motion[
                    "path_length"
                ]
            )

            active_time_ms += (
                motion[
                    "duration_ms"
                ]
            )

            all_speeds.extend(
                motion[
                    "speed_profile"
                ]
            )

            all_direction_changes.extend(
                motion[
                    "direction_profile"
                ]
            )

            for point in stroke:

                if (
                    point.get(
                        "pointer_type"
                    )
                    == "touch"
                ):

                    # VALID SIGNATURE CONTENT
                    touch_point_count += 1

                try:

                    pressure_values.append(
                        float(
                            point.get(
                                "pressure",
                                0.0,
                            )
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    pass

            raw_times = []

            for point in stroke:

                try:

                    raw_times.append(
                        float(
                            point.get(
                                "time_ms",
                                0.0,
                            )
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    continue

            if raw_times:

                stroke_start_times.append(
                    raw_times[0]
                )

                stroke_end_times.append(
                    raw_times[-1]
                )

        # ----------------------------------------------------
        # Inter-stroke timing
        # ----------------------------------------------------

        inter_stroke_gaps_ms = []

        for i in range(
            len(
                stroke_end_times
            ) - 1
        ):

            gap = (
                stroke_start_times[
                    i + 1
                ]
                - stroke_end_times[i]
            )

            inter_stroke_gaps_ms.append(
                max(
                    0.0,
                    gap,
                )
            )

        # ----------------------------------------------------
        # Pressure summary
        # ----------------------------------------------------

        if pressure_values:

            pressure_mean = (
                sum(
                    pressure_values
                )
                / len(
                    pressure_values
                )
            )

        else:

            pressure_mean = 0.0

        if len(
            pressure_values
        ) > 1:

            pressure_variance = (
                sum(
                    (
                        p
                        - pressure_mean
                    ) ** 2
                    for p in pressure_values
                )
                / (
                    len(
                        pressure_values
                    )
                    - 1
                )
            )

        else:

            pressure_variance = 0.0

        return {
            "sample_id": str(
                payload.get(
                    "sample_id"
                )
                or ""
            ),
            "stroke_count": len(
                valid_strokes
            ),
            "point_count": len(
                all_points
            ),
            "touch_point_count": (
                touch_point_count
            ),
            "normalized_bbox": {
                "width": (
                    max_x
                    - min_x
                ) / scale,
                "height": (
                    max_y
                    - min_y
                ) / scale,
                "scale": scale,
            },
            "path_length": (
                total_path_length
            ),
            "active_time_ms": (
                active_time_ms
            ),
            "mean_speed": (
                sum(
                    all_speeds
                )
                / len(
                    all_speeds
                )
                if all_speeds
                else 0.0
            ),
            "mean_direction_change": (
                sum(
                    all_direction_changes
                )
                / len(
                    all_direction_changes
                )
                if all_direction_changes
                else 0.0
            ),
            "pressure_mean": (
                pressure_mean
            ),
            "pressure_variance": (
                pressure_variance
            ),
            "normalized_strokes": (
                normalized_strokes
            ),
            "stroke_features": (
                stroke_features
            ),
            "inter_stroke_gaps_ms": (
                inter_stroke_gaps_ms
            ),
        }

    # ========================================================
    # DISTRIBUTED KNOWLEDGE SCHEMA
    # ========================================================

    @classmethod
    def _new_knowledge(
        cls,
    ) -> dict[str, Any]:

        return {
            "schema_version": REFERENCE_KNOWLEDGE_VERSION,
            "storage_version": KNOWLEDGE_STORAGE_VERSION,
            "sample_count": 0,
            "sample_ids": [],
            # Runtime index only. Full sample knowledge lives beside each sample.
            "samples": {},
            "feature_schema": {
                "normalization": "translation_and_global_scale",
                "stroke_resampling_points": RESAMPLE_POINTS,
                "cross_stroke_bridging": False,
                "touch_points_are_valid": True,
                "sample_weighting": "equal_per_sample",
                "full_sample_trajectory": True,
                "velocity_profile": True,
                "pressure_profile": True,
                "direction_profile": True,
                "curvature_profile": True,
                "inter_stroke_timing": True,
                "tilt_and_twist_profile": True,
            },
            "learning_policy": {
                "duplicate_sample_id": "ignored",
                "duplicate_strokes_hash": "ignored",
                "status_weighting": "disabled",
                "pointer_type_filtering": "disabled",
                "library_scanning_for_learning": False,
                "source_of_truth": "per_sample_knowledge",
                "incremental_updates": True,
                "generated_signatures_are_reference": False,
            },
            "aggregate": {
                "scalar_statistics": {},
                "inter_stroke_gap_statistics": {},
                "stroke_duration_statistics": {},
                "stroke_path_length_statistics": {},
                "stroke_speed_statistics": {},
                "stroke_profiles": {},
                "stroke_velocity_profiles": {},
                "stroke_pressure_profiles": {},
                "stroke_direction_profiles": {},
                "stroke_curvature_profiles": {},
            },
        }

    @staticmethod
    def _write_json_atomic(
        path: Path,
        payload: dict[str, Any],
    ) -> None:

        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")

        with temp.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        temp.replace(path)

    @staticmethod
    def _required_feature_schema() -> set[str]:
        return {
            "normalization",
            "stroke_resampling_points",
            "cross_stroke_bridging",
            "touch_points_are_valid",
            "sample_weighting",
            "full_sample_trajectory",
            "velocity_profile",
            "pressure_profile",
            "direction_profile",
            "curvature_profile",
            "inter_stroke_timing",
            "tilt_and_twist_profile",
        }

    @staticmethod
    def _required_learning_policy() -> set[str]:
        return {
            "duplicate_sample_id",
            "duplicate_strokes_hash",
            "status_weighting",
            "pointer_type_filtering",
            "library_scanning_for_learning",
            "source_of_truth",
            "incremental_updates",
            "generated_signatures_are_reference",
        }

    @staticmethod
    def _required_aggregate() -> set[str]:
        return {
            "scalar_statistics",
            "inter_stroke_gap_statistics",
            "stroke_duration_statistics",
            "stroke_path_length_statistics",
            "stroke_speed_statistics",
            "stroke_profiles",
            "stroke_velocity_profiles",
            "stroke_pressure_profiles",
            "stroke_direction_profiles",
            "stroke_curvature_profiles",
        }

    @classmethod
    def _knowledge_structure_valid(
        cls,
        knowledge: Any,
    ) -> bool:

        if not isinstance(knowledge, dict):
            return False

        if knowledge.get("schema_version") != REFERENCE_KNOWLEDGE_VERSION:
            return False

        if knowledge.get("storage_version") != KNOWLEDGE_STORAGE_VERSION:
            return False

        feature_schema = knowledge.get("feature_schema")
        learning_policy = knowledge.get("learning_policy")
        aggregate = knowledge.get("aggregate")

        if not isinstance(feature_schema, dict):
            return False
        if not cls._required_feature_schema().issubset(feature_schema.keys()):
            return False
        if not isinstance(learning_policy, dict):
            return False
        if not cls._required_learning_policy().issubset(learning_policy.keys()):
            return False
        if not isinstance(aggregate, dict):
            return False
        if not cls._required_aggregate().issubset(aggregate.keys()):
            return False

        if not isinstance(knowledge.get("samples"), dict):
            return False
        if not isinstance(knowledge.get("sample_ids"), list):
            return False
        if knowledge.get("sample_count") != len(knowledge.get("sample_ids", [])):
            return False

        return True

    def _sample_trajectory_file(
        self,
        sample_dir: Path,
    ) -> Path:
        """Return the per-sample motion/trajectory knowledge file."""
        return Path(sample_dir) / "trajectory.json"

    def _sample_knowledge_file(
        self,
        sample_dir: Path,
    ) -> Path:
        return Path(sample_dir) / "sample_knowledge.json"

    def _sample_knowledge_document(
        self,
        sample_dir: Path,
        features: dict[str, Any],
        strokes_hash: str,
    ) -> dict[str, Any]:

        return {
            "knowledge_version": REFERENCE_KNOWLEDGE_VERSION,
            "storage_version": KNOWLEDGE_STORAGE_VERSION,
            "sample_id": str(features["sample_id"]),
            "source": {
                "sample_dir": str(sample_dir),
                "strokes_file": str(Path(sample_dir) / "strokes.json"),
                "strokes_sha256": strokes_hash,
            },
            "features": {
                "stroke_count": features["stroke_count"],
                "point_count": features["point_count"],
                "touch_point_count": features["touch_point_count"],
                "normalized_bbox": features["normalized_bbox"],
                "path_length": features["path_length"],
                "active_time_ms": features["active_time_ms"],
                "mean_speed": features["mean_speed"],
                "mean_direction_change": features["mean_direction_change"],
                "pressure_mean": features["pressure_mean"],
                "pressure_variance": features["pressure_variance"],
                "normalized_strokes": features["normalized_strokes"],
                "stroke_features": features["stroke_features"],
                "inter_stroke_gaps_ms": features["inter_stroke_gaps_ms"],
            },
        }

    @classmethod
    def _build_sample_trajectory(
        cls,
        payload: dict[str, Any],
        features: dict[str, Any],
        strokes_hash: str,
    ) -> dict[str, Any]:
        """
        Build durable motion knowledge for one real reference sample.

        Raw strokes remain the source of truth. This derived document keeps
        the execution sequence needed by Generation without copying the
        complete raw strokes into the central aggregate.
        """
        stroke_features = list(features.get("stroke_features", []))
        normalized_strokes = list(features.get("normalized_strokes", []))
        gaps = list(features.get("inter_stroke_gaps_ms", []))

        raw_strokes = payload.get("strokes", [])
        if not isinstance(raw_strokes, list):
            raise ValueError("Invalid strokes structure.")

        strokes = []
        valid_index = 0

        for raw_stroke in raw_strokes:
            if not isinstance(raw_stroke, dict):
                continue
            points = raw_stroke.get("points", [])
            if not isinstance(points, list) or not points:
                continue

            clean = []
            for point in points:
                if not isinstance(point, dict):
                    continue
                try:
                    x = float(point.get("x", 0.0))
                    y = float(point.get("y", 0.0))
                    t = float(point.get("time_ms", 0.0))
                    pressure = float(point.get("pressure", 0.0))
                except (TypeError, ValueError):
                    continue
                if not all(math.isfinite(v) for v in (x, y, t, pressure)):
                    continue
                clean.append((x, y, t, max(0.0, min(1.0, pressure))))

            if not clean:
                continue

            feature = (
                stroke_features[valid_index]
                if valid_index < len(stroke_features)
                else {}
            )
            normalized = (
                normalized_strokes[valid_index]
                if valid_index < len(normalized_strokes)
                else []
            )

            start = clean[0]
            end = clean[-1]

            strokes.append({
                "stroke_index": valid_index,
                "point_count": len(clean),
                "start": {
                    "x": start[0],
                    "y": start[1],
                    "time_ms": start[2],
                    "pressure": start[3],
                },
                "end": {
                    "x": end[0],
                    "y": end[1],
                    "time_ms": end[2],
                    "pressure": end[3],
                },
                "duration_ms": float(feature.get("duration_ms", 0.0)),
                "path_length": float(feature.get("path_length", 0.0)),
                "mean_speed": float(feature.get("mean_speed", 0.0)),
                "normalized_trajectory": normalized,
                "speed_profile": list(feature.get("speed_profile", [])),
                "pressure_profile": list(feature.get("pressure_profile", [])),
                "direction_profile": list(feature.get("direction_profile", [])),
                "curvature_profile": list(feature.get("curvature_profile", [])),
                "tilt_x_profile": list(feature.get("tilt_x_profile", [])),
                "tilt_y_profile": list(feature.get("tilt_y_profile", [])),
                "twist_profile": list(feature.get("twist_profile", [])),
            })
            valid_index += 1

        if not strokes:
            raise ValueError("Cannot build trajectory from empty strokes.")

        transitions = []
        for i in range(len(strokes) - 1):
            transitions.append({
                "from_stroke": i,
                "to_stroke": i + 1,
                "type": "pen_lift",
                "gap_ms": float(gaps[i]) if i < len(gaps) else 0.0,
                "from_end": strokes[i]["end"],
                "to_start": strokes[i + 1]["start"],
            })

        return {
            "trajectory_schema_version": TRAJECTORY_SCHEMA_VERSION,
            "knowledge_version": REFERENCE_KNOWLEDGE_VERSION,
            "sample_id": str(
                features.get("sample_id")
                or payload.get("sample_id")
                or ""
            ),
            "source": {
                "source_of_truth": "strokes.json",
                "strokes_file": "strokes.json",
                "strokes_sha256": strokes_hash,
            },
            "execution": {
                "stroke_count": len(strokes),
                "stroke_order": [s["stroke_index"] for s in strokes],
                "inter_stroke_gaps_ms": gaps,
                "transitions": transitions,
            },
            "strokes": strokes,
        }

    def _write_sample_trajectory(
        self,
        sample_dir: Path,
        payload: dict[str, Any],
        features: dict[str, Any],
        strokes_hash: str,
    ) -> Path:
        trajectory = self._build_sample_trajectory(
            payload,
            features,
            strokes_hash,
        )
        path = self._sample_trajectory_file(sample_dir)
        self._write_json_atomic(path, trajectory)
        return path

    def _write_sample_knowledge(
        self,
        sample_dir: Path,
        features: dict[str, Any],
        strokes_hash: str,
    ) -> None:

        document = self._sample_knowledge_document(
            sample_dir,
            features,
            strokes_hash,
        )

        self._write_json_atomic(
            self._sample_knowledge_file(sample_dir),
            document,
        )

    def _load_reference_knowledge(
        self,
    ) -> dict[str, Any]:

        index_payload = None
        aggregate_payload = None

        if self.reference_knowledge_index_file.exists():
            try:
                with self.reference_knowledge_index_file.open("r", encoding="utf-8") as file:
                    index_payload = json.load(file)
            except Exception:
                index_payload = None

        if self.reference_knowledge_aggregate_file.exists():
            try:
                with self.reference_knowledge_aggregate_file.open("r", encoding="utf-8") as file:
                    aggregate_payload = json.load(file)
            except Exception:
                aggregate_payload = None

        if isinstance(index_payload, dict) and isinstance(aggregate_payload, dict):
            knowledge = self._new_knowledge()
            knowledge["schema_version"] = index_payload.get("schema_version")
            knowledge["storage_version"] = index_payload.get("storage_version")
            knowledge["sample_count"] = int(index_payload.get("sample_count", 0))
            knowledge["sample_ids"] = list(index_payload.get("sample_ids", []))
            knowledge["samples"] = dict(index_payload.get("samples", {}))
            knowledge["feature_schema"] = dict(index_payload.get("feature_schema", knowledge["feature_schema"]))
            knowledge["learning_policy"] = dict(index_payload.get("learning_policy", knowledge["learning_policy"]))
            knowledge["aggregate"] = aggregate_payload.get("aggregate", aggregate_payload)

            if self._knowledge_structure_valid(knowledge):
                return knowledge

        # One-time migration source. The old monolithic file is never written again.
        if self.reference_knowledge_file.exists():
            migrated = self._migrate_legacy_reference_knowledge()
            if migrated is not None:
                return migrated

        return self._new_knowledge()

    def _migrate_legacy_reference_knowledge(
        self,
    ) -> dict[str, Any] | None:

        try:
            with self.reference_knowledge_file.open("r", encoding="utf-8") as file:
                legacy = json.load(file)
        except Exception:
            return None

        if not isinstance(legacy, dict):
            return None

        legacy_samples = legacy.get("samples")
        legacy_ids = legacy.get("sample_ids")
        legacy_aggregate = legacy.get("aggregate")

        if not isinstance(legacy_samples, dict) or not isinstance(legacy_ids, list):
            return None
        if not isinstance(legacy_aggregate, dict):
            return None

        knowledge = self._new_knowledge()
        knowledge["aggregate"] = legacy_aggregate

        for sample_id in sorted(str(x) for x in legacy_ids):
            sample_dir = self.reference_samples_dir / sample_id
            legacy_sample = legacy_samples.get(sample_id)

            if not sample_dir.is_dir() or not isinstance(legacy_sample, dict):
                continue

            strokes_path = sample_dir / "strokes.json"
            if not strokes_path.is_file():
                continue

            strokes_hash = str(legacy_sample.get("strokes_sha256") or self.calculate_hash(strokes_path))

            document = {
                "knowledge_version": REFERENCE_KNOWLEDGE_VERSION,
                "storage_version": KNOWLEDGE_STORAGE_VERSION,
                "sample_id": sample_id,
                "source": {
                    "sample_dir": str(sample_dir),
                    "strokes_file": str(strokes_path),
                    "strokes_sha256": strokes_hash,
                    "migrated_from": "reference_knowledge.json",
                },
                "features": legacy_sample,
            }

            self._write_json_atomic(
                self._sample_knowledge_file(sample_dir),
                document,
            )

            try:
                with strokes_path.open("r", encoding="utf-8") as source_file:
                    payload = json.load(source_file)
                migrated_features = dict(legacy_sample)
                migrated_features["sample_id"] = sample_id
                self._write_sample_trajectory(
                    sample_dir,
                    payload,
                    migrated_features,
                    strokes_hash,
                )
            except Exception:
                # Migration of legacy knowledge must not destroy the valid
                # per-sample knowledge document. The normal learning pass
                # can restore trajectory.json later.
                pass

            knowledge["samples"][sample_id] = {
                "sample_id": sample_id,
                "strokes_sha256": strokes_hash,
                "knowledge_file": str(self._sample_knowledge_file(sample_dir)),
            }
            knowledge["sample_ids"].append(sample_id)

        knowledge["sample_ids"].sort()
        knowledge["sample_count"] = len(knowledge["sample_ids"])
        self._save_reference_knowledge(knowledge)

        return knowledge

    def _save_reference_knowledge(
        self,
        knowledge: dict[str, Any],
    ) -> None:

        self.reference_knowledge_dir.mkdir(parents=True, exist_ok=True)

        index_payload = {
            "schema_version": REFERENCE_KNOWLEDGE_VERSION,
            "storage_version": KNOWLEDGE_STORAGE_VERSION,
            "sample_count": int(knowledge.get("sample_count", 0)),
            "sample_ids": list(knowledge.get("sample_ids", [])),
            "samples": dict(knowledge.get("samples", {})),
            "feature_schema": dict(knowledge.get("feature_schema", {})),
            "learning_policy": dict(knowledge.get("learning_policy", {})),
        }

        aggregate_payload = {
            "schema_version": REFERENCE_KNOWLEDGE_VERSION,
            "storage_version": KNOWLEDGE_STORAGE_VERSION,
            "sample_count": int(knowledge.get("sample_count", 0)),
            "aggregate": knowledge.get("aggregate", {}),
        }

        self._write_json_atomic(
            self.reference_knowledge_index_file,
            index_payload,
        )
        self._write_json_atomic(
            self.reference_knowledge_aggregate_file,
            aggregate_payload,
        )

    # ========================================================
    # PROFILE AGGREGATION
    # ========================================================

    @staticmethod
    def _profile_vector(
        points: list[
            dict[str, Any]
        ],
        keys: tuple[str, ...],
    ) -> list[float]:

        vector = []

        for point in points:

            for key in keys:

                vector.append(
                    float(
                        point.get(
                            key,
                            0.0,
                        )
                    )
                )

        return vector

    def _update_profile_aggregate(
        self,
        profiles: dict[str, Any],
        index: int,
        vector: list[float],
    ) -> None:

        if not vector:
            return

        key = str(index)

        state = profiles.setdefault(
            key,
            {
                "count": 0,
                "mean": [],
                "m2": [],
            },
        )

        if not state[
            "mean"
        ]:

            state[
                "mean"
            ] = [
                0.0
                for _ in vector
            ]

            state[
                "m2"
            ] = [
                0.0
                for _ in vector
            ]

        self._welford_update(
            state,
            vector,
        )

    # ========================================================
    # ADD ONE SAMPLE TO KNOWLEDGE
    # ========================================================

    def _update_reference_knowledge(
        self,
        knowledge: dict[str, Any],
        features: dict[str, Any],
        strokes_hash: str,
    ) -> bool:

        sample_id = str(
            features[
                "sample_id"
            ]
        )

        # ----------------------------------------------------
        # Sample ID duplicate
        # ----------------------------------------------------

        if sample_id in (
            knowledge[
                "samples"
            ]
        ):

            return False

        # ----------------------------------------------------
        # Exact strokes.json duplicate
        # ----------------------------------------------------

        for sample in (
            knowledge[
                "samples"
            ].values()
        ):

            if (
                sample.get(
                    "strokes_sha256"
                )
                == strokes_hash
            ):

                return False

        # ----------------------------------------------------
        # Store only compact metadata in the central index.
        # Full sample knowledge is stored beside the sample.
        # ----------------------------------------------------

        sample_dir = self.reference_samples_dir / sample_id

        knowledge["samples"][sample_id] = {
            "sample_id": sample_id,
            "strokes_sha256": strokes_hash,
            "knowledge_file": str(
                self._sample_knowledge_file(sample_dir)
            ),
            "trajectory_file": str(
                self._sample_trajectory_file(sample_dir)
            ),
        }

        knowledge[
            "sample_ids"
        ].append(
            sample_id
        )

        knowledge[
            "sample_ids"
        ].sort()

        knowledge[
            "sample_count"
        ] = len(
            knowledge[
                "sample_ids"
            ]
        )

        aggregate = knowledge[
            "aggregate"
        ]

        # ----------------------------------------------------
        # Scalar statistics
        # ----------------------------------------------------

        scalar_values = {
            "stroke_count": (
                features[
                    "stroke_count"
                ]
            ),
            "point_count": (
                features[
                    "point_count"
                ]
            ),
            "touch_point_count": (
                features[
                    "touch_point_count"
                ]
            ),
            "path_length": (
                features[
                    "path_length"
                ]
            ),
            "active_time_ms": (
                features[
                    "active_time_ms"
                ]
            ),
            "mean_speed": (
                features[
                    "mean_speed"
                ]
            ),
            "mean_direction_change": (
                features[
                    "mean_direction_change"
                ]
            ),
            "pressure_mean": (
                features[
                    "pressure_mean"
                ]
            ),
            "pressure_variance": (
                features[
                    "pressure_variance"
                ]
            ),
        }

        scalar_statistics = (
            aggregate[
                "scalar_statistics"
            ]
        )

        for name, value in (
            scalar_values.items()
        ):

            state = (
                scalar_statistics.setdefault(
                    name,
                    {},
                )
            )

            self._stats_update(
                state,
                float(value),
            )

        # ----------------------------------------------------
        # Inter-stroke gaps
        # ----------------------------------------------------

        gap_statistics = (
            aggregate[
                "inter_stroke_gap_statistics"
            ]
        )

        for gap in (
            features[
                "inter_stroke_gaps_ms"
            ]
        ):

            self._stats_update(
                gap_statistics.setdefault(
                    "all",
                    {},
                ),
                float(gap),
            )

        # ----------------------------------------------------
        # Per-stroke statistics
        # ----------------------------------------------------

        duration_stats = (
            aggregate[
                "stroke_duration_statistics"
            ]
        )

        path_stats = (
            aggregate[
                "stroke_path_length_statistics"
            ]
        )

        speed_stats = (
            aggregate[
                "stroke_speed_statistics"
            ]
        )

        geometry_profiles = (
            aggregate[
                "stroke_profiles"
            ]
        )

        velocity_profiles = (
            aggregate[
                "stroke_velocity_profiles"
            ]
        )

        pressure_profiles = (
            aggregate[
                "stroke_pressure_profiles"
            ]
        )

        direction_profiles = (
            aggregate[
                "stroke_direction_profiles"
            ]
        )

        curvature_profiles = (
            aggregate[
                "stroke_curvature_profiles"
            ]
        )

        for stroke in (
            features[
                "stroke_features"
            ]
        ):

            index = int(
                stroke[
                    "stroke_index"
                ]
            )

            key = str(
                index
            )

            self._stats_update(
                duration_stats.setdefault(
                    key,
                    {},
                ),
                float(
                    stroke[
                        "duration_ms"
                    ]
                ),
            )

            self._stats_update(
                path_stats.setdefault(
                    key,
                    {},
                ),
                float(
                    stroke[
                        "path_length"
                    ]
                ),
            )

            self._stats_update(
                speed_stats.setdefault(
                    key,
                    {},
                ),
                float(
                    stroke[
                        "mean_speed"
                    ]
                ),
            )

            trajectory = (
                stroke[
                    "normalized_trajectory"
                ]
            )

            geometry_vector = (
                self._profile_vector(
                    trajectory,
                    (
                        "x",
                        "y",
                        "pressure",
                    ),
                )
            )

            self._update_profile_aggregate(
                geometry_profiles,
                index,
                geometry_vector,
            )

            self._update_profile_aggregate(
                velocity_profiles,
                index,
                self._resample_profile(
                    [
                        float(x)
                        for x in stroke[
                            "speed_profile"
                        ]
                    ]
                ),
            )

            self._update_profile_aggregate(
                pressure_profiles,
                index,
                self._resample_profile(
                    [
                        float(x)
                        for x in stroke[
                            "pressure_profile"
                        ]
                    ]
                ),
            )


            self._update_profile_aggregate(
                direction_profiles,
                index,
                self._resample_profile(
                    [
                        float(x)
                        for x in stroke[
                            "direction_profile"
                        ]
                    ]
                ),
            )


            self._update_profile_aggregate(
                curvature_profiles,
                index,
                self._resample_profile(
                    [
                        float(x)
                        for x in stroke[
                            "curvature_profile"
                        ]
                    ]
                ),
            )





        return True

    # ========================================================
    # SAMPLE DISCOVERY
    # ========================================================

    def _reference_sample_dirs(
        self,
    ) -> list[Path]:

        if not (
            self.reference_samples_dir.exists()
        ):

            raise FileNotFoundError(
                "Reference samples not found:\n"
                f"{self.reference_samples_dir}"
            )

        return sorted(
            path
            for path in (
                self.reference_samples_dir.iterdir()
            )
            if (
                path.is_dir()
                and (
                    path
                    / "strokes.json"
                ).is_file()
            )
        )

    # ========================================================
    # LEARN ONE SAMPLE
    # ========================================================

    def learn_sample(
        self,
        sample: str | Path,
        knowledge: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        path = Path(
            sample
        )

        strokes_path = (
            path
            / "strokes.json"
            if path.is_dir()
            else path
        )

        if not strokes_path.is_file():

            raise FileNotFoundError(
                f"strokes.json not found: "
                f"{strokes_path}"
            )

        with strokes_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            payload = json.load(
                file
            )

        features = (
            self._extract_reference_features(
                payload
            )
        )

        sample_id = str(
            features[
                "sample_id"
            ]
            or strokes_path.parent.name
        )

        features[
            "sample_id"
        ] = sample_id

        strokes_hash = (
            self.calculate_hash(
                strokes_path
            )
        )

        if knowledge is None:

            knowledge = (
                self._load_reference_knowledge()
            )

        added = (
            self._update_reference_knowledge(
                knowledge,
                features,
                strokes_hash,
            )
        )

        if added:
            self._write_sample_knowledge(
                strokes_path.parent,
                features,
                strokes_hash,
            )
            self._write_sample_trajectory(
                strokes_path.parent,
                payload,
                features,
                strokes_hash,
            )

        return {
            "sample_id": sample_id,
            "added": added,
            "sample_count": (
                knowledge[
                    "sample_count"
                ]
            ),
        }

    # ========================================================
    # INCREMENTAL REFERENCE LEARNING
    # ========================================================

    def learn_reference_samples(
        self,
    ) -> dict[str, Any]:

        """
        Incremental learning using the distributed Knowledge Store.

        Source of truth:
            samples/<sample_id>/strokes.json
            samples/<sample_id>/sample_knowledge.json

        Central knowledge files contain only:
            knowledge/index.json
            knowledge/aggregate.json

        The legacy reference_knowledge.json is migration-only and is
        never written by this learning path.
        """

        sample_dirs = self._reference_sample_dirs()
        knowledge = self._load_reference_knowledge()

        learned_ids = set(knowledge.get("sample_ids", []))
        pending: list[tuple[Path, str]] = []

        for sample_dir in sample_dirs:
            strokes_path = sample_dir / "strokes.json"

            try:
                with strokes_path.open("r", encoding="utf-8") as file:
                    payload = json.load(file)
            except Exception as exc:
                print(f"{sample_dir.name:<20}ERROR reading JSON: {exc}")
                continue

            sample_id = str(payload.get("sample_id") or sample_dir.name)
            knowledge_file = self._sample_knowledge_file(sample_dir)
            strokes_hash = self.calculate_hash(strokes_path)

            index_entry = knowledge.get("samples", {}).get(sample_id, {})
            index_hash = str(index_entry.get("strokes_sha256", ""))

            if sample_id not in learned_ids:
                # Genuinely new reference sample. Add it to the aggregate once.
                pending.append((sample_dir, sample_id))
                continue

            if index_hash != strokes_hash:
                # Reference samples are immutable. We must never silently add a
                # changed version to an aggregate that already contains the old one.
                raise RuntimeError(
                    "REFERENCE SAMPLE CHANGED AFTER LEARNING: "
                    f"{sample_id}. Raw reference samples are immutable; "
                    "restore the original strokes.json or perform an explicit rebuild."
                )

            trajectory_file = self._sample_trajectory_file(sample_dir)

            if (
                not knowledge_file.is_file()
                or not trajectory_file.is_file()
            ):
                # The central aggregate is already authoritative. Recreate
                # only missing per-sample derived documents.
                try:
                    features = self._extract_reference_features(payload)
                    features["sample_id"] = sample_id

                    if not knowledge_file.is_file():
                        self._write_sample_knowledge(
                            sample_dir,
                            features,
                            strokes_hash,
                        )

                    if not trajectory_file.is_file():
                        self._write_sample_trajectory(
                            sample_dir,
                            payload,
                            features,
                            strokes_hash,
                        )

                    print(f"{sample_id:<20}RESTORED")
                except Exception as exc:
                    raise RuntimeError(
                        f"Unable to restore sample knowledge for {sample_id}: {exc}"
                    ) from exc

        print()
        print("=" * 60)
        print("SIGNATURE MACHINE")
        print("ONLINE REFERENCE LEARNING")
        print("=" * 60)
        print("Reference samples path:")
        print(self.reference_samples_dir)
        print(f"Samples discovered: {len(sample_dirs)}")
        print(f"Already learned:    {len(sample_dirs) - len(pending)}")
        print(f"New/changed samples: {len(pending)}")
        print()

        added = 0
        failed = 0

        for sample_dir, sample_id in pending:
            try:
                result = self.learn_sample(
                    sample_dir,
                    knowledge=knowledge,
                )

                if result["added"]:
                    added += 1
                    print(f"{sample_id:<20}OK")
                else:
                    print(f"{sample_id:<20}SKIPPED")

            except Exception as exc:
                failed += 1
                print(f"{sample_id:<20}ERROR: {exc}")

        self._save_reference_knowledge(knowledge)

        print()
        print(f"Knowledge samples: {knowledge.get('sample_count', 0)}")
        print(f"Knowledge index:   {self.reference_knowledge_index_file}")
        print(f"Knowledge aggregate: {self.reference_knowledge_aggregate_file}")
        print(f"Processed:         {len(pending)}")
        print(f"Added:             {added}")
        if failed:
            print(f"Failed:            {failed}")
        print("ONLINE REFERENCE LEARNING COMPLETE")

        return {
            "discovered": len(sample_dirs),
            "processed": len(pending),
            "added": added,
            "failed": failed,
            "sample_count": knowledge.get("sample_count", 0),
            "knowledge_index": str(self.reference_knowledge_index_file),
            "knowledge_aggregate": str(self.reference_knowledge_aggregate_file),
        }

    def validate_reference_knowledge_sync(
        self,
    ) -> dict[str, Any]:

        """Validate that every reference sample is represented in Knowledge."""

        sample_dirs = self._reference_sample_dirs()
        knowledge = self._load_reference_knowledge()
        learned_ids = set(knowledge.get("sample_ids", []))

        missing: list[str] = []
        stale: list[str] = []

        for sample_dir in sample_dirs:
            sample_id = sample_dir.name
            strokes_path = sample_dir / "strokes.json"
            knowledge_file = self._sample_knowledge_file(sample_dir)
            trajectory_file = self._sample_trajectory_file(sample_dir)
            index_entry = knowledge.get("samples", {}).get(sample_id, {})

            if (
                sample_id not in learned_ids
                or not knowledge_file.is_file()
                or not trajectory_file.is_file()
            ):
                missing.append(sample_id)
                continue

            current_hash = self.calculate_hash(strokes_path)
            if str(index_entry.get("strokes_sha256", "")) != current_hash:
                stale.append(sample_id)

        return {
            "reference_sample_count": len(sample_dirs),
            "knowledge_sample_count": int(knowledge.get("sample_count", 0)),
            "missing": sorted(missing),
            "stale": sorted(stale),
            "in_sync": (
                len(sample_dirs) == int(knowledge.get("sample_count", 0))
                and not missing
                and not stale
            ),
        }

    # GENERATION
    # ========================================================

    @staticmethod
    def _generation_rng(
        seed: int | None = None,
    ) -> random.Random:

        if seed is None:
            seed = GENERATION_RANDOM_SEED

        return random.Random(seed)

    # --------------------------------------------------------
    # Load one original reference sample
    # --------------------------------------------------------

    def _load_generation_sample(
        self,
        sample_dir: Path,
    ) -> dict[str, Any]:

        strokes_path = (
            sample_dir
            / "strokes.json"
        )

        if not strokes_path.is_file():

            raise FileNotFoundError(
                f"strokes.json not found: "
                f"{strokes_path}"
            )

        with strokes_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            payload = json.load(
                file
            )

        strokes = payload.get(
            "strokes",
            [],
        )

        if not isinstance(
            strokes,
            list,
        ):

            raise ValueError(
                f"Invalid strokes structure: "
                f"{sample_dir}"
            )

        valid_strokes = []

        for stroke in strokes:

            points = stroke.get(
                "points",
                [],
            )

            if not points:
                continue

            valid_points = []

            for point in points:

                try:

                    valid_points.append(
                        {
                            "x": float(
                                point.get(
                                    "x",
                                    0.0,
                                )
                            ),
                            "y": float(
                                point.get(
                                    "y",
                                    0.0,
                                )
                            ),
                            "pressure": float(
                                point.get(
                                    "pressure",
                                    0.0,
                                )
                            ),
                        }
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    continue

            if valid_points:

                valid_strokes.append(
                    valid_points
                )

        if not valid_strokes:

            raise ValueError(
                f"No valid strokes: "
                f"{sample_dir}"
            )

        return {
            "sample_id": str(
                payload.get(
                    "sample_id",
                    sample_dir.name,
                )
            ),
            "strokes": valid_strokes,
        }

    # --------------------------------------------------------
    # Select a reference sample
    #
    # Generation v0.1 deliberately starts from real
    # reference trajectories instead of constructing a
    # synthetic trajectory from aggregate means.
    # --------------------------------------------------------

    def _select_generation_sample(
        self,
        sample_dirs: list[Path],
        rng: random.Random,
    ) -> Path:

        if not sample_dirs:

            raise ValueError(
                "No reference samples available "
                "for generation."
            )

        return rng.choice(
            sample_dirs
        )

    # --------------------------------------------------------
    # Calculate sample bounding box
    # --------------------------------------------------------

    @staticmethod
    def _generation_bbox(
        strokes: list[list[dict[str, float]]],
    ) -> tuple[
        float,
        float,
        float,
        float,
    ]:

        xs = []
        ys = []

        for stroke in strokes:

            for point in stroke:

                xs.append(
                    float(
                        point["x"]
                    )
                )

                ys.append(
                    float(
                        point["y"]
                    )
                )

        if not xs or not ys:

            raise ValueError(
                "Cannot calculate generation "
                "bounding box."
            )

        return (
            min(xs),
            min(ys),
            max(xs),
            max(ys),
        )

    # --------------------------------------------------------
    # Normalize one reference sample
    #
    # Translation + global scale only.
    #
    # The internal shape of each stroke remains intact.
    # --------------------------------------------------------

    @classmethod
    def _normalize_generation_strokes(
        cls,
        strokes: list[
            list[
                dict[str, float]
            ]
        ],
    ) -> list[
        list[
            dict[str, float]
        ]
    ]:

        min_x, min_y, max_x, max_y = (
            cls._generation_bbox(
                strokes
            )
        )

        width = max(
            max_x - min_x,
            1.0,
        )

        height = max(
            max_y - min_y,
            1.0,
        )

        scale = max(
            width,
            height,
        )

        normalized = []

        for stroke in strokes:

            normalized_stroke = []

            for point in stroke:

                normalized_stroke.append(
                    {
                        "x": (
                            float(
                                point["x"]
                            )
                            - min_x
                        )
                        / scale,
                        "y": (
                            float(
                                point["y"]
                            )
                            - min_y
                        )
                        / scale,
                        "pressure": max(
                            0.0,
                            min(
                                1.0,
                                float(
                                    point.get(
                                        "pressure",
                                        0.0,
                                    )
                                ),
                            ),
                        ),
                    }
                )

            normalized.append(
                normalized_stroke
            )

        return normalized

    # --------------------------------------------------------
    # Controlled geometric variation
    # --------------------------------------------------------

    @classmethod
    def _vary_generation_strokes(
        cls,
        strokes: list[
            list[
                dict[str, float]
            ]
        ],
        rng: random.Random,
    ) -> list[
        list[
            dict[str, float]
        ]
    ]:

        scale_variation = (
            1.0
            + rng.uniform(
                -GENERATION_VARIATION_SCALE,
                GENERATION_VARIATION_SCALE,
            )
        )

        angle = math.radians(
            rng.uniform(
                -GENERATION_VARIATION_ROTATION_DEGREES,
                GENERATION_VARIATION_ROTATION_DEGREES,
            )
        )

        cos_a = math.cos(
            angle
        )

        sin_a = math.sin(
            angle
        )

        translate_x = rng.uniform(
            -GENERATION_VARIATION_TRANSLATION,
            GENERATION_VARIATION_TRANSLATION,
        )

        translate_y = rng.uniform(
            -GENERATION_VARIATION_TRANSLATION,
            GENERATION_VARIATION_TRANSLATION,
        )

        result = []

        for stroke in strokes:

            varied_stroke = []

            for point in stroke:

                x = (
                    float(
                        point["x"]
                    )
                    * scale_variation
                )

                y = (
                    float(
                        point["y"]
                    )
                    * scale_variation
                )

                rotated_x = (
                    x * cos_a
                    - y * sin_a
                )

                rotated_y = (
                    x * sin_a
                    + y * cos_a
                )

                pressure = (
                    float(
                        point.get(
                            "pressure",
                            0.0,
                        )
                    )
                    + rng.uniform(
                        -GENERATION_VARIATION_PRESSURE,
                        GENERATION_VARIATION_PRESSURE,
                    )
                )

                varied_stroke.append(
                    {
                        "x": (
                            rotated_x
                            + translate_x
                        ),
                        "y": (
                            rotated_y
                            + translate_y
                        ),
                        "pressure": max(
                            0.0,
                            min(
                                1.0,
                                pressure,
                            ),
                        ),
                    }
                )

            result.append(
                varied_stroke
            )

        return result

    # --------------------------------------------------------
    # Render candidate for visual evaluation
    #
    # IMPORTANT:
    # This output is intentionally marked as evaluation-only.
    # --------------------------------------------------------

    @staticmethod
    def _render_generation_candidate(
        strokes: list[
            list[
                dict[str, float]
            ]
        ],
        output_path: Path,
        candidate_id: int,
        source_sample_id: str,
    ) -> None:

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not strokes:

            raise ValueError(
                "Cannot render candidate: "
                "no strokes."
            )

        all_points = [
            point
            for stroke in strokes
            for point in stroke
            if isinstance(point, dict)
        ]

        if not all_points:

            raise ValueError(
                "Cannot render candidate: "
                "no points."
            )

        # ----------------------------------------------------
        # Extract coordinates
        # ----------------------------------------------------

        coordinates = []

        for point in all_points:

            try:

                x = float(
                    point["x"]
                )

                y = float(
                    point["y"]
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                continue

            if (
                math.isfinite(x)
                and math.isfinite(y)
            ):

                coordinates.append(
                    (
                        x,
                        y,
                    )
                )

        if not coordinates:

            raise ValueError(
                "Candidate contains no "
                "finite coordinates."
            )

        # ----------------------------------------------------
        # Bounding box
        # ----------------------------------------------------

        min_x = min(
            x
            for x, y in coordinates
        )

        max_x = max(
            x
            for x, y in coordinates
        )

        min_y = min(
            y
            for x, y in coordinates
        )

        max_y = max(
            y
            for x, y in coordinates
        )

        width = max(
            max_x - min_x,
            1e-9,
        )

        height = max(
            max_y - min_y,
            1e-9,
        )

        # ----------------------------------------------------
        # Canvas
        # ----------------------------------------------------

        canvas_width = (
            GENERATION_CANVAS_WIDTH
        )

        canvas_height = (
            GENERATION_CANVAS_HEIGHT
        )

        margin = (
            GENERATION_MARGIN
        )

        available_width = max(
            canvas_width
            - 2 * margin,
            1,
        )

        available_height = max(
            canvas_height
            - 2 * margin,
            1,
        )

        scale = min(
            available_width / width,
            available_height / height,
        )

        # ----------------------------------------------------
        # Create image
        # ----------------------------------------------------

        image = Image.new(
            "RGB",
            (
                canvas_width,
                canvas_height,
            ),
            "white",
        )

        draw = ImageDraw.Draw(
            image
        )

        rendered_stroke_count = 0
        rendered_segment_count = 0

        # ----------------------------------------------------
        # Render every real trajectory
        # ----------------------------------------------------

        for stroke in strokes:

            if not stroke:
                continue

            rendered = []

            for point in stroke:

                try:

                    x = float(
                        point["x"]
                    )

                    y = float(
                        point["y"]
                    )

                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):

                    continue

                if not (
                    math.isfinite(x)
                    and math.isfinite(y)
                ):

                    continue

                px = (
                    margin
                    + (
                        x - min_x
                    )
                    * scale
                )

                py = (
                    margin
                    + (
                        y - min_y
                    )
                    * scale
                )

                rendered.append(
                    (
                        int(
                            round(px)
                        ),
                        int(
                            round(py)
                        ),
                    )
                )

            if not rendered:
                continue

            rendered_stroke_count += 1

            # ------------------------------------------------
            # Normal stroke
            # ------------------------------------------------

            if len(rendered) >= 2:

                draw.line(
                    rendered,
                    fill="black",
                    width=max(
                        1,
                        int(
                            GENERATION_STROKE_WIDTH
                        ),
                    ),
                    joint="curve",
                )

                rendered_segment_count += (
                    len(rendered) - 1
                )

            # ------------------------------------------------
            # Single-point stroke
            #
            # Some reference signatures may contain
            # intentional isolated pen marks.
            # ------------------------------------------------

            elif len(rendered) == 1:

                x, y = rendered[0]

                radius = max(
                    1,
                    int(
                        GENERATION_STROKE_WIDTH
                        / 2
                    ),
                )

                draw.ellipse(
                    (
                        x - radius,
                        y - radius,
                        x + radius,
                        y + radius,
                    ),
                    fill="black",
                )

        # ----------------------------------------------------
        # HARD FAILURE if nothing was actually drawn
        # ----------------------------------------------------

        if rendered_stroke_count == 0:

            raise ValueError(
                "Generation renderer produced "
                "zero drawable strokes."
            )

        if rendered_segment_count == 0:

            # At least one isolated point is allowed,
            # but completely empty rendering is not.
            if not any(
                stroke
                for stroke in strokes
            ):

                raise ValueError(
                    "Generation renderer produced "
                    "no drawable content."
                )

        # ----------------------------------------------------
        # Save PURE SIGNATURE IMAGE
        #
        # No metadata
        # No evaluation label
        # No watermark
        # ----------------------------------------------------

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image.save(
            output_path,
            format="PNG",
        )

        # ----------------------------------------------------
        # Final verification
        # ----------------------------------------------------

        if not output_path.is_file():

            raise IOError(
                "Generation output was not created: "
                f"{output_path}"
            )

        # Verify that image contains at least
        # one non-white pixel.
        #
        # This prevents a silent white PNG from
        # being reported as successful.
        # ----------------------------------------------------

        verification = image.convert(
            "RGB"
        )

        non_white = False

        for pixel in verification.getdata():

            if pixel != (
                255,
                255,
                255,
            ):

                non_white = True
                break

        if not non_white:

            raise ValueError(
                "Generation output is completely "
                "white."
            )
        # --------------------------------------------------------
    # Select multiple real reference samples
    #
    # Generation v0.2:
    #
    # A candidate is no longer derived from one reference
    # sample only.
    #
    # The structural skeleton comes from one real sample,
    # while individual strokes may be borrowed from other
    # real reference samples.
    #
    # No synthetic trajectory is created.
    # --------------------------------------------------------

    def _select_generation_sources(
        self,
        sample_dirs: list[Path],
        rng: random.Random,
        count: int = 3,
    ) -> list[Path]:

        if not sample_dirs:

            raise ValueError(
                "No reference samples available."
            )

        if count <= 0:

            count = 1

        if len(sample_dirs) <= count:

            result = list(
                sample_dirs
            )

            rng.shuffle(
                result
            )

            return result

        return rng.sample(
            sample_dirs,
            count,
        )

    # --------------------------------------------------------
    # Blend real strokes
    #
    # IMPORTANT:
    #
    # Every output stroke originates from an actual reference
    # trajectory.
    #
    # We never interpolate arbitrary points between unrelated
    # trajectories and never invent a new curve.
    # --------------------------------------------------------

    @classmethod
    def _compose_generation_strokes(
        cls,
        sources: list[
            dict[str, Any]
        ],
        rng: random.Random,
    ) -> tuple[
        list[
            list[
                dict[str, float]
            ]
        ],
        list[str],
    ]:

        if not sources:

            raise ValueError(
                "No generation sources available."
            )

        # ----------------------------------------------------
        # Select structural base.
        #
        # The first source defines the stroke count.
        # ----------------------------------------------------

        base = sources[
            0
        ]

        base_strokes = (
            cls._normalize_generation_strokes(
                base["strokes"]
            )
        )

        if not base_strokes:

            raise ValueError(
                "Base reference contains no strokes."
            )

        composed = []

        source_ids = [
            str(
                source[
                    "sample_id"
                ]
            )
            for source in sources
        ]

        # ----------------------------------------------------
        # Each stroke comes from a real reference.
        #
        # We prefer references that contain the requested
        # stroke index. If they do not, we fall back to the
        # structural base.
        # ----------------------------------------------------

        for stroke_index in range(
            len(base_strokes)
        ):

            eligible = [
                source
                for source in sources
                if stroke_index
                < len(
                    source[
                        "strokes"
                    ]
                )
            ]

            if not eligible:

                eligible = [
                    base
                ]

            selected_source = (
                rng.choice(
                    eligible
                )
            )

            normalized = (
                cls._normalize_generation_strokes(
                    selected_source[
                        "strokes"
                    ]
                )
            )

            selected_stroke = (
                normalized[
                    stroke_index
                ]
            )

            # Make a deep numeric copy so that later
            # variation never mutates the source data.
            copied_stroke = []

            for point in selected_stroke:

                copied_stroke.append(
                    {
                        "x": float(
                            point["x"]
                        ),
                        "y": float(
                            point["y"]
                        ),
                        "pressure": float(
                            point.get(
                                "pressure",
                                0.0,
                            )
                        ),
                    }
                )

            composed.append(
                copied_stroke
            )

        return (
            composed,
            source_ids,
        )

    # --------------------------------------------------------
    # Generate ONE candidate
    # --------------------------------------------------------


    # ========================================================
    # GENERATION v0.3
    # Learned Whole-Signature Morphing
    # ========================================================

    @staticmethod
    def _generation_sample_normal(
        mean: float,
        m2: float,
        count: int,
        rng: random.Random,
        strength: float = 0.35,
    ) -> float:

        if count <= 1:
            return float(mean)

        variance = max(
            0.0,
            float(m2)
            / float(count - 1),
        )

        std = math.sqrt(
            variance
        )

        return (
            float(mean)
            + rng.gauss(
                0.0,
                std * strength,
            )
        )

    @staticmethod
    def _generation_profile_state(
        aggregate: dict[str, Any],
        section: str,
        stroke_index: int,
    ) -> dict[str, Any] | None:

        profiles = aggregate.get(
            section,
            {},
        )

        state = profiles.get(
            str(stroke_index)
        )

        if not isinstance(
            state,
            dict,
        ):
            return None

        mean = state.get(
            "mean",
            [],
        )

        m2 = state.get(
            "m2",
            [],
        )

        count = int(
            state.get(
                "count",
                0,
            )
            or 0
        )

        if not isinstance(
            mean,
            list,
        ):
            return None

        if not isinstance(
            m2,
            list,
        ):
            return None

        if not mean:
            return None

        if len(mean) != len(m2):
            return None

        if count <= 0:
            return None

        return {
            "count": count,
            "mean": mean,
            "m2": m2,
        }

    # --------------------------------------------------------
    # Determine a plausible stroke count from learned
    # reference stroke-presence statistics.
    #
    # This does NOT copy the stroke count of one sample.
    # It samples the structural distribution learned from all
    # reference samples.
    # --------------------------------------------------------

    def _sample_generation_stroke_count(
        self,
        knowledge: dict[str, Any],
        rng: random.Random,
    ) -> int:
        trajectory_samples = (
            self._load_generation_trajectory_samples()
        )

        counts = [
            int(sample["stroke_count"])
            for sample in trajectory_samples
            if int(sample.get("stroke_count", 0)) > 0
        ]

        if not counts:
            raise ValueError(
                "No trajectory stroke-count knowledge available."
            )

        return rng.choice(counts)

    def _generation_stroke_match_cost(
        a: list[dict[str, float]],
        b: list[dict[str, float]],
    ) -> float:
        """Compare complete strokes, never fragments."""

        if not a or not b:
            return float("inf")

        def endpoint(stroke, index):
            point = stroke[index]
            return (
                float(point["x"]),
                float(point["y"]),
            )

        ax0, ay0 = endpoint(a, 0)
        ax1, ay1 = endpoint(a, -1)
        bx0, by0 = endpoint(b, 0)
        bx1, by1 = endpoint(b, -1)

        start_cost = math.hypot(
            ax0 - bx0,
            ay0 - by0,
        )
        end_cost = math.hypot(
            ax1 - bx1,
            ay1 - by1,
        )

        a_mid = a[len(a) // 2]
        b_mid = b[len(b) // 2]
        mid_cost = math.hypot(
            float(a_mid["x"])
            - float(b_mid["x"]),
            float(a_mid["y"])
            - float(b_mid["y"]),
        )

        return (
            start_cost * 0.35
            + end_cost * 0.35
            + mid_cost * 0.30
        )

    @classmethod
    def _generation_align_strokes(
        cls,
        base: list[
            list[
                dict[str, float]
            ]
        ],
        other: list[
            list[
                dict[str, float]
            ]
        ],
    ) -> list[
        list[
            dict[str, float]
        ]
    ]:
        """
        Match COMPLETE strokes by learned spatial role.

        No partial stroke is selected and no source path is spliced.
        """

        remaining = list(
            range(len(other))
        )
        aligned = []

        for base_stroke in base:
            if not remaining:
                return []

            best_index = min(
                remaining,
                key=lambda index: cls._generation_stroke_match_cost(
                    base_stroke,
                    other[index],
                ),
            )

            aligned.append(
                other[best_index]
            )
            remaining.remove(
                best_index
            )

        return aligned

    def _load_generation_trajectory_samples(
        self,
    ) -> list[dict[str, Any]]:
        """
        Load the per-sample trajectory knowledge.

        Generation v0.4 deliberately reads trajectory.json from each
        reference sample instead of expecting the old monolithic
        knowledge["samples"][...]["normalized_strokes"] structure.
        """

        documents = []

        for sample_dir in self._reference_sample_dirs():
            trajectory_path = (
                sample_dir / "trajectory.json"
            )

            if not trajectory_path.is_file():
                continue

            try:
                with trajectory_path.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    document = json.load(file)
            except Exception:
                continue

            if not isinstance(document, dict):
                continue

            strokes = document.get("strokes", [])
            execution = document.get("execution", {})

            if not isinstance(strokes, list):
                continue

            try:
                stroke_count = int(
                    execution.get(
                        "stroke_count",
                        len(strokes),
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                stroke_count = len(strokes)

            if stroke_count <= 0 or len(strokes) != stroke_count:
                continue

            normalized_strokes = []

            valid = True

            for stroke in strokes:
                trajectory = (
                    stroke.get(
                        "normalized_trajectory",
                        [],
                    )
                    if isinstance(stroke, dict)
                    else []
                )

                if not isinstance(trajectory, list):
                    valid = False
                    break

                clean = []

                for point in trajectory:
                    if not isinstance(point, dict):
                        continue

                    try:
                        x = float(point.get("x", 0.0))
                        y = float(point.get("y", 0.0))
                        pressure = float(
                            point.get("pressure", 0.0)
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        continue

                    if not (
                        math.isfinite(x)
                        and math.isfinite(y)
                        and math.isfinite(pressure)
                    ):
                        continue

                    clean.append(
                        {
                            "x": x,
                            "y": y,
                            "pressure": max(
                                0.0,
                                min(1.0, pressure),
                            ),
                        }
                    )

                if len(clean) < 2:
                    valid = False
                    break

                normalized_strokes.append(clean)

            if not valid:
                continue

            documents.append(
                {
                    "sample_id": str(
                        document.get(
                            "sample_id",
                            sample_dir.name,
                        )
                    ),
                    "stroke_count": stroke_count,
                    "strokes": normalized_strokes,
                    "execution": execution,
                }
            )

        return documents

    @classmethod
    def _trajectory_stroke_match_cost(
        cls,
        a: list[dict[str, float]],
        b: list[dict[str, float]],
    ) -> float:
        """Compare two complete strokes by start/end/mid geometry."""

        if not a or not b:
            return float("inf")

        def endpoint(stroke, index):
            p = stroke[index]
            return float(p["x"]), float(p["y"])

        ax0, ay0 = endpoint(a, 0)
        ax1, ay1 = endpoint(a, -1)
        bx0, by0 = endpoint(b, 0)
        bx1, by1 = endpoint(b, -1)

        a_mid = a[len(a) // 2]
        b_mid = b[len(b) // 2]

        return (
            0.35 * math.hypot(ax0 - bx0, ay0 - by0)
            + 0.35 * math.hypot(ax1 - bx1, ay1 - by1)
            + 0.30 * math.hypot(
                float(a_mid["x"]) - float(b_mid["x"]),
                float(a_mid["y"]) - float(b_mid["y"]),
            )
        )

    @classmethod
    def _align_complete_trajectory_strokes(
        cls,
        base: list[list[dict[str, float]]],
        other: list[list[dict[str, float]]],
    ) -> list[list[dict[str, float]]]:
        """
        Align complete strokes only.

        No stroke is cut, spliced, or borrowed partially.
        """

        if len(base) != len(other):
            return []

        remaining = list(range(len(other)))
        aligned = []

        for base_stroke in base:
            if not remaining:
                return []

            index = min(
                remaining,
                key=lambda i: cls._trajectory_stroke_match_cost(
                    base_stroke,
                    other[i],
                ),
            )

            aligned.append(other[index])
            remaining.remove(index)

        return aligned

    @staticmethod
    def _generation_blend_weights(
        count: int,
        rng: random.Random,
    ) -> list[float]:
        """
        Return normalized weights for complete trajectory sources.

        The weights provide controlled variation while ensuring every
        selected source contributes to the whole-signature synthesis.
        """
        if count <= 0:
            raise ValueError(
                "Blend weight count must be greater than zero."
            )

        if count == 1:
            return [1.0]

        raw = [
            0.70 + rng.random() * 0.60
            for _ in range(count)
        ]

        total = sum(raw)

        if total <= 0.0:
            return [
                1.0 / count
                for _ in range(count)
            ]

        return [
            value / total
            for value in raw
        ]

    @staticmethod
    def _generation_smooth_noise(
        point_count: int,
        rng: random.Random,
        control_points: int = 8,
    ) -> list[float]:
        """
        Generate low-frequency, smoothly interpolated deformation.

        This deliberately avoids independent point-to-point random noise,
        which would damage the learned trajectory.
        """
        if point_count <= 0:
            return []

        if point_count == 1:
            return [0.0]

        control_count = max(
            2,
            min(
                control_points,
                point_count,
            ),
        )

        controls = [
            rng.uniform(-1.0, 1.0)
            for _ in range(control_count)
        ]

        values = []

        for index in range(point_count):
            position = (
                index
                * (control_count - 1)
                / (point_count - 1)
            )

            left = int(math.floor(position))
            right = min(
                left + 1,
                control_count - 1,
            )

            fraction = position - left

            # Smoothstep interpolation.
            smooth = (
                fraction
                * fraction
                * (3.0 - 2.0 * fraction)
            )

            value = (
                controls[left]
                * (1.0 - smooth)
                + controls[right]
                * smooth
            )

            values.append(value)

        return values

    def _synthesize_generation_geometry(
        self,
        knowledge: dict[str, Any],
        stroke_count: int,
        rng: random.Random,
    ) -> list[list[dict[str, float]]]:
        """
        Generation v0.4 — trajectory-based new-signature synthesis.

        The generator reads complete trajectories from the decentralized
        trajectory.json files. It learns a whole-signature geometric pattern
        from the eligible references, aligns complete strokes, blends their
        corresponding trajectories, and applies a smooth low-frequency
        deformation.

        This is NOT source-signature selection and NOT partial-stroke
        splicing.
        """

        trajectory_samples = (
            self._load_generation_trajectory_samples()
        )

        eligible = [
            sample
            for sample in trajectory_samples
            if sample["stroke_count"] == stroke_count
        ]

        if not eligible:
            # If an exact stroke-count bucket is unavailable, choose the
            # nearest learned bucket rather than failing Generation.
            available = sorted(
                {
                    int(sample["stroke_count"])
                    for sample in trajectory_samples
                }
            )

            if not available:
                raise ValueError(
                    "No trajectory knowledge available."
                )

            nearest = min(
                available,
                key=lambda value: abs(value - stroke_count),
            )

            eligible = [
                sample
                for sample in trajectory_samples
                if sample["stroke_count"] == nearest
            ]

            stroke_count = nearest

        source_count = min(
            8,
            len(eligible),
        )

        if source_count == 1:
            selected = eligible
        else:
            selected = rng.sample(
                eligible,
                source_count,
            )

        base = selected[0]["strokes"]
        aligned_sources = [base]

        for sample in selected[1:]:
            aligned = self._align_complete_trajectory_strokes(
                base,
                sample["strokes"],
            )

            if aligned:
                aligned_sources.append(aligned)

        if not aligned_sources:
            raise ValueError(
                "Trajectory alignment produced no usable sources."
            )

        weights = self._generation_blend_weights(
            len(aligned_sources),
            rng,
        )

        generated_strokes = []

        rotation = math.radians(
            rng.uniform(-3.0, 3.0)
        )
        cos_a = math.cos(rotation)
        sin_a = math.sin(rotation)

        scale = rng.uniform(
            0.96,
            1.04,
        )

        shear = rng.uniform(
            -0.018,
            0.018,
        )

        for stroke_index in range(stroke_count):
            point_count = min(
                len(source[stroke_index])
                for source in aligned_sources
            )

            if point_count < 2:
                continue

            noise = self._generation_smooth_noise(
                point_count,
                rng,
                control_points=min(
                    8,
                    max(5, point_count // 5),
                ),
            )

            generated = []

            for point_index in range(point_count):
                x = 0.0
                y = 0.0
                pressure = 0.0

                for weight, source in zip(
                    weights,
                    aligned_sources,
                ):
                    point = source[
                        stroke_index
                    ][point_index]

                    x += weight * point["x"]
                    y += weight * point["y"]
                    pressure += weight * point["pressure"]

                u = point_index / max(
                    point_count - 1,
                    1,
                )

                # Smooth normal deformation, strongest in the middle and
                # approaching zero at stroke endpoints.
                if point_index == 0:
                    p0 = aligned_sources[0][
                        stroke_index
                    ][0]
                    p1 = aligned_sources[0][
                        stroke_index
                    ][1]
                elif point_index == point_count - 1:
                    p0 = aligned_sources[0][
                        stroke_index
                    ][point_count - 2]
                    p1 = aligned_sources[0][
                        stroke_index
                    ][point_count - 1]
                else:
                    p0 = generated[-1]
                    p1 = aligned_sources[0][
                        stroke_index
                    ][point_index + 1]

                tx = p1["x"] - p0["x"]
                ty = p1["y"] - p0["y"]

                length = math.hypot(tx, ty)

                if length > 1e-9:
                    tx /= length
                    ty /= length
                    nx = -ty
                    ny = tx

                    endpoint_weight = (
                        math.sin(math.pi * u) ** 0.9
                    )

                    displacement = (
                        noise[point_index]
                        * 0.012
                        * endpoint_weight
                    )

                    x += nx * displacement
                    y += ny * displacement

                sx = x * scale + shear * y
                sy = y * scale

                rx = (
                    sx * cos_a
                    - sy * sin_a
                )
                ry = (
                    sx * sin_a
                    + sy * cos_a
                )

                generated.append(
                    {
                        "x": rx,
                        "y": ry,
                        "pressure": max(
                            0.0,
                            min(
                                1.0,
                                pressure,
                            ),
                        ),
                        "u": u,
                    }
                )

            generated_strokes.append(
                generated
            )

        if not generated_strokes:
            raise ValueError(
                "Trajectory synthesis produced no strokes."
            )

        # Global normalization keeps the complete generated signature
        # coherent after the candidate-level transformation.
        all_points = [
            point
            for stroke in generated_strokes
            for point in stroke
        ]

        min_x = min(
            point["x"]
            for point in all_points
        )
        max_x = max(
            point["x"]
            for point in all_points
        )
        min_y = min(
            point["y"]
            for point in all_points
        )
        max_y = max(
            point["y"]
            for point in all_points
        )

        global_scale = max(
            max_x - min_x,
            max_y - min_y,
            1e-9,
        )

        for stroke in generated_strokes:
            for point in stroke:
                point["x"] = (
                    point["x"] - min_x
                ) / global_scale
                point["y"] = (
                    point["y"] - min_y
                ) / global_scale

        return generated_strokes

    # --------------------------------------------------------
    # Learned dynamic profiles
    #
    # Geometry is the primary trajectory.
    #
    # Velocity / pressure / direction / curvature are
    # generated from their learned distributions and attached
    # to the new trajectory as behavioral metadata.
    # --------------------------------------------------------

    @classmethod
    def _synthesize_generation_dynamics(
        cls,
        knowledge: dict[str, Any],
        strokes: list[
            list[
                dict[str, float]
            ]
        ],
        rng: random.Random,
    ) -> list[
        list[
            dict[str, float]
        ]
    ]:
        """
        Attach learned behavioral dynamics to the newly synthesized path.

        Direction/curvature are used as style signals, not as independent
        coordinate noise. Velocity and pressure remain smooth profiles.
        """

        aggregate = knowledge.get(
            "aggregate",
            {},
        )

        for stroke_index, stroke in enumerate(strokes):
            if not stroke:
                continue

            velocity_state = cls._generation_profile_state(
                aggregate,
                "stroke_velocity_profiles",
                stroke_index,
            )
            pressure_state = cls._generation_profile_state(
                aggregate,
                "stroke_pressure_profiles",
                stroke_index,
            )
            direction_state = cls._generation_profile_state(
                aggregate,
                "stroke_direction_profiles",
                stroke_index,
            )
            curvature_state = cls._generation_profile_state(
                aggregate,
                "stroke_curvature_profiles",
                stroke_index,
            )

            point_count = len(stroke)

            # One smooth stochastic field per behavioral dimension.
            velocity_noise = cls._generation_smooth_noise(
                point_count,
                rng,
                control_points=5,
            )
            pressure_noise = cls._generation_smooth_noise(
                point_count,
                rng,
                control_points=5,
            )

            for i, point in enumerate(stroke):
                u = i / max(point_count - 1, 1)

                if velocity_state:
                    mean = velocity_state["mean"]
                    m2 = velocity_state["m2"]
                    count = velocity_state["count"]
                    j = min(i, len(mean) - 1)
                    velocity = cls._generation_sample_normal(
                        mean[j],
                        m2[j],
                        count,
                        rng,
                        strength=0.10,
                    )
                    point["velocity"] = max(
                        0.0,
                        velocity + abs(velocity_noise[i]) * max(0.0, velocity) * 0.025,
                    )

                if pressure_state:
                    mean = pressure_state["mean"]
                    m2 = pressure_state["m2"]
                    count = pressure_state["count"]
                    j = min(i, len(mean) - 1)
                    pressure = cls._generation_sample_normal(
                        mean[j],
                        m2[j],
                        count,
                        rng,
                        strength=0.10,
                    )
                    point["pressure"] = max(
                        0.0,
                        min(
                            1.0,
                            pressure + 0.02 * pressure_noise[i],
                        ),
                    )

                # Keep these as diagnostics/behavioral metadata. They are
                # not turned into random coordinate jumps.
                if direction_state:
                    mean = direction_state["mean"]
                    m2 = direction_state["m2"]
                    count = direction_state["count"]
                    j = min(i, len(mean) - 1)
                    point["direction_delta"] = max(
                        0.0,
                        cls._generation_sample_normal(
                            mean[j],
                            m2[j],
                            count,
                            rng,
                            strength=0.08,
                        ),
                    )

                if curvature_state:
                    mean = curvature_state["mean"]
                    m2 = curvature_state["m2"]
                    count = curvature_state["count"]
                    j = min(i, len(mean) - 1)
                    point["curvature"] = max(
                        0.0,
                        cls._generation_sample_normal(
                            mean[j],
                            m2[j],
                            count,
                            rng,
                            strength=0.08,
                        ),
                    )

                point["u"] = u

        return strokes

    # --------------------------------------------------------
    # Generate a NEW learned trajectory
    #
    # This is deliberately independent from reference sample
    # selection.
    # --------------------------------------------------------

    def _generate_learned_trajectory(
        self,
        knowledge: dict[str, Any],
        rng: random.Random,
    ) -> tuple[
        list[
            list[
                dict[str, float]
            ]
        ],
        int,
    ]:

        stroke_count = (
            self._sample_generation_stroke_count(
                knowledge,
                rng,
            )
        )

        strokes = (
            self._synthesize_generation_geometry(
                knowledge,
                stroke_count,
                rng,
            )
        )

        strokes = (
            self._synthesize_generation_dynamics(
                knowledge,
                strokes,
                rng,
            )
        )

        return (
            strokes,
            stroke_count,
        )

        # --------------------------------------------------------
    # Generate ONE learned candidate
    # --------------------------------------------------------

    def _generate_candidate(
        self,
        knowledge: dict[str, Any],
        rng: random.Random,
        candidate_id: int,
        output_dir: Path,
    ) -> dict[str, Any]:

        strokes, stroke_count = (
            self._generate_learned_trajectory(
                knowledge,
                rng,
            )
        )

        output_path = (
            output_dir
            / (
                f"candidate_"
                f"{candidate_id:03d}.png"
            )
        )

        self._render_generation_candidate(
            strokes,
            output_path,
            candidate_id,
            "LEARNED",
        )

        return {
            "candidate_id": candidate_id,

            "source_sample_id": None,

            "source_sample_ids": [],

            "output": str(
                output_path
            ),

            "stroke_count": (
                stroke_count
            ),

            "generation_method": (
                "trajectory_based_new_signature"
            ),
        }

  
    
    # --------------------------------------------------------
    # Generate multiple candidates
    # --------------------------------------------------------

    def generate_signatures(
        self,
        count: int = (
            GENERATION_DEFAULT_CANDIDATES
        ),
        output_dir: str | Path | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:

        if count <= 0:

            raise ValueError(
                "Generation count must be greater than zero."
            )

        sample_dirs = (
            self._reference_sample_dirs()
        )

        if not sample_dirs:

            raise FileNotFoundError(
                "No reference samples available."
            )

        knowledge = (
            self._load_reference_knowledge()
        )

        sync = self.validate_reference_knowledge_sync()

        if not sync["in_sync"]:
            raise RuntimeError(
                "REFERENCE KNOWLEDGE OUT OF SYNC: "
                f"references={sync['reference_sample_count']} "
                f"knowledge={sync['knowledge_sample_count']} "
                f"missing={sync['missing']} "
                f"stale={sync['stale']}"
            )

        knowledge_sample_count = int(
            knowledge.get(
                "sample_count",
                0,
            )
        )

        if knowledge_sample_count <= 0:

            raise ValueError(
                "Reference Knowledge is empty."
            )

        if output_dir is None:

            output_dir = (
                self.reference_learning_dir
                / "generation"
                / "evaluation"
            )

        output_dir = Path(
            output_dir
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        rng = (
            self._generation_rng(
                seed
            )
        )

        print()
        print("=" * 60)
        print(
            "SIGNATURE MACHINE"
        )
        print(
            "GENERATION v"
            f"{GENERATION_VERSION}"
        )
        print("=" * 60)

        print(
            "Reference samples:"
        )

        print(
            len(sample_dirs)
        )

        print(
            "Knowledge samples:"
        )

        print(
            knowledge_sample_count
        )

        print(
            "Candidates:"
        )

        print(
            count
        )

        print()

        generated = []

        failed = 0

        for candidate_id in range(
            1,
            count + 1,
        ):

            try:

                result = (
                    self._generate_candidate(
                        knowledge,
                        rng,
                        candidate_id,
                        output_dir,
                    )
                )

                generated.append(
                    result
                )

                print(
                    f"Candidate "
                    f"{candidate_id:03d} "
                    "OK"
                )

                print(
                    "  source: "
                    f"{result['source_sample_id']}"
                )

                print(
                    "  strokes: "
                    f"{result['stroke_count']}"
                )

                print(
                    "  output: "
                    f"{result['output']}"
                )

            except Exception as exc:

                failed += 1

                print(
                    f"Candidate "
                    f"{candidate_id:03d} "
                    f"ERROR: {exc}"
                )

        print()

        print(
            "Generated:"
            f" {len(generated)}"
        )

        print(
            "Failed:"
            f" {failed}"
        )

        print(
            "GENERATION COMPLETE"
        )

        return {
            "generation_version": (
                GENERATION_VERSION
            ),
            "knowledge_sample_count": (
                knowledge_sample_count
            ),
            "reference_sample_count": (
                len(sample_dirs)
            ),
            "requested": count,
            "generated": len(
                generated
            ),
            "failed": failed,
            "candidates": generated,
            "output_dir": str(
                output_dir
            ),
        }



# ============================================================
# MAIN
# ============================================================

def main() -> None:

    # IMPORTANT:
    #
    # Normal execution NEVER scans library/.
    #
    # The learning source is exclusively:
    #
    # online_training_data/
    #     reference_learning/
    #         samples/
    #
    SignatureCore().learn_reference_samples()

        # ========================================================

if __name__ == "__main__":
    main()