# -*- coding: utf-8 -*-
from pathlib import Path
import argparse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from PIL import Image

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "online_training_data" / "reference_learning" / "samples"

COPIES = 20
COLS, ROWS = 4, 5
INK_ALPHA = 0.58

def find_asset(final_dir):
    candidates = sorted(final_dir.glob("*BLACK_ON_WHITE*.png"))
    if candidates:
        return candidates[0]
    pngs = sorted(final_dir.glob("*.png"))
    if not pngs:
        raise FileNotFoundError("No PNG found in 01_FINAL_ASSETS")
    return pngs[0]

def make_pdf(sample_dir):
    final_dir = sample_dir / "CUSTOMER_PACKAGE" / "01_FINAL_ASSETS"
    training_dir = sample_dir / "CUSTOMER_PACKAGE" / "02_TRAINING"
    training_dir.mkdir(parents=True, exist_ok=True)

    source = find_asset(final_dir)
    im = Image.open(source).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size

    rgba = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    src, dst = im.load(), rgba.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = src[x, y]
            darkness = 255 - min(r, g, b)
            aa = int(max(0, min(255, darkness * INK_ALPHA)))
            dst[x, y] = (85, 85, 85, aa)

    temp = training_dir / ".practice_temp.png"
    rgba.save(temp)
    pdf_path = training_dir / "01_PRACTICE.pdf"

    page_w, page_h = A4
    c = canvas.Canvas(str(pdf_path), pagesize=A4)

    margin_x = 9 * mm
    top = 18 * mm
    bottom = 7 * mm
    header_h = 7 * mm
    cell_w = (page_w - 2 * margin_x) / COLS
    cell_h = (page_h - top - bottom - header_h) / ROWS

    c.setFillColorRGB(0.30, 0.30, 0.30)
    c.setFont("Helvetica", 9)
    c.drawString(margin_x, page_h - 12 * mm, "Signature Practice - 20 repetitions")

    for i in range(COPIES):
        row, col = divmod(i, COLS)
        max_w, max_h = cell_w * 0.90, cell_h * 0.68
        scale = min(max_w / max(w, 1), max_h / max(h, 1))
        dw, dh = w * scale, h * scale
        cell_x = margin_x + col * cell_w
        cell_y = page_h - top - header_h - (row + 1) * cell_h
        x = cell_x + (cell_w - dw) / 2
        y = cell_y + (cell_h - dh) / 2 + 1.5 * mm

        c.drawImage(str(temp), x, y, width=dw, height=dh,
                    mask="auto", preserveAspectRatio=True)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.setFont("Helvetica", 6)
        c.drawString(cell_x + 2 * mm, cell_y + 2 * mm, str(i + 1))

    c.save()
    temp.unlink(missing_ok=True)
    return pdf_path, source

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="append", required=True)
    args = ap.parse_args()

    print("=" * 70)
    print("PRACTICE PDF BUILDER - PDF ONLY")
    print("=" * 70)

    for name in args.sample:
        try:
            pdf, source = make_pdf(SAMPLES / name)
            print(f"{name}: OK")
            print(f"  source: {source.name}")
            print(f"  created: {pdf}")
        except Exception as e:
            print(f"{name}: ERROR: {e}")
    print("Done.")

if __name__ == "__main__":
    main()
