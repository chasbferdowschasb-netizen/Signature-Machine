from pathlib import Path
import re
from collections import defaultdict

ROOT = Path.cwd()
OUT = ROOT / "STEP1_DEPENDENCY_AUDIT.txt"

VERSION_PATTERNS = [
    re.compile(r'(?i)(?:^|[_\-])(v\d+(?:[_\-]\d+)*|fixed|backup|old|final|step\d+)(?:[_\-.]|$)'),
    re.compile(r'(?i)(?:_v\d+|_fixed|_backup|_old|_final)(?:\.|$)'),
]

TEXT_EXTENSIONS = {
    ".py", ".json", ".html", ".htm", ".js", ".css",
    ".md", ".txt", ".ps1", ".bat", ".cmd", ".yaml", ".yml"
}

EXCLUDE_DIRS = {
    ".git", ".venv", "__pycache__", "candidates",
    "library", "cleaner_test20", "diagnostic_v061"
}

def is_excluded(path):
    return any(part in EXCLUDE_DIRS for part in path.parts)

def is_versioned(path):
    name = path.name
    return any(p.search(name) for p in VERSION_PATTERNS)

files = []
for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    if is_excluded(p.relative_to(ROOT)):
        continue
    files.append(p)

versioned = sorted(
    [p for p in files if is_versioned(p)],
    key=lambda p: str(p).lower()
)

all_text_files = [
    p for p in files
    if p.suffix.lower() in TEXT_EXTENSIONS
]

# Full textual reference index
references = defaultdict(list)

for source in all_text_files:
    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue

    for target in versioned:
        rel = target.relative_to(ROOT)
        candidates = {
            target.name.lower(),
            str(rel).replace("\\", "/").lower(),
            str(rel).replace("\\", "\\\\").lower(),
        }

        low = text.lower()

        if any(c in low for c in candidates):
            references[target].append(source)

# Python import/reference analysis
python_refs = defaultdict(list)

for source in [p for p in files if p.suffix.lower() == ".py"]:
    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue

    low = text.lower()

    for target in versioned:
        if target.suffix.lower() != ".py":
            continue

        stem = target.stem.lower()

        import_patterns = [
            rf'\bimport\s+{re.escape(stem)}\b',
            rf'\bfrom\s+{re.escape(stem)}\s+import\b',
            rf'\b{re.escape(stem)}\.',
            rf'\b{re.escape(stem)}\.py\b',
        ]

        if any(re.search(pattern, low) for pattern in import_patterns):
            python_refs[target].append(source)

print("=" * 78)
print("SIGNATURE MACHINE")
print("STEP 1 - DEPENDENCY / REFERENCE AUDIT")
print("=" * 78)
print()
print(f"PROJECT ROOT: {ROOT}")
print(f"TOTAL FILES SCANNED: {len(files)}")
print(f"VERSIONED / OLD / BACKUP CANDIDATES: {len(versioned)}")
print()

print("=" * 78)
print("[1] VERSIONED / OLD / BACKUP CANDIDATES")
print("=" * 78)

for p in versioned:
    try:
        size = p.stat().st_size
    except Exception:
        size = 0

    print(f"{p.relative_to(ROOT)}    [{size:,} bytes]")

print()
print("=" * 78)
print("[2] DEPENDENCY STATUS")
print("=" * 78)

for target in versioned:
    rel = target.relative_to(ROOT)
    refs = references.get(target, [])
    py = python_refs.get(target, [])

    print()
    print(f"TARGET: {rel}")
    print(f"REFERENCED_BY_COUNT: {len(refs)}")
    print(f"PYTHON_IMPORT_COUNT: {len(py)}")

    if refs:
        print("REFERENCED_BY:")
        for src in sorted(set(refs), key=lambda x: str(x).lower()):
            print(f"  - {src.relative_to(ROOT)}")
    else:
        print("REFERENCED_BY: NONE")

    if py:
        print("PYTHON_IMPORTS:")
        for src in sorted(set(py), key=lambda x: str(x).lower()):
            print(f"  - {src.relative_to(ROOT)}")
    else:
        print("PYTHON_IMPORTS: NONE")

    if not refs and not py:
        print("INITIAL_CLASSIFICATION: UNUSED_CANDIDATE")
    elif py:
        print("INITIAL_CLASSIFICATION: ACTIVE_DEPENDENCY")
    else:
        print("INITIAL_CLASSIFICATION: REFERENCED_NON_PYTHON")

print()
print("=" * 78)
print("[3] IMPORTANT CURRENT ARCHITECTURE FILES")
print("=" * 78)

important = [
    "core.py",
    "build_motion_style_state.py",
    "build_customer_packages_v2_3.py",
    "build_reference_manifest_v001.py",
    "online_training_final.py",
    "online_training_final.html",
    "online_training_with_package.py",
    "reference_feature_extractor.py",
    "reference_analyzer.py",
    "stroke_engine.py",
    "workspace_manager.py",
]

for name in important:
    p = ROOT / name
    print(f"{name:<40} {'EXISTS' if p.exists() else 'MISSING'}")

print()
print("=" * 78)
print("[4] CURRENT LEARNING ARCHITECTURE")
print("=" * 78)

architecture_paths = [
    ROOT / "online_training_data" / "reference_learning" / "samples",
    ROOT / "online_training_data" / "reference_learning" / "knowledge" / "index.json",
    ROOT / "online_training_data" / "reference_learning" / "knowledge" / "aggregate.json",
    ROOT / "online_training_data" / "motion_learning" / "motion_style_state.json",
]

for p in architecture_paths:
    print(f"{p.relative_to(ROOT)}    {'EXISTS' if p.exists() else 'MISSING'}")

print()
print("=" * 78)
print("[5] VERSIONED FILES WITH ZERO REFERENCES")
print("=" * 78)

unused = []

for target in versioned:
    if not references.get(target) and not python_refs.get(target):
        unused.append(target)

if unused:
    for p in unused:
        print(p.relative_to(ROOT))
else:
    print("NONE")

print()
print("=" * 78)
print("[6] VERSIONED FILES WITH ACTIVE REFERENCES")
print("=" * 78)

active = []

for target in versioned:
    if references.get(target) or python_refs.get(target):
        active.append(target)

if active:
    for p in active:
        print(p.relative_to(ROOT))
else:
    print("NONE")

print()
print("=" * 78)
print("[7] NO DELETIONS PERFORMED")
print("=" * 78)
print("This audit is read-only.")
print("No project files were modified or deleted.")
print()
print("STEP 1 AUDIT COMPLETE")
print("=" * 78)

# Save the exact same report by rerunning captured output is inconvenient,
# so this script writes the report by invoking itself through the console.
