# Spoken reactions (WoW Forever)

When a friend whispers you a reaction (GZ!, F, Congrats! and the personality
lines) in **Nynorsk**, WoW Status on **Forever** can read it aloud in the voice
of the personality that wrote it. The clips are recorded in advance with
Google's Gemini 3.8 Flash TTS; nothing is generated in the game.

- **Receiver:** at most one reaction is read per interval (0–60 minutes,
  1 by default) and clips never overlap. Reactions in between stay text-only
  and are not queued. Options → Notifications → *Spoken reactions* turns it off,
  sets the interval and shows the voice pack link (WoW cannot download files,
  so the link is there to copy).
- **Sender:** in Nynorsk, 90 % of reactions use a recorded line; a quarter of
  those come from the lines that ship inside the addon, so friends without the
  pack hear voices too (`V.VOICED_SHARE` and `V.SAMPLE_SHARE` in
  `addon/shared/Voices.lua`). Nothing extra is sent.
- **Not voiced yet:** "Enjoy <zone>!" lines (no list of Forever zone names to
  record), English lines and Classic reactions.

## Where everything lives

| What | Where | In Git? |
| --- | --- | --- |
| Voices, styles, model and counts | `docs/voices/voices.json` | yes |
| Chosen lines per personality | `docs/voices/selection/<id>.json` | yes |
| Every recorded clip (id, text, length, voice, model) | `docs/voices/clips.json` | yes |
| What the addon can play | `addon/forever/WoWStatus/VoiceData.lua` (generated) | yes |
| Sample clips inside the addon (~100 per personality) | `addon/forever/WoWStatus/Sounds/Voices/<id>.ogg` | yes |
| Full pack for players | GitHub release `voice-pack` → `WoWStatus_Voices.zip` | release |
| Lossless masters (FLAC), one ZIP per personality | GitHub release `voice-pack` → `voices-masters-<id>.zip` | release |
| Working copy of all audio | `dist/voices/clips/*.ogg`, `dist/voices/masters/*.flac` | no (cache) |

Clips are mono Ogg Vorbis at 44.1 kHz (quality 0, about 52 kbps). WoW Forever
stops MP3s under 64 kbps early, at the point where a 64 kbps file would end
(tested in game on 8 November 2026), so do not switch to small MP3s.
`reencode` rebuilds every clip from its lossless master after a format change.

A clip's id comes from its personality, kind and exact Nynorsk text, so the
same line always has the same file and an edited line gets a new one. Your own
computer only holds a cache: `restore` fetches the published audio again.

Level lines are recorded up to the number ("Skål for nivå") and the number is a
clip of its own ("trettisju!"), played 0.12 s later. Only lines that end with
their level are chosen for this.

## Setup (any computer)

1. Clone the repository and create `.venv` as in `AGENTS.md`.
2. Install `ffmpeg` and the GitHub CLI, then `gh auth login` with an account
   that can write releases in the repository.
3. Put `GOOGLE_API_KEY=…` in the repository's `.env` (ignored by Git). An
   AI Studio key works. A Git worktree also reads the main checkout's `.env`.

## Adding or re-recording voices

```sh
python scripts/voices.py restore            # on a fresh computer: fetch the published audio
python scripts/voices.py select             # choose lines; earlier choices are kept
python scripts/voices.py generate --dry-run # how many clips, how long, what it costs
python scripts/voices.py generate           # record only what is missing (about $0.75 per 1,000 lines)
python scripts/voices.py sample             # copy the sample clips into the Forever addon
python scripts/voices.py build              # write VoiceData.lua
python scripts/voices.py release            # upload a new draft pack (voice-pack-vN)
# listen to the draft, then:
python scripts/voices.py publish N          # make it the current pack
```

Commit `docs/voices/`, `VoiceData.lua` and `Sounds/Voices/` after `publish`.
Players with an older pack simply hear the newer lines as text.

- **More lines:** raise `lines_per_kind` (and `level_lines`) in `voices.json`
  and run the steps above. Only new lines are recorded.
- **A different voice or style:** change `voices.json`, delete that
  personality's entries from `clips.json` and generate again. Clips keep the
  voice and model they were recorded with until then.
- **One computer at a time:** `release` refuses when a newer pack exists than
  the one `clips.json` was built on; pull, run `restore` and try again.

## Checks

`tests/test_voices.py` covers choosing, recording only missing clips, packing
and the committed `VoiceData.lua` (it must match the choices, records and
sample files: run `build` after `sample`). `tests/test_spoken_reactions.py`
covers playback, the interval, the pack, level numbers, sender weighting and
the settings. Neither proves the clips sound right or that the Forever client
plays them: listen to the draft and check in game.
