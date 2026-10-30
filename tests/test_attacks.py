from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from rated_rip.analyze import analyze
from rated_rip.attacks import describe
from rated_rip.engine import Analyzer, Features, Lighting


def burst(rate, kind='low', duration=0.18, decay=0.035):
    t = np.arange(round(rate * duration)) / rate
    if kind == 'low':
        signal = np.sin(2 * np.pi * 80 * t)
    else:
        noise = np.random.default_rng(12).normal(size=len(t))
        spectrum = np.fft.rfft(noise)
        frequencies = np.fft.rfftfreq(len(t), 1 / rate)
        limits = (500, 3000) if kind == 'mid' else (6000, 14000)
        spectrum[(frequencies < limits[0]) | (frequencies > limits[1])] = 0
        signal = np.fft.irfft(spectrum, n=len(t))
        signal /= np.max(np.abs(signal))
    return 0.6 * signal * np.minimum(t / 0.001, 1) * np.exp(-t / decay)


def fixture(rate, events, duration=2):
    audio = np.zeros(round(duration * rate))
    for start, kind in events:
        sample = burst(rate, kind)
        index = round(start * rate)
        count = min(len(sample), len(audio) - index)
        audio[index:index + count] += sample[:count]
    return audio


def detect(audio, rate=44100):
    analyzer = Analyzer(rate)
    result = []
    for start in range(0, len(audio) - analyzer.size + 1, analyzer.size):
        result.extend(analyzer.process(audio[start:start + analyzer.size]).attacks)
    return result


class AttackTests(unittest.TestCase):
    def test_isolated_attacks_have_fast_then_30_and_90_ms_reports(self):
        for rate in (44100, 48000):
            for kind in ('low', 'mid', 'high'):
                with self.subTest(rate=rate, kind=kind):
                    events = detect(fixture(rate, [(0.3, kind)]), rate)
                    self.assertEqual([e.stage for e in events], ['onset', 'body', 'tail'])
                    self.assertEqual(len({e.id for e in events}), 1)
                    onset, body, tail = events
                    self.assertLess(abs(onset.time - 0.3), 0.02)
                    self.assertGreaterEqual(onset.reported_at, 0.3)
                    self.assertLess(onset.reported_at - 0.3, 0.035)
                    self.assertIn(kind, tail.bands)
                    index = ('low', 'mid', 'high').index(kind)
                    self.assertGreater(tail.energy[index], 0.8)
                    self.assertGreaterEqual(body.reported_at - body.time, 0.03)
                    self.assertLess(body.reported_at - body.time, 0.03 + 256 / rate)
                    self.assertGreaterEqual(tail.reported_at - tail.time, 0.09)
                    self.assertLess(tail.reported_at - tail.time, 0.09 + 256 / rate)

    def test_rapid_hits_no_long_global_lockout(self):
        positions = np.arange(0.3, 2.3, 0.1)
        for rate in (44100, 48000):
            audio = fixture(rate, [(p, 'low') for p in positions], duration=2.6)
            onsets = [e for e in detect(audio, rate) if e.stage == 'onset']
            self.assertGreaterEqual(len(onsets), len(positions) - 1)
            self.assertLessEqual(len(onsets), len(positions) + 1)
            for position in positions:
                self.assertTrue(any(abs(e.time - position) < 0.025 for e in onsets))

    def test_simultaneous_low_high_is_one_event_with_two_components(self):
        events = detect(fixture(44100, [(0.3, 'low'), (0.3, 'high')]))
        self.assertEqual(sum(e.stage == 'onset' for e in events), 1)
        tail = events[-1]
        self.assertIn('low', tail.bands)
        self.assertIn('high', tail.bands)
        # Bandlimited noise has less RMS than the sine; compare useful evidence,
        # not an exact instrument classification.
        self.assertGreater(tail.energy[0], 0.2)
        self.assertGreater(tail.energy[2], 0.05)

    def test_close_different_band_hits_remain_separate_and_mark_overlap(self):
        events = detect(fixture(44100, [(0.3, 'low'), (0.34, 'high')]))
        onsets = [e for e in events if e.stage == 'onset']
        self.assertEqual(len(onsets), 2)
        self.assertLess(onsets[1].time - onsets[0].time, 0.06)
        self.assertTrue(all(e.overlapped for e in events if e.stage == 'tail'))

    def test_nearby_band_peaks_update_one_event_and_balanced_layers_have_evidence(self):
        events = detect(fixture(44100, [(0.3, 'low'), (0.31, 'high')]))
        self.assertEqual(sum(e.stage == 'onset' for e in events), 1)
        self.assertEqual(len({e.id for e in events}), 1)
        self.assertTrue(any(e.stage == 'bands' and 'high' in e.bands for e in events))
        audio = fixture(44100, [(0.3, 'low')]) + 2 * fixture(44100, [(0.3, 'high')])
        audio *= 0.8 / np.max(np.abs(audio))
        tail = detect(audio)[-1]
        self.assertTrue(tail.layered)
        self.assertFalse(detect(fixture(44100, [(0.3, 'low')]))[-1].layered)

    def test_sustained_tone_vibrato_and_noise_do_not_keep_retriggering(self):
        rate = 44100
        t = np.arange(rate * 3) / rate
        ramp = np.minimum(t / 0.3, 1)
        signals = [0.2 * np.sin(2 * np.pi * 440 * t) * ramp,
                   0.2 * np.sin(2 * np.pi * 440 * t + 2 * np.sin(2 * np.pi * 5 * t)) * ramp,
                   np.random.default_rng(15).normal(0, 0.1, len(t)) * ramp]
        for signal in signals:
            events = detect(signal)
            self.assertEqual([e for e in events if e.stage == 'onset' and e.time > 0.7], [])

    def test_antiphase_stereo_and_swapping_channels_preserve_attack_times(self):
        mono = fixture(44100, [(0.3, 'low'), (0.8, 'high')])
        antiphase = np.column_stack([mono, -mono])
        left = np.column_stack([mono, mono * 0.3])
        baseline = [e.time for e in detect(mono) if e.stage == 'onset']
        for signal in (antiphase, left, left[:, ::-1]):
            times = [e.time for e in detect(signal) if e.stage == 'onset']
            np.testing.assert_allclose(times, baseline, atol=256 / 44100)

    def test_clipped_shape_is_measured_even_below_full_scale(self):
        rate = 44100
        t = np.arange(round(rate * 0.09)) / rate
        clean = 0.8 * np.sin(2 * np.pi * 500 * t)
        limited = np.clip(clean * 4, -0.8, 0.8)
        a, b = describe(clean, rate), describe(limited, rate)
        self.assertGreater(b['plateau_fraction'], a['plateau_fraction'] + 0.5)
        self.assertLess(b['crest_db'], a['crest_db'])
        self.assertEqual(b['near_full_scale_fraction'], 0)
        self.assertGreater(describe(limited * 1.25, rate)['near_full_scale_fraction'], 0.5)

    def test_tonal_vs_noisy_attack_character(self):
        rate = 44100
        low = describe(burst(rate, 'low')[:round(rate * 0.03)], rate)
        high = describe(burst(rate, 'high')[:round(rate * 0.03)], rate)
        self.assertGreater(high['centroid_hz'], low['centroid_hz'] + 4000)
        self.assertGreater(high['flatness'], low['flatness'])

    def test_invalid_input_is_rejected(self):
        a = Analyzer()
        for audio in (np.zeros(255), np.full(256, np.nan), np.zeros((256, 3))):
            with self.assertRaises(ValueError):
                a.process(audio)
        a.process(np.zeros((256, 2)))
        with self.assertRaises(ValueError):
            a.process(np.zeros(256))

    def test_percussion_evidence_separates_decay_from_sustained_harmony(self):
        for rate in (44100, 48000):
            t = np.arange(rate * 2) / rate
            chord = sum(np.sin(2 * np.pi * f * t) / (i + 1)
                        for i, f in enumerate([160, 320, 480, 640, 800])) * 0.15
            swell = chord * np.clip((t - 0.3) / 0.1, 0, 1) * np.clip((1.6 - t) / 0.2, 0, 1)
            harmonic = [e for e in detect(swell, rate) if e.stage == 'tail'][0]
            self.assertLess(harmonic.percussiveness, 0.5)
            for kind in ('low', 'mid', 'high'):
                with self.subTest(rate=rate, kind=kind):
                    events = detect(fixture(rate, [(0.3, kind)]), rate)
                    tail = events[-1]
                    self.assertGreater(tail.percussiveness, harmonic.percussiveness + 0.2)
                    self.assertLess(events[0].reported_at - 0.3, 0.035)
                    self.assertTrue(all(0 <= e.percussiveness <= 1 for e in events))
            limited = np.clip(4 * fixture(rate, [(0.3, 'low')]), -0.4, 0.4)
            self.assertGreater(detect(limited, rate)[-1].percussiveness,
                               harmonic.percussiveness + 0.1)

    def test_percussion_evidence_is_stereo_phase_safe(self):
        audio = fixture(44100, [(0.3, 'low'), (0.8, 'mid')])
        mono = detect(audio)
        stereo = detect(np.column_stack([audio, -audio]))
        np.testing.assert_allclose([e.percussiveness for e in mono],
                                   [e.percussiveness for e in stereo], atol=1e-8)

    def test_weak_percussion_gives_a_gentler_spatial_accent(self):
        event = detect(fixture(44100, [(0.3, 'low')]))[0]
        output = []
        for score in (0.15, 0.9):
            light = Lighting(seed=7)
            attack = replace(event, percussiveness=score)
            rgb = light.update(Features(0.1, 0.25, 0.2, True, (attack,)), 256 / 44100)
            output.append(max(rgb[1]) - max(rgb[0]))
            age = light.voices[event.id]['age']
            light.update(Features(0.1, 0.25, 0.2, False,
                                  (replace(attack, stage='tail', percussiveness=0.1),)), 0.09)
            self.assertGreater(light.voices[event.id]['age'], age)
            self.assertEqual(light.beats, 1)
        self.assertLess(output[0], output[1] / 3)

    def test_lighting_routes_bands_and_updates_do_not_retrigger(self):
        event = [e for e in detect(fixture(44100, [(0.3, 'low')])) if e.stage == 'onset'][0]
        light = Lighting(seed=3)
        f = Features(0.1, 0.25, 0.2, True, (replace(event, bands=('low',)),))
        rgb = light.update(f, 256 / 44100)
        self.assertGreater(max(rgb[1]), max(rgb[0]))
        light.update(Features(0.1, 0.25, 0.2, False), 0.03)
        before = light.voices[event.id]['age']
        update = replace(event, stage='body', bands=('low', 'high'))
        light.update(Features(0.1, 0.25, 0.2, False, (update,)), 0.006)
        self.assertEqual(light.beats, 1)
        self.assertGreater(light.voices[event.id]['age'], before)
        for i in range(300):
            update = replace(event, id=i + 2, bands=('low', 'mid', 'high'))
            rgb = light.update(Features(1, 1, 1, True, (update,)), 0.01)
            self.assertTrue(all(0 <= c <= round(255 * light.brightness) for fixture in rgb for c in fixture))
        for _ in range(200):
            rgb = light.update(Features(0, 0, 0, False), 0.01)
        self.assertEqual(rgb, [(0, 0, 0)] * 3)

    def test_wav_replay_writes_valid_serializable_reports(self):
        audio = fixture(44100, [(0.3, 'low'), (0.8, 'high')])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes((audio * 32767).astype('<i2').tobytes())
            output = io.StringIO()
            summary = analyze(path, output)
        reports = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(summary['events'], dict(onset=2, bands=0, body=2, tail=2))
        self.assertEqual(len(reports), 6)
        self.assertEqual(summary['unfinished_events'], 0)


if __name__ == '__main__':
    unittest.main()
