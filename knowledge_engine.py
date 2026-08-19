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

    VERSION = "1.1"

    def __init__(
        self,
        knowledge_file: str | Path = "signature_knowledge.json",
    ):
        self.knowledge_file = Path(
            knowledge_file
        )

        self.data: dict[str, Any] = {}

        self.samples: list[dict] = []

        self.approved_samples: list = []

        self.surface_knowledge: dict = {}

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

                "sample_count":
                    len(self.samples),
            },

            "design_profile":
                design_profile,

            "surface_knowledge":
                self.surface_knowledge,

            "deep_knowledge":
                deep,

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