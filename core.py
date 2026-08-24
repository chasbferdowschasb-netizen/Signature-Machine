# -*- coding: utf-8 -*-

"""
Signature Machine
Core v0.3

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

REFERENCE_KNOWLEDGE_VERSION = "0.3"

RESAMPLE_POINTS = 32
GENERATION_VERSION = "0.1"

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
    # KNOWLEDGE SCHEMA
    # ========================================================

    @classmethod
    def _new_knowledge(
        cls,
    ) -> dict[str, Any]:

        return {
            "schema_version": (
                REFERENCE_KNOWLEDGE_VERSION
            ),
            "sample_count": 0,
            "sample_ids": [],
            "samples": {},
            "feature_schema": {
                "normalization": (
                    "translation_and_global_scale"
                ),
                "stroke_resampling_points": (
                    RESAMPLE_POINTS
                ),
                "cross_stroke_bridging": False,
                "touch_points_are_valid": True,
                "sample_weighting": (
                    "equal_per_sample"
                ),
                "full_sample_trajectory": True,
                "velocity_profile": True,
                "pressure_profile": True,
                "direction_profile": True,
                "curvature_profile": True,
                "inter_stroke_timing": True,
                "tilt_and_twist_profile": True,
            },
            "learning_policy": {
                "duplicate_sample_id": (
                    "ignored"
                ),
                "duplicate_strokes_hash": (
                    "ignored"
                ),
                "status_weighting": (
                    "disabled"
                ),
                "pointer_type_filtering": (
                    "disabled"
                ),
                "library_scanning_for_learning": (
                    False
                ),
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

    def _load_reference_knowledge(
        self,
    ) -> dict[str, Any]:

        if not (
            self.reference_knowledge_file.exists()
        ):

            return (
                self._new_knowledge()
            )

        try:

            with self.reference_knowledge_file.open(
                "r",
                encoding="utf-8",
            ) as file:

                knowledge = (
                    json.load(file)
                )

        except Exception:

            return (
                self._new_knowledge()
            )
        if (
            knowledge.get(
                "schema_version"
            )
            != REFERENCE_KNOWLEDGE_VERSION
        ):
            return (
                self._new_knowledge()
            )

        # ----------------------------------------------------
        # KNOWLEDGE STRUCTURE VALIDATION
        #
        # schema_version alone is not sufficient because an
        # older/incomplete Knowledge file may have the same
        # version number.
        # ----------------------------------------------------

        feature_schema = knowledge.get(
            "feature_schema"
        )

        required_feature_schema = {
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

        if not isinstance(
            feature_schema,
            dict,
        ):
            return (
                self._new_knowledge()
            )

        if not required_feature_schema.issubset(
            feature_schema.keys()
        ):
            return (
                self._new_knowledge()
            )

        # ----------------------------------------------------
        # LEARNING POLICY VALIDATION
        # ----------------------------------------------------

        learning_policy = knowledge.get(
            "learning_policy"
        )

        required_learning_policy = {
            "duplicate_sample_id",
            "duplicate_strokes_hash",
            "status_weighting",
            "pointer_type_filtering",
            "library_scanning_for_learning",
        }

        if not isinstance(
            learning_policy,
            dict,
        ):
            return (
                self._new_knowledge()
            )

        if not required_learning_policy.issubset(
            learning_policy.keys()
        ):
            return (
                self._new_knowledge()
            )

        # ----------------------------------------------------
        # AGGREGATE STRUCTURE VALIDATION
        # ----------------------------------------------------

        aggregate = knowledge.get(
            "aggregate"
        )

        required_aggregate = {
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

        if not isinstance(
            aggregate,
            dict,
        ):
            return (
                self._new_knowledge()
            )

        if not required_aggregate.issubset(
            aggregate.keys()
        ):
            return (
                self._new_knowledge()
            )

        # ----------------------------------------------------
        # BASIC SAMPLE STRUCTURE VALIDATION
        # ----------------------------------------------------

        if not isinstance(
            knowledge.get("samples"),
            dict,
        ):
            return (
                self._new_knowledge()
            )

        if not isinstance(
            knowledge.get("sample_ids"),
            list,
        ):
            return (
                self._new_knowledge()
            )

        if (
            knowledge.get("sample_count")
            != len(
                knowledge.get(
                    "sample_ids",
                    [],
                )
            )
        ):
            return (
                self._new_knowledge()
            )

        return knowledge

    def _save_reference_knowledge(
        self,
        knowledge: dict[str, Any],
    ) -> None:

        self.reference_learning_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp = (
            self.reference_knowledge_file
            .with_suffix(
                ".tmp"
            )
        )

        with temp.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                knowledge,
                file,
                ensure_ascii=False,
                indent=2,
            )

        temp.replace(
            self.reference_knowledge_file
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
        # Store complete sample
        # ----------------------------------------------------

        knowledge[
            "samples"
        ][sample_id] = {
            "strokes_sha256": (
                strokes_hash
            ),
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
            "normalized_bbox": (
                features[
                    "normalized_bbox"
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
            "normalized_strokes": (
                features[
                    "normalized_strokes"
                ]
            ),
            "stroke_features": (
                features[
                    "stroke_features"
                ]
            ),
            "inter_stroke_gaps_ms": (
                features[
                    "inter_stroke_gaps_ms"
                ]
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
        Normal learning path.

        IMPORTANT:
        This method ONLY scans:

            online_training_data/
            reference_learning/
            samples/

        It NEVER scans library/.

        If Knowledge schema is old, all existing reference samples
        are rebuilt once. Future runs are incremental.
        """

        sample_dirs = (
            self._reference_sample_dirs()
        )

        # ----------------------------------------------------
        # Detect old/new schema.
        # ----------------------------------------------------

        existing_knowledge = None

        if (
            self.reference_knowledge_file.exists()
        ):

            try:

                with (
                    self.reference_knowledge_file.open(
                        "r",
                        encoding="utf-8",
                    )
                ) as file:

                    existing_knowledge = (
                        json.load(file)
                    )

            except Exception:

                existing_knowledge = None

                # ----------------------------------------------------
        # Detect old/incomplete Knowledge.
        #
        # schema_version alone is NOT sufficient because an
        # older Knowledge file may have the same version number
        # while still using an incomplete feature schema.
        # ----------------------------------------------------

        required_feature_schema = {
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

        required_learning_policy = {
            "duplicate_sample_id",
            "duplicate_strokes_hash",
            "status_weighting",
            "pointer_type_filtering",
            "library_scanning_for_learning",
        }

        required_aggregate = {
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

        knowledge_structure_valid = False

        if isinstance(
            existing_knowledge,
            dict,
        ):

            feature_schema = (
                existing_knowledge.get(
                    "feature_schema"
                )
            )

            learning_policy = (
                existing_knowledge.get(
                    "learning_policy"
                )
            )

            aggregate = (
                existing_knowledge.get(
                    "aggregate"
                )
            )

            knowledge_structure_valid = (
                existing_knowledge.get(
                    "schema_version"
                )
                == REFERENCE_KNOWLEDGE_VERSION
                and isinstance(
                    feature_schema,
                    dict,
                )
                and required_feature_schema.issubset(
                    feature_schema.keys()
                )
                and isinstance(
                    learning_policy,
                    dict,
                )
                and required_learning_policy.issubset(
                    learning_policy.keys()
                )
                and isinstance(
                    aggregate,
                    dict,
                )
                and required_aggregate.issubset(
                    aggregate.keys()
                )
                and isinstance(
                    existing_knowledge.get(
                        "samples"
                    ),
                    dict,
                )
                and isinstance(
                    existing_knowledge.get(
                        "sample_ids"
                    ),
                    list,
                )
            )

        schema_changed = (
            existing_knowledge is not None
            and not knowledge_structure_valid
        )


        if existing_knowledge is None:

            knowledge = (
                self._new_knowledge()
            )

            rebuild = False

        elif schema_changed:

            knowledge = (
                self._new_knowledge()
            )

            rebuild = True

        else:

            knowledge = (
                existing_knowledge
            )

            rebuild = False

        learned_ids = set(
            knowledge.get(
                "sample_ids",
                [],
            )
        )

        pending = []

        for sample_dir in (
            sample_dirs
        ):

            strokes_path = (
                sample_dir
                / "strokes.json"
            )

            try:

                with strokes_path.open(
                    "r",
                    encoding="utf-8",
                ) as file:

                    payload = json.load(
                        file
                    )

            except Exception as exc:

                print(
                    f"{sample_dir.name:<20}"
                    f"ERROR reading JSON: "
                    f"{exc}"
                )

                continue

            sample_id = str(
                payload.get(
                    "sample_id"
                )
                or sample_dir.name
            )

            if (
                rebuild
                or sample_id
                not in learned_ids
            ):

                pending.append(
                    (
                        sample_dir,
                        sample_id,
                    )
                )

        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print(
            "SIGNATURE MACHINE"
        )
        print(
            "ONLINE REFERENCE LEARNING"
        )
        print("=" * 60)

        print(
            "Reference samples path:"
        )

        print(
            self.reference_samples_dir
        )

        print(
            f"Samples discovered: "
            f"{len(sample_dirs)}"
        )

        if rebuild:

            print(
                "Knowledge schema:     "
                f"{REFERENCE_KNOWLEDGE_VERSION}"
            )

            print(
                "Previous schema:      "
                f"{existing_knowledge.get('schema_version')}"
            )

            print(
                "Mode:                 "
                "REBUILD"
            )

            print(
                f"Samples to rebuild:   "
                f"{len(pending)}"
            )

        else:

            already_learned = (
                len(
                    sample_dirs
                )
                - len(
                    pending
                )
            )

            print(
                f"Already learned:    "
                f"{already_learned}"
            )

            print(
                f"New samples:        "
                f"{len(pending)}"
            )

        print()

        added = 0
        failed = 0

        # ----------------------------------------------------
        # Process only pending samples.
        # ----------------------------------------------------

        for (
            sample_dir,
            sample_id,
        ) in pending:

            try:

                result = (
                    self.learn_sample(
                        sample_dir,
                        knowledge=knowledge,
                    )
                )

                if result[
                    "added"
                ]:

                    added += 1

                    print(
                        f"{sample_id:<20}"
                        "OK"
                    )

                else:

                    print(
                        f"{sample_id:<20}"
                        "SKIPPED"
                    )

            except Exception as exc:

                failed += 1

                print(
                    f"{sample_id:<20}"
                    f"ERROR: {exc}"
                )

        # ----------------------------------------------------
        # Save ONE time at the end.
        #
        # This avoids repeatedly writing a potentially large
        # Knowledge file for every sample.
        # ----------------------------------------------------

        self._save_reference_knowledge(
            knowledge
        )

        print()

        print(
            f"Knowledge samples: "
            f"{knowledge.get('sample_count', 0)}"
        )

        print(
            "Knowledge file:    "
            f"{self.reference_knowledge_file}"
        )

        print(
            f"Processed:         "
            f"{len(pending)}"
        )

        print(
            f"Added:             "
            f"{added}"
        )

        if failed:

            print(
                f"Failed:            "
                f"{failed}"
            )

        print(
            "ONLINE REFERENCE LEARNING COMPLETE"
        )

        return {
            "discovered": len(
                sample_dirs
            ),
            "rebuild": rebuild,
            "processed": len(
                pending
            ),
            "added": added,
            "failed": failed,
            "sample_count": (
                knowledge.get(
                    "sample_count",
                    0,
                )
            ),
            "knowledge_file": str(
                self.reference_knowledge_file
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

        image = Image.new(
            "RGB",
            (
                GENERATION_CANVAS_WIDTH,
                GENERATION_CANVAS_HEIGHT,
            ),
            "white",
        )

        draw = ImageDraw.Draw(
            image
        )

        all_points = [
            point
            for stroke in strokes
            for point in stroke
        ]

        if not all_points:

            raise ValueError(
                "Cannot render empty candidate."
            )

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

        width = max(
            max_x - min_x,
            0.001,
        )

        height = max(
            max_y - min_y,
            0.001,
        )

        available_width = (
            GENERATION_CANVAS_WIDTH
            - 2
            * GENERATION_MARGIN
        )

        available_height = (
            GENERATION_CANVAS_HEIGHT
            - 2
            * GENERATION_MARGIN
        )

        scale = min(
            available_width / width,
            available_height / height,
        )

        for stroke in strokes:

            if len(stroke) < 2:
                continue

            rendered = []

            for point in stroke:

                x = (
                    GENERATION_MARGIN
                    + (
                        point["x"]
                        - min_x
                    )
                    * scale
                )

                y = (
                    GENERATION_MARGIN
                    + (
                        point["y"]
                        - min_y
                    )
                    * scale
                )

                rendered.append(
                    (
                        int(x),
                        int(y),
                    )
                )

            if len(rendered) >= 2:

                draw.line(
                    rendered,
                    width=GENERATION_STROKE_WIDTH,
                    joint="curve",
                )

        label = (
            "STYLE EVALUATION — "
            "NOT FOR SIGNING"
        )

        draw.text(
            (
                25,
                GENERATION_CANVAS_HEIGHT - 35,
            ),
            label,
        )

        metadata = (
            f"Candidate {candidate_id:03d} | "
            f"Source {source_sample_id}"
        )

        draw.text(
            (
                25,
                15,
            ),
            metadata,
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image.save(
            output_path,
            format="PNG",
        )

    # --------------------------------------------------------
    # Generate ONE candidate
    # --------------------------------------------------------

    def _generate_candidate(
        self,
        sample_dirs: list[Path],
        rng: random.Random,
        candidate_id: int,
        output_dir: Path,
    ) -> dict[str, Any]:

        source_dir = (
            self._select_generation_sample(
                sample_dirs,
                rng,
            )
        )

        source = (
            self._load_generation_sample(
                source_dir
            )
        )

        normalized = (
            self._normalize_generation_strokes(
                source["strokes"]
            )
        )

        varied = (
            self._vary_generation_strokes(
                normalized,
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
            varied,
            output_path,
            candidate_id,
            source["sample_id"],
        )

        return {
            "candidate_id": candidate_id,
            "source_sample_id": (
                source["sample_id"]
            ),
            "source_sample_path": str(
                source_dir
            ),
            "output": str(
                output_path
            ),
            "stroke_count": len(
                varied
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
                        sample_dirs,
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


if __name__ == "__main__":
    main()