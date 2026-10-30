import math
from dataclasses import dataclass

import numpy as np

from .attacks import AttackDetector
from .lighting import Lighting
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
