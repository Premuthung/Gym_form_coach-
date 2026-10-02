# 7. From this prototype to an Android APK

**Status today:** a web app on your laptop, tested in a browser. **There is no APK yet.** This laptop has
Java 17 and Node but no Android SDK, and an APK should not be built before the form rules are checked
(step 1 below). This page is the plan to get there.

## Three ways to make the APK

| | A. Wrap the web app | B. Native app, analysis on the server | C. Native app, analysis on the phone |
|---|---|---|---|
| How | Capacitor puts `frontend/` inside an Android shell | Kotlin or Flutter app calls the same API | Kotlin app runs the models itself |
| Work | Days | Weeks | Weeks to months |
| Needs internet | Yes | Yes | **No** |
| Videos leave the phone | Yes | Yes | **No** |
| Live feedback while exercising | No | No | **Yes** |
| Server cost | Yes | Yes | None |

**Recommendation:** A first, to put something on a real phone and test it with real beginners.
Then C, because privacy and live feedback are what make this product good.

## Path A - first APK (about a week)

1. Host the backend somewhere the phone can reach (your laptop on Wi-Fi for testing; a small cloud
   server later). It needs about 2 GB of memory.
2. Install Android Studio (this brings the Android SDK).
3. In `frontend/`: `npm init -y`, `npm i @capacitor/core @capacitor/cli @capacitor/android`,
   `npx cap init`, `npx cap add android`.
4. Point the app at the server address, then `npx cap sync` and build in Android Studio:
   *Build > Build APK*.
5. The photo and video buttons already use the phone camera through the standard file picker, so
   no camera code is needed.

## Path C - everything on the phone

Every part of the pipeline has a mobile version:

| Part | Prototype (laptop) | On Android |
|---|---|---|
| Pose | MediaPipe Pose Landmarker, Python | **Same model file**, MediaPipe Tasks for Android. Runs live at 20-30 frames per second on a mid-range phone |
| Angles, reps, checks, score | `geometry.py`, `analysis.py` (about 400 lines) | Rewrite in Kotlin. It is plain arithmetic. `catalog.json` is reused as it is |
| Posture models | scikit-learn | Export to ONNX or TFLite, or re-express as small networks; tiny files |
| Machine recogniser | Image-text model, about 400-800 MB | Too large. Replace with a small image classifier (MobileNet / EfficientNet-Lite, about 5-15 MB) trained on gym photos. See below |
| Guides | `catalog.json` | Bundled in the app |

The tests in `tests/` describe the expected behaviour, so the Kotlin rewrite can be checked against
the same cases.

## The order of work

1. **Check the rules with a trainer.** Record 5-10 people on each machine, correct and with each
   mistake. Compare the app's advice with the trainer's. Fix thresholds in `catalog.json`.
   Nothing else matters until the advice is right.
2. **Fix the machine recogniser** with real gym photos (see doc 6 for its current accuracy). Collect
   50-100 photos per machine from several gyms. First try a small classifier on top of frozen image
   embeddings; then train the small mobile model.
3. **APK by path A**; test with 10 beginners in a gym. Watch where they get stuck.
4. **Collect labelled videos** (with consent) to replace hand-set thresholds with learned models,
   split by person, not by frame.
5. **Path C**: on-device pose, live rep counter, spoken cues ("slower", "pull lower").
6. Accounts, workout plans, progress over weeks.

## Things to decide before a public release

- **Medical and legal wording.** Who is responsible if the advice is wrong? Get this reviewed.
- **Consent and storage** for any video kept for training.
- **Licences** of every dataset and model actually shipped. The app must credit them.
- **Accessibility**: voice guidance, larger text, languages other than English.
