# -*- coding: utf-8 -*-

"""
Signature Machine
Stage 2 - Signature Knowledge Engine

مسئولیت‌ها:
1. خواندن signature_knowledge.json
2. اعتبارسنجی ساختار Knowledge
3. دسترسی به دانش سطحی و عمیق
4. استخراج پروفایل طراحی
5. آماده‌سازی Knowledge برای Signature Generator

این فایل تصاویر را دوباره تحلیل نمی‌کند.
این فایل فقط Knowledge موجود را مصرف می‌کند.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SignatureKnowledgeEngine:
    """
    موتور مدیریت Knowledge امضاها.
    """

    def __init__(
        self,
        knowledge_file: str | Path = "signature_knowledge.json",
    ):
        self.knowledge_file = Path(
            knowledge_file
        )

        self.data: dict[str, Any] = {}

        self.load()

    # ========================================================
    # LOAD
    # ========================================================

    def load(self) -> dict:
        """
        بارگذاری Knowledge موجود.
        """

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

        self.validate()

        return self.data

    # ========================================================
    # VALIDATE
    # ========================================================

    def validate(self) -> None:
        """
        بررسی ساختار اصلی Knowledge.
        """

        required = {
            "version",
            "type",
            "source",
            "knowledge",
            "samples",
            "failed",
        }

        missing = required - set(
            self.data.keys()
        )

        if missing:

            raise ValueError(
                "Missing Knowledge fields: "
                + ", ".join(
                    sorted(missing)
                )
            )

        if self.data.get(
            "type"
        ) != "signature_knowledge":

            raise ValueError(
                "Invalid knowledge type."
            )

        if not isinstance(
            self.data.get("knowledge"),
            dict,
        ):

            raise ValueError(
                "Knowledge must be a dict."
            )

        if not isinstance(
            self.data.get("samples"),
            list,
        ):

            raise ValueError(
                "Samples must be a list."
            )

    # ========================================================
    # BASIC INFO
    # ========================================================

    @property
    def version(self) -> str:

        return str(
            self.data.get(
                "version",
                "unknown",
            )
        )

    @property
    def sample_count(self) -> int:

        return len(
            self.data.get(
                "samples",
                [],
            )
        )

    @property
    def failed_count(self) -> int:

        return len(
            self.data.get(
                "failed",
                [],
            )
        )

    # ========================================================
    # KNOWLEDGE ACCESS
    # ========================================================

    def get_knowledge(self) -> dict:

        return self.data.get(
            "knowledge",
            {},
        )

    def get_deep_knowledge(self) -> dict:

        knowledge = self.get_knowledge()

        return knowledge.get(
            "deep",
            {},
        )

    def get_average_features(self) -> dict:

        knowledge = self.get_knowledge()

        return knowledge.get(
            "average",
            {},
        )

    # ========================================================
    # SAMPLE ACCESS
    # ========================================================

    def get_samples(self) -> list[dict]:

        return self.data.get(
            "samples",
            [],
        )

    def get_sample(
        self,
        filename: str,
    ) -> dict | None:

        for sample in self.get_samples():

            if sample.get(
                "filename"
            ) == filename:

                return sample

        return None

    # ========================================================
    # APPROVED SAMPLES
    # ========================================================

    def get_approved_samples(self) -> list:

        return self.data.get(
            "approved_samples",
            [],
        )

    # ========================================================
    # DESIGN PROFILE
    # ========================================================

    def build_design_profile(self) -> dict:
        """
        ساخت پروفایل کلی طراحی
        برای استفاده توسط Generator آینده.
        """

        average = (
            self.get_average_features()
        )

        deep = (
            self.get_deep_knowledge()
        )

        return {
            "sample_count": self.sample_count,

            "average": {
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
            },

            "deep": {
                "average_curvature": deep.get(
                    "average_curvature",
                    0.0,
                ),

                "average_directional_variation": deep.get(
                    "average_directional_variation",
                    0.0,
                ),

                "average_path_length": deep.get(
                    "average_path_length",
                    0.0,
                ),
            },
        }

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(self) -> dict:

        return {
            "version": self.version,
            "samples": self.sample_count,
            "failed": self.failed_count,
            "approved": len(
                self.get_approved_samples()
            ),
            "deep_knowledge": bool(
                self.get_deep_knowledge()
            ),
        }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("SIGNATURE KNOWLEDGE ENGINE")
    print("=" * 60)

    engine = SignatureKnowledgeEngine()

    summary = engine.summary()

    print()
    print(
        f"Version: {summary['version']}"
    )

    print(
        f"Samples: {summary['samples']}"
    )

    print(
        f"Failed: {summary['failed']}"
    )

    print(
        f"Approved: {summary['approved']}"
    )

    print(
        f"Deep knowledge: "
        f"{summary['deep_knowledge']}"
    )

    print()

    profile = (
        engine.build_design_profile()
    )

    print(
        "Design profile:"
    )

    print(
        json.dumps(
            profile,
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print(
        "KNOWLEDGE ENGINE: OK"
    )