#!/usr/bin/env python3
"""Generate the reaction voice samples in docs/voice-samples/samples.json.

Each sample is stitched from pieces (opener, body, closer) that are generated
one request at a time with Google's Gemini TTS models, just as the voice pack
would play them in game. Listening aid only: nothing here is packaged into
the addon.

Models:
  * gemini-3.8-flash-tts (default) and gemini-3.8-flash-lite-tts go through
    the Gemini API with an API key (an AI Studio key works), or through the
    project's Agent Platform endpoint with --gcloud;
  * older models (gemini-3.1-flash-tts-preview, gemini-2.5-*-tts) go through
    the Cloud Text-to-Speech API (Cloud Text-to-Speech API enabled).

Authentication, first match wins:
  * GOOGLE_API_KEY in the environment or in the repository's .env file
    (ignored by Git);
  * --gcloud: an access token from `gcloud auth print-access-token`, billed to
    --project.

    python scripts/voice_samples.py --dry-run
    python scripts/voice_samples.py --whole
    python scripts/voice_samples.py --model gemini-3.8-flash-lite-tts

Output goes to dist/voice-samples/<model>/ (ignored by Git): a WAV per sample,
an MP3 at the bitrate a voice pack would use (needs ffmpeg) and
manifest.json with every piece's duration.
"""
from __future__ import annotations

import argparse
import array
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / 'docs' / 'voice-samples' / 'samples.json'
OUTPUT = ROOT / 'dist' / 'voice-samples'
CLOUD_TTS = 'https://texttospeech.googleapis.com/v1/text:synthesize'
AGENT_PLATFORM = 'https://aiplatform.googleapis.com/v1'
GEMINI_API = 'https://generativelanguage.googleapis.com/v1beta'
RATE = 24000
# USD per million audio tokens (25 tokens per second of audio), from Google's
# Cloud TTS pricing page, 8 November 2026 (3.8 prices double from 2027).
# Text input tokens cost far less.
AUDIO_PRICE = {
    'gemini-3.8-flash-tts': 9.0,
    'gemini-3.8-flash-lite-tts': 6.0,
    'gemini-2.5-flash-tts': 10.0,
    'gemini-2.5-flash-lite-preview-tts': 10.0,
    'gemini-2.5-pro-tts': 20.0,
    'gemini-3.1-flash-tts-preview': 20.0,
}


def api_key() -> str | None:
    key = os.environ.get('GOOGLE_API_KEY')
    if key:
        return key.strip()
    for env in (ROOT / '.env', main_checkout() / '.env'):
        if env.is_file():
            for line in env.read_text(encoding='utf-8').splitlines():
                name, _, value = line.partition('=')
                if name.strip() == 'GOOGLE_API_KEY' and value.strip():
                    return value.strip().strip('"').strip("'")
    return None


def main_checkout() -> Path:
    """The main checkout, whose .env a Git worktree of it can share."""
    result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                            capture_output=True, text=True, encoding='utf-8', check=False)
    return Path(result.stdout.strip()).parent if result.returncode == 0 and result.stdout.strip() else ROOT


def gcloud_token() -> str:
    gcloud = shutil.which('gcloud')
    if not gcloud:
        sys.exit('gcloud is not installed; set GOOGLE_API_KEY instead.')
    result = subprocess.run([gcloud, 'auth', 'print-access-token'], capture_output=True,
                            text=True, encoding='utf-8', check=False)
    if result.returncode != 0:
        sys.exit('gcloud auth print-access-token failed; run gcloud auth login first.')
    return result.stdout.strip()


def is_38(model: str) -> bool:
    return model.startswith('gemini-3.8-')


def request_for(text: str, prompt: str, voice: str, model: str, language: str | None,
                project: str | None) -> tuple[str, dict]:
    if is_38(model):
        # Agent Platform generateContent; 3.8 writes vocal tags in angle brackets.
        text = re.sub(r'\[([a-z ]+)\]', r'<\1>', text)
        speech = {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}}
        if language:
            speech['languageCode'] = language
        # An API key (such as an AI Studio key) goes to the Gemini API; gcloud
        # credentials go to the project's Agent Platform endpoint.
        url = (f'{AGENT_PLATFORM}/projects/{project}/locations/global/publishers/google/models/{model}:generateContent'
               if project else f'{GEMINI_API}/models/{model}:generateContent')
        return url, {
            'contents': [{'role': 'user', 'parts': [{'text': text, 'speechMetadata': {'style': prompt}}]}],
            'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': speech},
        }
    voice_config = {'name': voice, 'model_name': model}
    if language:
        voice_config['languageCode'] = language
    return CLOUD_TTS, {
        'input': {'prompt': prompt, 'text': text},
        'voice': voice_config,
        'audioConfig': {'audioEncoding': 'LINEAR16', 'sampleRateHertz': RATE},
    }


def audio_from(model: str, reply: dict) -> bytes:
    if is_38(model):
        for part in reply['candidates'][0]['content']['parts']:
            if 'inlineData' in part:
                return base64.b64decode(part['inlineData']['data'])
        sys.exit(f'No audio in the reply: {json.dumps(reply)[:600]}')
    return base64.b64decode(reply['audioContent'])


def synthesize(text: str, prompt: str, voice: str, model: str, language: str | None,
               headers: dict, project: str | None) -> bytes:
    url, payload = request_for(text, prompt, voice, model, language, project)
    body = json.dumps(payload).encode('utf-8')
    for attempt in range(5):
        request = urllib.request.Request(url, data=body, method='POST',
                                         headers={'Content-Type': 'application/json', **headers})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return pcm(audio_from(model, json.loads(response.read().decode('utf-8'))))
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')
            if error.code in (429, 500, 502, 503, 504) and attempt < 4:
                wait = 2 ** attempt * 2
                print(f'  HTTP {error.code}, retrying in {wait} s', file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f'HTTP {error.code} from Google: {detail[:600]}')
    sys.exit('Google kept failing.')


def pcm(audio: bytes) -> bytes:
    """16-bit mono PCM at RATE, from a WAV response or raw LINEAR16."""
    if audio[:4] != b'RIFF':
        return audio
    with wave.open(io.BytesIO(audio)) as source:
        if (source.getsampwidth(), source.getnchannels(), source.getframerate()) != (2, 1, RATE):
            sys.exit('Unexpected audio format from Google.')
        return source.readframes(source.getnframes())


def trim(audio: bytes, threshold: int = 350, margin_ms: int = 30) -> bytes:
    samples = array.array('h', audio)
    if sys.byteorder != 'little':
        samples.byteswap()
    loud = [i for i, value in enumerate(samples) if abs(value) > threshold]
    if not loud:
        return audio
    margin = RATE * margin_ms // 1000
    start, end = max(0, loud[0] - margin), min(len(samples), loud[-1] + margin)
    return audio[start * 2:end * 2]


def write_wav(path: Path, audio: bytes) -> None:
    with wave.open(str(path), 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(audio)


def to_mp3(wav: Path, kbps: int) -> Path | None:
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return None
    mp3 = wav.with_suffix('.mp3')
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(wav),
                    '-af', 'loudnorm=I=-18:TP=-2:LRA=7', '-ac', '1', '-ar', '22050',
                    '-b:a', f'{kbps}k', str(mp3)], check=True)
    return mp3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--model', default='gemini-3.8-flash-tts', help='Gemini TTS model')
    parser.add_argument('--no-language', action='store_true',
                        help='leave out the nn-NO language code and let the model detect the language')
    parser.add_argument('--only', action='append', help='sample id to generate (repeatable)')
    parser.add_argument('--whole', action='store_true',
                        help='also render each sample as one request, to compare with the stitched pieces')
    parser.add_argument('--kbps', type=int, default=32, help='MP3 bitrate, as a voice pack would ship')
    parser.add_argument('--gcloud', action='store_true', help='authenticate with gcloud instead of an API key')
    parser.add_argument('--project', help='Google Cloud project to bill with --gcloud')
    parser.add_argument('--dry-run', action='store_true', help='print the requests and call nothing')
    args = parser.parse_args()

    data = json.loads(SAMPLES.read_text(encoding='utf-8'))
    samples = [s for s in data['samples'] if not args.only or s['id'] in args.only]
    gap = bytes(2 * RATE * data.get('gap_ms', 120) // 1000)

    if args.dry_run:
        headers = {}
    elif args.gcloud:
        if not args.project:
            sys.exit('--gcloud needs --project.')
        headers = {'Authorization': f'Bearer {gcloud_token()}', 'x-goog-user-project': args.project}
    else:
        key = api_key()
        if not key:
            sys.exit('Set GOOGLE_API_KEY (environment or .env), or use --gcloud --project <id>.')
        headers = {'x-goog-api-key': key}

    language = None if args.no_language else data['language_code']
    project = args.project if args.gcloud else None
    folder = OUTPUT / args.model
    if args.dry_run:
        first = samples[0]
        url, payload = request_for(first['pieces'][0], data['personalities'][first['personality']]['prompt'],
                                   data['personalities'][first['personality']]['voice'], args.model,
                                   language, project)
        print(f'POST {url}\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n')
    else:
        folder.mkdir(parents=True, exist_ok=True)
    manifest, total_seconds = [], 0.0
    for sample in samples:
        personality = data['personalities'][sample['personality']]
        prompt = personality['prompt'] + (' ' + sample['mood'] if sample.get('mood') else '')
        print(f"{sample['id']}  ({personality['voice']})")
        pieces, entry = [], {'id': sample['id'], 'voice': personality['voice'], 'pieces': []}
        renders = [(text, False) for text in sample['pieces']]
        if args.whole:
            renders.append((' '.join(sample['pieces']), True))
        whole = None
        for text, is_whole in renders:
            print(f'  {"whole" if is_whole else "piece"}: {text}')
            if args.dry_run:
                continue
            audio = trim(synthesize(text, prompt, personality['voice'], args.model,
                                    language, headers, project))
            seconds = len(audio) / 2 / RATE
            total_seconds += seconds
            if is_whole:
                whole = audio
            else:
                pieces.append(audio)
                entry['pieces'].append({'text': text, 'seconds': round(seconds, 3)})
        if args.dry_run:
            continue
        stitched = gap.join(pieces)
        path = folder / f"{sample['id']}.wav"
        write_wav(path, stitched)
        to_mp3(path, args.kbps)
        if whole is not None:
            whole_path = folder / f"{sample['id']}_whole.wav"
            write_wav(whole_path, whole)
            to_mp3(whole_path, args.kbps)
        entry['seconds'] = round(len(stitched) / 2 / RATE, 3)
        manifest.append(entry)

    if args.dry_run:
        print('Dry run: no requests sent.')
        return
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                                          encoding='utf-8')
    price = AUDIO_PRICE.get(args.model)
    cost = f'about ${total_seconds * 25 / 1e6 * price:.4f} in audio tokens' if price else 'price unknown for this model'
    print(f'Wrote {len(manifest)} samples to {folder} ({total_seconds:.1f} s of audio, {cost}).')


if __name__ == '__main__':
    main()
