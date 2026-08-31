from pathlib import Path
import json
from collections import Counter

root = Path(r".\online_training_data\reference_learning\samples")

key_counts = Counter()
profile_counts = Counter()
files = 0
strokes = 0

for d in sorted(root.glob("sample_*")):
    path = d / "trajectory.json"
    if not path.is_file():
        continue

    data = json.loads(path.read_text(encoding="utf-8"))
    files += 1

    for stroke in data.get("strokes", []):
        strokes += 1
        key_counts.update(stroke.keys())
        profile_counts.update(
            k for k in stroke.keys()
            if k.endswith("_profile")
        )

print("TRAJECTORY_FILES:", files)
print("TOTAL_STROKES:", strokes)

print("STROKE_KEYS:")
for k, v in key_counts.most_common():
    print(" ", k, v)

print("PROFILE_KEYS:")
for k, v in profile_counts.most_common():
    print(" ", k, v)
