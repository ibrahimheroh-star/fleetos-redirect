#!/usr/bin/env python3
"""Turn ONE still image (PNG with transparency works best) into a 5 s vertical motion-graphic clip (silent).

Beats: ring burst -> sticker pops in with overshoot + impact flash + sparks + screen shake -> idle vibration that
"revs" on caption beats -> word-by-word English captions with hero-word highlight -> CTA pill.
Pair the output with pro_fx.py (grade + SFX + loudnorm + export): see examples/engine_motion_plan.json.

Usage: python image_to_motion.py IMAGE OUT.mp4 [--lines "BUILT TO ROAR" "FEEL THE POWER"] [--cta "FOLLOW FOR MORE"]
Edit BEATS below to retime. Requires: pillow, numpy, ffmpeg.
"""
import argparse, math, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

W, H, FPS, DUR = 1080, 1920, 30, 5.0
YEL = (255, 201, 51)
ORANGE = (255, 120, 30)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ---- timing (seconds): everything the SFX plan should sync to --------------------------------
LAND = 0.80                       # sticker lands + impact
REVS = [2.00, 3.65]               # engine "revs": extra vibration, ring, shake
PHRASES = [                       # (word start times, exit time)
    ([1.30, 1.60, 1.95], 2.95),
    ([3.05, 3.35, 3.65], 4.35),
]
CTA_AT = 4.60


def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def out_cubic(x): x = clamp(x); return 1 - (1 - x) ** 3
def out_back(x, k=1.9):
    x = clamp(x); return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2
def decay(t, t0, d): return 0.0 if t < t0 else math.exp(-(t - t0) / d)


def font(px): return ImageFont.truetype(FONT, px)


def make_bg():
    ys = np.linspace(0, 1, H)[:, None, None]
    top, bot = np.array([13, 13, 19]), np.array([30, 24, 36])
    return (top + (bot - top) * ys).repeat(W, 1).astype(np.uint8)


def radial_glow(size, color):
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx - size / 2, yy - size / 2) / (size / 2)
    a = np.clip(1 - d, 0, 1) ** 2
    g = np.zeros((size, size, 4), np.uint8); g[..., :3] = color; g[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(g, "RGBA")


def text_layer(txt, px, fill, stroke=12):
    f = font(px)
    bb = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), txt, font=f, stroke_width=stroke)
    w, h = bb[2] - bb[0] + 2 * stroke + 8, bb[3] - bb[1] + 2 * stroke + 8
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # soft drop shadow for depth, then stroked text
    d.text((stroke + 4 - bb[0], stroke + 10 - bb[1]), txt, font=f, fill=(0, 0, 0, 150), stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
    d.text((stroke + 4 - bb[0], stroke + 4 - bb[1]), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=(10, 10, 14, 255))
    return im


def paste_center(canvas, sprite, cx, cy, scale=1.0, angle=0.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01: return
    if scale != 1.0:
        sprite = sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))), Image.BICUBIC)
    if angle:
        sprite = sprite.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 1.0:
        a = sprite.getchannel("A").point(lambda v: int(v * alpha)); sprite = sprite.copy(); sprite.putalpha(a)
    canvas.alpha_composite(sprite, (int(cx - sprite.width / 2), int(cy - sprite.height / 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("out")
    ap.add_argument("--lines", nargs=2, default=["BUILT TO ROAR", "FEEL THE POWER"])
    ap.add_argument("--cta", default="FOLLOW FOR MORE")
    a = ap.parse_args()

    src = Image.open(a.image).convert("RGBA")
    BASE = 960
    hero = src.resize((BASE, int(BASE * src.height / src.width)), Image.LANCZOS)
    hero = hero.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    # soft contact shadow derived from the artwork's own silhouette
    sh = hero.getchannel("A").filter(ImageFilter.GaussianBlur(26)).point(lambda v: int(v * 0.55))
    shadow = Image.new("RGBA", hero.size, (0, 0, 0, 0)); shadow.putalpha(sh)

    bg = make_bg()
    glow_o = radial_glow(1400, ORANGE)
    ex, ey = W // 2, 700                       # sticker centre
    phrases = []
    for (times, tex), line in zip(PHRASES, a.lines):
        words = line.split()
        sprites = [text_layer(w, 200 if i == len(words) - 1 else 128, YEL if i == len(words) - 1 else (255, 255, 255))
                   for i, w in enumerate(words)]
        gap = 30
        total = 0   # layout is computed per line below (hero word sits on its own, larger line)
        phrases.append((times, tex, sprites, gap, total))
    cta_font = font(62)
    cta_bb = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), a.cta, font=cta_font)
    cta = Image.new("RGBA", (cta_bb[2] - cta_bb[0] + 110, 128), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cta); cd.rounded_rectangle((0, 0, cta.width - 1, 127), 64, fill=YEL)
    cd.text((55 - cta_bb[0], 64), a.cta, font=cta_font, fill=(15, 15, 20), anchor="lm")

    random.seed(7)
    sparks = []   # (t0, x0, y0, vx, vy, size, color)
    for t0, n, spread in [(LAND, 34, 1.0)] + [(r, 14, 0.6) for r in REVS]:
        for _ in range(n):
            ang = random.uniform(0, 2 * math.pi); sp = random.uniform(300, 900) * spread
            sparks.append((t0, ex + random.uniform(-120, 120), ey + random.uniform(-80, 120),
                           math.cos(ang) * sp, math.sin(ang) * sp - 250, random.uniform(5, 13),
                           random.choice([YEL, ORANGE, (255, 240, 200)])))

    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                           "-pix_fmt", "yuv420p", a.out], stdin=subprocess.PIPE)
    for fi in range(int(DUR * FPS)):
        t = fi / FPS
        scene = Image.fromarray(bg).convert("RGBA")
        d = ImageDraw.Draw(scene, "RGBA")

        # intro: ring collapses/expands toward the landing point
        if t < LAND + 0.5:
            p = out_cubic(t / LAND)
            r = 90 + 520 * p
            alpha = int(255 * (1 - clamp((t - LAND * 0.6) / (LAND * 0.5 + 0.25))))
            d.ellipse((ex - r, ey - r, ex + r, ey + r), outline=YEL + (alpha,), width=int(16 * (1 - p) + 4))

        # impact + rev shockwaves
        for t0, mx in [(LAND, 900)] + [(r, 650) for r in REVS]:
            if 0 <= t - t0 < 0.7:
                p = out_cubic((t - t0) / 0.7); r = 140 + mx * p
                d.ellipse((ex - r, ey - r, ex + r, ey + r), outline=(255, 190, 60, int(220 * (1 - p))), width=int(26 * (1 - p) + 3))

        # pulsing warm glow behind the sticker; brighter on revs
        rev_boost = max([decay(t, r, 0.35) for r in REVS] + [0]) + decay(t, LAND, 0.25)
        g = 0.18 + 0.55 * min(1, rev_boost)
        if t > LAND - 0.2:
            gs = glow_o.copy(); gs.putalpha(gs.getchannel("A").point(lambda v, g=g: int(v * g)))
            paste_center(scene, gs, ex, ey, 1.0 + 0.1 * rev_boost)

        # sticker: pop-in with overshoot, then idle vibration that intensifies on revs
        if t > LAND - 0.30:
            s_in = out_back((t - (LAND - 0.30)) / 0.42)
            tilt = -9 * (1 - out_back((t - (LAND - 0.30)) / 0.55, 1.2))
            vib = 2.2 + 9 * max([decay(t, r, 0.45) for r in REVS] + [0]) if t > LAND + 0.2 else 0
            dx, dy = vib * math.sin(t * 91), vib * math.cos(t * 77)
            drift = 1.0 + 0.06 * clamp((t - LAND) / (DUR - LAND))
            pulse = 1.0 + 0.035 * max([decay(t, r, 0.22) for r in REVS] + [0])
            sc = s_in * drift * pulse
            paste_center(scene, shadow, ex + dx + 14, ey + dy + 26, sc, tilt, 0.9)
            paste_center(scene, hero, ex + dx, ey + dy, sc, tilt)

        # sparks
        for t0, x0, y0, vx, vy, sz, col in sparks:
            lt = t - t0
            if 0 <= lt < 0.8:
                x, y = x0 + vx * lt, y0 + vy * lt + 1400 * lt * lt
                al = int(255 * (1 - lt / 0.8)); s = sz * (1 - lt / 1.2)
                d.ellipse((x - s, y - s, x + s, y + s), fill=col + (al,))

        # impact flash
        if LAND <= t < LAND + 0.14:
            fl = Image.new("RGBA", (W, H), (255, 245, 225, int(130 * (1 - (t - LAND) / 0.14)))); scene.alpha_composite(fl)

        # screen shake + impact punch on the scene layer (text stays rock-steady for legibility)
        sh_amp = 34 * decay(t, LAND, 0.10) + sum(20 * decay(t, r, 0.12) for r in REVS)
        ox, oy = sh_amp * math.sin(t * 143), sh_amp * math.cos(t * 121)
        zoom = 1.0 + 0.045 * decay(t, LAND, 0.12) + sum(0.03 * decay(t, r, 0.14) for r in REVS)
        sc_img = scene.convert("RGB").transform((W, H), Image.AFFINE,
                 (1 / zoom, 0, W / 2 - (W / 2 + ox) / zoom, 0, 1 / zoom, H / 2 - (H / 2 + oy) / zoom), Image.BILINEAR)
        frame = sc_img.convert("RGBA")

        # captions: word-by-word pop, hero word in yellow, whole phrase slides out
        for times, tex, sprites, gap, total in phrases:
            if times[0] <= t < tex + 0.3:
                exit_p = clamp((t - tex) / 0.28)
                # line 1: all words but the last (centred); line 2: the hero word, bigger, in yellow
                head, hero_w = sprites[:-1], sprites[-1]
                head_w = sum(sp.width for sp in head) + gap * (len(head) - 1)
                x = W / 2 - head_w / 2
                for i, (st, spr) in enumerate(zip(times, sprites)):
                    if spr is hero_w:
                        cx, cy = W / 2, 1495
                    else:
                        cx, cy = x + spr.width / 2, 1335; x += spr.width + gap
                    p = out_back((t - st) / 0.22, 2.6)
                    if t >= st:
                        paste_center(frame, spr, cx, cy + 90 * exit_p, p * (1 + 0.1 * decay(t, st, 0.12)), 0, 1 - exit_p)

        # CTA pill
        if t >= CTA_AT:
            p = out_back((t - CTA_AT) / 0.3, 2.2)
            paste_center(frame, cta, W / 2, 1500, p * (1 + 0.04 * math.sin((t - CTA_AT) * 14) * decay(t, CTA_AT, 0.5)))

        ff.stdin.write(np.asarray(frame.convert("RGB")).tobytes())
    ff.stdin.close(); ff.wait()
    print(a.out)


if __name__ == "__main__":
    main()
