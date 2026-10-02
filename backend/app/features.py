"""Feature engineering shared by training and the live app.

The same function builds the model input in both places. This matters: if
training and the app prepare the numbers differently, the model sees data it
was never trained on and its answers become meaningless.

Raw landmarks say "the left hip is at 43% of the picture width". That changes
when the person stands somewhere else or further from the camera. So we:

1. put x and y on the same scale (multiply x by the picture's width/height),
2. move the origin to the middle of the hips  (position no longer matters),
3. divide by the torso length                 (distance to camera no longer matters).

What is left describes only the shape of the body.
"""
from __future__ import annotations

import numpy as np

# Landmark sets used by each classifier (names follow MediaPipe).
UPPER_BODY = ["nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
              "left_wrist", "right_wrist", "left_hip", "right_hip"]
FULL_BODY = UPPER_BODY + ["left_knee", "right_knee", "left_ankle", "right_ankle",
                          "left_heel", "right_heel", "left_foot_index", "right_foot_index"]
LOWER_FOCUS = ["nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip",
               "left_knee", "right_knee", "left_ankle", "right_ankle",
               "left_heel", "right_heel", "left_foot_index", "right_foot_index"]


def body_shape_features(xy: np.ndarray, names: list[str]) -> np.ndarray:
    """xy: (n, k, 2) landmark positions with x already multiplied by the aspect ratio.

    Returns (n, 2k): hip-centred, torso-scaled coordinates.
    """
    i = {n: j for j, n in enumerate(names)}
    hip = (xy[:, i["left_hip"]] + xy[:, i["right_hip"]]) / 2
    shoulder = (xy[:, i["left_shoulder"]] + xy[:, i["right_shoulder"]]) / 2
    torso = np.linalg.norm(shoulder - hip, axis=-1, keepdims=True)
    torso = np.where(torso < 1e-6, np.nan, torso)
    out = (xy - hip[:, None, :]) / torso[:, None, :]
    return out.reshape(len(xy), -1)


def mirror(xy: np.ndarray, names: list[str]) -> np.ndarray:
    """The same pose as seen in a mirror: flip x and swap every left/right pair.

    Used to double the training data, so a model trained on people facing left
    also works on people facing right.
    """
    swapped = [n.replace("left_", "#").replace("right_", "left_").replace("#", "right_") for n in names]
    order = [names.index(n) for n in swapped]
    out = xy[:, order, :].copy()
    out[:, :, 0] *= -1
    return out
