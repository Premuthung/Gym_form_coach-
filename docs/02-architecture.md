# 2. Architecture: how the parts fit together

## The big picture

```
 Phone or laptop browser                     Your laptop (the server)
 ───────────────────────                     ─────────────────────────────────────────────
 frontend/  (HTML + CSS + JS)                 backend/app/  (Python, FastAPI)

   photo  ───── POST /api/identify ───────▶   machine_id.py   image-text model (zero-shot)
          ◀──── 3 best guesses ────────────

   guide  ◀──── GET /api/catalog ──────────   catalog.json    guides + scoring rules (data)

   video  ───── POST /api/analyze ────────▶   main.py         saves the file, starts a job
          ◀──── job id ────────────────────
                                              pose.py         MediaPipe pose: video -> 33 landmarks per frame
   poll   ───── GET /api/jobs/{id} ───────▶   geometry.py     landmarks -> joint angles over time
          ◀──── progress ... then result ──   analysis.py     angles -> reps -> checks -> score
                                              classifiers.py  3 small trained posture models
                                              render.py       draws the review video (overlay + graph)
                                              features.py     makes model inputs (shared with training)
```

## Tools used

| Layer | Tool | Why this one |
|---|---|---|
| Web server | **FastAPI** + **Uvicorn** | Small, modern Python web framework. Gives clear error messages. |
| Front end | Plain **HTML, CSS, JavaScript** | No build step, nothing to install. One page, six screens. |
| Video reading | **OpenCV** | Reads phone videos (MP4, MOV) frame by frame. |
| Pose model | **MediaPipe Pose Landmarker** | Free, runs on a normal CPU, and has an Android version for the APK. |
| Machine recogniser | **Transformers** + **PyTorch** | Loads open image-text models from Hugging Face. |
| Posture models | **scikit-learn** | Simple, fast models for small tables of numbers. |
| Numbers | **NumPy**, **pandas** | Angle maths and reading the training CSV files. |
| Review video | **Pillow**, **OpenCV**, **matplotlib**, **ffmpeg** (via imageio-ffmpeg) | Draws each frame and encodes an MP4 that plays in any browser. |

All free and open source. No paid API. No GPU. See [03-models-and-techniques.md](03-models-and-techniques.md) for the models.

## Folder map

```
gym-form-coach/
├─ run.bat                    start the server
├─ requirements.txt           Python packages and versions
├─ backend/app/
│  ├─ main.py                 web routes, job queue
│  ├─ catalog.json            17 machines, 17 exercises: guides AND scoring rules
│  ├─ machine_id.py           photo -> machine
│  ├─ pose.py                 video -> landmarks; draws the skeleton on snapshots
│  ├─ geometry.py             landmarks -> angles
│  ├─ analysis.py             the rule engine: reps, checks, score
│  ├─ render.py               the review video: overlay on the clip + a graph that draws itself
│  ├─ features.py             input features for the posture models
│  └─ classifiers.py          loads and runs the posture models
├─ frontend/                  index.html, styles.css, app.js
├─ models/                    pose model file, trained posture models, training report
├─ training/                  scripts that train and evaluate (run by hand, not by the app)
├─ tests/                     automatic tests of the rule engine
├─ data/                      uploads (temporary), job snapshots, evaluation photos
└─ docs/                      this folder
```

## What happens to one video

1. `main.py` saves the upload and puts a job in a queue. Only **one video is analysed at a time**,
   because the pose model already uses every CPU core.
2. `pose.py` reads about **12 frames per second** (a phone records 30; gym movements are slow, so 12
   is enough and 2.5 times faster). Each frame is shrunk to 640 px and passed to the pose model.
3. `geometry.py` turns landmarks into angles (elbow, knee, hip, torso lean, and so on) and smooths
   them over 0.3 seconds to remove jitter.
4. `analysis.py` finds repetitions, measures every check on every rep, and builds the score.
5. `classifiers.py` adds a learned opinion for the three exercises that have training data.
6. For each problem, `pose.py` draws the skeleton on the worst frame and saves it as a JPEG.
7. `render.py` makes the **review video** (1280x720, H.264): the user's frames with the measured
   joint and its angle drawn on, next to the angle graph, the rep counter and the score. It reuses the
   frames and angles from steps 2-4, so nothing is tracked twice. It adds 10-40 seconds.
8. The uploaded video is **deleted**. The browser receives the result as JSON, with links to the
   snapshots and the review video. Those are kept on the server for one day.

## The four API routes

| Route | Input | Output |
|---|---|---|
| `GET /api/catalog` | nothing | machines and guides (scoring rules are not sent to the browser) |
| `POST /api/identify` | `photo` file | `recognized`, 3 `candidates` with confidence |
| `POST /api/analyze` | `exercise_id`, `video` file | `job_id` |
| `GET /api/jobs/{id}` | job id | `status`, `progress`, and when done the `result` |

`GET /api/health` reports whether the models are loaded. FastAPI also builds an interactive page
for trying the routes at `http://localhost:8000/docs`.

## Why the rules live in `catalog.json`, not in code

Each exercise is described by data:

```json
"analysis": {
  "type": "reps", "primary": "elbow", "start": "extended",
  "checks": [
    {"id": "rom_peak", "metric": "elbow", "stat": "at_peak", "good": 85, "bad": 120,
     "title": "Bar not pulled low enough", "fix": "Pull the bar all the way to your upper chest."}
  ]
}
```

`analysis.py` is one engine that reads these rules. Adding a new machine exercise means adding
about 20 lines of data. A trainer can review and correct the numbers without reading Python.

## Limits of this design (prototype choices)

- Jobs are kept in memory. Restarting the server forgets them.
- One video at a time. Fine for one tester, not for many users.
- No login. Anyone on the same Wi-Fi can use it when started with `run.bat lan`.
- History is stored only in the browser.
