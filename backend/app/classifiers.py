"""Loads the trained posture classifiers and runs them on a pose sequence.

The models are trained by training/train_form_classifiers.py. They are optional:
if a model file is missing, the exercise is still scored by the angle rules.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

from .features import body_shape_features
from .geometry import pixel_points, smooth
from .pose import LM, PoseSequence

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


@lru_cache(maxsize=None)
def load(name: str) -> dict | None:
    path = MODEL_DIR / f"{name}.joblib"
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception as e:  # e.g. the file was saved by a different scikit-learn version
        print(f"[classifiers] could not load {path.name}: {e}")
        return None


def error_probability(seq: PoseSequence, name: str) -> np.ndarray | None:
    """Per-frame probability (0..1) that the posture is wrong. None if the model is unavailable."""
    bundle = load(name)
    if bundle is None:
        return None
    ids = [LM[n] for n in bundle["landmarks"]]
    xy = pixel_points(seq)[:, ids, :]
    X = body_shape_features(xy, bundle["landmarks"])
    ok = ~np.isnan(X).any(axis=1)
    out = np.full(len(X), np.nan)
    if ok.any():
        proba = bundle["model"].predict_proba(X[ok])
        correct_col = bundle["classes"].index(bundle["correct"])
        out[ok] = 1.0 - proba[:, correct_col]
    return smooth(out, max(1, round(seq.fps * 0.5)))
