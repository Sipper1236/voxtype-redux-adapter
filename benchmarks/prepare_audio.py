#!/usr/bin/env python3
"""Download the public dummy LibriSpeech corpus and recreate benchmark WAVs.

Requires numpy, pyarrow and soundfile. No model or inference is involved.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
CORPUS_URL = ('https://huggingface.co/datasets/hf-internal-testing/'
              'librispeech_asr_dummy/resolve/main/clean/validation-00000-of-00001.parquet')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-reference', action='store_true',
                        help='Compare generated hashes/durations with docs/audio-manifest.json')
    args = parser.parse_args()
    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf

    out = Path(os.environ.get('VOXTYPE_BENCH_AUDIO_DIR', str(ROOT / 'audio'))).resolve()
    out.mkdir(parents=True, exist_ok=True)
    corpus = out / 'librispeech.parquet'
    if not corpus.exists():
        temporary = corpus.with_suffix('.parquet.download')
        try:
            with urllib.request.urlopen(CORPUS_URL, timeout=120) as source, temporary.open('wb') as dest:
                import shutil
                shutil.copyfileobj(source, dest)
            temporary.replace(corpus)
        finally:
            temporary.unlink(missing_ok=True)
    clips = []
    for row in pq.read_table(corpus).to_pylist():
        audio, rate = sf.read(io.BytesIO(row['audio']['bytes']), dtype='float32')
        if rate != 16000 or audio.ndim != 1:
            raise ValueError('source corpus must contain mono 16 kHz audio')
        clips.append({'id': row['id'], 'text': row['text'], 'audio': audio,
                      'seconds': len(audio) / rate})
    manifest = []
    # Preserve the original whole-utterance largest-first packing and noise sequence.
    for target in [5, 15, 30, 60, 120]:
        if target == 5:
            chosen = [min(clips, key=lambda x: abs(x['seconds'] - target))]
        else:
            chosen, remaining = [], target
            for clip in sorted(clips, key=lambda x: -x['seconds']):
                overhead = .2 if chosen else 0
                if clip['seconds'] + overhead <= remaining:
                    chosen.append(clip)
                    remaining -= clip['seconds'] + overhead
        pieces = []
        for clip in chosen:
            if pieces:
                pieces.append(np.zeros(3200, dtype=np.float32))
            pieces.append(clip['audio'])
        audio = np.concatenate(pieces)
        file = out / f'clean-{target}s.wav'
        sf.write(file, audio, 16000, subtype='PCM_16')
        entry = {'id': f'clean-{target}s', 'file': file.name, 'seconds': len(audio) / 16000,
                 'reference': ' '.join(x['text'] for x in chosen),
                 'utterances': [x['id'] for x in chosen],
                 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
        manifest.append(entry)
        if target == 30:
            noise = np.random.default_rng(42).normal(size=len(audio))
            noise *= np.sqrt(np.mean(audio**2)) / np.sqrt(np.mean(noise**2)) / 10
            noisy = audio + noise
            noisy /= max(1., np.max(np.abs(noisy)))
            file = out / 'noise-30s-20db.wav'
            sf.write(file, noisy, 16000, subtype='PCM_16')
            manifest.append(dict(entry, id='noise-30s-20db', file=file.name,
                                 sha256=hashlib.sha256(file.read_bytes()).hexdigest(), snr_db=20))
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if args.verify_reference:
        reference = json.loads((ROOT.parent / 'docs/audio-manifest.json').read_text())
        expected = {entry['id']: entry for entry in reference}
        mismatches = []
        if set(expected) != {entry['id'] for entry in manifest}:
            mismatches.append('case IDs differ')
        for entry in manifest:
            previous = expected.get(entry['id'], {})
            for key in ('sha256', 'seconds'):
                if entry[key] != previous.get(key):
                    mismatches.append(f"{entry['id']}: {key} differs")
        if mismatches:
            raise SystemExit('Reference verification failed: ' + '; '.join(mismatches))
        print('Reference hashes and durations match.')
    print('Manifest:', out / 'manifest.json')
    print([(x['id'], round(x['seconds'], 3), len(x['reference'].split())) for x in manifest])


if __name__ == '__main__':
    main()
