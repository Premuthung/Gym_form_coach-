# 6. Test report

Tested on 2 October 2026, on the development laptop (Windows 11, Ryzen 5 3500U, 6 GB memory, no GPU),
server running at `http://localhost:8000`.

## Summary

| Area | Result | How sure |
|---|---|---|
| Machine recognition | 87% first guess, 97% in top 3 (61 photos) | Medium: small test set, internet photos |
| Rejecting non-gym photos | 22 of 24 rejected | Low: small test set |
| Rule engine logic | 18 of 18 automatic tests pass | High for the logic |
| Real videos, 4 free exercises | Runs end to end, finds real faults | Medium: one person, not checked by a trainer |
| Real videos, 9 machine exercises | **Not tested on real video** | None yet |
| Posture classifiers | 0.93-0.996 F1, split by clip | Low for new people (see doc 3) |
| Web server and API | All routes and error cases behave correctly | High |
| Web page | 3 of 6 screens checked by screenshot | Medium |
| Phone over Wi-Fi | **Not tested** | None yet |

## 1. Machine recognition

Script: `training/eval_machine_recognition.py`. Photos: 61 from Wikimedia Commons, each checked by eye,
16 of the 17 machines (no usable chest-press photo was found). Full output:
`models/machine_recognition_report.json`.

| Measure | Result |
|---|---|
| First guess correct | 53 of 61 (86.9%) |
| Correct machine in the 3 guesses shown | 59 of 61 (96.7%) |
| App said "This looks like ..." | 59 of 61; of those, 89.8% had the right first guess |
| Time per photo | about 1.4 seconds |

By machine: bench press 3/3, cable machine 5/7, dumbbells 5/5, exercise bike 3/3, exercise mat 2/2,
lat pulldown 7/8, leg curl 1/1, leg extension 1/1, leg press 8/9, pec deck 2/2, rowing machine 5/6,
seated cable row 1/1, shoulder press 1/2, **Smith machine 0/2**, squat rack 2/2, treadmill 7/7.

Mistakes: cable machine -> lat pulldown (2), Smith machine -> shoulder press / bench press,
and four single mix-ups.

**Non-gym photos:** 24 unrelated Commons photos (statues, documents, flags, portraits). 22 were
answered with "we are not sure". 2 were wrongly accepted as dumbbells.

**Caveats:** several machines have only 1-2 test photos. The photos were labelled by one reviewer from
small previews. Real beginner photos (bad light, people in the way, half a machine) will be harder.

## 2. Rule engine: automatic tests

Run: `.venv\Scripts\python tests\test_analysis.py` -> **18/18 passed**.

A computer-drawn stick figure performs the movement with known angles, and the test checks that the
engine reports exactly the mistakes that were put in:

| Test | Expected | Result |
|---|---|---|
| 5 clean reps | counts 5 | pass |
| Reps that start bent (leg extension style) | counts 4 | pass |
| Standing still with small shakes | 0 reps | pass |
| Noisy signal | still 6 reps, none split in two | pass |
| Video starts in the middle of a rep | partial rep dropped | pass |
| Good lat pulldown | score 95+, no problems | pass |
| Half reps | "Bar not pulled low enough" | pass |
| Arms never straighten | only that problem reported | pass |
| Reps in 0.9 seconds | only "too fast" reported | pass |
| Torso rocks 40 degrees | "swinging" and "leaning back"; range score stays high | pass |
| One half rep among five good ones | reported for rep 4 only | pass |
| Leg press with locked knees / without | reported / not reported | pass |
| No person in the video | clear failure message | pass |
| Every rule in `catalog.json` is well formed | - | pass |

**What this proves:** the counting and scoring logic does what it is designed to do.
**What it does not prove:** that the pose model sees a person on a real machine well, or that the
thresholds match what a trainer would say.

## 3. Real videos

Six demo videos from the two reference repositories (the only real videos available here).

| Video | Exercise | View | Reps | Score | Problems reported |
|---|---|---|---|---|---|
| Posture `correct-squat.mp4` | Squat | side | 4 | 100 | none |
| Posture `knee_squat.mp4` | Squat | angled | 3 | 100 | none - **a miss, see below** |
| Exercise-Correction `squat_demo.mp4` | Squat | front | 6 | 96 | knees falling inwards (rep 3); low-confidence warning shown |
| `bc_demo.mp4` | Bicep curl | side | 5 | 73 | elbow leaving the side (reps 4, 5); arm not straight at bottom (1, 4, 5); short curl (3); leaning back (4, 5) |
| `lunge_demo.mp4` | Lunge | side | 5 | 83 | upper body leaning forward (3, 5); knee past toes (3) |
| `plank_demo.mp4` | Plank | side | 15 s hold | 68 | hips too high (10-14 s); hips sagging (6-8 s); hold short |

What we can say:

- The whole pipeline runs on real phone-style video, and a person was found in 99-100% of frames.
- The problem snapshots show what the text says. Example: the bicep-curl frame for "elbow moving away
  from your side" shows the person swinging back with the elbow forward.
- For the plank, the rule (hip position) and the trained model flag the same seconds.

What we cannot say:

- **Rep counts were not compared with a human count.** They look plausible on the angle chart.
  On the front-view squat video the count changed between 5 and 7 while tuning thresholds, so that
  one is uncertain.
- **`knee_squat.mp4` is labelled as a knee error by its authors and scored 100.** The knee check only
  runs in a front view, and this video is filmed at an angle. This is a real gap.
- The bicep, lunge and plank videos come from the same author as the classifier training data, so they
  are not an independent test of those models.
- No trainer has judged whether the reported problems are the right ones.

## 4. Machine exercises (lat pulldown, rows, presses, leg machines, pushdown)

**Not tested on real video.** No openly licensed videos of these were available. They share the same
engine as the tested exercises, and their logic is covered by the stick-figure tests, but:

- machines can hide body parts from the camera (weight stacks, pads, the leg-press sled),
- a seated or lying body may be tracked less well by the pose model,
- the thresholds are untested.

**This is the first thing to test in a gym.** Record 3 sets per machine and compare.

## 5. Server and API

Tested with real HTTP requests against the running server.

| Case | Expected | Result |
|---|---|---|
| Home page, script, manifest | 200 | pass |
| `GET /api/catalog` | 17 machines, 17 exercises, no internal rules leaked | pass |
| Photo of a lat pulldown / leg press / cable machine | right machine first | pass (0.89 / 0.96 / 0.71) |
| Upload a text file as a photo | 400 with a clear message | pass |
| Unknown exercise id | 404 | pass |
| Exercise without form check | 400 | pass |
| Upload a non-video file | 400 | pass |
| Text file renamed to `.mp4` | job ends with "Could not open this video" | pass |
| Unknown job id | 404 | pass |
| Real squat video | progress rises, then result | pass |
| Real bicep video | result with 4 problems and 4 snapshot pictures | pass |
| Uploaded video deleted afterwards | upload folder empty | pass |

**Speed:** 15-second video (352x640) -> 21 seconds. 22-second video (1920x1080) -> 72 seconds.
Recogniser ready about 1-2 minutes after the server starts.

## 6. Web page

Checked with screenshots from a real browser engine (headless Microsoft Edge):

- Home screen: renders, 17 machine tiles. 
- Guide screen (dumbbells): tabs, steps, mistakes, safety box, button.
- Result screen (bicep job): score ring, problem cards with snapshots, fixes, area scores, rep bars, chart.

A bug was found and fixed this way (the word "false" printed under a heading).

**Not checked by eye:** the photo-result screen, the record screen and the progress screen, because
they need a click or a file picker. Their code passed a syntax check and the API calls they make were
tested separately. **Please click through these once.**

**Not tested at all:** a real phone over Wi-Fi (`run.bat lan`), the phone camera buttons, iPhone videos.

## 7. Known problems and limits

1. Thresholds are not validated by a trainer. (Most important.)
2. Machine exercises are untested on real video.
3. Side view is required for most checks. Front view gives a low-confidence result.
4. One person in the picture. If someone walks behind, tracking can jump to them.
5. Knee-inwards is only checked from the front; back rounding is not detected at all (the pose model
   has no spine landmarks).
6. Lunge classifier trained on 11 clips.
7. Smith machine not recognised in 2 of 2 test photos.
8. Memory is tight on a 6 GB laptop. Close other programs if the server is slow.
9. Only the first 60 seconds of a video are analysed.

## How to repeat these tests

```
.venv\Scripts\python tests\test_analysis.py
.venv\Scripts\python training\eval_machine_recognition.py
.venv\Scripts\python training\train_form_classifiers.py
```
