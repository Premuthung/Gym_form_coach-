"""Draw the graphs that show how the models were trained and chosen.

Two steps:

1. measure  - retrain with extra bookkeeping (loss per epoch, score versus amount of data) and
              read one demo video. Slow (several minutes). Saved to models/training_curves.json.
2. draw     - turn the saved numbers into PNG files in docs/graphs/. Fast.

Run:  python training/make_training_graphs.py             (measure if needed, then draw)
      python training/make_training_graphs.py --measure   (force step 1 again)

No large language model (LLM) is trained in this project. The trained models are three small
posture classifiers. See docs/08-training-graphs.md for how to read each graph.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "training"))

MODELS = ROOT / "models"
OUT = ROOT / "docs" / "graphs"
CURVES = MODELS / "training_curves.json"
DEMO_VIDEO = ROOT.parent / "Exercise-Correction-main" / "demo" / "bc_demo.mp4"

TASK_NAME = {"bicep_lean_back": "Bicep curl: leaning back", "plank_posture": "Plank: body line",
             "lunge_knee_over_toe": "Lunge: knee over toe"}
ALGO_NAME = {"logistic_regression": "Logistic regression", "random_forest": "Random forest", "mlp_64_32": "Neural network (MLP)"}

# ---- look: one small design system for every graph ------------------------------------------
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"     # categorical slots 1-3 (validated as a set)
BLUE_LIGHT, BLUE_DARK = "#86b6ef", "#184f95"             # two steps of one hue, for "before -> after"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DPI = 200

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9.5,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False,
})


def titled(fig, title: str, subtitle: str) -> None:
    fig.text(0.012, 0.975, title, fontsize=13, fontweight="bold", va="top", color=INK)
    fig.text(0.012, 0.975 - 0.34 / fig.get_figheight(), subtitle, fontsize=9.5, va="top", color=INK2)


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=DPI)
    plt.close(fig)
    print("wrote", OUT / name)


def hbar(ax, y: float, value: float, colour: str, thick_px: float = 14, radius_px: float = 4) -> None:
    """A horizontal bar from 0 to `value`: square at the baseline, 4 px rounded at the data end."""
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform((0, 0)), inv.transform((1, 1))
    px_x, px_y = abs(x1 - x0), abs(y1 - y0)                 # data units per screen pixel
    h, rx, ry = thick_px * px_y / 2, radius_px * px_x, radius_px * px_y
    rx = min(rx, value)
    v = [(0, y - h), (value - rx, y - h), (value, y - h), (value, y - h + ry), (value, y + h - ry),
         (value, y + h), (value - rx, y + h), (0, y + h), (0, y - h)]
    c = [MplPath.MOVETO, MplPath.LINETO, MplPath.CURVE3, MplPath.CURVE3, MplPath.LINETO,
         MplPath.CURVE3, MplPath.CURVE3, MplPath.LINETO, MplPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MplPath(v, c), facecolor=colour, edgecolor="none", zorder=3))


# ================================== step 1: measure ===========================================
def measure() -> dict:
    import train_form_classifiers as T
    from sklearn.model_selection import GroupKFold, learning_curve

    warnings.filterwarnings("ignore")
    out: dict = {"tasks": {}}
    report = json.loads((MODELS / "form_classifiers_report.json").read_text())

    for name, cfg in T.TASKS.items():
        lms = cfg["landmarks"]
        xy, y, clip = T.load(T.DATA / cfg["train"], lms, step=T.FRAME_STEP)
        X, Y, G = T.build(xy, y, clip, lms, augment=True)
        print(f"{name}: {len(Y)} rows", flush=True)

        # (a) the neural network, epoch by epoch
        mlp_pipe = T.candidates()["mlp_64_32"].fit(X, Y)
        mlp = mlp_pipe[-1]

        # (b) score versus amount of training data, for the algorithm that was chosen
        chosen = report["tasks"][name]["chosen"]
        folds = min(5, len(np.unique(clip)))
        sizes, train_scores, valid_scores = learning_curve(
            # Accuracy, not macro F1: with few clips a validation fold can hold a single class,
            # and macro F1 on one class is meaningless (it reads about 0.5 for a perfect model).
            T.candidates()[chosen], X, Y, groups=G, cv=GroupKFold(n_splits=folds), scoring="accuracy",
            train_sizes=[0.05, 0.1, 0.2, 0.4, 0.7, 1.0], shuffle=True, random_state=0)
        out["tasks"][name] = {
            "mlp_loss": [float(v) for v in mlp.loss_curve_],
            "mlp_validation_accuracy": [float(v) for v in mlp.validation_scores_],
            "chosen": chosen,
            "learning_sizes": [int(s) for s in sizes],
            "learning_train": train_scores.mean(axis=1).round(4).tolist(),
            "learning_valid": valid_scores.mean(axis=1).round(4).tolist(),
            "learning_valid_min": valid_scores.min(axis=1).round(4).tolist(),
            "learning_valid_max": valid_scores.max(axis=1).round(4).tolist(),
        }
        print("  done", flush=True)

    # (c) one real video: the elbow angle and the reps found in it
    if DEMO_VIDEO.exists():
        from app.analysis import ENTER_SHARE, EXIT_SHARE, find_reps
        from app.geometry import compute_metrics, pick_side
        from app.pose import extract_pose

        seq = extract_pose(DEMO_VIDEO, keep_frames=False)
        elbow = compute_metrics(seq, pick_side(seq), use_3d=False)["elbow"]
        reps = find_reps(elbow, seq.t, "extended")
        lo, hi = np.nanpercentile(-elbow, [5, 95])
        out["rep_signal"] = {
            "video": "Exercise-Correction/demo/bc_demo.mp4", "t": seq.t.round(2).tolist(),
            "elbow": elbow.round(1).tolist(),
            "enter": round(float(-(lo + ENTER_SHARE * (hi - lo))), 1), "exit": round(float(-(lo + EXIT_SHARE * (hi - lo))), 1),
            "reps": [[float(seq.t[r.start]), float(seq.t[r.peak]), float(seq.t[r.end])] for r in reps],
        }
    CURVES.write_text(json.dumps(out))
    print("saved", CURVES)
    return out


# ================================== step 2: draw ==============================================
def graph_honest_vs_leaky(report: dict) -> None:
    """Dumbbell: the same model scored two ways."""
    rows = [(t, a, m["cv_random_f1"], m["cv_by_clip_f1"]) for t, task in report["tasks"].items() for a, m in task["models"].items()]
    fig, ax = plt.subplots(figsize=(8, 5.2))
    fig.subplots_adjust(left=0.33, right=0.93, top=0.80, bottom=0.11)
    titled(fig, "A random split makes the models look better than they are",
           "Macro F1 from 5-fold cross-validation. Same data, same model, two ways of splitting.")
    ys, y = [], 0.0
    for i, (task, algo, leaky, honest) in enumerate(rows):
        if i and i % 3 == 0:
            y += 0.7
        ys.append(y)
        ax.plot([honest, leaky], [y, y], color=AXIS, linewidth=2, zorder=2, solid_capstyle="round")
        ax.scatter([leaky], [y], s=75, color=BLUE_LIGHT, edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ax.scatter([honest], [y], s=75, color=BLUE_DARK, edgecolor=SURFACE, linewidth=1.5, zorder=4)
        if leaky - honest >= 0.02:   # label only the gaps worth reading
            ax.text(honest - 0.008, y, f"{honest:.2f}", ha="right", va="center", color=INK2, fontsize=9)
            ax.text(leaky + 0.008, y, f"{leaky:.2f}", ha="left", va="center", color=INK2, fontsize=9)
        chosen = report["tasks"][task]["chosen"] == algo
        ax.text(-0.02, y, ALGO_NAME[algo] + ("  ✓ chosen" if chosen else ""), transform=ax.get_yaxis_transform(),
                ha="right", va="center", color=INK if chosen else INK2, fontweight="bold" if chosen else "normal")
        if i % 3 == 0:
            clips = report["tasks"][task]["clips"]
            ax.text(-0.52, y - 0.62, f"{TASK_NAME[task]}  ·  {clips} clips", transform=ax.get_yaxis_transform(),
                    ha="left", va="center", color=INK, fontweight="bold", fontsize=9.5)
        y += 1
    ax.set_ylim(max(ys) + 0.6, -1.1)
    ax.set_xlim(0.72, 1.012)
    ax.set_yticks([])
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Macro F1 (1.0 = perfect)")
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=BLUE_DARK, markersize=8, label="Split by clip (honest)"),
               plt.Line2D([], [], marker="o", linestyle="", color=BLUE_LIGHT, markersize=8, label="Random split of frames (leaky)")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.885), ncol=2, handletextpad=0.3, columnspacing=1.6)
    save(fig, "01-honest-vs-leaky-validation.png")


def graph_mlp_training(curves: dict) -> None:
    """Two panels (never two y-axes on one panel): loss, then validation accuracy, per epoch."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.9))
    fig.subplots_adjust(left=0.08, right=0.985, top=0.70, bottom=0.14, wspace=0.24)
    titled(fig, "Training the neural network, epoch by epoch",
           "MLP with two hidden layers (64 and 32 neurons). One epoch = one pass over the training frames. The dot marks where training stopped.")
    colours = dict(zip(TASK_NAME, [BLUE, ORANGE, AQUA]))
    for key, ax, label in (("mlp_loss", axes[0], "Training loss (cross-entropy, lower is better)"),
                           ("mlp_validation_accuracy", axes[1], "Accuracy on held-out frames (higher is better)")):
        for task, name in TASK_NAME.items():
            v = curves["tasks"][task][key]
            x = np.arange(1, len(v) + 1)
            ax.plot(x, v, color=colours[task], linewidth=2, solid_capstyle="round", solid_joinstyle="round")
            ax.scatter([x[-1]], [v[-1]], s=42, color=colours[task], edgecolor=SURFACE, linewidth=1.5, zorder=4)
        ax.set_title(label, loc="left", fontsize=9.5, color=INK2, pad=8)
        ax.set_xlabel("Epoch")
        ax.set_xlim(left=0)
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylim(top=1.004)
    handles = [plt.Line2D([], [], color=colours[t], linewidth=2, marker="o", markersize=5,
                          label=f"{TASK_NAME[t].split(':')[0]} ({len(curves['tasks'][t]['mlp_loss'])} epochs)") for t in TASK_NAME]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.84), ncol=3, handletextpad=0.5, columnspacing=1.6)
    save(fig, "02-neural-network-training-curves.png")


def graph_learning_curves(curves: dict) -> None:
    """Small multiples: one panel per classifier, shared y-axis."""
    fig, axes = plt.subplots(1, 3, figsize=(8, 4.1), sharey=True)
    fig.subplots_adjust(left=0.075, right=0.975, top=0.62, bottom=0.14, wspace=0.10)
    titled(fig, "Does more data help? Accuracy as the training set grows",
           "The chosen algorithm for each task. Validation uses whole clips the model never saw. Shaded: worst to best of 5 folds.")
    for ax, (task, name) in zip(axes, TASK_NAME.items()):
        c = curves["tasks"][task]
        x = np.array(c["learning_sizes"])
        ax.fill_between(x, c["learning_valid_min"], c["learning_valid_max"], color=ORANGE, alpha=0.12, linewidth=0)
        ax.plot(x, c["learning_train"], color=BLUE, linewidth=2, marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1)
        ax.plot(x, c["learning_valid"], color=ORANGE, linewidth=2, marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1)
        ax.set_title(f"{name}\n{ALGO_NAME[c['chosen']]}", loc="left", fontsize=9.5, color=INK2, pad=8)
        ax.set_xlabel("Training frames")
        ax.set_xscale("log")
        ax.set_xticks(x[[0, 2, 5]], [f"{v:,}" for v in x[[0, 2, 5]]])
        ax.minorticks_off()
        ax.annotate(f"{c['learning_valid'][-1]:.3f}", (x[-1], c["learning_valid"][-1]), textcoords="offset points",
                    xytext=(-2, -14), ha="right", color=INK2, fontsize=9)
    axes[0].set_ylabel("Accuracy")
    low = min(min(curves["tasks"][t]["learning_valid_min"]) for t in TASK_NAME)
    axes[0].set_ylim(np.floor(low * 10) / 10 - 0.02, 1.02)
    handles = [plt.Line2D([], [], color=BLUE, linewidth=2, marker="o", markersize=5, label="On the frames it trained on"),
               plt.Line2D([], [], color=ORANGE, linewidth=2, marker="o", markersize=5, label="On unseen clips (validation)")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.85), ncol=2, handletextpad=0.5, columnspacing=1.6)
    save(fig, "03-learning-curves.png")


def graph_confusion(report: dict) -> None:
    """Heatmaps, one hue (more = darker), with the count written in every cell."""
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("blue", [SURFACE] + BLUE_RAMP)
    words = {"C": "Correct", "L": "Error (L)", "H": "High back"}
    fig, axes = plt.subplots(1, 3, figsize=(8.6, 3.7), gridspec_kw={"width_ratios": [2, 3, 2]})
    fig.subplots_adjust(left=0.10, right=0.985, top=0.66, bottom=0.16, wspace=0.62)
    titled(fig, "Where the chosen models are right and wrong",
           "The dataset authors' separate test file. Rows: the true label. Columns: what the model said. Number = frames.")
    for ax, (task, name) in zip(axes, TASK_NAME.items()):
        t = report["tasks"][task]
        cm = np.array(t["test_confusion_matrix"])
        labels = [words[c] if not (c == "L" and task == "plank_posture") else "Low back" for c in t["classes"]]
        labels = [l.replace("Error (L)", "Lean back" if task.startswith("bicep") else "Knee over toe") for l in labels]
        share = cm / cm.sum(axis=1, keepdims=True)      # colour = share of that true label
        for (r, c), v in np.ndenumerate(cm):
            ax.add_patch(plt.Rectangle((c - 0.47, r - 0.47), 0.94, 0.94, facecolor=cmap(share[r, c]), edgecolor="none"))
            ax.text(c, r, f"{v}", ha="center", va="center", fontsize=10.5,
                    color="#ffffff" if share[r, c] > 0.5 else INK, fontweight="bold" if r == c else "normal")
        ax.set_xlim(-0.5, len(labels) - 0.5)
        ax.set_ylim(len(labels) - 0.5, -0.5)
        ax.set_aspect("equal")
        ax.set_xticks(range(len(labels)), [l.replace(" ", "\n", 1) if len(labels) == 3 else l for l in labels], color=INK2)
        ax.set_yticks(range(len(labels)), labels, color=INK2)
        ax.grid(visible=False)
        for s in ax.spines.values():
            s.set_visible(False)
        right = int(np.trace(cm))
        ax.set_title(f"{name}\n{right} of {cm.sum()} frames right", loc="left", fontsize=9.5, color=INK2, pad=8)
        ax.set_xlabel("Model said")
    axes[0].set_ylabel("True label")
    save(fig, "04-confusion-matrices.png")


def graph_model_comparison(comparison: dict) -> None:
    rows = comparison["models"]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.subplots_adjust(left=0.30, right=0.95, top=0.70, bottom=0.15)
    titled(fig, "Choosing the machine recogniser: three pretrained models, same photos",
           f"Zero-shot (no training on gym photos), {comparison['photos']} hand-checked photos of {comparison['classes']} machines.")
    ax.set_xlim(0, 100)
    ax.set_ylim(len(rows) - 0.45, -0.55)
    fig.canvas.draw()
    for i, m in enumerate(rows):
        for off, key, colour in ((-0.17, "top1", BLUE), (0.17, "top3", ORANGE)):
            v = m[key] * 100
            hbar(ax, i + off, v, colour, thick_px=15)
            ax.text(v + 1.2, i + off, f"{v:.0f}%", va="center", ha="left", color=INK, fontsize=9.5)
    ax.set_yticks(range(len(rows)), [m["label"] for m in rows], color=INK)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Share of photos (%)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE, label="First guess is right"),
               plt.Rectangle((0, 0), 1, 1, color=ORANGE, label="Right machine is in the 3 guesses shown")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.845), ncol=2, handlelength=1, handleheight=1, columnspacing=1.6)
    save(fig, "05-machine-recogniser-model-comparison.png")


def graph_per_machine(rec: dict) -> None:
    items = sorted(((k, *map(int, v.split("/"))) for k, v in rec["per_class"].items()), key=lambda r: (-r[1] / r[2], -r[2]))
    fig, ax = plt.subplots(figsize=(8, 5.3))
    fig.subplots_adjust(left=0.235, right=0.93, top=0.83, bottom=0.10)
    titled(fig, "Machine recognition, machine by machine (SigLIP base)",
           f"First guess correct, {rec['photos']} photos. Most machines have very few test photos, so read the counts.")
    ax.set_xlim(0, 100)
    ax.set_ylim(len(items) - 0.4, -0.6)
    fig.canvas.draw()
    for i, (name, hit, n) in enumerate(items):
        v = 100 * hit / n
        if v > 0:
            hbar(ax, i, v, BLUE, thick_px=13)
        ax.text(max(v, 0) + 1.2, i, f"{hit} of {n}", va="center", ha="left", color=INK, fontsize=9.5)
    ax.set_yticks(range(len(items)), [k.replace("_", " ").capitalize() for k, _, _ in items], color=INK)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Photos where the first guess was right (%)")
    save(fig, "06-machine-recognition-per-machine.png")


def graph_rep_signal(curves: dict) -> None:
    s = curves.get("rep_signal")
    if not s:
        print("skipped rep-signal graph (demo video not found when measuring)")
        return
    t, elbow = np.array(s["t"]), np.array(s["elbow"])
    fig, ax = plt.subplots(figsize=(8, 3.9))
    fig.subplots_adjust(left=0.075, right=0.865, top=0.74, bottom=0.14)
    titled(fig, "How repetitions are counted: elbow angle in a real bicep-curl video",
           "A rep starts when the angle drops below ENTER and ends when it rises back above EXIT. Shaded: the reps found.")
    for k, (a, _, b) in enumerate(s["reps"], start=1):
        ax.axvspan(a + 0.06, b - 0.06, color=BLUE, alpha=0.10, linewidth=0)
        ax.text((a + b) / 2, 178, f"rep {k}", ha="center", va="top", color=INK2, fontsize=9)
    ax.plot(t, elbow, color=BLUE, linewidth=2, solid_joinstyle="round")
    for key, text in (("exit", "EXIT"), ("enter", "ENTER")):
        ax.axhline(s[key], color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
        ax.text(1.01, s[key], f"{text}  {s[key]:.0f}°", transform=ax.get_yaxis_transform(), va="center", color=INK2, fontsize=9)
    ax.set_ylim(40, 180)
    ax.set_xlim(0, t[-1])
    ax.set_xlabel("Time in the video (seconds)")
    ax.set_ylabel("Elbow angle (degrees; 180 = straight arm)")
    save(fig, "07-rep-counting-on-a-real-video.png")


def main() -> None:
    curves = measure() if "--measure" in sys.argv or not CURVES.exists() else json.loads(CURVES.read_text())
    report = json.loads((MODELS / "form_classifiers_report.json").read_text())
    graph_honest_vs_leaky(report)
    graph_mlp_training(curves)
    graph_learning_curves(curves)
    graph_confusion(report)
    graph_model_comparison(json.loads((MODELS / "image_text_model_comparison.json").read_text()))
    graph_per_machine(json.loads((MODELS / "machine_recognition_report.json").read_text()))
    graph_rep_signal(curves)


if __name__ == "__main__":
    main()
