# -*- coding: utf-8 -*-

"""
Signature Machine
Knowledge Engine

مسئولیت‌ها:
1. خواندن signature_knowledge.json
2. استخراج دانش سطحی
3. استخراج Deep Knowledge از samples
4. یکپارچه‌سازی دانش
5. ساخت Design Profile
6. ذخیره Knowledge نهایی
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SignatureKnowledgeEngine:

    VERSION = "1.2"
    TRAJECTORY_KNOWLEDGE_VERSION = "0.1"
    REFERENCE_FIRST = 1
    REFERENCE_LAST = 25
    REFERENCE_COUNT = 25
    REFERENCE_WEIGHT = 1.0 / REFERENCE_COUNT
    DEFAULT_TRAJECTORY_EVALUATION = (
        Path("online_training_data")
        / "reference_learning"
        / "TRAJECTORY_EVALUATION_v0.1.json"
    )

    def __init__(
        self,
        knowledge_file: str | Path = "signature_knowledge.json",
        trajectory_evaluation_file: str | Path | None = None,
    ):
        self.knowledge_file = Path(
            knowledge_file
        )

        self.trajectory_evaluation_file = Path(
            trajectory_evaluation_file
            if trajectory_evaluation_file is not None
            else self.DEFAULT_TRAJECTORY_EVALUATION
        )

        self.data: dict[str, Any] = {}

        self.samples: list[dict] = []

        self.approved_samples: list = []

        self.surface_knowledge: dict = {}

        self.trajectory_evaluation: dict[str, Any] = {}

        self.trajectory_knowledge: dict[str, Any] = {}

    # ========================================================
    # LOAD
    # ========================================================

    def load(self) -> dict:

        if not self.knowledge_file.exists():

            raise FileNotFoundError(
                f"Knowledge file not found: "
                f"{self.knowledge_file}"
            )

        with open(
            self.knowledge_file,
            "r",
            encoding="utf-8",
        ) as file:

            self.data = json.load(file)

        self.samples = self.data.get(
            "samples",
            [],
        )

        self.approved_samples = self.data.get(
            "approved_samples",
            [],
        )

        self.surface_knowledge = self.data.get(
            "knowledge",
            {},
        )

        return self.data

    # ========================================================
    # DEEP KNOWLEDGE
    # ========================================================

    def _extract_deep_knowledge(self) -> dict:
         """
         استخراج Deep Knowledge از خروجی مستقیم
         visual_analyzer.py
         """

         deep_samples = self.data.get(
            "deep_visual_analysis",
            [],
        )

         if not isinstance(
            deep_samples,
            list,
         ):
            deep_samples = []

         curvature_values = []
         direction_values = []
         path_values = []

         for sample in deep_samples:

            if not isinstance(sample, dict):
                continue

            curvature = sample.get(
                "curvature",
                {},
            )

            direction = sample.get(
                "direction",
                {},
            )

            if isinstance(curvature, dict):

                value = curvature.get(
                    "curvature_proxy"
                )

                if isinstance(
                    value,
                    (int, float),
                ):
                    curvature_values.append(
                        value
                    )

                value = curvature.get(
                    "path_length_proxy"
                )

                if isinstance(
                    value,
                    (int, float),
                ):
                    path_values.append(
                        value
                    )

            if isinstance(direction, dict):

                value = direction.get(
                    "directional_variation"
                )

                if isinstance(
                    value,
                    (int, float),
                ):
                    direction_values.append(
                        value
                    )

         sample_count = len(
            deep_samples
        )

         def average(
            values: list[float],
        ) -> float:

            if not values:
                return 0.0

            return round(
                sum(values) / len(values),
                6,
            )

         return {
            "sample_count": sample_count,

            "average_curvature":
                average(
                    curvature_values
                ),

            "average_directional_variation":
                average(
                    direction_values
                ),

            "average_path_length":
                average(
                    path_values
                ),
        }

    
    # ========================================================
    # TRAJECTORY KNOWLEDGE
    # STEP 6 — integrated into the existing Knowledge Engine
    # ========================================================

    @staticmethod
    def _trajectory_numeric(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _trajectory_sample_id(sample: dict[str, Any]) -> int | None:
        value = sample.get("sample_id", sample.get("id"))
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(c for c in value if c.isdigit())
            if digits:
                try:
                    return int(digits)
                except ValueError:
                    return None
        return None

    @classmethod
    def _flatten_trajectory_numeric(
        cls,
        value: Any,
        prefix: str = "",
    ) -> dict[str, float]:
        result: dict[str, float] = {}

        number = cls._trajectory_numeric(value)
        if number is not None:
            if prefix:
                result[prefix] = number
            return result

        if isinstance(value, dict):
            for key, child in value.items():
                child_prefix = (
                    f"{prefix}.{key}" if prefix else str(key)
                )
                result.update(
                    cls._flatten_trajectory_numeric(
                        child, child_prefix
                    )
                )
            return result

        if isinstance(value, list):
            for index, child in enumerate(value):
                child_prefix = (
                    f"{prefix}[{index}]"
                    if prefix else f"[{index}]"
                )
                result.update(
                    cls._flatten_trajectory_numeric(
                        child, child_prefix
                    )
                )

        return result

    @classmethod
    def _trajectory_feature_profile(
        cls,
        samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Equal-weight aggregation.
        Every reference sample has weight exactly 1/25.
        Missing values are not converted to zero.
        """
        observations: dict[str, list[float]] = {}

        for sample in samples:
            flat = cls._flatten_trajectory_numeric(sample)
            for key, value in flat.items():
                observations.setdefault(key, []).append(value)

        profile: dict[str, Any] = {}

        for key, values in sorted(observations.items()):
            if not values:
                continue

            profile[key] = {
                "mean": sum(values) / len(values),
                "observations": len(values),
                "reference_count": len(samples),
                "weight_per_reference": cls.REFERENCE_WEIGHT,
            }

        return profile

    def _load_trajectory_evaluation(self) -> dict[str, Any]:
        if not self.trajectory_evaluation_file.exists():
            return {}

        with open(
            self.trajectory_evaluation_file,
            "r",
            encoding="utf-8",
        ) as file:
            value = json.load(file)

        return value if isinstance(value, dict) else {}

    def _extract_trajectory_evaluation_samples(
        self,
        evaluation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        for key in (
            "samples",
            "evaluations",
            "trajectories",
            "results",
        ):
            value = evaluation.get(key)
            if isinstance(value, list):
                return [
                    item for item in value
                    if isinstance(item, dict)
                ]
        return []

    def _build_trajectory_knowledge(self) -> dict[str, Any]:
        """
        Build trajectory/style knowledge from the existing evaluator
        output.

        This does NOT:
        - create a new engine,
        - use MP4/video,
        - create random points,
        - modify samples 001..025,
        - create MODEL v001,
        - create Sample 026.
        """
        evaluation = self._load_trajectory_evaluation()
        self.trajectory_evaluation = evaluation

        raw_samples = (
            self._extract_trajectory_evaluation_samples(
                evaluation
            )
        )

        selected: list[dict[str, Any]] = []

        for sample in raw_samples:
            sample_id = self._trajectory_sample_id(sample)
            if sample_id is None:
                continue
            if (
                self.REFERENCE_FIRST
                <= sample_id
                <= self.REFERENCE_LAST
            ):
                selected.append(sample)

        selected.sort(
            key=lambda item:
                self._trajectory_sample_id(item) or 0
        )

        ids = [
            self._trajectory_sample_id(sample)
            for sample in selected
        ]

        complete = ids == list(
            range(
                self.REFERENCE_FIRST,
                self.REFERENCE_LAST + 1,
            )
        )

        return {
            "version": self.TRAJECTORY_KNOWLEDGE_VERSION,
            "type": "trajectory_style_knowledge",
            "status": {
                "available": bool(selected),
                "reference_complete": complete,
                "reference_count": len(selected),
                "expected_reference_count":
                    self.REFERENCE_COUNT,
                "equal_weight": True,
                "weight_per_reference":
                    self.REFERENCE_WEIGHT,
                "priority_policy": "none",
                "source": str(
                    self.trajectory_evaluation_file
                ),
                "video_used": False,
                "random_points_used": False,
                "generated_samples_used": False,
                "reference_samples_modified": False,
                "model_v001": False,
                "sample_026_created": False,
            },
            "reference_samples": ids,
            "features": self._trajectory_feature_profile(
                selected
            ),
            "learning_policy": {
                "method":
                    "equal_weight_reference_aggregation",
                "weight_per_sample":
                    self.REFERENCE_WEIGHT,
                "samples_have_priority": False,
                "baseline_cycle": "CYCLE_v0.1",
                "baseline_loss":
                    0.3243999843612536,
            },
            "generation_policy": {
                "generation_ready": False,
                "new_name_generation": False,
                "model_version": None,
            },
        }

    # ========================================================
    # DESIGN PROFILE
    # ========================================================

    def build_design_profile(
        self,
        deep: dict,
    ) -> dict:

        average = self.surface_knowledge.get(
            "average",
            {},
        )

        return {
            "sample_count": len(
                self.samples
            ),

            "aspect_ratio": average.get(
                "aspect_ratio",
                0.0,
            ),

            "content_aspect_ratio": average.get(
                "content_aspect_ratio",
                0.0,
            ),

            "bbox_fill_ratio": average.get(
                "bbox_fill_ratio",
                0.0,
            ),

            "ink_density": average.get(
                "ink_density",
                0.0,
            ),

            "left_margin": average.get(
                "left_margin",
                0.0,
            ),

            "right_margin": average.get(
                "right_margin",
                0.0,
            ),

            "top_margin": average.get(
                "top_margin",
                0.0,
            ),

            "bottom_margin": average.get(
                "bottom_margin",
                0.0,
            ),

            "deep": {
                "average_curvature":
                    deep.get(
                        "average_curvature",
                        0.0,
                    ),

                "average_directional_variation":
                    deep.get(
                        "average_directional_variation",
                        0.0,
                    ),

                "average_path_length":
                    deep.get(
                        "average_path_length",
                        0.0,
                    ),
            },
        }

    # ========================================================
    # BUILD
    # ========================================================

    def build(self) -> dict:

        if not self.data:
            self.load()

        deep = self._extract_deep_knowledge()

        deep_available = (
            deep["sample_count"] > 0
        )

        design_profile = (
            self.build_design_profile(
                deep
            )
        )

        trajectory = self._build_trajectory_knowledge()

        source = self.data.get(
            "source",
            {},
        )

        result = {
            "version": self.VERSION,

            "type":
                "signature_unified_knowledge",

            "source":
                source,

            "status": {
                "surface_knowledge": True,

                "deep_knowledge":
                    deep_available,

                "trajectory_knowledge":
                    trajectory.get("status", {}).get(
                        "available",
                        False,
                    ),

                "sample_count":
                    len(self.samples),
            },

            "design_profile":
                design_profile,

            "surface_knowledge":
                self.surface_knowledge,

            "deep_knowledge":
                deep,

            "trajectory_knowledge":
                trajectory,

            "samples":
                self.samples,

            "approved_samples":
                self.approved_samples,

            "failed":
                self.data.get(
                    "failed",
                    [],
                ),
        }

        return result

    # ========================================================
    # SAVE
    # ========================================================

    def save(
        self,
        output_file: str | Path =
            "signature_unified_knowledge.json",
    ) -> dict:

        output_file = Path(
            output_file
        )

        result = self.build()

        with open(
            output_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2,
            )

        return result

    # ========================================================
    # REPORT
    # ========================================================

    def print_report(
        self,
        result: dict,
    ) -> None:

        status = result.get(
            "status",
            {},
        )

        profile = result.get(
            "design_profile",
            {},
        )

        deep = result.get(
            "deep_knowledge",
            {},
        )

        trajectory = result.get(
            "trajectory_knowledge",
            {},
        )

        trajectory_status = trajectory.get(
            "status",
            {},
        )

        print()
        print("=" * 60)
        print("SIGNATURE KNOWLEDGE ENGINE")
        print("=" * 60)
        print()

        print(
            f"Version: "
            f"{result.get('version')}"
        )

        print(
            f"Samples: "
            f"{status.get('sample_count', 0)}"
        )

        print(
            f"Failed: "
            f"{len(result.get('failed', []))}"
        )

        print(
            f"Approved: "
            f"{len(result.get('approved_samples', []))}"
        )

        print(
            f"Deep knowledge: "
            f"{status.get('deep_knowledge', False)}"
        )

        print(
            f"Trajectory knowledge: "
            f"{status.get('trajectory_knowledge', False)}"
        )

        if trajectory_status:
            print(
                f"Trajectory references: "
                f"{trajectory_status.get('reference_count', 0)}"
            )
            print(
                f"Trajectory equal weight: "
                f"{trajectory_status.get('equal_weight', False)}"
            )
            print(
                f"Trajectory weight/sample: "
                f"{trajectory_status.get('weight_per_reference')}"
            )
            print(
                f"Trajectory video used: "
                f"{trajectory_status.get('video_used', False)}"
            )
            print(
                f"Trajectory random points: "
                f"{trajectory_status.get('random_points_used', False)}"
            )

        print()
        print("Design profile:")

        print(
            json.dumps(
                profile,
                ensure_ascii=False,
                indent=2,
            )
        )

        print()
        print("Deep knowledge:")

        print(
            json.dumps(
                deep,
                ensure_ascii=False,
                indent=2,
            )
        )

        print()
        print(
            "KNOWLEDGE ENGINE: OK"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    engine = SignatureKnowledgeEngine(
        "signature_knowledge.json"
    )

    result = engine.save(
        "signature_unified_knowledge.json"
    )

    engine.print_report(
        result
    )