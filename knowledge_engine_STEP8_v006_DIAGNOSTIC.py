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
import math

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
    # STEP 8 — ITERATIVE TRAJECTORY STYLE LEARNING
    # ========================================================
    # Integrated into the existing Knowledge Engine.
    # Frozen references 001..025; equal weight 1/25.
    # No video, random points, generated samples, MODEL v001,
    # or Sample 026 are used/created.
    # ========================================================

    STEP8_VERSION = "0.1"
    DEFAULT_CYCLE_REPORT = (
        Path("online_training_data") / "reference_learning"
        / "CYCLE_v0.1" / "cycle_report.json"
    )
    DEFAULT_STEP8_REPORT = (
        Path("online_training_data") / "reference_learning"
        / "STEP8_ITERATIVE_LEARNING_v0.1.json"
    )

    def _step8_load_cycle_report(self) -> dict[str, Any]:
        if not self.DEFAULT_CYCLE_REPORT.exists():
            return {}
        try:
            with open(self.DEFAULT_CYCLE_REPORT, "r", encoding="utf-8") as f:
                value = json.load(f)
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _step8_reference_rows(self) -> list[dict[str, Any]]:
        evaluation = self._load_trajectory_evaluation()
        raw = self._extract_trajectory_evaluation_samples(evaluation)
        rows = []
        for item in raw:
            sid = self._trajectory_sample_id(item)
            if sid is not None and self.REFERENCE_FIRST <= sid <= self.REFERENCE_LAST:
                row = dict(item)
                row["_sample_id"] = sid
                rows.append(row)

        rows.sort(key=lambda x: x["_sample_id"])
        expected = list(range(1, self.REFERENCE_COUNT + 1))
        actual = [x["_sample_id"] for x in rows]
        if actual != expected:
            raise ValueError(
                "STEP 8 requires complete frozen references 001..025. "
                f"Found: {actual}"
            )
        return rows

    @classmethod
    def _step8_flat_features(cls, row: dict[str, Any]) -> dict[str, float]:
        return cls._flatten_trajectory_numeric(
            {k: v for k, v in row.items() if k != "_sample_id"}
        )

    @classmethod
    def _step8_statistics(cls, rows):
        observations: dict[str, list[float]] = {}

        for row in rows:
            for key, value in cls._step8_flat_features(row).items():
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError(
                        f"STEP 8 found non-finite feature value: {key}={value}"
                    )
                observations.setdefault(key, []).append(value)

        stats = {}

        for key, values in observations.items():
            n = len(values)
            mean = sum(values) / n

            ordered = sorted(values)
            mid = n // 2
            median = (
                ordered[mid]
                if n % 2
                else (ordered[mid - 1] + ordered[mid]) / 2.0
            )

            deviations = sorted(abs(v - median) for v in values)
            mad_mid = n // 2
            mad = (
                deviations[mad_mid]
                if n % 2
                else (deviations[mad_mid - 1] + deviations[mad_mid]) / 2.0
            )

            variance = sum((v - mean) ** 2 for v in values) / n
            std = math.sqrt(max(variance, 0.0))
            robust_scale = mad * 1.4826
            scale = max(std, robust_scale, 1e-9)

            stats[key] = {
                "mean": mean,
                "median": median,
                "std": std,
                "mad": mad,
                "scale": scale,
                "min": min(values),
                "max": max(values),
                "observations": n,
                "learnable": std > 1e-9 or robust_scale > 1e-9,
            }

        return observations, stats

    @classmethod
    def _step8_standardized_rows(cls, rows, stats):
        standardized = []

        for row in rows:
            flat = cls._step8_flat_features(row)
            zrow = {}

            for key, value in flat.items():
                info = stats[key]
                zrow[key] = (
                    (value - info["mean"]) / info["scale"]
                    if info["learnable"]
                    else 0.0
                )

            standardized.append(zrow)

        return standardized

    @classmethod
    def _step8_reconstruction_loss(
        cls,
        standardized_rows,
        prototype,
    ) -> float:
        """
        Equal-weight reconstruction loss in normalized trajectory space.

        This is deliberately separate from CYCLE v0.1's loss. It measures
        how well the learned style representation explains the 25 frozen
        reference trajectories.
        """
        if not standardized_rows:
            return 0.0

        losses = []

        for row in standardized_rows:
            errors = [
                (value - prototype[key]) ** 2
                for key, value in row.items()
            ]
            losses.append(
                sum(errors) / len(errors) if errors else 0.0
            )

        return sum(losses) / len(losses)

    @classmethod
    def _step8_feature_weights(cls, standardized_rows):
        """
        Equal reference weighting is preserved. Feature weights are only
        used to prevent a large number of repeated indexed fields from
        dominating the style representation.
        """
        counts = {}

        for row in standardized_rows:
            for key in row:
                root = key.split("[", 1)[0]
                counts[root] = counts.get(root, 0) + 1

        weights = {}
        for row in standardized_rows:
            for key in row:
                root = key.split("[", 1)[0]
                weights[key] = 1.0 / max(counts.get(root, 1), 1)

        return weights

    def _run_step8_iterative_learning(
        self,
        *,
        max_iterations=250,
        learning_rate=0.20,
        tolerance=1e-8,
        stable_iterations=8,
    ):
        if self.REFERENCE_COUNT != 25:
            raise ValueError("STEP 8 requires exactly 25 frozen references.")

        rows = self._step8_reference_rows()
        observations, stats = self._step8_statistics(rows)
        standardized_rows = self._step8_standardized_rows(rows, stats)
        feature_weights = self._step8_feature_weights(standardized_rows)

        learnable_keys = [
            key
            for key, info in stats.items()
            if info["learnable"]
        ]

        if not learnable_keys:
            raise RuntimeError(
                "STEP 8 found no learnable trajectory features."
            )

        # Start from the neutral style point, not the answer itself.
        # This makes the iteration measurable rather than a one-step mean
        # assignment.
        prototype = {key: 0.0 for key in learnable_keys}

        def loss_for(candidate):
            losses = []

            for row in standardized_rows:
                weighted_errors = []
                total_weight = 0.0

                for key in learnable_keys:
                    weight = feature_weights.get(key, 1.0)
                    error = row.get(key, 0.0) - candidate[key]
                    weighted_errors.append(weight * error * error)
                    total_weight += weight

                losses.append(
                    sum(weighted_errors) / total_weight
                    if total_weight
                    else 0.0
                )

            # Exactly equal weight for all 25 references.
            return sum(losses) / len(losses)

        initial_loss = loss_for(prototype)
        if not math.isfinite(initial_loss):
            raise RuntimeError("STEP 8 initial loss is non-finite.")

        history = []
        previous_loss = initial_loss
        current_lr = float(learning_rate)
        stable_count = 0
        converged = False

        for iteration in range(1, max_iterations + 1):
            gradients = {}

            # Exact gradient of the normalized reconstruction objective.
            for key in learnable_keys:
                numerator = 0.0
                denominator = 0.0

                for row in standardized_rows:
                    weight = feature_weights.get(key, 1.0)
                    numerator += weight * (
                        prototype[key] - row.get(key, 0.0)
                    )
                    denominator += weight

                gradients[key] = (
                    2.0 * numerator / denominator
                    if denominator
                    else 0.0
                )

            accepted = False
            trial_lr = current_lr
            candidate_loss = float("nan")
            update_sq = 0.0

            for _ in range(24):
                candidate = {
                    key: prototype[key] - trial_lr * gradients[key]
                    for key in learnable_keys
                }

                candidate_loss = loss_for(candidate)
                update_sq = sum(
                    (candidate[key] - prototype[key]) ** 2
                    for key in learnable_keys
                )

                if math.isfinite(candidate_loss) and (
                    candidate_loss <= previous_loss + 1e-15
                ):
                    prototype = candidate
                    current_loss = candidate_loss
                    accepted = True
                    break

                trial_lr *= 0.5

            if not accepted:
                current_loss = previous_loss
                stable_count += 1
            else:
                delta = previous_loss - current_loss

                if abs(delta) <= tolerance:
                    stable_count += 1
                else:
                    stable_count = 0

                current_lr = min(max(trial_lr * 1.05, 1e-6), 0.5)

            gradient_values = list(gradients.values())
            gradient_abs = [abs(v) for v in gradient_values] or [0.0]

            history.append({
                "iteration": iteration,
                "loss": current_loss,
                "delta": previous_loss - current_loss,
                "learning_rate": trial_lr,
                "accepted": accepted,
                "stable_count": stable_count,

                # STEP 8 diagnostic trace; does not participate in learning.
                "diagnostic": {
                    "gradient_mean": (
                        sum(gradient_values) / len(gradient_values)
                        if gradient_values else 0.0
                    ),
                    "gradient_abs_max": max(gradient_abs),
                    "gradient_abs_min": min(gradient_abs),
                    "update_norm": math.sqrt(max(update_sq, 0.0)),
                    "candidate_loss": candidate_loss,
                    "loss_changed": abs(
                        current_loss - previous_loss
                    ) > 1e-15,
                },
            })

            previous_loss = current_loss

            if stable_count >= stable_iterations:
                converged = True
                break

        final_loss = loss_for(prototype)

        if not math.isfinite(final_loss):
            raise RuntimeError(
                "STEP 8 ended with non-finite loss; result rejected."
            )

        learned_profile = {}
        for key, info in stats.items():
            if info["learnable"]:
                learned_profile[key] = (
                    info["mean"]
                    + prototype[key] * info["scale"]
                )
            else:
                learned_profile[key] = info["mean"]

        baseline = (
            self._step8_load_cycle_report()
            .get("loss", {})
            .get("weighted_total_loss")
        )

        return {
            "version": "0.3-diagnostic",
            "type": "trajectory_style_iterative_learning",
            "status": {
                "complete": True,
                "converged": converged,
                "reference_complete": True,
                "reference_count": 25,
                "equal_weight": True,
                "weight_per_reference": 0.04,
                "video_used": False,
                "random_points_used": False,
                "generated_samples_used": False,
                "reference_samples_modified": False,
                "model_v001": False,
                "sample_026_created": False,
                "finite_loss": True,
                "monotonic_non_increasing_loss": all(
                    history[i]["loss"] <= history[i - 1]["loss"] + 1e-15
                    for i in range(1, len(history))
                ),
            },
            "reference_policy": {
                "first": 1,
                "last": 25,
                "count": 25,
                "weight_per_reference": 0.04,
                "priority_policy": "none",
                "all_references_equal": True,
            },
            "learning_policy": {
                "objective": "equal_weight_standardized_trajectory_style_reconstruction",
                "optimizer": "deterministic_gradient_descent_with_backtracking",
                "initial_learning_rate": learning_rate,
                "max_iterations": max_iterations,
                "tolerance": tolerance,
                "required_stable_iterations": stable_iterations,
                "feature_count_total": len(stats),
                "feature_count_learnable": len(learnable_keys),
                "constant_features_excluded_from_optimization": (
                    len(stats) - len(learnable_keys)
                ),
                "normalization": "mean_centered_robust_scale",
                "reference_weighting": "exactly_equal_1_over_25",
                "feature_repetition_control": "root_feature_balancing",
            },
            "cycle_v0_1_baseline": {
                "loss": baseline,
                "not_directly_comparable": True,
                "reason": (
                    "CYCLE v0.1 and STEP 8 use different loss spaces."
                ),
            },
            "iteration": {
                "iterations_run": len(history),
                "initial_normalized_loss": initial_loss,
                "final_normalized_loss": final_loss,
                "improvement": initial_loss - final_loss,
                "relative_improvement": (
                    (initial_loss - final_loss) / initial_loss
                    if initial_loss
                    else 0.0
                ),
                "history": history,
            },
            "learned_style": {
                "representation": "trajectory_style_prototype_v0.3",
                "learned_profile": learned_profile,
                "feature_statistics": stats,
                "feature_weights": feature_weights,
                "learnable_features": {
                    key: stats[key]["learnable"]
                    for key in stats
                },
                "feature_observation_counts": {
                    key: len(values)
                    for key, values in observations.items()
                },
            },
            "generation_policy": {
                "generation_ready": False,
                "new_name_generation": False,
                "model_version": None,
            },
            "important_note": (
                "STEP 8 v0.3 learns a deterministic trajectory STYLE "
                "representation from the 25 frozen references. It does not "
                "claim to be a generative signature model, does not use "
                "video or random points, and must not create Sample 026."
            ),
        }

    def run_step8(self, output_file=DEFAULT_STEP8_REPORT, **kwargs):
        result = self._run_step8_iterative_learning(**kwargs)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result

    @staticmethod
    def print_step8_report(result):
        s = result["status"]
        i = result["iteration"]
        print("=" * 60)
        print("SIGNATURE MACHINE — STEP 8")
        print("ITERATIVE TRAJECTORY STYLE LEARNING")
        print("=" * 60)
        print("Reference set: 001..025")
        print(f"Reference count: {s['reference_count']}")
        print(f"Equal weight: {s['weight_per_reference']}")
        print(f"Iterations: {i['iterations_run']}")
        print(f"Initial normalized loss: {i['initial_normalized_loss']}")
        print(f"Final normalized loss: {i['final_normalized_loss']}")
        print(f"Converged: {s['converged']}")
        print(f"CYCLE v0.1 baseline loss: {result['cycle_v0_1_baseline']['loss']}")
        print(f"Video used: {s['video_used']}")
        print(f"Random points: {s['random_points_used']}")
        print(f"MODEL v001 created: {s['model_v001']}")
        print(f"Sample 026 created: {s['sample_026_created']}")
        print("STEP 8: STYLE REPRESENTATION LEARNING COMPLETE")

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

    import sys

    engine = SignatureKnowledgeEngine(
        "signature_knowledge.json"
    )

    if len(sys.argv) > 1 and sys.argv[1].upper() == "STEP8":
        result = engine.run_step8(max_iterations=250, learning_rate=0.20, tolerance=1e-8, stable_iterations=8)
        engine.print_step8_report(result)

        print()
        print("STEP 8 DIAGNOSTIC TRACE")
        print("-" * 60)
        iteration_data = result.get("iteration", {})
        history = iteration_data.get("history", [])

        for item in history[:10]:
            diag = item.get("diagnostic", {})
            print(
                f"Iteration {item.get('iteration')}: "
                f"loss={item.get('loss')} "
                f"delta={item.get('delta')} "
                f"accepted={item.get('accepted')} "
                f"lr={item.get('learning_rate')}"
            )
            print(
                f"  gradient_mean={diag.get('gradient_mean')} "
                f"gradient_abs_max={diag.get('gradient_abs_max')} "
                f"update_norm={diag.get('update_norm')}"
            )
            print(
                f"  candidate_loss={diag.get('candidate_loss')} "
                f"loss_changed={diag.get('loss_changed')}"
            )
    else:
        result = engine.save(
            "signature_unified_knowledge.json"
        )

        engine.print_report(
            result
        )
