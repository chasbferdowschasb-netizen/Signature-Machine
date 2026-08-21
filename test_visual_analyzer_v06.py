# -*- coding: utf-8 -*-
"""
TEST ONLY — Signature Visual Analyzer v0.5

IMPORTANT:
- This script NEVER scans library/ recursively.
- It uses the exact 20 files recorded by test_visual_results_v04.json when that
  file exists.
- It NEVER updates signature_knowledge.json.
- Results: test_visual_results_v06.json
- Debug:   test_debug_v06/
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from visual_analyzer_v06 import DeepVisualAnalyzer


EXPECTED = 20
PREVIOUS_RESULTS = Path("test_visual_results_v04.json")


def resolve_previous_samples() -> list[Path]:
    if not PREVIOUS_RESULTS.exists():
        raise FileNotFoundError(
            "test_visual_results_v04.json was not found. "
            "This v0.5 test intentionally refuses to scan library/ blindly. "
            "Restore the v0.4 results file or create a 20-file test list first."
        )

    data = json.loads(PREVIOUS_RESULTS.read_text(encoding="utf-8"))
    rows = data.get("results", [])
    files = []
    for row in rows:
        raw = row.get("path") or row.get("filename")
        if raw:
            files.append(Path(raw))

    # v0.4 may have stored only filenames. In that case resolve them inside library.
    resolved = []
    for p in files:
        if p.exists():
            resolved.append(p)
            continue
        candidate = Path("library") / p
        if candidate.exists():
            resolved.append(candidate)
            continue
        matches = list(Path("library").glob(p.name)) if Path("library").exists() else []
        if len(matches) == 1:
            resolved.append(matches[0])

    # Preserve order from v0.4 and remove accidental duplicates.
    unique = []
    seen = set()
    for p in resolved:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)

    if len(unique) != EXPECTED:
        raise RuntimeError(
            f"Expected exactly {EXPECTED} samples from v0.4 results, but resolved {len(unique)}. "
            "No test was run."
        )

    return unique


def main() -> None:
    files = resolve_previous_samples()
    debug_dir = Path("test_debug_v06")
    results_file = Path("test_visual_results_v06.json")

    analyzer = DeepVisualAnalyzer(debug=True, debug_dir=debug_dir)
    results = []
    failed = []

    print()
    print("=" * 70)
    print("VISUAL ANALYZER V0.6 — EXACT 20 SAMPLE TEST")
    print("=" * 70)
    print(f"Expected: {EXPECTED}")
    print("Library recursive scan: DISABLED")
    print("Knowledge file: NOT modified")
    print()

    for index, path in enumerate(files, start=1):
        try:
            result = analyzer.analyze_image(path)
            results.append(result)
            ex = result["signature_extraction"]
            curv = result["curvature"]
            print(
                f"[{index:02d}/{EXPECTED}] OK  {path.name} | "
                f"polarity={ex.get('polarity')} | "
                f"mask={ex.get('signature_ratio', 0):.6f} | "
                f"paths={curv.get('traced_paths', 0)} | "
                f"loops={curv.get('graph', {}).get('loops', 0)}"
            )
        except Exception as exc:
            failed.append({
                "filename": str(path),
                "type": type(exc).__name__,
                "error": str(exc),
            })
            print()
            print("ERROR")
            print(f"File: {path}")
            print(f"Type: {type(exc).__name__}")
            print(f"Message: {exc}")
            traceback.print_exc()

    output = {
        "analyzer_version": DeepVisualAnalyzer.VERSION,
        "pipeline_version": DeepVisualAnalyzer.PIPELINE_VERSION,
        "expected": EXPECTED,
        "sample_count": len(files),
        "successful": len(results),
        "failed": len(failed),
        "source": "exact_samples_from_test_visual_results_v04.json",
        "results": results,
        "failed_files": failed,
    }

    results_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print(f"Expected:   {EXPECTED}")
    print(f"Successful: {len(results)}")
    print(f"Failed:     {len(failed)}")
    print(f"Results:    {results_file}")
    print(f"Debug:      {debug_dir}")
    print()


if __name__ == "__main__":
    main()