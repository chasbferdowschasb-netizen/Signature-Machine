# -*- coding: utf-8 -*-

"""
Signature Machine
Generation Evaluator v0.1

مسئولیت‌ها:
1. بررسی خروجی Generation
2. استخراج ویژگی‌های بصری از Signature تولیدشده
3. مقایسه با Design Profile
4. محاسبه فاصله و Score
5. تولید Evaluation Report

این موتور:
- Dataset اصلی را تغییر نمی‌دهد.
- Knowledge را تغییر نمی‌دهد.
- فقط خروجی تولیدشده را ارزیابی می‌کند.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PIL import Image


class SignatureGenerationEvaluator:

    VERSION = "0.1"

    def __init__(
        self,
        knowledge_file: str | Path = (
            "signature_unified_knowledge.json"
        ),
        generated_file: str | Path = (
            "generated_signature.png"
        ),
        report_file: str | Path = (
            "generation_evaluation.json"
        ),
    ) -> None:

        self.knowledge_file = Path(
            knowledge_file
        )

        self.generated_file = Path(
            generated_file
        )

        self.report_file = Path(
            report_file
        )

        self.knowledge: dict[str, Any] = {}

        self.profile: dict[str, Any] = {}

    # ========================================================
    # LOAD KNOWLEDGE
    # ========================================================

    def load_knowledge(self) -> None:

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

            self.knowledge = json.load(file)

        self.profile = self.knowledge.get(
            "design_profile",
            {},
        )

    # ========================================================
    # IMAGE FEATURES
    # ========================================================

    @staticmethod
    def analyze_image(
        image_path: Path,
    ) -> dict[str, Any]:

        if not image_path.exists():

            raise FileNotFoundError(
                f"Generated image not found: "
                f"{image_path}"
            )

        with Image.open(
            image_path
        ) as image:

            rgba = image.convert(
                "RGBA"
            )

            width, height = rgba.size

            pixels = list(
                rgba.getdata()
            )

        total = len(pixels)

        visible = []

        for pixel in pixels:

            r, g, b, a = pixel

            luminance = (
                0.299 * r
                + 0.587 * g
                + 0.114 * b
            )

            if a > 10 and luminance < 180:

                visible.append(
                    pixel
                )

        ink_pixels = len(
            visible
        )

        if not ink_pixels:

            return {
                "width": width,
                "height": height,
                "aspect_ratio": (
                    width / max(height, 1)
                ),
                "ink_density": 0.0,
                "content_aspect_ratio": 0.0,
                "bbox_fill_ratio": 0.0,
                "left_margin": 1.0,
                "right_margin": 1.0,
                "top_margin": 1.0,
                "bottom_margin": 1.0,
            }

        xs = []
        ys = []

        for index, pixel in enumerate(
            pixels
        ):

            r, g, b, a = pixel

            luminance = (
                0.299 * r
                + 0.587 * g
                + 0.114 * b
            )

            if a > 10 and luminance < 180:

                xs.append(
                    index % width
                )

                ys.append(
                    index // width
                )

        min_x = min(xs)
        max_x = max(xs)

        min_y = min(ys)
        max_y = max(ys)

        content_width = (
            max_x - min_x + 1
        )

        content_height = (
            max_y - min_y + 1
        )

        bbox_area = (
            content_width
            * content_height
        )

        return {
            "width": width,

            "height": height,

            "aspect_ratio": round(
                width / max(
                    height,
                    1,
                ),
                6,
            ),

            "ink_density": round(
                ink_pixels / max(
                    total,
                    1,
                ),
                6,
            ),

            "content_aspect_ratio": round(
                content_width / max(
                    content_height,
                    1,
                ),
                6,
            ),

            "bbox_fill_ratio": round(
                ink_pixels / max(
                    bbox_area,
                    1,
                ),
                6,
            ),

            "left_margin": round(
                min_x / max(
                    width,
                    1,
                ),
                6,
            ),

            "right_margin": round(
                (
                    width
                    - max_x
                    - 1
                )
                / max(
                    width,
                    1,
                ),
                6,
            ),

            "top_margin": round(
                min_y / max(
                    height,
                    1,
                ),
                6,
            ),

            "bottom_margin": round(
                (
                    height
                    - max_y
                    - 1
                )
                / max(
                    height,
                    1,
                ),
                6,
            ),
        }

    # ========================================================
    # DISTANCE
    # ========================================================

    @staticmethod
    def normalized_difference(
        actual: float,
        target: float,
    ) -> float:

        denominator = max(
            abs(target),
            0.000001,
        )

        difference = abs(
            actual - target
        ) / denominator

        return min(
            difference,
            1.0,
        )

    # ========================================================
    # FEATURE COMPARISON
    # ========================================================

    def compare_features(
        self,
        actual: dict[str, Any],
    ) -> dict[str, Any]:

        average = self.profile.get(
            "average",
            {},
        )

        feature_names = [
            "aspect_ratio",
            "content_aspect_ratio",
            "bbox_fill_ratio",
            "ink_density",
            "left_margin",
            "right_margin",
            "top_margin",
            "bottom_margin",
        ]

        differences = {}

        for name in feature_names:

            target = float(
                average.get(
                    name,
                    0.0,
                )
            )

            value = float(
                actual.get(
                    name,
                    0.0,
                )
            )

            differences[name] = round(
                self.normalized_difference(
                    value,
                    target,
                ),
                6,
            )

        average_difference = (
            sum(
                differences.values()
            )
            / max(
                len(differences),
                1,
            )
        )

        score = (
            1.0
            - average_difference
        )

        return {
            "differences": differences,

            "average_difference": round(
                average_difference,
                6,
            ),

            "score": round(
                score * 100.0,
                2,
            ),
        }

    # ========================================================
    # STRUCTURAL SCORE
    # ========================================================

    def structural_score(
        self,
        actual: dict[str, Any],
    ) -> float:

        checks = []

        width = actual.get(
            "width",
            0,
        )

        height = actual.get(
            "height",
            0,
        )

        if width > 0 and height > 0:
            checks.append(1.0)

        if actual.get(
            "ink_density",
            0.0,
        ) > 0:
            checks.append(1.0)

        if actual.get(
            "bbox_fill_ratio",
            0.0,
        ) > 0:
            checks.append(1.0)

        if not checks:
            return 0.0

        return round(
            (
                sum(checks)
                / len(checks)
            )
            * 100.0,
            2,
        )

    # ========================================================
    # FINAL SCORE
    # ========================================================

    def calculate_final_score(
        self,
        feature_score: float,
        structural_score: float,
    ) -> float:

        score = (
            feature_score * 0.85
            + structural_score * 0.15
        )

        return round(
            max(
                0.0,
                min(
                    score,
                    100.0,
                ),
            ),
            2,
        )

    # ========================================================
    # EVALUATE
    # ========================================================

    def evaluate(self) -> dict[str, Any]:

        self.load_knowledge()

        actual = self.analyze_image(
            self.generated_file
        )

        comparison = (
            self.compare_features(
                actual
            )
        )

        structural = (
            self.structural_score(
                actual
            )
        )

        final_score = (
            self.calculate_final_score(
                comparison["score"],
                structural,
            )
        )

        result = {
            "version": self.VERSION,

            "generated_file": str(
                self.generated_file
            ),

            "knowledge_file": str(
                self.knowledge_file
            ),

            "actual_features": actual,

            "comparison": comparison,

            "structural_score":
                structural,

            "final_score":
                final_score,
        }

        with open(
            self.report_file,
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
        result: dict[str, Any],
    ) -> None:

        print()
        print("=" * 60)
        print("SIGNATURE GENERATION EVALUATOR")
        print("=" * 60)
        print()

        print(
            f"Version: {self.VERSION}"
        )

        print(
            f"Generated: "
            f"{self.generated_file}"
        )

        print()

        print(
            "Actual features:"
        )

        print(
            json.dumps(
                result[
                    "actual_features"
                ],
                ensure_ascii=False,
                indent=2,
            )
        )

        print()

        print(
            "Feature score: "
            f"{result['comparison']['score']}"
        )

        print(
            "Structural score: "
            f"{result['structural_score']}"
        )

        print()

        print(
            "FINAL SCORE: "
            f"{result['final_score']}"
        )

        print()

        print(
            f"Report saved to: "
            f"{self.report_file}"
        )

        print()
        print(
            "GENERATION EVALUATOR: OK"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    evaluator = SignatureGenerationEvaluator(
        knowledge_file=(
            "signature_unified_knowledge.json"
        ),
        generated_file=(
            "generated_signature.png"
        ),
        report_file=(
            "generation_evaluation.json"
        ),
    )

    result = evaluator.evaluate()

    evaluator.print_report(
        result
    )


if __name__ == "__main__":

    main()