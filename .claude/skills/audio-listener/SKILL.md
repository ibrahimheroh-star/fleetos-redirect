---
name: audio-listener
description: Lets Claude "hear" audio by transcribing speech to text and by measuring music/non-speech sound — voice notes (WhatsApp/Telegram .opus/.ogg/.m4a), recordings, meetings, calls, podcasts, songs, background music, and the soundtrack of videos (.mp4/.mov/.webm, YouTube links). Use this skill whenever the user sends or mentions an audio or video file, a voice message, "فويس", "تسجيل صوتي", "اسمع", "فرّغ", "حوّل الصوت لنص", "شو بيقول هالفيديو", "شو نوع هالموسيقى", "شو إيقاع/مقام هالأغنية", or asks to transcribe, summarize, translate, pull action items from anything spoken, or describe/identify music — even if they never say the word "transcribe". Claude cannot natively listen to audio, so reach for this skill before telling the user you can't process it.
---

# Audio Listener

Claude can't ingest raw audio. The workaround is a pipeline: **extract the audio → transcribe it → reason over the text**. This skill picks the best available transcription route and handles messy real-world input (WhatsApp voice notes, long videos, Arabic dialects).

## Step 1 — Get the audio into a local file

- Attached/local file: use its path.
- YouTube link: first try the `vidiq_video_transcript` MCP tool (instant, no download). If unavailable or the video has no captions, try `yt-dlp -x --audio-format mp3 -o "<scratch>/%(id)s.%(ext)s" URL`.
- Other URLs: `curl -L -o <scratch>/input.<ext> URL` (respect the sandbox proxy notes in the environment).
- If there is no file and nothing downloadable, ask the user to attach it — don't guess at content.

## Step 2 — Normalize with ffmpeg

```bash
python <skill-dir>/scripts/prepare_audio.py INPUT --out <scratch>/audio
```

This strips video, converts to mono 16 kHz, and splits long files into 10‑minute chunks (many APIs cap upload size, and chunking keeps local models from running out of memory). It prints JSON with the ordered `chunks`. Use `--format mp3` if the chosen backend wants a smaller upload. A "no audio stream" error means the video is silent — tell the user rather than inventing content.

## Step 2b — Speech or music?

Decide before transcribing, because speech models fed music don't fail loudly — they hallucinate fluent text (repeated phrases, "thanks for watching", random lyrics). Run `analyze_music.py` on the first chunk (a few seconds is enough) and read `speech_likelihood_0_1`, or just ask the user if it's obvious from context.

- Mostly speech → Step 3.
- Music/no speech → jump to **Step 3m** below. Don't transcribe it.
- Song with vocals → do both: Step 3m for the musical facts, Step 3 for lyrics (expect errors on sung words; mark them unclear).
- Transcript came back empty, looping, or implausible → treat it as music/noise and say so.

## Step 3m — Describing music and non-speech sound

```bash
pip install -q librosa     # once
python <skill-dir>/scripts/analyze_music.py CHUNK --sections 8
```

You get tempo (BPM), estimated key/mode, loudness, brightness, percussive share, and a per-section loudness timeline. Turn those numbers into a plain description: e.g. "~120 BPM, minor key, steady drums, gets louder halfway". Be upfront that this is measurement, not listening: tempo can be double/half, and key detection is shaky on non-Western scales (maqam, quarter tones) and on dense mixes. It cannot reliably name instruments, genre, mood, or lyrics' meaning on its own — offer a cautious guess from the numbers and label it as a guess.

To **identify a song** (name/artist), analysis can't do it — that needs audio fingerprinting. Use a connected fingerprint tool if there is one (e.g. via the Composio `insta` MCP search for a recognition tool), or ask the user for any metadata, the video's description, or the platform's "music" tag. Never invent a title.

For a video where the music matters, also look at the video's own metadata/description, which often names the track.

## Step 3 — Transcribe speech (pick the first route that works)

1. **MCP tools already connected** (no setup, best quality for dialects):
   - ElevenLabs `creative_transcribe_audio` — needs the file on a flow first (`creative_attach_reference_file` for a URL, or `creative_create_asset_upload` → PUT bytes → `creative_finalize_asset_upload`), then pass the node as `connect_from`. Poll `creative_get_flow_run_status` until done. This spends the user's credits, so mention it for large files.
   - Speko `audio_transcribe`.
   Load their schemas with ToolSearch first; they are deferred tools.
2. **Local, offline, free** — `faster-whisper`:
   ```bash
   pip install -q faster-whisper          # once
   python <skill-dir>/scripts/transcribe_local.py CHUNK --model small
   ```
   For each later chunk pass `--offset <seconds so far>` so timestamps stay continuous (chunk N starts at N × chunk_seconds). Use `--model medium` or `large-v3` for Arabic dialects, accents, or noisy recordings; `small` is fine for clear speech. Leave `--lang` unset to auto-detect, but set it (`--lang ar`) when you know it — short voice notes are sometimes misdetected.
   The first run downloads the model from huggingface.co. If that returns a proxy `403`, the sandbox network policy blocks the host — use route 1 instead (or the user can allow `huggingface.co`, see the environment network docs).
3. If both fail (no network for model download, no tools), say exactly what blocked you and what the user can do (e.g. paste a transcript, or enable a connector) — don't fabricate a transcript.

## Step 4 — Respond to what the user actually asked

The transcript is raw material, not the deliverable. Match the request:

- "شو بيقول / what does it say" → short faithful summary in the user's language, plus the transcript if brief.
- "فرّغ / transcribe" → full transcript with timestamps; keep the original language unless asked to translate.
- Meetings/calls → summary, decisions, action items with owners if mentioned.
- Voice note asking for something → treat the content as the request and act on it (confirm first if it implies outward-facing or irreversible actions).
- Video → remember you only heard the audio; say so if visual context might matter (on-screen text, demos).

Reply in the language the user wrote to you (Arabic → Arabic, same dialect register where natural).

## Quality notes (why these matter)

- Speech models make mistakes on names, numbers, and dialect words. Flag low-confidence spots as `[غير واضح]` / `[unclear]` instead of smoothing them into plausible-sounding text — a confident wrong quote is worse than a marked gap.
- Mixed Arabic/English (code-switching) is common; keep both as spoken rather than translating mid-sentence.
- Multiple speakers: Whisper doesn't diarize. Don't assign names to speakers unless the content makes it unambiguous; use "متحدث 1/2" only if turn changes are clear.
- Audio of other people is private data: transcribe for the user who supplied it, don't send it to services beyond what the task needs (the local route keeps everything on the machine).
- Clean up scratch audio when finished if the file was sensitive.
