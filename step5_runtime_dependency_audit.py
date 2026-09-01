from pathlib import Path
import ast

ROOT = Path(".").resolve()
OUT = ROOT / "STEP5_RUNTIME_DEPENDENCY_AUDIT.txt"

files = sorted(
    p for p in ROOT.rglob("*.py")
    if ".venv" not in p.parts
    and "__pycache__" not in p.parts
)

lines = []
lines.append("=" * 80)
lines.append("SIGNATURE MACHINE")
lines.append("STEP 5 — RUNTIME DEPENDENCY AUDIT")
lines.append("=" * 80)
lines.append(f"ROOT: {ROOT}")
lines.append(f"PYTHON FILES: {len(files)}")
lines.append("")

for path in files:
    rel = path.relative_to(ROOT)

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        lines.append(f"[PARSE ERROR] {rel}: {exc}")
        continue

    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    lines.append("-" * 80)
    lines.append(str(rel))
    lines.append(f"SIZE: {path.stat().st_size}")

    if imports:
        lines.append("IMPORTS:")
        for item in sorted(set(imports)):
            lines.append(f"  {item}")
    else:
        lines.append("IMPORTS: NONE")

lines.append("")
lines.append("=" * 80)
lines.append("STEP 5 AUDIT COMPLETE")
lines.append("READ-ONLY — NO FILES MODIFIED OR DELETED")
lines.append("=" * 80)

OUT.write_text("\n".join(lines), encoding="utf-8")

print(f"CREATED: {OUT}")
