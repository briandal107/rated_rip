from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from rated_rip.analyze import analyze
from rated_rip.engine import Analyzer, Features, Lighting
from rated_rip.vocals import VocalDetector, VocalFeatureExtractor, VocalModel, VocalState, VocalTracker


class VocalTests(unittest.TestCase):
    def test_feature_context_is_causal_and_phase_safe(self):
        rate = 44100
        t = np.arange(rate * 2) / rate
        signal = 0.1 * (np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 540 * t))
        mono, stereo = VocalFeatureExtractor(), VocalFeatureExtractor()
        for start in range(0, len(signal) - 255, 256):
            block = signal[start:start + 256]
            first = mono.process(block)
            second = stereo.process(np.column_stack([block, -block]))
            if first is not None:
                self.assertLessEqual(first[0], (start + 256) / rate)
                self.assertEqual(len(first[1]), 132)
                np.testing.assert_allclose(first[1], second[1], atol=1e-5)
                self.assertTrue(np.isfinite(first[1]).all())

    def test_silence_and_disable_do_not_claim_vocals(self):
        for rate in (44100, 48000):
            detector = VocalDetector(rate)
            for _ in range(round(2 * rate / 256)):
                state = detector.process(np.zeros((256, 2)))
                self.assertFalse(state.active)
                self.assertEqual(state.score, 0)
                self.assertEqual(state.tonal_register, 'unknown')
            self.assertTrue(state.ready)
        analyzer = Analyzer(vocals=False)
        self.assertIsNone(analyzer.vocal_detector)
        self.assertEqual(analyzer.process(np.zeros(256)).vocal, VocalState())

    def test_score_hysteresis_and_silence_reset(self):
        tracker = VocalTracker(0.02, 0.7)
        for step in range(100):
            state = tracker.update((step + 1) * 0.02, 0.95, 0.1, 0.1, 0.1, 240, 0.7)
            if state.time < 1:
                self.assertFalse(state.active)
        self.assertTrue(state.active)
        # A single weak frame must not flicker the lighting state.
        state = tracker.update(2.02, 0.1, 0.1, 0.1, 0.1, 240, 0.7)
        self.assertTrue(state.active)
        state = tracker.update(2.04, 1, 0, 0, 0, 240, 0.7)
        self.assertFalse(state.active)
        self.assertEqual(state.envelope, 0)
        self.assertEqual(state.delivery, 'uncertain')

    def test_phrase_rhythm_needs_history_and_activity(self):
        tracker = VocalTracker(0.02, 0.7)
        states = []
        for step in range(300):
            t = (step + 1) * 0.02
            level = (1 + 0.25 * np.sin(2 * np.pi * 3 * t)) ** 2
            states.append(tracker.update(t, 0.99, level, 1, 0.1, 240, 0.7))
        self.assertTrue(all(s.phrase_pulse_hz == 0 for s in states if s.time < 3))
        self.assertAlmostEqual(states[-1].phrase_pulse_hz, 3, delta=0.25)
        self.assertGreater(states[-1].groove_confidence, 0.45)
        self.assertEqual(states[-1].delivery, 'articulated')
        quiet = VocalTracker(0.02, 0.7)
        for step in range(300):
            t = (step + 1) * 0.02
            state = quiet.update(t, 0, (1 + 0.25 * np.sin(2 * np.pi * 3 * t)) ** 2, 1, 0.1, 240, 0.7)
        self.assertEqual(state.phrase_pulse_hz, 0)

    def test_bundled_model_and_input_contract(self):
        model = VocalModel()
        self.assertEqual(model.model['schema'], 'rated-rip-vocal-v1')
        self.assertEqual(model.model['feature_count'], 132)
        self.assertTrue(0 <= model.predict(np.zeros(132)) <= 1)
        with self.assertRaises(ValueError):
            model.predict(np.zeros(4))
        extractor = VocalFeatureExtractor()
        for signal in [np.zeros(255), np.zeros((256, 3)), np.full(256, np.nan)]:
            with self.assertRaises(ValueError):
                extractor.process(signal)

    def test_vocal_lighting_is_bounded_and_fades_away(self):
        vocal = VocalState(time=3, ready=True, score=0.9, active=True, envelope=0.8,
                           articulation=0.6, delivery='articulated')
        with_vocals, without = Lighting(seed=7, brightness=0.4), Lighting(seed=7, brightness=0.4)
        base = Features(0.1, 0.7, 0.5, False)
        for _ in range(200):
            lit = with_vocals.update(replace(base, vocal=vocal), 0.02)
            plain = without.update(base, 0.02)
        self.assertGreater(max(lit[0]), max(plain[0]))
        self.assertGreater(max(lit[2]), max(plain[2]))
        self.assertTrue(all(c <= 102 for fixture in lit for c in fixture))
        for _ in range(300):
            lit = with_vocals.update(Features(0, 0, 0, False), 0.02)
        self.assertEqual(lit, [(0, 0, 0)] * 3)
        self.assertLess(with_vocals.vocal_presence, 0.001)

    def test_wav_vocal_log_has_distinct_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'silence.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(44100)
                wav.writeframes(bytes(44100 * 2 * 2 * 2))
            attacks, vocals = io.StringIO(), io.StringIO()
            summary = analyze(path, attacks, vocals)
        rows = [json.loads(line) for line in vocals.getvalue().splitlines()]
        self.assertEqual(summary['vocal_updates'], len(rows))
        self.assertGreater(len(rows), 80)
        self.assertEqual(len({r['time'] for r in rows}), len(rows))
        self.assertTrue(all(not r['active'] for r in rows))

    def test_continuous_vocals_without_attacks_cannot_freeze_palette(self):
        vocal = VocalState(time=5, ready=True, score=0.99, active=True, envelope=0.6)
        light = Lighting(seed=7)
        f = Features(0.1, 0.6, 0.3, False, vocal=vocal)
        changes, target = [], light.target_hue
        for step in range(6000):
            light.update(f, 0.02)
            if light.target_hue != target:
                changes.append((step + 1) * 0.02)
                target = light.target_hue
        self.assertGreaterEqual(len(changes), 4)
        self.assertLessEqual(max(np.diff([0] + changes + [120])), 24.02 + 1e-9)
        quiet_target, age = light.target_hue, light.scene_age
        for _ in range(3000):
            light.update(Features(0, 0, 0, False, vocal=vocal), 0.02)
        self.assertEqual(light.target_hue, quiet_target)
        self.assertEqual(light.scene_age, age)

    def test_vocals_make_color_steps_smaller_and_transitions_slower(self):
        vocal = VocalState(time=5, ready=True, score=0.99, active=True)
        plain, voice = Lighting(seed=7), Lighting(seed=7)
        base = Features(0.1, 0.6, 0.3, False)
        start = plain.hue
        for _ in range(1201):
            plain.update(base, 0.02)
            voice.update(replace(base, vocal=vocal), 0.02)
        distance = lambda a, b: abs((a - b + 0.5) % 1 - 0.5)
        self.assertLess(distance(voice.target_hue, start), distance(plain.target_hue, start))
        for _ in range(50):
            plain.update(base, 0.02)
            voice.update(replace(base, vocal=vocal), 0.02)
        progress_plain = distance(plain.hue, start) / distance(plain.target_hue, start)
        progress_voice = distance(voice.hue, start) / distance(voice.target_hue, start)
        self.assertLess(progress_voice, progress_plain)


if __name__ == '__main__':
    unittest.main()
