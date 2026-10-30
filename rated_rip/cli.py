import argparse
import json
import math
import shutil
import signal
import subprocess
import time
from dataclasses import asdict

import numpy as np

from . import __version__
from .dmx import EnttecPro, universe
from .engine import Analyzer, Lighting


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise RuntimeError("Audio capture ended before a complete block")
        data.extend(chunk)
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description="Live audio-reactive three-fixture RGB lighting")
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--simulate', action='store_true', help='Synthetic audio; no ALSA hardware needed')
    parser.add_argument('--device', default='default', help='ALSA capture device, e.g. plughw:CARD=USB,DEV=0')
    parser.add_argument('--rate', type=int, default=44100)
    parser.add_argument('--channels', type=int, choices=[1, 2], default=2)
    parser.add_argument('--duration', type=float, default=0, help='Seconds; 0 runs until Ctrl-C')
    parser.add_argument('--dmx-port', help='Explicitly enable ENTTEC USB Pro-compatible output')
    parser.add_argument('--addresses', type=int, nargs=3, default=[1, 5, 9],
                        help='DMX start addresses (default: 1 5 9)')
    parser.add_argument('--brightness', type=float, default=0.65)
    parser.add_argument('--scheme', choices=('auto',) + Lighting.SCHEMES, default='auto',
                        help='Lighting scheme; auto rotates through all four (default)')
    parser.add_argument('--scheme-seconds', type=float, default=150,
                        help='Audible seconds before requesting the next scheme (default: 150, minimum: 5)')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--attack-log', help='Write attack descriptors to a new JSONL file (no audio)')
    parser.add_argument('--vocal-log', help='Write experimental vocal/phrase cues to a new JSONL file')
    parser.add_argument('--no-vocals', action='store_true', help='Disable experimental vocal analysis and lighting')
    args = parser.parse_args()
    if args.no_vocals and args.vocal_log:
        parser.error('--vocal-log requires vocal analysis; omit --no-vocals')
    if args.rate not in (44100, 48000) or args.duration < 0 or not 0 <= args.brightness <= 1:
        parser.error('Use rate 44100 or 48000, duration >= 0, and brightness 0..1')
    if not math.isfinite(args.scheme_seconds) or args.scheme_seconds < 5:
        parser.error('--scheme-seconds must be finite and at least 5')
    try:
        universe([(0, 0, 0)] * 3, args.addresses)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.simulate and not shutil.which('arecord'):
        parser.error('Live capture requires ALSA arecord: install alsa-utils')
    analyzer = Analyzer(args.rate, vocals=not args.no_vocals)
    lighting = Lighting(args.seed, args.brightness, args.scheme, args.scheme_seconds)
    capture = output = attack_log = vocal_log = None
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True
        if capture is not None:
            capture.terminate()

    old_handlers = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    dt = analyzer.size / args.rate
    tick = 0
    started = time.monotonic()
    last_send = last_report = -1.0
    last_vocal_time = 0.0
    rng = np.random.default_rng(args.seed)
    try:
        if args.attack_log:
            attack_log = open(args.attack_log, 'x', encoding='utf-8')
        if args.vocal_log:
            vocal_log = open(args.vocal_log, 'x', encoding='utf-8')
        if args.dmx_port:
            output = EnttecPro(args.dmx_port)
        if not args.simulate:
            capture = subprocess.Popen(['arecord', '-q', '-D', args.device, '-t', 'raw',
                                        '--buffer-time=50000', '--period-time=10000',
                                        '-f', 'S16_LE', '-r', str(args.rate), '-c', str(args.channels)],
                                       stdout=subprocess.PIPE)
        while not stopped and (not args.duration or tick * dt < args.duration):
            if args.simulate:
                t = (np.arange(analyzer.size) + tick * analyzer.size) / args.rate
                pulse = np.exp(-((t % 0.5) / 0.035))
                noise = np.diff(rng.standard_normal(analyzer.size + 1))
                snare = np.exp(-(((t - 0.5) % 1.0) / 0.03))
                hat = np.exp(-(((t + 0.0625) % 0.125) / 0.012))
                samples = 0.45 * pulse * np.sin(2 * math.pi * 90 * t)
                samples += noise * (0.12 * snare + 0.02 * hat)
            else:
                raw = read_exact(capture.stdout, analyzer.size * args.channels * 2)
                audio = np.frombuffer(raw, dtype='<i2').reshape(-1, args.channels).astype(float) / 32768
                samples = audio
            features = analyzer.process(samples)
            if attack_log:
                for attack in features.attacks:
                    attack_log.write(json.dumps(dict(asdict(attack), layered_evidence=attack.layered)) + '\n')
            if vocal_log and features.vocal.time > last_vocal_time:
                vocal_log.write(json.dumps(asdict(features.vocal)) + '\n')
                last_vocal_time = features.vocal.time
            rgb = lighting.update(features, dt)
            elapsed = time.monotonic() - started
            if output and elapsed - last_send >= 1 / 30:
                output.send(universe(rgb, args.addresses))
                last_send = elapsed
            if elapsed - last_report >= 1:
                print(json.dumps({'rms': round(features.rms, 4), 'loudness': round(features.loudness, 3),
                                  'density': round(features.density, 3), 'attacks': lighting.beats,
                                  'vocal_score': round(features.vocal.score, 3),
                                  'vocal_active': features.vocal.active, 'scheme': lighting.scheme,
                                  'scheme_changes': lighting.scheme_changes, 'rgb': rgb}), flush=True)
                last_report = elapsed
            tick += 1
            if args.simulate:
                time.sleep(max(0, started + tick * dt - time.monotonic()))
    except (OSError, RuntimeError) as exc:
        if not stopped:
            parser.exit(1, f'Error: {exc}\n')
    finally:
        if capture is not None:
            if capture.poll() is None:
                capture.terminate()
            try:
                capture.wait(timeout=2)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait()
            capture.stdout.close()
        try:
            if output is not None:
                output.close()
        finally:
            if attack_log is not None:
                attack_log.close()
            if vocal_log is not None:
                vocal_log.close()
            for s, handler in old_handlers.items():
                signal.signal(s, handler)


if __name__ == '__main__':
    main()
