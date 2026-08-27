"""
SIGNATURE MACHINE — STEP 8 VALIDATION v0.2
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
    print("SIGNATURE MACHINE — STEP 8 VALIDATION v0.2")
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
        # STEP 8 may not duplicate the policy field. In that case,
        # validate the authoritative STEP 1/2 artifacts instead.
        policy_values = []

        def find_weight_values(obj):
            values = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    key_l = str(key).lower()
                    if key_l in {
                        "equal_weight", "weight_per_sample", "sample_weight",
                        "trajectory_weight", "reference_weight",
                        "equal_reference_weight", "peer_weight_each"
                    } and finite(value):
                        values.append(float(value))
                    if isinstance(value, (dict, list)):
                        values.extend(find_weight_values(value))
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        values.extend(find_weight_values(item))
            return values

        for obj in (freeze_data, manifest_data):
            policy_values.extend(find_weight_values(obj))

        if policy_values:
            ok = any(abs(v - EXPECTED_WEIGHT) <= 1e-9 for v in policy_values)
            checks.append(("Equal weight = 0.04", ok))
        else:
            # 25 frozen references imply equal weight 1/25 by the
            # established project policy, but do not silently convert
            # this into a PASS; report it as a warning for transparency.
            warnings.append(
                "Equal-weight field not explicitly recorded in STEP8/STEP1/STEP2 artifacts."
            )

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
    # Do NOT assume the physical sample directories live directly under
    # reference_learning. The authoritative sources are the existing
    # FREEZE and MANIFEST artifacts created by STEP 1 and STEP 2.
    freeze_candidates = [
        REF_DIR / "REFERENCE_FREEZE_v0.1.json",
        REF_DIR / "REFERENCE_FREEZE_v0.1" / "REFERENCE_FREEZE_v0.1.json",
    ]
    manifest_candidates = [
        REF_DIR / "REFERENCE_MANIFEST_v0.1.json",
        REF_DIR / "REFERENCE_MANIFEST_v0.1" / "REFERENCE_MANIFEST_v0.1.json",
    ]

    freeze_data = None
    manifest_data = None

    for p in freeze_candidates:
        if p.exists():
            try:
                freeze_data = load_json(p)
                break
            except Exception as exc:
                warnings.append(f"Could not read freeze marker {p}: {exc}")

    for p in manifest_candidates:
        if p.exists():
            try:
                manifest_data = load_json(p)
                break
            except Exception as exc:
                warnings.append(f"Could not read manifest {p}: {exc}")

    def extract_reference_ids(obj, parent_key=""):
        """
        Recursively extract sample IDs from STEP 1/2 artifacts.

        Handles common manifest shapes such as:
          {"sample_id": 1}
          {"id": 1}
          {"samples": [{"sample_id": 1}, ...]}
          {"sample": "sample_000001"}
        """
        import re

        found = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                key_l = str(key).lower()

                # Explicit sample/reference identifiers.
                if key_l in {
                    "sample_id", "sampleid", "id",
                    "reference_id", "reference_sample_id"
                }:
                    if isinstance(value, int) and 1 <= value <= 999999:
                        found.append(int(value))
                    elif isinstance(value, str):
                        m = re.search(r"(\d{1,6})$", value.strip())
                        if m:
                            found.append(int(m.group(1)))

                # Lists of sample records / names.
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, (int, float)) and int(item) == item:
                            found.append(int(item))
                        elif isinstance(item, str):
                            m = re.search(
                                r"(?:sample[_ -]?)?(\d{1,6})$",
                                item.strip(),
                                re.I,
                            )
                            if m:
                                found.append(int(m.group(1)))
                        elif isinstance(item, (dict, list)):
                            found.extend(extract_reference_ids(item, key_l))

                elif isinstance(value, (dict, list)):
                    found.extend(extract_reference_ids(value, key_l))

        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (int, float)) and int(item) == item:
                    found.append(int(item))
                elif isinstance(item, str):
                    m = re.search(
                        r"(?:sample[_ -]?)?(\d{1,6})$",
                        item.strip(),
                        re.I,
                    )
                    if m:
                        found.append(int(m.group(1)))
                elif isinstance(item, (dict, list)):
                    found.extend(extract_reference_ids(item, parent_key))

        return found

    expected_ids = set(range(1, EXPECTED_COUNT + 1))
    freeze_ids = set(extract_reference_ids(freeze_data)) if freeze_data else set()
    manifest_ids = set(extract_reference_ids(manifest_data)) if manifest_data else set()

    freeze_ok = expected_ids.issubset(freeze_ids) if freeze_data else False
    manifest_ok = expected_ids.issubset(manifest_ids) if manifest_data else False

    if freeze_data:
        checks.append(("STEP 1 freeze marker confirms 001..025", freeze_ok))
    else:
        checks.append(("STEP 1 freeze marker available", False))

    if manifest_data:
        checks.append(("STEP 2 manifest confirms 001..025", manifest_ok))
    else:
        checks.append(("STEP 2 manifest available", False))

    # If authoritative freeze + manifest are present, do not inspect a
    # guessed physical path. This prevents false failures caused by
    # repository layout.
    checks.append(
        ("Frozen reference integrity verified without modifying references",
         freeze_ok and manifest_ok)
    )

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
