# -*- coding: utf-8 -*-

"""
Signature Machine
Stage 2 - Signature-Only Deep Visual Analyzer

هدف:
1. حذف پس‌زمینه، قاب، حاشیه، لوگو، watermark و عناصر layout تا حد ممکن
2. استخراج ماسک خطوط امضا، نه ماسک کل تصویر
3. ساخت skeleton از خطوط امضا
4. تحلیل ساختار، جهت، انحنا، تراکم و اجزای خطی
5. یادگیری incremental فقط از فایل‌های داخل library/
6. پردازش مجدد خودکار وقتی pipeline/version تغییر کرده است
7. نگهداری debug artifacts برای بازبینی انسانی

وابستگی‌های اصلی:
    numpy
    Pillow

اگر scipy موجود باشد برای connected-components استفاده می‌شود؛
در غیر این صورت fallback داخلی فعال است.
"""

from __future__ import annotations

import hashlib
import json
import math
import traceback
from collections import deque
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageOps


try:
    from scipy import ndimage as ndi
except Exception:  # pragma: no cover
    ndi = None

try:
    from skimage.morphology import skeletonize as skimage_skeletonize
except Exception:  # pragma: no cover
    skimage_skeletonize = None


Point = Tuple[float, float]


class DeepVisualAnalyzer:
    """
    Signature-only visual analyzer.

    نکته مهم:
    هیچ feature بصری مستقیماً از تصویر خام وارد Knowledge نمی‌شود.
    ابتدا signature mask ساخته می‌شود و تمام تحلیل‌های اصلی از همان
    mask پاک‌سازی‌شده و skeleton آن استخراج می‌شوند.
    """

    IMAGE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }

    # با تغییر منطق extraction این مقدار باید تغییر کند تا نمونه‌های قدیمی
    # به اشتباه به عنوان نتیجه معتبر pipeline جدید تلقی نشوند.
    VERSION = "0.4"
    PIPELINE_VERSION = "signature_only_v3_shape_aware"

    KNOWLEDGE_TYPE = "signature_knowledge"

    def __init__(
        self,
        threshold: int = 180,
        blur_radius: float = 0.6,
        background_radius: int | None = None,
        min_component_pixels: int = 12,
        debug: bool = False,
        debug_dir: str | Path = ".signature_knowledge/review",
    ):
        self.threshold = threshold
        self.blur_radius = blur_radius
        self.background_radius = background_radius
        self.min_component_pixels = min_component_pixels
        self.debug = debug
        self.debug_dir = Path(debug_dir)

    # ========================================================
    # FILE HASH
    # ========================================================

    @staticmethod
    def file_hash(image_path: Path) -> str:
        sha = hashlib.sha256()

        with open(image_path, "rb") as file:
            for chunk in iter(
                lambda: file.read(1024 * 1024),
                b"",
            ):
                sha.update(chunk)

        return sha.hexdigest()

    # ========================================================
    # IMAGE LOADING
    # ========================================================

    @staticmethod
    def _load_rgba(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
        image = Image.open(image_path).convert("RGBA")
        rgba = np.asarray(image, dtype=np.uint8)

        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3]

        return rgb, alpha

    @staticmethod
    def _grayscale(rgb: np.ndarray) -> np.ndarray:
        gray = (
            0.299 * rgb[:, :, 0]
            + 0.587 * rgb[:, :, 1]
            + 0.114 * rgb[:, :, 2]
        )

        return np.clip(gray, 0, 255).astype(np.uint8)

    # ========================================================
    # CANVAS / PANEL DETECTION
    # ========================================================

    def _local_mean(self, gray: np.ndarray) -> np.ndarray:
        """تخمین background نرم و کم‌فرکانس."""
        if ndi is not None:
            sigma = max(
                6.0,
                float(self.background_radius or min(gray.shape) * 0.015),
            )
            return ndi.gaussian_filter(
                gray.astype(np.float32),
                sigma=sigma,
            )

        radius = int(max(5, self.background_radius or min(gray.shape) * 0.015))
        return np.asarray(
            Image.fromarray(gray).filter(
                ImageFilter.GaussianBlur(radius)
            ),
            dtype=np.float32,
        )

    def _canvas_mask(self, gray: np.ndarray) -> np.ndarray:
        """
        پنل‌های واقعی امضا را از layout جدا می‌کند.

        منطق v0.4:
        - پنل‌های روشن/تیره محصور با نسبت ابعاد تقریباً مربع/دایره‌ای ترجیح دارند.
        - باکس‌های افقی لوگو و watermark به عنوان panel پذیرفته نمی‌شوند.
        - اگر هیچ panel محصوری پیدا نشود، کل canvas به عنوان یک panel در نظر گرفته می‌شود.
        """
        h, w = gray.shape
        image_area = max(h * w, 1)
        local = self._local_mean(gray)

        # دو polarity را بررسی می‌کنیم. local_mean برای حذف textureهای ریز
        # و background pattern استفاده می‌شود.
        candidates = {
            "light": local > 175,
            "dark": local < 80,
        }

        best = np.zeros_like(gray, dtype=bool)
        best_score = -1.0
        best_count = 0

        if ndi is None:
            # fallback: در نبود scipy، کل تصویر را panel می‌گیریم؛
            # مرحله candidate بعداً polarity را تعیین می‌کند.
            return np.ones_like(gray, dtype=np.uint8)

        for polarity, candidate in candidates.items():
            labels, count = ndi.label(
                candidate,
                structure=np.ones((3, 3), dtype=np.uint8),
            )

            if count == 0:
                continue

            objects = ndi.find_objects(labels)
            selected = np.zeros_like(candidate, dtype=bool)
            selected_area = 0
            selected_count = 0

            for label_id, slc in enumerate(objects, start=1):
                if slc is None:
                    continue

                area = int(np.count_nonzero(labels[slc] == label_id))
                area_ratio = area / image_area
                if area_ratio < 0.025:
                    continue

                y0, y1 = slc[0].start, slc[0].stop - 1
                x0, x1 = slc[1].start, slc[1].stop - 1
                bw = x1 - x0 + 1
                bh = y1 - y0 + 1
                aspect = bw / max(bh, 1)

                touches_border = (
                    x0 <= 1 or y0 <= 1
                    or x1 >= w - 2 or y1 >= h - 2
                )

                # برای panelهای محصور، نسبت ابعاد نزدیک 1 امتیاز اصلی است.
                square_score = max(
                    0.0,
                    1.0 - min(abs(math.log(max(aspect, 1e-6))), 2.0) / 2.0,
                )

                # باکس‌های لوگو معمولاً بسیار کشیده‌اند و حتی اگر محصور باشند
                # نباید به عنوان canvas پذیرفته شوند.
                is_panel_like = (
                    0.62 <= aspect <= 1.62
                    and area_ratio >= 0.035
                )

                # panel خیلی بزرگِ مربع/دایره‌ای می‌تواند خودش کل تصویر باشد؛
                # فقط اگر border را لمس نکند آن را به عنوان panel محصور نگه می‌داریم.
                if touches_border and area_ratio < 0.18:
                    is_panel_like = False

                if not is_panel_like:
                    continue

                selected[labels == label_id] = True
                selected_area += area
                selected_count += 1

            score = (
                selected_count * 3.0
                + selected_area / image_area * 20.0
            )

            if selected_count > 0 and score > best_score:
                best = selected
                best_score = score
                best_count = selected_count

        if best_count > 0:
            return best.astype(np.uint8)

        # تصویر ساده: white/black background کل canvas است.
        return np.ones_like(gray, dtype=np.uint8)

    def _candidate_mask(
        self,
        rgb: np.ndarray,
        alpha: np.ndarray,
    ) -> np.ndarray:
        """استخراج اولیه جوهر داخل panelهای انتخاب‌شده."""
        gray = self._grayscale(rgb)
        canvas = self._canvas_mask(gray).astype(bool)

        if not np.any(canvas):
            return np.zeros_like(gray, dtype=np.uint8)

        rgb_f = rgb.astype(np.float32)
        if ndi is not None:
            local_rgb = np.stack(
                [ndi.gaussian_filter(rgb_f[:, :, c], sigma=10.0) for c in range(3)],
                axis=2,
            )
        else:
            local = self._local_mean(gray)
            local_rgb = np.stack([local, local, local], axis=2)

        color_distance = np.linalg.norm(rgb_f - local_rgb, axis=2)

        # polarity را از خود panel تعیین می‌کنیم.
        canvas_median = float(np.median(gray[canvas]))
        if canvas_median >= 150.0:
            # سفید/روشن panel -> جوهر تیره یا رنگی
            candidate = (gray < 155) | (color_distance > 28.0)
        else:
            # مشکی/تیره panel -> جوهر روشن یا رنگی
            candidate = (gray > 100) | (color_distance > 28.0)

        candidate &= canvas
        candidate &= alpha >= 16

        # یک ring خیلی نازک از بیرون panel را حذف می‌کنیم، اما دیگر 4%
        # از شعاع panel را حذف نمی‌کنیم؛ چون ممکن است flourish نزدیک لبه باشد.
        if ndi is not None:
            labels, count = ndi.label(
                canvas,
                structure=np.ones((3, 3), dtype=np.uint8),
            )
            objects = ndi.find_objects(labels)
            cleaned = np.zeros_like(candidate, dtype=bool)

            for label_id, slc in enumerate(objects, start=1):
                if slc is None:
                    continue
                panel = labels == label_id
                panel_area = int(np.count_nonzero(panel))
                if panel_area < 0.02 * canvas.size:
                    continue

                distance = ndi.distance_transform_edt(panel)
                ring = max(5, int(min(gray.shape) * 0.006))
                interior = distance > ring

                # اگر panel محصور و تقریباً دایره/مربع است، یک ellipse داخلی
                # می‌سازیم تا حلقه‌ی تزئینی دور مدال/دایره وارد signature mask نشود.
                y0, y1 = slc[0].start, slc[0].stop
                x0, x1 = slc[1].start, slc[1].stop
                ph = max(1, y1 - y0)
                pw = max(1, x1 - x0)
                aspect = pw / ph
                touches_border = (
                    x0 <= 1 or y0 <= 1
                    or x1 >= gray.shape[1] - 1
                    or y1 >= gray.shape[0] - 1
                )

                shape_inside = np.ones_like(panel, dtype=bool)
                if (
                    not touches_border
                    and 0.70 <= aspect <= 1.45
                    and panel_area < 0.90 * canvas.size
                ):
                    yy, xx = np.ogrid[:gray.shape[0], :gray.shape[1]]
                    cx = (x0 + x1 - 1) / 2.0
                    cy = (y0 + y1 - 1) / 2.0
                    rx = max(1.0, pw * 0.380)
                    ry = max(1.0, ph * 0.380)
                    ellipse = (
                        ((xx - cx) / rx) ** 2
                        + ((yy - cy) / ry) ** 2
                        <= 1.0
                    )
                    shape_inside = ellipse

                cleaned |= candidate & panel & interior & shape_inside

            candidate = cleaned

        return candidate.astype(np.uint8)

    # ========================================================
    # MORPHOLOGY
    # ========================================================

    @staticmethod
    def _binary_pil(
        mask: np.ndarray,
    ) -> Image.Image:
        return Image.fromarray(
            (mask.astype(np.uint8) * 255),
            mode="L",
        )

    @staticmethod
    def _morph_close(
        mask: np.ndarray,
        size: int = 3,
    ) -> np.ndarray:
        size = max(3, int(size))
        if size % 2 == 0:
            size += 1

        image = DeepVisualAnalyzer._binary_pil(mask)

        # close = dilation -> erosion
        image = image.filter(ImageFilter.MaxFilter(size))
        image = image.filter(ImageFilter.MinFilter(size))

        return (
            np.asarray(image) > 127
        ).astype(np.uint8)

    @staticmethod
    def _morph_open(
        mask: np.ndarray,
        size: int = 3,
    ) -> np.ndarray:
        size = max(3, int(size))
        if size % 2 == 0:
            size += 1

        image = DeepVisualAnalyzer._binary_pil(mask)

        # open = erosion -> dilation
        image = image.filter(ImageFilter.MinFilter(size))
        image = image.filter(ImageFilter.MaxFilter(size))

        return (
            np.asarray(image) > 127
        ).astype(np.uint8)

    # ========================================================
    # CONNECTED COMPONENTS
    # ========================================================

    @staticmethod
    def _components_scipy(
        mask: np.ndarray,
    ) -> list[dict]:
        structure = np.ones((3, 3), dtype=np.uint8)

        labels, count = ndi.label(
            mask.astype(bool),
            structure=structure,
        )

        if count == 0:
            return []

        objects = ndi.find_objects(labels)

        components = []

        for label_id, slc in enumerate(objects, start=1):
            if slc is None:
                continue

            ys, xs = slc

            y0 = int(ys.start)
            y1 = int(ys.stop - 1)
            x0 = int(xs.start)
            x1 = int(xs.stop - 1)

            area = int(
                np.count_nonzero(labels[slc] == label_id)
            )

            components.append(
                {
                    "label": label_id,
                    "area": area,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "width": x1 - x0 + 1,
                    "height": y1 - y0 + 1,
                }
            )

        return components

    @staticmethod
    def _components_fallback(
        mask: np.ndarray,
    ) -> list[dict]:
        """
        Fallback بدون scipy.
        برای library بسیار بزرگ، scipy توصیه می‌شود.
        """

        h, w = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        components = []
        label = 0

        neighbors = (
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1),
        )

        for y in range(h):
            for x in range(w):
                if not mask[y, x] or visited[y, x]:
                    continue

                label += 1
                stack = [(y, x)]
                visited[y, x] = True

                area = 0
                min_x = max_x = x
                min_y = max_y = y

                while stack:
                    cy, cx = stack.pop()

                    area += 1

                    min_x = min(min_x, cx)
                    max_x = max(max_x, cx)
                    min_y = min(min_y, cy)
                    max_y = max(max_y, cy)

                    for dy, dx in neighbors:
                        ny = cy + dy
                        nx = cx + dx

                        if (
                            0 <= ny < h
                            and 0 <= nx < w
                            and mask[ny, nx]
                            and not visited[ny, nx]
                        ):
                            visited[ny, nx] = True
                            stack.append((ny, nx))

                components.append(
                    {
                        "label": label,
                        "area": area,
                        "x0": min_x,
                        "y0": min_y,
                        "x1": max_x,
                        "y1": max_y,
                        "width": max_x - min_x + 1,
                        "height": max_y - min_y + 1,
                    }
                )

        return components

    def _components(
        self,
        mask: np.ndarray,
    ) -> list[dict]:
        if ndi is not None:
            return self._components_scipy(mask)

        return self._components_fallback(mask)

    # ========================================================
    # COMPONENT FILTERING
    # ========================================================

    @staticmethod
    def _component_score(
        component: dict,
        image_shape: tuple[int, int],
    ) -> float:
        h, w = image_shape

        area = float(component["area"])
        bw = float(component["width"])
        bh = float(component["height"])

        image_area = float(h * w)
        bbox_area = max(1.0, bw * bh)

        area_ratio = area / image_area
        bbox_ratio = bbox_area / image_area
        fill_ratio = area / bbox_area

        cx = (component["x0"] + component["x1"]) / 2.0
        cy = (component["y0"] + component["y1"]) / 2.0

        center_distance = math.sqrt(
            ((cx - w / 2.0) / max(w, 1)) ** 2
            + ((cy - h / 2.0) / max(h, 1)) ** 2
        )

        touches_border = (
            component["x0"] <= 1
            or component["y0"] <= 1
            or component["x1"] >= w - 2
            or component["y1"] >= h - 2
        )

        aspect = max(
            bw / max(bh, 1.0),
            bh / max(bw, 1.0),
        )

        score = 0.0

        # امضای واقعی معمولاً component قابل توجهی دارد.
        score += min(area_ratio * 1200.0, 3.0)

        # component کشیده معمولاً به فرم امضا نزدیک‌تر است.
        score += min((aspect - 1.0) * 0.35, 1.5)

        # مرکز تصویر امتیاز کمی مثبت می‌گیرد.
        score += max(
            0.0,
            1.0 - center_distance * 3.0,
        )

        # قاب‌های بزرگ و کم‌تراکم را شدیداً جریمه کن.
        if (
            bbox_ratio > 0.55
            and fill_ratio < 0.18
        ):
            score -= 5.0

        if (
            bbox_ratio > 0.70
            and fill_ratio < 0.35
        ):
            score -= 4.0

        # component متصل به حاشیه، مخصوصاً اگر بزرگ باشد،
        # احتمالاً قاب/حاشیه است.
        if touches_border and bbox_ratio > 0.08:
            score -= 4.0

        # component بسیار فشرده و کوچک بیشتر شبیه متن/نقطه است.
        if (
            area < 0.00003 * image_area
            and bbox_ratio < 0.01
        ):
            score -= 2.0

        return score

    @staticmethod
    def _component_mask(
        labels_mask: np.ndarray,
        label: int,
    ) -> np.ndarray:
        if ndi is not None:
            labels, _ = ndi.label(
                labels_mask.astype(bool),
                structure=np.ones((3, 3), dtype=np.uint8),
            )
            return (
                labels == label
            ).astype(np.uint8)

        # fallback: label در fallback فقط برای component metadata است؛
        # در این مسیر mask مجدداً با flood fill ساخته می‌شود.
        return labels_mask.astype(np.uint8)

    def _remove_obvious_layout_components(
        self,
        candidate: np.ndarray,
    ) -> tuple[np.ndarray, dict]:
        """
        مرحله اول حذف nuisance:
        - قاب‌های بزرگ
        - حاشیه‌های متصل به border
        - componentهای خیلی کوچک
        - componentهای بسیار بزرگ و کم‌تراکم
        """

        h, w = candidate.shape
        components = self._components(candidate)

        if not components:
            return np.zeros_like(candidate), {
                "component_count": 0,
                "kept_labels": [],
                "removed_labels": [],
            }

        usable = [
            c
            for c in components
            if c["area"] >= self.min_component_pixels
        ]

        if not usable:
            return np.zeros_like(candidate), {
                "component_count": len(components),
                "kept_labels": [],
                "removed_labels": [c["label"] for c in components],
            }

        scored = [
            (
                self._component_score(c, (h, w)),
                c,
            )
            for c in usable
        ]

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        primary_score, primary = scored[0]

        # اگر بهترین component خودش خیلی بد باشد، کل تصویر را به آن
        # component محدود نمی‌کنیم؛ چند component خوب را بررسی می‌کنیم.
        primary_bbox = (
            primary["x0"],
            primary["y0"],
            primary["x1"],
            primary["y1"],
        )

        pad_x = int(w * 0.10)
        pad_y = int(h * 0.10)

        expanded = (
            primary_bbox[0] - pad_x,
            primary_bbox[1] - pad_y,
            primary_bbox[2] + pad_x,
            primary_bbox[3] + pad_y,
        )

        kept: list[dict] = []

        for score, component in scored:
            bw = component["width"]
            bh = component["height"]
            bbox_area_ratio = (
                bw * bh
            ) / max(h * w, 1)

            fill_ratio = (
                component["area"]
                / max(bw * bh, 1)
            )

            cx = (
                component["x0"]
                + component["x1"]
            ) / 2.0

            cy = (
                component["y0"]
                + component["y1"]
            ) / 2.0

            near_primary = (
                expanded[0] <= cx <= expanded[2]
                and expanded[1] <= cy <= expanded[3]
            )

            touches_border = (
                component["x0"] <= 1
                or component["y0"] <= 1
                or component["x1"] >= w - 2
                or component["y1"] >= h - 2
            )

            obvious_frame = (
                bbox_area_ratio > 0.55
                and fill_ratio < 0.18
            )

            huge_border_object = (
                touches_border
                and bbox_area_ratio > 0.08
            )

            tiny = (
                component["area"]
                < max(
                    self.min_component_pixels,
                    int(h * w * 0.00001),
                )
            )

            if obvious_frame or huge_border_object or tiny:
                continue

            # component اصلی همیشه حفظ می‌شود.
            if component["label"] == primary["label"]:
                kept.append(component)
                continue

            # اجزای کوچک نزدیک component اصلی می‌توانند نقطه/تکه‌ای از
            # امضا باشند و نباید کورکورانه حذف شوند.
            if near_primary and score > primary_score - 4.0:
                kept.append(component)

        # اگر هیچ چیز نماند، primary را نگه می‌داریم.
        if not kept:
            kept = [primary]

        result = np.zeros_like(candidate)

        if ndi is not None:
            labels, _ = ndi.label(
                candidate.astype(bool),
                structure=np.ones((3, 3), dtype=np.uint8),
            )

            for component in kept:
                result[
                    labels == component["label"]
                ] = 1
        else:
            # fallback: فقط primary bbox را از candidate نگه می‌داریم.
            for component in kept:
                result[
                    component["y0"]:component["y1"] + 1,
                    component["x0"]:component["x1"] + 1,
                ] |= candidate[
                    component["y0"]:component["y1"] + 1,
                    component["x0"]:component["x1"] + 1,
                ]

        return result.astype(np.uint8), {
            "component_count": len(components),
            "usable_component_count": len(usable),
            "kept_labels": [
                c["label"] for c in kept
            ],
            "removed_labels": [
                c["label"]
                for c in components
                if c["label"]
                not in {
                    k["label"] for k in kept
                }
            ],
        }

    # ========================================================
    # SIGNATURE MASK PIPELINE
    # ========================================================

    @staticmethod
    def _remove_layout_lines(
        component_mask: np.ndarray,
    ) -> np.ndarray:
        """
        خطوط افقی/عمودی بسیار بلندِ مربوط به قاب و grid را از یک component
        پیچیده جدا می‌کند. فقط وقتی caller تشخیص داده باشد که component layout
        است از این helper استفاده می‌شود.
        """
        if ndi is None or not np.any(component_mask):
            return component_mask.astype(np.uint8)

        h, w = component_mask.shape
        horizontal_len = max(40, int(w * 0.10))
        vertical_len = max(40, int(h * 0.10))

        horizontal = ndi.binary_opening(
            component_mask.astype(bool),
            structure=np.ones((1, horizontal_len), dtype=bool),
        )
        vertical = ndi.binary_opening(
            component_mask.astype(bool),
            structure=np.ones((vertical_len, 1), dtype=bool),
        )

        layout_lines = horizontal | vertical
        cleaned = component_mask.astype(bool) & ~layout_lines
        return cleaned.astype(np.uint8)

    def _frame_interior_mask(
        self,
        candidate: np.ndarray,
    ) -> tuple[np.ndarray, list[dict]]:
        """
        قاب‌های بزرگ را به ROI داخلی تبدیل می‌کند.

        این مرحله برای صفحات نمونه‌ای که امضا داخل مربع/مستطیل قرار دارد
        حیاتی است: به جای حذف component مشترک frame+signature، فقط داخل frame
        را نگه می‌داریم و حاشیه را حذف می‌کنیم.
        """
        if ndi is None:
            return candidate.astype(np.uint8), []

        labels, count = ndi.label(
            candidate.astype(bool),
            structure=np.ones((3, 3), dtype=np.uint8),
        )
        if count == 0:
            return candidate.astype(np.uint8), []

        objects = ndi.find_objects(labels)
        h, w = candidate.shape
        rois = []

        for label_id, slc in enumerate(objects, start=1):
            if slc is None:
                continue
            area = int(np.count_nonzero(labels[slc] == label_id))
            y0, y1 = slc[0].start, slc[0].stop
            x0, x1 = slc[1].start, slc[1].stop
            bw = x1 - x0
            bh = y1 - y0
            fill = area / max(bw * bh, 1)

            if (
                bw < 0.15 * w
                or bh < 0.15 * h
                or bw > 0.85 * w
                or bh > 0.85 * h
            ):
                continue

            aspect = bw / max(bh, 1)
            if not (0.65 <= aspect <= 1.60):
                continue

            # قاب معمولاً sparse تا متوسط است؛ component پر از جوهر را frame
            # فرض نمی‌کنیم.
            if not (0.05 <= fill <= 0.55):
                continue

            # بررسی وجود ساختار نزدیک حداقل سه ضلع bbox.
            ys, xs = np.where(labels[slc] == label_id)
            edge = max(3, int(min(bw, bh) * 0.02))
            left = float(np.mean(xs <= edge))
            right = float(np.mean(xs >= bw - 1 - edge))
            top = float(np.mean(ys <= edge))
            bottom = float(np.mean(ys >= bh - 1 - edge))
            sides = sum(v > 0.02 for v in (left, right, top, bottom))
            if sides < 3:
                continue

            margin_x = max(8, int(bw * 0.055))
            margin_y = max(8, int(bh * 0.055))
            roi = np.zeros_like(candidate, dtype=bool)
            roi[
                y0 + margin_y:y1 - margin_y,
                x0 + margin_x:x1 - margin_x,
            ] = True
            rois.append({
                "label": label_id,
                "bbox": [x0, y0, x1 - 1, y1 - 1],
                "roi": roi,
            })

        if not rois:
            return candidate.astype(np.uint8), []

        # اگر frame ROI داریم، فقط interior آن‌ها را نگه می‌داریم.
        combined = np.zeros_like(candidate, dtype=bool)
        for item in rois:
            combined |= item["roi"]

        return (candidate.astype(bool) & combined).astype(np.uint8), rois

    def _select_signature_components(
        self,
        candidate: np.ndarray,
        panel: np.ndarray,
    ) -> tuple[np.ndarray, dict]:
        """
        اجزای واقعی داخل panel را حفظ می‌کند.

        اصل مهم v0.4:
        دیگر بر اساس «بزرگ بودن component» تصمیم نمی‌گیریم؛ چون یک امضای
        واقعی ممکن است از چند stroke جدا تشکیل شده باشد. فقط noise بسیار کوچک
        و اجزای واضحاً خارج از ناحیه داخلی حذف می‌شوند.
        """
        result = np.zeros_like(candidate, dtype=np.uint8)

        if not np.any(candidate):
            return result, {
                "component_count": 0,
                "kept_components": 0,
            }

        if ndi is None:
            return candidate.astype(np.uint8), {
                "component_count": 1,
                "kept_components": 1,
            }

        # حذف فقط ring لبه panel.
        distance = ndi.distance_transform_edt(panel.astype(bool))
        edge_margin = max(5, int(min(candidate.shape) * 0.006))
        interior = distance > edge_margin
        work = candidate.astype(bool) & interior

        labels, count = ndi.label(
            work,
            structure=np.ones((3, 3), dtype=np.uint8),
        )

        if count == 0:
            return result, {
                "component_count": 0,
                "kept_components": 0,
            }

        image_area = max(candidate.shape[0] * candidate.shape[1], 1)
        min_area = max(4, int(image_area * 0.0000025))
        objects = ndi.find_objects(labels)
        kept = []
        removed = []

        for label_id, slc in enumerate(objects, start=1):
            if slc is None:
                continue

            area = int(np.count_nonzero(labels[slc] == label_id))
            if area < min_area:
                removed.append(label_id)
                continue

            bw = slc[1].stop - slc[1].start
            bh = slc[0].stop - slc[0].start
            bbox_area = max(bw * bh, 1)
            fill = area / bbox_area

            # یک component که تقریباً کل panel را پر کرده و fill پایین دارد،
            # احتمالاً border/graphic artifact است.
            bbox_ratio = bbox_area / image_area
            huge_sparse = bbox_ratio > 0.55 and fill < 0.12

            # تشخیص ring دور panel: componentی که بخش عمده‌اش نزدیک مرز panel
            # است و bbox آن نسبت بزرگی از خود panel را پوشش می‌دهد.
            ys, xs = np.where(labels[slc] == label_id)
            if len(xs):
                gy = ys + slc[0].start
                gx = xs + slc[1].start
                local_distance = distance[gy, gx]
                boundary_fraction = float(
                    np.mean(local_distance <= max(10.0, min(candidate.shape) * 0.012))
                )
                panel_h, panel_w = panel.shape
                panel_bbox_ratio = (
                    (bw / max(panel_w, 1))
                    * (bh / max(panel_h, 1))
                )
                border_ring = (
                    panel_bbox_ratio > 0.28
                    and boundary_fraction > 0.55
                    and fill < 0.35
                )

                # تشخیص قاب مستطیلی/مربعی داخل یک صفحه سفید.
                # قاب واقعی معمولاً همزمان به چهار ضلع bbox نزدیک است؛
                # یک stroke معمولی امضا چنین الگوی چهارضلعی‌ای ندارد.
                local_x = xs.astype(np.float32)
                local_y = ys.astype(np.float32)
                left_frac = float(np.mean(local_x <= max(2.0, bw * 0.018)))
                right_frac = float(np.mean(local_x >= bw - 1 - max(2.0, bw * 0.018)))
                top_frac = float(np.mean(local_y <= max(2.0, bh * 0.018)))
                bottom_frac = float(np.mean(local_y >= bh - 1 - max(2.0, bh * 0.018)))
                outline_sides = min(left_frac, right_frac, top_frac, bottom_frac)

                strong_sides = sum(
                    value > 0.020
                    for value in (left_frac, right_frac, top_frac, bottom_frac)
                )

                rectangular_outline = (
                    bw >= 0.10 * candidate.shape[1]
                    and bh >= 0.10 * candidate.shape[0]
                    and 0.45 <= (bw / max(bh, 1)) <= 2.20
                    and fill < 0.32
                    and strong_sides >= 3
                )

                # بنرهای افقی watermark/logo نیز معمولاً در لبه صفحه قرار دارند.
                banner_outline = (
                    bw >= 0.20 * candidate.shape[1]
                    and bh >= 0.025 * candidate.shape[0]
                    and fill < 0.18
                    and strong_sides >= 3
                )

                cx = (slc[1].start + slc[1].stop - 1) / 2.0
                cy = (slc[0].start + slc[0].stop - 1) / 2.0
                near_left = cx < 0.18 * candidate.shape[1]
                near_right = cx > 0.82 * candidate.shape[1]
                near_top = cy < 0.18 * candidate.shape[0]
                near_bottom = cy > 0.82 * candidate.shape[0]
                near_corner = (near_left or near_right) and (near_top or near_bottom)

                corner_layout = (
                    near_corner
                    and bw >= 0.08 * candidate.shape[1]
                    and bh >= 0.035 * candidate.shape[0]
                    and area >= 0.0005 * image_area
                )
            else:
                border_ring = False
                rectangular_outline = False
                banner_outline = False
                corner_layout = False

            giant_layout = (
                bw >= 0.65 * candidate.shape[1]
                and bh >= 0.55 * candidate.shape[0]
                and 0.08 <= fill <= 0.40
            )

            if huge_sparse or border_ring or banner_outline or corner_layout:
                removed.append(label_id)
                continue

            if giant_layout:
                component_pixels = (labels == label_id)
                cleaned_layout = self._remove_layout_lines(component_pixels)
                if np.count_nonzero(cleaned_layout) >= min_area:
                    result[cleaned_layout.astype(bool)] = 1
                else:
                    removed.append(label_id)
                continue

            if rectangular_outline:
                # قاب و امضا ممکن است یک component مشترک باشند. کل component را
                # حذف نمی‌کنیم؛ فقط نوار نزدیک چهار ضلع bbox را می‌تراشیم تا خود
                # strokeهای داخل قاب باقی بمانند.
                component_pixels = labels == label_id
                y_idx, x_idx = np.where(component_pixels)
                x0, x1 = x_idx.min(), x_idx.max()
                y0, y1 = y_idx.min(), y_idx.max()
                edge = max(4, int(min(bw, bh) * 0.025))
                inside_component = component_pixels.copy()
                yy, xx = np.where(inside_component)
                near_edge = (
                    (xx <= x0 + edge)
                    | (xx >= x1 - edge)
                    | (yy <= y0 + edge)
                    | (yy >= y1 - edge)
                )
                cleaned_component = np.zeros_like(component_pixels)
                cleaned_component[yy[~near_edge], xx[~near_edge]] = 1
                if np.count_nonzero(cleaned_component) >= min_area:
                    result[cleaned_component.astype(bool)] = 1
                else:
                    removed.append(label_id)
                continue

            kept.append(label_id)

        for label_id in kept:
            result[labels == label_id] = 1

        return result, {
            "component_count": int(count),
            "kept_components": len(kept),
            "removed_components": len(removed),
            "min_component_area": int(min_area),
        }

    def extract_signature_mask(
        self,
        image_path: Path,
    ) -> tuple[np.ndarray, dict]:
        rgb, alpha = self._load_rgba(image_path)
        gray = self._grayscale(rgb)
        canvas = self._canvas_mask(gray)
        candidate = self._candidate_mask(rgb, alpha)

        candidate = self._morph_open(candidate, size=3)
        candidate = self._morph_close(candidate, size=3)

        frame_candidate, frame_rois = self._frame_interior_mask(candidate)
        # فقط وقتی ROIهای معتبر قاب پیدا شدند از آن‌ها استفاده می‌کنیم؛
        # در غیر این صورت رفتار قبلی حفظ می‌شود.
        if frame_rois:
            candidate = frame_candidate

        if ndi is not None:
            labels, _ = ndi.label(
                canvas.astype(bool),
                structure=np.ones((3, 3), dtype=np.uint8),
            )
            objects = ndi.find_objects(labels)
        else:
            labels = None
            objects = [None]

        final = np.zeros_like(candidate, dtype=np.uint8)
        panel_stats = []

        if ndi is not None:
            for panel_id, slc in enumerate(objects, start=1):
                if slc is None:
                    continue
                panel = labels[slc] == panel_id
                panel_area = int(np.count_nonzero(panel))
                if panel_area < 0.015 * canvas.size:
                    continue
                local_candidate = candidate[slc] & panel
                selected, stats = self._select_signature_components(
                    local_candidate,
                    panel,
                )
                final[slc] |= selected
                panel_stats.append({"panel_id": panel_id, "area": panel_area, **stats})
        else:
            selected, stats = self._select_signature_components(
                candidate,
                canvas.astype(bool),
            )
            final |= selected
            panel_stats.append(stats)

        diagnostics = {
            "canvas_pixels": int(np.count_nonzero(canvas)),
            "candidate_pixels": int(np.count_nonzero(candidate)),
            "signature_pixels": int(np.count_nonzero(final)),
            "canvas_ratio": round(float(np.mean(canvas)), 6),
            "candidate_ratio": round(float(np.mean(candidate)), 6),
            "signature_ratio": round(float(np.mean(final)), 6),
            "panel_count": len(panel_stats),
            "panels": panel_stats,
            "frame_roi_count": len(frame_rois),
            "frame_rois": [
                {"bbox": item["bbox"]} for item in frame_rois
            ],
        }
        return final.astype(np.uint8), diagnostics

    # ========================================================
    # ZHANG-SUEN SKELETONIZATION
    # ========================================================

    @staticmethod
    def skeletonize(
        mask: np.ndarray,
        max_iterations: int = 100,
    ) -> np.ndarray:
        """
        Zhang-Suen thinning.
        بدون وابستگی به OpenCV/skimage.
        """

        img = (
            mask.astype(np.uint8) > 0
        ).astype(np.uint8)

        if not np.any(img):
            return img

        # skimage implementation is much faster for the large images in
        # library/. Zhang-Suen below remains the dependency-free fallback.
        if skimage_skeletonize is not None:
            return skimage_skeletonize(img > 0).astype(np.uint8)

        for _ in range(max_iterations):
            changed = False

            for step in (0, 1):
                p = np.pad(
                    img,
                    ((1, 1), (1, 1)),
                    mode="constant",
                )

                P2 = p[:-2, 1:-1]
                P3 = p[:-2, 2:]
                P4 = p[1:-1, 2:]
                P5 = p[2:, 2:]
                P6 = p[2:, 1:-1]
                P7 = p[2:, :-2]
                P8 = p[1:-1, :-2]
                P9 = p[:-2, :-2]

                neighbors = (
                    P2 + P3 + P4 + P5
                    + P6 + P7 + P8 + P9
                )

                transitions = (
                    (P2 == 0) & (P3 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P3 == 0) & (P4 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P4 == 0) & (P5 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P5 == 0) & (P6 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P6 == 0) & (P7 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P7 == 0) & (P8 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P8 == 0) & (P9 == 1)
                ).astype(np.uint8)
                transitions += (
                    (P9 == 0) & (P2 == 1)
                ).astype(np.uint8)

                if step == 0:
                    condition = (
                        (img == 1)
                        & (neighbors >= 2)
                        & (neighbors <= 6)
                        & (transitions == 1)
                        & ((P2 * P4 * P6) == 0)
                        & ((P4 * P6 * P8) == 0)
                    )
                else:
                    condition = (
                        (img == 1)
                        & (neighbors >= 2)
                        & (neighbors <= 6)
                        & (transitions == 1)
                        & ((P2 * P4 * P8) == 0)
                        & ((P2 * P6 * P8) == 0)
                    )

                if np.any(condition):
                    img[condition] = 0
                    changed = True

            if not changed:
                break

        return img.astype(np.uint8)

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

        total_pixels = width * height

        if ink_pixels == 0:
            return {
                "ink_pixels": 0,
                "ink_ratio": 0.0,
                "bbox_width_ratio": 0.0,
                "bbox_height_ratio": 0.0,
                "bbox_aspect_ratio": 0.0,
                "fill_ratio": 0.0,
            }

        ys, xs = np.where(mask > 0)

        min_x = int(xs.min())
        max_x = int(xs.max())
        min_y = int(ys.min())
        max_y = int(ys.max())

        bbox_width = max_x - min_x + 1
        bbox_height = max_y - min_y + 1
        bbox_area = bbox_width * bbox_height

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
                bbox_width / max(bbox_height, 1),
                6,
            ),
            "fill_ratio": round(
                ink_pixels / max(bbox_area, 1),
                6,
            ),
        }

    # ========================================================
    # PROJECTION
    # ========================================================

    @staticmethod
    def projection_features(
        mask: np.ndarray,
    ) -> dict:
        horizontal = np.sum(mask, axis=1)
        vertical = np.sum(mask, axis=0)

        return {
            "horizontal_max": int(
                horizontal.max()
            ) if horizontal.size else 0,
            "vertical_max": int(
                vertical.max()
            ) if vertical.size else 0,
            "horizontal_mean": round(
                float(horizontal.mean())
                if horizontal.size else 0.0,
                6,
            ),
            "vertical_mean": round(
                float(vertical.mean())
                if vertical.size else 0.0,
                6,
            ),
            "horizontal_variation": round(
                float(np.std(horizontal))
                if horizontal.size else 0.0,
                6,
            ),
            "vertical_variation": round(
                float(np.std(vertical))
                if vertical.size else 0.0,
                6,
            ),
        }

    # ========================================================
    # CENTER
    # ========================================================

    @staticmethod
    def center_features(
        mask: np.ndarray,
    ) -> dict:
        ys, xs = np.where(mask > 0)

        if len(xs) == 0:
            return {
                "center_x": 0.0,
                "center_y": 0.0,
            }

        height, width = mask.shape

        return {
            "center_x": round(
                float(xs.mean()) / width,
                6,
            ),
            "center_y": round(
                float(ys.mean()) / height,
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
        ys, xs = np.where(mask > 0)

        if len(xs) < 2:
            return {
                "dominant_angle": 0.0,
                "directional_variation": 0.0,
            }

        x_center = float(xs.mean())
        y_center = float(ys.mean())

        dx = xs.astype(np.float64) - x_center
        dy = ys.astype(np.float64) - y_center

        covariance = np.cov(dx, dy)

        eigenvalues, eigenvectors = np.linalg.eigh(
            covariance
        )

        index = int(
            np.argmax(eigenvalues)
        )

        vector = eigenvectors[:, index]

        angle = math.degrees(
            math.atan2(
                vector[1],
                vector[0],
            )
        )

        if angle < 0:
            angle += 180.0

        ratio = (
            float(eigenvalues[index])
            / max(
                float(eigenvalues.sum()),
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
    # SKELETON GRAPH FEATURES
    # ========================================================

    @staticmethod
    def _neighbor_coordinates(
        y: int,
        x: int,
        h: int,
        w: int,
    ) -> list[tuple[int, int]]:
        result = []

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue

                ny = y + dy
                nx = x + dx

                if (
                    0 <= ny < h
                    and 0 <= nx < w
                ):
                    result.append((ny, nx))

        return result

    @classmethod
    def _skeleton_degrees(
        cls,
        skeleton: np.ndarray,
    ) -> np.ndarray:
        padded = np.pad(
            skeleton,
            ((1, 1), (1, 1)),
            mode="constant",
        )

        degree = np.zeros_like(
            skeleton,
            dtype=np.uint8,
        )

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue

                degree += padded[
                    1 + dy:1 + dy + skeleton.shape[0],
                    1 + dx:1 + dx + skeleton.shape[1],
                ]

        degree *= skeleton

        return degree

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        while angle > math.pi:
            angle -= 2.0 * math.pi

        while angle < -math.pi:
            angle += 2.0 * math.pi

        return angle

    @classmethod
    def curvature_features(
        cls,
        mask: np.ndarray,
        skeleton: np.ndarray | None = None,
    ) -> dict:
        """
        curvature از skeleton استخراج می‌شود، اما دیگر به ازای هر pixel یک
        direction change ثبت نمی‌شود. نقاط turn با فاصله مکانی گروه‌بندی می‌شوند
        تا یک قوس بلند هزاران تغییر مصنوعی تولید نکند.
        """
        if skeleton is None:
            skeleton = cls.skeletonize(mask)

        if not np.any(skeleton):
            return {
                "curvature_proxy": 0.0,
                "direction_changes": 0,
                "path_length_proxy": 0.0,
            }

        h, w = skeleton.shape
        degrees = cls._skeleton_degrees(skeleton)

        turn_values: list[float] = []
        turn_points: list[tuple[int, int]] = []

        ys, xs = np.where(
            (skeleton > 0)
            & (degrees == 2)
        )

        for y, x in zip(ys, xs):
            neighbors = []
            for ny, nx in cls._neighbor_coordinates(
                int(y), int(x), h, w
            ):
                if skeleton[ny, nx]:
                    neighbors.append((ny, nx))

            if len(neighbors) != 2:
                continue

            (y1, x1), (y2, x2) = neighbors
            a1 = math.atan2(y1 - y, x1 - x)
            a2 = math.atan2(y2 - y, x2 - x)
            turn = abs(cls._wrap_angle(a2 - a1))
            deviation = abs(math.pi - turn)

            if deviation > math.radians(20):
                turn_values.append(deviation)
                turn_points.append((int(y), int(x)))

        # Group nearby turn pixels into one geometric event.
        direction_changes = 0
        if turn_points:
            cell = max(6, int(min(h, w) * 0.006))
            cells = {
                (y // cell, x // cell)
                for y, x in turn_points
            }

            # همسایگی سلول‌ها را یکی می‌کنیم تا یک قوس پیوسته یک event باشد.
            groups = []
            remaining = set(cells)
            while remaining:
                seed = remaining.pop()
                stack = [seed]
                group = {seed}
                while stack:
                    cy, cx = stack.pop()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if not dy and not dx:
                                continue
                            n = (cy + dy, cx + dx)
                            if n in remaining:
                                remaining.remove(n)
                                group.add(n)
                                stack.append(n)
                groups.append(group)

            direction_changes = len(groups)

        curvature = (
            float(np.mean(turn_values))
            if turn_values
            else 0.0
        )

        path_length = float(np.count_nonzero(skeleton))
        diagonal = math.sqrt(w ** 2 + h ** 2)

        return {
            "curvature_proxy": round(curvature, 6),
            "direction_changes": int(direction_changes),
            "path_length_proxy": round(
                path_length / max(diagonal, 1.0),
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
            "top_left": mask[:h2, :w2],
            "top_right": mask[:h2, w2:],
            "bottom_left": mask[h2:, :w2],
            "bottom_right": mask[h2:, w2:],
        }

        return {
            name: round(
                float(np.mean(zone))
                if zone.size
                else 0.0,
                6,
            )
            for name, zone in zones.items()
        }

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
                mask.astype(np.float32)
                - horizontal_flip.astype(np.float32)
            )
        )

        vertical_difference = np.mean(
            np.abs(
                mask.astype(np.float32)
                - vertical_flip.astype(np.float32)
            )
        )

        return {
            "horizontal_symmetry": round(
                1.0 - float(horizontal_difference),
                6,
            ),
            "vertical_symmetry": round(
                1.0 - float(vertical_difference),
                6,
            ),
        }

    # ========================================================
    # DEBUG ARTIFACTS
    # ========================================================

    def _save_debug_images(
        self,
        image_path: Path,
        candidate: np.ndarray,
        signature_mask: np.ndarray,
        skeleton: np.ndarray,
    ) -> dict:
        if not self.debug:
            return {}

        self.debug_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_hash = self.file_hash(
            image_path
        )[:16]

        prefix = (
            self.debug_dir
            / file_hash
        )

        candidate_path = prefix.with_name(
            prefix.name + "_candidate.png"
        )

        mask_path = prefix.with_name(
            prefix.name + "_signature_mask.png"
        )

        skeleton_path = prefix.with_name(
            prefix.name + "_skeleton.png"
        )

        # سفید = foreground
        Image.fromarray(
            (candidate * 255).astype(np.uint8)
        ).save(candidate_path)

        Image.fromarray(
            (signature_mask * 255).astype(np.uint8)
        ).save(mask_path)

        Image.fromarray(
            (skeleton * 255).astype(np.uint8)
        ).save(skeleton_path)

        return {
            "candidate_mask": str(candidate_path),
            "signature_mask": str(mask_path),
            "skeleton": str(skeleton_path),
        }

    # ========================================================
    # SINGLE IMAGE
    # ========================================================

    def analyze_image(
        self,
        image_path: str | Path,
    ) -> dict:
        image_path = Path(image_path)

        candidate = None
        signature_mask = None
        skeleton = None

        signature_mask, extraction = (
            self.extract_signature_mask(
                image_path
            )
        )

        skeleton = self.skeletonize(
            signature_mask
        )

        rgb, alpha = self._load_rgba(image_path)
        extraction_mask = self._candidate_mask(rgb, alpha)

        debug_paths = self._save_debug_images(
            image_path,
            extraction_mask,
            signature_mask,
            skeleton,
        )

        result = {
            "filename": image_path.name,
            "file_hash": self.file_hash(
                image_path
            ),
            "analyzer_version": self.VERSION,
            "pipeline_version": self.PIPELINE_VERSION,

            # مهم: تمام featureهای اصلی از signature_mask تمیز استخراج می‌شوند.
            "mask_features": self.mask_features(
                signature_mask
            ),
            "projection": self.projection_features(
                signature_mask
            ),
            "center": self.center_features(
                signature_mask
            ),
            "direction": self.directional_features(
                signature_mask
            ),
            "curvature": self.curvature_features(
                signature_mask,
                skeleton,
            ),
            "density_zones": self.density_zones(
                signature_mask
            ),
            "symmetry": self.symmetry_features(
                signature_mask
            ),

            "signature_extraction": extraction,
            "debug": debug_paths,
        }

        return result

    # ========================================================
    # KNOWLEDGE
    # ========================================================

    @staticmethod
    def _empty_knowledge() -> dict:
        return {
            "version": "0.2",
            "type": DeepVisualAnalyzer.KNOWLEDGE_TYPE,
            "source": {
                "learning_root": "library",
                "rule": "only_library_images",
            },
            "knowledge": {},
            "samples": [],
            "failed": [],
            "deep_visual_analysis": [],
            "signature_visual_analysis": [],
        }

    @staticmethod
    def load_knowledge(
        filename: str | Path,
    ) -> dict:
        filename = Path(filename)

        if not filename.exists():
            return DeepVisualAnalyzer._empty_knowledge()

        with open(
            filename,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(
                "Knowledge file must contain a JSON object."
            )

        defaults = DeepVisualAnalyzer._empty_knowledge()

        for key, value in defaults.items():
            data.setdefault(key, value)

        return data

    # ========================================================
    # EXISTING CURRENT-PIPELINE HASHES
    # ========================================================

    def _existing_current_hashes(
        self,
        data: dict,
    ) -> set[str]:
        hashes = set()

        # فقط pipeline جدید معتبر است.
        for item in data.get(
            "signature_visual_analysis",
            [],
        ):
            if (
                item.get("file_hash")
                and item.get("pipeline_version")
                == self.PIPELINE_VERSION
            ):
                hashes.add(
                    item["file_hash"]
                )

        return hashes

    # ========================================================
    # LIBRARY SCAN
    # ========================================================

    def _library_files(
        self,
        library_path: Path,
    ) -> list[Path]:
        return sorted(
            path
            for path in library_path.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower()
                in self.IMAGE_EXTENSIONS
                and ".signature_knowledge"
                not in path.parts
            )
        )

    # ========================================================
    # INCREMENTAL ANALYSIS
    # ========================================================

    def analyze_new_files(
        self,
        library_path: str | Path,
        knowledge_file: str | Path = "signature_knowledge.json",
    ) -> dict:
        """
        فقط فایل‌هایی که در pipeline فعلی قبلاً تحلیل نشده‌اند پردازش می‌شوند.

        اگر PIPELINE_VERSION تغییر کند:
            نمونه‌های قدیمی دوباره تحلیل می‌شوند،
            چون mask قدیمی دیگر قابل اعتماد نیست.

        این رفتار عمداً برای جلوگیری از آلودگی Knowledge با pipeline قبلی است.
        """

        library_path = Path(library_path)
        knowledge_file = Path(knowledge_file)

        if not library_path.exists():
            raise FileNotFoundError(
                f"Library not found: {library_path}"
            )

        data = self.load_knowledge(
            knowledge_file
        )

        existing = self._existing_current_hashes(
            data
        )

        files = self._library_files(
            library_path
        )

        pending: list[tuple[Path, str]] = []

        for path in files:
            try:
                file_hash = self.file_hash(path)
            except Exception:
                continue

            if file_hash not in existing:
                pending.append(
                    (path, file_hash)
                )

        total = len(pending)

        print()
        print("=" * 70)
        print("SIGNATURE-ONLY DEEP VISUAL ANALYSIS")
        print("=" * 70)
        print()
        print(f"Library files: {len(files)}")
        print(f"Already learned (current pipeline): {len(existing)}")
        print(f"New / reprocessable files: {total}")
        print(f"Pipeline: {self.PIPELINE_VERSION}")
        print()

        successful = 0
        failed: list[dict] = []

        # همیشه این list وجود داشته باشد.
        data.setdefault(
            "signature_visual_analysis",
            [],
        )

        for index, (path, file_hash) in enumerate(
            pending,
            start=1,
        ):
            try:
                result = self.analyze_image(path)

                data[
                    "signature_visual_analysis"
                ].append(result)

                successful += 1

            except Exception as exc:
                print()
                print("ERROR")
                print(f"File: {path}")
                print(f"Type: {type(exc).__name__}")
                print(f"Message: {exc}")
                traceback.print_exc()

                failed.append(
                    {
                        "filename": str(path),
                        "file_hash": file_hash,
                        "pipeline_version": self.PIPELINE_VERSION,
                        "error": str(exc),
                        "type": type(exc).__name__,
                    }
                )

            if (
                index == 1
                or index % 20 == 0
                or index == total
            ):
                print(
                    f"Processed: {index}/{total}"
                )

        # failedهای اجرای فعلی را append می‌کنیم، ولی دانش موفق قبلی دست‌نخورده می‌ماند.
        data.setdefault(
            "failed",
            [],
        )

        data["failed"].extend(
            failed
        )

        self._update_aggregate(
            data
        )

        data[
            "signature_visual_analysis_version"
        ] = self.VERSION

        data[
            "signature_visual_analysis_pipeline"
        ] = self.PIPELINE_VERSION

        data.setdefault(
            "source",
            {},
        )

        data["source"].update(
            {
                "learning_root": str(
                    library_path
                ),
                "rule": "only_library_images",
                "incremental": True,
                "file_identity": "sha256",
            }
        )

        knowledge_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

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
        print("=" * 70)
        print("SIGNATURE-ONLY ANALYSIS COMPLETE")
        print("=" * 70)
        print()
        print(
            f"Processed successfully: {successful}"
        )
        print(
            f"Failed: {len(failed)}"
        )
        print(
            f"Knowledge updated: {knowledge_file}"
        )
        print()

        return data

    # ========================================================
    # AGGREGATE KNOWLEDGE
    # ========================================================

    @staticmethod
    def _update_aggregate(
        data: dict,
    ) -> None:
        samples = [
            item
            for item in data.get(
                "signature_visual_analysis",
                [],
            )
            if (
                item.get("pipeline_version")
                == DeepVisualAnalyzer.PIPELINE_VERSION
            )
        ]

        if not samples:
            return

        def values(
            section: str,
            key: str,
        ) -> list[float]:
            result = []

            for item in samples:
                obj = item.get(section)

                if not isinstance(obj, dict):
                    continue

                value = obj.get(key)

                if isinstance(value, (int, float)):
                    result.append(float(value))

            return result

        def avg(
            vals: list[float],
        ) -> float:
            if not vals:
                return 0.0

            return round(
                sum(vals) / len(vals),
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
            "pipeline_version": DeepVisualAnalyzer.PIPELINE_VERSION,
            "sample_count": len(samples),
            "average_curvature": avg(
                values(
                    "curvature",
                    "curvature_proxy",
                )
            ),
            "average_directional_variation": avg(
                values(
                    "direction",
                    "directional_variation",
                )
            ),
            "average_path_length": avg(
                values(
                    "curvature",
                    "path_length_proxy",
                )
            ),
        }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    analyzer = DeepVisualAnalyzer(
        debug=False,
    )

    analyzer.analyze_new_files(
        library_path="library",
        knowledge_file="signature_knowledge.json",
    )