from dataclasses import replace
import math
import unittest

from rated_rip.attacks import Attack
from rated_rip.dmx import universe
from rated_rip.engine import Features, Lighting
from rated_rip.vocals import VocalState


BASE = Features(0.1, 0.8, 0.5, False)
QUIET = Features(0, 0, 0, False)


def hit(number=1, bands=('low',), **changes):
    event = Attack(number, 0, 0, 'onset', bands, 0.8, (0.8, 0.15, 0.05),
                   120, 0.05, 9, 0, 0, 0.3, percussiveness=0.9)
    return replace(event, **changes)


def settle(light, seconds=1, features=BASE):
    for _ in range(round(seconds / 0.01)):
        rgb = light.update(features, 0.01)
    return rgb


class SchemeTests(unittest.TestCase):
    def test_punchy_schemes_have_visible_attack_contrast_at_35_percent(self):
        for scheme in ('pulse', 'chase', 'split'):
            with self.subTest(scheme=scheme):
                light = Lighting(seed=7, brightness=0.35, scheme=scheme)
                before = max(c for rgb in settle(light) for c in rgb)
                peak = max(c for rgb in light.update(replace(BASE, beat=True, attacks=(hit(),)), 0.01)
                           for c in rgb)
                after = max(c for rgb in settle(light, 0.5) for c in rgb)
                self.assertGreater(peak - before, 40)
                self.assertLess(after - before, (peak - before) * 0.15)

    def test_pulse_shares_kicks_but_split_routes_center_and_sides(self):
        outputs = {}
        for scheme in ('pulse', 'split'):
            light = Lighting(seed=7, scheme=scheme)
            settle(light)
            outputs[scheme] = [max(c) for c in light.update(
                replace(BASE, beat=True, attacks=(hit(),)), 0.01)]
        self.assertGreater(min(outputs['pulse']), 70)
        self.assertGreater(outputs['split'][1], max(outputs['split'][::2]) * 4)
        split = Lighting(seed=7, scheme='split')
        settle(split)
        rgb = split.update(replace(BASE, beat=True, attacks=(hit(bands=('mid',)),)), 0.01)
        self.assertGreater(min(max(rgb[0]), max(rgb[2])), max(rgb[1]) * 4)

    def test_chase_moves_on_attacks_and_refinements_do_not_advance_it(self):
        light = Lighting(seed=7, scheme='chase')
        settle(light)
        positions = []
        for number in range(1, 5):
            event = hit(number)
            rgb = light.update(replace(BASE, beat=True, attacks=(event,)), 0.01)
            positions.append(max(range(3), key=lambda i: max(rgb[i])))
            position, count = light.chase_position, light.beats
            light.update(replace(BASE, attacks=(replace(event, stage='body'),)), 0.03)
            self.assertEqual((light.chase_position, light.beats), (position, count))
            settle(light, 0.5)
        self.assertEqual(positions, [0, 1, 2, 1])
        position = light.chase_position
        light.update(replace(BASE, beat=True, attacks=(hit(5, ('high',)),)), 0.01)
        self.assertEqual(light.chase_position, position)
        settle(light, 3)
        self.assertEqual(light.chase_position, position)

    def test_bloom_has_a_slower_rise_and_longer_tail(self):
        traces = {}
        for scheme in ('pulse', 'bloom'):
            light = Lighting(seed=7, scheme=scheme)
            baseline = settle(light)
            traces[scheme] = []
            for frame in range(60):
                f = replace(BASE, beat=True, attacks=(hit(),)) if frame == 0 else BASE
                rgb = light.update(f, 0.01)
                traces[scheme].append(max(max(rgb[i]) - max(baseline[i]) for i in range(3)))
        self.assertGreater(traces['bloom'][8], traces['bloom'][0] * 2)
        self.assertGreater(traces['bloom'][40], traces['pulse'][40] * 2)

    def test_rotation_covers_all_schemes_without_adjacent_repeats(self):
        light = Lighting(seed=7, scheme_seconds=5)
        sequence = [light.scheme]
        for _ in range(4200):
            light.update(replace(BASE, beat=True), 0.01)
            if light.scheme != sequence[-1]:
                sequence.append(light.scheme)
        self.assertGreaterEqual(len(sequence), 8)
        for start in (0, 4):
            self.assertEqual(set(sequence[start:start + 4]), set(Lighting.SCHEMES))
        self.assertTrue(all(a != b for a, b in zip(sequence, sequence[1:])))

    def test_rotation_waits_for_attack_then_has_a_deadline_even_with_vocals(self):
        light = Lighting(seed=7, scheme_seconds=5)
        vocal = VocalState(ready=True, active=True, score=0.99, envelope=0.9)
        f = replace(BASE, vocal=vocal)
        settle(light, 5.5, f)
        self.assertEqual(light.scheme_changes, 0)
        age = light.scheme_age
        self.assertEqual(settle(light, 20, QUIET), [(0, 0, 0)] * 3)
        self.assertEqual(light.scheme_age, age)
        settle(light, 2.6, f)
        self.assertEqual(light.scheme_changes, 1)

    def test_default_interval_and_manual_selection(self):
        automatic = Lighting(seed=7)
        fixed = Lighting(seed=7, scheme='split', scheme_seconds=5)
        for _ in range(1490):
            automatic.update(BASE, 0.1)
            fixed.update(BASE, 0.1)
        self.assertEqual(automatic.scheme_changes, 0)
        for _ in range(50):
            automatic.update(BASE, 0.1)
        self.assertEqual(automatic.scheme_changes, 1)
        self.assertEqual(fixed.scheme, 'split')
        self.assertEqual(fixed.scheme_changes, 0)

    def test_scheme_switch_crossfades_instead_of_cutting(self):
        automatic = Lighting(seed=7, scheme_seconds=5)
        fixed = Lighting(seed=7, scheme='pulse')
        f = replace(BASE, beat=True)
        while not automatic.scheme_changes:
            before = fixed.update(f, 0.01)
            after = automatic.update(f, 0.01)
        self.assertLessEqual(max(abs(a - b) for x, y in zip(before, after)
                                 for a, b in zip(x, y)), 3)
        self.assertIsNotNone(automatic.previous_scheme)
        settle(automatic, 1.3)
        self.assertIsNone(automatic.previous_scheme)

    def test_all_schemes_bound_dense_attacks_leave_uv_off_and_fade_to_black(self):
        for scheme in Lighting.SCHEMES:
            with self.subTest(scheme=scheme):
                light = Lighting(seed=7, brightness=0.35, scheme=scheme)
                for index in range(150):
                    f = replace(BASE, beat=True, attacks=(hit(index, ('low', 'mid', 'high')),))
                    rgb = light.update(f, 0.01)
                    self.assertTrue(all(0 <= c <= 89 for triplet in rgb for c in triplet))
                    data = universe(rgb, [1, 5, 9])
                    self.assertEqual([data[i] for i in (3, 7, 11)], [0, 0, 0])
                    self.assertEqual(data[12:], bytes(500))
                self.assertEqual(settle(light, 2, QUIET), [(0, 0, 0)] * 3)

    def test_deterministic_rotation_and_output(self):
        a, b = (Lighting(seed=19, scheme_seconds=5) for _ in range(2))
        for index in range(1500):
            f = replace(BASE, beat=True, attacks=(hit(index),)) if index % 20 == 0 else BASE
            self.assertEqual(a.update(f, 0.02), b.update(f, 0.02))
            self.assertEqual(a.scheme, b.scheme)

    def test_invalid_configuration(self):
        for value in (0, 4.9, math.nan, math.inf):
            with self.assertRaises(ValueError):
                Lighting(scheme_seconds=value)
        with self.assertRaises(ValueError):
            Lighting(scheme='unknown')


if __name__ == '__main__':
    unittest.main()
