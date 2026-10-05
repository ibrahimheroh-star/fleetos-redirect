# Sound design for short-form video

Sound is half the edit. A flat video with good SFX feels more expensive than a pretty one without. Read this
before placing effects. Commands: `pro_fx.py sfx-list` (see what is bundled) and
`pro_fx.py sfx-mix IN OUT --cue TIME:NAME:DB ...`.

## Core rules (from pro guides)
1. **Whoosh = movement.** Under every styled transition, text slide, or fast camera move. Keep it low
   (about -18 to -24 dB under dialogue): felt more than heard. Shorter and softer = subtle; longer and brighter = flashy.
2. **Impact/hit = weight.** On a title reveal, a punch-in, a beat drop, or just after a whoosh to "button" the cut.
3. **Riser = anticipation.** Build into the hook, a reveal, or the drop. Align the riser's **peak** with the key
   visual moment; riser then whoosh/hit is the classic complete transition.
4. **Land it on the cut.** Offset the effect so its peak/end meets the cut instead of starting on it. `sfx-mix` starts
   a sound AT the time you give, so start a 0.45 s whoosh about 0.2-0.3 s BEFORE the cut and an impact exactly ON it.
5. **Layer.** A bright transient (tick/click) on top of a low boom gives cinematic punch. Two or three small layers
   beat one loud sound.
6. **Less is more.** Roughly one effect per visual event, not per word. Over-SFX-ed videos sound cheap. Leave breathing
   room in the quiet parts so the hits land.
7. **Voice stays king.** Keep voice around -14 LUFS final; music about -24 dB under speech; SFX peaks never above the voice.
8. **Silence is an effect.** A 0.2-0.4 s dip before a big hit makes it hit harder (drop the music/SFX bed just before).

## Which sound for which moment

| Moment | Use | Level (gain in `--cue`) |
|---|---|---|
| Normal cut between clips | `whoosh_short` or `swish_fast`, start 0.2 s before cut | -18 to -22 |
| Topic change / bigger transition | `whoosh_medium` + `impact_hit` on the cut | -18 / -12 |
| Slide / zoom transition | `whoosh_rise` (zoom in/up), `whoosh_fall` (out/down) | -18 |
| Punch-in zoom on emphasis | `hit_snap` or `pop`; or `impact_hit` for big ones | -14 to -18 |
| Hook / opening line | `riser_short` ending on the first word + `impact_hit` | -18 / -12 |
| Big reveal / drop | `reverse_hit` ending on the cut, then `boom_sub` or `impact_heavy` (+ `shake`) | -16 / -10 |
| Text/caption pops, stickers, bullets | `pop`, `pop_soft`, `tick`, `click` | -16 to -20 |
| Typing / screen text | `keyboard_key` repeated every 0.08-0.12 s | -20 |
| Photo / "screenshot" moment | `camera_shutter` | -14 |
| Number goes up / success | `ding`, `success_chime` | -16 |
| Mistake / wrong / "don't" | `error_buzz`, `record_scratch` | -14 |
| Tech / hype / scene glitch | `glitch_short`, `glitch_long`, `digital_zap`, `laser` | -16 |
| Dramatic emphasis / tension | `tension_drone` underneath, `heartbeat`, `sub_drop` | -22 / -20 / -14 |
| Retro / nostalgic texture | `vinyl_crackle` under music | -30 |

## Bundled library (34 files in `assets/sfx/`, peak-normalised to -3 dB)
Whooshes: `whoosh_short`, `whoosh_medium`, `whoosh_long`, `swish_fast`, `whoosh_rise`, `whoosh_fall`.
Impacts: `impact_hit`, `impact_heavy`, `boom_sub`, `sub_drop`, `hit_snap`, `stinger_cinematic`.
Risers/builds: `riser_short`, `riser_long`, `tension_drone`, `reverse_hit`.
UI/pop: `pop`, `pop_soft`, `click`, `tick`, `keyboard_key`, `camera_shutter`, `ding`, `success_chime`, `error_buzz`, `notification`.
Glitch/digital: `glitch_short`, `glitch_long`, `digital_zap`, `record_scratch`, `laser`.
Texture: `swoosh_air`, `vinyl_crackle`, `heartbeat`.

These are **synthesised** (noise + sine sweeps + envelopes by `scripts/make_sfx.py`), so they are original and free to
use commercially with no attribution. They are clean and functional, not recorded. For hero moments (the
main hook hit, a signature whoosh) a real recorded sample sounds richer, so use the libraries below when the user can
download from them. Regenerate or tweak with `python scripts/make_sfx.py`.

## Where to get more (real recordings, free)
Check each site's current licence before commercial use or client work.
- [Pixabay Sound Effects](https://pixabay.com/sound-effects/): large library, no attribution required, MP3 download.
- [Mixkit free sound effects](https://mixkit.co/free-sound-effects/): free for commercial and personal projects without attribution.
- [BigSoundBank](https://bigsoundbank.com/): 3,500+ free sounds, no attribution required.
- [Sonniss GameAudioGDC](https://sonniss.com/gameaudiogdc/): big royalty-free professional archive from game audio.
- [Freesound](https://freesound.org/): huge; licences vary per sound (CC0 vs CC-BY needing credit), so filter by CC0.
- Packs and guides: [MixClap transition SFX pack](https://www.mixclap.com/en/blog/transition-sound-effects), [YouTubeSFX free pack](https://youtubesfx.com/free-sfx-pack/), [Pixabay guide to editing SFX](https://pixabay.com/blog/posts/free-and-high-quality-sound-effects-for-video-edit-453/).
Save downloads into a folder and pass either the path or `--sfx-dir` to `sfx-mix`. Never use copyrighted tracks/sounds
ripped from other videos on monetised content.

## Sources for the rules above
[FlexClip: 9 cinematic transition SFX](https://www.flexclip.com/learn/transition-sound-effects.html),
[Ocular Sounds: whoosh audio effect](https://ocularsounds.com/blogs/sound-design-tips-tricks/whoosh-audio-effect-adding-motion-and-energy-to-your-edits),
[DL-Sounds: whoosh effects](https://www.dl-sounds.com/whoosh-sound-effects/),
[Filmora: adding whoosh effects](https://filmora.wondershare.com/audio-editing-tips/whoosh-sound-effect.html),
[Epidemic Sound: risers](https://www.epidemicsound.com/sound-effects/categories/designed/riser/).
