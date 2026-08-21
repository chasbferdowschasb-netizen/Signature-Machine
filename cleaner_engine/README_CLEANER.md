# Signature Cleaner Engine

This version is a learned cleaner for the signature dataset. It learns pixel-level foreground/background behavior from the approved V4 masks in the test set, then applies the model to new images.

## Install

```bash
pip install opencv-python numpy scikit-learn joblib
```

## 1. Train once

Use the V4 reference images/masks:

```bash
python train_signature_cleaner.py \
  --original ./v4_reference/v4_outputs/original \
  --masks ./v4_reference/v4_outputs/mask \
  --model ./signature_cleaner_model.joblib
```

## 2. Run on one image

```bash
python run_signature_cleaner.py input.png \
  --model ./signature_cleaner_model.joblib \
  --output ./cleaned
```

## 3. Run on a directory

```bash
python run_signature_cleaner.py ./input_images \
  --model ./signature_cleaner_model.joblib \
  --output ./cleaned
```

For every image the engine writes:

- `*_mask.png` — detected signature mask
- `*_clean.png` — black signature on white background
- `*_clean_color.png` — original signature colors on white background

Original files are never modified.

## Important

Do not run this on all 4599 files yet. The current model is a V1 learned from the approved test masks. First validate it on the complete 20-image test set, then add the remaining approved masks/examples and retrain. Only after that should we run a 100-image pilot from the 4599 files.
