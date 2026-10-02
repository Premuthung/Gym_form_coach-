# 3. Models and machine-learning techniques

The app uses **two pretrained models**, **three small models we trained**, and **one rule engine**.

| # | Job | Model / technique | Type of ML | Trained by us? |
|---|---|---|---|---|
| 1 | Photo -> machine name | SigLIP (image-text model) | Zero-shot classification | No |
| 2 | Video -> body landmarks | MediaPipe Pose (BlazePose) | Pose estimation (deep CNN) | No |
| 3 | Landmarks -> angles | Geometry | Feature engineering (no ML) | - |
| 4 | Angles -> repetitions | Two-threshold state machine | Signal processing (no ML) | - |
| 5 | Repetition -> score | Rule engine | Expert rules (no ML) | - |
| 6 | Posture right or wrong (3 exercises) | Random forest / small neural network | Supervised classification | **Yes** |

Words used on this page:

- **Model**: a function with many adjustable numbers (weights) that turns an input into an output.
- **Training**: adjusting those numbers using examples.
- **Pretrained**: someone else already trained it on a huge dataset; we only run it.
- **Inference**: running a trained model on new input.

---

## 1. Machine recognition: zero-shot classification with SigLIP

**Model:** `google/siglip-base-patch16-224` (about 200 million weights, Apache 2.0 licence).

**What an image-text model is.** It has two halves. One turns a picture into a list of 768 numbers
(an *embedding*). The other turns a sentence into a list of 768 numbers. It was trained on a very large
number of picture + caption pairs so that a picture and its true caption get similar numbers.
The image half is a *Vision Transformer*: it cuts the picture into 16x16-pixel patches and lets
every patch "look at" every other patch.

**What zero-shot means.** We never show the model a labelled gym photo. Instead:

1. For each of the 17 machines we write short descriptions, for example
   `"a photo of a leg press machine."`, `"a person using a leg press machine."`
   (5 sentence templates x 2-3 names per machine).
2. The text half turns every sentence into an embedding. We average them per machine. This is done
   once and saved in `models/text_embeddings.npz`.
3. The image half turns the user's photo into an embedding.
4. We measure the angle between the photo's embedding and each machine's embedding
   (*cosine similarity*). The closest machines are the answer.
5. An 18th class, "not gym equipment" (a person, a room, food, a document ...), lets the app say
   "we are not sure" instead of forcing a wrong answer. It also says so when the best match is under 30%.

**Why zero-shot.** There was no labelled gym-photo dataset to train on, and adding a machine is one
entry in `catalog.json`.

**Why SigLIP and not CLIP.** We measured three models on the same 61 hand-checked photos:

| Model | First guess right | Right machine in top 3 |
|---|---|---|
| CLIP ViT-B/32 (OpenAI) | 51% | 67% |
| CLIP ViT-B/16 (OpenAI) | 44% | 70% |
| **SigLIP base** (Google) | **87%** | **97%** |

CLIP was good at treadmills, bikes and dumbbells but mixed up strength machines (leg press 1 of 9,
cable machine 0 of 7). SigLIP is trained with a different loss (a yes/no *sigmoid* decision for every
picture-caption pair instead of a contest inside each batch) on more data, and is much better at this
fine-grained task. Changing the wording of the prompts changed CLIP's result by only a few points.

**Limits.** 61 photos is a small test. A Smith machine was missed twice. Photos from the internet
are cleaner than a beginner's photo in a crowded gym. The model is large (about 800 MB) and cannot
go into a phone app as it is.

**Next technique: few-shot learning.** A side experiment showed that adding the average embedding
of a handful of labelled photos per machine to the text embeddings raised CLIP B/16 from 44% to 56%.
With 50-100 real photos per machine, a small classifier on top of frozen embeddings (a *linear probe*)
or a fine-tuned small mobile network is the path to the APK.

Code: `backend/app/machine_id.py`. Measurement: `training/eval_machine_recognition.py`.

---

## 2. Pose estimation: MediaPipe Pose Landmarker (BlazePose)

**Model:** `pose_landmarker_full.task` (9 MB, Apache 2.0), from Google.

It is two convolutional neural networks (CNNs) run one after the other:

1. a **detector** finds the person in the frame,
2. a **landmark network** looks at that crop and outputs **33 body landmarks**
   (nose, shoulders, elbows, wrists, hips, knees, ankles, heels, toes ...).

Each landmark has `x, y` in the picture (0 to 1), a `visibility` score, and a second set of
`x, y, z` in metres relative to the hips ("world landmarks"). In video mode the model also uses
the previous frame, which makes the track steadier.

We use it as it is. On this laptop (Ryzen 5 3500U, no GPU) it processes about 11 frames per second,
so we analyse 12 frames per second of video.

**Why this model.** Free, fast on a CPU, includes feet landmarks, and the same model file runs on
Android. The training data for our posture models was also made with MediaPipe.

Code: `backend/app/pose.py`.

---

## 3. Feature engineering: from landmarks to angles

Raw landmark positions depend on where the person stands and how far the camera is. A coach does
not talk about positions; a coach talks about **angles**. So every measurement is an angle or a ratio:

| Measurement | Definition |
|---|---|
| Elbow angle | angle at the elbow between shoulder and wrist (180 = straight arm) |
| Knee angle | angle at the knee between hip and ankle |
| Torso lean | angle between the hip-to-shoulder line and straight up |
| Upper-arm swing | angle between the upper arm and straight down |
| Hip offset (plank) | how far the hip is above or below the shoulder-ankle line, as a share of body length |
| Knee/ankle width (squat, front view) | distance between knees divided by distance between ankles |

Details that matter:

- **Aspect ratio.** x is a share of the width and y a share of the height. We multiply x by
  width/height first, otherwise every angle in a portrait video is wrong.
- **Which side.** We use the side of the body with the higher visibility score.
- **2D or 3D.** Filmed from the side, angles in the picture are accurate. Filmed from the front,
  a bending elbow or knee points at the camera and the picture angle is meaningless, so we switch to the
  3D world landmarks and show a warning. We measured that a straight limb reads about 179 degrees
  in 2D but about 165 degrees in 3D, so "straight" targets are relaxed by 10 degrees in 3D mode.
- **View detection.** Shoulder width divided by torso length is near 0 from the side and about 0.7
  from the front.
- **Smoothing.** A moving average over 0.3 seconds removes frame-to-frame jitter.

Code: `backend/app/geometry.py`.

---

## 4. Counting repetitions: a state machine with two thresholds

The main joint angle over time looks like a wave. One wave is one rep.

```
 angle
 170 |‾‾\      /‾‾\      /‾‾        rest
     |    \    /    \    /
 ENTER ----\--/------\--/-----      must cross this to START a rep (45% of the range)
     |      \/        \/
 EXIT ------------------------      must come back past this to FINISH it (20% of the range)
  70 |     rep 1     rep 2
```

- The two lines are placed inside the range **this person covered in this video** (5th to 95th
  percentile). So it works for long and short arms and for different machines.
- Two lines instead of one is called **hysteresis**. With one line, a small shake near the line would
  be counted as many reps.
- The main joint must move at least 25 degrees, or nothing is counted.
- A video that starts in the middle of a rep drops that partial rep.
- ENTER is below one half on purpose: a **half rep is still counted**, and then marked down by the
  range-of-motion check. Otherwise half reps would silently disappear.

For the plank there are no reps. The hold is cut into 2-second windows and each window is scored.

Code: `find_reps` in `backend/app/analysis.py`.

---

## 5. Scoring: a rule engine

Each exercise has 3-5 **checks** in `catalog.json`. A check names a measurement, how to summarise it
over one rep, a `good` value and a `bad` value:

```json
{"id": "rom_peak", "group": "range", "metric": "elbow", "stat": "at_peak",
 "good": 85, "bad": 120, "weight": 2, "title": "Bar not pulled low enough", "fix": "..."}
```

Score of one check on one rep: **100 at `good` or better, 0 at `bad` or worse, a straight line between.**
Elbow reached 85 degrees -> 100. Reached 120 -> 0. Reached 102 -> 50.

- **Rep score** = weighted average of its checks.
- **Overall score** = average of the rep scores.
- **Area scores**: range of motion, posture and stability, control and tempo.
- A check becomes a **listed problem** when its average is under 75, or a third of the reps fail it,
  or one rep fails it badly. The frame where it was worst becomes the snapshot.

The three kinds of check:

| Group | Examples |
|---|---|
| Range of motion | elbow angle at the bottom of a pulldown; knee angle at the bottom of a squat |
| Posture and stability | how much the torso swings in a rep; elbows drifting; knees locking; hips sagging |
| Control and tempo | seconds per rep |

**Why rules and not a trained model.** To train a model that judges a lat pulldown, we would need
many videos of correct and incorrect lat pulldowns labelled by a trainer. No such open dataset exists.
Rules need no data, every number can be explained to the user, and a trainer can correct them.

**The honest limit.** The `good` and `bad` values come from general coaching guidance. They are
reasonable starting points, **not validated**. See [06-test-report.md](06-test-report.md).

---

## 6. Trained posture classifiers (supervised learning)

Three exercises have open, labelled landmark data, so for these we trained models:

| Model | Question it answers | Classes | Algorithm chosen |
|---|---|---|---|
| `bicep_lean_back` | Is the person leaning back? | correct / lean back | Random forest |
| `plank_posture` | Is the body line right? | correct / low back / high back | Random forest |
| `lunge_knee_over_toe` | Is the front knee past the toes? | correct / knee over toe | Neural network (MLP 64-32) |

**Supervised classification** means: give the model many examples with the right answer, and it
learns a rule that maps input to answer.

### Input features

`features.py` turns landmarks into a body-shape description:

1. multiply x by the aspect ratio (same scale for x and y),
2. subtract the hip centre (position in the picture no longer matters),
3. divide by torso length (distance to the camera no longer matters).

The **same function** is used in training and in the app. If the two prepared the numbers
differently, the model would get inputs it never saw.

**Data augmentation:** every training pose is also added as its mirror image, so a model trained on
people facing left also works on people facing right.

### The three algorithms compared

| Algorithm | Idea in one line |
|---|---|
| Logistic regression | One straight boundary between the classes. Simple baseline. |
| Random forest | 100 decision trees, each trained on a random part of the data; they vote. |
| MLP (multi-layer perceptron) | A small neural network: 2 hidden layers of 64 and 32 neurons, ReLU, early stopping. |

Inputs are standardised (mean 0, spread 1) for logistic regression and the MLP. The scaler and the
model are saved together as one pipeline.

### Honest evaluation: split by clip, not by frame

The data is video frames in order. Neighbouring frames are near copies. A random split puts
near copies of the test frames into the training set, so the score looks better than it is
(**data leakage**). We keep whole clips on one side of the split (**GroupKFold cross-validation**)
and choose the algorithm by that number.

Macro F1 score (1.0 is perfect):

| Model | Algorithm | Split by clip (honest) | Random split (leaky) | Authors' test file |
|---|---|---|---|---|
| bicep_lean_back (66 clips) | logistic regression | 0.968 | 0.971 | 0.995 |
| | **random forest** | **0.991** | 0.992 | 0.998 |
| | MLP | 0.984 | 0.992 | 1.000 |
| plank_posture (221 clips) | logistic regression | 0.979 | 0.997 | 0.992 |
| | **random forest** | **0.996** | 0.997 | 0.990 |
| | MLP | 0.976 | 0.996 | 0.989 |
| lunge_knee_over_toe (11 clips) | logistic regression | 0.762 | 0.982 | 0.998 |
| | random forest | 0.856 | 0.997 | 0.999 |
| | **MLP** | **0.928** | 0.997 | 0.998 |

What this table says:

- For lunge, the leaky number claims 0.98-1.00 while the honest number is 0.76-0.93. With only
  **11 clips**, this model has seen very few situations. Treat its output as a hint.
- The authors' test file scores near 1.0 for everything. That most likely means it was recorded in the
  same sessions as the training data. It does not prove the models work on new people.
- Even "split by clip" is optimistic: the clips come from a few people. The real test is new people
  in new gyms, and we have no such data yet.

### How the app uses them

The model gives each frame a probability of "wrong posture". We smooth it over 0.5 seconds, count a
frame as wrong at 70% or more, and the share of wrong frames in a rep becomes one more check in the rule
engine (for lunge, only the deep part of the rep is judged). The classifiers are **one opinion among
several**, not the whole score. If a model file is missing, the exercise is still scored by its rules.

Code: `training/train_form_classifiers.py`, `backend/app/classifiers.py`.
Full numbers: `models/form_classifiers_report.json`.

---

## Techniques not used yet (and when they would be)

| Technique | Would be used for | Needs |
|---|---|---|
| Sequence models (1D CNN, GRU) over landmark windows | Judging the movement over time instead of single frames | Labelled clips |
| Fine-tuning a small image classifier | A machine recogniser that fits in the APK | 50-100 photos per machine |
| Quantisation, TFLite / ONNX export | Small, fast models on the phone | The models above |
| Learned thresholds per check | Replacing hand-set `good` / `bad` values | Trainer-labelled reps |
