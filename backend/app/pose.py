"""Step 1 of form analysis: turn a video into body landmarks over time.

Model: MediaPipe Pose Landmarker (BlazePose GHUM, "full" variant), a pretrained
neural network from Google. For every frame it returns 33 body landmarks:

* image landmarks  - x, y in the picture (0..1), plus a visibility score
* world landmarks  - x, y, z in metres, with the hip centre as the origin

We do not train this model. We only run it (this is called inference).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "pose_landmarker_full.task"

TARGET_FPS = 12        # frames per second we analyse (phones record 30; 12 is enough for gym reps)
MAX_SECONDS = 60       # only the first minute of a video is analysed
MAX_SIDE = 640         # frames are shrunk so the long side is 640 px (faster, less memory)

# Landmark index for each body part (MediaPipe's fixed order).
LM = {
    "nose": 0, "left_ear": 7, "right_ear": 8,
    "left_shoulder": 11, "right_shoulder": 12, "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16, "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26, "left_ankle": 27, "right_ankle": 28,
    "left_heel": 29, "right_heel": 30, "left_foot_index": 31, "right_foot_index": 32,
}

# Pairs of landmarks joined by a line when we draw the skeleton.
BONES = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28), (27, 29), (29, 31), (27, 31), (28, 30), (30, 32), (28, 32),
]


@dataclass
class PoseSequence:
    """Landmarks for every analysed frame of one video."""
    t: np.ndarray            # (n,) time of each frame in seconds
    image: np.ndarray        # (n, 33, 4) x, y, z, visibility  - NaN when no person was found
    world: np.ndarray        # (n, 33, 3) metres               - NaN when no person was found
    width: int
    height: int
    fps: float               # analysed frames per second
    truncated: bool = False  # True when the video was longer than MAX_SECONDS
    jpegs: list[bytes] = field(default_factory=list)  # small JPEG of each frame, for snapshots

    @property
    def found(self) -> np.ndarray:
        return ~np.isnan(self.image[:, 0, 0])

    @property
    def coverage(self) -> float:
        return float(self.found.mean()) if len(self.t) else 0.0

    @property
    def aspect(self) -> float:
        return self.width / self.height


def _new_landmarker() -> vision.PoseLandmarker:
    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,  # VIDEO mode tracks the person between frames
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


def extract_pose(video_path: str | Path, progress: Callable[[float], None] | None = None,
                 keep_frames: bool = True) -> PoseSequence:
    """Read a video file and run the pose model on about TARGET_FPS frames per second."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("Could not open this video. Try an MP4 recorded with the phone camera.")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not 1 <= src_fps <= 240:
        src_fps = 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, round(src_fps / TARGET_FPS))
    max_frames = int(MAX_SECONDS * src_fps)

    times, image_rows, world_rows, jpegs = [], [], [], []
    width = height = 0
    truncated = False
    landmarker = _new_landmarker()
    try:
        index = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if index >= max_frames:
                truncated = True
                break
            if index % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                h, w = frame.shape[:2]
                scale = MAX_SIDE / max(h, w)
                if scale < 1:
                    frame = cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
                height, width = frame.shape[:2]
                t_ms = int(index * 1000 / src_fps)
                rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), t_ms)
                if result.pose_landmarks:
                    image_rows.append([[p.x, p.y, p.z, p.visibility] for p in result.pose_landmarks[0]])
                    world_rows.append([[p.x, p.y, p.z] for p in result.pose_world_landmarks[0]])
                else:
                    image_rows.append(np.full((33, 4), np.nan))
                    world_rows.append(np.full((33, 3), np.nan))
                times.append(t_ms / 1000)
                if keep_frames:
                    jpegs.append(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes())
                if progress and total:
                    progress(min(1.0, index / min(total, max_frames)))
            index += 1
    finally:
        cap.release()
        landmarker.close()

    if not times:
        raise ValueError("This video has no readable frames.")
    return PoseSequence(
        t=np.array(times), image=np.array(image_rows, dtype=float), world=np.array(world_rows, dtype=float),
        width=width, height=height, fps=src_fps / step, truncated=truncated, jpegs=jpegs,
    )


def draw_skeleton(jpeg: bytes, landmarks: np.ndarray, highlight: list[int] | None = None,
                  caption: str | None = None) -> bytes:
    """Draw the stick figure on one stored frame. `highlight` joints are drawn in red."""
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    h, w = frame.shape[:2]
    if not np.isnan(landmarks[0, 0]):
        pts = (landmarks[:, :2] * [w, h]).astype(int)
        vis = landmarks[:, 3]
        for a, b in BONES:
            if vis[a] > 0.3 and vis[b] > 0.3:
                cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (255, 255, 255), 3, cv2.LINE_AA)
                cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (200, 140, 30), 2, cv2.LINE_AA)
        for i in range(11, 33):
            if vis[i] > 0.3:
                cv2.circle(frame, tuple(pts[i]), 4, (255, 255, 255), -1, cv2.LINE_AA)
        for i in highlight or []:
            cv2.circle(frame, tuple(pts[i]), 11, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, tuple(pts[i]), 9, (60, 60, 230), -1, cv2.LINE_AA)
    if caption:
        cv2.rectangle(frame, (0, h - 34), (w, h), (30, 30, 30), -1)
        cv2.putText(frame, caption, (10, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
