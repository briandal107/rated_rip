# Version 0.4: moving palettes and gentler harmonic accents

Version 0.4 implements both changes identified by the original eight-track
replay. The same eight MP3s were replayed in full (26.6 minutes), at their original
gain, with seed 7, a 65% brightness ceiling, 44.1 kHz stereo input and 30 fps
output sampling. The comparison is the saved **version 0.3 with vocals enabled**,
not the earlier comparison with vocals disabled. No song-specific rules or vocal
model retraining were added.

## What changed

Vocal-like activity now increases the minimum wait for a palette opportunity
from 8 toward 16 audible seconds, reduces the hue step by up to 55%, and lengthens
the fade time constant from 2.5 toward 6 seconds. An opportunity is every eighth
detected attack after that wait, not a tracked bar. If none arrives, a new target
is chosen at 24 audible seconds (within one processing hop). Silence pauses the
timer. The hue continues to interpolate smoothly; a target change is not a flash.

Attack descriptions now include `rise_db`, `noisiness` and `percussiveness`.
Immediate evidence uses the available rise and spectrum; the existing 30/90 ms
updates refine it with the observed decay. A tonal kick can score from rise and
decay, and a compressed noisy hit need not have a high crest factor. Known
interference from a later attack reduces the effect of negative decay evidence.
Weak evidence softens the spatial accent and adds a small coordinated bloom.
Strong evidence retains the faster low/mid/high gestures. Updates never restart
an event's age. This is a causal heuristic, not source separation or a calibrated
probability that a sound is a drum.

## Full-song measurements

Palette holds below use elapsed song time, including any quiet intervals. The
runtime limit is in audible time. Brightness variation is the mean absolute
30 fps step in each fixture's maximum RGB channel, averaged over the complete
track. It measures the commanded brightness envelope, not physical illumination
or perceptual quality. Smaller variation is not inherently a better show.

| Track | Palette targets: 0.3 → 0.4 | Longest hold: 0.3 → 0.4 | Brightness variation reduction |
| --- | ---: | ---: | ---: |
| EsDeeKid, fakemink - LV Sandals | 0 → 6 | 111.2 → 17.1 s | 40.8% |
| underscores - Innuendo (I Get U) | 4 → 13 | 68.1 → 17.8 s | 26.8% |
| NOTION - UNCONDITIONAL ft Nate Sib | 13 → 13 | 24.0 → 24.0 s | 48.3% |
| Kettama - Comes and Goes | 14 → 20 | 46.4 → 15.5 s | 41.0% |
| Aaron Hibell - i think i'm in love | 14 → 16 | 28.1 → 16.7 s | 33.0% |
| Skrillex - Fuji Opener | 2 → 11 | 148.2 → 18.0 s | 42.2% |
| Olivia Rodrigo - stupid song | 8 → 13 | 46.5 → 19.3 s | 34.4% |
| Imogen Heap - Hide and Seek | 5 → 16 | 113.4 → 18.1 s | 25.5% |

LV Sandals and Fuji Opener no longer spend most or all of the track at one target
palette. UNCONDITIONAL keeps the same number of palette changes but their timing,
size and transition speed differ. Hide and Seek has gentler brightness changes
and continued color evolution; all 660 original detected attacks still exist.
About 70% of its completed events have percussion evidence below 0.45, a descriptive
cutoff rather than a classifier decision boundary.

The new accent mapping also reduces brightness variation on the dance and rap
tracks. It does **not** selectively smooth only vocals, and it can soften real
drums in dense mixes. Abrupt chord entrances can still resemble drums in their
first short window; later refinements cannot undo light already emitted. Long
boomy drums, vocoders, distortion and overlapping sources remain ambiguous.
The goal is a more restrained response to uncertainty, not a claim that source
identification is solved. These eight songs now inform development; they are not
an untouched test set for future accuracy claims.

## Validation

- 30 fast automated tests passed; the separate full-song unittest is opt-in.
- All eight full-song replays completed and passed finite/range/coverage checks.
- Every attack timestamp, onset band, strength, vocal state, loudness and density
  trace matched the previous replay. The vocal model and onset-selection logic
  are unchanged; the new event descriptors and lighting policy cause the differences.
- Synthetic checks at 44.1/48 kHz separate decaying low/mid/high bursts from a
  sustained harmonic swell, including a clipped tonal kick. Initial responses
  retain the existing sub-35 ms synthetic onset bound. Later reports keep the
  same event ID and do not retrigger the envelope.
- Continuous vocal activity without attacks still produces palette changes;
  vocal influence produces smaller target steps and slower transitions, while
  silence pauses the scene timer and still fades to black.

These checks do not measure Raspberry Pi CPU load, audio/DMX latency, physical
fixture response or human preference. There are no drum/vocal stems or manually
annotated events for these recordings, so no detection-accuracy score is claimed.

## Reproduce and preview

The generated report includes an interactive full-song viewer and eight 45-second
videos with sound. Each uses the same excerpt as the original report, after
continuous analysis from the song's beginning. Version 0.4 appears above the
saved version 0.3. Select the original MP3s in `index.html` for full-song sound;
the browser reads them locally. The shorter videos already include audio.

```sh
.venv/bin/python tools/replay_show.py --output-dir /tmp/rated-rip-v04 \
  --reference-dir /path/to/original-v03-report --clips
.venv/bin/python -m unittest discover -s tests -v
```

Without `--reference-dir`, the comparison is version 0.4 with its vocal layer
disabled. Use a fresh report directory for different code or a different comparison.
The fixtures, SHA-256 checksums and numeric baselines are in `tests/audio/`.
The source MP3s stay out of the small Pi application ZIP and installed wheel.
The evaluation was completed before repository publication.
