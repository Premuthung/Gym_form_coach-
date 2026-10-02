"""Train the three posture classifiers from open-source landmark data.

Data: CSV files from the MIT-licensed project "Exercise-Correction" by Ngo Hong Quoc Bao
(https://github.com/NgoQuocBao1010/Exercise-Correction). Each row is one video frame:
a label plus MediaPipe landmarks (x, y, z, visibility). We read the files in place and
do not copy them into this project.

    classifier            file                       classes
    bicep_lean_back       bicep_model/train.csv      C correct, L leaning back
    plank_posture         plank_model/train.csv      C correct, L low back, H high back
    lunge_knee_over_toe   lunge_model/err.train.csv  C correct, L knee over toe

How we measure honestly
-----------------------
Rows in these files are video frames in order. Frame 100 and frame 101 are almost the
same picture. If we split rows at random, near-copies of the test rows sit in the training
set and the score looks better than it is. This is called data leakage.

The files have no video id, so we rebuild groups: every unbroken run of the same label is
treated as one clip. Cross-validation then keeps a whole clip on one side of the split
(GroupKFold). We also report the random-split score next to it, to show how big the
illusion is, and the score on the authors' separate test file.

Run:  python training/train_form_classifiers.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold, KFold, cross_val_predict
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.features import FULL_BODY, LOWER_FOCUS, UPPER_BODY, body_shape_features, mirror  # noqa: E402

DATA = ROOT.parent / "Exercise-Correction-main" / "core"
OUT = ROOT / "models"

# The source videos are landscape 16:9 (checked: in the front-view squat data, shoulder width
# divided by torso height is 0.42 in normalised units = 0.75 x 9/16, the expected body ratio).
TRAIN_ASPECT = 16 / 9

# Neighbouring video frames are almost identical, so every 3rd frame carries nearly all of the
# information and training is 3x faster. The test file is always used in full.
FRAME_STEP = 3

TASKS = {
    "bicep_lean_back": dict(train="bicep_model/train.csv", test="bicep_model/test.csv",
                            landmarks=UPPER_BODY, correct="C"),
    "plank_posture": dict(train="plank_model/train.csv", test="plank_model/test.csv",
                          landmarks=FULL_BODY, correct="C"),
    "lunge_knee_over_toe": dict(train="lunge_model/err.train.csv", test="lunge_model/err.test.csv",
                                landmarks=LOWER_FOCUS, correct="C"),
}


def candidates() -> dict:
    return {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)),
        "random_forest": RandomForestClassifier(n_estimators=100, min_samples_leaf=5, n_jobs=-1, random_state=0),
        "mlp_64_32": make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3,
                                                                    early_stopping=True, max_iter=300, random_state=0)),
    }


def load(path: Path, landmarks: list[str], step: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns landmark positions (n, k, 2), labels, and a clip id for every row."""
    df = pd.read_csv(path)
    xy = np.stack([np.c_[df[f"{n}_x"] * TRAIN_ASPECT, df[f"{n}_y"]] for n in landmarks], axis=1)
    y = df["label"].to_numpy()
    clip = (df["label"] != df["label"].shift()).cumsum().to_numpy()
    return xy[::step], y[::step], clip[::step]


def build(xy: np.ndarray, y: np.ndarray, clip: np.ndarray, landmarks: list[str], augment: bool):
    X = body_shape_features(xy, landmarks)
    if not augment:
        return X, y, clip
    Xm = body_shape_features(mirror(xy, landmarks), landmarks)
    return np.vstack([X, Xm]), np.concatenate([y, y]), np.concatenate([clip, clip])


def main() -> None:
    warnings.filterwarnings("ignore")
    OUT.mkdir(exist_ok=True)
    report_path = OUT / "form_classifiers_report.json"
    report = {"sklearn_version": sklearn.__version__, "train_aspect": TRAIN_ASPECT,
              "frame_step": FRAME_STEP, "tasks": {}}

    for name, cfg in TASKS.items():
        lms = cfg["landmarks"]
        xy, y, clip = load(DATA / cfg["train"], lms, step=FRAME_STEP)
        xy_t, y_t, _ = load(DATA / cfg["test"], lms)
        X, Y, G = build(xy, y, clip, lms, augment=True)
        X_test = body_shape_features(xy_t, lms)
        n_clips = len(np.unique(clip))
        folds = min(5, n_clips)
        print(f"\n=== {name}: {len(y)} frames in {n_clips} clips, classes {dict(pd.Series(y).value_counts())}")

        rows = {}
        for model_name, model in candidates().items():
            grouped = cross_val_predict(model, X, Y, groups=G, cv=GroupKFold(n_splits=folds))
            random_ = cross_val_predict(model, X, Y, cv=KFold(n_splits=folds, shuffle=True, random_state=0))
            fitted = model.fit(X, Y)
            test_pred = fitted.predict(X_test)
            rows[model_name] = {
                "cv_by_clip_f1": round(f1_score(Y, grouped, average="macro"), 3),
                "cv_random_f1": round(f1_score(Y, random_, average="macro"), 3),
                "test_file_f1": round(f1_score(y_t, test_pred, average="macro"), 3),
                "test_file_accuracy": round(accuracy_score(y_t, test_pred), 3),
            }
            print(f"  {model_name:20s} {rows[model_name]}")

        # Choose by the honest number: cross-validation that keeps clips together.
        best = max(rows, key=lambda k: rows[k]["cv_by_clip_f1"])
        model = candidates()[best].fit(X, Y)
        classes = [str(c) for c in model.classes_]
        cm = confusion_matrix(y_t, model.predict(X_test), labels=model.classes_).tolist()
        print(f"  -> chosen: {best}; test-file confusion matrix {classes}: {cm}")

        joblib.dump({
            "model": model, "landmarks": lms, "classes": classes, "correct": cfg["correct"],
            "sklearn_version": sklearn.__version__, "name": name, "algorithm": best,
        }, OUT / f"{name}.joblib")
        report["tasks"][name] = {
            "frames": int(len(y)), "clips": int(n_clips), "classes": classes, "chosen": best,
            "models": rows, "test_confusion_matrix": cm, "test_frames": int(len(y_t)),
        }
        report_path.write_text(json.dumps(report, indent=2))  # saved after every task

    print("\nsaved models and report to", OUT)


if __name__ == "__main__":
    main()
