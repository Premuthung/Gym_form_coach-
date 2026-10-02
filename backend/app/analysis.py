"""Step 3 of form analysis: count repetitions, check each one, and give a score.

The pipeline for one video:

    landmarks  ->  angles over time  ->  repetitions  ->  checks per repetition  ->  score + advice

Every exercise is described by data in catalog.json (which angle to follow, and a list of
checks with a "good" and a "bad" value). This file is the engine that runs those rules, so
adding a new exercise means adding data, not code.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import classifiers
from .geometry import camera_view, compute_metrics, pick_side, side_visibility
from .pose import LM, PoseSequence

MIN_COVERAGE = 0.5          # a person must be found in at least half of the frames
MIN_REP_RANGE = 25.0        # degrees the main joint must move for the motion to count as reps
MIN_REP_SECONDS = 0.5
BOUNDARY_SEARCH_SECONDS = 1.5
CLASSIFIER_THRESHOLD = 0.7  # a frame counts as "wrong" when the model is at least 70% sure
HOLD_WINDOW_SECONDS = 2.0
# Rep detection thresholds, as a share of the range the main joint covers in this video.
# ENTER is kept under one half so that a half rep is still counted (and then marked down
# by the range-of-motion check) instead of silently disappearing.
ENTER_SHARE, EXIT_SHARE = 0.45, 0.20
# Measured on the demo videos: a straight limb reads ~179 deg in the picture but only ~165 deg
# on MediaPipe's 3D landmarks. When we must use 3D (front view), "straight" targets are relaxed.
STRAIGHT_LIMB_3D_OFFSET = 10.0

ANGLE_METRICS = {"elbow", "knee", "hip", "shoulder", "body_line", "knee_both", "elbow_both"}
HIGHLIGHT = {
    "elbow": ["shoulder", "elbow", "wrist"], "elbow_both": ["shoulder", "elbow", "wrist"],
    "knee": ["hip", "knee", "ankle"], "knee_both": ["hip", "knee", "ankle"],
    "torso_lean": ["shoulder", "hip"], "upper_arm_swing": ["shoulder", "elbow"],
    "hip_offset": ["shoulder", "hip", "ankle"], "body_line": ["shoulder", "hip", "ankle"],
    "classifier": ["shoulder", "hip", "knee"], "knee_ankle_ratio": ["knee", "ankle"],
}
METRIC_LABEL = {
    "elbow": "Elbow angle", "elbow_both": "Elbow angle", "knee": "Knee angle", "knee_both": "Knee angle",
    "body_line": "Body line angle",
}
GROUP_LABEL = {"range": "Range of motion", "posture": "Posture and stability", "control": "Control and tempo"}
GROUP_PRAISE = {
    "range": "Full range of motion on your reps.",
    "posture": "Your body position stayed stable.",
    "control": "Good, controlled speed.",
}
PART_WORDS = {"shoulder": "shoulder", "elbow": "elbow", "wrist": "wrist", "hip": "hip", "knee": "knee", "ankle": "ankle"}


@dataclass
class Rep:
    start: int
    peak: int
    end: int


def find_reps(signal: np.ndarray, t: np.ndarray, start: str) -> list[Rep]:
    """Find repetitions in an angle signal with a two-threshold state machine.

    We flip the signal if needed so that the hardest point of every rep is a maximum.
    Two thresholds are placed inside the range the signal actually covers:

        the motion must rise above ENTER (45% of the range) to begin a rep
        and fall below EXIT (20% of the range) to finish it.

    Using two thresholds instead of one (this is called hysteresis) stops small shakes
    around a single line from being counted as many reps.
    """
    u = -signal if start == "extended" else signal.copy()
    if np.isnan(u).all():
        return []
    lo, hi = np.nanpercentile(u, [5, 95])
    span = hi - lo
    if span < MIN_REP_RANGE:
        return []
    enter, exit_ = lo + ENTER_SHARE * span, lo + EXIT_SHARE * span
    fps = (len(t) - 1) / max(t[-1] - t[0], 1e-6)
    reach = max(1, int(BOUNDARY_SEARCH_SECONDS * fps))

    reps: list[Rep] = []
    state = "unknown"  # the video may begin in the middle of a rep; wait for the first rest
    enter_i = peak_i = prev_exit_i = 0
    for i, value in enumerate(u):
        if state == "unknown":
            if value < exit_:
                state, prev_exit_i = "rest", i
        elif state == "rest":
            if value > enter:
                state, enter_i, peak_i = "work", i, i
        elif state == "work":
            if value > u[peak_i]:
                peak_i = i
            if value < exit_:
                a0 = max(prev_exit_i, enter_i - reach)
                start_i = a0 + int(np.argmin(u[a0:enter_i + 1]))
                b1 = min(len(u), i + reach)
                # stop the search for the end of this rep where the next rep begins
                nxt = np.nonzero(u[i:b1] > enter)[0]
                if len(nxt):
                    b1 = i + int(nxt[0])
                end_i = i + int(np.argmin(u[i:max(b1, i + 1)]))
                if t[end_i] - t[start_i] >= MIN_REP_SECONDS:
                    reps.append(Rep(start_i, peak_i, end_i))
                state, prev_exit_i = "rest", i
    return reps


def check_score(value: float, good: float, bad: float) -> float:
    """100 when the value is at `good` or better, 0 at `bad` or worse, a straight line between."""
    if np.isnan(value):
        return float("nan")
    return float(np.clip((value - bad) / (good - bad), 0.0, 1.0) * 100.0)


def _measure(check: dict, metrics: dict, rep: Rep, t: np.ndarray, err: np.ndarray | None,
             primary_flipped: np.ndarray, enter_level: float, hold_seconds: float | None) -> tuple[float, int]:
    """The measured value of one check on one rep, and the frame that shows it best."""
    stat, metric = check["stat"], check["metric"]
    sl = slice(rep.start, rep.end + 1)
    if metric == "duration":
        if stat == "hold":
            return float(hold_seconds or 0.0), rep.peak
        return float(t[rep.end] - t[rep.start]), rep.peak
    if metric == "classifier":
        if err is None:
            return float("nan"), rep.peak
        window = err[sl]
        if check.get("window") == "peak":  # only judge the deep part of the rep
            deep = primary_flipped[sl] >= enter_level
            window = window[deep] if deep.any() else window
        if np.isnan(window).all():
            return float("nan"), rep.peak
        return float(np.nanmean(window >= CLASSIFIER_THRESHOLD)), rep.start + int(np.nanargmax(err[sl]))
    x = metrics[metric]
    seg = x[sl]
    if stat == "at_peak":
        return float(x[rep.peak]), rep.peak
    if stat == "at_start":
        return float((x[rep.start] + x[rep.end]) / 2), rep.start
    if stat == "max":
        return float(np.nanmax(seg)), rep.start + int(np.nanargmax(seg))
    if stat == "min":
        return float(np.nanmin(seg)), rep.start + int(np.nanargmin(seg))
    if stat == "mean":
        worst = np.nanargmin(seg) if check["good"] > check["bad"] else np.nanargmax(seg)
        return float(np.nanmean(seg)), rep.start + int(worst)
    if stat == "range":
        return float(np.nanmax(seg) - np.nanmin(seg)), rep.start + int(np.nanargmax(seg))
    raise ValueError(f"unknown stat {stat}")


def _detail(check: dict, value: float) -> str:
    """One plain sentence with the measured number and the target."""
    good, metric, stat = check["good"], check["metric"], check["stat"]
    at_most = good < check["bad"]
    if metric == "duration" and stat == "hold":
        return f"You held for {value:.0f} seconds. Target: {good:.0f} seconds or more."
    if metric == "duration":
        return f"A rep took {value:.1f} seconds on average. Target: {good:.1f} seconds or more."
    if metric == "classifier":
        return f"The posture model flagged {value * 100:.0f}% of the frames it checked."
    if metric == "hip_offset":
        side = "below" if value < 0 else "above"
        return f"Your hips were {abs(value) * 100:.0f}% of your body length {side} the straight line."
    if metric == "knee_ankle_ratio":
        return (f"At the bottom your knees were {value * 100:.0f}% as wide apart as your ankles. "
                f"Target: {good * 100:.0f}% or more.")
    if stat == "range":
        return f"It moved through {value:.0f} degrees during a rep. Target: under {good:.0f} degrees."
    word = METRIC_LABEL.get(metric, "Angle").lower() if metric in METRIC_LABEL else "angle"
    if metric == "torso_lean":
        word = "upper-body lean"
    if metric == "upper_arm_swing":
        word = "upper-arm angle"
    return f"Measured {word}: {value:.0f} degrees. Target: {good:.0f} degrees or {'less' if at_most else 'more'}."


def _verdict(score: int) -> str:
    if score >= 85:
        return "Great form"
    if score >= 70:
        return "Good - a few things to fix"
    if score >= 50:
        return "Needs work"
    return "Let's fix the basics first"


def _failure(reason: str, tips: list[str], **extra) -> dict:
    return {"ok": False, "reason": reason, "tips": tips, **extra}


def analyze(seq: PoseSequence, exercise: dict) -> dict:
    """Score one video for one exercise. Returns plain data (ready to send as JSON)."""
    cfg = exercise["analysis"]
    base = {
        "duration_s": round(float(seq.t[-1]), 1), "frames_analyzed": int(len(seq.t)),
        "pose_coverage": round(seq.coverage, 2), "truncated": seq.truncated,
    }
    if seq.coverage < MIN_COVERAGE:
        return _failure(
            "We could not see a person clearly in this video.",
            ["Make sure your whole body is in the picture.", "Use good light and avoid filming against a window.",
             "Place the phone 2-3 metres away and keep it still."], **base)

    side = pick_side(seq)
    view = camera_view(seq)
    use_3d = view == "front"
    metrics = compute_metrics(seq, side, use_3d)
    t = seq.t

    warnings: list[str] = []
    wanted_view = exercise.get("camera", {}).get("view", "side")
    if wanted_view == "side" and view == "front":
        warnings.append("This video is filmed from the front. Angles were estimated in 3D and are less exact. "
                        "Film from the side for a more accurate score.")
    visibility = side_visibility(seq, side, cfg["parts"])
    if visibility < 0.6:
        names = ", ".join(PART_WORDS[p] for p in cfg["parts"])
        warnings.append(f"Parts of your body ({names}) were hard to see. Move the phone back or remove things in the way.")
    if seq.truncated:
        warnings.append("Only the first 60 seconds were analysed.")

    err = classifiers.error_probability(seq, cfg["classifier"]) if cfg.get("classifier") else None

    primary = metrics[cfg["primary"]]
    hold_seconds = None
    if cfg["type"] == "hold":
        # Plank: the "reps" are 2-second windows of the time the body is close to horizontal.
        active = np.nonzero(seq.found & (metrics["torso_lean"] > 50))[0]
        if len(active) < seq.fps * 3:
            return _failure("We could not find a plank hold of at least 3 seconds.",
                            ["Film from the side with your whole body in the picture.",
                             "Start recording when you are already in position."], **base, view=view, warnings=warnings)
        hold_seconds = len(active) / seq.fps
        size = max(2, int(HOLD_WINDOW_SECONDS * seq.fps))
        reps = [Rep(int(active[i]), int(active[min(i + size // 2, len(active) - 1)]), int(active[min(i + size - 1, len(active) - 1)]))
                for i in range(0, len(active) - size // 2, size)]
        flipped, enter_level = primary, -np.inf
    else:
        reps = find_reps(primary, t, cfg["start"])
        flipped = -primary if cfg["start"] == "extended" else primary
        lo, hi = np.nanpercentile(flipped, [5, 95])
        enter_level = lo + 0.6 * (hi - lo)  # the deep part of a rep, used by posture models
        if not reps:
            return _failure(
                "We could not find a full repetition in this video.",
                [f"We look for your {METRIC_LABEL.get(cfg['primary'], 'joint angle').lower()} moving through a clear range.",
                 "Record at least 3 full reps, from the start position back to the start position.",
                 exercise.get("camera", {}).get("tip", "Film from the side.")],
                **base, view=view, warnings=warnings)

    # ---- run every check on every rep -------------------------------------------------
    checks = []
    for check in cfg["checks"]:
        if "views" in check and view not in check["views"]:
            continue
        if check["metric"] == "classifier":
            if err is None:
                continue
            check = {**check, "window": cfg.get("classifier_window")}
        good, bad = check["good"], check["bad"]
        if use_3d and check["metric"] in ANGLE_METRICS and good >= 150:
            if good < bad:
                continue  # "do not lock the joint" cannot be judged on 3D landmarks
            good, bad = good - STRAIGHT_LIMB_3D_OFFSET, bad - STRAIGHT_LIMB_3D_OFFSET
        checks.append({**check, "good": good, "bad": bad})

    rep_rows = []
    per_check: dict[str, list[tuple[float, float, int]]] = {c["id"]: [] for c in checks}
    for n, rep in enumerate(reps, start=1):
        total = weight_sum = 0.0
        row_checks = {}
        for c in checks:
            value, frame = _measure(c, metrics, rep, t, err, flipped, enter_level, hold_seconds)
            score = check_score(value, c["good"], c["bad"])
            per_check[c["id"]].append((value, score, frame))
            if not np.isnan(score):
                total += score * c["weight"]
                weight_sum += c["weight"]
                row_checks[c["id"]] = {"value": round(value, 2), "score": round(score)}
        rep_rows.append({
            "n": n, "t_start": round(float(t[rep.start]), 2), "t_peak": round(float(t[rep.peak]), 2),
            "t_end": round(float(t[rep.end]), 2),
            "score": round(total / weight_sum) if weight_sum else None, "checks": row_checks,
        })

    scored = [r["score"] for r in rep_rows if r["score"] is not None]
    if not scored:
        return _failure("The joints needed for this exercise were not visible.",
                        [exercise.get("camera", {}).get("tip", "Film from the side.")], **base, view=view, warnings=warnings)
    overall = round(float(np.mean(scored)))

    # ---- sub-scores, problems and praise -----------------------------------------------
    subscores, issues, positives = {}, [], []
    for group, label in GROUP_LABEL.items():
        num = den = 0.0
        for c in checks:
            s = [x[1] for x in per_check[c["id"]] if not np.isnan(x[1])]
            if c["group"] == group and s:
                num += np.mean(s) * c["weight"]
                den += c["weight"]
        if den:
            subscores[group] = {"label": label, "score": round(num / den)}
            if num / den >= 85:
                positives.append(GROUP_PRAISE[group])

    for c in checks:
        rows = [(i, *x) for i, x in enumerate(per_check[c["id"]]) if not np.isnan(x[1])]
        if not rows:
            continue
        scores = np.array([r[2] for r in rows])
        flagged = [r for r in rows if r[2] < 60]
        # Report a check when the average is weak, when a third of the reps fail it,
        # or when a single rep fails it badly.
        if scores.mean() >= 75 and len(flagged) < max(1, len(rows) / 3) and scores.min() >= 35:
            continue
        shown = flagged or rows
        worst = min(shown, key=lambda r: r[2])
        mean_value = float(np.mean([r[1] for r in shown]))
        mean_score = float(scores.mean())
        issues.append({
            "id": c["id"], "group": c["group"], "title": c["title"], "fix": c["fix"],
            "detail": _detail(c, mean_value),
            "severity": "high" if mean_score < 40 else "medium" if mean_score < 70 else "low",
            "score": round(mean_score),
            "reps_affected": [r[0] + 1 for r in flagged],
            "t": round(float(t[worst[3]]), 2),
            "frame": int(worst[3]),
            "highlight": [LM[f"{side}_{p}"] for p in HIGHLIGHT.get(c["metric"], [])] if c["metric"] != "duration" else None,
        })
    issues.sort(key=lambda i: i["score"])

    confidence = "high"
    if view != wanted_view or visibility < 0.75:
        confidence = "medium"
    if visibility < 0.6 or seq.coverage < 0.8 or (wanted_view == "side" and view == "front"):
        confidence = "low"

    unit = "window" if cfg["type"] == "hold" else "rep"
    return {
        "ok": True, **base,
        "type": cfg["type"], "score": overall, "verdict": _verdict(overall),
        "rep_count": len(reps) if cfg["type"] == "reps" else None,
        "hold_seconds": round(hold_seconds, 1) if hold_seconds else None,
        "unit": unit, "reps": rep_rows, "subscores": subscores,
        "issues": issues, "positives": positives, "warnings": warnings,
        "view": view, "side": side, "angles_from": "3D landmarks" if use_3d else "picture (2D)",
        "confidence": confidence, "classifier_used": cfg.get("classifier") if err is not None else None,
        "series": {
            "label": METRIC_LABEL.get(cfg["primary"], cfg["primary"]),
            "t": [round(float(x), 2) for x in t],
            "value": [None if np.isnan(v) else round(float(v), 1) for v in primary],
        },
    }
