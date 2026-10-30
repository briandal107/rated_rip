"""Causal, multiband attack evidence, with delayed descriptions of the audio mix.

Inspired by positive spectral difference and frequency-neighbour suppression;
this is not a SuperFlux implementation or an instrument/source separator.
"""
from dataclasses import dataclass, replace
import math

import numpy as np

BANDS = ('low', 'mid', 'high')


@dataclass(frozen=True)
class Attack:
    id: int
    time: float
    reported_at: float
    stage: str
    bands: tuple
    strength: float
    energy: tuple
    centroid_hz: float
    flatness: float
    crest_db: float
    plateau_fraction: float
    near_full_scale_fraction: float
    tail_ratio: float
    overlapped: bool = False
    rise_db: float = 0.0
    noisiness: float = 0.0
    percussiveness: float = 0.5

    @property
    def layered(self):
        """Coincident low and higher-band onsets, not proof of separate drums."""
        return ('low' in self.bands and len(self.bands) > 1
                and self.energy[0] > 0.15 and sum(self.energy[1:]) > 0.2)


def describe(audio, rate):
    """Describe the observed window, including any overlapping/background sounds."""
    audio = np.asarray(audio, dtype=float)
    if audio.ndim == 1:
        audio = audio[:, None]
    centered = audio - audio.mean(axis=0)
    window = np.hanning(len(audio))[:, None]
    spectrum = np.mean(np.abs(np.fft.rfft(centered * window, axis=0)) ** 2, axis=1)
    freqs = np.fft.rfftfreq(len(audio), 1 / rate)
    audible = (freqs >= 35) & (freqs < 16000)
    power = spectrum[audible]
    total = float(power.sum())
    masks = [(freqs >= 35) & (freqs < 250), (freqs >= 250) & (freqs < 4000),
             (freqs >= 4000) & (freqs < 16000)]
    energy = tuple(float(spectrum[m].sum() / total) if total > 1e-18 else 0.0 for m in masks)
    centroid = float(np.sum(freqs[audible] * power) / total) if total > 1e-18 else 0.0
    flatness = float(np.exp(np.mean(np.log(power + 1e-18))) / (np.mean(power) + 1e-18)) if total > 1e-18 else 0.0
    # Energy concentrated in a few adjacent FFT bins suggests a tonal sound.
    # Unlike whole-band flatness, this also works for band-limited noise. The
    # score is a texture cue, not a probability that the source is a drum.
    local_power = np.convolve(power, np.ones(9), mode='same') if len(power) >= 9 else power
    concentration = float(np.sum(power ** 2 / np.maximum(local_power, 1e-18)) / total) if total > 1e-18 else 0.45
    noisiness = float(np.clip((0.45 - concentration) / 0.30, 0, 1))
    # Measure each channel separately; do not cancel stereo or invent a composite waveform.
    peak = np.max(np.abs(centered), axis=0)
    rms = np.sqrt(np.mean(centered ** 2, axis=0))
    active = rms > 1e-6
    crest = float(np.mean(20 * np.log10(np.maximum(1, peak[active] / rms[active])))) if np.any(active) else 0.0
    near_peak = np.abs(centered[1:]) >= 0.98 * peak
    flat_step = np.abs(np.diff(centered, axis=0)) <= 0.002 * np.maximum(peak, 1e-9)
    plateau = float(np.mean((near_peak & flat_step)[:, active])) if np.any(active) else 0.0
    full_scale = float(np.mean(np.abs(audio) >= 0.995))
    width = min(len(audio) // 2, round(rate * 0.02))
    early = float(np.mean(centered[:width] ** 2))
    late = float(np.mean(centered[-width:] ** 2))
    tail = min(4.0, math.sqrt(late / max(early, 1e-12))) if early > 1e-12 else 0.0
    return dict(energy=energy, centroid_hz=centroid, flatness=flatness, crest_db=crest,
                plateau_fraction=plateau, near_full_scale_fraction=full_scale, tail_ratio=tail,
                noisiness=noisiness)


def percussion_evidence(rise_db, noisiness, tail_ratio=None):
    """Bounded acoustic evidence: fast rise, diffuse spectrum, then decay.

    A tonal kick can score highly from its rise and decay. A compressed noisy
    hit can score from its spectrum without requiring a high crest factor.
    """
    edge = max(0.0, min(1.0, (rise_db - 1.5) / 10))
    if tail_ratio is None:
        return min(1.0, 0.10 + 0.55 * edge + 0.30 * noisiness)
    decay = max(0.0, min(1.0, (1 - tail_ratio) / 0.65))
    return min(1.0, 0.10 + 0.25 * edge + 0.20 * noisiness + 0.45 * decay)


class AttackDetector:
    """256-sample hops, 1024-sample detection window, independent band thresholds.

    A local peak costs one hop of look-ahead. Nearby band peaks are merged into
    one event; 30/90 ms updates retain that ID and must never retrigger a light.
    """
    def __init__(self, rate=44100, hop=256):
        if rate not in (44100, 48000) or not 1 <= hop <= 1024:
            raise ValueError('Use 44100/48000 Hz and a hop of 1..1024 samples')
        self.rate, self.hop = rate, hop
        self.nfft = 1024
        self.window = np.hanning(self.nfft)[:, None]
        freqs = np.fft.rfftfreq(self.nfft, 1 / rate)
        self.masks = [(freqs >= 35) & (freqs < 250), (freqs >= 250) & (freqs < 4000),
                      (freqs >= 4000) & (freqs < 16000)]
        self.history = None
        self.total = 0
        self.previous_spectrum = np.zeros(self.nfft // 2 + 1)
        self.level_mean = np.zeros(3)
        self.mean = np.zeros(3)
        self.deviation = np.zeros(3)
        self.prev_flux = np.zeros(3)
        self.prev_candidate = np.zeros(3, dtype=bool)
        self.prev_strength = np.zeros(3)
        self.prev_rising = np.zeros(3, dtype=bool)
        self.last_hit = np.full(3, -1.0)
        self.pending = []
        self.next_id = 1

    def _slice(self, start, end):
        origin = self.total - len(self.history)
        return self.history[max(0, start - origin):max(0, end - origin)]

    def process(self, audio):
        audio = np.asarray(audio, dtype=float)
        if audio.ndim == 1:
            audio = audio[:, None]
        if (audio.ndim != 2 or audio.shape[0] != self.hop or audio.shape[1] not in (1, 2)
                or not np.isfinite(audio).all()):
            raise ValueError('Expected one finite mono/stereo audio hop')
        if self.history is None:
            self.history = np.zeros((round(self.rate * 0.22), audio.shape[1]))
        if audio.shape[1] != self.history.shape[1]:
            raise ValueError('Channel count must remain constant during capture')
        self.history[:-self.hop] = self.history[self.hop:]
        self.history[-self.hop:] = audio
        self.total += self.hop
        now = self.total / self.rate
        frame = self.history[-self.nfft:]
        # Average channel powers: antiphase audio survives, and channels never switch.
        magnitude = np.sqrt(np.mean(np.abs(np.fft.rfft(frame * self.window, axis=0)) ** 2, axis=1)) / self.window.sum()
        self.magnitude = magnitude
        self.rms = float(np.sqrt(np.mean((frame - frame.mean(axis=0)) ** 2)))
        log_spec = np.log1p(magnitude / 0.001)
        reference = np.maximum.reduce([self.previous_spectrum,
                                       np.r_[self.previous_spectrum[0], self.previous_spectrum[:-1]],
                                       np.r_[self.previous_spectrum[1:], self.previous_spectrum[-1]]])
        difference = np.maximum(log_spec - reference, 0)
        flux = np.array([difference[m].mean() for m in self.masks])
        levels = np.array([np.sqrt(np.sum(magnitude[m] ** 2)) for m in self.masks])
        threshold = np.maximum(0.025, self.mean + 3.5 * self.deviation)
        shares = levels ** 2 / max(float(np.sum(levels ** 2)), 1e-12)
        rising = levels > self.level_mean * np.array([1.4, 1.4, 1.35])
        candidate = (flux > threshold) & (levels > 0.0015) & (shares > np.array([0.05, 0.025, 0.025]))
        level_alpha = 1 - math.exp(-self.hop / self.rate / 0.06)
        self.level_mean += level_alpha * (levels - self.level_mean)
        # Select an actual peak, not every hop along the rising edge.
        hits = (self.prev_candidate & (flux < self.prev_flux) & (rising | self.prev_rising)
                & ((now - self.last_hit) >= 0.055))
        output = []
        if np.any(hits) and self.total >= self.nfft:
            self.last_hit[hits] = now
            bands = tuple(BANDS[i] for i in np.flatnonzero(hits))
            strength = float(np.clip(self.prev_strength[hits].max() / 4, 0.25, 1))
            merge = self.pending[-1] if self.pending and now - self.pending[-1]['detected'] <= 0.02 else None
            if merge is not None:
                old = merge['attack']
                merged_bands = tuple(b for b in BANDS if b in old.bands or b in bands)
                merge['attack'] = replace(old, bands=merged_bands, strength=max(old.strength, strength))
                if merged_bands != old.bands:
                    output.append(replace(merge['attack'], reported_at=now, stage='bands'))
            else:
                start = max(0, self.total - self.nfft // 2 - self.hop)
                context = describe(self.history[-self.nfft:], self.rate)
                before = self._slice(start - round(self.rate * 0.02), start)
                after = self._slice(start, self.total)
                before_power = float(np.mean(before ** 2)) if len(before) else 0.0
                after_power = float(np.mean(after ** 2))
                rise_db = float(np.clip(10 * math.log10(max(after_power, 1e-12)
                                                       / max(before_power, 1e-12)), -24, 24))
                percussiveness = percussion_evidence(rise_db, context['noisiness'])
                attack = Attack(self.next_id, start / self.rate, now, 'onset', bands, strength,
                                rise_db=rise_db, percussiveness=percussiveness, **context)
                self.next_id += 1
                if self.pending:
                    attack = replace(attack, overlapped=True)
                    for item in self.pending:
                        item['attack'] = replace(item['attack'], overlapped=True)
                self.pending.append(dict(start=start, detected=now, stage=0, attack=attack))
                output.append(attack)
        alpha = 1 - math.exp(-self.hop / self.rate / 0.7)
        self.deviation += alpha * (np.abs(flux - self.mean) - self.deviation)
        self.mean += alpha * (flux - self.mean)
        self.previous_spectrum = log_spec
        self.prev_flux = flux
        self.prev_candidate = candidate
        self.prev_strength = flux / threshold
        self.prev_rising = rising
        keep = []
        for item in self.pending:
            for index, (seconds, label) in enumerate([(0.03, 'body'), (0.09, 'tail')]):
                end = item['start'] + round(self.rate * seconds)
                if item['stage'] == index and self.total >= end:
                    context = describe(self._slice(item['start'], end), self.rate)
                    old = item['attack']
                    evidence = percussion_evidence(old.rise_db, context['noisiness'], context['tail_ratio'])
                    weight = 0.35 if label == 'body' else 0.75
                    # A new sound may fill in an older hit's decaying tail. Do
                    # not strongly demote it using that contaminated window.
                    if old.overlapped and evidence < old.percussiveness:
                        weight *= 0.35
                    score = old.percussiveness + weight * (evidence - old.percussiveness)
                    attack = replace(old, reported_at=now, stage=label,
                                     percussiveness=score, **context)
                    item['attack'] = attack
                    item['stage'] += 1
                    output.append(attack)
            if item['stage'] < 2:
                keep.append(item)
        self.pending = keep
        return tuple(output)
