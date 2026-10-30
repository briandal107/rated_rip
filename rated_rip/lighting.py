"""Four causal lighting schemes, sharing audio cues and a bounded DMX ceiling."""
import colorsys
import math
import random


class Lighting:
    """Attack-driven shows. Scheme changes use audible time, not a BPM clock."""

    SCHEMES = ('pulse', 'chase', 'split', 'bloom')
    MAX_PALETTE_HOLD = 24.0
    SCHEME_FADE = 1.2
    SWITCH_GRACE = 3.0

    def __init__(self, seed=None, brightness=0.65, scheme='auto', scheme_seconds=150):
        if not 0 <= brightness <= 1:
            raise ValueError('brightness must be between 0 and 1')
        if scheme not in ('auto',) + self.SCHEMES:
            raise ValueError('unknown lighting scheme')
        if not math.isfinite(scheme_seconds) or scheme_seconds < 5:
            raise ValueError('scheme_seconds must be finite and at least 5')
        self.rng = random.Random(seed)
        # Vocal/palette decisions must not change the order of the shows.
        self.scheme_rng = random.Random(None if seed is None else f'{seed}:schemes')
        self.brightness = brightness
        self.automatic = scheme == 'auto'
        self.scheme = 'pulse' if self.automatic else scheme
        self.scheme_seconds = scheme_seconds
        self.scheme_age = 0.0
        self.scheme_changes = 0
        self.previous_scheme = None
        self.transition_age = self.SCHEME_FADE
        self.scheme_queue = list(self.SCHEMES[1:])
        self.scheme_rng.shuffle(self.scheme_queue)
        self.hue = self.rng.random()
        self.target_hue = self.hue
        self.scene_age = 0.0
        self.density = 0.0
        self.phase = 0.0
        self.beats = 0  # Detected attacks, not a beat-grid count.
        self.voices = {}
        self.side = 0
        self.chase_position = -1
        self.step_age = 1.0
        self.major_hits = 0
        self.vocal_presence = 0.0
        self.vocal_envelope = 0.0
        self.peak = 0.03
        self.energy = 0.0
        self.gate = 0.0

    def _change_palette(self):
        step = self.rng.choice([0.16, 0.33, 0.5]) * (1 - 0.25 * self.vocal_presence)
        self.target_hue = (self.hue + step) % 1
        self.scene_age = 0.0

    def _change_scheme(self):
        if not self.scheme_queue:
            self.scheme_queue = list(self.SCHEMES)
            self.scheme_rng.shuffle(self.scheme_queue)
            if self.scheme_queue[-1] == self.scheme:
                self.scheme_queue[0], self.scheme_queue[-1] = self.scheme_queue[-1], self.scheme_queue[0]
        self.previous_scheme = self.scheme
        self.scheme = self.scheme_queue.pop()
        self.scheme_age = 0.0
        self.transition_age = 0.0
        self.scheme_changes += 1
        self._change_palette()

    def update(self, features, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('dt must be finite and positive')
        audible = features.rms >= 0.003 and features.loudness > 0.05
        if audible:
            self.scene_age += dt
            self.scheme_age += dt
        self.transition_age = min(self.SCHEME_FADE, self.transition_age + dt)
        if self.transition_age >= self.SCHEME_FADE:
            self.previous_scheme = None
        self.phase += dt * (0.3 + self.density * 0.55)
        self.step_age += dt
        self.density += (1 - math.exp(-dt / 2)) * (features.density - self.density)
        target = features.vocal.score if features.vocal.active and features.vocal.ready else 0.0
        self.vocal_presence += (1 - math.exp(-dt / 0.6)) * (target - self.vocal_presence)
        self.vocal_envelope += (1 - math.exp(-dt / 0.2)) * (features.vocal.envelope - self.vocal_envelope)
        # Faster than the analyzer's slow envelope: a dip between drums should
        # remain visible. Gate all schemes on actual audio, including their tails.
        self.peak = max(0.03, features.rms, self.peak * math.exp(-dt / 8))
        target = min(1.0, features.rms / self.peak) if features.rms >= 0.003 else 0.0
        tau = 0.012 if target > self.energy else 0.14
        self.energy += (1 - math.exp(-dt / tau)) * (target - self.energy)
        target = float(features.rms >= 0.003)
        self.gate += (1 - math.exp(-dt / (0.012 if target else 0.18))) * (target - self.gate)
        self.voices = {key: dict(v, age=v['age'] + dt) for key, v in self.voices.items()
                       if v['age'] + dt < 1.4}
        for attack in features.attacks:
            if attack.stage == 'onset':
                self.beats += 1
                # High-only attacks decorate the chase; they do not race it
                # around the fixtures at hi-hat speed. No free-running chase.
                if (audible and self.step_age >= 0.10 and attack.strength >= 0.15
                        and ('low' in attack.bands or 'mid' in attack.bands)):
                    self.chase_position = (self.chase_position + 1) % 4
                    self.major_hits += 1
                    self.step_age = 0.0
                step = (0, 1, 2, 1)[max(0, self.chase_position)]
                self.voices[attack.id] = dict(attack=attack, age=0.0, side=self.side,
                                             step=step, color=(self.major_hits // 4) % 3,
                                             percussiveness=attack.percussiveness)
                if 'mid' in attack.bands:
                    self.side = 2 - self.side
            elif attack.id in self.voices:
                # The 30/90 ms descriptions refine an existing gesture. They
                # never restart its age, advance the chase or count another hit.
                voice = self.voices[attack.id]
                if 'mid' in attack.bands and 'mid' not in voice['attack'].bands:
                    voice['side'] = self.side
                    self.side = 2 - self.side
                voice['attack'] = attack
        for voice in self.voices.values():
            voice['percussiveness'] += (1 - math.exp(-dt / 0.03)) * (
                voice['attack'].percussiveness - voice['percussiveness'])

        # Wait briefly for an attack at the interval, then switch even in a
        # sustained passage. Silence pauses this clock; vocals cannot veto it.
        if (self.automatic and audible and self.scheme_age >= self.scheme_seconds
                and (features.beat or self.scheme_age >= self.scheme_seconds + self.SWITCH_GRACE)):
            self._change_scheme()
        elif audible and ((self.scene_age >= 6 + 4 * self.vocal_presence
                           and features.beat and self.beats and self.beats % 8 == 0)
                          or self.scene_age >= self.MAX_PALETTE_HOLD):
            self._change_palette()
        delta = (self.target_hue - self.hue + 0.5) % 1 - 0.5
        self.hue = (self.hue + delta * (1 - math.exp(-dt / (0.45 + 0.65 * self.vocal_presence)))) % 1

        fixtures = self._render(self.scheme, features)
        if self.previous_scheme is not None:
            old = self._render(self.previous_scheme, features)
            blend = self.transition_age / self.SCHEME_FADE
            blend = blend * blend * (3 - 2 * blend)
            fixtures = [tuple(a + blend * (b - a) for a, b in zip(before, after))
                        for before, after in zip(old, fixtures)]
        scale = 255 * self.brightness * self.gate
        return [tuple(round(max(0, min(1, c)) * scale) for c in rgb) for rgb in fixtures]

    def _render(self, scheme, features):
        accents, accent_hues, texture = [0.0] * 3, [self.hue] * 3, [0.0] * 3

        def accent(fixture, amount, hue, noise):
            # Keep the strongest gesture rather than piling dense drums into
            # an almost constant full-brightness wash.
            if amount > accents[fixture]:
                accents[fixture] = amount
                accent_hues[fixture] = hue % 1
                texture[fixture] = noise

        for voice in self.voices.values():
            a, age, side = voice['attack'], voice['age'], voice['side']
            percussion = voice['percussiveness']
            rise = percussion + (1 - percussion) * (1 - math.exp(-age / 0.045))
            strength = math.sqrt(max(0, min(1, a.strength))) * (0.4 + 0.6 * percussion) * rise
            noise = min(1, a.flatness * 3 + a.plateau_fraction)
            tail = min(1, a.tail_ratio)
            color = (0.0, 0.16, 0.5)[voice['color']]
            if scheme == 'pulse':
                if 'low' in a.bands:
                    envelope = strength * math.exp(-age / (0.12 + 0.05 * tail))
                    for i, gain in enumerate((0.85, 1.15, 0.85)):
                        accent(i, gain * envelope, self.hue, noise)
                if 'mid' in a.bands:
                    accent(side, strength * math.exp(-age / 0.11), self.hue + 0.16, noise)
                if 'high' in a.bands:
                    accent(2 - side, 0.35 * strength * math.exp(-age / 0.07), self.hue + 0.16, noise)
            elif scheme == 'chase':
                step = voice['step']
                if 'low' in a.bands or 'mid' in a.bands:
                    accent(step, 1.2 * strength * math.exp(-age / 0.14), self.hue + color, noise)
                    accent((step + 2) % 3, 0.22 * strength * math.exp(-age / 0.23), self.hue + color, noise)
                if 'high' in a.bands:
                    accent((step + 1) % 3, 0.3 * strength * math.exp(-age / 0.07), self.hue + 0.5, noise)
            elif scheme == 'split':
                if 'low' in a.bands:
                    accent(1, 1.2 * strength * math.exp(-age / (0.13 + 0.05 * tail)), self.hue, noise)
                if 'mid' in a.bands:
                    envelope = strength * math.exp(-age / 0.14)
                    accent(side, 1.1 * envelope, self.hue + 0.5, noise)
                    accent(2 - side, 0.65 * envelope, self.hue + 0.5, noise)
                if 'high' in a.bands:
                    accent(2 - side, 0.55 * strength * math.exp(-age / 0.08), self.hue + 0.6, noise)
            else:  # bloom: broad, slower swells, with the same causal attacks.
                envelope = strength * (1 - math.exp(-(age + 0.01) / 0.07)) * math.exp(-age / 0.38)
                for i in range(3):
                    gain = 1.05 if i == voice['step'] else 0.8
                    accent(i, gain * envelope, self.hue + (i - 1) * 0.18 + color * 0.3, noise)

        level = 0.35 * features.loudness + 0.65 * self.energy
        fixtures = []
        for i in range(3):
            if scheme == 'pulse':
                base = 0.09 * level
                hue = self.hue
            elif scheme == 'chase':
                base = 0.025 * level
                hue = self.hue + i * 0.16
            elif scheme == 'split':
                base = (0.045 if i == 1 else 0.065) * level
                hue = self.hue + (0 if i == 1 else 0.5)
            else:
                motion = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.phase + i * 2.094))
                base = (0.12 + 0.35 * level ** 1.5) * level * motion
                hue = self.hue + (i - 1) * (0.12 + 0.10 * self.density)
            if i != 1:
                base += ((0.025 + 0.04 * self.vocal_envelope) * self.vocal_presence * level
                         * (2 if scheme == 'bloom' else 1))
            base_rgb = colorsys.hsv_to_rgb(hue % 1, 0.94, min(1, base))
            accent_rgb = colorsys.hsv_to_rgb(accent_hues[i], 0.94 - 0.16 * texture[i],
                                             min(1, accents[i]))
            fixtures.append(tuple(min(1, b + a) for b, a in zip(base_rgb, accent_rgb)))
        return fixtures
