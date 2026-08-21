#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Signature Cleaner / Normalizer

Purpose:
  Convert heterogeneous signature images into a clean, uniform representation:
    - suppress background / texture
    - suppress borders, frames, logos and template text
    - keep likely signature strokes
    - produce a black-on-white normalized image and a binary mask

This is deliberately a deterministic CV pipeline. It does NOT overwrite originals.
For a large dataset, validate on a fixed test set first.

Dependencies: opencv-python, numpy, Pillow (Pillow only used for optional contact sheet).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import cv2
import numpy as np

IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}


def read_image(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    return img


def resize_work(img: np.ndarray, max_side: int = 1800):
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        out = cv2.resize(img, (round(w*scale), round(h*scale)), interpolation=cv2.INTER_AREA)
    else:
        out = img.copy()
    return out, scale


def robust_border_stats(img: np.ndarray, frac: float = 0.035):
    h, w = img.shape[:2]
    t = max(2, int(min(h, w) * frac))
    b = np.concatenate([
        img[:t].reshape(-1, 3), img[-t:].reshape(-1, 3),
        img[:, :t].reshape(-1, 3), img[:, -t:].reshape(-1, 3)
    ], axis=0)
    gray = cv2.cvtColor(b.reshape(-1,1,3), cv2.COLOR_BGR2GRAY).reshape(-1)
    return float(np.median(gray)), float(np.percentile(gray, 25)), float(np.percentile(gray, 75))


def remove_large_border_regions(mask: np.ndarray, border_frac: float = 0.02):
    """Remove large connected components that touch the outer image border.
    Small border-touching signature fragments are preserved.
    """
    h, w = mask.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = mask.copy()
    border = max(2, int(min(h, w) * border_frac))
    image_area = h * w
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        touches = x <= border or y <= border or x+ww >= w-border or y+hh >= h-border
        if touches and area > max(120, image_area * 0.00025):
            # Do not kill a small legitimate stroke merely because it touches the edge.
            if area > image_area * 0.001 or ww > w*0.20 or hh > h*0.20:
                out[labels == i] = 0
    return out


def suppress_template_bands(mask: np.ndarray, top=0.075, bottom=0.075, sides=0.055):
    """Suppress the most common template-only bands.
    These are intentionally modest; they do not consume the center of the page.
    """
    h, w = mask.shape
    out = mask.copy()
    out[:int(h*top), :] = 0
    out[int(h*(1-bottom)):, :] = 0
    out[:, :int(w*sides)] = 0
    out[:, int(w*(1-sides)):] = 0
    return out


def remove_straight_template_lines(mask: np.ndarray):
    """Remove long, very straight horizontal/vertical template rules.
    Signature strokes are usually curved/branched; only exceptionally long thin rules
    are removed here.
    """
    h, w = mask.shape
    work = mask.copy()
    # Long horizontal/vertical opening isolates straight rules.
    hk = max(25, w // 18)
    vk = max(25, h // 18)
    horiz = cv2.morphologyEx(work, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 1)))
    vert = cv2.morphologyEx(work, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk)))
    # Only remove rules that are very long relative to image size.
    rule = ((horiz > 0) | (vert > 0)).astype(np.uint8) * 255
    # Slightly thicken to erase antialiasing around the rule.
    rule = cv2.dilate(rule, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3)), 1)
    work[rule > 0] = 0
    return work


def remove_rectangular_frames(mask: np.ndarray):
    """Remove large rectangular frame contours while leaving interior strokes."""
    out = mask.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape
    for c in contours:
        area = cv2.contourArea(c)
        if area < h*w*0.008:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02*peri, True)
        if 4 <= len(approx) <= 6:
            x,y,ww,hh = cv2.boundingRect(c)
            if ww > w*0.15 and hh > h*0.10:
                # erase only the contour, not its interior
                cv2.drawContours(out, [c], -1, 0, thickness=max(2, min(h,w)//180))
    return out


def remove_round_template_rings(mask: np.ndarray):
    """Remove obvious large circular/elliptical rings used as template frames."""
    out = mask.copy()
    h, w = mask.shape
    circles = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, dp=1.2,
                               minDist=max(20, min(h,w)//5), param1=80,
                               param2=30, minRadius=max(12, min(h,w)//20),
                               maxRadius=max(20, min(h,w)//2))
    if circles is not None:
        circles = np.round(circles[0]).astype(int)
        for x,y,r in circles:
            # only erase a narrow ring
            cv2.circle(out, (x,y), r, 0, max(2, min(h,w)//170))
    return out


def build_foreground_mask(img: np.ndarray) -> np.ndarray:
    """Main segmentation stage.

    Strategy:
      1) estimate the local background with a large blur;
      2) score pixels by Lab/color distance from that background;
      3) use polarity-aware local contrast as a second signal;
      4) remove obvious template geometry and page bands.

    This is intentionally conservative: it tries to keep strong ink strokes while
    rejecting weak watermark/background texture.
    """
    work, _ = resize_work(img, max_side=1500)
    h, w = work.shape[:2]
    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB).astype(np.float32)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Large local background estimate. For wood/textured backgrounds this is much
    # more useful than a global threshold.
    kbg = max(31, int(min(h,w)*0.08) | 1)
    bg = cv2.GaussianBlur(lab, (kbg,kbg), 0)
    dist = np.sqrt(np.sum((lab-bg)**2, axis=2))

    # Local luminance contrast, useful for black ink on wood and white ink on black.
    g8 = np.uint8(np.clip(gray,0,255))
    k = max(21, int(min(h,w)*0.035) | 1)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k))
    blackhat = cv2.morphologyEx(g8, cv2.MORPH_BLACKHAT, ker).astype(np.float32)
    tophat = cv2.morphologyEx(g8, cv2.MORPH_TOPHAT, ker).astype(np.float32)

    border_med, _, _ = robust_border_stats(work)
    # Choose polarity from border/background brightness, but also allow mixed images.
    if border_med > 150:
        pol = blackhat
    elif border_med < 105:
        pol = tophat
    else:
        pol = np.maximum(blackhat, tophat)

    # Robust thresholds. Percentile-based scoring avoids hardcoding a single color.
    dthr = max(9.0, float(np.percentile(dist, 93)))
    pthr = max(7.0, float(np.percentile(pol, 90)))
    score = (dist / dthr) * 0.72 + (pol / pthr) * 0.28
    mask = (score > 1.0).astype(np.uint8)*255

    # Saturated colored ink (e.g. blue pen) can have lower luminance contrast.
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    sat = hsv[:,:,1].astype(np.float32)
    # High saturation relative to its local neighborhood is useful; keep it modest.
    sat_bg = cv2.GaussianBlur(sat, (kbg,kbg), 0)
    sat_delta = np.abs(sat-sat_bg)
    color_ink = (sat_delta > max(18, np.percentile(sat_delta, 94))).astype(np.uint8)*255
    mask = cv2.bitwise_or(mask, color_ink)

    # Morphology: preserve thin handwriting but eliminate isolated pixels.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2,2)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))

    # Template cleanup.
    mask = remove_straight_template_lines(mask)
    mask = remove_rectangular_frames(mask)
    # Circle detection is expensive and can remove genuine signature loops. Only use
    # it on images where the mask contains a large, clean circular component.
    mask = remove_round_template_rings(mask)
    mask = remove_large_border_regions(mask)

    # Fixed template bands: logos and legal/advertising text in these datasets are
    # concentrated near the page edges. Do not erase the center.
    mask = suppress_template_bands(mask, top=0.055, bottom=0.085, sides=0.025)

    # Component cleanup. Keep components that are small/elongated/branched, but reject
    # very dense rectangular blocks typical of logos and filled template graphics.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = np.zeros_like(mask)
    min_area = max(10, int(h*w*0.0000035))
    for i in range(1,n):
        x,y,ww,hh,area = stats[i]
        if area < min_area:
            continue
        fill = area / max(1, ww*hh)
        aspect = max(ww,hh) / max(1,min(ww,hh))
        # Remove solid blocks and giant banner-like pieces.
        if area > h*w*0.08 and fill > 0.28:
            continue
        if (ww > w*0.55 and hh < h*0.03) or (hh > h*0.55 and ww < w*0.03):
            continue
        # Corner logos are usually compact, dense rectangles; handwriting is sparse.
        in_corner = (x < w*0.18 or x+ww > w*0.82) and (y < h*0.18 or y+hh > h*0.82)
        if in_corner and fill > 0.32 and area > h*w*0.0003:
            continue
        out[labels == i] = 255

    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE,
                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    return out

def normalize_mask(mask: np.ndarray, target_long: int = 1600) -> np.ndarray:
    # Keep original geometry; just optionally scale the whole canvas down.
    h,w = mask.shape
    scale = min(1.0, target_long/max(h,w))
    if scale < 1:
        return cv2.resize(mask, (round(w*scale), round(h*scale)), interpolation=cv2.INTER_AREA)
    return mask


def make_clean(img: np.ndarray, mask: np.ndarray, preserve_color=False) -> np.ndarray:
    if preserve_color:
        bg = np.full_like(img, 255)
        # Keep the original ink color but suppress everything else.
        bg[mask > 0] = img[mask > 0]
        return bg
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Re-map selected strokes to black; background stays white.
    out = np.full_like(gray, 255)
    out[mask > 0] = 0
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def process_one(src: Path, out_dir: Path):
    img = read_image(src)
    mask_small = build_foreground_mask(img)
    # build_foreground_mask may work on a downscaled canvas for speed; restore the mask
    # to the original image dimensions before creating final outputs.
    if mask_small.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask_small, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    else:
        mask = mask_small
    clean_bw = make_clean(img, mask, preserve_color=False)
    clean_color = make_clean(img, mask, preserve_color=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    cv2.imwrite(str(out_dir / f"{stem}_mask.png"), mask)
    cv2.imwrite(str(out_dir / f"{stem}_clean_bw.png"), clean_bw)
    cv2.imwrite(str(out_dir / f"{stem}_clean_color.png"), clean_color)
    return mask, clean_bw, clean_color


def main():
    ap = argparse.ArgumentParser(description="Clean heterogeneous signature images")
    ap.add_argument("input", help="image file or directory")
    ap.add_argument("--output", default="cleaned_output")
    args = ap.parse_args()
    inp = Path(args.input)
    out = Path(args.output)
    files = [inp] if inp.is_file() else sorted(p for p in inp.rglob('*') if p.suffix.lower() in IMG_EXTS)
    if not files:
        raise SystemExit("No image files found")
    ok = 0
    for p in files:
        try:
            process_one(p, out)
            ok += 1
            print(f"OK  {p}")
        except Exception as e:
            print(f"ERR {p}: {e}")
    print(f"Processed {ok}/{len(files)} images")

if __name__ == "__main__":
    main()
