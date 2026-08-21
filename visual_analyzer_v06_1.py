# -*- coding: utf-8 -*-
"""
Signature Machine
Stage 2 - Deep Visual Analyzer v0.5

v0.5 changes:
1. Foreground polarity is detected from the image itself (black/white background).
2. No fixed assumption that dark pixels are ink.
3. Aggressive rectangular-outline trimming from v0.4 is removed.
4. Border/frame cleanup removes layout without cutting normal signature strokes.
5. Skeleton is generated from the cleaned signature mask.
6. Curvature/path analysis follows skeleton graph paths instead of sorting pixels by X.
7. Debug output is separated into foreground, cleaned mask, skeleton and overlay.

This file does NOT run the library automatically. The test runner is separate.
"""

from __future__ import annotations

import hashlib
import json
import math
import traceback
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

try:
    from scipy import ndimage as ndi
except Exception:
    ndi = None

try:
    from skimage.morphology import skeletonize as skimage_skeletonize
except Exception:
    skimage_skeletonize = None


class DeepVisualAnalyzer:
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    VERSION = "0.6.1"
    PIPELINE_VERSION = "signature_only_v6_1_safe_layout_strip_graph"
    KNOWLEDGE_TYPE = "signature_knowledge"

    def __init__(
        self,
        blur_radius: float = 0.4,
        min_component_pixels: int = 8,
        border_band_ratio: float = 0.018,
        debug: bool = False,
        debug_dir: str | Path = "test_debug_v06_1",
    ):
        self.blur_radius = blur_radius
        self.min_component_pixels = min_component_pixels
        self.border_band_ratio = border_band_ratio
        self.debug = debug
        self.debug_dir = Path(debug_dir)

    @staticmethod
    def file_hash(image_path: Path) -> str:
        sha = hashlib.sha256()
        with open(image_path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def _load(image_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        image = Image.open(image_path).convert("RGBA")
        rgba = np.asarray(image, dtype=np.uint8)
        rgb = rgba[:, :, :3]
        alpha = rgba[:, :, 3]
        gray = (
            0.299 * rgb[:, :, 0]
            + 0.587 * rgb[:, :, 1]
            + 0.114 * rgb[:, :, 2]
        ).astype(np.uint8)
        return rgb, gray, alpha

    @staticmethod
    def _otsu(values: np.ndarray) -> int:
        values = values.astype(np.uint8).ravel()
        if values.size == 0:
            return 128
        hist = np.bincount(values, minlength=256).astype(np.float64)
        total = hist.sum()
        if total <= 0:
            return 128
        cumulative = np.cumsum(hist)
        cumulative_mean = np.cumsum(hist * np.arange(256))
        global_mean = cumulative_mean[-1]
        denom = cumulative * (total - cumulative)
        denom[denom == 0] = 1.0
        between = (global_mean * cumulative - cumulative_mean) ** 2 / denom
        return int(np.argmax(between))

    def _detect_polarity(self, gray: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, dict]:
        h, w = gray.shape
        # Some of the signature PNGs in the test set carry the actual raster
        # information in RGB while their alpha channel is mostly 0/1 (a legacy
        # export/transparency artifact). Treating alpha as a hard visibility
        # mask in that case makes the whole image disappear and produces an
        # entirely black debug mask. Only trust alpha when it has a substantial
        # visible region; otherwise analyze RGB normally.
        alpha_visible_ratio = float(np.mean(alpha >= 16))
        alpha_nonzero_ratio = float(np.mean(alpha > 0))
        if alpha_visible_ratio >= 0.05:
            visible = alpha >= 16
            alpha_mode = "trusted"
        else:
            visible = np.ones_like(gray, dtype=bool)
            alpha_mode = "ignored_low_alpha_artifact"

        if not np.any(visible):
            return np.zeros_like(gray, dtype=np.uint8), {
                "polarity": "none",
                "threshold": 0,
                "border_fraction": 1.0,
                "alpha_mode": alpha_mode,
                "alpha_visible_ratio": round(alpha_visible_ratio, 6),
                "alpha_nonzero_ratio": round(alpha_nonzero_ratio, 6),
            }

        # v0.5 uses local contrast instead of a global grayscale threshold.
        # This is important for photographed paper, textured backgrounds and
        # images where a dark footer/header is present outside the signature.
        if ndi is not None:
            sigma = max(6.0, min(h, w) * 0.018)
            local_bg = ndi.gaussian_filter(gray.astype(np.float32), sigma=sigma)
        else:
            local_bg = gray.astype(np.float32)

        residual = gray.astype(np.float32) - local_bg
        av = np.abs(residual[visible])
        noise_level = float(np.percentile(av, 65)) if av.size else 0.0
        contrast_threshold = max(35.0, min(80.0, noise_level * 1.5))

        dark = (residual < -contrast_threshold) & visible
        light = (residual > contrast_threshold) & visible

        border = max(2, int(min(h, w) * 0.025))
        border_mask = np.zeros_like(visible, dtype=bool)
        border_mask[:border, :] = True
        border_mask[-border:, :] = True
        border_mask[:, :border] = True
        border_mask[:, -border:] = True

        dark_border = float(np.mean(dark[border_mask]))
        light_border = float(np.mean(light[border_mask]))
        dark_center = float(np.mean(dark[int(.08*h):int(.92*h), int(.08*w):int(.92*w)]))
        light_center = float(np.mean(light[int(.08*h):int(.92*h), int(.08*w):int(.92*w)]))

        # Prefer the polarity with the stronger central contrast and lower
        # border contamination. This works for black-on-white, white-on-black
        # and colored/photographic backgrounds.
        center = gray[int(.08*h):int(.92*h), int(.08*w):int(.92*w)][visible[int(.08*h):int(.92*h), int(.08*w):int(.92*w)]]
        median_center = float(np.median(center)) if center.size else 128.0
        p05 = float(np.percentile(center, 5)) if center.size else median_center
        p95 = float(np.percentile(center, 95)) if center.size else median_center
        low_deviation = median_center - p05
        high_deviation = p95 - median_center

        dark_score = dark_center * 4.0 - dark_border * 8.0
        light_score = light_center * 4.0 - light_border * 8.0

        # First use the dominant background level. This prevents a bright
        # signature on black from being mistaken for dark texture, and a black
        # signature on orange/white from being mistaken for bright highlights.
        if median_center < 80.0 and high_deviation > low_deviation * 1.15:
            mask = light
            polarity = "light_ink_on_dark_or_colored_background"
            chosen_border = light_border
        elif median_center > 190.0 and low_deviation > high_deviation * 1.15:
            mask = dark
            polarity = "dark_ink_on_light_or_colored_background"
            chosen_border = dark_border
        elif low_deviation > high_deviation * 1.25 and dark_center > 0.001:
            mask = dark
            polarity = "dark_ink_on_light_or_colored_background"
            chosen_border = dark_border
        elif high_deviation > low_deviation * 1.25 and light_center > 0.001:
            mask = light
            polarity = "light_ink_on_dark_or_colored_background"
            chosen_border = light_border
        elif dark_score > light_score and dark_center > 0.001:
            mask = dark
            polarity = "dark_ink_on_light_or_colored_background"
            chosen_border = dark_border
        elif light_center > 0.001:
            mask = light
            polarity = "light_ink_on_dark_or_colored_background"
            chosen_border = light_border
        else:
            # Fallback for extremely flat images.
            threshold = self._otsu(gray[visible])
            dark_global = (gray <= threshold) & visible
            light_global = (gray > threshold) & visible
            if float(np.mean(dark_global[border_mask])) < float(np.mean(light_global[border_mask])):
                mask = dark_global
                polarity = "dark_global_fallback"
                chosen_border = float(np.mean(dark_global[border_mask]))
            else:
                mask = light_global
                polarity = "light_global_fallback"
                chosen_border = float(np.mean(light_global[border_mask]))

        return mask.astype(np.uint8), {
            "polarity": polarity,
            "contrast_threshold": round(float(contrast_threshold), 4),
            "border_fraction": round(float(chosen_border), 6),
            "foreground_ratio_before_cleanup": round(float(np.mean(mask[visible])), 6),
            "alpha_mode": alpha_mode,
            "alpha_visible_ratio": round(alpha_visible_ratio, 6),
            "alpha_nonzero_ratio": round(alpha_nonzero_ratio, 6),
        }

    @staticmethod
    def _morph(mask: np.ndarray) -> np.ndarray:
        if ndi is None:
            return mask.astype(np.uint8)
        work = mask.astype(bool)
        # Small close/open only. v0.5 deliberately avoids aggressive morphology.
        work = ndi.binary_closing(work, structure=np.ones((3, 3), dtype=bool), iterations=1)
        work = ndi.binary_opening(work, structure=np.ones((2, 2), dtype=bool), iterations=1)
        return work.astype(np.uint8)

    @staticmethod
    def _component_data(mask: np.ndarray) -> tuple[np.ndarray, list[dict]]:
        if ndi is None:
            return mask.astype(np.int32), []
        labels, count = ndi.label(mask.astype(bool), structure=np.ones((3, 3), dtype=np.uint8))
        objects = ndi.find_objects(labels)
        components = []
        h, w = mask.shape
        for label_id, slc in enumerate(objects, start=1):
            if slc is None:
                continue
            area = int(np.count_nonzero(labels[slc] == label_id))
            y0, y1 = slc[0].start, slc[0].stop - 1
            x0, x1 = slc[1].start, slc[1].stop - 1
            bw = x1 - x0 + 1
            bh = y1 - y0 + 1
            touches_border = x0 <= 1 or y0 <= 1 or x1 >= w - 2 or y1 >= h - 2
            components.append({
                "label": label_id,
                "area": area,
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "width": bw, "height": bh,
                "touches_border": touches_border,
                "bbox_ratio": (bw * bh) / max(h * w, 1),
                "fill": area / max(bw * bh, 1),
            })
        return labels, components

    def _cleanup_layout(self, mask: np.ndarray) -> tuple[np.ndarray, dict]:
        if not np.any(mask):
            return mask.astype(np.uint8), {"removed_components": 0, "kept_components": 0}

        labels, components = self._component_data(mask)
        if not components:
            return mask.astype(np.uint8), {"removed_components": 0, "kept_components": 1}

        h, w = mask.shape
        image_area = h * w
        result = np.zeros_like(mask, dtype=np.uint8)
        removed = 0
        kept = 0

        for c in components:
            label_id = c["label"]
            area = c["area"]
            if area < self.min_component_pixels:
                removed += 1
                continue

            component = labels == label_id
            x0, x1 = c["x0"], c["x1"]
            y0, y1 = c["y0"], c["y1"]
            bw, bh = c["width"], c["height"]
            fill = c["fill"]

            # Layout objects touching the border are usually headers, footers,
            # frames, scan edges or photographed objects. Remove clearly layout-like
            # shapes completely; only use band-trimming for ambiguous components.
            if c["touches_border"] and c["bbox_ratio"] > 0.015:
                horizontal_layout = (
                    bw >= 0.50 * w and bh <= 0.12 * h
                )
                vertical_layout = (
                    bh >= 0.35 * h and bw <= 0.18 * w
                )
                giant_layout = (
                    c["bbox_ratio"] > 0.45 and fill < 0.55
                )
                if horizontal_layout or vertical_layout:
                    removed += 1
                    continue

                # IMPORTANT v0.6: never delete a giant component wholesale.
                # A signature can be connected to a frame/ring, and deleting
                # the whole component was the reason some samples became empty.
                # For giant/ambiguous border objects, strip only a narrow border
                # band and preserve everything in the interior.
                if giant_layout or c["touches_border"]:
                    band = max(3, int(min(h, w) * self.border_band_ratio))
                    inner = component.copy()
                    yy, xx = np.where(component)
                    edge = (
                        (xx <= band)
                        | (yy <= band)
                        | (xx >= w - 1 - band)
                        | (yy >= h - 1 - band)
                    )
                    inner[yy[edge], xx[edge]] = False
                    remaining = int(np.count_nonzero(inner))
                    if remaining >= self.min_component_pixels:
                        result[inner] = 1
                        kept += 1
                    else:
                        # Keep the original component as a last-resort fallback
                        # instead of returning an empty signature mask.
                        result[component] = 1
                        kept += 1
                    continue

            # Corner watermark boxes / logos: only remove when they are clearly
            # layout-like rectangular objects, not ordinary signature strokes.
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            near_corner = (cx < 0.20 * w or cx > 0.80 * w) and (cy < 0.20 * h or cy > 0.80 * h)
            rectangular = 0.75 <= bw / max(bh, 1) <= 3.2
            # Also catch thin outlined logo boxes: fill can be low because the
            # component is only the outline.
            yy, xx = np.where(component)
            if len(xx):
                left_frac = float(np.mean(xx <= x0 + max(2, int(bw * 0.025))))
                right_frac = float(np.mean(xx >= x1 - max(2, int(bw * 0.025))))
                top_frac = float(np.mean(yy <= y0 + max(2, int(bh * 0.025))))
                bottom_frac = float(np.mean(yy >= y1 - max(2, int(bh * 0.025))))
                outline_sides = sum(v > 0.025 for v in (left_frac, right_frac, top_frac, bottom_frac))
            else:
                outline_sides = 0
            large_corner_box = (
                near_corner
                and bw >= 0.08 * w
                and bh >= 0.035 * h
                and c["bbox_ratio"] >= 0.0010
                and rectangular
                and (fill >= 0.20 or outline_sides >= 3)
            )
            if large_corner_box:
                removed += 1
                continue

            # Do not use v0.4's rectangular-outline trimming. A signature itself
            # can easily look rectangular when its strokes surround empty space.
            result[component] = 1
            kept += 1

        return result, {
            "component_count": len(components),
            "removed_components": removed,
            "kept_components": kept,
        }

    def extract_signature_mask(self, image_path: Path) -> tuple[np.ndarray, dict]:
        rgb, gray, alpha = self._load(image_path)
        _ = rgb
        candidate, polarity = self._detect_polarity(gray, alpha)
        candidate = self._morph(candidate)
        cleaned, cleanup = self._cleanup_layout(candidate)

        # A tiny component filter after layout removal, but never a "largest
        # component only" rule: signatures can contain detached dots/strokes.
        if ndi is not None and np.any(cleaned):
            labels, count = ndi.label(cleaned.astype(bool), structure=np.ones((3, 3), dtype=np.uint8))
            objects = ndi.find_objects(labels)
            min_area = max(self.min_component_pixels, int(cleaned.size * 0.000002))
            filtered = np.zeros_like(cleaned, dtype=np.uint8)
            kept_small = 0
            for label_id, slc in enumerate(objects, start=1):
                if slc is None:
                    continue
                area = int(np.count_nonzero(labels[slc] == label_id))
                if area >= min_area:
                    filtered[labels == label_id] = 1
                    kept_small += 1
            if np.any(filtered):
                cleaned = filtered
            else:
                # Safety fallback: the previous filter must never turn a valid
                # candidate into a completely black image.
                cleaned = cleaned
            cleanup["post_filter_components"] = kept_small
            cleanup["post_filter_min_area"] = min_area

        diagnostics = {
            **polarity,
            **cleanup,
            "candidate_ratio": round(float(np.mean(candidate)), 6),
            "signature_ratio": round(float(np.mean(cleaned)), 6),
            "signature_pixels": int(np.count_nonzero(cleaned)),
        }
        return cleaned.astype(np.uint8), diagnostics

    @staticmethod
    def skeletonize(mask: np.ndarray) -> np.ndarray:
        if not np.any(mask):
            return np.zeros_like(mask, dtype=np.uint8)
        if skimage_skeletonize is not None:
            return skimage_skeletonize(mask > 0).astype(np.uint8)
        # Simple fallback: no thinning library available.
        return mask.astype(np.uint8)

    @staticmethod
    def mask_features(mask: np.ndarray) -> dict:
        h, w = mask.shape
        pixels = int(np.count_nonzero(mask))
        if pixels == 0:
            return {"ink_pixels": 0, "ink_ratio": 0.0, "bbox_width_ratio": 0.0,
                    "bbox_height_ratio": 0.0, "bbox_aspect_ratio": 0.0, "fill_ratio": 0.0}
        ys, xs = np.where(mask > 0)
        bw = int(xs.max() - xs.min() + 1)
        bh = int(ys.max() - ys.min() + 1)
        return {
            "ink_pixels": pixels,
            "ink_ratio": round(pixels / max(h * w, 1), 6),
            "bbox_width_ratio": round(bw / max(w, 1), 6),
            "bbox_height_ratio": round(bh / max(h, 1), 6),
            "bbox_aspect_ratio": round(bw / max(bh, 1), 6),
            "fill_ratio": round(pixels / max(bw * bh, 1), 6),
        }

    @staticmethod
    def projection_features(mask: np.ndarray) -> dict:
        horizontal = np.sum(mask, axis=1)
        vertical = np.sum(mask, axis=0)
        return {
            "horizontal_max": int(horizontal.max()) if horizontal.size else 0,
            "vertical_max": int(vertical.max()) if vertical.size else 0,
            "horizontal_mean": round(float(horizontal.mean()), 6) if horizontal.size else 0.0,
            "vertical_mean": round(float(vertical.mean()), 6) if vertical.size else 0.0,
            "horizontal_variation": round(float(np.std(horizontal)), 6) if horizontal.size else 0.0,
            "vertical_variation": round(float(np.std(vertical)), 6) if vertical.size else 0.0,
        }

    @staticmethod
    def center_features(mask: np.ndarray) -> dict:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return {"center_x": 0.0, "center_y": 0.0}
        h, w = mask.shape
        return {"center_x": round(float(xs.mean()) / w, 6), "center_y": round(float(ys.mean()) / h, 6)}

    @staticmethod
    def directional_features(mask: np.ndarray) -> dict:
        ys, xs = np.where(mask > 0)
        if len(xs) < 2:
            return {"dominant_angle": 0.0, "directional_variation": 0.0}
        cov = np.cov(xs.astype(float), ys.astype(float))
        vals, vecs = np.linalg.eigh(cov)
        i = int(np.argmax(vals))
        angle = math.degrees(math.atan2(vecs[1, i], vecs[0, i])) % 180.0
        ratio = float(vals[i]) / max(float(vals.sum()), 1e-9)
        return {"dominant_angle": round(angle, 6), "directional_variation": round(1.0 - ratio, 6)}

    @staticmethod
    def density_zones(mask: np.ndarray) -> dict:
        h, w = mask.shape
        h2, w2 = h // 2, w // 2
        zones = {
            "top_left": mask[:h2, :w2],
            "top_right": mask[:h2, w2:],
            "bottom_left": mask[h2:, :w2],
            "bottom_right": mask[h2:, w2:],
        }
        return {k: round(float(np.mean(v)), 6) if v.size else 0.0 for k, v in zones.items()}

    @staticmethod
    def symmetry_features(mask: np.ndarray) -> dict:
        hf = np.flip(mask, axis=1)
        vf = np.flip(mask, axis=0)
        hd = float(np.mean(np.abs(mask.astype(np.float32) - hf.astype(np.float32))))
        vd = float(np.mean(np.abs(mask.astype(np.float32) - vf.astype(np.float32))))
        return {"horizontal_symmetry": round(1.0 - hd, 6), "vertical_symmetry": round(1.0 - vd, 6)}

    @staticmethod
    def _degree_map(skeleton: np.ndarray) -> np.ndarray:
        if ndi is not None:
            kernel = np.ones((3, 3), dtype=np.uint8)
            kernel[1, 1] = 0
            return (ndi.convolve(skeleton.astype(np.uint8), kernel, mode="constant", cval=0) * skeleton).astype(np.uint8)
        padded = np.pad(skeleton, 1)
        deg = np.zeros_like(skeleton, dtype=np.uint8)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    deg += padded[1 + dy:1 + dy + skeleton.shape[0], 1 + dx:1 + dx + skeleton.shape[1]]
        return (deg * skeleton).astype(np.uint8)

    @staticmethod
    def _neighbors(y: int, x: int, skeleton: np.ndarray) -> list[tuple[int, int]]:
        h, w = skeleton.shape
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if not (dx or dy):
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and skeleton[ny, nx]:
                    out.append((ny, nx))
        return out

    @classmethod
    def _trace_graph(cls, skeleton: np.ndarray) -> tuple[list[list[tuple[int, int]]], dict]:
        """Trace skeleton into edge paths between endpoints/junctions."""
        if not np.any(skeleton):
            return [], {"nodes": 0, "endpoints": 0, "junctions": 0, "graph_components": 0, "loops": 0}

        degree = cls._degree_map(skeleton)
        node_pixels = set(map(tuple, np.argwhere((skeleton > 0) & (degree != 2))))
        endpoints = sum(1 for p in node_pixels if degree[p] == 1)
        junctions = sum(1 for p in node_pixels if degree[p] >= 3)

        visited_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        paths: list[list[tuple[int, int]]] = []

        def edge_key(a, b):
            return (a, b) if a <= b else (b, a)

        for node in list(node_pixels):
            for nxt in cls._neighbors(node[0], node[1], skeleton):
                key = edge_key(node, nxt)
                if key in visited_edges:
                    continue
                path = [node]
                prev = node
                cur = nxt
                visited_edges.add(key)
                while True:
                    path.append(cur)
                    if cur in node_pixels and cur != node:
                        break
                    ns = [p for p in cls._neighbors(cur[0], cur[1], skeleton) if p != prev]
                    if not ns:
                        break
                    # Prefer the continuation with the smallest turn.
                    if len(ns) > 1:
                        vx, vy = cur[1] - prev[1], cur[0] - prev[0]
                        best = None
                        best_score = None
                        for candidate in ns:
                            cx, cy = candidate[1] - cur[1], candidate[0] - cur[0]
                            n1 = math.hypot(vx, vy) or 1.0
                            n2 = math.hypot(cx, cy) or 1.0
                            score = (vx * cx + vy * cy) / (n1 * n2)
                            if best_score is None or score > best_score:
                                best_score, best = score, candidate
                        nxt2 = best
                    else:
                        nxt2 = ns[0]
                    visited_edges.add(edge_key(cur, nxt2))
                    prev, cur = cur, nxt2
                if len(path) >= 2:
                    paths.append(path)

        # Pure cycles have no node pixels. Trace each remaining skeleton pixel cycle.
        remaining = set(map(tuple, np.argwhere(skeleton > 0)))
        used_pixels = set(p for path in paths for p in path)
        remaining -= used_pixels
        while remaining:
            start = next(iter(remaining))
            path = [start]
            prev = None
            cur = start
            for _ in range(max(16, skeleton.size)):
                remaining.discard(cur)
                ns = [p for p in cls._neighbors(cur[0], cur[1], skeleton) if p != prev]
                if not ns:
                    break
                nxt = ns[0]
                if nxt == start:
                    path.append(nxt)
                    break
                prev, cur = cur, nxt
                if cur in path:
                    break
                path.append(cur)
            if len(path) >= 3:
                paths.append(path)

        if ndi is not None:
            _, graph_components = ndi.label(skeleton.astype(bool), structure=np.ones((3, 3), dtype=np.uint8))
        else:
            graph_components = 1

        # Euler cycle estimate: E - V + C. We approximate edges by local adjacency.
        v = int(np.count_nonzero(skeleton))
        e = 0
        ys, xs = np.where(skeleton > 0)
        for y, x in zip(ys, xs):
            for ny, nx in cls._neighbors(int(y), int(x), skeleton):
                if (ny > y) or (ny == y and nx > x):
                    e += 1
        loops = max(0, int(e - v + graph_components))

        return paths, {
            "nodes": len(node_pixels),
            "endpoints": int(endpoints),
            "junctions": int(junctions),
            "graph_components": int(graph_components),
            "loops": loops,
        }

    @staticmethod
    def _path_metrics(path: list[tuple[int, int]]) -> tuple[float, float, int]:
        if len(path) < 4:
            return 0.0, 0.0, 0

        pts = np.asarray([(x, y) for y, x in path], dtype=np.float64)
        diffs = np.diff(pts, axis=0)
        lengths = np.linalg.norm(diffs, axis=1)
        valid = lengths > 0
        diffs = diffs[valid]
        lengths = lengths[valid]
        if len(diffs) < 3:
            return float(lengths.sum()), 0.0, 0

        cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
        total_length = float(cumulative[-1])
        if total_length < 6.0:
            return total_length, 0.0, 0

        # Measure tangent direction several pixels apart. This suppresses
        # one-pixel staircase jitter from raster skeletons.
        step = max(3.0, min(10.0, total_length * 0.025))
        positions = np.arange(0.0, total_length + 1e-6, step)
        if positions[-1] < total_length:
            positions = np.append(positions, total_length)

        xs = np.interp(positions, cumulative, pts[:, 0], left=pts[0, 0], right=pts[-1, 0])
        ys = np.interp(positions, cumulative, pts[:, 1], left=pts[0, 1], right=pts[-1, 1])
        smooth = np.column_stack([xs, ys])
        tangent = np.diff(smooth, axis=0)
        tlen = np.linalg.norm(tangent, axis=1)
        valid = tlen > 0
        tangent = tangent[valid]
        if len(tangent) < 2:
            return total_length, 0.0, 0

        angles = np.unwrap(np.arctan2(tangent[:, 1], tangent[:, 0]))
        changes = np.abs(np.diff(angles))
        # Cap individual jumps so a graph junction does not dominate the mean.
        changes = np.minimum(changes, math.pi)
        meaningful = changes > math.radians(25)
        return total_length, float(np.sum(changes)), int(np.count_nonzero(meaningful))

    @classmethod
    def curvature_features(cls, skeleton: np.ndarray) -> dict:
        paths, graph = cls._trace_graph(skeleton)
        total_length = 0.0
        total_turn = 0.0
        direction_changes = 0
        for path in paths:
            length, turn, changes = cls._path_metrics(path)
            total_length += length
            total_turn += turn
            direction_changes += changes
        h, w = skeleton.shape
        diagonal = math.hypot(w, h)
        curvature = total_turn / max(total_length, 1e-9)
        return {
            "curvature_proxy": round(curvature, 6),
            "direction_changes": int(direction_changes),
            "path_length_proxy": round(total_length / max(diagonal, 1.0), 6),
            "skeleton_pixels": int(np.count_nonzero(skeleton)),
            "graph": graph,
            "traced_paths": len(paths),
        }

    def _save_debug(self, image_path: Path, foreground: np.ndarray, signature: np.ndarray, skeleton: np.ndarray) -> dict:
        if not self.debug:
            return {}
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        prefix = self.debug_dir / self.file_hash(image_path)[:16]
        fg_path = prefix.with_name(prefix.name + "_foreground.png")
        mask_path = prefix.with_name(prefix.name + "_signature_mask.png")
        sk_path = prefix.with_name(prefix.name + "_skeleton.png")
        overlay_path = prefix.with_name(prefix.name + "_overlay.png")

        # Save every debug stage as explicit 8-bit grayscale/RGB.
        # v0.6.1 also verifies the written overlay so a silent all-black
        # debug artifact can never be mistaken for a successful extraction.
        fg_u8 = np.where(foreground > 0, 255, 0).astype(np.uint8)
        sig_u8 = np.where(signature > 0, 255, 0).astype(np.uint8)
        sk_u8 = np.where(skeleton > 0, 255, 0).astype(np.uint8)
        Image.fromarray(fg_u8, mode="L").save(fg_path)
        Image.fromarray(sig_u8, mode="L").save(mask_path)
        Image.fromarray(sk_u8, mode="L").save(sk_path)

        base = np.zeros((signature.shape[0], signature.shape[1], 3), dtype=np.uint8)
        base[sig_u8 > 0] = 220
        base[sk_u8 > 0] = 255
        Image.fromarray(base, mode="RGB").save(overlay_path)
        # Read back and validate the actual file, not just the in-memory array.
        written = np.asarray(Image.open(overlay_path).convert("RGB"))
        if np.count_nonzero(written) == 0 and np.count_nonzero(sig_u8) > 0:
            raise RuntimeError("DEBUG_OVERLAY_WRITE_FAILED: signature mask is non-empty but overlay file is all black")
        return {
            "foreground": str(fg_path),
            "signature_mask": str(mask_path),
            "skeleton": str(sk_path),
            "overlay": str(overlay_path),
        }

    def analyze_image(self, image_path: str | Path) -> dict:
        image_path = Path(image_path)
        rgb, gray, alpha = self._load(image_path)
        _ = rgb, gray, alpha
        signature_mask, extraction = self.extract_signature_mask(image_path)
        skeleton = self.skeletonize(signature_mask)
        foreground, _ = self._detect_polarity(gray, alpha)
        return {
            "filename": image_path.name,
            "path": str(image_path),
            "file_hash": self.file_hash(image_path),
            "analyzer_version": self.VERSION,
            "pipeline_version": self.PIPELINE_VERSION,
            "mask_features": self.mask_features(signature_mask),
            "projection": self.projection_features(signature_mask),
            "center": self.center_features(signature_mask),
            "direction": self.directional_features(signature_mask),
            "curvature": self.curvature_features(skeleton),
            "density_zones": self.density_zones(signature_mask),
            "symmetry": self.symmetry_features(signature_mask),
            "signature_extraction": extraction,
            "debug": self._save_debug(image_path, foreground, signature_mask, skeleton),
        }

    @staticmethod
    def load_knowledge(filename: str | Path) -> dict:
        filename = Path(filename)
        if not filename.exists():
            return {
                "version": "0.5",
                "type": DeepVisualAnalyzer.KNOWLEDGE_TYPE,
                "source": {},
                "knowledge": {},
                "samples": [],
                "failed": [],
                "signature_visual_analysis": [],
            }
        data = json.loads(filename.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Knowledge file must contain a JSON object.")
        data.setdefault("signature_visual_analysis", [])
        data.setdefault("knowledge", {})
        return data

    def analyze_new_files(self, library_path: str | Path, knowledge_file: str | Path = "signature_knowledge.json") -> dict:
        library_path = Path(library_path)
        knowledge_file = Path(knowledge_file)
        if not library_path.exists():
            raise FileNotFoundError(f"Library not found: {library_path}")
        data = self.load_knowledge(knowledge_file)
        current = {
            item.get("file_hash") for item in data.get("signature_visual_analysis", [])
            if item.get("pipeline_version") == self.PIPELINE_VERSION and item.get("file_hash")
        }
        files = sorted(
            p for p in library_path.rglob("*")
            if p.is_file() and p.suffix.lower() in self.IMAGE_EXTENSIONS and ".signature_knowledge" not in p.parts
        )
        pending = []
        for p in files:
            try:
                h = self.file_hash(p)
            except Exception:
                continue
            if h not in current:
                pending.append((p, h))

        print("=" * 70)
        print("SIGNATURE-ONLY DEEP VISUAL ANALYSIS V0.5")
        print("=" * 70)
        print(f"Library files: {len(files)}")
        print(f"Pending:       {len(pending)}")
        print(f"Pipeline:      {self.PIPELINE_VERSION}")

        failed = []
        for i, (path, file_hash) in enumerate(pending, 1):
            try:
                data["signature_visual_analysis"].append(self.analyze_image(path))
            except Exception as exc:
                traceback.print_exc()
                failed.append({"filename": str(path), "file_hash": file_hash, "type": type(exc).__name__, "error": str(exc)})
            if i == 1 or i % 20 == 0 or i == len(pending):
                print(f"Processed: {i}/{len(pending)}")

        data["failed"] = data.get("failed", []) + failed
        data["deep_visual_analysis_version"] = self.VERSION
        knowledge_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data


if __name__ == "__main__":
    print("visual_analyzer_v05.py loaded successfully.")
    print("Use test_visual_analyzer_v05.py for the 20-sample test.")