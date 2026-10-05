#!/usr/bin/env python3
"""Motion-graphics template library (30 animated overlays/scenes) rendered with Pillow + ffmpeg.

  python mg.py list                                      # templates + their parameters
  python mg.py TEMPLATE OUT.mov [--dur S] [--p key=value ...]      # transparent overlay (qtrle .mov)
  python mg.py TEMPLATE OUT.mp4 --bg 0x101018 [--p ...]            # on a solid background (.mp4)
  python mg.py overlay VIDEO MG.mov OUT.mp4 --at 2.5 [--x 0 --y 0] # composite an overlay onto a video at time T

Everything is full-canvas (default 1080x1920) so overlays drop straight onto a vertical video. Text supports Arabic
(Pillow+raqm shapes and orders it) and English; keep lines short. Colours are hex like FFD933.
Preview fast with --size 540x960. Requires pillow, numpy, ffmpeg.
"""
import argparse, math, os, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

W, H, FPS = 1080, 1920, 30
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = {}
YEL, WHITE, DARK = "FFD933", "FFFFFF", "0F0F14"


# ---------------------------------------------------------------- helpers
def rgb(h, a=255):
    h = h.lstrip("#").replace("0x", ""); return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def out_cubic(x): x = clamp(x); return 1 - (1 - x) ** 3
def in_out(x): x = clamp(x); return x * x * (3 - 2 * x)
def out_back(x, k=1.8): x = clamp(x); return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2
def out_elastic(x):
    x = clamp(x); return 0 if x == 0 else 1 if x == 1 else 2 ** (-9 * x) * math.sin((x * 10 - 0.75) * 2 * math.pi / 3) + 1
def decay(t, t0, d): return 0.0 if t < t0 else math.exp(-(t - t0) / d)
def S(v): return v * W / 1080.0
def blank(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))
def font(px): return ImageFont.truetype(BOLD, max(6, int(S(px))), layout_engine=ImageFont.Layout.RAQM)


def text_sprite(txt, px, fill=WHITE, stroke=0, stroke_fill="0F0F14", shadow=False):
    f = font(px); st = int(S(stroke)); pad = st + int(S(14))
    bb = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), txt, font=f, stroke_width=st)
    w, h = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if shadow: d.text((pad - bb[0] + S(4), pad - bb[1] + S(9)), txt, font=f, fill=(0, 0, 0, 140), stroke_width=st, stroke_fill=(0, 0, 0, 140))
    d.text((pad - bb[0], pad - bb[1]), txt, font=f, fill=rgb(fill), stroke_width=st, stroke_fill=rgb(stroke_fill))
    if im.width > W * 0.94:  # auto-fit: never overflow the frame (long words / Arabic phrases)
        k = W * 0.94 / im.width; im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    return im


def paste(canvas, spr, cx, cy, scale=1.0, angle=0.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01: return
    if abs(scale - 1) > 1e-3: spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BICUBIC)
    if angle: spr = spr.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        spr = spr.copy(); spr.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(spr, (int(cx - spr.width / 2), int(cy - spr.height / 2)))


def star_pts(cx, cy, r, n=5, inner=0.45, rot=-math.pi / 2):
    return [(cx + (r if i % 2 == 0 else r * inner) * math.cos(rot + i * math.pi / n), cy + (r if i % 2 == 0 else r * inner) * math.sin(rot + i * math.pi / n)) for i in range(2 * n)]
def heart_pts(cx, cy, r):
    pts = []
    for i in range(60):
        a = i / 60 * 2 * math.pi
        pts.append((cx + r * 16 * math.sin(a) ** 3 / 16, cy - r * (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16))
    return pts
def glow(img, radius, strength=1.0):
    g = img.filter(ImageFilter.GaussianBlur(S(radius)))
    if strength != 1: g.putalpha(g.getchannel("A").point(lambda v: min(255, int(v * strength))))
    return g


class P:
    def __init__(self, d): self.d = d
    def s(self, k): return str(self.d[k])
    def f(self, k): return float(self.d[k])
    def i(self, k): return int(float(self.d[k]))
    def c(self, k): return self.d[k]


def template(tname, doc, /, dur=3.0, **defaults):
    def deco(fn): REG[tname] = dict(fn=fn, doc=doc, dur=dur, defaults=defaults); return fn
    return deco


# ================================================================== TEXT & TITLES
@template("lower-third", "name + title bar slides in, holds, slides out", dur=4.0, name="IBRAHIM", title="FOUNDER", color=YEL, y=0.74)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); y = H * p.f("y"); a_in = out_cubic(t / 0.45); a_out = in_out((t - (d - 0.45)) / 0.45)
    prog = a_in * (1 - a_out); x0 = S(60)
    n = text_sprite(p.s("name"), 78, WHITE, 0, shadow=True); ti = text_sprite(p.s("title"), 44, DARK)
    w = max(n.width, ti.width + S(50)) + S(40)
    dr.rounded_rectangle((x0 - S(30) - (1 - prog) * (w + S(100)), y - S(10), x0 - S(30) + w - (1 - prog) * (w + S(100)), y + S(150)), S(10), fill=(15, 15, 20, 215))
    dr.rectangle((x0 - S(30) - (1 - prog) * (w + S(100)), y - S(10), x0 - S(18) - (1 - prog) * (w + S(100)), y + S(150)), fill=rgb(p.c("color")))
    paste(c, n, x0 + n.width / 2 - (1 - prog) * (w + S(100)), y + S(48), alpha=clamp(prog * 1.5))
    dr.rounded_rectangle((x0, y + S(98), x0 + ti.width + S(24), y + S(146)), S(6), fill=rgb(p.c("color")) if prog > 0.01 else None)
    if prog > 0.01: paste(c, ti, x0 + ti.width / 2 + S(12), y + S(122))
    return c


@template("title-card", "kinetic title: words fly in alternately with overshoot, underline sweeps", dur=3.5, text="BUILT TO ROAR", color=YEL, y=0.45, size=170)
def _(t, d, p):
    c = blank(); words = p.s("text").split(); y = H * p.f("y"); sp = [text_sprite(w, p.f("size"), p.c("color") if i == len(words) - 1 else WHITE, 14, shadow=True) for i, w in enumerate(words)]
    lh = max(s.height for s in sp) * 0.95; ex = in_out((t - (d - 0.4)) / 0.4)
    for i, s in enumerate(sp):
        t0 = 0.12 + i * 0.18; k = out_back((t - t0) / 0.35, 2.2); side = -1 if i % 2 == 0 else 1
        cx = W / 2 + side * (1 - clamp((t - t0) / 0.35)) * W * 0.7; cy = y + (i - (len(sp) - 1) / 2) * lh
        paste(c, s, cx, cy + ex * H * 0.1, k, 0, 1 - ex)
    dr = ImageDraw.Draw(c); ul = out_cubic((t - 0.12 - len(sp) * 0.18) / 0.4)
    if ul > 0: dr.rounded_rectangle((W / 2 - W * 0.32 * ul, y + len(sp) * lh / 2 + S(10), W / 2 + W * 0.32 * ul, y + len(sp) * lh / 2 + S(26)), S(8), fill=rgb(p.c("color"), int(255 * (1 - ex))))
    return c


@template("typewriter", "quote typed out with cursor, then author line", dur=4.0, text="Make it simple, but significant.", author="DON DRAPER", color=YEL, size=70)
def _(t, d, p):
    c = blank(); full = p.s("text"); n = int(len(full) * clamp((t - 0.3) / (d * 0.55)))
    lines = []; cur = ""
    for w in full[:n].split(" "):
        if len(cur) + len(w) > 20 and cur: lines.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    lines.append(cur + ("|" if int(t * 3) % 2 == 0 else " "))
    y = H * 0.4
    box = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(box).rounded_rectangle((S(60), y - S(60), W - S(60), y + S(120) * len(lines) + S(150)), S(30), fill=(15, 15, 20, int(200 * clamp(t / 0.3))))
    c.alpha_composite(box)
    for i, ln in enumerate(lines): paste(c, text_sprite(ln, p.f("size"), WHITE, 0), W / 2, y + S(60) + i * S(100))
    if n >= len(full): paste(c, text_sprite("— " + p.s("author"), 44, p.c("color")), W / 2, y + S(110) * len(lines) + S(60), out_back((t - d * 0.6) / 0.3), 0, clamp((t - d * 0.6) / 0.2))
    return c


@template("kinetic-words", "sentence appears word by word with rotation/scale pops, hero word highlighted", dur=4.0, text="SLOW DOWN TO SPEED UP", hero=3, color=YEL, size=140)
def _(t, d, p):
    c = blank(); words = p.s("text").split(); hero = p.i("hero") % len(words); rnd = random.Random(5)
    per = (d - 0.9) / len(words); cy = H * 0.45
    for i, w in enumerate(words):
        t0 = 0.15 + i * per; k = out_back((t - t0) / 0.28, 2.6)
        if t < t0: continue
        spr = text_sprite(w, p.f("size") * (1.25 if i == hero else 1), p.c("color") if i == hero else WHITE, 12, shadow=True)
        ang = rnd.uniform(-8, 8) * (1 - clamp((t - t0) / 0.5)) + (0 if i != hero else 3)
        paste(c, spr, W / 2 + rnd.uniform(-60, 60) * (1 - clamp((t - t0) / 0.3)), cy + (i - (len(words) - 1) / 2) * S(170), k, ang, 1 - in_out((t - (d - 0.35)) / 0.35))
    return c


@template("glitch-title", "title with RGB split + slice jitter bursts, then settles", dur=3.0, text="SYSTEM FAILURE", color="00F0FF", size=130)
def _(t, d, p):
    c = blank(); rnd = random.Random(int(t * 24)); base = text_sprite(p.s("text"), p.f("size"), WHITE, 0)
    jit = decay(t, 0, 0.5) + (decay(t, 1.6, 0.25) if t > 1.6 else 0)
    ox = int(S(14) * jit * (1 if rnd.random() > 0.5 else -1))
    r = Image.new("RGBA", base.size, rgb("FF0050")); r.putalpha(base.getchannel("A")); b = Image.new("RGBA", base.size, rgb(p.c("color"))); b.putalpha(base.getchannel("A"))
    cx, cy = W / 2, H * 0.45; vis = 1 - in_out((t - (d - 0.3)) / 0.3)
    paste(c, r, cx - ox, cy, 1, 0, 0.9 * vis); paste(c, b, cx + ox, cy, 1, 0, 0.9 * vis); paste(c, base, cx, cy, 1, 0, vis)
    if jit > 0.15:
        for _ in range(3):
            y0 = rnd.randint(int(cy - base.height / 2), int(cy + base.height / 2) - 10); h = rnd.randint(8, 40); dx = rnd.randint(-int(S(60)), int(S(60)))
            strip = c.crop((0, y0, W, y0 + h)); c.paste((0, 0, 0, 0), (0, y0, W, y0 + h)); c.alpha_composite(strip, (dx, y0))
    return c


@template("neon-text", "neon sign text with glow and flicker", dur=3.5, text="OPEN 24/7", color="FF2FA0", size=150)
def _(t, d, p):
    c = blank(); fl = 1.0 if t > 1.2 else (0.25 if int(t * 14) % 3 == 0 else 1.0)
    spr = text_sprite(p.s("text"), p.f("size"), "FFFFFF", 0); tint = Image.new("RGBA", spr.size, rgb(p.c("color"))); tint.putalpha(spr.getchannel("A"))
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0)); paste(big, tint, W / 2, H * 0.45)
    for r, s in ((60, 1.6), (28, 1.4), (10, 1.2)): c.alpha_composite(glow(big, r, s * fl))
    paste(c, spr, W / 2, H * 0.45, 1, 0, fl); return c


@template("highlight-box", "marker highlight sweeps behind a text line (emphasis)", dur=3.0, text="THIS IS THE KEY", color=YEL, size=100)
def _(t, d, p):
    c = blank(); spr = text_sprite(p.s("text"), p.f("size"), DARK, 0); cy = H * 0.45; w = spr.width + S(60); k = out_cubic((t - 0.2) / 0.5)
    ImageDraw.Draw(c).rounded_rectangle((W / 2 - w / 2, cy - spr.height / 2 - S(6), W / 2 - w / 2 + w * k, cy + spr.height / 2 + S(6)), S(12), fill=rgb(p.c("color"), int(255 * (1 - in_out((t - (d - 0.3)) / 0.3)))))
    paste(c, spr, W / 2, cy, 1, 0, clamp((t - 0.25) / 0.2) * (1 - in_out((t - (d - 0.3)) / 0.3))); return c


@template("split-reveal", "text revealed by two halves sliding apart", dur=3.0, text="THE REVEAL", color=YEL, size=160)
def _(t, d, p):
    c = blank(); spr = text_sprite(p.s("text"), p.f("size"), p.c("color"), 10, shadow=True); cx, cy = W / 2, H * 0.45; k = in_out((t - 0.3) / 0.6)
    ex = in_out((t - (d - 0.4)) / 0.4)
    top = spr.crop((0, 0, spr.width, spr.height // 2)); bot = spr.crop((0, spr.height // 2, spr.width, spr.height))
    lid = Image.new("RGBA", (W, H), (0, 0, 0, 0)); paste(lid, spr, cx, cy, 1, 0, 1 - ex)
    mask = Image.new("L", (W, H), 0); h = (spr.height + 20) * k / 2; ImageDraw.Draw(mask).rectangle((0, cy - h, W, cy + h), fill=255)
    c.paste(lid, (0, 0), ImageChops.multiply(mask, lid.getchannel("A")))
    dr = ImageDraw.Draw(c); lw = W * 0.7 * (1 - abs(k - 0.5) * 0.0); dr.line((cx - lw / 2 * k, cy, cx + lw / 2 * k, cy), fill=rgb(WHITE, int(255 * (1 - k))), width=int(S(4)))
    return c


@template("step-number", "big step number + title wipe (01 / 02 / 03 explainers)", dur=3.0, number="01", text="PLAN YOUR HOOK", color=YEL)
def _(t, d, p):
    c = blank(); n = text_sprite(p.s("number"), 330, p.c("color"), 0, shadow=True); ti = text_sprite(p.s("text"), 78, WHITE, 6, shadow=True)
    k = out_back((t - 0.1) / 0.5, 2.0); ex = 1 - in_out((t - (d - 0.35)) / 0.35)
    paste(c, n, W / 2, H * 0.38, k, 0, ex); paste(c, ti, W / 2, H * 0.38 + S(260), 1, 0, clamp((t - 0.45) / 0.3) * ex)
    ImageDraw.Draw(c).rounded_rectangle((W / 2 - S(200) * out_cubic((t - 0.35) / 0.5), H * 0.38 + S(190), W / 2 + S(200) * out_cubic((t - 0.35) / 0.5), H * 0.38 + S(200)), S(5), fill=rgb(p.c("color"), int(255 * ex)))
    return c


@template("social-handle", "@handle card: avatar circle, verified tick, slide in/out", dur=3.5, handle="@your.handle", sub="FOLLOW FOR MORE", color=YEL)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); prog = out_cubic(t / 0.5) * (1 - in_out((t - (d - 0.4)) / 0.4)); w = W - S(160); x0 = S(80) + (1 - prog) * W; y = H * 0.82
    dr.rounded_rectangle((x0, y, x0 + w, y + S(170)), S(85), fill=(15, 15, 20, 230)); r = S(60)
    dr.ellipse((x0 + S(24), y + S(25), x0 + S(24) + 2 * r, y + S(25) + 2 * r), fill=rgb(p.c("color")))
    h = text_sprite(p.s("handle"), 56, WHITE, 0); sb = text_sprite(p.s("sub"), 34, p.c("color"), 0)
    paste(c, h, x0 + S(170) + h.width / 2, y + S(62)); paste(c, sb, x0 + S(170) + sb.width / 2, y + S(120))
    vx = x0 + S(170) + h.width + S(26); vy = y + S(62); dr.ellipse((vx - S(22), vy - S(22), vx + S(22), vy + S(22)), fill=rgb("3897F0"))
    dr.line([(vx - S(10), vy), (vx - S(3), vy + S(8)), (vx + S(11), vy - S(8))], fill=(255, 255, 255, 255), width=int(S(5)), joint="curve")
    return c


# ================================================================== NUMBERS & CHARTS
@template("counter", "number counts up with pop at the end (stats, results)", dur=3.0, to=1000, start=0, prefix="", suffix="+", label="FOLLOWERS", color=YEL, size=260)
def _(t, d, p):
    c = blank(); k = out_cubic((t - 0.2) / (d * 0.6)); v = int(p.f("start") + (p.f("to") - p.f("start")) * k)
    s = text_sprite(f"{p.s('prefix')}{v:,}{p.s('suffix')}", p.f("size"), p.c("color"), 12, shadow=True); lab = text_sprite(p.s("label"), 70, WHITE, 6)
    pop = 1 + 0.12 * decay(t, d * 0.6 + 0.2, 0.15) if t > d * 0.6 + 0.2 else 1; ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    paste(c, s, W / 2, H * 0.43, out_back(t / 0.3) * pop, 0, ex); paste(c, lab, W / 2, H * 0.43 + S(210), 1, 0, clamp((t - 0.3) / 0.3) * ex); return c


@template("progress-ring", "circular ring fills to a percentage with number in the centre", dur=3.0, percent=75, label="COMPLETE", color=YEL)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); cx, cy, r = W / 2, H * 0.42, S(300); k = out_cubic((t - 0.2) / (d * 0.65)); pc = p.f("percent") * k
    ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, int(60 * ex)), width=int(S(40)))
    if pc > 0.2: dr.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * pc / 100, fill=rgb(p.c("color"), int(255 * ex)), width=int(S(40)))
    paste(c, text_sprite(f"{int(pc)}%", 190, WHITE, 8, shadow=True), cx, cy, 1, 0, ex); paste(c, text_sprite(p.s("label"), 54, p.c("color"), 0), cx, cy + r + S(90), 1, 0, ex * clamp((t - 0.4) / 0.3)); return c


@template("bar-chart", "animated bar chart. values like 'JAN:30,FEB:55,MAR:90'", dur=4.0, values="JAN:30,FEB:55,MAR:90,APR:70", color=YEL, title="GROWTH")
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); items = [(a, float(b)) for a, b in (x.split(":") for x in p.s("values").split(","))]; mx = max(v for _, v in items)
    base, top = H * 0.62, H * 0.25; bw = (W - S(200)) / len(items) * 0.62; gap = (W - S(200)) / len(items); ex = 1 - in_out((t - (d - 0.35)) / 0.35)
    paste(c, text_sprite(p.s("title"), 80, WHITE, 6, shadow=True), W / 2, H * 0.18, out_back(t / 0.35), 0, ex)
    for i, (lab, v) in enumerate(items):
        k = out_back((t - 0.3 - i * 0.15) / 0.55, 1.3); h = (base - top) * v / mx * clamp(k, 0, 1.15); x = S(100) + gap * i + (gap - bw) / 2
        dr.rounded_rectangle((x, base - h, x + bw, base), S(16), fill=rgb(p.c("color"), int(255 * ex)))
        paste(c, text_sprite(lab, 40, WHITE, 0), x + bw / 2, base + S(50), 1, 0, ex); paste(c, text_sprite(str(int(v * clamp(k))), 46, WHITE, 5), x + bw / 2, base - h - S(40), 1, 0, ex * clamp(k))
    return c


@template("rating-stars", "stars fill one by one with pop (reviews)", dur=3.0, stars=5, label="5.0 RATING", color=YEL)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); n = p.i("stars"); r = S(78); gap = S(170); ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    for i in range(n):
        cx = W / 2 + (i - (n - 1) / 2) * gap; k = out_back((t - 0.25 - i * 0.2) / 0.35, 2.4); pts = star_pts(cx, H * 0.43, r * max(k, 0.01))
        dr.polygon(star_pts(cx, H * 0.43, r), fill=(255, 255, 255, int(50 * ex)))
        if t > 0.25 + i * 0.2: dr.polygon(pts, fill=rgb(p.c("color"), int(255 * ex)))
    paste(c, text_sprite(p.s("label"), 70, WHITE, 6, shadow=True), W / 2, H * 0.43 + S(170), 1, 0, ex * clamp((t - 0.3 - n * 0.2) / 0.3)); return c


@template("checklist", "checklist: items type in, check marks draw. items 'A|B|C'", dur=4.5, items="HOOK|VALUE|CTA", color="3DDC84", size=84)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); its = p.s("items").split("|"); ex = 1 - in_out((t - (d - 0.35)) / 0.35); y0 = H * 0.36
    for i, it in enumerate(its):
        t0 = 0.2 + i * 0.7; y = y0 + i * S(170); k = out_cubic((t - t0) / 0.35)
        if t < t0: continue
        dr.rounded_rectangle((S(110), y - S(46), S(202), y + S(46)), S(18), outline=(255, 255, 255, int(255 * ex)), width=int(S(7)))
        ck = clamp((t - t0 - 0.35) / 0.3)
        if ck > 0:
            pts = [(S(128), y), (S(150), y + S(24)), (S(188), y - S(26))]; seg = ck * 2
            line = [pts[0], pts[1]] if seg <= 1 else [pts[0], pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * (seg - 1), pts[1][1] + (pts[2][1] - pts[1][1]) * (seg - 1))]
            if seg < 1: line = [pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * seg, pts[0][1] + (pts[1][1] - pts[0][1]) * seg)]
            dr.line(line, fill=rgb(p.c("color"), int(255 * ex)), width=int(S(14)), joint="curve")
        s = text_sprite(it, p.f("size"), WHITE, 6, shadow=True); paste(c, s, S(250) + s.width / 2 + (1 - k) * S(80), y, 1, 0, k * ex)
    return c


@template("sale-badge", "starburst price/discount badge that pops, rotates and pulses", dur=3.0, text="50% OFF", sub="TODAY ONLY", color="FF3B30")
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); cx, cy = W / 2, H * 0.42; k = out_elastic(t / 0.7); ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    pulse = 1 + 0.04 * math.sin(t * 9); ang = math.sin(t * 2.2) * 5
    bd = Image.new("RGBA", (W, H), (0, 0, 0, 0)); bdd = ImageDraw.Draw(bd)
    bdd.polygon(star_pts(cx, cy, S(330), 16, 0.82, t * 0.6), fill=rgb(p.c("color"))); bdd.ellipse((cx - S(250), cy - S(250), cx + S(250), cy + S(250)), outline=(255, 255, 255, 255), width=int(S(8)))
    paste(c, bd, W / 2, H / 2, k * pulse, ang, ex); paste(c, text_sprite(p.s("text"), 120, WHITE, 8), cx, cy - S(15), k * pulse, ang, ex); paste(c, text_sprite(p.s("sub"), 46, WHITE, 0), cx, cy + S(100), k * pulse, ang, ex); return c


@template("countdown", "3-2-1 countdown with ring sweep and pop per number", dur=3.5, start=3, color=YEL)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); n = p.i("start"); idx = int(t / 1.0); cx, cy, r = W / 2, H * 0.42, S(280)
    if idx >= n: return c
    lt = t - idx; num = n - idx; k = out_back(lt / 0.3, 2.2); fade = 1 - in_out((lt - 0.8) / 0.2)
    dr.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * (1 - lt), fill=rgb(p.c("color"), int(255 * fade)), width=int(S(26)))
    paste(c, text_sprite(str(num), 420, WHITE, 14, shadow=True), cx, cy, k, 0, fade); return c


# ================================================================== PICTOGRAMS & SHAPES
@template("callout-circle", "hand-drawn circle draws around a point (x,y,r as fractions) + optional label", dur=3.0, x=0.5, y=0.45, r=0.2, color="FF3B30", label="LOOK HERE")
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); cx, cy, r = W * p.f("x"), H * p.f("y"), W * p.f("r"); k = out_cubic((t - 0.15) / 0.7); ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    n = int(120 * k) + 2; pts = []
    for i in range(n):
        a = -math.pi / 2 + i / 120 * 2 * math.pi * 1.06; rr = r * (1 + 0.04 * math.sin(a * 3 + 1) + 0.03 * i / 120); pts.append((cx + rr * math.cos(a), cy + rr * 0.9 * math.sin(a)))
    if len(pts) > 1: dr.line(pts, fill=rgb(p.c("color"), int(255 * ex)), width=int(S(14)), joint="curve")
    if p.s("label"): paste(c, text_sprite(p.s("label"), 60, p.c("color"), 6, shadow=True), cx, cy - r * 1.25, out_back((t - 0.7) / 0.3), 0, ex * clamp((t - 0.7) / 0.2))
    return c


@template("arrow-pointer", "bold arrow bounces toward a point (x,y fractions, angle degrees)", dur=3.0, x=0.5, y=0.55, angle=90, color=YEL, size=230)
def _(t, d, p):
    c = blank(); L = S(p.f("size")); ang = math.radians(p.f("angle")); bob = math.sin(t * 8) * S(26) * clamp(t / 0.4); ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    tx, ty = W * p.f("x"), H * p.f("y"); k = out_back(t / 0.35)
    dx, dy = math.cos(ang), math.sin(ang)           # direction the arrow points (0=right, 90=down)
    ox, oy = -dx * (L + S(40) + bob), -dy * (L + S(40) + bob); hx, hy = tx + ox, ty + oy
    px, py = -dy, dx; w = L * 0.28
    poly = [(hx - dx * L * 0.1 + px * w, hy - dy * L * 0.1 + py * w), (hx + dx * L * 0.5, hy + dy * L * 0.5), (hx - dx * L * 0.1 - px * w, hy - dy * L * 0.1 - py * w)]
    shaft = [(hx - dx * L * 0.1 + px * w * 0.4, hy - dy * L * 0.1 + py * w * 0.4), (hx - dx * L * 0.9 + px * w * 0.4, hy - dy * L * 0.9 + py * w * 0.4), (hx - dx * L * 0.9 - px * w * 0.4, hy - dy * L * 0.9 - py * w * 0.4), (hx - dx * L * 0.1 - px * w * 0.4, hy - dy * L * 0.1 - py * w * 0.4)]
    lay = blank(); ld = ImageDraw.Draw(lay)
    for off, col in ((S(8), (0, 0, 0, 120)), (0, rgb(p.c("color")))):
        ld.polygon([(x + off, y + off) for x, y in poly], fill=col); ld.polygon([(x + off, y + off) for x, y in shaft], fill=col)
    paste(c, lay, W / 2, H / 2, k, 0, ex); return c


@template("follow-button", "FOLLOW pill gets tapped by a cursor and turns into FOLLOWING + check", dur=3.5, color=YEL, text="FOLLOW", done="FOLLOWING")
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); cx, cy = W / 2, H * 0.5; w, h = S(560), S(150); tap = 1.6; ex = 1 - in_out((t - (d - 0.3)) / 0.3); k = out_back(t / 0.4)
    st = t >= tap; sc = 1 - 0.1 * decay(t, tap, 0.12) * (1 if st else 0)
    fill = (255, 255, 255, 255) if st else rgb(p.c("color")); lay = blank(); ld = ImageDraw.Draw(lay)
    ld.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), h / 2, fill=fill, outline=rgb(p.c("color")) if st else None, width=int(S(8)))
    lab = text_sprite(p.s("done") if st else p.s("text"), 62, DARK if not st else "333333", 0); paste(lay, lab, cx + (S(30) if st else 0), cy)
    if st:
        ck = clamp((t - tap) / 0.25); x0 = cx - lab.width / 2 - S(30)
        ld.line([(x0 - S(24), cy), (x0 - S(8), cy + S(18) * min(1, ck * 2)), ] + ([(x0 - S(8) + S(36) * (ck * 2 - 1), cy + S(18) - S(40) * (ck * 2 - 1))] if ck > 0.5 else []), fill=(61, 220, 132, 255), width=int(S(10)), joint="curve")
    paste(c, lay, W / 2, H / 2, k * sc, 0, ex)
    mx = cx + S(240) - (S(240) - S(60)) * out_cubic(t / tap) ; my = cy + S(420) - S(420 - 30) * out_cubic(t / tap)
    if t < tap + 0.5:
        cur = [(mx, my), (mx, my + S(70)), (mx + S(20), my + S(52)), (mx + S(40), my + S(88)), (mx + S(54), my + S(80)), (mx + S(34), my + S(46)), (mx + S(58), my + S(44))]
        dr.polygon(cur, fill=(255, 255, 255, int(255 * ex)), outline=(0, 0, 0, int(255 * ex)))
    return c


@template("like-burst", "hearts float up and fade (like / love moment)", dur=3.0, color="FF2D55", count=22)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); rnd = random.Random(11)
    for i in range(p.i("count")):
        t0 = rnd.uniform(0, d * 0.5); x0 = W * rnd.uniform(0.15, 0.85); sp = rnd.uniform(0.25, 0.45) * H; sz = S(rnd.uniform(34, 80)); ph = rnd.uniform(0, 6)
        lt = t - t0
        if lt < 0 or lt > 1.8: continue
        x = x0 + math.sin(lt * 3 + ph) * S(40); y = H * 0.85 - sp * lt; al = int(255 * (1 - lt / 1.8) * clamp(lt / 0.15)); s = sz * out_back(lt / 0.25)
        dr.polygon(heart_pts(x, y, s), fill=rgb(p.c("color"), al))
    return c


@template("confetti", "colourful confetti burst falling with spin (celebration)", dur=3.5, count=160)
def _(t, d, p):
    c = blank(); rnd = random.Random(3); cols = ["FF3B30", "FFD933", "3DDC84", "35A7FF", "FF2FA0", "FFFFFF"]
    for i in range(p.i("count")):
        t0 = rnd.uniform(0, 0.25); x0 = W * rnd.uniform(0.2, 0.8); vx = rnd.uniform(-800, 800) * W / 1080; vy = rnd.uniform(-2100, -800) * H / 1920; lt = t - t0
        if lt < 0: continue
        x = x0 + vx * lt * (1 - 0.35 * lt); y = H * 0.55 + vy * lt + 700 * (H / 1920) * lt * lt; ang = lt * rnd.uniform(-720, 720); w, h = S(rnd.uniform(14, 28)), S(rnd.uniform(8, 16))
        sp = Image.new("RGBA", (int(w) + 2, int(h) + 2), rgb(rnd.choice(cols))); paste(c, sp, x, y, 1, ang, clamp(1 - (lt - 2.2) / 1.0))
    return c


@template("location-pin", "map pin drops with ripple + place name", dur=3.5, text="DUBAI", color="FF3B30")
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); cx, cy = W / 2, H * 0.48; fall = out_cubic(t / 0.45); y = cy - (1 - fall) * H * 0.35 - (S(40) * decay(t, 0.45, 0.12) if t > 0.45 else 0); ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    if t > 0.45:
        for i in range(3):
            lt = (t - 0.45 - i * 0.25) / 1.0
            if 0 < lt < 1: r = S(60 + 260 * lt); dr.ellipse((cx - r, cy + S(80) - r * 0.35, cx + r, cy + S(80) + r * 0.35), outline=rgb(p.c("color"), int(200 * (1 - lt) * ex)), width=int(S(8)))
    lay = blank(); ld = ImageDraw.Draw(lay); R = S(95)
    ld.polygon([(cx - R * 0.8, y + R * 0.55), (cx, y + R * 2.1), (cx + R * 0.8, y + R * 0.55)], fill=rgb(p.c("color"))); ld.ellipse((cx - R, y - R, cx + R, y + R), fill=rgb(p.c("color"))); ld.ellipse((cx - R * 0.4, y - R * 0.4, cx + R * 0.4, y + R * 0.4), fill=(255, 255, 255, 255))
    paste(c, lay, W / 2, H / 2, 1, 0, ex); paste(c, text_sprite(p.s("text"), 100, WHITE, 8, shadow=True), cx, cy + S(250), out_back((t - 0.6) / 0.35), 0, ex * clamp((t - 0.6) / 0.2)); return c


@template("speed-lines", "manga/anime radial speed lines (action, zoom, impact)", dur=2.0, color="FFFFFF", density=90, inner=0.28)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); rnd = random.Random(int(t * 14)); cx, cy = W / 2, H / 2; R = math.hypot(W, H); ex = 1 - in_out((t - (d - 0.3)) / 0.3)
    for _ in range(p.i("density")):
        a = rnd.uniform(0, 2 * math.pi); r0 = R * rnd.uniform(p.f("inner"), p.f("inner") + 0.2); w = rnd.uniform(0.004, 0.018)
        dr.polygon([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + R * math.cos(a - w), cy + R * math.sin(a - w)), (cx + R * math.cos(a + w), cy + R * math.sin(a + w))], fill=rgb(p.c("color"), int(235 * ex)))
    return c


@template("news-ticker", "BREAKING news bar with scrolling text", dur=5.0, label="BREAKING", text="YOUR HEADLINE SCROLLS ACROSS THE BOTTOM OF THE SCREEN  •  ", color="E50914")
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); y = H * 0.86; h = S(120); prog = out_cubic(t / 0.4) * (1 - in_out((t - (d - 0.4)) / 0.4))
    dr.rectangle((0, y + (1 - prog) * h * 2, W, y + h + (1 - prog) * h * 2), fill=(15, 15, 20, 235))
    tx = text_sprite(p.s("text") * 4, 52, WHITE, 0); x = W - ((t * S(260)) % (tx.width / 4)) - S(150)
    layer = blank(); layer.alpha_composite(tx, (int(x - tx.width / 4 + S(400)), int(y + h / 2 - tx.height / 2 + (1 - prog) * h * 2)))
    c.alpha_composite(layer); lb = text_sprite(p.s("label"), 50, WHITE, 0)
    dr.rectangle((0, y + (1 - prog) * h * 2, lb.width + S(60), y + h + (1 - prog) * h * 2), fill=rgb(p.c("color"))); paste(c, lb, lb.width / 2 + S(30), y + h / 2 + (1 - prog) * h * 2); return c


# ================================================================== IMAGE-BASED (need image=PATH)
def load_img(path, width):
    im = Image.open(path).convert("RGBA"); w = int(S(width)); return im.resize((w, int(w * im.height / im.width)), Image.LANCZOS)


@template("logo-reveal", "image/logo reveal: ring burst, bounce-in, light shine sweep", dur=3.5, image="", width=700, color=YEL)
def _(t, d, p):
    c = blank(); dr = ImageDraw.Draw(c); logo = load_img(p.s("image"), p.f("width")); cx, cy = W / 2, H * 0.45; ex = 1 - in_out((t - (d - 0.35)) / 0.35)
    if 0 < t < 1.1:
        k = out_cubic(t / 1.1); r = S(120 + 520 * k); dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=rgb(p.c("color"), int(255 * (1 - k))), width=int(S(24 * (1 - k) + 3)))
    k = out_elastic((t - 0.2) / 0.9); paste(c, logo, cx, cy, k, (1 - clamp(k)) * -12, ex * clamp((t - 0.2) / 0.1))
    sh = (t - 1.1) / 0.6
    if 0 < sh < 1:
        band = Image.new("L", logo.size, 0); bd = ImageDraw.Draw(band); x = -logo.width * 0.3 + sh * logo.width * 1.6
        bd.polygon([(x, 0), (x + logo.width * 0.18, 0), (x + logo.width * 0.18 - logo.height * 0.4, logo.height), (x - logo.height * 0.4, logo.height)], fill=200)
        white = Image.new("RGBA", logo.size, (255, 255, 255, 255)); white.putalpha(ImageChops.multiply(band, logo.getchannel("A"))); paste(c, white, cx, cy, 1, 0, ex)
    return c


@template("sticker-pop", "image pops in like a sticker with wobble, then floats (use PNG with transparency)", dur=3.5, image="", width=760)
def _(t, d, p):
    c = blank(); im = load_img(p.s("image"), p.f("width")); cx, cy = W / 2, H * 0.45; k = out_back(t / 0.45, 2.4); wob = math.sin(t * 7) * 3 * decay(t, 0.3, 0.7); fl = math.sin(t * 2.4) * S(18) if t > 0.7 else 0; ex = 1 - in_out((t - (d - 0.35)) / 0.35)
    sh = im.getchannel("A").filter(ImageFilter.GaussianBlur(S(18))).point(lambda v: int(v * 0.5)); shd = Image.new("RGBA", im.size, (0, 0, 0, 0)); shd.putalpha(sh)
    paste(c, shd, cx + S(12), cy + fl + S(26), k, wob, ex); paste(c, im, cx, cy + fl, k, wob, ex); return c


@template("before-after", "before/after wipe with moving divider (needs before= and after= images)", dur=4.0, before="", after="", color=YEL)
def _(t, d, p):
    c = Image.new("RGBA", (W, H), (0, 0, 0, 255)); a = Image.open(p.s("after")).convert("RGBA"); b = Image.open(p.s("before")).convert("RGBA")
    def fit(im): return ImageChops.offset(Image.new("RGBA", (W, H), (0, 0, 0, 255)), 0, 0) if False else Image.composite(im.resize((W, H), Image.LANCZOS), Image.new("RGBA", (W, H), (0, 0, 0, 255)), im.resize((W, H), Image.LANCZOS).getchannel("A"))
    A, B = fit(a), fit(b); x = W * (0.5 + 0.38 * math.sin((t / d) * math.pi * 2 - math.pi / 2) * 1.0) if t > 0.4 else W * 0.5
    c.alpha_composite(A); crop = B.crop((0, 0, int(x), H)); c.alpha_composite(crop, (0, 0)); dr = ImageDraw.Draw(c)
    dr.rectangle((x - S(5), 0, x + S(5), H), fill=rgb(p.c("color"))); dr.ellipse((x - S(44), H / 2 - S(44), x + S(44), H / 2 + S(44)), fill=rgb(p.c("color")))
    paste(c, text_sprite("BEFORE", 54, WHITE, 6), S(160), H * 0.08); paste(c, text_sprite("AFTER", 54, WHITE, 6), W - S(150), H * 0.08); return c


@template("slideshow", "images (comma list) with Ken-Burns zoom and crossfades; full-frame video", dur=6.0, images="", fade=0.4)
def _(t, d, p):
    paths = [x for x in p.s("images").split(",") if x]; n = len(paths); seg = d / n; i = min(n - 1, int(t / seg)); lt = t - i * seg
    def frame(idx, lt):
        im = Image.open(paths[idx]).convert("RGB"); sc = max(W / im.width, H / im.height) * (1.0 + 0.12 * lt / seg); im = im.resize((int(im.width * sc), int(im.height * sc)), Image.BICUBIC)
        return im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H)).convert("RGBA")
    c = frame(i, lt); f = p.f("fade")
    if i > 0 and lt < f: c = Image.blend(frame(i - 1, seg + lt), c, lt / f)
    return c


# ================================================================== runner
def render(name, out, dur=None, bg=None, size=None, params=None, still=None):
    global W, H
    spec = REG[name]
    if size: W, H = [int(x) for x in size.lower().split("x")]
    prm = dict(spec["defaults"]); prm.update(params or {}); pp = P(prm); d = dur or spec["dur"]; n = int(d * FPS)
    transparent = out.endswith(".mov") and bg is None
    if still is not None:
        f = spec["fn"](still, d, pp); (Image.alpha_composite(Image.new("RGBA", f.size, rgb(bg) if bg else (16, 16, 22, 255)), f) if bg or not transparent else f).save(out); return
    if transparent:
        enc = ["-c:v", "qtrle", "-pix_fmt", "argb"]
    else:
        enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"]
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"] + enc + [out], stdin=subprocess.PIPE)
    base = Image.new("RGBA", (W, H), rgb(bg)) if bg else None
    for i in range(n):
        f = spec["fn"](i / FPS, d, pp)
        if base is not None: f = Image.alpha_composite(base, f)
        ff.stdin.write(np.asarray(f).tobytes())
    ff.stdin.close(); ff.wait()
    if ff.returncode: sys.exit(f"render failed for {name}")


def overlay(video, mg, out, at=0.0, x="0", y="0"):
    from reel_tools import has_audio, run  # noqa: E402
    g = f"[1:v]format=rgba,setpts=PTS-STARTPTS+{at}/TB[o];[0:v][o]overlay={x}:{y}:eof_action=pass,format=yuv420p[v]"
    cmd = ["ffmpeg", "-y", "-i", video, "-i", mg, "-filter_complex", g, "-map", "[v]"] + (["-map", "0:a"] if has_audio(video) else [])
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"] + (["-c:a", "copy"] if has_audio(video) else []) + [out])


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for k, v in REG.items():
            dflt = " ".join(f"{a}={b!r}" for a, b in v["defaults"].items())
            print(f"{k:16s} {v['doc']}  [{v['dur']}s]\n{'':16s} params: {dflt}")
        print(f"\n{len(REG)} templates"); return
    if len(sys.argv) > 1 and sys.argv[1] == "overlay":
        ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("video"); ap.add_argument("mg"); ap.add_argument("out")
        ap.add_argument("--at", type=float, default=0.0); ap.add_argument("--x", default="0"); ap.add_argument("--y", default="0")
        a = ap.parse_args(); overlay(a.video, a.mg, a.out, a.at, a.x, a.y); print(a.out); return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("template"); ap.add_argument("out"); ap.add_argument("--dur", type=float); ap.add_argument("--bg")
    ap.add_argument("--size"); ap.add_argument("--p", action="append", default=[]); ap.add_argument("--still", type=float, help="render one PNG frame at this time")
    a = ap.parse_args()
    if a.template not in REG: sys.exit(f"unknown template. `mg.py list` shows all.")
    render(a.template, a.out, a.dur, a.bg, a.size, dict(x.split("=", 1) for x in a.p), a.still); print(a.out)


if __name__ == "__main__":
    main()
