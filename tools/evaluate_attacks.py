"""Reproducible synthetic timing evaluation; not a commercial-music benchmark."""
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_attacks import detect, fixture


def main():
    results = []
    for rate in (44100, 48000):
        schedule = [(float(p), ['low', 'mid', 'high'][i % 3])
                    for i, p in enumerate(np.arange(0.5, 9.5, 0.125))]
        base = fixture(rate, schedule, duration=10)
        t = np.arange(len(base)) / rate
        cases = [('isolated', base), ('quiet', base * 0.1),
                 ('with_tonal_bed', base + 0.035 * np.sin(2 * np.pi * 330 * t)),
                 ('limited_mix', np.clip(base * 3, -0.65, 0.65))]
        for name, audio in cases:
            begin = time.perf_counter()
            reports = detect(audio, rate)
            elapsed = time.perf_counter() - begin
            onsets = [e for e in reports if e.stage == 'onset']
            matched, used = [], set()
            for target, _ in schedule:
                choices = [(abs(e.time - target), i, e) for i, e in enumerate(onsets)
                           if i not in used and abs(e.time - target) < 0.025]
                if choices:
                    _, index, event = min(choices)
                    used.add(index)
                    matched.append((event.reported_at - target) * 1000)
            results.append(dict(rate=rate, case=name, expected=len(schedule), matched=len(matched),
                                extra=len(onsets) - len(used),
                                detection_delay_ms_max=round(max(matched), 2) if matched else None,
                                processing_seconds=round(elapsed, 3)))
    print(json.dumps(dict(machine=platform.machine(), results=results), indent=2))
    return 0 if all(r['matched'] == r['expected'] and r['extra'] == 0 for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
