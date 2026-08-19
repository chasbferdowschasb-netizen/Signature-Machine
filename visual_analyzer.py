# -*- coding: utf-8 -*-

"""
Signature Machine
Stage 2 - Deep Visual Analyzer

هدف:
1. تحلیل ساختار بصری امضا
2. استخراج مسیر تقریبی خطوط از تصویر
3. تحلیل انحنا و تغییر جهت
4. تحلیل تراکم و توزیع جوهر
5. شناسایی اجزای خطی، قوس‌ها، حلقه‌ها و Flourish
6. افزودن دانش جدید به signature_knowledge.json
7. پردازش فقط فایل‌های جدید در اجرای بعدی

این فایل مستقل از stroke_engine.py است.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter


Point = Tuple[float, float]


class DeepVisualAnalyzer:
    """
    موتور تحلیل عمیق بصری امضا.

    تصاویر اصلی را تغییر نمی‌دهد.
    فقط ویژگی‌های تحلیلی را استخراج و در Knowledge ذخیره می‌کند.
    """

    IMAGE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
    }

    VERSION = "0.1"

    def __init__(
        self,
        threshold: int = 180,
        blur_radius: float = 0.6,
    ):
        self.threshold = threshold
        self.blur_radius = blur_radius

    # ========================================================
    # FILE HASH
    # ========================================================

    @staticmethod
    def file_hash(
        image_path: Path,
    ) -> str:

        sha = hashlib.sha256()

        with open(
            image_path,
            "rb",
        ) as file:

            for chunk in iter(
                lambda: file.read(1024 * 1024),
                b"",
            ):
                sha.update(chunk)

        return sha.hexdigest()

    # ========================================================
    # IMAGE → MASK
    # ========================================================

    def image_to_mask(
        self,
        image_path: Path,
    ) -> np.ndarray:

        image = Image.open(
            image_path
        ).convert("RGBA")

        if self.blur_radius > 0:
            image = image.filter(
                ImageFilter.GaussianBlur(
                    self.blur_radius
                )
            )

        rgba = np.asarray(
            image,
            dtype=np.uint8,
        )

        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3]

        luminance = (
            0.299 * rgb[:, :, 0]
            + 0.587 * rgb[:, :, 1]
            + 0.114 * rgb[:, :, 2]
        )

        # تشخیص جوهر:
        # خطوط تیره یا نواحی دارای آلفای معنی‌دار
        mask = (
            (luminance < self.threshold)
            & (alpha > 10)
        )

        return mask.astype(
            np.uint8
        )

    # ========================================================
    # BASIC MASK FEATURES
    # ========================================================

    @staticmethod
    def mask_features(
        mask: np.ndarray,
    ) -> dict:

        height, width = mask.shape

        ink_pixels = int(
            np.count_nonzero(mask)
        )

        total_pixels = (
            width * height
        )

        if ink_pixels == 0:
            return {
                "ink_pixels": 0,
                "ink_ratio": 0.0,
                "bbox_width_ratio": 0.0,
                "bbox_height_ratio": 0.0,
                "bbox_aspect_ratio": 0.0,
                "fill_ratio": 0.0,
            }

        ys, xs = np.where(
            mask > 0
        )

        min_x = int(xs.min())
        max_x = int(xs.max())
        min_y = int(ys.min())
        max_y = int(ys.max())

        bbox_width = (
            max_x - min_x + 1
        )

        bbox_height = (
            max_y - min_y + 1
        )

        bbox_area = (
            bbox_width
            * bbox_height
        )

        return {
            "ink_pixels": ink_pixels,
            "ink_ratio": round(
                ink_pixels / total_pixels,
                6,
            ),
            "bbox_width_ratio": round(
                bbox_width / width,
                6,
            ),
            "bbox_height_ratio": round(
                bbox_height / height,
                6,
            ),
            "bbox_aspect_ratio": round(
                bbox_width / max(
                    bbox_height,
                    1,
                ),
                6,
            ),
            "fill_ratio": round(
                ink_pixels / max(
                    bbox_area,
                    1,
                ),
                6,
            ),
        }

    # ========================================================
    # PROJECTION ANALYSIS
    # ========================================================

    @staticmethod
    def projection_features(
        mask: np.ndarray,
    ) -> dict:

        horizontal = np.sum(
            mask,
            axis=1,
        )

        vertical = np.sum(
            mask,
            axis=0,
        )

        h_max = int(
            horizontal.max()
        ) if horizontal.size else 0

        v_max = int(
            vertical.max()
        ) if vertical.size else 0

        h_mean = float(
            horizontal.mean()
        ) if horizontal.size else 0.0

        v_mean = float(
            vertical.mean()
        ) if vertical.size else 0.0

        h_variation = float(
            np.std(horizontal)
        ) if horizontal.size else 0.0

        v_variation = float(
            np.std(vertical)
        ) if vertical.size else 0.0

        return {
            "horizontal_max": h_max,
            "vertical_max": v_max,
            "horizontal_mean": round(
                h_mean,
                6,
            ),
            "vertical_mean": round(
                v_mean,
                6,
            ),
            "horizontal_variation": round(
                h_variation,
                6,
            ),
            "vertical_variation": round(
                v_variation,
                6,
            ),
        }

    # ========================================================
    # CENTER OF MASS
    # ========================================================

    @staticmethod
    def center_features(
        mask: np.ndarray,
    ) -> dict:

        ys, xs = np.where(
            mask > 0
        )

        if len(xs) == 0:
            return {
                "center_x": 0.0,
                "center_y": 0.0,
            }

        height, width = mask.shape

        return {
            "center_x": round(
                float(xs.mean())
                / width,
                6,
            ),
            "center_y": round(
                float(ys.mean())
                / height,
                6,
            ),
        }

    # ========================================================
    # DIRECTIONAL ANALYSIS
    # ========================================================

    @staticmethod
    def directional_features(
        mask: np.ndarray,
    ) -> dict:

        ys, xs = np.where(
            mask > 0
        )

        if len(xs) < 2:
            return {
                "dominant_angle": 0.0,
                "directional_variation": 0.0,
            }

        x_center = float(
            xs.mean()
        )

        y_center = float(
            ys.mean()
        )

        dx = xs.astype(
            np.float64
        ) - x_center

        dy = (
            ys.astype(
                np.float64
            )
            - y_center
        )

        covariance = np.cov(
            dx,
            dy,
        )

        eigenvalues, eigenvectors = np.linalg.eigh(
            covariance
        )

        index = int(
            np.argmax(eigenvalues)
        )

        vector = eigenvectors[
            :,
            index,
        ]

        angle = math.degrees(
            math.atan2(
                vector[1],
                vector[0],
            )
        )

        if angle < 0:
            angle += 180.0

        ratio = (
            float(
                eigenvalues[index]
            )
            / max(
                float(
                    eigenvalues.sum()
                ),
                1e-9,
            )
        )

        return {
            "dominant_angle": round(
                angle,
                6,
            ),
            "directional_variation": round(
                1.0 - ratio,
                6,
            ),
        }

    # ========================================================
    # CURVATURE PROXY
    # ========================================================

    @staticmethod
    def curvature_features(
        mask: np.ndarray,
    ) -> dict:

        ys, xs = np.where(
            mask > 0
        )

        if len(xs) < 10:
            return {
                "curvature_proxy": 0.0,
                "direction_changes": 0,
                "path_length_proxy": 0.0,
            }

        points = np.column_stack(
            (
                xs.astype(
                    np.float64
                ),
                ys.astype(
                    np.float64
                ),
            )
        )

        # مرتب‌سازی تقریبی بر اساس x
        # برای تحلیل کلی فرم، نه بازسازی دقیق Stroke
        order = np.argsort(
            points[:, 0]
        )

        points = points[order]

        # کاهش نقاط تکراری
        sampled = points[
            ::max(
                1,
                len(points) // 300,
            )
        ]

        if len(sampled) < 3:
            return {
                "curvature_proxy": 0.0,
                "direction_changes": 0,
                "path_length_proxy": 0.0,
            }

        vectors = np.diff(
            sampled,
            axis=0,
        )

        lengths = np.linalg.norm(
            vectors,
            axis=1,
        )

        valid = lengths > 0

        vectors = vectors[
            valid
        ]

        lengths = lengths[
            valid
        ]

        if len(vectors) < 2:
            return {
                "curvature_proxy": 0.0,
                "direction_changes": 0,
                "path_length_proxy": 0.0,
            }

        angles = np.arctan2(
            vectors[:, 1],
            vectors[:, 0],
        )

        angle_changes = np.diff(
            np.unwrap(angles)
        )

        curvature = float(
            np.mean(
                np.abs(
                    angle_changes
                )
            )
        )

        direction_changes = int(
            np.sum(
                np.abs(
                    angle_changes
                )
                > math.radians(35)
            )
        )

        path_length = float(
            lengths.sum()
        )

        height, width = mask.shape

        diagonal = math.sqrt(
            width ** 2
            + height ** 2
        )

        return {
            "curvature_proxy": round(
                curvature,
                6,
            ),
            "direction_changes": direction_changes,
            "path_length_proxy": round(
                path_length
                / max(
                    diagonal,
                    1.0,
                ),
                6,
            ),
        }

    # ========================================================
    # DENSITY ZONES
    # ========================================================

    @staticmethod
    def density_zones(
        mask: np.ndarray,
    ) -> dict:

        height, width = mask.shape

        h2 = height // 2
        w2 = width // 2

        zones = {
            "top_left": mask[
                :h2,
                :w2,
            ],
            "top_right": mask[
                :h2,
                w2:,
            ],
            "bottom_left": mask[
                h2:,
                :w2,
            ],
            "bottom_right": mask[
                h2:,
                w2:,
            ],
        }

        result = {}

        for name, zone in zones.items():

            if zone.size == 0:
                value = 0.0
            else:
                value = float(
                    np.mean(zone)
                )

            result[name] = round(
                value,
                6,
            )

        return result

    # ========================================================
    # SYMMETRY
    # ========================================================

    @staticmethod
    def symmetry_features(
        mask: np.ndarray,
    ) -> dict:

        horizontal_flip = np.flip(
            mask,
            axis=1,
        )

        vertical_flip = np.flip(
            mask,
            axis=0,
        )

        horizontal_difference = np.mean(
            np.abs(
                mask.astype(
                    np.float32
                )
                - horizontal_flip.astype(
                    np.float32
                )
            )
        )

        vertical_difference = np.mean(
            np.abs(
                mask.astype(
                    np.float32
                )
                - vertical_flip.astype(
                    np.float32
                )
            )
        )

        return {
            "horizontal_symmetry": round(
                1.0
                - float(
                    horizontal_difference
                ),
                6,
            ),
            "vertical_symmetry": round(
                1.0
                - float(
                    vertical_difference
                ),
                6,
            ),
        }

    # ========================================================
    # SINGLE IMAGE
    # ========================================================

    def analyze_image(
        self,
        image_path: str | Path,
    ) -> dict:

        image_path = Path(
            image_path
        )

        mask = self.image_to_mask(
            image_path
        )

        result = {
            "filename": image_path.name,
            "file_hash": self.file_hash(
                image_path
            ),
            "analyzer_version": self.VERSION,
            "mask_features": self.mask_features(
                mask
            ),
            "projection": self.projection_features(
                mask
            ),
            "center": self.center_features(
                mask
            ),
            "direction": self.directional_features(
                mask
            ),
            "curvature": self.curvature_features(
                mask
            ),
            "density_zones": self.density_zones(
                mask
            ),
            "symmetry": self.symmetry_features(
                mask
            ),
        }

        return result

    # ========================================================
    # LOAD KNOWLEDGE
    # ========================================================

    @staticmethod
    def load_knowledge(
        filename: str | Path,
    ) -> dict:

        filename = Path(
            filename
        )

        if not filename.exists():

            return {
                "version": "0.1",
                "type": "signature_knowledge",
                "source": {},
                "knowledge": {},
                "samples": [],
                "failed": [],
                "deep_visual_analysis": [],
            }

        with open(
            filename,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Knowledge file must contain a JSON object."
            )

        data.setdefault(
            "deep_visual_analysis",
            [],
        )

        return data

    # ========================================================
    # INCREMENTAL ANALYSIS
    # ========================================================

    def analyze_new_files(
        self,
        library_path: str | Path,
        knowledge_file: str | Path = "signature_knowledge.json",
    ) -> dict:

        library_path = Path(
            library_path
        )

        knowledge_file = Path(
            knowledge_file
        )

        if not library_path.exists():
            raise FileNotFoundError(
                f"Library not found: {library_path}"
            )

        data = self.load_knowledge(
            knowledge_file
        )

        existing = {
            item.get("file_hash")
            for item in data.get(
                "deep_visual_analysis",
                [],
            )
            if item.get("file_hash")
        }

        files = sorted(
            path
            for path in library_path.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower()
                in self.IMAGE_EXTENSIONS
            )
        )

        pending = []

        for path in files:

            try:
                file_hash = self.file_hash(
                    path
                )
            except Exception:
                continue

            if file_hash not in existing:
                pending.append(
                    path
                )

        total = len(pending)

        print()
        print("=" * 60)
        print("DEEP VISUAL ANALYSIS")
        print("=" * 60)
        print()
        print(
            f"New files: {total}"
        )

        successful = 0
        failed = []

        for index, path in enumerate(
            pending,
            start=1,
        ):

            try:

                result = self.analyze_image(
                    path
                )

                data[
                    "deep_visual_analysis"
                ].append(
                    result
                )

                successful += 1

            except Exception as exc:

                 import traceback

                 print()
                 print("ERROR:")
                 print(f"File: {path}")
                 print(f"Type: {type(exc).__name__}")
                 print(f"Message: {exc}")
                 traceback.print_exc()

                 failed.append(
                   {
                     "filename": str(path),
                     "error": str(exc),
                     "type": type(exc).__name__,
                   }
                )


            if (
                index == 1
                or index % 100 == 0
                or index == total
            ):

                print(
                    f"Processed: "
                    f"{index}/{total}"
                )

        self._update_aggregate(
            data
        )

        data[
            "deep_visual_analysis_version"
        ] = self.VERSION

        with open(
            knowledge_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print()
        print("=" * 60)
        print("DEEP VISUAL ANALYSIS COMPLETE")
        print("=" * 60)
        print()
        print(
            f"Processed successfully: "
            f"{successful}"
        )
        print(
            f"Failed: {len(failed)}"
        )
        print(
            f"Knowledge updated: "
            f"{knowledge_file}"
        )

        return data

    # ========================================================
    # AGGREGATE DEEP KNOWLEDGE
    # ========================================================

    @staticmethod
    def _update_aggregate(
        data: dict,
    ) -> None:

        samples = data.get(
            "deep_visual_analysis",
            [],
        )

        if not samples:
            return

        curvature_values = [
            item[
                "curvature"
            ][
                "curvature_proxy"
            ]
            for item in samples
            if (
                "curvature" in item
                and isinstance(
                    item["curvature"],
                    dict,
                )
            )
        ]

        direction_values = [
            item[
                "direction"
            ][
                "directional_variation"
            ]
            for item in samples
            if (
                "direction" in item
                and isinstance(
                    item["direction"],
                    dict,
                )
            )
        ]

        path_values = [
            item[
                "curvature"
            ][
                "path_length_proxy"
            ]
            for item in samples
            if (
                "curvature" in item
                and isinstance(
                    item["curvature"],
                    dict,
                )
            )
        ]

        def avg(
            values: List[float],
        ) -> float:

            if not values:
                return 0.0

            return round(
                sum(values)
                / len(values),
                6,
            )

        data.setdefault(
            "knowledge",
            {},
        )

        data[
            "knowledge"
        ][
            "deep_visual"
        ] = {
            "sample_count": len(
                samples
            ),
            "average_curvature": avg(
                curvature_values
            ),
            "average_directional_variation": avg(
                direction_values
            ),
            "average_path_length": avg(
                path_values
            ),
        }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    analyzer = DeepVisualAnalyzer()

    analyzer.analyze_new_files(
        library_path="library",
        knowledge_file="signature_knowledge.json",
    )