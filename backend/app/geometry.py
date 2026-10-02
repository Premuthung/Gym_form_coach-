"""Step 2 of form analysis: turn landmarks into numbers a coach would talk about.

Raw landmark positions change when the person stands closer to the camera or
moves to the left of the picture. Joint angles do not. So every check in this
app is built on angles (and a few ratios), never on raw positions.
"""
from __future__ import annotations

import warnings

import numpy as np

from .pose import LM, PoseSequence

SIDE_PARTS = ["shoulder", "elbow", "wrist", "hip", "knee", "ankle"]


def _angle_between(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Angle in degrees between two sets of vectors, row by row."""
    dot = (u * v).sum(axis=-1)
    norm = np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.degrees(np.arccos(np.clip(dot / norm, -1.0, 1.0)))


def joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle at joint b, formed by the points a-b-c. 180 = straight, 90 = right angle."""
    return _angle_between(a - b, c - b)


def smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Fill gaps, then apply a moving average to remove frame-to-frame jitter."""
    x = np.asarray(x, dtype=float).copy()
    ok = ~np.isnan(x)
    if ok.sum() < 2:
        return x
    idx = np.arange(len(x))
    x[~ok] = np.interp(idx[~ok], idx[ok], x[ok])
    window = max(1, window | 1)  # force an odd window
    if window == 1:
        return x
    pad = window // 2
    padded = np.pad(x, pad, mode="edge")
    return np.convolve(padded, np.ones(window) / window, mode="valid")


def pick_side(seq: PoseSequence) -> str:
    """The side of the body that the camera sees best (highest average visibility)."""
    vis = {}
    for side in ("left", "right"):
        ids = [LM[f"{side}_{p}"] for p in SIDE_PARTS]
        vis[side] = np.nanmean(seq.image[:, ids, 3]) if seq.found.any() else 0.0
    return "left" if vis["left"] >= vis["right"] else "right"


def camera_view(seq: PoseSequence) -> str:
    """'side' or 'front', from how wide the shoulders look compared with the torso.

    Seen from the front, shoulder width is about 0.7 x torso length.
    Seen from the side, the two shoulders overlap, so the ratio is close to 0.
    """
    if not seq.found.any():
        return "unknown"
    p = seq.world  # metres, so no aspect-ratio correction is needed
    shoulder_w = np.abs(p[:, LM["left_shoulder"], 0] - p[:, LM["right_shoulder"], 0])
    torso = np.linalg.norm(
        (p[:, LM["left_shoulder"]] + p[:, LM["right_shoulder"]]) / 2
        - (p[:, LM["left_hip"]] + p[:, LM["right_hip"]]) / 2, axis=-1)
    ratio = np.nanmedian(shoulder_w / torso)
    if ratio < 0.35:
        return "side"
    if ratio > 0.5:
        return "front"
    return "angled"


def pixel_points(seq: PoseSequence) -> np.ndarray:
    """Image landmarks in units of picture height, so x and y use the same scale."""
    pts = seq.image[:, :, :2].copy()
    pts[:, :, 0] *= seq.aspect
    return pts


def compute_metrics(seq: PoseSequence, side: str, use_3d: bool) -> dict[str, np.ndarray]:
    """All per-frame measurements used by the exercise rules, smoothed over ~0.3 s.

    use_3d=False -> angles measured in the picture (accurate when filmed from the side)
    use_3d=True  -> angles measured on the 3D world landmarks (works from any direction, noisier)
    """
    flat = pixel_points(seq)
    pts = seq.world if use_3d else flat

    def P(name: str, source=pts) -> np.ndarray:
        return source[:, LM[f"{side}_{name}"]]

    def both(fn) -> np.ndarray:
        """Average of a measurement over the left and right side."""
        out = []
        for s in ("left", "right"):
            out.append(fn(lambda n, s=s: pts[:, LM[f"{s}_{n}"]]))
        with warnings.catch_warnings():  # frames with no person are NaN on both sides; that is expected
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(np.stack(out), axis=0)

    m: dict[str, np.ndarray] = {}
    m["elbow"] = joint_angle(P("shoulder"), P("elbow"), P("wrist"))
    m["knee"] = joint_angle(P("hip"), P("knee"), P("ankle"))
    m["hip"] = joint_angle(P("shoulder"), P("hip"), P("knee"))
    m["shoulder"] = joint_angle(P("hip"), P("shoulder"), P("elbow"))
    m["body_line"] = joint_angle(P("shoulder"), P("hip"), P("ankle"))
    m["knee_both"] = both(lambda q: joint_angle(q("hip"), q("knee"), q("ankle")))
    m["elbow_both"] = both(lambda q: joint_angle(q("shoulder"), q("elbow"), q("wrist")))

    # Lean angles are always measured in the picture: "up" in the picture is up in the gym
    # as long as the phone is held straight. World landmarks have no reliable "up".
    up = np.array([0.0, -1.0])
    down = np.array([0.0, 1.0])
    torso = P("shoulder", flat) - P("hip", flat)
    m["torso_lean"] = _angle_between(torso, np.broadcast_to(up, torso.shape))
    upper_arm = P("elbow", flat) - P("shoulder", flat)
    m["upper_arm_swing"] = _angle_between(upper_arm, np.broadcast_to(down, upper_arm.shape))

    # Plank: how far the hip is above (+) or below (-) the straight shoulder-ankle line,
    # as a share of body length. Picture y grows downwards, hence the minus sign.
    sh, hp, an = P("shoulder", flat), P("hip", flat), P("ankle", flat)
    body = an - sh
    length = np.linalg.norm(body, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = ((hp - sh) * body).sum(axis=-1) / length**2
        line_y = sh[:, 1] + frac * body[:, 1]
        m["hip_offset"] = -(hp[:, 1] - line_y) / length

    # Squat, front view: distance between the knees divided by distance between the ankles.
    # Below ~0.9 the knees are inside the feet ("knees caving in"). Uses 3D landmarks (metres).
    w = seq.world
    knees = np.linalg.norm(w[:, LM["left_knee"]] - w[:, LM["right_knee"]], axis=-1)
    ankles = np.linalg.norm(w[:, LM["left_ankle"]] - w[:, LM["right_ankle"]], axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        m["knee_ankle_ratio"] = knees / ankles

    window = max(1, round(seq.fps * 0.3))
    return {k: smooth(v, window) for k, v in m.items()}


def side_visibility(seq: PoseSequence, side: str, parts: list[str]) -> float:
    """Average visibility (0..1) of the named joints on one side."""
    if not seq.found.any():
        return 0.0
    ids = [LM[f"{side}_{p}"] for p in parts]
    return float(np.nanmean(seq.image[:, ids, 3]))
