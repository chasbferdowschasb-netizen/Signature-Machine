"""
SIGNATURE MACHINE — STEP 8 VALIDATION v0.1
------------------------------------------------------------
Purpose:
    Validate the learned STEP 8 trajectory-style representation
    before MODEL v001 is allowed.

Architecture rule:
    This file performs validation only. It does not replace or
    modify the existing Knowledge Engine, STEP 1-7 files, CYCLE v0.1,
    frozen references, MODEL v001, or Sample 026.

Safety:
    - Read-only validation.
    - No training.
    - No generation.
    - No file modification.
    - No sample creation.
    - Frozen references 001..025 remain untouched.

Expected input:
    online_training_data/reference_learning/STEP8_ITERATIVE_LEARNING_v0.1.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parent
REF_DIR = ROOT / "online_training_data" / "reference_learning"
STEP8_JSON = REF_DIR / "STEP8_ITERATIVE_LEARNING_v0.1.json"
CYCLE_JSON = REF_DIR / "CYCLE_v0.1" / "cycle_report.json"

EXPECTED_COUNT = 25
EXPECTED_WEIGHT = 0.04
LOSS_EPS = 1e-12
MIN_HISTORY = 2


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def get_path(obj, *keys, default=None):
    cur = obj
    for key in keys:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def find_history(data):
    candidates = [
        get_path(data, "iteration", "history"),
        get_path(data, "history"),
        get_path(data, "learning", "history"),
        get_path(data, "iterations"),
    ]
    for item in candidates:
        if isinstance(item, list):
            return item
    return []


def extract_number(item, names):
    if not isinstance(item, dict):
        return None
    for name in names:
        value = item.get(name)
        if finite(value):
            return float(value)
    diagnostic = item.get("diagnostic")
    if isinstance(diagnostic, dict):
        for name in names:
            value = diagnostic.get(name)
            if finite(value):
                return float(value)
    return None


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("=" * 72)
    print("SIGNATURE MACHINE — STEP 8 VALIDATION v0.1")
    print("=" * 72)
    print("[READ-ONLY] No files will be modified.")
    print()

    if not STEP8_JSON.exists():
        print("[FAIL] STEP8 report not found:")
        print(f"       {STEP8_JSON}")
        return 2

    data = load_json(STEP8_JSON)
    history = find_history(data)

    checks = []
    warnings = []

    # ------------------------------------------------------------
    # Reference policy
    # ------------------------------------------------------------
    ref_count = (
        get_path(data, "reference_policy", "reference_count")
        or get_path(data, "reference_policy", "count")
        or get_path(data, "reference_count")
    )
    weight = (
        get_path(data, "reference_policy", "weight_per_sample")
        or get_path(data, "reference_policy", "equal_weight")
        or get_path(data, "weight_per_sample")
    )

    if ref_count is not None:
        ok = int(ref_count) == EXPECTED_COUNT
        checks.append(("Reference count = 25", ok))
    else:
        warnings.append("Reference count field not found in STEP8 report.")

    if weight is not None:
        ok = abs(float(weight) - EXPECTED_WEIGHT) <= 1e-9
        checks.append(("Equal weight = 0.04", ok))
    else:
        warnings.append("Equal-weight field not found in STEP8 report.")

    # ------------------------------------------------------------
    # History integrity
    # ------------------------------------------------------------
    if len(history) < MIN_HISTORY:
        checks.append(("Iteration history available", False))
        print("[FAIL] Iteration history is missing or too short.")
        return 2

    checks.append(("Iteration history available", True))

    iterations = []
    losses = []
    deltas = []
    updates = []
    accepted = []

    for row in history:
        it = extract_number(row, ["iteration", "step"])
        loss = extract_number(row, ["loss", "normalized_loss"])
        delta = extract_number(row, ["delta", "loss_delta"])
        update = extract_number(row, ["update_norm"])
        acc = row.get("accepted") if isinstance(row, dict) else None

        if it is not None:
            iterations.append(int(it))
        if loss is not None:
            losses.append(loss)
        if delta is not None:
            deltas.append(delta)
        if update is not None:
            updates.append(update)
        if isinstance(acc, bool):
            accepted.append(acc)

    finite_losses = bool(losses) and all(finite(x) for x in losses)
    checks.append(("All recorded losses finite", finite_losses))

    ordered = iterations == sorted(iterations) and len(set(iterations)) == len(iterations)
    checks.append(("Iteration sequence ordered", ordered))

    if accepted:
        checks.append(("No rejected learning step", all(accepted)))
    else:
        warnings.append("Accepted flags were not found.")

    # ------------------------------------------------------------
    # Loss behavior
    # ------------------------------------------------------------
    initial_loss = losses[0] if losses else None
    final_loss = losses[-1] if losses else None

    if initial_loss is not None and final_loss is not None:
        improvement = initial_loss - final_loss
        checks.append(("Final loss lower than initial", improvement > LOSS_EPS))

        # Count actual decreases rather than assuming monotonicity.
        decreases = sum(
            1 for a, b in zip(losses, losses[1:]) if b < a - LOSS_EPS
        )
        non_increases = sum(
            1 for a, b in zip(losses, losses[1:]) if b <= a + LOSS_EPS
        )

        print(f"Initial loss: {initial_loss:.15f}")
        print(f"Final loss:   {final_loss:.15f}")
        print(f"Loss improvement: {improvement:.15f}")
        print(f"Decreasing transitions: {decreases}/{max(0, len(losses)-1)}")

        if non_increases < len(losses) - 1:
            warnings.append(
                "Loss is not fully monotonic; inspect rejected/accepted steps."
            )
    else:
        checks.append(("Loss values available", False))

    # ------------------------------------------------------------
    # Parameter movement / gradient evidence
    # ------------------------------------------------------------
    if updates:
        positive_updates = sum(1 for x in updates if x > LOSS_EPS)
        checks.append(("Learning produced non-zero updates", positive_updates > 0))
        print(f"Non-zero update steps: {positive_updates}/{len(updates)}")
    else:
        warnings.append("update_norm values were not found.")

    # ------------------------------------------------------------
    # Alpha safety
    # ------------------------------------------------------------
    alpha_values = []
    for row in history:
        for name in ("alpha_min", "alpha_max", "alpha_mean"):
            value = extract_number(row, [name])
            if value is not None:
                alpha_values.append(value)

    if alpha_values:
        finite_alpha = all(finite(x) for x in alpha_values)
        checks.append(("Alpha values finite", finite_alpha))

        # The current STEP 8 design intentionally permits negative alpha.
        # We only reject runaway/non-finite values here.
        alpha_abs_max = max(abs(x) for x in alpha_values)
        print(f"Maximum |alpha| observed: {alpha_abs_max:.9f}")

        if alpha_abs_max > 10.0:
            warnings.append(
                "Alpha magnitude exceeded 10; inspect parameter stability."
            )
    else:
        warnings.append("Alpha diagnostics were not found.")

    # ------------------------------------------------------------
    # Generation gate
    # ------------------------------------------------------------
    generation_ready = get_path(data, "generation_policy", "generation_ready")
    new_name_generation = get_path(data, "generation_policy", "new_name_generation")
    model_version = get_path(data, "generation_policy", "model_version")

    if generation_ready is not None:
        checks.append(("Generation gate remains OFF", generation_ready is False))
    if new_name_generation is not None:
        checks.append(("New-name generation remains OFF", new_name_generation is False))
    if model_version is not None:
        checks.append(("MODEL version remains null", model_version is None))

    # ------------------------------------------------------------
    # Frozen reference guard
    # ------------------------------------------------------------
    frozen_ok = True
    for i in range(1, EXPECTED_COUNT + 1):
        p = REF_DIR / f"sample_{i:06d}"
        if not p.exists():
            frozen_ok = False
            warnings.append(f"Frozen reference missing: sample_{i:06d}")

    checks.append(("Frozen reference set 001..025 present", frozen_ok))

    # ------------------------------------------------------------
    # CYCLE baseline is informational only
    # ------------------------------------------------------------
    baseline = None
    if CYCLE_JSON.exists():
        try:
            cycle = load_json(CYCLE_JSON)
            baseline = get_path(cycle, "loss", "weighted_total_loss")
            if baseline is None:
                baseline = get_path(cycle, "loss", "mean_loss")
        except Exception as exc:
            warnings.append(f"Could not read CYCLE baseline: {exc}")

    # ------------------------------------------------------------
    # Result
    # ------------------------------------------------------------
    failed = [name for name, ok in checks if not ok]

    print()
    print("-" * 72)
    print("VALIDATION CHECKS")
    print("-" * 72)
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")

    if baseline is not None:
        print()
        print(f"CYCLE v0.1 baseline (informational): {float(baseline):.15f}")
        print("NOTE: STEP 8 normalized loss is not treated as directly")
        print("      comparable to the CYCLE v0.1 baseline.")

    print()
    print("-" * 72)
    print("WARNINGS")
    print("-" * 72)
    if warnings:
        for w in warnings:
            print(f"[WARNING] {w}")
    else:
        print("None")

    print()
    print("=" * 72)

    if failed:
        print("STEP 8 VALIDATION: FAIL")
        print("MODEL v001: NOT AUTHORIZED")
        print("Sample 026: NOT AUTHORIZED")
        print("=" * 72)
        return 1

    print("STEP 8 VALIDATION: PASS")
    print("MODEL v001: NOT CREATED")
    print("Sample 026: NOT CREATED")
    print("Frozen references: UNCHANGED")
    print("Training/generation: NOT PERFORMED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
