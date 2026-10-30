"""Small causal music-vocal activity model and cautious phrase descriptors.

The model estimates vocal-like content in a mix, not lead/backing identity,
biological sex, lyrics, or a reliable sung/rap class.
"""
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import math

import numpy as np


@lru_cache(maxsize=1)
def _default_model():
    return json.loads(files('rated_rip').joinpath('vocal_model.json').read_text())


@dataclass(frozen=True)
class VocalState:
    time: float = 0.0
    ready: bool = False
    score: float = 0.0
    active: bool = False
    envelope: float = 0.0
    articulation: float = 0.0
    delivery: str = 'uncertain'
    tonal_pitch_hz: float = 0.0
    tonal_register: str = 'unknown'
    phrase_pulse_hz: float = 0.0
    groove_confidence: float = 0.0


class VocalFeatureExtractor:
    """46 ms spectral context, 200 ms/1 s EMAs, approximately 23 ms updates."""
    def __init__(self, rate=44100, hop=256):
        if rate not in (44100, 48000):
            raise ValueError('Vocal analysis requires 44100 or 48000 Hz')
        self.rate, self.hop = rate, hop
        self.nfft = 2048
        self.step = math.ceil(0.02 * rate / hop) * hop
        self.dt = self.step / rate
        self.total = self.last = 0
        self.audio = None
        self.window = np.hanning(self.nfft)[:, None]
        self.freq = np.fft.rfftfreq(self.nfft, 1 / rate)
        edges = 700 * (10 ** (np.linspace(2595 * np.log10(1 + 80 / 700),
                                         2595 * np.log10(1 + 8000 / 700), 26) / 2595) - 1)
        self.filters = np.array([np.maximum(0, np.minimum((self.freq - a) / (b - a),
                                                       (c - self.freq) / (c - b)))
                                 for a, b, c in zip(edges, edges[1:], edges[2:])])
        self.dct = np.cos(np.pi * np.arange(1, 13)[:, None] * (np.arange(24) + 0.5) / 24) / 24
        self.regions = [(self.freq >= a) & (self.freq < b)
                        for a, b in [(80, 500), (500, 2000), (2000, 4000), (4000, 8000)]]
        self.fast = self.slow = self.variance = self.previous = None
        self.level_fast = np.zeros(2)
        self.level_slow = np.zeros(2)
        self.pitch = self.tonality = 0.0
        self.rms = 0.0

    def process(self, audio):
        audio = np.asarray(audio, dtype=float)
        if audio.ndim == 1:
            audio = audio[:, None]
        if (audio.ndim != 2 or audio.shape != (self.hop, audio.shape[-1])
                or audio.shape[1] not in (1, 2) or not np.isfinite(audio).all()):
            raise ValueError('Expected a finite mono/stereo hop')
        if self.audio is None:
            self.audio = np.zeros((self.nfft, audio.shape[1]))
        if self.audio.shape[1] != audio.shape[1]:
            raise ValueError('Channel count must remain constant')
        self.audio[:-self.hop] = self.audio[self.hop:]
        self.audio[-self.hop:] = audio
        self.total += self.hop
        if self.total - self.last < self.step:
            return None
        self.last = self.total
        frame = self.audio - self.audio.mean(axis=0)
        power = np.mean(np.abs(np.fft.rfft(frame * self.window, axis=0)) ** 2, axis=1) / self.window.sum() ** 2
        self.rms = float(np.sqrt(np.mean(frame ** 2)))
        mel = self.filters @ power
        shape = np.log(np.maximum(mel / max(float(mel.sum()), 1e-12), 1e-6))
        cepstra = self.dct @ shape
        flatness = [float(np.exp(np.mean(np.log(power[m] + 1e-15))) / (power[m].mean() + 1e-15)) for m in self.regions]
        relevant = (self.freq >= 80) & (self.freq <= 8000)
        p = power[relevant]
        total = float(p.sum())
        centroid = float(np.sum(self.freq[relevant] * p) / max(total, 1e-12)) / 8000
        # Cepstral periodicity is an acoustic cue; the strongest pitch can belong to an instrument.
        cep = np.fft.irfft(np.log(power + 1e-12), n=self.nfft)
        lo, hi = int(self.rate / 500), int(self.rate / 80)
        region = cep[lo:hi]
        peak = int(np.argmax(region)) + lo
        self.pitch = self.rate / peak
        self.tonality = float(np.clip(cep[peak] / (np.mean(np.abs(region)) + 1e-9) / 12, 0, 1))
        change = float(np.mean(np.abs(shape - self.previous))) if self.previous is not None else 0.0
        current = np.r_[shape, cepstra, flatness, centroid, self.tonality, self.pitch / 500, min(change, 3)]
        self.previous = shape
        if self.fast is None:
            self.fast, self.slow, self.variance = current.copy(), current.copy(), np.zeros_like(current)
        a, b = 1 - math.exp(-self.dt / 0.2), 1 - math.exp(-self.dt / 1.0)
        self.fast += a * (current - self.fast)
        self.variance += b * ((current - self.slow) ** 2 - self.variance)
        self.slow += b * (current - self.slow)
        # Deliberately simple baseline for the user's mids/highs EMA hypothesis.
        levels = np.array([np.sum(power[(self.freq >= 250) & (self.freq < 4000)]),
                           np.sum(power[(self.freq >= 4000) & (self.freq < 16000)])])
        self.level_fast += a * (levels - self.level_fast)
        self.level_slow += b * (levels - self.level_slow)
        baseline = np.log10(np.maximum(np.r_[self.level_fast, self.level_slow], 1e-12))
        vector = np.r_[self.fast, self.slow, np.sqrt(np.maximum(self.variance, 0))].astype(np.float32)
        return self.total / self.rate, vector, baseline


class VocalModel:
    """Exported small decision trees; training libraries are not needed on the Pi."""
    def __init__(self, model=None):
        if model is None:
            model = _default_model()
        self.model = model
        self.threshold = model['threshold']

    def predict(self, vector):
        if len(vector) != self.model.get('feature_count', 132):
            raise ValueError('Vocal model feature count does not match extractor')
        value = self.model['bias']
        for tree in self.model['trees']:
            index = 0
            while tree['left'][index] != -1:
                index = (tree['left'][index] if vector[tree['feature'][index]] <= tree['threshold'][index]
                         else tree['right'][index])
            value += self.model['learning_rate'] * tree['value'][index]
        return 1 / (1 + math.exp(-max(-30, min(30, value))))


class VocalTracker:
    """Confidence smoothing and mix-envelope groove cues, never invented syllables."""
    def __init__(self, dt, threshold):
        self.dt, self.threshold = dt, threshold
        self.score = 0.0
        self.active = False
        self.phrase = 0.0
        self.articulation = 0.0
        self.history = deque(maxlen=round(5 / dt))
        self.state = VocalState()
        self.counter = 0
        self.pulse = self.groove = 0.0

    def update(self, time, score, mid_fast, mid_slow, rms, pitch, tonality):
        ready = time >= 1.0
        if rms < 0.003:
            score = 0.0
        tau = 0.25 if score > self.score else 0.5
        self.score += (1 - math.exp(-self.dt / tau)) * (score - self.score)
        if ready and rms >= 0.003 and self.score >= self.threshold:
            self.active = True
        elif not ready or rms < 0.003 or self.score < self.threshold - 0.10:
            self.active = False
        ratio = math.sqrt(max(mid_fast, 0) / max(mid_slow, 1e-12))
        envelope = float(np.clip((ratio - 0.65) / 0.8, 0, 1)) if rms >= 0.003 else 0.0
        variation = abs(envelope - self.phrase)
        self.phrase += (1 - math.exp(-self.dt / 0.08)) * (envelope - self.phrase)
        self.articulation += (1 - math.exp(-self.dt / 1)) * (min(1, variation * 12) - self.articulation)
        self.history.append((self.phrase, self.active))
        self.counter += 1
        if self.counter % 10 == 0:
            self.pulse = self.groove = 0.0
            if len(self.history) * self.dt >= 3 and np.mean([h[1] for h in self.history]) > 0.65:
                values = np.array([h[0] for h in self.history])
                values -= values.mean()
                if np.std(values) > 0.04:
                    correlations = []
                    lags = range(max(1, round(1 / (8 * self.dt))), round(1 / self.dt) + 1)
                    for lag in lags:
                        left, right = values[:-lag], values[lag:]
                        norm = math.sqrt(float(left @ left) * float(right @ right))
                        correlations.append(float(left @ right) / max(norm, 1e-12))
                    # Prefer the first strong local peak over a later multiple
                    # of the same period; octave ambiguity can still remain.
                    floor = max(0.45, 0.85 * max(correlations))
                    peaks = [i for i in range(1, len(correlations) - 1)
                             if correlations[i] >= floor and correlations[i] > correlations[i - 1]
                             and correlations[i] >= correlations[i + 1]]
                    if peaks:
                        best = peaks[0]
                        confidence = max(0, correlations[best])
                        self.pulse = 1 / (list(lags)[best] * self.dt)
                        self.groove = confidence
        delivery = ('articulated' if self.articulation > 0.35 else 'sustained') if self.active else 'uncertain'
        register = 'unknown'
        if self.active and tonality > 0.45:
            register = 'lower' if pitch < 180 else 'higher' if pitch > 260 else 'middle'
        self.state = VocalState(time, ready, self.score, self.active,
                                self.phrase if self.active else 0.0, self.articulation, delivery,
                                pitch if register != 'unknown' else 0.0, register,
                                self.pulse if self.active else 0.0, self.groove if self.active else 0.0)
        return self.state


class VocalDetector:
    def __init__(self, rate=44100, hop=256, model=None):
        self.extractor = VocalFeatureExtractor(rate, hop)
        self.model = VocalModel(model)
        self.tracker = VocalTracker(self.extractor.dt, self.model.threshold)
        self.state = VocalState()

    def process(self, samples):
        result = self.extractor.process(samples)
        if result is not None:
            time, vector, _ = result
            e = self.extractor
            self.state = self.tracker.update(time, self.model.predict(vector), e.level_fast[0],
                                             e.level_slow[0], e.rms, e.pitch, e.tonality)
        return self.state
