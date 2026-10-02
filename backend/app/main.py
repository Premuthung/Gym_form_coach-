"""The web server. It serves the phone-style web app and four small API routes.

    GET  /api/catalog          machines and exercise guides
    POST /api/identify         photo of a machine  -> the 3 most likely machines
    POST /api/analyze          exercise video      -> a job id (analysis runs in the background)
    GET  /api/jobs/{job_id}    progress, then the score and advice

Start it with run.ps1 (see README.md).
"""
from __future__ import annotations

import io
import json
import shutil
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from . import classifiers
from .analysis import analyze
from .machine_id import MachineRecognizer
from .pose import draw_skeleton, extract_pose
from .render import render_review_video

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
UPLOADS = ROOT / "data" / "uploads"
JOBS_DIR = ROOT / "data" / "jobs"
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
VIDEO_TYPES = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv", ".3gp"}
KEEP_JOBS_SECONDS = 24 * 3600

CATALOG = json.loads((Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))
recognizer = MachineRecognizer(CATALOG)
jobs: dict[str, dict] = {}
# One video at a time: the pose model uses every CPU core, so running two together is slower for both.
worker = ThreadPoolExecutor(max_workers=1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    for folder in (UPLOADS, JOBS_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    for old in UPLOADS.iterdir():          # uploads are never kept after analysis
        old.unlink(missing_ok=True)
    for old in JOBS_DIR.iterdir():         # snapshots are kept for one day
        if time.time() - old.stat().st_mtime > KEEP_JOBS_SECONDS:
            shutil.rmtree(old, ignore_errors=True)
    recognizer.load_in_background()        # CLIP takes a while to load; do not block startup
    yield
    worker.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Gym Form Coach", lifespan=lifespan)


def public_exercise(ex_id: str) -> dict:
    ex = CATALOG["exercises"][ex_id]
    out = {k: v for k, v in ex.items() if k != "analysis"}
    out.update(id=ex_id, form_check=ex["analysis"] is not None)
    return out


@app.get("/api/health")
def health() -> dict:
    return {
        "machine_recognizer": recognizer.status,
        "machine_recognizer_error": recognizer.error,
        "posture_models": {n: classifiers.load(n) is not None
                           for n in ("bicep_lean_back", "plank_posture", "lunge_knee_over_toe")},
    }


@app.get("/api/catalog")
def catalog() -> dict:
    machines = [{k: v for k, v in m.items() if k != "labels"} for m in CATALOG["machines"]]
    return {"machines": machines, "exercises": {e: public_exercise(e) for e in CATALOG["exercises"]}}


@app.post("/api/identify")
def identify(photo: UploadFile = File(...)) -> dict:
    data = photo.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "This photo is too large. The limit is 15 MB.")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "This file is not a photo we can read. Use a JPG or PNG.")
    try:
        return recognizer.identify(image)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


def run_job(job_id: str, video: Path, exercise_id: str) -> None:
    job = jobs[job_id]
    try:
        job.update(status="running", stage="Finding your body in each frame")
        seq = extract_pose(video, progress=lambda p: job.update(progress=round(p * 0.7, 2)))
        job.update(stage="Counting reps and checking form", progress=0.72)
        result = analyze(seq, CATALOG["exercises"][exercise_id])
        result["exercise_id"] = exercise_id
        result["exercise_name"] = CATALOG["exercises"][exercise_id]["name"]

        out = JOBS_DIR / job_id
        out.mkdir(parents=True, exist_ok=True)
        for k, issue in enumerate(result.get("issues", [])):
            frame, highlight = issue.pop("frame"), issue.pop("highlight")
            if highlight is not None and seq.jpegs:
                picture = draw_skeleton(seq.jpegs[frame], seq.image[frame], highlight, caption=issue["title"])
                (out / f"issue_{k}.jpg").write_bytes(picture)
                issue["snapshot"] = f"/media/{job_id}/issue_{k}.jpg"

        if result["ok"] and seq.jpegs:
            # The review video is a bonus: if it cannot be made, the written result is still returned.
            job.update(stage="Making your review video", progress=0.75)
            try:
                render_review_video(seq, CATALOG["exercises"][exercise_id], result, out / "review.mp4",
                                    progress=lambda p: job.update(progress=round(0.75 + p * 0.24, 2)))
                result["video"] = f"/media/{job_id}/review.mp4"
                result["video_poster"] = f"/media/{job_id}/review.jpg"
            except Exception:
                traceback.print_exc()
        job.update(status="done", progress=1.0, stage="Done", result=result)
    except ValueError as e:        # a problem with the video that the user can fix
        job.update(status="error", error=str(e))
    except Exception:
        traceback.print_exc()
        job.update(status="error", error="Something went wrong while analysing this video.")
    finally:
        video.unlink(missing_ok=True)  # privacy: the uploaded video is deleted as soon as we finish


@app.post("/api/analyze")
def start_analysis(exercise_id: str = Form(...), video: UploadFile = File(...)) -> dict:
    exercise = CATALOG["exercises"].get(exercise_id)
    if exercise is None:
        raise HTTPException(404, "Unknown exercise.")
    if exercise["analysis"] is None:
        raise HTTPException(400, "Form check is not available for this exercise yet.")
    suffix = Path(video.filename or "").suffix.lower()
    if suffix not in VIDEO_TYPES:
        raise HTTPException(400, "Please upload a video file (MP4, MOV or WEBM).")

    job_id = uuid.uuid4().hex[:12]
    path = UPLOADS / f"{job_id}{suffix}"
    size = 0
    with path.open("wb") as f:
        while chunk := video.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_VIDEO_BYTES:
                f.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, "This video is too large. The limit is 150 MB. Record 10-30 seconds.")
            f.write(chunk)

    jobs[job_id] = {"status": "queued", "progress": 0.0, "stage": "Waiting to start", "created": time.time()}
    worker.submit(run_job, job_id, path, exercise_id)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job. The server may have restarted. Please upload again.")
    return job


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


JOBS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=JOBS_DIR), name="media")
app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
