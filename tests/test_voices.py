"""scripts/voices.py: choosing voiced lines, recording only what is missing, and packaging."""
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

lupa = pytest.importorskip('lupa')

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


def load(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f'{name}_under_test', SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def voices():
    return load('voices')


CFG = {
    'repository': 'owner/repo', 'pack_tag': 'voice-pack', 'model': 'gemini-3.8-flash-tts',
    'language_code': 'nn-NO', 'gap_seconds': 0.12, 'ogg_quality': 0, 'accent': 'Nynorsk.',
    'counts': {'sample_per_kind': 2, 'sample_extra': {'gz': 1}, 'lines_per_kind': 6, 'level_lines': 3},
    'personalities': {'dwarf': {'voice': 'Algenib', 'style': 'Gruff.'}},
}


def fake_captions(voices, root):
    """A dwarf with small reaction banks: 20 lines per kind, some unspeakable."""
    for kind in voices.personalities.REACTIONS:
        rows = []
        for i in range(20):
            if kind == 'level':
                text = f'Nivå {{level}}, linje {i}!' if i % 2 else f'Linje {i}: nivå {{level}}!'
            elif kind == 'enjoy':
                text = f'Kos deg i {{zone}}, {i}!'
            else:
                text = f'{kind} linje {i}' + (' :)' if i == 3 else '') + '.' * (i % 4)
            rows.append({'en': text, 'nn': text})
        path = root / 'dwarf' / 'reactions' / f'{kind}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return root


def test_spoken_text_drops_chat_shorthand_and_numbers_are_nynorsk_words(voices):
    assert voices.spoken('GZ! Skål for deg!') == 'Gratulerer! Skål for deg!'
    assert voices.spoken('Eit stille GZ frå nabobordet.') == 'Eit stille gratulerer frå nabobordet.'
    assert voices.spoken('Å, ven. F. Rist av deg støvet.') == 'Å, ven. Rist av deg støvet.'
    assert voices.spoken('F, modige ven.') == 'Modige ven.'
    assert voices.spoken('F') == 'F'
    assert [voices.number_words(n) for n in (2, 13, 20, 21, 37, 60)] == [
        'to', 'tretten', 'tjue', 'tjueein', 'trettisju', 'seksti']
    assert voices.level_parts('Skål for nivå {level}!') == ('Skål for nivå', '!')
    assert voices.level_parts('Nivå {level}, kjempe!') is None
    assert voices.clip_id('dwarf', 'gz', 'GZ!') == voices.clip_id('dwarf', 'gz', 'GZ!') != voices.clip_id(
        'bard', 'gz', 'GZ!')


def test_select_spreads_short_lines_keeps_earlier_choices_and_tops_up(voices, tmp_path, monkeypatch):
    monkeypatch.setattr(voices.personalities, 'REACTION_VOICES', ('dwarf',))
    source, target = fake_captions(voices, tmp_path / 'captions'), tmp_path / 'selection'
    first = voices.select(CFG, source=source, target=target)['dwarf']
    assert 'enjoy' not in first['pack'] and 'enjoy' not in first['sample']
    assert len(first['sample']['gz']) == 3 and len(first['sample']['f']) == 2 and first['sample']['level'] == []
    for kind in ('gz', 'f', 'congrats_loot'):
        chosen = first['sample'][kind] + first['pack'][kind]
        assert len(chosen) == 6 and len(set(chosen)) == 6
        assert not any(':)' in line for line in chosen)
        assert not set(first['sample'][kind]) & set(first['pack'][kind])
    assert len(first['pack']['level']) == 3 and all(line.endswith('nivå {level}!') for line in first['pack']['level'])
    # More lines later: earlier choices stay, new ones are added.
    bigger = {**CFG, 'counts': {**CFG['counts'], 'lines_per_kind': 10}}
    second = voices.select(bigger, source=source, target=target)['dwarf']
    assert second['sample'] == first['sample']
    assert set(first['pack']['gz']) <= set(second['pack']['gz']) and len(second['pack']['gz']) == 7


def test_required_clips_are_unique_include_numbers_and_notice_edited_lines(voices, tmp_path, monkeypatch):
    monkeypatch.setattr(voices.personalities, 'REACTION_VOICES', ('dwarf',))
    source, target = fake_captions(voices, tmp_path / 'captions'), tmp_path / 'selection'
    voices.select(CFG, source=source, target=target)
    clips = voices.required(CFG, source=source, selection=target)
    numbers = [clip for clip in clips if clip.kind == 'number']
    assert [clip.index for clip in numbers] == list(range(2, 61)) and numbers[35].text == 'trettisju!'
    level = [clip for clip in clips if clip.kind == 'level']
    assert level and all(clip.tier == 2 and not clip.text.endswith('!') for clip in level)
    assert len({clip.id for clip in clips}) == len(clips)
    assert {clip.tier for clip in clips if clip.kind == 'gz'} == {1, 2}
    # A chosen line that was edited away must be chosen again before recording.
    chosen = json.loads((target / 'dwarf.json').read_text(encoding='utf-8'))
    chosen['pack']['f'][0] = 'not a line any more'
    (target / 'dwarf.json').write_text(json.dumps(chosen), encoding='utf-8')
    with pytest.raises(voices.VoiceError, match='select'):
        voices.required(CFG, source=source, selection=target)


def recorded(clips, skip=()):
    return {clip.id: {'seconds': 1.5, 'personality': clip.personality, 'kind': clip.kind, 'text': clip.text}
            for clip in clips if clip.id not in skip}


def test_voice_data_lists_only_playable_recorded_lines(voices, tmp_path, monkeypatch):
    monkeypatch.setattr(voices.personalities, 'REACTION_VOICES', ('dwarf',))
    source, target, sample_dir = fake_captions(voices, tmp_path / 'c'), tmp_path / 's', tmp_path / 'Voices'
    voices.select(CFG, source=source, target=target)
    clips = voices.required(CFG, source=source, selection=target)
    sample_dir.mkdir()
    in_addon = [clip for clip in clips if clip.tier == 1][:-1]  # one sample clip not copied yet
    for clip in in_addon:
        (sample_dir / f'{clip.id}.ogg').write_bytes(b'ogg')
    unrecorded = next(clip for clip in clips if clip.tier == 2 and clip.kind == 'f')
    text = voices.render(CFG, clips, recorded(clips, {unrecorded.id}), sample_dir)
    lua = lupa.LuaRuntime()
    lua.execute(text)
    data = lua.globals().WoWStatusVoiceData
    assert data.pack.url == 'https://github.com/owner/repo/releases/download/voice-pack/WoWStatus_Voices.zip'
    tier1 = sum(1 for kind in data.lines.dwarf.values() for entry in kind.values() if entry[2] == 1)
    assert tier1 == len(in_addon)
    assert data.lines.dwarf.f[unrecorded.index] is None
    assert len(list(data.numbers.dwarf.values())) == 59 and data.lines.dwarf.level is not None
    # Without every number, level lines cannot play and are left out.
    some_number = next(clip for clip in clips if clip.kind == 'number')
    lua.execute(voices.render(CFG, clips, recorded(clips, {some_number.id}), sample_dir))
    assert lua.globals().WoWStatusVoiceData.lines.dwarf.level is None


def test_generate_records_only_missing_clips_and_pack_holds_the_pack_tier(voices, tmp_path, monkeypatch):
    monkeypatch.setattr(voices.personalities, 'REACTION_VOICES', ('dwarf',))
    source, target = fake_captions(voices, tmp_path / 'c'), tmp_path / 'selection'
    voices.select(CFG, source=source, target=target)
    monkeypatch.setattr(voices, 'CAPTIONS', source)
    monkeypatch.setattr(voices, 'SELECTION', target)
    monkeypatch.setattr(voices, 'CLIPS', tmp_path / 'clips.json')
    monkeypatch.setattr(voices, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(voices, 'SAMPLE_DIR', tmp_path / 'addon' / 'Voices')
    tts = load('voice_samples')
    monkeypatch.setitem(sys.modules, 'voice_samples', tts)
    said = []
    monkeypatch.setattr(tts, 'api_key', lambda: 'test-key')
    monkeypatch.setattr(tts, 'synthesize', lambda text, *rest: said.append(text) or b'\x10\x27' * 2400)

    def encode(pcm, rate, flac, clip, quality):
        for path in (flac, clip):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'audio')
    monkeypatch.setattr(voices, 'encode', encode)
    assert voices.main(['generate', '--workers', '2', '--limit', '5']) == 0
    assert len(said) == 5
    assert voices.main(['generate', '--workers', '2']) == 0
    clips = voices.required(CFG)
    assert len(said) == len(clips) and len(set(said)) <= len(clips)
    known = json.loads((tmp_path / 'clips.json').read_text(encoding='utf-8'))['clips']
    assert set(known) == {clip.id for clip in clips}
    assert voices.main(['generate']) == 0 and len(said) == len(clips)  # nothing left to record
    assert voices.main(['sample']) == 0
    tier1 = {clip.id for clip in clips if clip.tier == 1}
    assert {path.stem for path in (tmp_path / 'addon' / 'Voices').glob('*.ogg')} == tier1
    pack_path, masters_path = voices.pack(CFG, 4)  # one personality: one masters ZIP
    assert masters_path.name == 'voices-masters-dwarf.zip'
    with zipfile.ZipFile(pack_path) as archive:
        names = set(archive.namelist())
        assert 'WoWStatus_Voices/WoWStatus_Voices.toc' in names and 'WoWStatus_Voices/Pack.lua' in names
        sounds = {Path(name).stem for name in names if name.endswith('.ogg')}
        assert sounds == {clip.id for clip in clips if clip.tier == 2}
        toc = archive.read('WoWStatus_Voices/WoWStatus_Voices.toc').decode('utf-8')
        assert '## Interface: 16001' in toc and '## Version: 4' in toc
        assert 'version = 4' in archive.read('WoWStatus_Voices/Pack.lua').decode('utf-8')
    with zipfile.ZipFile(masters_path) as archive:
        assert len([n for n in archive.namelist() if n.endswith('.flac')]) == len(clips)


def test_release_refuses_when_someone_made_a_newer_pack(voices, monkeypatch, tmp_path):
    monkeypatch.setattr(voices, 'CLIPS', tmp_path / 'clips.json')
    voices.write_json(tmp_path / 'clips.json', {'release': 'voice-pack-v2', 'clips': {}})
    monkeypatch.setattr(voices, 'gh', lambda *args: json.dumps([{'tagName': 'voice-pack-v2'},
                                                                 {'tagName': 'voice-pack-v3'},
                                                                 {'tagName': 'v1.2.0'}]))
    with pytest.raises(voices.VoiceError, match='voice-pack-v3 exists'):
        voices.release(CFG, force=False)


def test_committed_voice_data_matches_the_choices_and_recordings(voices):
    cfg = voices.config()
    text = voices.render(cfg, voices.required(cfg), voices.registry()['clips'])
    assert voices.DATA_LUA.read_text(encoding='utf-8') == text, 'run python scripts/voices.py build'
    # Every clip that ships inside the addon is listed, and nothing else is there.
    listed = set(__import__('re').findall(r'\{"([0-9a-f]{12})", 1\}', text))
    present = {path.stem for path in voices.SAMPLE_DIR.glob('*.ogg')}
    assert listed == present
    for pid in cfg['personalities']:
        assert pid in voices.personalities.REACTION_VOICES, pid


def test_the_forever_zip_carries_the_voice_clips_and_nothing_else(tmp_path):
    builder = load('build_homepage')
    toc = 'Safe.lua\nVoices.lua\n'
    tracked = {'WoWStatus.toc', 'Safe.lua', 'Voices.lua', 'Sounds/Voices/0123456789ab.ogg',
               'Sounds/Voices/notes.txt', 'Sounds/other.ogg', 'Sounds/Voices/0123456789AB.OGG'}
    assert builder.package_files(toc, tracked) == ['Safe.lua', 'Sounds/Voices/0123456789ab.ogg',
                                                    'Voices.lua', 'WoWStatus.toc']


def test_one_failed_clip_is_reported_and_the_rest_are_still_recorded(voices, tmp_path, monkeypatch):
    monkeypatch.setattr(voices.personalities, 'REACTION_VOICES', ('dwarf',))
    source, target = fake_captions(voices, tmp_path / 'c'), tmp_path / 'selection'
    voices.select(CFG, source=source, target=target)
    for name, value in (('CAPTIONS', source), ('SELECTION', target), ('CLIPS', tmp_path / 'clips.json'),
                        ('CACHE', tmp_path / 'cache'), ('SAMPLE_DIR', tmp_path / 'Voices')):
        monkeypatch.setattr(voices, name, value)
    tts = load('voice_samples')
    monkeypatch.setitem(sys.modules, 'voice_samples', tts)
    monkeypatch.setattr(tts, 'api_key', lambda: 'test-key')
    bad = voices.required(CFG)[3].text

    def synthesize(text, *rest):
        if text == bad:
            raise SystemExit('HTTP 400 from Google: refused')
        return b'\x10\x27' * 2400
    monkeypatch.setattr(tts, 'synthesize', synthesize)
    monkeypatch.setattr(voices, 'encode', lambda pcm, rate, flac, clip, quality: None)
    assert voices.main(['generate', '--workers', '3']) == 1
    known = json.loads((tmp_path / 'clips.json').read_text(encoding='utf-8'))['clips']
    assert len(known) == len(voices.required(CFG)) - 1
    assert all(entry['text'] != bad for entry in known.values())
