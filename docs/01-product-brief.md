# 1. Product brief

## The problem

A person joins a gym for the first time. They see 30 machines and do not know:

1. what each machine is for,
2. how to set it up and use it safely,
3. whether they are doing the movement correctly.

A personal trainer solves all three, but costs money and is not always there. Many beginners
copy other people, guess, get hurt, or stop coming.

## Who it is for

**Main user: the gym beginner** (first 3 months). Has a phone. Does not know machine names.
Is a little embarrassed to ask. Wants a clear "do this" answer, not a lecture.

Later users: people training alone at home, and gyms that want an "always there" assistant.

## The promise

> Point your phone at any machine. Know how to use it in one minute. Film one set. Know what to fix.

## The user journey (the scenario you described)

| Step | What the user does | What the app does | Built in this prototype? |
|---|---|---|---|
| 1 | Takes a photo of a machine | Names the machine (3 best guesses, user confirms) | Yes |
| 2 | Reads the guide | Shows muscles, a first workout, setup steps, how to do it, common mistakes, safety | Yes, 17 machines |
| 3 | Films one set from the side | Tells them where to put the phone | Yes |
| 4 | Uploads the video | Finds the body, counts reps, checks each rep | Yes, 13 exercises |
| 5 | Reads the result | Score out of 100, what is wrong, a picture of the moment, how to fix it | Yes |
| 6 | Watches the set back | Review video: their clip with the joint angle drawn on, next to a live graph and rep counter | Yes |
| 7 | Tries again | Keeps the last scores on the phone | Yes (last 8) |

## Design decisions and why

| Decision | Why |
|---|---|
| The app shows **3 guesses** and the user taps the right one | No recogniser is 100% right. A wrong machine name leads to a wrong guide, which is a safety problem. One tap removes that risk. |
| Every problem comes with **a number, a picture and a fix** | "Bad form" does not help. "Your elbow reached 104 degrees, target 85, pull lower" does. |
| The app says **how sure it is** (confidence, warnings) | A video filmed from the front or with a hidden arm gives a weaker measurement. Hiding that would break trust. |
| **The uploaded video is deleted** right after analysis | Gym videos are private. The problem snapshots and the review video are kept for one day, on the computer that runs the server, so the user can watch and save them. |
| The review video shows **only what was measured** | It is drawn from the same angles and reps as the written result, so the two can never disagree. It also lets the user see when the tracking is wrong. |
| Machines without a form check still get a **guide** | A beginner is helped by steps 1-2 alone. We do not pretend to score what we cannot measure. |
| Plain short sentences, big buttons | The user is in a gym, standing, with one hand free. |

## What "good" looks like (success measures)

For a real launch these would be tracked:

- **Machine found**: the right machine is in the top 3 guesses. Target 95%.
- **Rep count correct**: counted reps equal real reps, within 1. Target 95% of videos.
- **Advice agrees with a trainer**: a trainer watching the same video names the same main problem. Target 80%.
- **Time to first guide**: under 10 seconds from opening the app.
- **Comes back**: the user checks form again within 7 days.

The prototype's measured numbers are in [06-test-report.md](06-test-report.md).

## Scope of this prototype

In: the full journey above, running on your laptop, usable from a phone browser on the same Wi-Fi.

Out (planned, see [07-roadmap-to-apk.md](07-roadmap-to-apk.md)): the Android APK itself, live feedback
while exercising, user accounts, workout plans, a trainer-checked dataset.

## Risks

| Risk | How bad | What we do about it |
|---|---|---|
| Wrong advice causes an injury | High | Conservative rules, safety text on every guide, "not medical advice" notice, a trainer must review the rules before launch |
| Machine recogniser is wrong | Medium | User confirms from 3 guesses; full list always one tap away |
| Camera angle spoils the measurement | Medium | Filming instructions, view detection, warnings, confidence label |
| Rules were not checked against a trainer | High for launch | This is the main open item. See the test report |
| Videos are private data | Medium | Delete after analysis; the APK plan moves all analysis onto the phone |
