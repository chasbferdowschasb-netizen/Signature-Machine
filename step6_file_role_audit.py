from pathlib import Path
import re

ROOT = Path(".").resolve()
OUT = ROOT / "STEP6_FILE_ROLE_AUDIT.txt"

files = sorted(
    p for p in ROOT.rglob("*")
    if p.is_file()
    and ".git" not in p.parts
    and ".venv" not in p.parts
    and "__pycache__" not in p.parts
)

py_files = [p for p in files if p.suffix.lower() == ".py"]

lines = [
    "=" * 80,
    "SIGNATURE MACHINE",
    "STEP 6 — FILE ROLE AUDIT",
    "=" * 80,
    f"ROOT: {ROOT}",
    f"TOTAL FILES: {len(files)}",
    f"PYTHON FILES: {len(py_files)}",
    "",
]

for path in py_files:
    rel = path.relative_to(ROOT)
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        lines.append(f"[READ ERROR] {rel}: {exc}")
        continue

    lines.append("-" * 80)
    lines.append(str(rel))
    lines.append(f"SIZE: {path.stat().st_size}")

    markers = []

    patterns = {
        "IMPORT_TARGET": r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)",
        "VERSIONED": r"(?:_v\d+|v\d+|STEP\d+|FIXED|BACKUP|DIAGNOSTIC)",
        "AUDIT": r"audit|dependency|validation|inspect|test",
        "GENERATION": r"generate|generation|candidate",
        "LEARNING": r"learn|knowledge|motion|trajectory",
        "TRAINING": r"training|train",
        "VISUAL": r"visual|analyzer",
    }

    for name, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            markers.append(name)

    lines.append(
        "ROLE_MARKERS: "
        + (", ".join(markers) if markers else "NONE")
    )

    imports = re.findall(
        r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)",
        text,
        re.MULTILINE,
    )

    if imports:
        lines.append("IMPORTS:")
        for item in sorted(set(imports)):
            lines.append(f"  {item}")

lines.extend([
    "",
    "=" * 80,
    "STEP 6 AUDIT COMPLETE",
    "READ-ONLY — NO FILES MODIFIED OR DELETED",
    "=" * 80,
])

OUT.write_text("\n".join(lines), encoding="utf-8")

print(f"CREATED: {OUT}")
