"""Draw the short "how to film your set" video shown before a user uploads.

It is an animation, not a real recording, so no person's footage is needed. Five scenes:
where to put the phone, what a good video looks like, then three recordings that do not work
(too close, from the front, phone moving).

Run:  python training/make_filming_demo.py
Writes frontend/demo/how-to-film.mp4 and frontend/demo/how-to-film.jpg (the poster picture).
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.render import _font, _rgb  # noqa: E402

OUT = ROOT / "frontend" / "demo"
W, H, FPS = 720, 900, 24
S = 2                                   # draw at twice the size, then shrink: smooth edges
BG, CARD, INK, MUTED, LINE = "#f4f6fa", "#ffffff", "#0f172a", "#5b6577", "#e2e7ef"
BRAND, GOOD, BAD, ORANGE = "#2563eb", "#15803d", "#b91c1c", "#eb6834"
WALL, FLOOR = "#e6ecf5", "#cfd8e6"
PHONE = (150, 170, 570, 750)            # the phone screen, in 720 x 900 units
REP_SECONDS = 2.4


def px(*values: float) -> list[int]:
    return [round(v * S) for v in values]


def text(d: ImageDraw.ImageDraw, xy: tuple[float, float], s: str, size: int, colour: str = INK,
         bold: bool = False, anchor: str = "la") -> None:
    d.text(px(*xy), s, font=_font(size * S, bold), fill=colour, anchor=anchor)


def limb(d: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float], width: float, colour: str) -> None:
    d.line(px(*a, *b), fill=colour, width=round(width * S))
    for x, y in (a, b):                 # round ends
        r = width / 2
        d.ellipse(px(x - r, y - r, x + r, y + r), fill=colour)


def dot(d: ImageDraw.ImageDraw, p: tuple[float, float], r: float, colour: str, outline: str | None = None) -> None:
    d.ellipse(px(p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=colour, outline=outline, width=round(2 * S))


def squat_depth(t: float) -> float:
    """0 = standing, 1 = bottom of the squat."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * t / REP_SECONDS)


def side_points(ankle: tuple[float, float], height: float, depth: float) -> dict[str, tuple[float, float]]:
    """Joint positions of a person seen from the side, facing right, doing a squat."""
    def step(p, length, degrees_from_up):
        a = math.radians(degrees_from_up)
        return p[0] + length * height * math.sin(a), p[1] - length * height * math.cos(a)
    knee = step(ankle, 0.25, 6 + 26 * depth)
    hip = step(knee, 0.25, -(4 + 84 * depth))
    shoulder = step(hip, 0.30, 5 + 36 * depth)
    hand = step(shoulder, 0.30, 180 - 82 * depth)
    return {"ankle": ankle, "toe": (ankle[0] + 0.10 * height, ankle[1]), "knee": knee, "hip": hip,
            "shoulder": shoulder, "hand": hand, "head": step(shoulder, 0.115, 12 + 10 * depth)}


def draw_side(d: ImageDraw.ImageDraw, ankle: tuple[float, float], height: float, depth: float, joints: bool) -> None:
    p, w = side_points(ankle, height, depth), height * 0.045
    for a, b in (("ankle", "toe"), ("ankle", "knee"), ("knee", "hip"), ("hip", "shoulder"), ("shoulder", "hand")):
        limb(d, p[a], p[b], w, INK)
    dot(d, p["head"], height * 0.07, INK)
    if joints:                          # the three points the app measures on a squat
        limb(d, p["hip"], p["knee"], w * 0.35, ORANGE)
        limb(d, p["knee"], p["ankle"], w * 0.35, ORANGE)
        for name in ("hip", "knee", "ankle"):
            dot(d, p[name], w * 0.55, ORANGE, CARD)


def draw_front(d: ImageDraw.ImageDraw, centre_x: float, floor_y: float, height: float, depth: float) -> None:
    """The same squat seen from the front: the knee bend is hidden, the body only gets shorter."""
    side = side_points((0, floor_y), height, depth)
    hip_y, shoulder_y, w = side["hip"][1], side["shoulder"][1], height * 0.045
    knee_y = side["knee"][1]
    for sign in (-1, 1):
        foot = (centre_x + sign * 0.10 * height, floor_y)
        knee = (centre_x + sign * (0.10 + 0.05 * depth) * height, knee_y)
        hip = (centre_x + sign * 0.06 * height, hip_y)
        shoulder = (centre_x + sign * 0.11 * height, shoulder_y)
        hand = (centre_x + sign * 0.13 * height, shoulder_y + (0.30 - 0.12 * depth) * height)
        for a, b in ((foot, knee), (knee, hip), (shoulder, hand)):
            limb(d, a, b, w, INK)
    limb(d, (centre_x - 0.11 * height, shoulder_y), (centre_x + 0.11 * height, shoulder_y), w, INK)
    limb(d, (centre_x - 0.06 * height, hip_y), (centre_x + 0.06 * height, hip_y), w, INK)
    limb(d, (centre_x, shoulder_y), (centre_x, hip_y), w * 1.6, INK)
    dot(d, (centre_x, shoulder_y - 0.115 * height), height * 0.07, INK)


def phone_view(kind: str, t: float) -> Image.Image:
    """What the phone camera sees in one scene."""
    x0, y0, x1, y1 = PHONE
    w, h = x1 - x0, y1 - y0
    view = Image.new("RGB", (w * S, h * S), WALL)
    d = ImageDraw.Draw(view)
    depth = squat_depth(t)
    floor_y = h * 0.86 if kind != "close" else h * 1.12
    if floor_y < h:
        d.rectangle(px(0, floor_y, w, h), fill=FLOOR)
    if kind == "close":
        draw_side(d, (w * 0.34, floor_y), h * 1.25, depth, joints=False)
    elif kind == "front":
        draw_front(d, w * 0.5, floor_y, h * 0.62, depth)
    else:
        draw_side(d, (w * 0.40, floor_y), h * 0.62, depth, joints=kind == "good")
    if kind == "moving":
        angle = 7 * math.sin(2 * math.pi * t / 1.3) + 3 * math.sin(2 * math.pi * t / 0.37)
        shift = (round(14 * S * math.sin(2 * math.pi * t / 0.9)), round(8 * S * math.sin(2 * math.pi * t / 0.5)))
        view = view.rotate(angle, resample=Image.BICUBIC, translate=shift, fillcolor=_rgb(WALL))
    return view


def tick_or_cross(d: ImageDraw.ImageDraw, centre: tuple[float, float], good: bool) -> None:
    x, y = centre
    dot(d, centre, 22, GOOD if good else BAD)
    if good:
        d.line(px(x - 10, y + 1, x - 3, y + 8, x + 11, y - 8), fill=CARD, width=4 * S, joint="curve")
    else:
        d.line(px(x - 8, y - 8, x + 8, y + 8), fill=CARD, width=4 * S)
        d.line(px(x + 8, y - 8, x - 8, y + 8), fill=CARD, width=4 * S)


def heading(d: ImageDraw.ImageDraw, title: str, sub: str) -> None:
    text(d, (W / 2, 62), title, 38, bold=True, anchor="mm")
    text(d, (W / 2, 114), sub, 23, MUTED, anchor="mm")


def verdict(d: ImageDraw.ImageDraw, good: bool, message: str) -> None:
    d.rounded_rectangle(px(60, 782, W - 60, 862), radius=20 * S, fill=CARD, outline=GOOD if good else BAD, width=3 * S)
    tick_or_cross(d, (106, 822), good)
    text(d, (142, 822), message, 25, bold=True, anchor="lm")


def scene_phone(kind: str, t: float, title: str, sub: str, good: bool, message: str) -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)
    heading(d, title, sub)
    x0, y0, x1, y1 = PHONE
    d.rounded_rectangle(px(x0 - 14, y0 - 14, x1 + 14, y1 + 14), radius=44 * S, fill=INK)   # phone body
    mask = Image.new("L", ((x1 - x0) * S, (y1 - y0) * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, mask.width - 1, mask.height - 1], radius=32 * S, fill=255)
    img.paste(phone_view(kind, t), px(x0, y0), mask)
    if int(t * 2) % 2 == 0:                                                             # blinking REC light
        dot(d, (x0 + 30, y0 + 30), 8, BAD)
    text(d, (x0 + 46, y0 + 30), "REC", 18, INK, bold=True, anchor="lm")
    verdict(d, good, message)
    return img


def scene_placement(t: float) -> Image.Image:
    """Seen from above: you in the middle, the phone at your side."""
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)
    heading(d, "1. Phone at your side", "2 to 3 metres away, leaning on something")
    d.rounded_rectangle(px(60, 170, W - 60, 750), radius=28 * S, fill=CARD, outline=LINE, width=2 * S)
    you, phone_x = (230, 460), 230 + 310 * min(1.0, t / 1.2)
    # what the camera sees
    cone = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(cone).polygon(px(phone_x, you[1], you[0] - 40, you[1] - 190, you[0] - 40, you[1] + 190), fill=(*_rgb(BRAND), 38))
    img.paste(cone, (0, 0), cone)
    # the person, from above, facing the top of the picture
    d.ellipse(px(you[0] - 34, you[1] - 78, you[0] + 34, you[1] + 78), fill=INK)
    dot(d, you, 30, "#334155")
    d.line(px(you[0], you[1] - 110, you[0], you[1] - 170), fill=MUTED, width=4 * S)
    d.polygon(px(you[0], you[1] - 188, you[0] - 12, you[1] - 166, you[0] + 12, you[1] - 166), fill=MUTED)
    text(d, (you[0], you[1] - 212), "you face this way", 20, MUTED, anchor="mm")
    text(d, (you[0], you[1] + 112), "You", 24, bold=True, anchor="mm")
    # the phone
    d.rounded_rectangle(px(phone_x - 9, you[1] - 34, phone_x + 9, you[1] + 34), radius=5 * S, fill=BRAND)
    text(d, (phone_x, you[1] + 62), "Phone", 24, BRAND, bold=True, anchor="mm")
    if t > 1.2:                         # the distance, as a dashed line
        x = you[0] + 50
        while x < phone_x - 24:
            d.line(px(x, you[1], min(x + 12, phone_x - 24), you[1]), fill=INK, width=3 * S)
            x += 22
        text(d, ((you[0] + phone_x) / 2 + 14, you[1] - 26), "2-3 m", 26, bold=True, anchor="mm")
    verdict(d, True, "Side view. Not front, not behind.")
    return img


def scene_summary(t: float) -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)
    heading(d, "Ready to film", "Check these, then press record")
    lines = ["Side view, 2-3 metres away", "Whole body in the picture", "Phone still, leaning on something",
             "3 to 8 reps, 10 to 30 seconds", "One person, good light", "Light weight, normal speed"]
    for k, line in enumerate(lines):
        if t < 0.35 * k:
            break
        y = 210 + 92 * k
        d.rounded_rectangle(px(60, y, W - 60, y + 76), radius=18 * S, fill=CARD, outline=LINE, width=2 * S)
        tick_or_cross(d, (104, y + 38), True)
        text(d, (142, y + 38), line, 26, bold=True, anchor="lm")
    return img


# (seconds, function of the time inside the scene)
SCENES = [
    (4.0, scene_placement),
    (5.0, lambda t: scene_phone("good", t, "2. Whole body in the picture", "Head to feet, for the whole set", True, "Good: this is what we need")),
    (3.6, lambda t: scene_phone("close", t, "Too close", "We cannot see the hips, knees or feet", False, "Step back until all of you fits")),
    (3.6, lambda t: scene_phone("front", t, "Filmed from the front", "The bend of the knee is hidden", False, "Move the phone to your side")),
    (3.6, lambda t: scene_phone("moving", t, "Phone moving", "Held in a hand, or tilted", False, "Lean it on a bottle or a bag")),
    (4.4, scene_summary),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "how-to-film.mp4"
    ffmpeg = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "24", "-preset", "slow", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    for k, (seconds, scene) in enumerate(SCENES):
        for i in range(round(seconds * FPS)):
            frame = scene(i / FPS).resize((W, H), Image.LANCZOS)
            if k == 1 and i == round(0.9 * FPS):        # poster: the good example, mid squat
                frame.save(OUT / "how-to-film.jpg", quality=85)
            ffmpeg.stdin.write(frame.tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("ffmpeg could not write the video")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {sum(s for s, _ in SCENES):.0f} s)")


if __name__ == "__main__":
    main()
