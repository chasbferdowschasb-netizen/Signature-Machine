# -*- coding: utf-8 -*-
from pathlib import Path
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
PROJECT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT))

from visual_analyzer_v06_1 import DeepVisualAnalyzer

DEFAULT_IMAGE = PROJECT / "test_debug" / "02e13d43f1407342_candidate.png"
OUT_DIR = PROJECT / "diagnostic_v061"
REPORT = OUT_DIR / "diagnostic_report.txt"

def stats(name, a):
    a = np.asarray(a)
    return (
        f"{name}: shape={a.shape}, dtype={a.dtype}, min={a.min()}, max={a.max()}, "
        f"nonzero={np.count_nonzero(a)}, ratio={np.mean(a != 0):.8f}, "
        f"unique={np.unique(a)[:20].tolist()}"
    )

def save_binary(a, path):
    from PIL import Image
    Image.fromarray(np.where(np.asarray(a) > 0, 255, 0).astype(np.uint8), mode="L").save(path)

def main(image_path):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log = []
    log += ["="*78, "SIGNATURE CLEANER V0.6.1 DIAGNOSTIC", "="*78]
    log += [f"IMAGE: {image_path}", ""]

    if not image_path.exists():
        log += [f"FATAL: image not found: {image_path}"]
        REPORT.write_text("\n".join(log), encoding="utf-8")
        print("\n".join(log))
        return 2

    a = DeepVisualAnalyzer(debug=False)

    rgb, gray, alpha = a._load(image_path)
    log += ["[1] RAW LOAD"]
    log += [stats("RGB", rgb), stats("GRAY", gray), stats("ALPHA", alpha)]
    log += [
        f"alpha>=16 ratio={np.mean(alpha >= 16):.8f}",
        f"alpha>0  ratio={np.mean(alpha > 0):.8f}", ""
    ]

    candidate, polarity = a._detect_polarity(gray, alpha)
    log += ["[2] _detect_polarity"]
    log += [stats("CANDIDATE", candidate)]
    log += [f"{k}={v}" for k,v in polarity.items()] + [""]
    save_binary(candidate, OUT_DIR/"01_candidate.png")

    morphed = a._morph(candidate)
    log += ["[3] _morph"]
    log += [stats("MORPHED", morphed)]
    log += [f"pixels: {np.count_nonzero(candidate)} -> {np.count_nonzero(morphed)}", ""]
    save_binary(morphed, OUT_DIR/"02_morphed.png")

    cleaned, cleanup = a._cleanup_layout(morphed)
    log += ["[4] _cleanup_layout"]
    log += [stats("CLEANED", cleaned)]
    log += [f"{k}={v}" for k,v in cleanup.items()] + [""]
    save_binary(cleaned, OUT_DIR/"03_cleaned.png")

    filtered = cleaned.copy()
    try:
        from scipy import ndimage as ndi
        if np.any(filtered):
            labels, count = ndi.label(filtered.astype(bool), structure=np.ones((3,3), dtype=np.uint8))
            objects = ndi.find_objects(labels)
            min_area = max(a.min_component_pixels, int(filtered.size * 0.000002))
            post = np.zeros_like(filtered, dtype=np.uint8)
            kept = 0
            for label_id, slc in enumerate(objects, 1):
                if slc is None:
                    continue
                area = int(np.count_nonzero(labels[slc] == label_id))
                if area >= min_area:
                    post[labels == label_id] = 1
                    kept += 1
            if np.any(post):
                filtered = post
            log += ["[5] POST COMPONENT FILTER",
                     stats("FILTERED", filtered),
                     f"components={count}", f"min_area={min_area}",
                     f"kept={kept}", ""]
        else:
            log += ["[5] POST COMPONENT FILTER", "SKIPPED: input already empty", ""]
    except Exception as e:
        log += [f"[5] FILTER ERROR: {type(e).__name__}: {e}", ""]

    save_binary(filtered, OUT_DIR/"04_filtered.png")

    skeleton = a.skeletonize(filtered)
    log += ["[6] SKELETONIZE", stats("SKELETON", skeleton), ""]
    save_binary(skeleton, OUT_DIR/"05_skeleton.png")

    log += ["[7] FINAL VERDICT"]
    counts = [np.count_nonzero(x) for x in (candidate,morphed,cleaned,filtered,skeleton)]
    names = ["candidate","morphed","cleaned","filtered","skeleton"]
    for n,c in zip(names,counts):
        log.append(f"{n}: {c}")

    if counts[0] == 0:
        verdict = "FAIL: _detect_polarity returned EMPTY. Problem is before layout cleanup."
    elif counts[1] == 0:
        verdict = "FAIL: _morph destroyed the candidate."
    elif counts[2] == 0:
        verdict = "FAIL: _cleanup_layout removed EVERYTHING."
    elif counts[3] == 0:
        verdict = "FAIL: post component filter removed EVERYTHING."
    elif counts[4] == 0:
        verdict = "FAIL: skeletonization returned EMPTY."
    else:
        verdict = "PASS: extraction remains non-empty through every stage."

    log += ["", verdict, "", f"Diagnostic folder: {OUT_DIR}",
            f"Report: {REPORT}", "="*78]
    REPORT.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    return 0

if __name__ == "__main__":
    image = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    raise SystemExit(main(image))