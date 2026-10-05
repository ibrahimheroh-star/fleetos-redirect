#!/usr/bin/env python3
"""ffmpeg helpers for vertical short-form video editing (Reels / TikTok / Shorts)."""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

W, H = 1080, 1920
ARABIC_FONTS = ["Noto Sans Arabic", "Noto Naskh Arabic", "Cairo", "Tajawal", "Amiri", "DejaVu Sans"]


def run(cmd, capture=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg/ffprobe failed:\n{' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r


def probe_data(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]).stdout
    return json.loads(out)


def has_audio(path):
    return any(s["codec_type"] == "audio" for s in probe_data(path)["streams"])


def cmd_probe(a):
    d = probe_data(a.input)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    dur = float(d["format"]["duration"])
    size_mb = int(d["format"]["size"]) / 1e6
    print(f"duration: {dur:.2f}s   size: {size_mb:.1f} MB")
    if v:
        num, den = v["r_frame_rate"].split("/")
        print(f"video: {v['width']}x{v['height']}  {float(num)/float(den):.2f} fps  {v['codec_name']}")
        print("vertical: " + ("yes" if v["height"] > v["width"] else "no (needs reframe)"))
    print("audio: " + (f"{au['codec_name']} {au.get('sample_rate','?')} Hz" if au else "none"))


def enc(out, crf=18):
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]


def cmd_trim(a):
    cmd = ["ffmpeg", "-y", "-i", a.input, "-ss", str(a.start)]
    if a.end:
        cmd += ["-to", str(a.end)]
    run(cmd + enc(a.output))
    print(a.output)


def cmd_cut_silence(a):
    if not has_audio(a.input):
        sys.exit("No audio stream, nothing to detect.")
    dur = float(probe_data(a.input)["format"]["duration"])
    r = subprocess.run(["ffmpeg", "-i", a.input, "-af",
                        f"silencedetect=noise={a.threshold}:d={a.min_silence}", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    if len(ends) < len(starts):
        ends.append(dur)
    keep, cur = [], 0.0
    for s, e in zip(starts, ends):
        s_pad, e_pad = s + a.pad, e - a.pad
        if s_pad > cur:
            keep.append((cur, s_pad))
        cur = max(cur, e_pad)
    if cur < dur:
        keep.append((cur, dur))
    keep = [(s, e) for s, e in keep if e - s > 0.15]
    if not keep:
        sys.exit("Everything looked like silence; try a lower --threshold (e.g. -45dB).")
    parts = []
    for i, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}];"
                     f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(keep)))
    fc = ";".join(parts) + f";{cat}concat=n={len(keep)}:v=1:a=1[v][a]"
    run(["ffmpeg", "-y", "-i", a.input, "-filter_complex", fc, "-map", "[v]", "-map", "[a]"] + enc(a.output))
    new = sum(e - s for s, e in keep)
    print(f"{a.output}  ({dur:.1f}s -> {new:.1f}s, {len(keep)} segments kept)")


def cmd_reframe(a):
    if a.mode == "crop":
        # x_offset in [-1,1]: shift the crop window away from centre
        fc = (f"[0:v]scale=-2:{H},crop={W}:{H}:(in_w-{W})/2*(1+({a.x_offset})):0,setsar=1[v]")
    elif a.mode == "blur":
        fc = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"boxblur=30:5,eq=brightness=-0.08[bg];[b]scale={W}:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
    else:
        fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[v]")
    cmd = ["ffmpeg", "-y", "-i", a.input, "-filter_complex", fc, "-map", "[v]"]
    if has_audio(a.input):
        cmd += ["-map", "0:a"]
    run(cmd + ["-r", "30"] + enc(a.output))
    print(a.output)


def pick_font(requested):
    if requested:
        return requested
    try:
        fams = subprocess.run(["fc-list", ":lang=ar", "family"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        fams = ""
    for f in ARABIC_FONTS:
        if f.lower() in fams.lower():
            return f
    return "DejaVu Sans"


def cmd_subs(a):
    font = pick_font(a.font) if a.lang == "ar" else (a.font or "Arial")
    tmp = tempfile.mkdtemp()
    ass = os.path.join(tmp, "s.ass")
    # Convert SRT -> ASS ourselves and write the header/style explicitly. Relying on the
    # subtitles filter's force_style + PlayRes scaling silently dropped Arabic cues in testing.
    run(["ffmpeg", "-y", "-i", a.srt, ass])
    text = open(ass, encoding="utf-8").read()
    style = (f"Style: Default,{font},{a.size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
             f"1,0,0,0,100,100,0,0,1,4,0,2,60,60,{int(H*0.18)},1")
    text = re.sub(r"(?m)^PlayResX:.*$", f"PlayResX: {W}", text)
    text = re.sub(r"(?m)^PlayResY:.*$", f"PlayResY: {H}", text)
    text = re.sub(r"(?m)^Style: Default,.*$", lambda m: style, text)
    open(ass, "w", encoding="utf-8").write(text)
    cmd = ["ffmpeg", "-y", "-i", os.path.abspath(a.input), "-vf", "ass=s.ass", "-map", "0:v"]
    if has_audio(a.input):
        cmd += ["-map", "0:a"]
    cmd += enc(os.path.abspath(a.output))
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp)  # cwd=tmp avoids filter-path escaping
    if r.returncode != 0:
        sys.exit(r.stderr[-1500:])
    print(f"{a.output}  (font: {font})")


def cmd_loudnorm(a):
    run(["ffmpeg", "-y", "-i", a.input, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy",
         "-ar", "48000", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", a.output])
    print(a.output)


def cmd_mix_music(a):
    vol = f"volume={a.music_db}dB"
    if has_audio(a.input):
        fc = (f"[1:a]{vol},aloop=loop=-1:size=2e9[m];"
              f"[m][0:a]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=400[duck];"
              f"[0:a][duck]amix=inputs=2:duration=first:normalize=0[a]")
    else:  # silent video: the music becomes the soundtrack (looped/trimmed to the video length) with short fades
        dur = float(probe_data(a.input)["format"]["duration"])
        fc = f"[1:a]{vol},aloop=loop=-1:size=2e9,atrim=0:{dur:.3f},afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 0.6):.3f}:d=0.6[a]"
    run(["ffmpeg", "-y", "-i", a.input, "-i", a.music, "-filter_complex", fc,
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-shortest", "-movflags", "+faststart", a.output])
    print(a.output)


def cmd_frame(a):
    run(["ffmpeg", "-y", "-ss", str(a.at), "-i", a.input, "-frames:v", "1", "-q:v", "2", a.output])
    print(a.output)


def cmd_export(a):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    cmd = ["ffmpeg", "-y", "-i", a.input, "-vf", vf, "-r", "30"]
    run(cmd + enc(a.output, crf=a.crf))
    print(a.output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("probe"); s.add_argument("input"); s.set_defaults(f=cmd_probe)

    s = sp.add_parser("trim"); s.add_argument("input"); s.add_argument("output")
    s.add_argument("--start", type=float, default=0); s.add_argument("--end", type=float)
    s.set_defaults(f=cmd_trim)

    s = sp.add_parser("cut-silence"); s.add_argument("input"); s.add_argument("output")
    s.add_argument("--threshold", default="-35dB"); s.add_argument("--min-silence", type=float, default=0.4)
    s.add_argument("--pad", type=float, default=0.12); s.set_defaults(f=cmd_cut_silence)

    s = sp.add_parser("reframe"); s.add_argument("input"); s.add_argument("output")
    s.add_argument("--mode", choices=["crop", "blur", "fit"], default="crop")
    s.add_argument("--x-offset", type=float, default=0.0, help="-1 (left) .. 1 (right), crop mode only")
    s.set_defaults(f=cmd_reframe)

    s = sp.add_parser("subs"); s.add_argument("input"); s.add_argument("srt"); s.add_argument("output")
    s.add_argument("--lang", choices=["ar", "en"], default="ar"); s.add_argument("--font")
    s.add_argument("--size", type=int, default=64, help="font size in px on the 1080x1920 canvas")
    s.set_defaults(f=cmd_subs)

    s = sp.add_parser("loudnorm"); s.add_argument("input"); s.add_argument("output"); s.set_defaults(f=cmd_loudnorm)

    s = sp.add_parser("mix-music"); s.add_argument("input"); s.add_argument("music"); s.add_argument("output")
    s.add_argument("--music-db", type=float, default=-14, help="music gain before ducking"); s.set_defaults(f=cmd_mix_music)

    s = sp.add_parser("frame"); s.add_argument("input"); s.add_argument("output")
    s.add_argument("--at", type=float, default=1.0); s.set_defaults(f=cmd_frame)

    s = sp.add_parser("export"); s.add_argument("input"); s.add_argument("output")
    s.add_argument("--crf", type=int, default=20); s.set_defaults(f=cmd_export)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
