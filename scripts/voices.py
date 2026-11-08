#!/usr/bin/env python3
"""Spoken reactions for WoW Forever: choose, generate, package and release voice clips.

A friend's Nynorsk reaction whisper is read aloud on the receiver's client in the
sender's personality voice. Text, choices and clip records live in Git; the audio
lives in dist/voices/ (a cache, ignored by Git) and in GitHub Releases. See
docs/voices/README.md for the whole workflow.

    python scripts/voices.py select            # choose (or top up) the voiced lines
    python scripts/voices.py generate --dry-run
    python scripts/voices.py generate          # record only the clips that are missing
    python scripts/voices.py sample            # copy the in-addon sample into the Forever addon
    python scripts/voices.py build             # write addon/forever/WoWStatus/VoiceData.lua
    python scripts/voices.py build --check     # fail if VoiceData.lua is stale
    python scripts/voices.py pack              # build the voice pack ZIPs in dist/voices/
    python scripts/voices.py release           # upload them as a draft GitHub release
    python scripts/voices.py publish 3         # publish voice-pack-v3 as the current pack
    python scripts/voices.py restore           # fetch the published audio into dist/voices/
    python scripts/voices.py bundle --zip dist/homepage/downloads/WoWStatus-forever.zip
                                               # CurseForge: put every clip into the Forever ZIP
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_personalities as personalities  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VOICES = ROOT / 'docs' / 'voices'
CONFIG = VOICES / 'voices.json'
CLIPS = VOICES / 'clips.json'
SELECTION = VOICES / 'selection'
CAPTIONS = ROOT / 'docs' / 'caption-personalities'
CACHE = ROOT / 'dist' / 'voices'
FOREVER = ROOT / 'addon' / 'forever' / 'WoWStatus'
SAMPLE_DIR = FOREVER / 'Sounds' / 'Voices'
DATA_LUA = FOREVER / 'VoiceData.lua'
PACK_ADDON = 'WoWStatus_Voices'
PACK_ZIP = 'WoWStatus_Voices.zip'
# Lossless masters, one ZIP per personality (GitHub allows 2 GiB per release file).
MASTERS_ZIP = 'voices-masters-{}.zip'
FOREVER_INTERFACE = 16001
MAX_LEVEL = 60
# Zone names are not recorded yet, so "Enjoy <zone>!" lines stay text-only.
UNVOICED_KINDS = ('enjoy',)
# Text that only works when read: emoticons, salutes, asterisks.
UNSPOKEN = re.compile(r'[:;]-?[()DPp]|<3|\bxD\b|\bo7\b|\blol\b|\*', re.IGNORECASE)
LEVEL_AT_END = re.compile(r'^(.*\S)\s*\{level\}([!.?…]*)$')
# Rough clip lengths for estimates (measured on the first samples).
SECONDS_LINE, SECONDS_NUMBER = 3.4, 0.9
AUDIO_TOKENS_PER_SECOND = 25
AUDIO_PRICE = {'gemini-3.8-flash-tts': 9.0, 'gemini-3.8-flash-lite-tts': 6.0}

UNITS = ('', 'ein', 'to', 'tre', 'fire', 'fem', 'seks', 'sju', 'åtte', 'ni', 'ti', 'elleve', 'tolv',
         'tretten', 'fjorten', 'femten', 'seksten', 'sytten', 'atten', 'nitten')
TENS = {20: 'tjue', 30: 'tretti', 40: 'førti', 50: 'femti', 60: 'seksti'}


class VoiceError(RuntimeError):
    """A voice step cannot continue; nothing more has been changed."""


def number_words(n: int) -> str:
    """A level in Nynorsk words, as it is spoken after "nivå"."""
    if not 1 <= n <= 69:
        raise ValueError(n)
    if n < 20:
        return UNITS[n]
    tens = n - n % 10
    return TENS[tens] + (UNITS[n % 10] if n % 10 else '')


def clip_id(*parts: str) -> str:
    """A stable file name: the same personality, kind and text always give the same id."""
    return hashlib.sha1('\n'.join(parts).encode('utf-8')).hexdigest()[:12]


def spoken(text: str) -> str:
    """What the voice says for a line: the line itself, minus chat shorthand."""
    # "F" (pay respects) on its own is shown, not said: "Å, ven. F. Rist av deg" says "Å, ven. Rist av deg".
    said = re.sub(r'(?:^|(?<=[.!?] ))F\b[.,!]*\s*', '', text).strip()
    said = (said[:1].upper() + said[1:]) if said else text

    def gz(match: re.Match) -> str:
        start = match.start() == 0 or said[:match.start()].rstrip().endswith(('.', '!', '?'))
        return 'Gratulerer' if start else 'gratulerer'
    return re.sub(r'\bG[Zz]\b|\bgz\b', gz, said)


def shown(path: Path) -> str:
    """A path relative to the repository when it is inside it."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write beside it, then swap: a recording stopped mid-save never leaves half a file.
    partial = path.with_name(path.name + '.partial')
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    partial.replace(path)


def config() -> dict:
    data = read_json(CONFIG)
    if not data:
        raise VoiceError(f'{CONFIG} is missing')
    return data


def voiced_personalities(cfg: dict) -> list[str]:
    """Reaction voices that ship and have a voice in voices.json, in menu order."""
    return [p.id for p in personalities.PERSONALITIES
            if p.id in personalities.REACTION_VOICES and p.id in cfg['personalities']]


def bank(pid: str, kind: str, source: Path | None = None) -> list[str]:
    """The Nynorsk reaction lines of one kind, in the addon's order (Lua index = position + 1)."""
    rows = read_json((source or CAPTIONS) / pid / 'reactions' / f'{kind}.json')
    if not isinstance(rows, list):
        raise VoiceError(f'{pid}/reactions/{kind}.json is missing')
    return [row['nn'] for row in rows]


def level_parts(template: str) -> tuple[str, str] | None:
    """A level line that ends in its number: (text before the number, closing punctuation)."""
    match = LEVEL_AT_END.match(template)
    return (match.group(1), match.group(2)) if match else None


def spread(items: list, count: int) -> list:
    """count items evenly spread over the list, keeping its order."""
    if count <= 0:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[0]]
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def candidates(lines: list[str], kind: str) -> list[str]:
    if kind == 'level':
        return [line for line in lines if level_parts(line) and not UNSPOKEN.search(line)]
    return [line for line in lines if not UNSPOKEN.search(line)]


def choose(lines: list[str], kind: str, count: int, keep: list[str]) -> list[str]:
    """Keep earlier choices that still exist, then top up with short lines spread over the bank."""
    pool = candidates(lines, kind)
    kept = [line for line in keep if line in pool]
    rest = [line for line in pool if line not in kept]
    # The shorter part of the bank: quicker to hear and smaller to ship.
    shortest = sorted(rest, key=lambda line: (len(line), lines.index(line)))
    shortlist = sorted(shortest[:max(count, int(len(rest) * .6))], key=lines.index)
    chosen = kept + spread(shortlist, count - len(kept))
    return sorted(chosen, key=lines.index)


def select(cfg: dict, only: str | None = None, source: Path | None = None, target: Path | None = None) -> dict:
    """Write selection/<id>.json for each voice; earlier choices are kept, counts are topped up."""
    counts, written, target = cfg['counts'], {}, target or SELECTION
    for pid in voiced_personalities(cfg):
        if only and pid != only:
            continue
        path = target / f'{pid}.json'
        old = read_json(path, {'sample': {}, 'pack': {}})
        result = {'sample': {}, 'pack': {}}
        for kind in personalities.REACTIONS:
            if kind in UNVOICED_KINDS:
                continue
            lines = bank(pid, kind, source)
            earlier = old['sample'].get(kind, []) + old['pack'].get(kind, [])
            total = counts['level_lines'] if kind == 'level' else counts['lines_per_kind']
            picked = choose(lines, kind, total, earlier)
            sample_count = 0 if kind == 'level' else counts['sample_per_kind'] + counts['sample_extra'].get(kind, 0)
            sample = [line for line in old['sample'].get(kind, []) if line in picked]
            sample += spread([line for line in picked if line not in sample], sample_count - len(sample))
            sample = sorted(sample, key=lines.index)
            result['sample'][kind] = sample
            result['pack'][kind] = [line for line in picked if line not in sample]
        write_json(path, result)
        written[pid] = result
    return written


@dataclass(frozen=True)
class Clip:
    id: str
    personality: str
    kind: str          # a reaction kind, or "number"
    text: str          # what the voice says
    tier: int          # 1: ships inside the addon, 2: in the voice pack
    index: int = 0     # Lua index in the Nynorsk bank; the level for "number"


def required(cfg: dict, source: Path | None = None, selection: Path | None = None) -> list[Clip]:
    """Every clip the current selection needs, in a stable order."""
    clips, selection = [], selection or SELECTION
    for pid in voiced_personalities(cfg):
        chosen = read_json(selection / f'{pid}.json')
        if not chosen:
            continue
        levels = False
        for kind in personalities.REACTIONS:
            lines = bank(pid, kind, source) if kind not in UNVOICED_KINDS else []
            # addon_sample false: the sample lines ship in the pack too, and the addon carries no audio.
            sample_tier = 1 if cfg.get('addon_sample', True) else 2
            for tier, group in ((sample_tier, 'sample'), (2, 'pack')):
                for template in chosen[group].get(kind, []):
                    if template not in lines:
                        raise VoiceError(f'{pid}/{kind}: {template!r} is no longer a reaction line; '
                                         'run scripts/voices.py select')
                    index = lines.index(template) + 1
                    if kind == 'level':
                        parts = level_parts(template)
                        if not parts:
                            raise VoiceError(f'{pid}/level: {template!r} does not end with its level')
                        said, levels = spoken(parts[0]), True
                    else:
                        said = spoken(template)
                    clips.append(Clip(clip_id(pid, kind, template), pid, kind, said, tier, index))
        if levels:
            for level in range(2, MAX_LEVEL + 1):
                clips.append(Clip(clip_id(pid, 'number', str(level)), pid, 'number',
                                  number_words(level) + '!', 2, level))
    ids = [clip.id for clip in clips]
    if len(set(ids)) != len(ids):
        raise VoiceError('Two clips share an id; a line is chosen twice')
    return clips


def registry() -> dict:
    return read_json(CLIPS, {'release': None, 'clips': {}})


def estimate(clips: list[Clip], model: str) -> str:
    seconds = sum(SECONDS_NUMBER if clip.kind == 'number' else SECONDS_LINE for clip in clips)
    price = AUDIO_PRICE.get(model)
    cost = f'about ${seconds * AUDIO_TOKENS_PER_SECOND / 1e6 * price:.2f}' if price else 'unknown cost'
    return f'{len(clips)} clips, about {seconds / 3600:.1f} h of audio, {cost} with {model}'


def ffmpeg() -> str:
    found = shutil.which('ffmpeg')
    if not found:
        raise VoiceError('ffmpeg is needed for FLAC masters and Ogg Vorbis clips')
    return found


# WoW Forever cuts MP3s under 64 kbps short (it stops where a 64 kbps file would
# end), so clips are Ogg Vorbis, WoW's own format, which plays to the end.
def to_clip(source: Path, clip: Path, quality: int) -> None:
    """Encode one clip for the game: loudness-normalised mono Ogg Vorbis, 44.1 kHz."""
    clip.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg(), '-y', '-loglevel', 'error', '-i', str(source), '-af', 'loudnorm=I=-18:TP=-2:LRA=7',
                    '-ac', '1', '-ar', '44100', '-c:a', 'libvorbis', '-q:a', str(quality), str(clip)], check=True)


def encode(pcm: bytes, rate: int, flac: Path, clip: Path, quality: int) -> None:
    flac.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / 'clip.wav'
        with wave.open(str(wav), 'wb') as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(rate)
            target.writeframes(pcm)
        subprocess.run([ffmpeg(), '-y', '-loglevel', 'error', '-i', str(wav), str(flac)], check=True)
        to_clip(wav, clip, quality)


def cached_clip(clip_id_: str) -> Path:
    return CACHE / 'clips' / f'{clip_id_}.ogg'


def cached_flac(clip_id_: str) -> Path:
    return CACHE / 'masters' / f'{clip_id_}.flac'


def generate(cfg: dict, args) -> int:
    import voice_samples as tts

    needed = required(cfg)
    if args.only:
        needed = [clip for clip in needed if clip.personality == args.only]
    if args.tier:
        needed = [clip for clip in needed if clip.tier == args.tier]
    known = registry()
    todo = [clip for clip in needed if clip.id not in known['clips']]
    lost = [clip for clip in needed if clip.id in known['clips'] and not cached_clip(clip.id).is_file()
            and not (SAMPLE_DIR / f'{clip.id}.ogg').is_file()]
    if args.limit:
        todo = todo[:args.limit]
    print(f'{len(needed)} clips selected, {len(needed) - len(todo)} already recorded.')
    print('To record: ' + estimate(todo, cfg['model']))
    if lost:
        print(f'{len(lost)} recorded clips are not in dist/voices/ on this computer; '
              'run scripts/voices.py restore before packing.')
    if args.dry_run or not todo:
        return 0
    key = tts.api_key()
    if not key:
        raise VoiceError('Set GOOGLE_API_KEY (environment or the repository .env)')
    headers = {'x-goog-api-key': key}
    lock, done, started = threading.Lock(), [0], time.monotonic()

    def record(clip: Clip) -> tuple[Clip, float]:
        voice = cfg['personalities'][clip.personality]
        style = voice['style'] + ' ' + cfg['accent']
        audio = tts.trim(tts.synthesize(clip.text, style, voice['voice'], cfg['model'], cfg['language_code'],
                                        headers, None))
        encode(audio, tts.RATE, cached_flac(clip.id), cached_clip(clip.id), cfg['ogg_quality'])
        return clip, len(audio) / 2 / tts.RATE

    def save() -> None:
        write_json(CLIPS, known)

    failed = []
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = {pool.submit(record, clip): clip for clip in todo}
        for future in as_completed(futures):
            try:
                clip, seconds = future.result()
            except (Exception, SystemExit) as error:  # one bad clip: note it, keep going
                failed.append(futures[future])
                print(f'  failed: {futures[future].personality} {futures[future].text!r}: {error}', flush=True)
                continue
            with lock:
                known['clips'][clip.id] = {'personality': clip.personality, 'kind': clip.kind,
                                           'text': clip.text, 'seconds': round(seconds, 3),
                                           'voice': cfg['personalities'][clip.personality]['voice'],
                                           'model': cfg['model'], 'recorded': time.strftime('%Y-%m-%d')}
                done[0] += 1
                if done[0] % 25 == 0:
                    save()
                    rate = done[0] / (time.monotonic() - started)
                    print(f'  {done[0]}/{len(todo)} recorded ({rate * 60:.0f} a minute)', flush=True)
    finally:
        # On a stop (Ctrl+C or an error), queued clips are cancelled, not paid for.
        pool.shutdown(wait=True, cancel_futures=True)
        save()
    print(f'Recorded {done[0]} clips into dist/voices/ and {shown(CLIPS)}.')
    if failed:
        print(f'{len(failed)} clips failed; run generate again to retry them.')
        return 1
    return 0


def reencode(cfg: dict, workers: int) -> int:
    """Make every game clip again from its lossless master: a format change costs no recording."""
    known = registry()['clips']
    masters = [cid for cid in sorted(known) if cached_flac(cid).is_file()]
    missing = len(known) - len(masters)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda cid: to_clip(cached_flac(cid), cached_clip(cid), cfg['ogg_quality']), masters))
    for old in (CACHE / 'clips').glob('*.mp3'):
        old.unlink()
    print(f'Re-encoded {len(masters)} clips from their masters into {shown(CACHE / "clips")}.')
    if missing:
        print(f'{missing} clips have no master here; run scripts/voices.py restore first.')
        return 1
    return 0


def sample(cfg: dict) -> int:
    """Copy the tier-1 clips into the Forever addon and remove stale ones (all of them when
    addon_sample is false: then the pack carries every clip)."""
    known = registry()['clips']
    wanted = {clip.id for clip in required(cfg) if clip.tier == 1 and clip.id in known}
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for clip in sorted(wanted):
        target = SAMPLE_DIR / f'{clip}.ogg'
        if cached_clip(clip).is_file():
            shutil.copyfile(cached_clip(clip), target)
        elif not target.is_file():
            missing.append(clip)
    removed = 0
    for path in SAMPLE_DIR.glob('*'):
        if path.suffix != '.ogg' or path.stem not in wanted:
            path.unlink()
            removed += 1
    if missing:
        raise VoiceError(f'{len(missing)} sample clips are neither cached nor in the addon; run restore')
    if not wanted:  # no audio in the addon: leave no empty folders behind
        for folder in (SAMPLE_DIR, SAMPLE_DIR.parent):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        print(f'No clips in the addon; {removed} removed. Every clip ships in the voice pack.')
        return 0
    size = sum(path.stat().st_size for path in SAMPLE_DIR.glob('*.ogg'))
    print(f'{len(wanted)} sample clips in {shown(SAMPLE_DIR)} ({size / 1e6:.1f} MB), {removed} removed.')
    return 0


def lua_string(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def render(cfg: dict, clips: list[Clip], known: dict, sample_dir: Path | None = None) -> str:
    """VoiceData.lua: which reaction lines have a recorded voice, and where."""
    sample_dir = sample_dir or SAMPLE_DIR
    lines: dict[str, dict[str, list[tuple[int, str, int]]]] = {}
    numbers: dict[str, list[tuple[int, str]]] = {}
    seconds: dict[str, float] = {}
    for clip in clips:
        if clip.id not in known:
            continue  # not recorded yet: the line stays text-only
        if clip.tier == 1 and not (sample_dir / f'{clip.id}.ogg').is_file():
            continue  # not copied into the addon: it cannot play
        seconds[clip.id] = known[clip.id]['seconds']
        if clip.kind == 'number':
            numbers.setdefault(clip.personality, []).append((clip.index, clip.id))
        else:
            lines.setdefault(clip.personality, {}).setdefault(clip.kind, []).append((clip.index, clip.id, clip.tier))
    # A level line can only play with its number.
    for pid, kinds in lines.items():
        if 'level' in kinds and len(numbers.get(pid, [])) < MAX_LEVEL - 1:
            del kinds['level']
    url = f'https://github.com/{cfg["repository"]}/releases/download/{cfg["pack_tag"]}/{PACK_ZIP}'
    out = [
        '-- Generated by scripts/voices.py build from docs/voices/. Do not edit.',
        '-- Reaction lines with a recorded Nynorsk voice (Forever only): lines[voice][kind][index]',
        '-- = {clip, tier}; tier 1 ships in Sounds/Voices/, tier 2 in the WoWStatus_Voices pack.',
        '-- A level line is the text before the number; numbers[voice][level] is the number.',
        'WoWStatusVoiceData = {',
        f'    pack = {{addon = {lua_string(PACK_ADDON)}, url = {lua_string(url)}}},',
        f'    gap = {cfg["gap_seconds"]},',
        '    lines = {',
    ]
    for pid in sorted(lines):
        out.append(f'        {pid} = {{')
        for kind in personalities.REACTIONS:
            entries = lines[pid].get(kind)
            if entries:
                body = ', '.join(f'[{index}] = {{"{cid}", {tier}}}' for index, cid, tier in sorted(entries))
                out.append(f'            {kind} = {{{body}}},')
        out.append('        },')
    out.append('    },')
    out.append('    numbers = {')
    for pid in sorted(numbers):
        body = ', '.join(f'[{level}] = "{cid}"' for level, cid in sorted(numbers[pid]))
        out.append(f'        {pid} = {{{body}}},')
    out.append('    },')
    out.append('    seconds = {')
    for cid in sorted(seconds):
        out.append(f'        ["{cid}"] = {seconds[cid]},')
    out.append('    },')
    out.append('}')
    return '\n'.join(out) + '\n'


def build(cfg: dict, check: bool) -> int:
    text = render(cfg, required(cfg), registry()['clips'])
    current = DATA_LUA.read_text(encoding='utf-8') if DATA_LUA.is_file() else None
    if current == text:
        print(f'{shown(DATA_LUA)} is up to date.')
        return 0
    if check:
        print(f'voices: {shown(DATA_LUA)} is stale; run scripts/voices.py build', file=sys.stderr)
        return 1
    DATA_LUA.write_bytes(text.encode('utf-8'))
    print(f'Wrote {shown(DATA_LUA)}.')
    return 0


def pack_toc(version: int) -> str:
    return '\n'.join([
        f'## Interface: {FOREVER_INTERFACE}',
        '## Title: WoW Status — Voices',
        '## Notes: Spoken Nynorsk reactions for WoW Status on WoW Forever. Needs WoW Status.',
        '## Author: fraval13',
        f'## Version: {version}',
        '## Dependencies: WoWStatus',
        'Pack.lua',
    ]) + '\n'


def pack(cfg: dict, version: int) -> list[Path]:
    """The voice pack (tier-2 clips as an addon), then one masters ZIP (FLAC) per personality."""
    known = registry()
    clips = [clip for clip in required(cfg) if clip.id in known['clips']]
    tier2 = sorted({clip.id for clip in clips if clip.tier == 2})
    missing = [cid for cid in tier2 if not cached_clip(cid).is_file()]
    masters = sorted({clip.id for clip in clips if cached_flac(clip.id).is_file()})
    if missing:
        raise VoiceError(f'{len(missing)} pack clips are not in dist/voices/; run scripts/voices.py restore')
    if len(masters) != len(clips):
        raise VoiceError(f'{len(clips) - len(masters)} FLAC masters are missing; run scripts/voices.py restore')
    CACHE.mkdir(parents=True, exist_ok=True)
    pack_path = CACHE / PACK_ZIP
    for old in CACHE.glob(MASTERS_ZIP.format('*')):
        old.unlink()
    with zipfile.ZipFile(pack_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f'{PACK_ADDON}/{PACK_ADDON}.toc', pack_toc(version))
        archive.writestr(f'{PACK_ADDON}/Pack.lua', '-- Marks the voice pack as installed for WoW Status.\n'
                         f'WoWStatusVoicePack = {{version = {version}, clips = {len(tier2)}}}\n')
        for cid in tier2:
            archive.write(cached_clip(cid), f'{PACK_ADDON}/Sounds/{cid}.ogg', zipfile.ZIP_STORED)
    owners = {clip.id: clip.personality for clip in clips}
    paths = [pack_path]
    for pid in sorted(set(owners.values())):
        path = CACHE / MASTERS_ZIP.format(pid)
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as archive:
            for cid in masters:
                if owners[cid] == pid:
                    archive.write(cached_flac(cid), f'masters/{cid}.flac')
        paths.append(path)
    size = sum(path.stat().st_size for path in paths[1:])
    print(f'{shown(pack_path)}: {len(tier2)} clips, {pack_path.stat().st_size / 1e6:.1f} MB')
    print(f'{len(paths) - 1} masters ZIPs: {len(masters)} clips, {size / 1e6:.1f} MB')
    return paths


def bundle(cfg: dict, archive: Path, pack_file: Path | None = None) -> int:
    """Put every clip the addon lists into an edition ZIP (the CurseForge Forever build).

    The clips come from the published voice pack (or pack_file), so audio never
    enters Git or the homepage deploy. VoiceData.lua in the ZIP is marked
    bundled, so the addon plays the clips from its own folder.
    """
    folder, data_name = 'WoWStatus/', 'WoWStatus/VoiceData.lua'
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        if data_name not in names:
            raise VoiceError(f'{archive.name} has no VoiceData.lua; only the Forever build carries voices')
        data = source.read(data_name).decode('utf-8')
    wanted = sorted(set(re.findall(r'"([0-9a-f]{12})"', data)))
    if not wanted:
        raise VoiceError('VoiceData.lua lists no clips; there is nothing to bundle')
    with tempfile.TemporaryDirectory() as temp:
        if pack_file is None:
            url = f'https://github.com/{cfg["repository"]}/releases/download/{cfg["pack_tag"]}/{PACK_ZIP}'
            pack_file = Path(temp) / PACK_ZIP
            request = urllib.request.Request(url, headers={'User-Agent': 'wow-status-release'})
            with urllib.request.urlopen(request, timeout=600) as response, pack_file.open('wb') as target:
                shutil.copyfileobj(response, target)
        with zipfile.ZipFile(pack_file) as pack_zip:
            clips = {Path(name).stem: name for name in pack_zip.namelist()
                     if name.startswith(f'{PACK_ADDON}/Sounds/') and name.endswith('.ogg')}
            missing = [cid for cid in wanted if cid not in clips]
            if missing:
                raise VoiceError(f'The voice pack lacks {len(missing)} clips this addon lists; '
                                 'publish a newer pack (scripts/voices.py release, then publish)')
            bundled = Path(temp) / archive.name
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(bundled, 'w', zipfile.ZIP_DEFLATED) as out:
                for info in source.infolist():
                    content = source.read(info)
                    if info.filename == data_name:
                        content += b'-- This build carries every clip itself (scripts/voices.py bundle).\n'
                        content += b'WoWStatusVoiceData.bundled = true\n'
                    out.writestr(info, content)
                for cid in wanted:
                    name = f'{folder}Sounds/Voices/{cid}.ogg'
                    if name in names:
                        continue
                    entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                    entry.external_attr = 0o100644 << 16  # a regular file, as the other entries
                    out.writestr(entry, pack_zip.read(clips[cid]), zipfile.ZIP_STORED)
        shutil.move(str(bundled), str(archive))
    print(f'{archive.name}: {len(wanted)} clips added, {archive.stat().st_size / 1e6:.1f} MB.')
    return 0


def gh(*args: str) -> str:
    if not shutil.which('gh'):
        raise VoiceError('The GitHub CLI (gh) is needed; install it and run gh auth login')
    result = subprocess.run(['gh', *args], capture_output=True, text=True, encoding='utf-8', check=False)
    if result.returncode != 0:
        raise VoiceError(f'gh {" ".join(args[:2])} failed: {result.stderr.strip()[:400]}')
    return result.stdout


def pack_versions(cfg: dict) -> list[int]:
    releases = json.loads(gh('release', 'list', '-R', cfg['repository'], '--limit', '200', '--json', 'tagName'))
    prefix = cfg['pack_tag'] + '-v'
    return sorted(int(r['tagName'][len(prefix):]) for r in releases
                  if r['tagName'].startswith(prefix) and r['tagName'][len(prefix):].isdigit())


def release(cfg: dict, force: bool) -> int:
    versions = pack_versions(cfg)
    known = registry()
    newest = f'{cfg["pack_tag"]}-v{versions[-1]}' if versions else None
    if newest and known.get('release') != newest and not force:
        raise VoiceError(f'{newest} exists but docs/voices/clips.json was built on {known.get("release")}. '
                         'Someone else made a newer pack: pull, run restore, and try again.')
    version = (versions[-1] if versions else 0) + 1
    tag = f'{cfg["pack_tag"]}-v{version}'
    assets = [str(path) for path in pack(cfg, version)]
    gh('release', 'create', tag, *assets, '-R', cfg['repository'], '--draft',
       '--latest=false', '--title', f'Voice pack {version}',
       '--notes', f'Spoken Nynorsk reactions for WoW Status on WoW Forever, pack {version}. Draft until approved: '
                  f'listen, then run scripts/voices.py publish {version}.')
    print(f'Draft release {tag} created. Listen to it, then: python scripts/voices.py publish {version}')
    return 0


def publish(cfg: dict, version: int) -> int:
    tag, fixed = f'{cfg["pack_tag"]}-v{version}', cfg['pack_tag']
    with tempfile.TemporaryDirectory() as folder:
        gh('release', 'download', tag, '-R', cfg['repository'], '-D', folder)
        assets = sorted(str(path) for path in Path(folder).glob('*.zip'))
        gh('release', 'edit', tag, '-R', cfg['repository'], '--draft=false', '--latest=false')
        existing = {r['tagName'] for r in json.loads(gh('release', 'list', '-R', cfg['repository'], '--limit', '200',
                                                        '--json', 'tagName'))}
        if fixed not in existing:
            gh('release', 'create', fixed, *assets, '-R', cfg['repository'], '--latest=false', '--title',
               'Voice pack (current)', '--notes', 'The current WoW Status voice pack. Download WoWStatus_Voices.zip, '
               'extract it into Interface/AddOns next to WoWStatus and restart WoW.')
        else:
            gh('release', 'upload', fixed, *assets, '-R', cfg['repository'], '--clobber')
    known = registry()
    known['release'] = tag
    write_json(CLIPS, known)
    print(f'{tag} is published and is now the current pack. Commit docs/voices/clips.json.')
    return 0


def restore(cfg: dict) -> int:
    """Fetch the current pack's audio into dist/voices/, plus the in-addon sample."""
    with tempfile.TemporaryDirectory() as folder:
        gh('release', 'download', cfg['pack_tag'], '-R', cfg['repository'], '-D', folder)
        with zipfile.ZipFile(Path(folder) / PACK_ZIP) as archive:
            for name in archive.namelist():
                if name.endswith('.ogg'):
                    target = cached_clip(Path(name).stem)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
        for masters in sorted(Path(folder).glob(MASTERS_ZIP.format('*'))):
            with zipfile.ZipFile(masters) as archive:
                for name in archive.namelist():
                    if name.endswith('.flac'):
                        target = cached_flac(Path(name).stem)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
    for path in SAMPLE_DIR.glob('*.ogg'):
        cached_clip(path.stem).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, cached_clip(path.stem))
    print(f'Restored the published audio into {shown(CACHE)}.')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    chosen = sub.add_parser('select', help='choose or top up the voiced lines')
    chosen.add_argument('--only', metavar='ID')
    made = sub.add_parser('generate', help='record the clips that are missing')
    made.add_argument('--dry-run', action='store_true')
    made.add_argument('--only', metavar='ID')
    made.add_argument('--tier', type=int, choices=(1, 2), help='only the in-addon sample (1) or the pack (2)')
    made.add_argument('--limit', type=int, help='record at most this many now')
    made.add_argument('--workers', type=int, default=4)
    again = sub.add_parser('reencode', help='make every game clip again from its lossless master')
    again.add_argument('--workers', type=int, default=8)
    sub.add_parser('sample', help='copy the sample clips into the Forever addon')
    built = sub.add_parser('build', help='write VoiceData.lua')
    built.add_argument('--check', action='store_true')
    packed = sub.add_parser('pack', help='build the pack ZIPs in dist/voices/')
    packed.add_argument('--version', type=int, default=0)
    released = sub.add_parser('release', help='upload a new draft voice pack release')
    released.add_argument('--force', action='store_true', help='skip the check for a newer pack')
    published = sub.add_parser('publish', help='publish a draft and make it the current pack')
    published.add_argument('version', type=int)
    sub.add_parser('restore', help='fetch the current pack audio into dist/voices/')
    bundled = sub.add_parser('bundle', help='put every clip into an edition ZIP (the CurseForge Forever build)')
    bundled.add_argument('--zip', type=Path, required=True, help='the built WoWStatus-forever.zip, changed in place')
    bundled.add_argument('--pack', type=Path, help='a local WoWStatus_Voices.zip instead of the published one')
    args = parser.parse_args(argv)
    try:
        cfg = config()
        if args.command == 'select':
            chosen_lines = select(cfg, args.only)
            for pid, result in chosen_lines.items():
                sample_count = sum(len(v) for v in result['sample'].values())
                pack_count = sum(len(v) for v in result['pack'].values())
                print(f'{pid}: {sample_count} in the addon, {pack_count} in the pack')
            return 0
        if args.command == 'generate':
            return generate(cfg, args)
        if args.command == 'reencode':
            return reencode(cfg, args.workers)
        if args.command == 'sample':
            return sample(cfg)
        if args.command == 'build':
            return build(cfg, args.check)
        if args.command == 'pack':
            pack(cfg, args.version)
            return 0
        if args.command == 'release':
            return release(cfg, args.force)
        if args.command == 'publish':
            return publish(cfg, args.version)
        if args.command == 'bundle':
            return bundle(cfg, args.zip, args.pack)
        return restore(cfg)
    except VoiceError as error:
        print(f'voices: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
