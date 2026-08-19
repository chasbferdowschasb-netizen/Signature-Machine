# -*- coding: utf-8 -*-

"""
Signature Machine
Stage 1 - Stroke Engine + Renderer

هدف:
1. تولید مسیرهای Bezier
2. شبیه‌سازی حرکت دست
3. تولید Pressure / Width / Speed
4. ذخیره Stroke Data در JSON
5. Render کردن Stroke به PNG
6. پشتیبانی رسمی از دو حالت خروجی:
   - مشکی روی سفید
   - سفید روی مشکی

اصل معماری:
- قابلیت‌های مرتبط در همین ماژول نگه داشته می‌شوند.
- از ایجاد فایل‌های غیرضروری خودداری می‌کنیم.
- PNG شفاف برای پردازش داخلی حفظ می‌شود.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, asdict
from typing import List, Tuple

from PIL import Image, ImageDraw


Point = Tuple[float, float]
RGB = Tuple[int, int, int]


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class Stroke:
    """
    یک حرکت پیوسته قلم.
    """

    points: List[Point]
    pressure: List[float]
    width: List[float]
    speed: List[float]
    pen_down: bool = True


# ============================================================
# STROKE ENGINE
# ============================================================

class StrokeEngine:
    """
    موتور تولید مسیر و داده حرکتی قلم.
    """

    def __init__(
        self,
        seed: int | None = None,
        jitter: float = 1.2,
        base_width: float = 5.0,
        pressure_variation: float = 0.20,
    ):
        self.random = random.Random(seed)

        self.jitter = jitter
        self.base_width = base_width
        self.pressure_variation = pressure_variation

    # --------------------------------------------------------
    # BEZIER
    # --------------------------------------------------------

    @staticmethod
    def cubic_bezier(
        p0: Point,
        p1: Point,
        p2: Point,
        p3: Point,
        steps: int = 100,
    ) -> List[Point]:

        if steps < 2:
            raise ValueError(
                "steps باید حداقل 2 باشد."
            )

        points = []

        for i in range(steps):

            t = i / (steps - 1)
            mt = 1.0 - t

            x = (
                mt**3 * p0[0]
                + 3 * mt**2 * t * p1[0]
                + 3 * mt * t**2 * p2[0]
                + t**3 * p3[0]
            )

            y = (
                mt**3 * p0[1]
                + 3 * mt**2 * t * p1[1]
                + 3 * mt * t**2 * p2[1]
                + t**3 * p3[1]
            )

            points.append((x, y))

        return points

    # --------------------------------------------------------
    # JITTER
    # --------------------------------------------------------

    def add_jitter(
        self,
        points: List[Point],
    ) -> List[Point]:

        result = []

        for x, y in points:

            dx = self.random.uniform(
                -self.jitter,
                self.jitter,
            )

            dy = self.random.uniform(
                -self.jitter,
                self.jitter,
            )

            result.append(
                (
                    x + dx,
                    y + dy,
                )
            )

        return result

    # --------------------------------------------------------
    # PRESSURE
    # --------------------------------------------------------

    def generate_pressure(
        self,
        count: int,
    ) -> List[float]:

        if count <= 0:
            return []

        pressure = []

        for i in range(count):

            position = i / max(
                count - 1,
                1,
            )

            # فشار طبیعی:
            # ابتدا افزایش، سپس کاهش
            wave = math.sin(
                position * math.pi
            )

            noise = self.random.uniform(
                -self.pressure_variation,
                self.pressure_variation,
            )

            value = (
                0.35
                + 0.45 * wave
                + noise
            )

            value = max(
                0.05,
                min(1.0, value),
            )

            pressure.append(value)

        return pressure

    # --------------------------------------------------------
    # PRESSURE -> WIDTH
    # --------------------------------------------------------

    def pressure_to_width(
        self,
        pressure: List[float],
    ) -> List[float]:

        widths = []

        for p in pressure:

            width = (
                self.base_width
                * (0.55 + p)
            )

            widths.append(width)

        return widths

    # --------------------------------------------------------
    # SPEED
    # --------------------------------------------------------

    @staticmethod
    def calculate_speed(
        points: List[Point],
    ) -> List[float]:

        if not points:
            return []

        speeds = [0.0]

        for i in range(1, len(points)):

            x1, y1 = points[i - 1]
            x2, y2 = points[i]

            distance = math.sqrt(
                (x2 - x1) ** 2
                + (y2 - y1) ** 2
            )

            speeds.append(distance)

        return speeds

    # --------------------------------------------------------
    # CREATE STROKE
    # --------------------------------------------------------

    def create_stroke(
        self,
        points: List[Point],
        apply_jitter: bool = True,
    ) -> Stroke:

        if len(points) < 2:
            raise ValueError(
                "Stroke باید حداقل دو نقطه داشته باشد."
            )

        if apply_jitter:
            points = self.add_jitter(points)

        pressure = self.generate_pressure(
            len(points)
        )

        width = self.pressure_to_width(
            pressure
        )

        speed = self.calculate_speed(
            points
        )

        return Stroke(
            points=points,
            pressure=pressure,
            width=width,
            speed=speed,
        )

    # ========================================================
    # DEMO SIGNATURE
    # ========================================================

    def create_demo_signature(
        self,
    ) -> List[Stroke]:

        strokes = []

        # Stroke 1
        curve1 = self.cubic_bezier(
            (120, 180),
            (180, 60),
            (320, 60),
            (390, 170),
            120,
        )

        strokes.append(
            self.create_stroke(curve1)
        )

        # Stroke 2
        curve2 = self.cubic_bezier(
            (300, 170),
            (380, 240),
            (520, 250),
            (600, 130),
            120,
        )

        strokes.append(
            self.create_stroke(curve2)
        )

        # Flourish
        curve3 = self.cubic_bezier(
            (90, 235),
            (300, 290),
            (650, 285),
            (900, 210),
            160,
        )

        strokes.append(
            self.create_stroke(curve3)
        )

        return strokes


# ============================================================
# RENDERER
# ============================================================

class StrokeRenderer:
    """
    تبدیل Stroke Data به تصویر.

    حالت‌های رسمی خروجی:

    transparent
        خروجی شفاف برای پردازش داخلی.

    black_on_white
        امضای مشکی روی زمینه سفید.

    white_on_black
        امضای سفید روی زمینه مشکی.
    """

    MODES = {
        "transparent",
        "black_on_white",
        "white_on_black",
    }

    BLACK: RGB = (0, 0, 0)
    WHITE: RGB = (255, 255, 255)

    def __init__(
        self,
        width: int = 1000,
        height: int = 350,
    ):
        self.width = width
        self.height = height

    # --------------------------------------------------------
    # COLORS
    # --------------------------------------------------------

    @classmethod
    def get_colors(
        cls,
        mode: str,
    ) -> Tuple[RGB | None, RGB | None]:

        if mode == "transparent":
            return None, cls.BLACK

        if mode == "black_on_white":
            return cls.WHITE, cls.BLACK

        if mode == "white_on_black":
            return cls.BLACK, cls.WHITE

        raise ValueError(
            f"حالت نامعتبر: {mode}. "
            f"حالت‌های مجاز: {sorted(cls.MODES)}"
        )

    # --------------------------------------------------------
    # RENDER
    # --------------------------------------------------------

    def render(
        self,
        strokes: List[Stroke],
        mode: str = "transparent",
    ) -> Image.Image:

        background, ink = self.get_colors(mode)

        if mode == "transparent":

            image = Image.new(
                "RGBA",
                (
                    self.width,
                    self.height,
                ),
                (
                    0,
                    0,
                    0,
                    0,
                ),
            )

        else:

            image = Image.new(
                "RGB",
                (
                    self.width,
                    self.height,
                ),
                background,
            )

        draw = ImageDraw.Draw(image)

        for stroke in strokes:

            points = stroke.points
            widths = stroke.width

            if len(points) < 2:
                continue

            for i in range(
                1,
                len(points),
            ):

                x1, y1 = points[i - 1]
                x2, y2 = points[i]

                width = max(
                    1,
                    int(
                        (
                            widths[i - 1]
                            + widths[i]
                        )
                        / 2
                    ),
                )

                if mode == "transparent":

                    fill = (
                        ink[0],
                        ink[1],
                        ink[2],
                        255,
                    )

                else:

                    fill = ink

                draw.line(
                    [
                        (x1, y1),
                        (x2, y2),
                    ],
                    fill=fill,
                    width=width,
                )

        return image

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    def save(
        self,
        strokes: List[Stroke],
        filename: str,
        mode: str = "transparent",
    ) -> None:

        image = self.render(
            strokes,
            mode=mode,
        )

        image.save(filename)


# ============================================================
# JSON STORAGE
# ============================================================

def save_strokes(
    strokes: List[Stroke],
    filename: str,
) -> None:

    data = {
        "version": "1.0",
        "type": "signature_strokes",
        "stroke_count": len(strokes),
        "strokes": [
            asdict(stroke)
            for stroke in strokes
        ],
    }

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

# ============================================================
# DATASET FEATURE EXTRACTION
# ============================================================
from pathlib import Path
from collections import Counter
import hashlib
import time


class SignatureFeatureExtractor:
    """
    استخراج ویژگی‌های بصری از نمونه‌های Signature Library.

    این کلاس فقط Feature استخراج می‌کند.
    تصاویر اصلی Library دستکاری نمی‌شوند.
    """

    IMAGE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
    }

    def __init__(self):
        self.samples = []
        self.knowledge_version = "0.2"

    # --------------------------------------------------------
    # SINGLE IMAGE
    # --------------------------------------------------------

    @staticmethod
    def analyze_image(
        image_path: str | Path,
    ) -> dict:

        image_path = Path(image_path)

        image = Image.open(image_path)

        width, height = image.size

        if width <= 0 or height <= 0:
            raise ValueError(
                "Invalid image dimensions."
            )

        aspect_ratio = width / height

        has_alpha = (
            "A" in image.getbands()
        )

        rgba = image.convert("RGBA")

        pixels = list(rgba.get_flattened_data())

        total_pixels = len(pixels)

        visible_pixels = 0
        dark_pixels = 0
        light_pixels = 0

        min_x = width
        min_y = height
        max_x = -1
        max_y = -1

        for index, pixel in enumerate(pixels):

            r, g, b, a = pixel

            x = index % width
            y = index // width

            # ------------------------------------------------
            # Alpha
            # ------------------------------------------------

            if a > 10:
                visible_pixels += 1

            # ------------------------------------------------
            # Luminance
            # ------------------------------------------------

            luminance = (
                0.299 * r
                + 0.587 * g
                + 0.114 * b
            )

            if luminance < 80:
                dark_pixels += 1

            if luminance > 200:
                light_pixels += 1

            # ------------------------------------------------
            # Ink / content detection
            # ------------------------------------------------

            is_content = False

            if a > 10:

                # Transparent background
                if a < 240:

                    is_content = True

                # Dark content
                elif luminance < 180:

                    is_content = True

            if is_content:

                min_x = min(
                    min_x,
                    x,
                )

                min_y = min(
                    min_y,
                    y,
                )

                max_x = max(
                    max_x,
                    x,
                )

                max_y = max(
                    max_y,
                    y,
                )

        # ----------------------------------------------------
        # Bounding Box
        # ----------------------------------------------------

        if max_x >= min_x and max_y >= min_y:

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

            content_aspect_ratio = (
                content_width
                / content_height
                if content_height
                else 0
            )

            bbox_fill_ratio = (
                bbox_area
                / total_pixels
            )

        else:

            content_width = 0
            content_height = 0
            content_aspect_ratio = 0
            bbox_fill_ratio = 0

        # ----------------------------------------------------
        # Ink Density
        # ----------------------------------------------------

        ink_density = (
            dark_pixels / total_pixels
            if total_pixels
            else 0
        )

        visible_ratio = (
            visible_pixels / total_pixels
            if total_pixels
            else 0
        )

        # ----------------------------------------------------
        # Background Classification
        # ----------------------------------------------------

        if has_alpha and visible_ratio < 0.98:

            background_type = "transparent"

        elif dark_pixels > total_pixels * 0.55:

            background_type = "dark"

        elif light_pixels > total_pixels * 0.55:

            background_type = "light"

        else:

            background_type = "mixed"

        # ----------------------------------------------------
        # Margins
        # ----------------------------------------------------

        if max_x >= min_x:

            left_margin = min_x / width

            right_margin = (
                width - max_x - 1
            ) / width

            top_margin = min_y / height

            bottom_margin = (
                height - max_y - 1
            ) / height

        else:

            left_margin = 1.0
            right_margin = 1.0
            top_margin = 1.0
            bottom_margin = 1.0

        return {
            "filename": image_path.name,
            "width": width,
            "height": height,
            "aspect_ratio": round(
                aspect_ratio,
                6,
            ),
            "content_width": content_width,
            "content_height": content_height,
            "content_aspect_ratio": round(
                content_aspect_ratio,
                6,
            ),
            "bbox_fill_ratio": round(
                bbox_fill_ratio,
                6,
            ),
            "ink_density": round(
                ink_density,
                6,
            ),
            "visible_ratio": round(
                visible_ratio,
                6,
            ),
            "left_margin": round(
                left_margin,
                6,
            ),
            "right_margin": round(
                right_margin,
                6,
            ),
            "top_margin": round(
                top_margin,
                6,
            ),
            "bottom_margin": round(
                bottom_margin,
                6,
            ),
            "has_alpha": has_alpha,
            "background_type": background_type,
        }
    # --------------------------------------------------------
    # FILE HASH
    # --------------------------------------------------------

    @staticmethod
    def calculate_file_hash(
        image_path: str | Path,
        chunk_size: int = 1024 * 1024,
    ) -> str:

        image_path = Path(image_path)

        sha256 = hashlib.sha256()

        with open(image_path, "rb") as file:

            while True:

                chunk = file.read(chunk_size)

                if not chunk:
                    break

                sha256.update(chunk)

        return sha256.hexdigest()

    # --------------------------------------------------------
    # INCREMENTAL KNOWLEDGE
    # --------------------------------------------------------

    @staticmethod
    def load_knowledge(
        output_file: str | Path,
    ) -> dict | None:

        output_file = Path(output_file)

        if not output_file.exists():
            return None

        try:

            with open(
                output_file,
                "r",
                encoding="utf-8",
            ) as file:

                return json.load(file)

        except Exception:

            return None

    # --------------------------------------------------------
    # SAMPLE INDEX
    # --------------------------------------------------------

    @staticmethod
    def build_sample_index(
        samples: List[dict],
    ) -> dict:

        return {
            item["filename"]: item
            for item in samples
            if item.get("filename")
        }

    



    # --------------------------------------------------------
    # DATASET
    # --------------------------------------------------------
    def analyze_dataset(
        self,
        library_path: str | Path,
        output_file: str = "signature_knowledge.json",
    ) -> dict:

        library_path = Path(library_path)

        if not library_path.exists():

            raise FileNotFoundError(
                f"Library not found: {library_path}"
            )

        files = [
            path
            for path in library_path.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower()
                in self.IMAGE_EXTENSIONS
            )
        ]

        total = len(files)

        print()
        print("=" * 60)
        print("SIGNATURE FEATURE EXTRACTION")
        print("=" * 60)
        print()
        print(f"Found images: {total}")

        # ----------------------------------------------------
        # Load existing knowledge
        # ----------------------------------------------------

        existing = self.load_knowledge(
            output_file
        )

        existing_samples = []

        if existing:

            existing_samples = existing.get(
                "samples",
                [],
            )

        sample_index = self.build_sample_index(
            existing_samples
        )

        features = []
        failed = []

        analyzed_count = 0
        skipped_count = 0

        # ----------------------------------------------------
        # Incremental analysis
        # ----------------------------------------------------

        for index, image_path in enumerate(
            files,
            start=1,
        ):

            try:

                file_hash = self.calculate_file_hash(
                    image_path
                )

                filename = image_path.name

                old_sample = sample_index.get(
                    filename
                )

                # ------------------------------------------------
                # Existing unchanged sample
                # ------------------------------------------------

                if (
                    old_sample
                    and old_sample.get("file_hash")
                    == file_hash
                ):

                    features.append(
                        old_sample
                    )

                    skipped_count += 1

                # ------------------------------------------------
                # New / changed sample
                # ------------------------------------------------

                else:

                    feature = self.analyze_image(
                        image_path
                    )

                    stat = image_path.stat()

                    feature["file_hash"] = file_hash
                    feature["file_size"] = stat.st_size
                    feature["modified_time"] = stat.st_mtime
                    feature["analyzed_at"] = time.time()

                    features.append(
                        feature
                    )

                    analyzed_count += 1

            except Exception as exc:

                failed.append(
                    {
                        "filename": str(
                            image_path
                        ),
                        "error": str(exc),
                    }
                )

            if (
                index == 1
                or index % 250 == 0
                or index == total
            ):

                print(
                    f"Processed: "
                    f"{index}/{total}"
                )

        # ----------------------------------------------------
        # Build knowledge
        # ----------------------------------------------------

        knowledge = self._build_knowledge(
            features
        )

        # ----------------------------------------------------
        # Preserve approved knowledge
        # ----------------------------------------------------

        approved = []

        if existing:

            approved = existing.get(
                "approved_samples",
                [],
            )

        result = {
            "version": self.knowledge_version,
            "type": "signature_knowledge",

            "source": {
                "library": str(
                    library_path
                ),
                "total_images": total,
                "successful": len(features),
                "failed": len(failed),
                "new_or_changed": analyzed_count,
                "skipped_unchanged": skipped_count,
            },

            "knowledge": knowledge,

            "samples": features,

            "approved_samples": approved,

            "failed": failed,
        }

        # ----------------------------------------------------
        # Save
        # ----------------------------------------------------

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

        print()
        print("=" * 60)
        print("FEATURE EXTRACTION COMPLETE")
        print("=" * 60)
        print()
        print(
            f"Successful: {len(features)}"
        )
        print(
            f"Failed:     {len(failed)}"
        )
        print(
            f"New/changed: {analyzed_count}"
        )
        print(
            f"Skipped unchanged: {skipped_count}"
        )
        print()
        print(
            f"Knowledge saved to: {output_file}"
        )

        return result
    # --------------------------------------------------------
    # KNOWLEDGE
    # --------------------------------------------------------

    @staticmethod
    def _build_knowledge(
        features: List[dict],
    ) -> dict:

        if not features:

            return {
                "sample_count": 0,
            }

        def average(
            key: str,
        ) -> float:

            values = [
                item[key]
                for item in features
                if isinstance(
                    item.get(key),
                    (int, float),
                )
            ]

            if not values:
                return 0.0

            return round(
                sum(values) / len(values),
                6,
            )

        background_counts = Counter(
            item["background_type"]
            for item in features
        )

        alpha_count = sum(
            1
            for item in features
            if item["has_alpha"]
        )

        return {
            "sample_count": len(
                features
            ),

            "average": {
                "width": average(
                    "width"
                ),
                "height": average(
                    "height"
                ),
                "aspect_ratio": average(
                    "aspect_ratio"
                ),
                "content_width": average(
                    "content_width"
                ),
                "content_height": average(
                    "content_height"
                ),
                "content_aspect_ratio": average(
                    "content_aspect_ratio"
                ),
                "bbox_fill_ratio": average(
                    "bbox_fill_ratio"
                ),
                "ink_density": average(
                    "ink_density"
                ),
                "visible_ratio": average(
                    "visible_ratio"
                ),
                "left_margin": average(
                    "left_margin"
                ),
                "right_margin": average(
                    "right_margin"
                ),
                "top_margin": average(
                    "top_margin"
                ),
                "bottom_margin": average(
                    "bottom_margin"
                ),
            },

            "background_distribution": dict(
                background_counts
            ),

            "alpha_images": alpha_count,

            "alpha_ratio": round(
                alpha_count
                / len(features),
                6,
            ),
        }
    
# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("SIGNATURE MACHINE")
    print("Stroke Engine + Renderer")
    print("=" * 60)

    # --------------------------------------------------------
    # Engine
    # --------------------------------------------------------

    engine = StrokeEngine(
        seed=1234,
        jitter=1.2,
        base_width=5.0,
    )

    # --------------------------------------------------------
    # Dataset Feature Extraction
    # --------------------------------------------------------

    extractor = SignatureFeatureExtractor()

    extractor.analyze_dataset(
        library_path="library",
        output_file="signature_knowledge.json",
    )

    print()
    print("FEATURE EXTRACTION: OK")
    
    # --------------------------------------------------------
    # Generate
    # --------------------------------------------------------

    strokes = engine.create_demo_signature()

    print()
    print(
        f"Generated strokes: {len(strokes)}"
    )

    for index, stroke in enumerate(
        strokes,
        start=1,
    ):

        print(
            f"  Stroke {index}: "
            f"{len(stroke.points)} points"
        )

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    save_strokes(
        strokes,
        "demo_signature.json",
    )

    print()
    print(
        "JSON: demo_signature.json"
    )

    # --------------------------------------------------------
    # Renderer
    # --------------------------------------------------------

    renderer = StrokeRenderer(
        width=1000,
        height=350,
    )

    # --------------------------------------------------------
    # Transparent
    # --------------------------------------------------------

    renderer.save(
        strokes,
        "demo_signature.png",
        mode="transparent",
    )

    print(
        "PNG:  demo_signature.png"
    )

    # --------------------------------------------------------
    # Official customer modes
    # --------------------------------------------------------

    renderer.save(
        strokes,
        "demo_signature_black_on_white.png",
        mode="black_on_white",
    )

    print(
        "PNG:  black_on_white"
    )

    renderer.save(
        strokes,
        "demo_signature_white_on_black.png",
        mode="white_on_black",
    )

    print(
        "PNG:  white_on_black"
    )

    print()
    print("STROKE ENGINE: OK")
    print("RENDERER: OK")
    print("COLOR MODES: OK")