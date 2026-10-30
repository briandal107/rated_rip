import colorsys
import math
import random
from dataclasses import dataclass

import numpy as np

from .attacks import AttackDetector
from .vocals import VocalDetector, VocalState


@dataclass(frozen=True)
class Features:
    rms: float
    loudness: float
    density: float
    beat: bool  # Compatibility name: an attack, not a tracked musical beat.
    attacks: tuple = ()
    vocal: VocalState = VocalState()


class Analyzer:
    """Continuous audio envelope plus causal attack detection and descriptions."""

    def __init__(self, rate=44100, size=256, vocals=True):
        self.rate, self.size = rate, size
        self.detector = AttackDetector(rate, size)
        self.vocal_detector = VocalDetector(rate, size) if vocals else None
        self.envelope = 0.0
        self.peak = 0.03

    def process(self, samples):
        attacks = self.detector.process(samples)
        dt = self.size / self.rate
        rms = self.detector.rms
        self.peak = max(0.03, rms, self.peak * math.exp(-dt / 8))
        target = min(1.0, (rms / self.peak) ** 0.7) if rms > 0.003 else 0.0
        tau = 0.06 if target > self.envelope else 0.45
        self.envelope += (1 - math.exp(-dt / tau)) * (target - self.envelope)
        power = self.detector.magnitude[1:] ** 2
        total = float(power.sum())
        p = power / total if total > 1e-12 else np.zeros_like(power)
        density = float(-np.sum(p * np.log(p + 1e-15)) / math.log(len(p)))
        vocal = self.vocal_detector.process(samples) if self.vocal_detector else VocalState()
        return Features(rms, self.envelope, max(0, min(1, density)),
                        any(a.stage == 'onset' for a in attacks), attacks, vocal)


class Lighting:
    """A slow color wash with separate, spatially routed transient envelopes."""

    MAX_PALETTE_HOLD = 24.0  # Audible seconds, including passages without attacks.

    def __init__(self, seed=None, brightness=0.65):
        if not 0 <= brightness <= 1:
            raise ValueError('brightness must be between 0 and 1')
        self.rng = random.Random(seed)
        self.brightness = brightness
        self.hue = self.rng.random()
        self.target_hue = self.hue
        self.scene_age = 0.0
        self.density = 0.0
        self.phase = 0.0
        self.beats = 0  # Counts detected attacks, retained for older callers.
        self.voices = {}
        self.side = 0
        self.vocal_presence = 0.0
        self.vocal_envelope = 0.0

    def update(self, features, dt):
        audible = features.rms >= 0.003 and features.loudness > 0.05
        if audible:
            self.scene_age += dt
        self.phase += dt * (0.18 + self.density * 0.35)
        self.density += (1 - math.exp(-dt / 2)) * (features.density - self.density)
        target = features.vocal.score if features.vocal.active and features.vocal.ready else 0.0
        self.vocal_presence += (1 - math.exp(-dt / 0.6)) * (target - self.vocal_presence)
        self.vocal_envelope += (1 - math.exp(-dt / 0.2)) * (features.vocal.envelope - self.vocal_envelope)
        self.voices = {key: dict(v, age=v['age'] + dt) for key, v in self.voices.items()
                       if v['age'] + dt < 0.8}
        for attack in features.attacks:
            if attack.stage == 'onset':
                self.beats += 1
                self.voices[attack.id] = dict(attack=attack, age=0.0, side=self.side,
                                             percussiveness=attack.percussiveness)
                if 'mid' in attack.bands:
                    self.side = 2 - self.side
            elif attack.id in self.voices:
                # Later descriptions adjust the existing envelope; never restart it.
                if 'mid' in attack.bands and 'mid' not in self.voices[attack.id]['attack'].bands:
                    self.voices[attack.id]['side'] = self.side
                    self.side = 2 - self.side
                self.voices[attack.id]['attack'] = attack
        # Favor an attack when a scene is old enough, but never let a vocal cue
        # or a lack of percussion veto evolution indefinitely. This is not BPM.
        minimum_hold = 8 + 8 * self.vocal_presence
        opportunity = features.beat and self.beats and self.beats % 8 == 0
        if audible and ((self.scene_age >= minimum_hold and opportunity)
                        or self.scene_age >= self.MAX_PALETTE_HOLD):
            step = self.rng.choice([0.12, 0.25, 0.5]) * (1 - 0.55 * self.vocal_presence)
            self.target_hue = (self.hue + step) % 1
            self.scene_age = 0
        delta = (self.target_hue - self.hue + 0.5) % 1 - 0.5
        transition = 2.5 + 3.5 * self.vocal_presence
        self.hue = (self.hue + delta * (1 - math.exp(-dt / transition))) % 1
        accents, texture = [0.0] * 3, [0.0] * 3
        bloom = 0.0
        for voice in self.voices.values():
            a, age, side = voice['attack'], voice['age'], voice['side']
            voice['percussiveness'] += (1 - math.exp(-dt / 0.03)) * (a.percussiveness - voice['percussiveness'])
            percussion = voice['percussiveness']
            # Weak percussion evidence gets a gentler start and a small shared
            # bloom. Strong evidence retains the fast, spatial band accents.
            rise = percussion + (1 - percussion) * (1 - math.exp(-age / 0.045))
            emphasis = (0.2 + 0.8 * percussion) * rise
            bloom += 0.12 * (1 - percussion) * a.strength * (1 - math.exp(-age / 0.045)) * math.exp(-age / 0.24)
            punch = min(1, a.crest_db / 12)
            tail = min(1, a.tail_ratio)
            assignments = []
            if 'low' in a.bands:
                assignments.append((1, 0.48, 0.12 + 0.08 * tail))
            if 'mid' in a.bands:
                assignments.append((side, 0.40, 0.075 + 0.04 * (1 - punch)))
            if 'high' in a.bands:
                assignments.append((2 - side, 0.22, 0.065))
            for fixture, gain, decay in assignments:
                amount = gain * a.strength * emphasis * math.exp(-age / decay)
                accents[fixture] += amount
                texture[fixture] += amount * min(1, a.flatness * 3 + a.plateau_fraction)
        fixtures = []
        for i in range(3):
            motion = 0.85 + 0.15 * math.sin(self.phase + i * 2.094)
            # Related outer lights breathe with the observed mix envelope.
            # No genre, gender, or guessed syllable clocks.
            vocal_glow = ((0.04 + 0.06 * self.vocal_envelope) * self.vocal_presence
                          * features.loudness if i != 1 else 0.0)
            value = min(1, 0.48 * features.loudness * motion + vocal_glow
                        + min(0.52, accents[i] + min(0.12, bloom)))
            spread = (0.035 + 0.09 * self.density) * (1 - 0.3 * self.vocal_presence)
            hue = (self.hue + (i - 1) * spread) % 1
            saturation = 0.85 - min(0.25, texture[i]) - 0.06 * self.vocal_presence
            rgb = colorsys.hsv_to_rgb(hue, saturation, value * self.brightness)
            fixtures.append(tuple(round(c * 255) for c in rgb))
        return fixtures
