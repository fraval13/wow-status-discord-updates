# Voiced reactions: research (8 November 2026)

> **What was built:** see [docs/voices/README.md](voices/README.md). Exact
> received lines are read aloud (not barks), Forever and Nynorsk only, about
> 1,000 lines per personality (100 inside the addon, the rest in a GitHub
> release pack), at most one per 0–60 minute interval, and level numbers
> stitched on. Zone lines are not voiced yet. This file is the research record
> that led there; parts of it (barks, pack hosting on the server) were not
> chosen.

Question: how could the friend who *receives* a reaction (GZ!, F, Congrats! and
the personality lines matched in `J.reaction`, `addon/shared/Journal.lua`) hear
it spoken? Options compared: the game's own text-to-speech (TTS), AI voice clips
made in the cloud, AI voice clips made on the owner's M3 Mac (36 GB), and a mix.

Research only: nothing was installed, generated or tested in a game client.
Labels: **[src]** checked in Blizzard's UI source or a primary vendor or model
page; **[2nd]** a secondary source such as warcraft.wiki.gg or a forum;
**[est]** my own estimate, with the arithmetic shown.

## Recommendation in short

1. **Ship short, pre-recorded "barks" in each personality's voice, not every
   line.** A bark is a short in-character shout ("GZ!", "Gratulerer!", a
   goblin cackle, a dwarf "Aye!") played when a reaction arrives, while the
   full line still shows as text. About 1,000 clips fit the size budget;
   97,200 full-line clips do not (see the budget section).
2. **Offer the full line through the game's own TTS as an opt-in.** It costs
   nothing in size and reads every line, including `{zone}` and `{level}`. But
   it sounds robotic, and no operating system ships a Nynorsk voice.
3. **Choose the engine by testing, not by reputation.** Nynorsk is the main
   quality risk for every engine. Test about 20 Nynorsk barks on four
   candidates, score them automatically with NB-Whisper, then have native
   speakers listen (see the verification plan).
4. Leading candidates:
   - Self-hosted: **VoxCPM2**. Apache-2.0, lists Norwegian, and can design a
     voice from a text description with no reference recording.
   - Cloud: **Google Gemini-TTS**. The only large vendor that lists
     `nn-NO` (Nynorsk), in Preview, and its delivery can be steered with plain
     instructions.
   - Character voice quality: **ElevenLabs Voice Design**, but it lists only
     "Norwegian", not Nynorsk.

## What the receiver has today [src: this repo]

- `Journal.lua:1327-1329` listens for `CHAT_MSG_WHISPER` and calls
  `J.reaction(text, sender)`.
- `J.reaction` accepts a whisper only if the sender is a group member, it
  arrives within 900 s (`REACTION_WINDOW`), and it matches one of the
  receiver's own events. Each event holds at most 20 reactions. These rules
  already limit how often a voice could play.
- `P.matchReaction(text)` (`Personalities.lua:193`) returns the reaction
  **kind** ("gz", "f", "congrats_loot", …) but not which personality the line
  came from. A voice needs that, so the matcher must also return the
  personality id, plus the line index if full lines are voiced. Of the 97,200
  strings, 96,865 are unique. The few shared ones (such as plain "GZ!") need a
  fallback voice.
- Lines with a slot: all 2,700 `level` pairs contain `{level}` and all 2,700
  `enjoy` pairs contain `{zone}`. A recording cannot contain the zone name or
  level number, which is one more reason to use barks or in-game TTS.
- If the receiver runs an older addon version, a new line will not match. The
  voice then has to fall back to a bark for the kind, or stay silent.
- In Retail, chat messages can be "secret" (unreadable to addons) during chat
  lockdown, for example in instances. `S.string` then yields nothing, so the
  reaction is ignored and nothing plays. That is the right quiet behaviour.
- Previews must never play real voices. Previews may play a local sample, but
  that path must stay separate from the receive path.

## The size problem

Corpus (`docs/caption-personalities/*/reactions/*.json`, measured):

- 9 personalities × 18 kinds × 300 lines = **48,600 English/Nynorsk pairs**,
  which is **97,200 clips**, **4,417,227 characters** and 810,888 words.
- Words per line: mean 8.3, median 8, 95th percentile 13, maximum 21.
- Audio [est]: 810,888 words ÷ 2.5–3 words per second, plus 0.3 s of padding
  per clip, comes to **83–98 hours**. That is about 3.1–3.6 s per clip.

Hard budgets [src: this repo]:

- The deploy receiver accepts **at most 64 MiB** (`deploy/make_release.py`,
  commit 3a50148). That archive contains the built homepage, which holds
  **all four edition ZIPs**. So each MB of audio in an edition ZIP costs about
  4 MB of that 64 MiB, unless the audio ships as one separate voice-pack
  download.
- `scripts/build_homepage.py` packages only the TOC, the files it lists and
  `Textures/*.tga`. A `Sounds/` folder needs a change to the builder (and its
  tests and the verifier).
- CurseForge: no official file-size limit found [could not verify].

Size by scope [est; mono Ogg Vorbis at 48 kbps is about 6 KB/s, plus about
4 KB of Vorbis header per file]:

| Scope | Clips | Audio | Per edition ZIP | Fits? |
|---|---|---|---|---|
| (a) every line, both languages | 97,200 | ~90 h | ~2 GB | No |
| (b) 10 lines per kind per personality, both languages | 3,240 | ~3 h | ~65 MB | Only as a separate optional voice pack, and even then near the deploy limit |
| (c) 3 barks per kind per personality, both languages | 972 | ~20 min at ~1.2 s each | ~11 MB | Yes as a voice pack. Tight inside all four ZIPs (~44 MB of the 64 MiB). |
| (c′) 1 language-neutral bark per kind per personality (GZ!/F/Aye!) | 162 | ~4 min | ~2 MB | Yes, even inside each ZIP |

There is a well-known precedent for scopes (b) and (c): **Deadly Boss Mods
ships its spoken alerts as separate, optional "voice pack" addons** [2nd,
general knowledge, not re-checked]. One edition-neutral pack (a
`WoWStatus_Voices` addon with one TOC per edition) would keep the main ZIPs
unchanged.

Voicing only a subset of full lines (scope b) has a catch. The sender picks
at random from 300 lines, so with 10 lines voiced, only about 3% of incoming
reactions would match a recording. Barks avoid this: the receiver only needs
(personality, kind), not the exact line.

## The game's own TTS [src: wow-ui-source, all four branches]

Checked in shallow clones of Gethe/wow-ui-source: `classic_era` 1.15.9,
`classic_anniversary` 2.5.6, `forever` 1.60.1, `live` 12.1.5.

- `C_VoiceChat.SpeakText(voiceID, text, rate, volume, overlap=false)` has the
  **same signature in all four**. The old `destination` argument is gone.
  - Retail and Forever mark it `SecretArguments = "AllowedWhenTainted"`, so
    addon code may call it. It is not protected and not covered by chat
    lockdown.
  - Blizzard's own `TextToSpeechFrame.lua:178` calls it with
    `C_TTSSettings.GetSpeechRate()` and `GetSpeechVolume()`.
- Supporting functions exist in all four:
  - `C_VoiceChat.GetTtsVoices()` returns `{voiceID, name}`.
  - `StopSpeakingText`.
  - Events `VOICE_CHAT_TTS_PLAYBACK_STARTED/FINISHED/FAILED` carry an
    `utteranceID`. Retail notes that utterances stopped early never fire
    FINISHED.
  - `C_TTSSettings.GetVoiceOptionID`.
- **Blizzard already offers whisper narration.** `TextToSpeechFrame.lua`
  includes `CHAT_MSG_WHISPER` among the chat types it can read aloud, in all
  four branches. So a player can already hear reactions spoken by turning on
  the game's TTS for whispers, with no addon code. Anything we build should
  sound clearly better than that.
- Voices come from the operating system:
  - Windows uses SAPI voices. Microsoft's Norwegian "Jon" is a OneCore voice
    and may not show up in WoW [2nd].
  - macOS has "Nora" (nb-NO) as an optional download [2nd].
  - Both are **Bokmål**. **No operating system Nynorsk voice was found.**
- Character [est]: picking a different installed voice and speech rate per
  personality gives some variety, but not a goblin or a bard.

## Pre-recorded clips: how playback works

- `PlaySoundFile(path or fileID, channel)` returns `willPlay, handle` [2nd:
  warcraft.wiki.gg]. Channels: Master, SFX, Music, Ambience, **Dialog**,
  Talking Head.
  - Blizzard's own code calls it in era and anniversary [src]. Forever and
    Retail have no Blizzard call site or documentation for it [src].
  - Addons use it widely there, but that is **not verified** for those two
    clients.
- The Dialog volume CVars `Sound_DialogVolume` and `Sound_EnableDialog` exist
  in all four [src]. Playing on "Dialog" lets players use their normal voice
  slider.
- Formats: Ogg Vorbis (not Opus) and MP3; 44.1 kHz recommended [2nd: MySounds
  on CurseForge].
- **New sound files are only seen after a full client restart; `/reload` is
  not enough** [2nd: several addon authors; no Blizzard statement]. So a voice
  pack update needs a restart, and the addon must cope with missing files
  (`willPlay` nil means skip quietly).
- Pipeline [est]:
  1. Generate a WAV for each bark id `<personality>_<kind>_<n>_<lang>`.
  2. Run `ffmpeg -af loudnorm=I=-18:TP=-2:LRA=7`, then trim silence.
  3. Encode mono Ogg Vorbis at about 48 kbps, 44.1 kHz.
  4. Write a Lua manifest (`WoWStatusVoices = {bard = {gz = {...}}}`), built
     the same way `build_personalities.py` builds the caption banks.
- The −18 LUFS target is a starting point. Match it by ear to WoW's own NPC
  dialogue at equal slider settings.

## Self-hosted on the M3 Mac (36 GB)

None of these was run. Speeds are published figures or labelled estimates.

| Model | Nynorsk | Character voices | Licence | Apple Silicon | Published speed |
|---|---|---|---|---|---|
| **VoxCPM2** (2B) | "Norwegian" among 30 languages [src]. Nynorsk not mentioned. Reported Norwegian WER 2.49% [src: README]. | Voice design from a text description, cloning from a short clip | Apache-2.0 [src] | MPS, llama.cpp-omni Metal, mlx-audio | **RTF ~1.76 on an M4 Pro** (Q8_0, Metal) [src: README l.358], i.e. slower than real time |
| **Chatterbox Multilingual v3** (500M) | "Norwegian" among 23 | Zero-shot cloning; `exaggeration` control | MIT; output is watermarked (Perth) | MPS, MLX ports | None for Apple. The README is reported to call the project retired [not re-checked]. |
| **OmniVoice** (0.6B) | **Explicit `nn`, but only 1.54 h of training data** (Bokmål 12.7 h) [src: languages.md] | Cloning from 3–10 s; voice design | Weights **CC-BY-NC**; whether generated audio may be shipped is unclear | MPS, mlx-audio | H100 only |
| Piper no_NO (talesyntese, nvcc) | Bokmål phonemes | One fixed voice; no characters | CC0 data; piper1 engine GPL-3.0 | CPU (ONNX), fast | "Real-time on a Raspberry Pi" [2nd] |
| akhbar/chatterbox-tts-norwegian, F5_Norwegian, XTTS-v2, Fish/OpenAudio, Higgs | — | — | Non-commercial or research only: **avoid** | — | — |
| Kokoro, Qwen3-TTS, Zonos, Spark, IndexTTS, Dia, CSM, Orpheus | No Norwegian | — | — | — | — |

Generation time on an M3 [est]:

- The only Apple figure is VoxCPM2's RTF 1.76 on an M4 Pro. An M3 (Pro) is
  probably slower: assume **RTF 2–2.5**. RTF is seconds of compute per second
  of audio.

| Scope | Audio | Compute at RTF 2–2.5 | With retakes and checks (×1.5) |
|---|---|---|---|
| (a) all 97,200 lines | ~90 h | 180–225 h | **~11–14 days, running nonstop** |
| (b) 3,240 lines | ~3 h | 6–7.5 h | ~1 day of evenings |
| (c) 972 barks | ~20 min | 40–50 min | **~1–1.5 h** |
| (c′) 162 barks | ~4 min | ~10 min | ~15 min |

- The NB-Whisper check adds little: whisper.cpp with Metal is much faster
  than real time on Apple Silicon [2nd].
- Memory: 36 GB is plenty for every candidate above (VoxCPM2 needs about
  8 GB; Chatterbox's checkpoint is 2.1 GB).
- Real numbers: run a 100-line benchmark on the Mac before committing to a
  scope.

## Cloud vendors [src: vendor pages, read 8 November 2026]

| Vendor | Nynorsk | Character voices | Licence to ship the audio | Cost: all (4.4M chars) / (b) ~200k / (c) ~20k |
|---|---|---|---|---|
| **Google Gemini-TTS** | **`nn-NO` listed (Preview)**; checked at source | About 30 voices, style set by plain-language prompts | Output is customer data. Generative AI may not be used in services aimed at under-18s. | ~$66 / ~$3 / ~$0.30 [est, at $9 per 1M audio tokens, which doubles from 2027] |
| ElevenLabs (v3, Flash) | "Norwegian" only | **Voice Design** from a 20–1,000-character description; the strongest for characters | Free plan forbids commercial use and requires credit; paid plans include a commercial licence | v3: $352 / $22 / $6 |
| OpenAI (gpt-4o-mini-tts) | Norwegian, English-tuned | 13 fixed voices plus `instructions` | **You must tell listeners the voice is AI**; the TTS models are announced to retire on 6 January 2027 | ~$66 / ~$3 / ~$0.30 |
| Azure Speech | Bokmål only (Pernille, Finn, Iselin) | No styles for nb-NO | Code of Conduct requires disclosure | $66 / free tier / free tier |
| ReadSpeaker | One Nynorsk voice ("Nora", from Nuance) | One voice | Not stated | Not published |

At scope (c), cost does not matter on any vendor; Nynorsk quality and
character voices decide. A free addon may still be "commercial use" under a
vendor's terms, especially with CurseForge rewards, so use a paid tier or a
self-hosted model with a permissive licence.

## Licences and disclosure

- Blizzard's UI Add-On Development Policy [src: forum post, 2009]:
  - add-ons must be free;
  - no objectionable content (ESRB T);
  - no "excessive use of the chat system";
  - nothing specific about audio.
- **Do not imitate Blizzard voice actors or named NPCs.** Do not clone real
  people without their consent. Designed voices (VoxCPM2, ElevenLabs Voice
  Design, Gemini prompts) avoid needing reference recordings.
- EU AI Act Art. 50 (from 2 August 2026): marking duties fall on the
  provider. The deployer's duty is mainly for deep fakes, and is lighter for
  clearly fictional, creative works. Norway has not yet adopted it [2nd].
- Practical step: say "Voices are AI-generated (<engine>)" in the README, on
  CurseForge and in the voice option. OpenAI and Azure require this anyway.

## A Nynorsk voice pack of about 2,000 clips (design proposal)

The voice does **not read the received line**. It plays a short spoken
reaction in the **sender's personality voice**, assembled from up to three
recorded pieces. The text line still shows as today. This sidesteps
`{zone}`/`{level}`, version mismatches and the 3% match problem. It can also
play when the sender writes in English, since the receiver needs only
(personality, kind).

### Pieces per personality (×9)

| Piece | Mood or kind | Count | Typical length |
|---|---|---|---|
| Opener: signature exclamation | 8 cheerful, 4 sombre | 12 | ~0.8 s |
| Body: what happened | 10 each for level, death, congrats, welcome and zone; 8 each for the 12 `congrats_*` kinds | 146 | ~1.8 s |
| Closer: signature sign-off | 7 cheerful, 3 sombre | 10 | ~0.8 s |
| Milestone level ("Nivå sytti!") | 10, 20, … 90 | 9 | ~1 s |
| Solo: complete one-liner | Any | 40 | ~2.5 s |
| **Per personality** | | **217** | ~6.6 min |

9 × 217 = **1,953 clips**, about **60 minutes of audio** [est].

### Playback

- Templates, picked at random: body (25%), opener + body (35%),
  body + closer (25%), opener + body + closer (15%); now and then a solo
  instead. A level-up on a milestone level may add the number piece.
- Avoid repeating the last piece, as the captions already do.
- Death uses only the sombre openers and closers.
- Variety [est]: for a `congrats_*` kind, 8 openers, 8 bodies and 7 closers
  give 8 + 64 + 56 + 448 = **576 different spoken versions per personality**.
- Pieces are chained with `C_Timer.After(duration + 0.12)`. `C_Timer.After`
  is called by Blizzard's own code in all four branches [src]. Each piece's
  duration comes from the manifest, so no "sound finished" event is needed.
- One voice at a time. While one plays, keep at most one more waiting and
  drop the rest. Add a short cooldown per sender.
- Play on the Dialog channel, behind an on/off option (default on once the
  pack is installed). Never play in previews, except a local "Test voice"
  button.

### Writing the pieces so they join well

- Each piece is a **complete, self-contained utterance** ending in "!" or
  "." with no grammatical dependence on its neighbours. Stitching works
  because no piece is cut in mid-sentence.
- Write for the ear, not for chat:
  - "Gratulerer!", not "GZ";
  - numbers as words;
  - no "F" or emoticons.
- Generate every piece with the same voice and style prompt. Make 2–3 takes
  and keep the best (lowest NB-Whisper WER, then by ear).
- Normalise loudness, trim silence and keep a fixed gap of about 120 ms.
- Example (dwarf, level-up): "Ved skjegget mitt!" + "Sterkare enn stein, du!"
  + "Eg spanderer neste krus!"

### Size and shipping [est]

- About 60 min of audio at 32–40 kbps is **about 15–25 MB**. MP3 avoids
  Vorbis's ~4 KB header per file, which is about 8 MB across 1,953 files.
- Today each edition ZIP is about 3 MB (`git archive` of each edition
  folder). Inside every edition ZIP the pack would take 60–100 MB of the
  64 MiB deploy limit, so it has to ship as **one separate, optional
  `WoWStatus_Voices` addon**.
- That addon needs a TOC for each client. Whether one folder can hold
  several flavour TOCs, or a comma-separated `## Interface:` line, in the
  Forever client is **not verified**.
- Cost and time:
  - Gemini-TTS, 3 takes: ~10,700 s of audio, ~268k audio tokens, about
    **$2.50** [est].
  - VoxCPM2 on the M3: about 6–7.5 h [est].

### Small sample in the addon, full pack as a separate download

- An addon cannot download anything from inside the game: WoW gives addons no
  HTTP access. So the full pack is a **second addon the player installs
  themselves**, from the homepage or from CurseForge, where it can be listed as
  an optional dependency or related project.
- **Sample in the main addon:** about 10 pieces per personality (3 openers,
  one body each for level, death, congrats, welcome and zone, 2 closers), so
  90 clips and about 1.5 min of audio. That is roughly **0.5–1 MB per edition
  ZIP**, or 2–4 MB across all four, well within the deploy limit.
- **Detection:** at login, check whether `WoWStatus_Voices` is loaded (through
  the Safe.lua adapter, since `C_AddOns.IsAddOnLoaded` and the old global
  `IsAddOnLoaded` differ between clients). If the pack is loaded, use its
  manifest; otherwise use the sample. The pack can be `LoadOnDemand` and loaded
  the first time a reaction needs a voice.
- **Telling players about it:** one line in the voice option ("More voices:
  install WoW Status Voices from the homepage"). No popup or chat nag.
- **Restart:** a newly installed addon, like a new sound file, is only seen
  after a full game restart. The homepage and the option text should say so.
- **Versions:** the pack's manifest carries its own version. The main addon
  ignores piece ids it does not recognise and falls back to the sample.

### Changes this needs

- `P.matchReaction` returns the personality id as well as the kind.
- A small `Voices.lua`: the queue, chaining and settings.
- The pieces as JSON (`docs/caption-personalities/<id>/voice/*.json`), and
  a generator that writes the manifest.
- `build_homepage.py`, its tests and `verify_homepage.py` package and check
  the voice-pack ZIP.

## Variant: WoW Forever only, 2,000 pieces per personality, one take

### Scope

- Only the Forever edition (interface 16001, maximum level 60, per
  `addon/forever/WoWStatus/Forever.lua`).
- The pack needs **one TOC**, which removes the open question about TOCs for
  several clients.
- The script should fit Forever's world:
  - levels up to 60 (milestone pieces for 10, 20, … 60, plus "maximum level"
    lines);
  - PvP ranks rather than modern rated PvP;
  - epic mounts at 60;
  - no flying, transmog or dungeon finder references.

### Pieces per personality

| Piece | Count | Length [est] |
|---|---|---|
| Openers (40 cheerful, 20 sombre) | 60 | 0.8 s |
| Closers (40 cheerful, 20 sombre) | 60 | 0.8 s |
| Level 10–60 (3 variants each) and 12 "maximum level" lines | 30 | 1.0 s |
| Bodies: 150 level, 150 death, 120 zone, 80 welcome, 100 general congrats, ~83 for each of the 12 `congrats_*` kinds | 1,600 | 1.8 s |
| Solos: complete one-liners | 250 | 2.5 s |
| **Per personality** | **2,000** | **~60 min** |

9 personalities make **18,000 clips** and about **9.1 hours of audio**.

### Cost with Gemini-TTS, one take

Prices from Google's Cloud TTS pricing page, read 8 November 2026 [src]. Audio
is billed at 25 tokens per second.

| Model | Audio (~817k tokens) | Text input (~0.9M tokens) [est] | Total |
|---|---|---|---|
| Gemini 3.8 Flash TTS, until 31 December 2026 ($9 per 1M audio tokens, $0.50 per 1M text tokens) | $7.35 | ~$0.45 | **~$8** |
| Same model from 1 January 2027 ($18 / $1) | $14.71 | ~$0.90 | **~$16** |
| Gemini 3.8 Flash-Lite TTS, 2026 ($6 / $0.50) | $4.90 | ~$0.45 | ~$5 |

- Clips that fail the NB-Whisper check get regenerated. Allow about 10–20%
  extra.
- Time depends on the account's request limit, which I could not verify:
  - 10 requests a minute: ~30 h;
  - 60 a minute: ~5 h;
  - 300 a minute: ~1 h.
- For comparison, VoxCPM2 on the M3 would take about 18–23 h of compute
  [est].

### Measured on 10 samples (Gemini 3.8 Flash TTS, 8 November 2026)

- 30 pieces averaged **2.7 s**: openers about 1.6 s, bodies about 3.6 s,
  closers about 2.7 s. The acted delivery is slow, about 2 words per second.
- That is roughly **twice** the estimate above. At this pace, the 18,000-clip
  plan becomes about 18–20 h of audio, about **$16 (2026) or $32 (2027)**,
  and about 200–260 MB. Asking for a faster delivery in the style prompts,
  or writing shorter pieces, would bring it back down.
- A stitched sample came to 4–12 s, about as long as the same text generated
  in one request.

### Size and hosting [est]

- 9.1 h of mono speech:
  - 24 kbps: about **96 MB**;
  - 32 kbps: about **128 MB**;
  - Ogg Vorbis adds ~4 KB of header per file (~70 MB), so use MP3.
- Even on its own the pack is **over the 64 MiB deploy limit**, so the
  current homepage pipeline cannot carry it. Options:
  - a separate CurseForge project (size limit not verified);
  - a GitHub Release asset;
  - a separate upload path on the server outside the deploy archive;
  - splitting into packs per personality (about 11–14 MB each), letting
    players install only the voices they want.
- Keep the small sample in the Forever ZIP, as above.

### Writing 18,000 Nynorsk pieces

- Write and review them per personality and per kind, in JSON next to the
  caption personalities, following the `caption-personality` skill's
  process.
- A native-speaker spot check is part of the job.
- Run a pilot of one personality (2,000 pieces, about $0.85 to generate)
  before writing the rest.

## First batch: 100 pieces per personality, shipped inside the Forever addon

### Pieces per personality

| Piece | Count |
|---|---|
| Openers (5 cheerful, 3 sombre) | 8 |
| Closers (5 cheerful, 3 sombre) | 8 |
| Levels 10, 20 … 60 | 6 |
| Bodies: 4 for each of the 18 kinds | 72 |
| Solos | 6 |
| **Total** | **100** |

- That makes 900 clips. At the measured 2.7 s per piece, that is about
  40 min of audio, about 7–10 MB at 24–32 kbps, and about **$0.55** to
  generate with Gemini 3.8 Flash TTS (2026 price).
- Each `congrats_*` kind still gets 5 × 4 × 5 + 5 × 4 + 4 × 5 + 4 = **144**
  spoken versions per personality.

### Why ship inside the addon (no server change)

- The root-owned receiver (`deploy/install_release.py`, `prepare_homepage`)
  accepts any edition ZIP whose entries all start with `WoWStatus/`.
- The receiver caps each ZIP's unpacked size and the whole deploy archive at
  64 MiB.
- Today the deploy archive is about 22 MB: about 9.2 MB of application
  (`git archive` with the release pathspec) plus 4 edition ZIPs of about
  3 MB each.
- So `WoWStatus/Sounds/*.mp3` in the Forever ZIP (+7–10 MB) fits without
  touching the receiver, Caddy or the server.
- Players get the voices with the normal Forever download and need no extra
  install.

### Repository changes

- Commit the MP3s under `addon/forever/WoWStatus/Sounds/`. Builds read addon
  files from Git, so the audio must be committed.
- Generate a `Voices.lua` manifest (piece id, file, seconds) and add it to
  the Forever TOC.
- `scripts/build_homepage.py` packages only TOC-listed files and
  `Textures/*.tga`. Extend it to `Sounds/*.mp3`, and update its tests and
  `scripts/verify_homepage.py`, which checks ZIP entries against the TOC.

### Later, for the full pack (~200+ MB)

That size goes over the receiver limit, so ship it as a separate
`WoWStatus_Voices` addon. Two routes:

- **No server change:** a GitHub Release asset in a public repository (2 GiB
  per file), linked from the homepage. The link
  `…/releases/latest/download/<file>.zip` stays stable across releases.
- **On the server**, which needs root:
  - a separate static folder, for example
    `/srv/wow-status-homepage-voices/`;
  - a Caddy route such as `/voices/`;
  - an upload path (a forced-command key or a sudo rule) used only when the
    voices change;
  - outside the 64 MiB application deploy.

## Verification plan (what would show it is right)

1. **Automatic intelligibility.** Transcribe every candidate clip with
   NB-Whisper (Apache-2.0; use `language='nn'` and the *verbatim* variant via
   whisper.cpp). Compute word error rate against the source text.
   - Pass: ≤ 10% WER for Nynorsk barks on the chosen engine.
   - Also check that the transcript is not Bokmål: Bokmål forms such as
     "jeg", "ikke", "hva" count as errors.
2. **Native listening.** 3–5 Nynorsk speakers rate blind A/B clips from 1 to 5.
   - Pass: average of 4 or more, no clip below 3.
3. **Size.** The builder reports each ZIP's size.
   - Pass: all four edition ZIPs plus any voice pack fit under the 64 MiB
     deploy limit with ≥ 25% headroom.
4. **Live client, in each of the four editions (the owner's check):**
   - A reaction plays one bark on the Dialog slider.
   - Barks never overlap; they queue or drop.
   - Nothing plays in a preview.
   - A missing voice pack fails silently.
   - In Retail, nothing is spoken during chat lockdown.
   - Mocked tests cannot establish any of this.
5. **Licence.** Record the engine, model version, licence URL and date in the
   voice pack's README before shipping.

## Not verified

- Whether `PlaySoundFile` and the "Dialog" channel work in the Forever and
  Retail clients (no Blizzard call site).
- A Blizzard statement that new sound files need a full restart.
- An official CurseForge size limit.
- Any model's real speed on an M3, and Nynorsk quality in practice for every
  engine.
- Whether Gemini-TTS adds a watermark.
- ElevenLabs terms for games specifically.
- Whether WoW on macOS lists every system voice.
- The DBM voice-pack precedent was not re-checked.
