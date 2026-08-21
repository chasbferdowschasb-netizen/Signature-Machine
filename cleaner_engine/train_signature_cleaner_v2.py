#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Signature Cleaner V2 Trainer

Trains an ExtraTrees pixel classifier from:

    original/
        ID.png

    masks/
        ID_mask.png

The script is intentionally verbose so that no training sample
can be silently skipped.
"""

from pathlib import Path
import argparse
import joblib
import cv2
import numpy as np

from sklearn.ensemble import ExtraTreesClassifier


EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


# ============================================================
# FEATURES
# ============================================================

def features(img, max_side=1200):

    h0, w0 = img.shape[:2]

    scale = min(
        1.0,
        max_side / max(h0, w0)
    )

    if scale < 1.0:
        img = cv2.resize(
            img,
            (
                round(w0 * scale),
                round(h0 * scale)
            ),
            interpolation=cv2.INTER_AREA
        )

    h, w = img.shape[:2]

    lab = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2LAB
    ).astype(np.float32) / 255.0

    hsv = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2HSV
    ).astype(np.float32) / 255.0

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    ).astype(np.float32) / 255.0

    blur = cv2.GaussianBlur(
        gray,
        (0, 0),
        3
    )

    blur9 = cv2.GaussianBlur(
        gray,
        (0, 0),
        9
    )

    local = np.abs(
        gray - blur
    )

    local9 = np.abs(
        gray - blur9
    )

    gx = cv2.Sobel(
        gray,
        cv2.CV_32F,
        1,
        0,
        ksize=3
    )

    gy = cv2.Sobel(
        gray,
        cv2.CV_32F,
        0,
        1,
        ksize=3
    )

    grad = cv2.magnitude(
        gx,
        gy
    )

    yy, xx = np.mgrid[
        0:h,
        0:w
    ].astype(np.float32)

    xx /= max(1, w - 1)
    yy /= max(1, h - 1)

    X = np.stack(
        [
            lab[:, :, 0],
            lab[:, :, 1],
            lab[:, :, 2],

            hsv[:, :, 0],
            hsv[:, :, 1],
            hsv[:, :, 2],

            gray,
            blur,
            local,
            local9,
            grad,

            xx,
            yy,
        ],
        axis=-1
    )

    return X, scale


# ============================================================
# FIND SOURCE
# ============================================================

def find_source(original_dir, name):

    candidates = [
        original_dir / f"{name}.png",
        original_dir / f"{name}.jpg",
        original_dir / f"{name}.jpeg",
        original_dir / f"{name}.bmp",
        original_dir / f"{name}.tif",
        original_dir / f"{name}.tiff",
        original_dir / f"{name}.webp",
    ]

    for p in candidates:

        if p.exists():
            return p

    return None


# ============================================================
# MAIN
# ============================================================

def main():

    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--original",
        required=True
    )

    ap.add_argument(
        "--masks",
        required=True
    )

    ap.add_argument(
        "--model",
        required=True
    )

    ap.add_argument(
        "--per-class",
        type=int,
        default=60000
    )

    args = ap.parse_args()

    original_dir = Path(args.original)
    masks_dir = Path(args.masks)
    model_path = Path(args.model)

    print("=" * 70)
    print("SIGNATURE CLEANER V2 TRAINING")
    print("=" * 70)

    print()
    print("Original directory:")
    print(original_dir)

    print()
    print("Mask directory:")
    print(masks_dir)

    print()
    print("Model:")
    print(model_path)

    # --------------------------------------------------------
    # Validate directories
    # --------------------------------------------------------

    if not original_dir.exists():

        raise SystemExit(
            f"ERROR: Original directory does not exist:\n"
            f"{original_dir}"
        )

    if not masks_dir.exists():

        raise SystemExit(
            f"ERROR: Mask directory does not exist:\n"
            f"{masks_dir}"
        )

    # --------------------------------------------------------
    # Find masks
    # --------------------------------------------------------

    mask_files = sorted(
        masks_dir.glob("*_mask.png")
    )

    print()
    print("-" * 70)
    print("MASK DISCOVERY")
    print("-" * 70)

    print(
        f"Mask files found: {len(mask_files)}"
    )

    if not mask_files:

        raise SystemExit(
            "ERROR: No *_mask.png files found."
        )

    # --------------------------------------------------------
    # Training containers
    # --------------------------------------------------------

    Xs = []
    ys = []

    rng = np.random.default_rng(42)

    valid_pairs = 0
    skipped = 0

    # ========================================================
    # PROCESS EACH TRAINING PAIR
    # ========================================================

    for index, mf in enumerate(mask_files, start=1):

        print()
        print(
            f"[{index:02d}/{len(mask_files):02d}] "
            f"{mf.name}"
        )

        # ----------------------------------------------------
        # Resolve ID
        # ----------------------------------------------------

        name = mf.name.replace(
            "_mask.png",
            ""
        )

        print(
            f"  ID: {name}"
        )

        # ----------------------------------------------------
        # Find original
        # ----------------------------------------------------

        src = find_source(
            original_dir,
            name
        )

        if src is None:

            print(
                "  ERROR: Original image not found"
            )

            skipped += 1
            continue

        print(
            f"  Original: {src.name}"
        )

        # ----------------------------------------------------
        # Read original
        # ----------------------------------------------------

        img = cv2.imread(
            str(src),
            cv2.IMREAD_COLOR
        )

        if img is None:

            print(
                "  ERROR: cv2.imread(original) failed"
            )

            skipped += 1
            continue

        print(
            f"  Original size: "
            f"{img.shape[1]} x {img.shape[0]}"
        )

        # ----------------------------------------------------
        # Read mask
        # ----------------------------------------------------

        m = cv2.imread(
            str(mf),
            cv2.IMREAD_GRAYSCALE
        )

        if m is None:

            print(
                "  ERROR: cv2.imread(mask) failed"
            )

            skipped += 1
            continue

        print(
            f"  Mask size: "
            f"{m.shape[1]} x {m.shape[0]}"
        )

        # ----------------------------------------------------
        # Feature extraction
        # ----------------------------------------------------

        try:

            X, scale = features(img)

        except Exception as e:

            print(
                f"  ERROR: feature extraction failed: {e}"
            )

            skipped += 1
            continue

        print(
            f"  Feature canvas: "
            f"{X.shape[1]} x {X.shape[0]}"
        )

        # ----------------------------------------------------
        # Resize mask if image was downscaled
        # ----------------------------------------------------

        if scale != 1.0:

            print(
                f"  Image scaled by: {scale:.6f}"
            )

            m = cv2.resize(
                m,
                (
                    X.shape[1],
                    X.shape[0]
                ),
                interpolation=cv2.INTER_NEAREST
            )

        # ----------------------------------------------------
        # Verify final dimensions
        # ----------------------------------------------------

        if (
            m.shape[0] != X.shape[0]
            or
            m.shape[1] != X.shape[1]
        ):

            print(
                "  ERROR: Image/mask dimensions "
                "still do not match"
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Convert mask to labels
        # ----------------------------------------------------

        y = (
            m > 127
        ).ravel().astype(
            np.uint8
        )

        x = X.reshape(
            -1,
            X.shape[-1]
        )

        pos = np.flatnonzero(
            y == 1
        )

        neg = np.flatnonzero(
            y == 0
        )

        print(
            f"  Positive pixels: {len(pos)}"
        )

        print(
            f"  Negative pixels: {len(neg)}"
        )

        # ----------------------------------------------------
        # Minimum data check
        # ----------------------------------------------------

        n = min(
            args.per_class,
            len(pos),
            len(neg)
        )

        if n < 100:

            print(
                f"  ERROR: insufficient pixels "
                f"(usable per class = {n})"
            )

            skipped += 1
            continue

        # ----------------------------------------------------
        # Balanced sampling
        # ----------------------------------------------------

        pi = rng.choice(
            pos,
            n,
            replace=False
        )

        ni = rng.choice(
            neg,
            n,
            replace=False
        )

        idx = np.concatenate(
            [
                pi,
                ni
            ]
        )

        rng.shuffle(idx)

        Xs.append(
            x[idx]
        )

        ys.append(
            y[idx]
        )

        valid_pairs += 1

        print(
            f"  USED: {2 * n} pixels"
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("TRAINING DATA SUMMARY")
    print("=" * 70)

    print(
        f"Mask files       : {len(mask_files)}"
    )

    print(
        f"Valid pairs      : {valid_pairs}"
    )

    print(
        f"Skipped pairs    : {skipped}"
    )

    if not Xs:

        raise SystemExit(
            "ERROR: No training pairs found."
        )

    if valid_pairs < 1:

        raise SystemExit(
            "ERROR: No valid training pairs."
        )

    # --------------------------------------------------------
    # Combine training data
    # --------------------------------------------------------

    X = np.concatenate(
        Xs,
        axis=0
    )

    y = np.concatenate(
        ys,
        axis=0
    )

    print()
    print(
        f"Training samples : {len(y)}"
    )

    print(
        f"Feature count    : {X.shape[1]}"
    )

    print(
        f"Class 0          : {np.sum(y == 0)}"
    )

    print(
        f"Class 1          : {np.sum(y == 1)}"
    )

    # ========================================================
    # TRAIN
    # ========================================================

    print()
    print("=" * 70)
    print("TRAINING EXTRA TREES")
    print("=" * 70)

    clf = ExtraTreesClassifier(
        n_estimators=140,
        max_depth=18,
        min_samples_leaf=2,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42
    )

    clf.fit(
        X,
        y
    )

    # ========================================================
    # SAVE MODEL
    # ========================================================

    model_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    payload = {
        "model": clf,

        "feature_names": [
            "LabL",
            "LabA",
            "LabB",
            "H",
            "S",
            "V",
            "gray",
            "blur3",
            "local3",
            "local9",
            "grad",
            "x",
            "y",
        ],

        "training_pairs": valid_pairs,

        "skipped_pairs": skipped,

        "python_model": "ExtraTreesClassifier",

        "trainer_version": "V2",
    }

    joblib.dump(
        payload,
        model_path,
        compress=3
    )

    print()
    print("=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)

    print()
    print(
        f"Model saved:"
    )

    print(
        model_path
    )

    print()
    print(
        f"Valid training pairs: {valid_pairs}"
    )

    print(
        f"Skipped pairs: {skipped}"
    )

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()