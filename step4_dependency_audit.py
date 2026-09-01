from pathlib import Path

ROOT = Path(".").resolve()

TARGETS = [
    "knowledge_engine.py",
    "knowledge_engine_STEP6.py",
    "knowledge_engine_STEP8_v005.py",
    "knowledge_engine_STEP8_v006_DIAGNOSTIC.py",
    "knowledge_engine_STEP8_v007.py",
    "knowledge_engine_STEP8_v008.py",
    "signature_knowledge_engine.py",
    "generation_engine.py",
    "generation_evaluator.py",
    "cycle_v001.py",
    "cycle_v001_STEP7.py",
    "cycle_v001_STEP7_FIXED.py",
    "cycle_v001_STEP7_FIXED_v2.py",
    "cycle_v001_STEP7_FIXED_v3.py",
    "cycle_v001_STEP7_FIXED_v4.py",
    "step8_validation_v001.py",
    "step8_validation_v002.py",
    "step8_validation_v003.py",
    "step8_validation_v003_backup.py",
    "step8_validation_v004.py",
    "trajectory_audit_v001.py",
    "trajectory_evaluator_v001.py",
    "visual_analyzer.py",
    "visual_analyzer_v06_2.py",
    "test_visual_analyzer.py",
    "test_visual_analyzer_v06_2.py",
    "online_training_final.py",
    "online_training_with_package.py",
    "reference_feature_extractor.py",
    "stroke_engine.py",
    "workspace_manager.py",
]

IGNORE = {
    ".git",
    ".venv",
    "__pycache__",
    "cleaner_test20",
    "diagnostic_v061",
}

EXTENSIONS = {
    ".py",
    ".json",
    ".txt",
    ".md",
    ".html",
    ".js",
    ".yaml",
    ".yml",
    ".toml",
}

def should_scan(path):
    if not path.is_file():
        return False
    if any(part in IGNORE for part in path.parts):
        return False
    return path.suffix.lower() in EXTENSIONS

all_files = [
    p for p in ROOT.rglob("*")
    if should_scan(p)
]

out = []

out.append("=" * 80)
out.append("SIGNATURE MACHINE")
out.append("STEP 4 — REAL DEPENDENCY AUDIT")
out.append("=" * 80)
out.append("")
out.append(f"ROOT: {ROOT}")
out.append(f"SCANNED FILES: {len(all_files)}")
out.append("")

for target in TARGETS:

    target_path = ROOT / target

    out.append("=" * 80)
    out.append(f"TARGET: {target}")
    out.append("=" * 80)

    if not target_path.exists():
        out.append("STATUS: MISSING")
        out.append("")
        continue

    out.append("STATUS: EXISTS")
    out.append(f"SIZE: {target_path.stat().st_size}")

    references = []

    for other in all_files:

        if other.resolve() == target_path.resolve():
            continue

        try:
            text = other.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except Exception:
            continue

        names = {
            target,
            target.replace("\\", "/"),
            target.replace("/", "\\"),
            target_path.stem,
        }

        if any(name in text for name in names):
            references.append(
                str(other.relative_to(ROOT))
            )

    references = sorted(set(references))

    out.append("")
    out.append(f"REFERENCED_BY: {len(references)}")

    if references:
        for ref in references:
            out.append(f"  - {ref}")

    out.append("")

out.append("=" * 80)
out.append("CURRENT ARCHITECTURE")
out.append("=" * 80)

CURRENT = [
    "core.py",
    "build_motion_style_state.py",
    "online_training_data/motion_learning/motion_style_state.json",
    "online_training_data/reference_learning/knowledge/index.json",
    "online_training_data/reference_learning/knowledge/aggregate.json",
]

for item in CURRENT:
    p = ROOT / item
    out.append(
        f"{item:<70} "
        + ("EXISTS" if p.exists() else "MISSING")
    )

out.append("")
out.append("=" * 80)
out.append("STEP 4 AUDIT COMPLETE")
out.append("NO FILES WERE MODIFIED OR DELETED")
out.append("=" * 80)

Path("STEP4_REAL_DEPENDENCY_AUDIT.txt").write_text(
    "\n".join(out) + "\n",
    encoding="utf-8"
)

print("\n".join(out))
print("")
print("REPORT SAVED:")
print(ROOT / "STEP4_REAL_DEPENDENCY_AUDIT.txt")
