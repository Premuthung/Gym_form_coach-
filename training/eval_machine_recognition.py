"""Measure the machine recogniser on hand-checked photos.

Photos: data/eval_machines/curated.csv (downloaded by fetch_eval_images.py, then checked by eye).
The recogniser is exactly the one the app uses (backend/app/machine_id.py), including its
"not gym equipment" class and its confidence threshold.

    top-1     the first guess is right
    top-3     the right machine is among the 3 guesses the app shows
    accepted  the app was confident enough to say "This looks like ..."

Run:  python training/eval_machine_recognition.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import machine_id  # noqa: E402

PHOTOS = ROOT / "data" / "eval_machines"


def main() -> None:
    catalog = json.loads((ROOT / "backend" / "app" / "catalog.json").read_text(encoding="utf-8"))
    rec = machine_id.MachineRecognizer(catalog)
    rows = list(csv.DictReader(open(PHOTOS / "curated.csv")))

    top1 = top3 = accepted = accepted_right = 0
    per_class: dict[str, list[int]] = {}
    confusions: Counter = Counter()
    seconds = []
    for row in rows:
        t0 = time.time()
        result = rec.identify(Image.open(PHOTOS / row["file"]))
        seconds.append(time.time() - t0)
        guesses = [c["machine_id"] for c in result["candidates"]]
        hit = guesses[0] == row["label"]
        top1 += hit
        top3 += row["label"] in guesses
        if result["recognized"]:
            accepted += 1
            accepted_right += hit
        per_class.setdefault(row["label"], []).append(int(hit))
        if not hit:
            confusions[(row["label"], guesses[0])] += 1

    n = len(rows)
    report = {
        "model": machine_id.MODEL_NAME, "photos": n, "classes_with_photos": len(per_class),
        "top1": round(top1 / n, 3), "top3": round(top3 / n, 3),
        "accepted_share": round(accepted / n, 3),
        "accuracy_when_accepted": round(accepted_right / accepted, 3) if accepted else None,
        "seconds_per_photo": round(sorted(seconds)[len(seconds) // 2], 2),
        "per_class": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(per_class.items())},
        "most_common_mistakes": [f"{a} -> {b} ({c}x)" for (a, b), c in confusions.most_common(8)],
    }
    print(json.dumps(report, indent=2))
    (ROOT / "models" / "machine_recognition_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
