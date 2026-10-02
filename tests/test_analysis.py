"""Tests for the rule engine, using a synthetic stick figure.

No public video dataset exists for machine exercises with labelled mistakes. To still test the
rules, we draw a stick figure with known joint angles (seen from the side), move it like a
lat pulldown, and check that the engine reports exactly the mistakes we put in.

This tests OUR logic (rep counting, checks, scoring). It does not test the pose model.

Run:  python tests/test_analysis.py        (or: pytest tests)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.analysis import analyze, check_score, find_reps  # noqa: E402
from app.pose import LM, PoseSequence  # noqa: E402

CATALOG = json.loads((ROOT / "backend" / "app" / "catalog.json").read_text(encoding="utf-8"))
FPS = 12


def wave(reps: int, rep_seconds: float, rest_value: float, peak_value: float, lead: float = 0.5) -> np.ndarray:
    """A signal that sits at rest_value, then moves smoothly to peak_value and back, `reps` times."""
    n = int(rep_seconds * FPS)
    one = rest_value + (peak_value - rest_value) * (1 - np.cos(np.linspace(0, 2 * np.pi, n))) / 2
    pad = np.full(int(lead * FPS), rest_value)
    return np.concatenate([pad, np.tile(one, reps), pad])


def polar(origin: np.ndarray, length: float, angle_deg: np.ndarray) -> np.ndarray:
    """Point at `length` from `origin`. 0 deg = straight up, 90 deg = to the right (picture coordinates)."""
    a = np.radians(angle_deg)
    return origin + length * np.stack([np.sin(a), -np.cos(a)], axis=-1)


def stick_figure(elbow: np.ndarray | None = None, knee: np.ndarray | None = None,
                 torso_lean: np.ndarray | None = None) -> PoseSequence:
    """A side-view person. Angles are per frame, in degrees (180 = straight limb)."""
    n = len(next(x for x in (elbow, knee, torso_lean) if x is not None))
    elbow = np.full(n, 170.0) if elbow is None else elbow
    knee = np.full(n, 170.0) if knee is None else knee
    lean = np.zeros(n) if torso_lean is None else torso_lean

    hip = np.tile([0.5, 0.60], (n, 1))
    shoulder = polar(hip, 0.25, lean)
    elbow_pt = polar(shoulder, 0.14, lean + 20)                 # upper arm raised in front, moving with the torso
    wrist = polar(elbow_pt, 0.13, lean + 20 + (180 - elbow))    # forearm folds back as the elbow bends
    knee_pt = polar(hip, 0.22, np.full(n, 100.0))               # seated: thigh points forward
    ankle = polar(knee_pt, 0.22, 100.0 + (180 - knee))
    nose = polar(shoulder, 0.10, lean)

    image = np.zeros((n, 33, 4))
    image[:, :, :2] = hip[:, None, :]
    image[:, :, 3] = 0.95
    parts = {"shoulder": shoulder, "elbow": elbow_pt, "wrist": wrist, "hip": hip, "knee": knee_pt,
             "ankle": ankle, "heel": ankle, "foot_index": ankle + [0.05, 0.0]}
    for name, pts in parts.items():
        for side in ("left", "right"):
            image[:, LM[f"{side}_{name}"], :2] = pts
    image[:, LM["nose"], :2] = nose
    image[:, [LM[f"right_{p}"] for p in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")], 3] = 0.4  # far side is hidden

    world = np.zeros((n, 33, 3))
    world[:, :, :2] = image[:, :, :2] * 2          # a square 2 m picture; side view, so both shoulders share one x
    world[:, :, 2] = np.where(np.arange(33) % 2 == 0, 0.18, -0.18)[None, :]
    return PoseSequence(t=np.arange(n) / FPS, image=image, world=world, width=640, height=640, fps=FPS)


def issue_ids(result: dict) -> set[str]:
    return {i["id"] for i in result["issues"]}


# ---- rep counting -----------------------------------------------------------------------
def test_counts_clean_reps():
    s = wave(5, 3.0, 170, 70)
    assert len(find_reps(s, np.arange(len(s)) / FPS, "extended")) == 5


def test_counts_reps_that_start_flexed():
    s = wave(4, 3.0, 85, 165)
    assert len(find_reps(s, np.arange(len(s)) / FPS, "flexed")) == 4


def test_small_shakes_are_not_reps():
    rng = np.random.default_rng(0)
    s = 160 + rng.normal(0, 3, 200)
    assert find_reps(s, np.arange(200) / FPS, "extended") == []


def test_noise_does_not_split_a_rep():
    rng = np.random.default_rng(1)
    s = wave(6, 2.5, 170, 80) + rng.normal(0, 4, len(wave(6, 2.5, 170, 80)))
    assert len(find_reps(s, np.arange(len(s)) / FPS, "extended")) == 6


def test_video_starting_mid_rep_drops_the_partial_rep():
    s = wave(4, 3.0, 170, 70)[int(0.5 * FPS) + int(1.5 * FPS):]   # cut in at the bottom of rep 1
    assert len(find_reps(s, np.arange(len(s)) / FPS, "extended")) == 3


# ---- scoring a single check --------------------------------------------------------------
def test_check_score_lower_is_better():
    assert check_score(80, good=85, bad=120) == 100
    assert check_score(120, good=85, bad=120) == 0
    assert check_score(102.5, good=85, bad=120) == 50


def test_check_score_higher_is_better():
    assert check_score(160, good=155, bad=125) == 100
    assert check_score(125, good=155, bad=125) == 0
    assert check_score(140, good=155, bad=125) == 50


# ---- whole pipeline on the stick figure -----------------------------------------------------
LAT = CATALOG["exercises"]["lat_pulldown"]


def test_good_lat_pulldown_scores_high_with_no_issues():
    r = analyze(stick_figure(elbow=wave(5, 3.0, 170, 70)), LAT)
    assert r["ok"] and r["rep_count"] == 5 and r["view"] == "side"
    assert r["score"] >= 95, r["score"]
    assert r["issues"] == []


def test_half_reps_are_reported():
    r = analyze(stick_figure(elbow=wave(5, 3.0, 170, 118)), LAT)
    assert r["rep_count"] == 5
    assert "rom_peak" in issue_ids(r) and r["score"] < 80


def test_not_straightening_the_arms_is_reported():
    r = analyze(stick_figure(elbow=wave(5, 3.0, 128, 70)), LAT)
    assert "rom_start" in issue_ids(r) and "rom_peak" not in issue_ids(r)


def test_fast_reps_are_reported():
    r = analyze(stick_figure(elbow=wave(6, 0.9, 170, 70)), LAT)
    assert r["rep_count"] == 6
    assert issue_ids(r) == {"tempo"}


def test_body_swing_is_reported():
    elbow = wave(5, 3.0, 170, 70)
    lean = wave(5, 3.0, 5, 45)          # the torso rocks back 40 degrees on every pull
    r = analyze(stick_figure(elbow=elbow, torso_lean=lean), LAT)
    assert {"swing", "lean"} <= issue_ids(r)
    assert r["subscores"]["range"]["score"] >= 95   # the arm movement itself was fine


def test_one_bad_rep_among_good_ones_is_reported():
    elbow = np.concatenate([wave(3, 3.0, 170, 70), wave(1, 3.0, 170, 122), wave(2, 3.0, 170, 70)])
    r = analyze(stick_figure(elbow=elbow), LAT)
    issue = next(i for i in r["issues"] if i["id"] == "rom_peak")
    assert issue["reps_affected"] == [4] and issue["severity"] == "low"


def test_leg_press_knee_lock_is_reported():
    r = analyze(stick_figure(knee=wave(5, 3.0, 179.5, 90)), CATALOG["exercises"]["leg_press"])
    assert r["rep_count"] == 5 and "lockout" in issue_ids(r)
    ok = analyze(stick_figure(knee=wave(5, 3.0, 165, 90)), CATALOG["exercises"]["leg_press"])
    assert ok["issues"] == [] and ok["score"] >= 95


def test_leg_extension_starts_flexed():
    r = analyze(stick_figure(knee=wave(5, 3.0, 90, 168)), CATALOG["exercises"]["leg_extension"])
    assert r["rep_count"] == 5 and r["issues"] == []


def test_no_person_in_video():
    seq = stick_figure(elbow=wave(3, 3.0, 170, 70))
    seq.image[:] = np.nan
    seq.world[:] = np.nan
    r = analyze(seq, LAT)
    assert r["ok"] is False and "person" in r["reason"]


def test_standing_still_gives_no_reps():
    r = analyze(stick_figure(elbow=np.full(120, 165.0)), LAT)
    assert r["ok"] is False and "repetition" in r["reason"]


# ---- the catalogue itself ---------------------------------------------------------------------
def test_catalog_is_consistent():
    known_metrics = {"elbow", "knee", "hip", "shoulder", "body_line", "knee_both", "elbow_both", "torso_lean",
                     "upper_arm_swing", "hip_offset", "knee_ankle_ratio", "duration", "classifier"}
    known_stats = {"at_peak", "at_start", "max", "min", "mean", "range", "rep", "hold", "error_share"}
    for m in CATALOG["machines"]:
        assert m["labels"], m["id"]
        for e in m["exercises"]:
            assert e in CATALOG["exercises"], f"{m['id']} points to unknown exercise {e}"
    for ex_id, ex in CATALOG["exercises"].items():
        for key in ("name", "muscles", "plan", "setup", "steps", "mistakes", "safety", "camera"):
            assert ex.get(key), f"{ex_id} is missing {key}"
        a = ex["analysis"]
        if a is None:
            continue
        assert a["type"] in ("reps", "hold") and a["primary"] in known_metrics
        ids = [c["id"] for c in a["checks"]]
        assert len(ids) == len(set(ids)), f"{ex_id} has duplicate check ids"
        for c in a["checks"]:
            assert c["metric"] in known_metrics and c["stat"] in known_stats, (ex_id, c["id"])
            assert c["good"] != c["bad"] and c["weight"] > 0 and c["group"] in ("range", "posture", "control")
            assert (c["metric"] == "classifier") <= ("classifier" in a), f"{ex_id}/{c['id']} needs a classifier"


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # AssertionError or a crash: both count as a failure
            failed += 1
            print("FAIL", name, "->", repr(e))
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
