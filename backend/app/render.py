"""Step 4 of form analysis: a review video the user can watch.

Left:  their own video, with the measured joint drawn on it and the angle next to it.
Right: the same angle as a graph that draws itself, with a rep counter and, at the end, the score.

Nothing new is measured here. The picture only shows what analysis.py already found, so the
video and the written result always agree.

The frames come from the copies kept during pose extraction (about 12 per second, 640 px), so the
video is rendered without reading or tracking the upload a second time.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .analysis import ENTER_SHARE, EXIT_SHARE, METRIC_LABEL
from .pose import LM, PoseSequence

W, H = 1280, 720
END_HOLD_SECONDS = 2.5
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"

# The three landmarks that form the measured angle (the middle one is the joint itself).
JOINTS = {
    "elbow": ("shoulder", "elbow", "wrist"), "elbow_both": ("shoulder", "elbow", "wrist"),
    "knee": ("hip", "knee", "ankle"), "knee_both": ("hip", "knee", "ankle"),
    "body_line": ("shoulder", "hip", "ankle"),
}
BODY = [("shoulder", "elbow"), ("elbow", "wrist"), ("shoulder", "hip"), ("hip", "knee"), ("knee", "ankle")]


def _rgb(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Segoe UI on Windows; otherwise the DejaVu font that ships with matplotlib."""
    for path in (Path(r"C:\Windows\Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    import matplotlib
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name), size)


def _fit_font(text: str, max_width: int, size: int) -> ImageFont.FreeTypeFont:
    """The largest bold font, up to `size`, in which `text` is no wider than `max_width`."""
    while size > 20 and _font(size, True).getlength(text) > max_width:
        size -= 2
    return _font(size, True)


def _crop_box(seq: PoseSequence, side: str, aspect: float) -> tuple[int, int, int, int]:
    """One window (width / height = aspect) that keeps the visible body in the picture for the whole video."""
    ids = [LM["nose"]] + [LM[f"{s}_{p}"] for s in ("left", "right") for p in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")]
    lm = seq.image[seq.found][:, ids]
    seen = lm[:, :, 3] > 0.5
    w, h = seq.width, seq.height
    if not seen.any():
        return 0, 0, w, h
    xs, ys = lm[:, :, 0][seen] * w, lm[:, :, 1][seen] * h
    x_lo, x_hi = np.percentile(xs, [1, 99])
    y_lo, y_hi = np.percentile(ys, [1, 99])
    cx, cy = (x_lo + x_hi) / 2, (y_lo + y_hi) / 2
    bw, bh = (x_hi - x_lo) * 1.3, (y_hi - y_lo) * 1.3
    cw = max(bw, bh * aspect, 80)
    ch = cw / aspect
    if cw > w:
        cw, ch = w, w / aspect
    if ch > h:
        ch, cw = h, h * aspect
    x0 = int(np.clip(cx - cw / 2, 0, w - cw))
    y0 = int(np.clip(cy - ch / 2, 0, h - ch))
    return x0, y0, int(x0 + cw), int(y0 + ch)


def _body_is_wide(seq: PoseSequence) -> bool:
    """True when the person is lying or leaning (plank, leg press, bench): use a landscape video panel."""
    ids = [LM[f"{s}_{p}"] for s in ("left", "right") for p in ("shoulder", "hip", "knee", "ankle")]
    lm = seq.image[seq.found][:, ids]
    if not len(lm):
        return seq.width > seq.height
    width = (np.nanmax(lm[:, :, 0], axis=1) - np.nanmin(lm[:, :, 0], axis=1)) * seq.width
    height = (np.nanmax(lm[:, :, 1], axis=1) - np.nanmin(lm[:, :, 1], axis=1)) * seq.height
    return float(np.median(width / np.maximum(height, 1))) > 1.1


def _draw_overlay(frame: np.ndarray, lm: np.ndarray, side: str, joints: tuple[str, str, str],
                  value: float, out_w: int) -> Image.Image:
    """The body as quiet lines, the measured limb in orange, and the angle on a dark chip."""
    Z = 2                                    # draw at double size and shrink: smooth lines
    h, w = frame.shape[:2]
    S = Z * w / out_w                        # one unit is one pixel of the finished panel
    img = Image.fromarray(frame).resize((w * Z, h * Z), Image.BILINEAR)
    d = ImageDraw.Draw(img, "RGBA")
    pts = lm[:, :2] * [w * Z, h * Z]
    vis = lm[:, 3]

    def line(a: int, b: int, colour, width: float) -> None:
        width = max(1, round(width))
        d.line([tuple(pts[a]), tuple(pts[b])], fill=colour, width=width)
        for p in (a, b):
            r = width / 2
            d.ellipse([pts[p][0] - r, pts[p][1] - r, pts[p][0] + r, pts[p][1] + r], fill=colour)

    a, j, c = (LM[f"{side}_{p}"] for p in joints)
    measured = {(a, j), (j, c)}
    for x, y in ((LM[f"{side}_{p}"], LM[f"{side}_{q}"]) for p, q in BODY):
        if (x, y) not in measured and vis[x] > 0.5 and vis[y] > 0.5:
            line(x, y, (255, 255, 255, 255), 7 * S)
            line(x, y, (*_rgb(BLUE), 255), 4 * S)
    for x, y in measured:
        line(x, y, (255, 255, 255, 255), 9 * S)
        line(x, y, (*_rgb(ORANGE), 255), 5.5 * S)

    e = pts[j]
    a1 = math.degrees(math.atan2(*(pts[a] - e)[::-1])) % 360
    a2 = math.degrees(math.atan2(*(pts[c] - e)[::-1])) % 360
    start, end = sorted((a1, a2))
    if end - start > 180:
        start, end = end, start + 360
    r = 34 * S
    d.pieslice([e[0] - r, e[1] - r, e[0] + r, e[1] + r], start, end, fill=(255, 255, 255, 70))
    d.arc([e[0] - r, e[1] - r, e[0] + r, e[1] + r], start, end, fill=(255, 255, 255, 255), width=max(1, round(3 * S)))
    for p in (a, j, c):
        for radius, colour in ((8 * S, (255, 255, 255, 255)), (5.5 * S, (*_rgb(ORANGE), 255))):
            d.ellipse([pts[p][0] - radius, pts[p][1] - radius, pts[p][0] + radius, pts[p][1] + radius], fill=colour)

    if not math.isnan(value):
        text = f"{value:.0f}°"
        f = _font(max(8, round(22 * S)), bold=True)
        tw, th = d.textbbox((0, 0), text, font=f)[2:]
        mid = math.radians((start + end) / 2)
        cx, cy = e[0] + math.cos(mid) * 74 * S, e[1] + math.sin(mid) * 74 * S
        pad = 7 * S
        cx = float(np.clip(cx, tw / 2 + pad, w * Z - tw / 2 - pad))      # keep the chip inside the picture
        cy = float(np.clip(cy, th / 2 + pad, h * Z - th / 2 - 2 * pad))
        d.rounded_rectangle([cx - tw / 2 - pad, cy - th / 2 - pad, cx + tw / 2 + pad, cy + th / 2 + pad * 1.6],
                            radius=7 * S, fill=(11, 11, 11, 215))
        d.text((cx - tw / 2, cy - th / 2 - 2 * S), text, font=f, fill=(255, 255, 255, 255))
    return img


def _chart_base(size: tuple[int, int], duration: float, label: str, thresholds: tuple[float, float] | None,
                y_range: tuple[float, float]):
    """The empty graph as a picture, and a function that turns (time, value) into pixel positions."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(size[0] / 100, size[1] / 100), dpi=100, facecolor=SURFACE)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes([0.105, 0.15, 0.71 if thresholds else 0.86, 0.80], facecolor=SURFACE)
    ax.set_xlim(0, max(duration, 0.1))
    ax.set_ylim(*y_range)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0, labelsize=10.5)
    ax.set_xlabel("Time in the video (seconds)", color=INK2, fontsize=11)
    ax.set_ylabel(f"{label} (degrees)", color=INK2, fontsize=11)
    if thresholds:
        for value, text in zip(thresholds, ("rep starts", "rep ends")):
            ax.axhline(value, color=MUTED, linewidth=1.1, linestyle=(0, (4, 3)))
            ax.text(1.02, value, f"{text}\n{value:.0f}°", transform=ax.get_yaxis_transform(), va="center", color=INK2, fontsize=9.5)
    canvas.draw()
    image = np.asarray(canvas.buffer_rgba())[:, :, :3].copy()
    height = image.shape[0]

    def to_pixel(t, v) -> np.ndarray:
        p = ax.transData.transform(np.column_stack([np.atleast_1d(t), np.atleast_1d(v)]))
        return np.column_stack([p[:, 0], height - p[:, 1]])

    return image, to_pixel, int(round(to_pixel(0, y_range[1])[0, 1])), int(round(to_pixel(0, y_range[0])[0, 1]))


def render_review_video(seq: PoseSequence, exercise: dict, result: dict, out_path: Path,
                        progress: Callable[[float], None] | None = None) -> None:
    """Write the side-by-side review video for one analysed upload. Raises if it cannot be made."""
    import imageio_ffmpeg

    cfg = exercise["analysis"]
    primary, side = cfg["primary"], result["side"]
    joints = JOINTS.get(primary, ("shoulder", "elbow", "wrist"))
    label = METRIC_LABEL.get(primary, "Angle")
    is_reps = result["type"] == "reps"
    values = np.array([np.nan if v is None else v for v in result["series"]["value"]], dtype=float)
    t = seq.t
    n, fps = len(t), seq.fps
    reps = result["reps"] if is_reps else []

    thresholds = None
    if is_reps:   # the same two lines the rep counter used
        flipped = -values if cfg["start"] == "extended" else values
        lo, hi = np.nanpercentile(flipped, [5, 95])
        sign = -1 if cfg["start"] == "extended" else 1
        thresholds = (sign * (lo + ENTER_SHARE * (hi - lo)), sign * (lo + EXIT_SHARE * (hi - lo)))
    y_range = (max(0.0, math.floor((np.nanmin(values) - 12) / 10) * 10), 190.0)

    # ---- layout: a tall video panel for a standing or seated person, a wide one for a lying person ----
    wide = _body_is_wide(seq)
    panel = (26, 132, 600, 450) if wide else (26, 26, 428, 668)
    right = panel[0] + panel[2] + 34
    chart = (right - 14, 268, W - right - 6, 404)
    px, py, pw, ph = panel
    x0, y0, x1, y1 = _crop_box(seq, side, pw / ph)
    cw, ch = x1 - x0, y1 - y0
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=18, fill=255)

    base, to_pixel, band_top, band_bottom = _chart_base(chart[2:], float(t[-1]), label, thresholds, y_range)
    curve = to_pixel(t, np.nan_to_num(values, nan=y_range[0]))

    background = Image.new("RGB", (W, H), SURFACE)
    d = ImageDraw.Draw(background)
    title_x = 26 if wide else right
    d.text((title_x, 22), "Gym Form Coach", font=_font(40, True), fill=INK)
    d.text((title_x, 76), result.get("exercise_name", exercise["name"]), font=_font(22), fill=INK2)
    column = W - right - 20
    tiles = {"angle": right, "count": right + int(column * 0.36), "score": right + int(column * 0.60)}
    number_font = _fit_font("100/100", W - 16 - tiles["score"], 70)
    number_y = 138
    count_label = "reps counted" if is_reps else "seconds held"
    for key, text in (("angle", f"{label.lower()} now"), ("count", count_label), ("score", "form score")):
        d.text((tiles[key], number_y + number_font.size + 14), text, font=_font(17), fill=INK2)
    d.text((right, H - 34), "Orange = the joint being measured.  Shaded = a counted rep, with its score."
           if is_reps else "Orange = the angle being measured.", font=_font(15), fill=MUTED)
    background = np.asarray(background).copy()
    blue = np.array(_rgb(BLUE), dtype=float)
    small = _font(14, True)

    ffmpeg = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "23", "-preset", "veryfast", "-movflags", "+faststart", str(out_path)],
        stdin=subprocess.PIPE)
    try:
        hold_start = next((r["t_start"] for r in result["reps"]), 0.0) if not is_reps else 0.0
        frame_rgb = None
        for i in range(n):
            now, value = float(t[i]), float(values[i])

            # ---- left: their video with the measured joint ----
            picture = cv2.cvtColor(cv2.imdecode(np.frombuffer(seq.jpegs[i], np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            crop = picture[y0:y1, x0:x1]
            lm = seq.image[i]
            if np.isnan(lm[0, 0]):
                shown = Image.fromarray(crop)
            else:
                local = lm.copy()
                local[:, 0] = (lm[:, 0] * seq.width - x0) / cw
                local[:, 1] = (lm[:, 1] * seq.height - y0) / ch
                shown = _draw_overlay(crop, local, side, joints, value, pw)
            canvas = Image.fromarray(background)
            canvas.paste(shown.resize((pw, ph), Image.BILINEAR), (px, py), mask)

            # ---- right: live numbers ----
            d = ImageDraw.Draw(canvas)
            if is_reps:
                count = str(sum(1 for r in reps if r["t_end"] <= now))
            else:
                held = float(np.sum((t <= now) & (t >= hold_start)) / fps) if result.get("hold_seconds") else 0.0
                count = f"{min(held, result.get('hold_seconds') or held):.0f}"
            d.text((tiles["angle"], number_y), "–" if math.isnan(value) else f"{value:.0f}°", font=number_font, fill=INK)
            d.text((tiles["count"], number_y), count, font=number_font, fill=INK)
            d.text((tiles["score"], number_y), "–", font=number_font, fill=MUTED)
            frame_rgb = np.asarray(canvas).copy()

            # ---- right: the graph so far ----
            graph = base.astype(float)
            labels = []
            for r in reps:   # a rep's block grows while the rep is happening
                if r["t_start"] <= now:
                    a = int(to_pixel(r["t_start"], 0)[0, 0]) + 2
                    b = int(to_pixel(min(now, r["t_end"]), 0)[0, 0]) - 2
                    if b > a:
                        graph[band_top:band_bottom, a:b] = graph[band_top:band_bottom, a:b] * 0.90 + blue * 0.10
                    if r["t_end"] <= now and r["score"] is not None:
                        labels.append(((a + b) // 2, str(r["score"])))
            graph = graph.astype(np.uint8)
            if i > 0:
                cv2.polylines(graph, [curve[: i + 1].astype(np.int32).reshape(-1, 1, 2)], False, _rgb(BLUE), 3, cv2.LINE_AA)
            dot = tuple(int(v) for v in curve[i])
            cv2.circle(graph, dot, 9, _rgb(SURFACE), -1, cv2.LINE_AA)
            cv2.circle(graph, dot, 7, _rgb(ORANGE), -1, cv2.LINE_AA)
            if labels:   # the score of each finished rep, at the top of its block
                g = Image.fromarray(graph)
                gd = ImageDraw.Draw(g)
                for x, text in labels:
                    gd.text((x - small.getlength(text) / 2, band_top + 4), text, font=small, fill=INK2)
                graph = np.asarray(g)
            frame_rgb[chart[1]:chart[1] + graph.shape[0], chart[0]:chart[0] + graph.shape[1]] = graph

            ffmpeg.stdin.write(frame_rgb.tobytes())
            if progress and i % 10 == 0:
                progress(i / n)

        # ---- end card: hold the last frame and reveal the score ----
        final = Image.fromarray(frame_rgb)
        d = ImageDraw.Draw(final)
        d.rectangle([tiles["count"] - 4, number_y, W, number_y + number_font.size + 10], fill=SURFACE)
        end_count = str(result["rep_count"]) if is_reps else f"{result.get('hold_seconds') or 0:.0f}"
        d.text((tiles["count"], number_y), end_count, font=number_font, fill=INK)
        d.text((tiles["score"], number_y), f"{result['score']}/100", font=number_font, fill=INK)
        final.save(out_path.with_suffix(".jpg"), quality=85)   # shown in the player before it starts
        last = np.asarray(final).tobytes()
        for _ in range(int(END_HOLD_SECONDS * fps)):
            ffmpeg.stdin.write(last)
    finally:
        ffmpeg.stdin.close()
        code = ffmpeg.wait()
    if code != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("the video encoder did not produce a file")
