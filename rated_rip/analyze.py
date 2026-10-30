"""Replay 16-bit PCM WAV files through the detector without lighting hardware."""
import argparse
from contextlib import ExitStack
from dataclasses import asdict
import json
import time
import wave

import numpy as np

from .engine import Analyzer


def analyze(path, output, vocal_output=None):
    started = time.perf_counter()
    counts = dict(onset=0, bands=0, body=0, tail=0)
    with wave.open(str(path), 'rb') as source:
        if (source.getsampwidth() != 2 or source.getnchannels() not in (1, 2)
                or source.getframerate() not in (44100, 48000) or source.getcomptype() != 'NONE'):
            raise ValueError('Use uncompressed 16-bit PCM WAV, mono/stereo, at 44100 or 48000 Hz')
        analyzer = Analyzer(source.getframerate(), vocals=vocal_output is not None)
        channels = source.getnchannels()
        duration = source.getnframes() / analyzer.rate
        discarded = 0
        last_vocal_time = 0.0
        vocal_updates = 0
        while True:
            raw = source.readframes(analyzer.size)
            if len(raw) != analyzer.size * channels * 2:
                discarded = len(raw) // (channels * 2)
                break
            samples = np.frombuffer(raw, dtype='<i2').reshape(-1, channels).astype(float) / 32768
            features = analyzer.process(samples)
            for attack in features.attacks:
                output.write(json.dumps(dict(asdict(attack), layered_evidence=attack.layered)) + '\n')
                counts[attack.stage] += 1
            if vocal_output is not None and features.vocal.time > last_vocal_time:
                vocal_output.write(json.dumps(asdict(features.vocal)) + '\n')
                last_vocal_time = features.vocal.time
                vocal_updates += 1
    return dict(duration_seconds=duration, processing_seconds=time.perf_counter() - started,
                events=counts, unfinished_events=len(analyzer.detector.pending),
                trailing_samples_not_analyzed=discarded, vocal_updates=vocal_updates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav')
    parser.add_argument('--output', required=True, help='New JSONL file; existing files are preserved')
    parser.add_argument('--vocal-output', help='Also write experimental vocal/phrase cues to a new JSONL file')
    args = parser.parse_args()
    try:
        with ExitStack() as stack:
            output = stack.enter_context(open(args.output, 'x', encoding='utf-8'))
            vocal_output = (stack.enter_context(open(args.vocal_output, 'x', encoding='utf-8'))
                            if args.vocal_output else None)
            summary = analyze(args.wav, output, vocal_output)
    except (OSError, ValueError, wave.Error) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
