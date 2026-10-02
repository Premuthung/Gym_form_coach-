"""Download openly licensed gym-equipment photos from Wikimedia Commons.

These photos are used ONLY to measure how well the machine recogniser works
(see training/eval_machine_recognition.py). Nothing is trained on them.

Every downloaded file is listed in data/eval_machines/ATTRIBUTION.csv with its
author, licence and source page, because most Commons licences require credit.

Run:  python training/fetch_eval_images.py               (keyword search)
      python training/fetch_eval_images.py --categories  (Commons categories, cleaner)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval_machines"
API = "https://commons.wikimedia.org/w/api.php"
UA = "GymFormCoachPrototype/0.1 (local student prototype; evaluation only)"
PER_CLASS = 8
THUMB_WIDTH = 500   # Commons asks clients to use its standard thumbnail sizes
PAUSE = 4.0         # seconds between requests; faster than this gets "429 Too Many Requests"

# machine id -> search phrases tried in order until PER_CLASS images are found
QUERIES: dict[str, list[str]] = {
    "lat_pulldown": ["lat pulldown machine", "lat pulldown"],
    "seated_cable_row": ["seated cable row machine", "seated row machine gym"],
    "chest_press_machine": ["chest press machine gym"],
    "shoulder_press_machine": ["shoulder press machine gym"],
    "leg_press": ["leg press machine", "leg press gym"],
    "leg_extension": ["leg extension machine"],
    "leg_curl": ["leg curl machine"],
    "cable_machine": ["cable crossover machine", "cable machine gym pulley"],
    "smith_machine": ["smith machine gym"],
    "squat_rack": ["power rack gym", "squat rack barbell"],
    "dumbbells": ["dumbbell rack gym", "dumbbells gym"],
    "bench_press": ["bench press barbell bench gym"],
    "pec_deck": ["pec deck machine", "butterfly machine gym"],
    "treadmill": ["treadmill gym"],
    "exercise_bike": ["stationary exercise bike gym"],
    "rowing_machine": ["indoor rowing machine ergometer"],
    "exercise_mat": ["exercise mat yoga mat floor"],
}


# machine id -> Commons category. Categories are curated by people, so they are far less
# noisy than keyword search (which returned statues, flags and a sewing machine).
CATEGORIES: dict[str, str] = {
    "chest_press_machine": "Seated chest press",
    "leg_press": "Leg press machines",
    "lat_pulldown": "Pull-down",
    "leg_curl": "Leg curls",
    "smith_machine": "Smith machine",
    "squat_rack": "Power rack",
    "cable_machine": "Cable machine",
    "exercise_bike": "Stationary bicycles",
    "shoulder_press_machine": "Overhead press",
}


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_category = "--categories" in sys.argv
    prefix = "cat_" if by_category else ""
    sources = {m: [c] for m, c in CATEGORIES.items()} if by_category else QUERIES
    rows = []
    for machine, queries in sources.items():
        folder = OUT / machine
        folder.mkdir(exist_ok=True)
        seen: set[str] = set()
        for q in queries:
            if len(seen) >= PER_CLASS:
                break
            source = ({"generator": "categorymembers", "gcmtitle": f"Category:{q}", "gcmtype": "file", "gcmlimit": 20}
                      if by_category else
                      {"generator": "search", "gsrnamespace": 6, "gsrsearch": f"{q} filetype:bitmap", "gsrlimit": 20})
            time.sleep(PAUSE)
            try:
                data = api({
                    "action": "query", **source,
                    "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": THUMB_WIDTH,
                })
            except Exception as e:  # throttled or offline: keep what we already have
                print(f"  {machine}: request failed ({e}); skipping")
                continue
            pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
            for p in pages:
                if len(seen) >= PER_CLASS:
                    break
                info = (p.get("imageinfo") or [{}])[0]
                if info.get("mime") not in ("image/jpeg", "image/png") or p["title"] in seen:
                    continue
                thumb = info.get("thumburl") or info.get("url")
                ext = ".png" if info["mime"] == "image/png" else ".jpg"
                dest = folder / f"{prefix}{machine}_{len(seen):02d}{ext}"
                try:
                    req = urllib.request.Request(thumb, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        dest.write_bytes(r.read())
                except Exception as e:  # network hiccup: skip this file
                    print("  skip", p["title"], e)
                    continue
                meta = info.get("extmetadata", {})
                rows.append({
                    "file": f"{machine}/{dest.name}",
                    "title": p["title"],
                    "author": strip_html(meta.get("Artist", {}).get("value", "")),
                    "license": meta.get("LicenseShortName", {}).get("value", ""),
                    "source": info.get("descriptionurl", ""),
                })
                seen.add(p["title"])
                time.sleep(PAUSE)  # be polite to the server
        print(f"{machine}: {len(seen)} images")

    target = OUT / "ATTRIBUTION.csv"
    new_file = not target.exists()
    with open(target, "a", newline="", encoding="utf-8") as f:  # append: the two modes share one file
        w = csv.DictWriter(f, fieldnames=["file", "title", "author", "license", "source"])
        if new_file:
            w.writeheader()
        w.writerows(rows)
    print("wrote", OUT / "ATTRIBUTION.csv", len(rows), "rows")


if __name__ == "__main__":
    main()
