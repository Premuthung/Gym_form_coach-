# Documentation

Read in this order. Each page is short.

| Page | Answers |
|---|---|
| [01-product-brief.md](01-product-brief.md) | Who is this for? What does it do? What is in and out of the prototype? |
| [02-architecture.md](02-architecture.md) | Which tools are used? How do the parts connect? What happens to a video? |
| [03-models-and-techniques.md](03-models-and-techniques.md) | **Which models and which machine-learning techniques are used, and how each one works** |
| [04-data-sources.md](04-data-sources.md) | Where do the models and data come from? What are the licences? |
| [05-reference-repos-review.md](05-reference-repos-review.md) | What do the two GitHub projects do? What did we keep and what did we change? |
| [06-test-report.md](06-test-report.md) | What was tested, with the measured numbers, and what is still unproven |
| [07-roadmap-to-apk.md](07-roadmap-to-apk.md) | How to turn this into an Android APK |
| [08-training-graphs.md](08-training-graphs.md) | **Graphs: how the models were trained and chosen**, with how to read each one |

## The one-paragraph version

A photo of a gym machine is matched to a machine name by a pretrained **image-text model**
(zero-shot classification: no training on gym photos). The app then shows a written guide. For the
form check, **MediaPipe Pose** finds 33 body points in every video frame. Those points become
**joint angles**. A **state machine** counts repetitions from the main joint angle. Each repetition
is checked by **rules** (range of motion, posture, speed) that give a score from 0 to 100. For three
exercises a small **trained classifier** (random forest or neural network, trained on open landmark
data) adds a posture check. The result is a score, a list of problems with a picture and a fix.
