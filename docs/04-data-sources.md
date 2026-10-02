# 4. Data and model sources (all open)

Nothing in this prototype was paid for, and no private data was collected.

## Pretrained models (used as they are, not trained by us)

| Model | From | Licence | Used for | File |
|---|---|---|---|---|
| Pose Landmarker "full" (BlazePose GHUM) | Google MediaPipe | Apache 2.0 | Body landmarks in video | `models/pose_landmarker_full.task` (9 MB) |
| Image-text model (see doc 3 for which one) | Hugging Face Hub | See doc 3 | Recognising the machine in a photo | Hugging Face cache in your user folder |

## Training data (used to train our three posture models)

**Source:** the `core/` folder of *Exercise-Correction* by Ngo Hong Quoc Bao, MIT licence.
<https://github.com/NgoQuocBao1010/Exercise-Correction>

The files hold **MediaPipe landmarks, not videos**: one row per video frame, a label, then
x, y, z and visibility for a set of landmarks. The author recorded themself, friends and family;
30 correct-plank pictures come from a public Kaggle yoga dataset.

| File | Rows | Labels | Trains |
|---|---|---|---|
| `bicep_model/train.csv` | 15,372 | C correct 8,238 / L lean back 7,134 | `bicep_lean_back` |
| `plank_model/train.csv` | 28,520 | C 9,904 / L low back 9,546 / H high back 9,070 | `plank_posture` |
| `lunge_model/err.train.csv` | 17,907 | C 8,793 / L knee over toe 9,114 | `lunge_knee_over_toe` |
| matching `test.csv` files | 604 / 710 / 1,107 | same | held-out check |

We read these files **in place** from `../Exercise-Correction-main`. They are not copied into this
project. If you publish this project, either keep that arrangement or copy the CSV files together
with the MIT licence text and the author's name.

### What we learned about this data (important for trusting the models)

- **Rows are video frames in order.** Row 100 and row 101 are almost the same picture.
- **There is no video id.** We rebuild "clips" from unbroken runs of the same label:
  66 clips for bicep, 221 for plank, and **only 11 for lunge**.
- **The videos are landscape 16:9.** We checked this from body proportions in the data, because
  x and y in the files are fractions of width and height and must be put on one scale.
- **Few people.** The models have seen a handful of bodies, in one or two rooms. They have not seen
  different body shapes, clothing, gyms or phones.
- **The test files look like the training files.** Scores on them are near 100%, which most likely means
  they come from the same recording sessions. We do not treat those scores as proof.

## Evaluation photos (used only to measure the machine recogniser)

**Source:** Wikimedia Commons, downloaded by `training/fetch_eval_images.py`.

- 157 photos downloaded, **61 kept** after checking each one by eye (`data/eval_machines/curated.csv`).
  The rest were wrong hits (statues, a flag, a sewing machine, a network cable), drawings, outdoor
  park equipment, or duplicates.
- Licences are mixed: CC BY-SA, CC BY, CC0, public domain. Author, licence and source page of every
  file are in `data/eval_machines/ATTRIBUTION.csv`.
- These photos are **not** used for training and are **not** shipped with the app. The folder is
  listed in `.gitignore`.
- Commons limits how fast you may download ("429 Too Many Requests"). The script waits 4 seconds
  between requests.

## Test videos

Used only on this laptop to check the pipeline. Not copied into the project.

| Video | From | What it shows |
|---|---|---|
| `demo/squat_demo.mp4`, `bc_demo.mp4`, `lunge_demo.mp4`, `plank_demo.mp4` | Exercise-Correction (MIT) | One person, each exercise with good and bad parts |
| `data/demo_files/correct-squat.mp4`, `knee_squat.mp4` | Posture (**no licence**) | Squats from the side and at an angle |

## Not used, and why

- **Posture's data and model** - the repository has no licence, so it may not be reused.
- **Exercise-Correction's trained `.pkl` models** - saved with scikit-learn 1.1.2; they do not load
  safely on current versions, and their validation was leaky. We retrained from the CSV files.

## Data we still need (the biggest gap)

There is **no open dataset of machine exercises with labelled form mistakes**. That is why
machine exercises are scored by rules, not by a trained model. To train one we would need, per
exercise, roughly 30 or more people filmed from the side doing correct and incorrect reps, labelled
by a trainer. See [07-roadmap-to-apk.md](07-roadmap-to-apk.md).

Open datasets worth checking next (not downloaded here; each needs its licence read first):
Fit3D (3D poses of gym exercises), the "Workout/Exercise Video" and "Gym Equipment" sets on Kaggle
and Roboflow Universe for machine photos, and Penn Action / UCF101 for general exercise clips.
