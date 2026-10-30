import unittest

import numpy as np

from rated_rip.dmx import pro_packet, universe
from rated_rip.engine import Analyzer, Features, Lighting


class AudioLightingTests(unittest.TestCase):
    def test_silence_is_black_and_has_no_beats(self):
        a, light = Analyzer(size=1024), Lighting(seed=4)
        for _ in range(150):
            f = a.process(np.zeros(1024))
            self.assertFalse(f.beat)
            self.assertEqual(light.update(f, 1024 / 44100), [(0, 0, 0)] * 3)

    def test_silence_fades_after_music(self):
        a, light = Analyzer(size=1024), Lighting(seed=1)
        tone = 0.2 * np.sin(2 * np.pi * 90 * np.arange(1024) / 44100)
        for _ in range(100):
            light.update(a.process(tone), 1024 / 44100)
        for _ in range(200):
            rgb = light.update(a.process(np.zeros(1024)), 1024 / 44100)
        self.assertEqual(rgb, [(0, 0, 0)] * 3)

    def test_periodic_onsets_are_detected(self):
        a = Analyzer()
        onsets = []
        for n in range(round(5 * a.rate / a.size)):
            t = (np.arange(a.size) + n * a.size) / a.rate
            x = (0.04 + 0.45 * np.exp(-(t % 0.5) / 0.045)) * np.sin(2 * np.pi * 90 * t)
            if a.process(x).beat:
                onsets.append(n * a.size / a.rate)
        self.assertGreaterEqual(len(onsets), 7)
        self.assertLessEqual(len(onsets), 11)

    def test_noise_has_higher_density_than_tone(self):
        a = Analyzer(size=1024)
        tone = np.sin(2 * np.pi * 90 * np.arange(1024) / 44100) * 0.2
        self.assertGreater(a.process(np.random.default_rng(1).normal(0, 0.2, 1024)).density,
                           a.process(tone).density)

    def test_dmx_mapping_and_framing(self):
        data = universe([(255, 0, 1), (2, 3, 4), (5, 6, 7)], [1, 4, 510])
        self.assertEqual(data[:6], bytes([255, 0, 1, 2, 3, 4]))
        self.assertEqual(data[-3:], bytes([5, 6, 7]))
        packet = pro_packet(data)
        self.assertEqual(packet[:5], b'\x7e\x06\x01\x02\x00')
        self.assertEqual(packet[-1:], b'\xe7')
        self.assertEqual(len(packet), 518)
        with self.assertRaises(ValueError):
            universe([(0, 0, 0)] * 3, [1, 3, 7])

    def test_brightness_limit(self):
        light = Lighting(seed=0, brightness=0.4)
        for _ in range(500):
            rgb = light.update(Features(1, 1, 1, True), 0.025)
            self.assertTrue(all(0 <= c <= 102 for fixture in rgb for c in fixture))


if __name__ == '__main__':
    unittest.main()
