# 5. Review of the two reference repositories

Both were read fully before building. Neither was edited. No code was copied; this prototype is
written from scratch. One of them supplies training data (see [04-data-sources.md](04-data-sources.md)).

## A. Exercise-Correction (Ngo Hong Quoc Bao) - MIT licence

A university thesis project. Four home exercises: bicep curl, plank, squat, lunge.

**How it works**

1. MediaPipe Pose gives 33 landmarks per frame.
2. For each exercise, a few landmarks (x, y, z, visibility) become one row of a CSV file with a label.
3. scikit-learn models (logistic regression, SVC, KNN, random forest, SGD) and small Keras networks
   are trained on those rows. One model per error:
   - bicep curl: leaning back (C / L)
   - plank: correct / low back / high back (C / L / H)
   - squat: stage up / down (used for counting)
   - lunge: stage, and knee over toe (C / L)
4. Other errors use angle and distance rules: elbow angle for reps and "weak peak contraction",
   upper-arm angle for "loose upper arm", feet-to-shoulder and knee-to-feet width ratios for squats.
5. A Django server analyses an uploaded video; a Vue.js page shows the error frames.

**Good ideas we kept**

- The hybrid design: learned models where there is data, simple geometry everywhere else.
- Counting reps from a joint angle with two thresholds.
- Showing the user the frame where the error happened.
- Its landmark CSV files, which train our three posture models.

**Problems we found (and what we did instead)**

| Problem in the repository | Why it matters | In this prototype |
|---|---|---|
| Train/validation split is random by frame (`train_test_split(..., test_size=0.2)` in all nine training notebooks) | Neighbouring frames are near copies, so the validation score is inflated (data leakage) | Cross-validation keeps whole clips together. We report both numbers. For lunge the gap is large (0.997 vs 0.928). |
| Models use raw picture coordinates | The model learns where the person stood in the frame, not the pose | Features are hip-centred and torso-scaled, plus mirrored copies |
| Scaler and model are saved as separate pickle files | They can go out of sync; the wrong scaler silently gives wrong answers | Scaler and model are one scikit-learn pipeline in one file |
| Pickles locked to scikit-learn 1.1.2 and Keras 2.9, Python 3.8 | They do not load on a current Python | Retrained on current versions; the version is stored in the model file |
| Uses `mp.solutions.pose` | Removed in MediaPipe 1.0 | Uses the current Tasks API (`PoseLandmarker`) |
| Fixed angle thresholds for rep counting (120 / 100 degrees) | Fails for people with a shorter range or another camera angle | Thresholds adapt to the range seen in each video |
| Only 4 body-weight / dumbbell exercises, no machines | Does not cover the gym-beginner scenario | 13 exercises with form checks, 17 machines with guides |
| Code is one long class per exercise, drawing mixed with logic | Hard to add an exercise | One engine, rules as data |

## B. Posture (twixupmysleeve) - no licence file

A hackathon project (Atlas Hacks). Squats only, live from a webcam.

**How it works**

1. MediaPipe Pose landmarks.
2. Five hand-made features per frame: neck angle, knee angle, hip angle, a foot depth value, knee height.
3. A Keras model with **a single Dense(5) layer** (so it is a linear model) trained with mean squared error
   to output five labels: correct, knee ahead, back wrong (two kinds), correct depth.
4. Labels come from `labels.csv`: a person marked time ranges in their own videos.
5. A Dash (Plotly) page shows the webcam with the feedback text.

**Good ideas we kept**

- **Engineered angle features instead of raw coordinates.** This is the main idea behind our rule engine.
- Normalising lengths by a body segment, so distance to the camera does not matter.
- Short coaching sentences ("keep your chest up").

**Problems we found**

| Problem | In this prototype |
|---|---|
| No licence. By default that means "all rights reserved" | We read it for ideas only. Its data and code are **not** used or copied. Its demo videos were used only as local test inputs. |
| Train/test split is "first 80% / last 20%" of frames in file order, and accuracy is reported on a regression loss | We do not use this model |
| One exercise, one camera, about 7,900 labelled frames | - |
| Needs TensorFlow and an old Dash version | Not needed |

## What neither repository does

- Recognise a machine from a photo.
- Teach how to use a machine.
- Cover machine exercises.
- Say how confident the result is, or warn about a bad camera angle.
- Give one overall score.

Those five points are what this prototype adds.
