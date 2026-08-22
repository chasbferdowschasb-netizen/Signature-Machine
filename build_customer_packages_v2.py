# -*- coding: utf-8 -*-
"""
Customer Package Builder v2
SAFE DEFAULT: build one sample at a time with --sample.
Does NOT modify ENGINE_DATA (raw.png, render.png, strokes.json, metadata.json).

Package:
CUSTOMER_PACKAGE/
  01_FINAL_ASSETS/
    01_FINAL_BLACK_ON_WHITE.png
    02_BLACK_TRANSPARENT.png
    03_WHITE_ON_BLACK.png
    04_WHITE_TRANSPARENT.png
  02_TRAINING/
    01_PRACTICE.pdf
    01_TRAINING.mp4
  manifest.json
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "online_training_data" / "reference_learning" / "samples"

PACKAGE_REL = Path("CUSTOMER_PACKAGE")
FINAL_REL = PACKAGE_REL / "01_FINAL_ASSETS"
TRAIN_REL = PACKAGE_REL / "02_TRAINING"

PRACTICE_COPIES = 20
PRACTICE_ALPHA = 0.48          # darker for physical printing
VIDEO_FPS = 60
VIDEO_W = 1280
VIDEO_H = 720
VIDEO_MARGIN_X = 0.10
VIDEO_MARGIN_Y = 0.18
VIDEO_MIN_SEC = 5.0
VIDEO_MAX_SEC = 20.0
VIDEO_PATH_SPEED = 115.0


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def alpha_from_image(path: Path) -> np.ndarray:
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im, dtype=np.uint8)
    rgb = a[..., :3].astype(np.float32)
    alpha = a[..., 3].astype(np.float32)
    gray = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    darkness = np.clip(255.0 - gray, 0, 255)

    # For white-background black-ink images, darkness is the useful coverage.
    if np.mean(alpha < 250) > 0.05:
        ink = np.maximum(darkness, alpha)
    else:
        ink = darkness

    ink[gray > 250] = 0
    return np.clip(ink, 0, 255).astype(np.uint8)


def signature_bbox(alpha: np.ndarray, pad_ratio: float = 0.035):
    ys, xs = np.where(alpha > 8)
    h, w = alpha.shape
    if len(xs) == 0:
        return 0, 0, w, h

    pad = max(8, int(round(min(w, h) * pad_ratio)))
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(w, int(xs.max()) + 1 + pad)
    y1 = min(h, int(ys.max()) + 1 + pad)
    return x0, y0, x1, y1


def build_final_assets(sample_dir: Path, final_dir: Path):
    # Prefer render.png because it is already the high-resolution browser render.
    source = sample_dir / "render.png"
    if not source.exists():
        source = sample_dir / "raw.png"
    if not source.exists():
        raise FileNotFoundError("Neither render.png nor raw.png exists.")

    im = Image.open(source).convert("RGBA")
    alpha = alpha_from_image(source)
    x0, y0, x1, y1 = signature_bbox(alpha)
    crop = alpha[y0:y1, x0:x1]

    # IMPORTANT:
    # Do NOT force a target size and do NOT upscale.
    # Preserve the actual high-resolution crop produced by online_training.html.
    mask = Image.fromarray(crop, "L")

    black_trans = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    black_trans.paste((0, 0, 0, 255), mask=mask)
    black_trans.save(final_dir / "02_BLACK_TRANSPARENT.png", optimize=True)

    white_trans = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    white_trans.paste((255, 255, 255, 255), mask=mask)
    white_trans.save(final_dir / "04_WHITE_TRANSPARENT.png", optimize=True)

    black_white = Image.new("RGBA", mask.size, (255, 255, 255, 255))
    black_white.paste((0, 0, 0, 255), mask=mask)
    black_white.convert("RGB").save(final_dir / "01_FINAL_BLACK_ON_WHITE.png", optimize=True)

    white_black = Image.new("RGBA", mask.size, (0, 0, 0, 255))
    white_black.paste((255, 255, 255, 255), mask=mask)
    white_black.convert("RGB").save(final_dir / "03_WHITE_ON_BLACK.png", optimize=True)

    return {
        "source": source.name,
        "crop": {"x": x0, "y": y0, "width": x1-x0, "height": y1-y0},
        "output_size": {"width": mask.width, "height": mask.height},
        "upscaled": False,
    }


def pressure_value(p):
    try:
        return max(0.0, min(1.0, float(p)))
    except Exception:
        return 0.5


def point_xy(p):
    return float(p["x"]), float(p["y"])


def stroke_length(points):
    if len(points) < 2:
        return 1.0
    total = 0.0
    for a, b in zip(points, points[1:]):
        x0, y0 = point_xy(a)
        x1, y1 = point_xy(b)
        total += math.hypot(x1-x0, y1-y0)
    return max(total, 1.0)


def catmull_rom(points, samples_per_segment=10):
    """Smooth geometry only for video rendering. Raw strokes remain untouched."""
    if not points:
        return []
    if len(points) == 1:
        x, y = point_xy(points[0])
        return [(x, y, pressure_value(points[0].get("pressure")))]

    P = [
        (float(p["x"]), float(p["y"]), pressure_value(p.get("pressure")))
        for p in points
    ]
    if len(P) == 2:
        return P

    out = [P[0]]
    for i in range(len(P)-1):
        p0 = P[max(0, i-1)]
        p1 = P[i]
        p2 = P[i+1]
        p3 = P[min(len(P)-1, i+2)]

        for k in range(1, samples_per_segment + 1):
            t = k / samples_per_segment
            t2 = t*t
            t3 = t2*t

            def cr(a0, a1, a2, a3):
                return 0.5 * (
                    2*a1 +
                    (-a0+a2)*t +
                    (2*a0-5*a1+4*a2-a3)*t2 +
                    (-a0+3*a1-3*a2+a3)*t3
                )

            x = cr(p0[0], p1[0], p2[0], p3[0])
            y = cr(p0[1], p1[1], p2[1], p3[1])
            pr = max(0.0, min(1.0, cr(p0[2], p1[2], p2[2], p3[2])))
            out.append((x, y, pr))
    return out


def make_training_video(sample_dir: Path, video_path: Path):
    data = load_json(sample_dir / "strokes.json")
    strokes = [s for s in data.get("strokes", []) if s.get("points")]
    if not strokes:
        raise ValueError("No strokes in strokes.json")

    raw_path = sample_dir / "raw.png"
    render_path = sample_dir / "render.png"
    if not raw_path.exists():
        raise FileNotFoundError("raw.png is required for coordinate mapping.")

    raw_im = Image.open(raw_path).convert("RGBA")
    raw_w, raw_h = raw_im.size
    alpha = alpha_from_image(raw_path)
    bx0, by0, bx1, by1 = signature_bbox(alpha, pad_ratio=0.02)

    # Determine the natural signature box from the raw Canvas.
    sig_w = max(1, bx1-bx0)
    sig_h = max(1, by1-by0)

    # Fit the signature into the center of a 1280x720 teaching frame.
    usable_w = int(VIDEO_W * (1.0 - 2*VIDEO_MARGIN_X))
    usable_h = int(VIDEO_H * (1.0 - 2*VIDEO_MARGIN_Y))
    scale = min(usable_w / sig_w, usable_h / sig_h)

    # Avoid excessive enlargement of tiny raw images; the high-res render is used
    # as the visual reference, but stroke coordinates remain in raw space.
    scale = min(scale, 3.0)

    placed_w = sig_w * scale
    placed_h = sig_h * scale
    off_x = (VIDEO_W - placed_w) / 2.0
    off_y = (VIDEO_H - placed_h) / 2.0

    def map_xy(x, y):
        return (off_x + (x-bx0)*scale, off_y + (y-by0)*scale)

    lengths = [stroke_length(s["points"]) for s in strokes]
    total_len = max(sum(lengths), 1.0)
    duration = max(VIDEO_MIN_SEC, min(VIDEO_MAX_SEC, total_len / VIDEO_PATH_SPEED))
    min_dur = 0.22
    base = [max(min_dur, duration*L/total_len) for L in lengths]
    factor = duration / sum(base)
    durations = [d*factor for d in base]

    timeline = []
    cursor = 0.0

    for stroke, dur in zip(strokes, durations):
        smooth = catmull_rom(stroke["points"], samples_per_segment=10)
        if not smooth:
            continue

        times = np.linspace(cursor, cursor+dur, len(smooth))
        timeline.append([
            (*map_xy(x, y), p, float(t))
            for (x, y, p), t in zip(smooth, times)
        ])
        cursor += dur

    # Use a high-quality intermediate frame and downsample for anti-aliasing.
    R = 2
    FW, FH = VIDEO_W*R, VIDEO_H*R

    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        VIDEO_FPS,
        (VIDEO_W, VIDEO_H),
    )
    if not writer.isOpened():
        raise RuntimeError("Could not create MP4 writer.")

    frames = max(1, int(math.ceil(cursor*VIDEO_FPS)))

    for fi in range(frames):
        t = fi / VIDEO_FPS
        hi = np.full((FH, FW, 3), 255, dtype=np.uint8)

        for pts in timeline:
            if not pts or t < pts[0][3]:
                continue

            visible = []
            for j, (x, y, p, tt) in enumerate(pts):
                if t >= tt:
                    visible.append((x, y, p))
                else:
                    if j > 0:
                        x0, y0, p0, t0 = pts[j-1]
                        f = max(0.0, min(1.0, (t-t0)/max(tt-t0, 1e-9)))
                        visible.append((
                            x0+(x-x0)*f,
                            y0+(y-y0)*f,
                            p0+(p-p0)*f
                        ))
                    break

            if len(visible) >= 2:
                for a, b in zip(visible, visible[1:]):
                    x0,y0,p0 = a
                    x1,y1,p1 = b
                    width = max(2, int(round((1.25 + ((p0+p1)/2)*5.2)*R)))
                    cv2.line(
                        hi,
                        (int(round(x0*R)), int(round(y0*R))),
                        (int(round(x1*R)), int(round(y1*R))),
                        (0,0,0),
                        width,
                        cv2.LINE_AA
                    )
            elif len(visible) == 1:
                x,y,p = visible[0]
                radius = max(1, int(round((1.25+p*2.6)*R)))
                cv2.circle(
                    hi,
                    (int(round(x*R)), int(round(y*R))),
                    radius,
                    (0,0,0),
                    -1,
                    cv2.LINE_AA
                )

        frame = cv2.resize(hi, (VIDEO_W, VIDEO_H), interpolation=cv2.INTER_AREA)
        writer.write(frame)

    writer.release()

    return {
        "duration_seconds": round(cursor, 2),
        "fps": VIDEO_FPS,
        "frame_size": [VIDEO_W, VIDEO_H],
        "centered": True,
        "idle_gaps_removed": True,
        "smooth_rendering": True,
        "raw_coordinates_preserved": True,
        "source_signature_bbox": [bx0, by0, bx1, by1],
        "scale": round(scale, 4),
    }


def make_practice_pdf(sample_dir: Path, pdf_path: Path):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "reportlab is not installed. Run: python -m pip install reportlab"
        ) from e

    source = sample_dir / "render.png"
    if not source.exists():
        source = sample_dir / "raw.png"

    alpha = alpha_from_image(source)
    x0,y0,x1,y1 = signature_bbox(alpha, pad_ratio=0.02)
    crop = alpha[y0:y1, x0:x1]

    # Darker, printable faint guide.
    rgba = np.zeros((crop.shape[0], crop.shape[1], 4), dtype=np.uint8)
    rgba[..., 0:3] = 95
    rgba[..., 3] = np.clip(crop.astype(np.float32) * PRACTICE_ALPHA, 0, 255).astype(np.uint8)

    temp = sample_dir / ".practice_faint.png"
    Image.fromarray(rgba, "RGBA").save(temp)

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    W,H = A4

    c.setFillColorRGB(0.35,0.35,0.35)
    c.setFont("Helvetica", 11)
    c.drawString(18*mm, H-15*mm, "Signature Practice")

    cols, rows = 4, 5
    margin_x = 9*mm
    top = 22*mm
    bottom = 7*mm
    cell_w = (W-2*margin_x)/cols
    cell_h = (H-top-bottom)/rows

    iw, ih = crop.shape[1], crop.shape[0]

    for i in range(PRACTICE_COPIES):
        r, cidx = divmod(i, cols)
        maxw = cell_w*0.90
        maxh = cell_h*0.68
        scale = min(maxw/iw, maxh/ih)
        dw, dh = iw*scale, ih*scale
        x = margin_x + cidx*cell_w + (cell_w-dw)/2
        y = H-top-(r+1)*cell_h + (cell_h-dh)/2

        c.drawImage(
            str(temp), x, y,
            width=dw, height=dh,
            mask="auto",
            preserveAspectRatio=True
        )
        c.setFillColorRGB(0.50,0.50,0.50)
        c.setFont("Helvetica", 6.5)
        c.drawString(x+2, y+2, str(i+1))

    c.save()
    temp.unlink(missing_ok=True)


def clean_training_dir(train_dir: Path):
    train_dir.mkdir(parents=True, exist_ok=True)
    for p in list(train_dir.iterdir()):
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)


def build_sample(sample_dir: Path, overwrite=True):
    if not sample_dir.is_dir():
        return False, "sample directory missing"
    if not (sample_dir/"strokes.json").exists():
        return False, "missing strokes.json"
    if not (sample_dir/"raw.png").exists() and not (sample_dir/"render.png").exists():
        return False, "missing raw.png/render.png"

    package = sample_dir/PACKAGE_REL
    final_dir = sample_dir/FINAL_REL
    train_dir = sample_dir/TRAIN_REL

    # For a controlled rebuild, delete only the CUSTOMER_PACKAGE.
    if overwrite and package.exists():
        shutil.rmtree(package)

    final_dir.mkdir(parents=True, exist_ok=True)
    train_dir.mkdir(parents=True, exist_ok=True)

    final_info = build_final_assets(sample_dir, final_dir)
    clean_training_dir(train_dir)

    video_info = make_training_video(
        sample_dir,
        train_dir/"01_TRAINING.mp4"
    )
    make_practice_pdf(
        sample_dir,
        train_dir/"01_PRACTICE.pdf"
    )

    meta = {}
    if (sample_dir/"metadata.json").exists():
        try:
            meta = load_json(sample_dir/"metadata.json")
        except Exception:
            pass

    manifest = {
        "schema_version": "customer_package_v2",
        "sample_id": sample_dir.name,
        "label": meta.get("label", "unlabeled"),
        "engine_data_untouched": True,
        "customer_package": {
            "final_assets": [
                "CUSTOMER_PACKAGE/01_FINAL_ASSETS/01_FINAL_BLACK_ON_WHITE.png",
                "CUSTOMER_PACKAGE/01_FINAL_ASSETS/02_BLACK_TRANSPARENT.png",
                "CUSTOMER_PACKAGE/01_FINAL_ASSETS/03_WHITE_ON_BLACK.png",
                "CUSTOMER_PACKAGE/01_FINAL_ASSETS/04_WHITE_TRANSPARENT.png",
            ],
            "training": [
                "CUSTOMER_PACKAGE/02_TRAINING/01_PRACTICE.pdf",
                "CUSTOMER_PACKAGE/02_TRAINING/01_TRAINING.mp4",
            ],
        },
        "practice_sheet": {
            "format": "A4",
            "copies": 20,
            "layout": "4x5",
            "print_faintness_alpha": PRACTICE_ALPHA,
        },
        "training_video": video_info,
        "final_assets": final_info,
        "notes": [
            "Final assets use the existing high-resolution render crop.",
            "No forced 1800px upscale is performed.",
            "Training video is centered in a 1280x720 white frame.",
            "Original stroke coordinates and raw points remain untouched.",
            "Real idle gaps between strokes are removed for continuous instruction.",
        ],
    }

    (package/"manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return True, "built"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        default=str(SAMPLES_DIR),
        help="Samples root directory"
    )
    ap.add_argument(
        "--sample",
        action="append",
        help="Build ONLY this sample, e.g. --sample sample_000023"
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only CUSTOMER_PACKAGE for selected sample(s)"
    )
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"Samples directory not found: {root}")

    if args.sample:
        samples = [root/s for s in args.sample]
    else:
        # SAFE: without --sample, require explicit confirmation.
        raise SystemExit(
            "Safety stop: specify --sample sample_000023. "
            "The builder will not bulk-modify samples by default."
        )

    print("="*72)
    print("CUSTOMER PACKAGE BUILDER v2")
    print("="*72)
    print("Samples:", len(samples))

    for sample in samples:
        try:
            ok, msg = build_sample(sample, overwrite=args.overwrite)
            print(f"{sample.name}: {msg}")
        except Exception as e:
            print(f"{sample.name}: ERROR: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
