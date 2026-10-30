# Vocal-like activity: an experiment with real music

Version 0.3 tests the idea that 200 ms–1 s spectral history can reveal vocals
and that 3–5 s envelope history can suggest phrase rhythm. The result is useful
as a modest lighting cue, but it is not reliable lead-vocal identification.

## What was downloaded and how it was tested

The official [MUSDB Python project](https://github.com/sigsep/sigsep-mus-db)
provides [seven-second excerpts for research/prototyping](https://github.com/sigsep/sigsep-mus-db/releases/download/v0.4.0/MUSDB18-7-STEMS.zip).
The downloaded v0.4.0 archive contains **144 excerpts: 94 training and 50 test**.
The 94 training excerpts were further divided using the project's official
14-track validation list: **80 fitting / 14 validation / 50 held-out test tracks**.
The downloaded archive's SHA-256 is
`365f66acffc57282e474a4c24b32afec3678258c50b8d45646ac849b0a287df3`.

Each excerpt has separate drums, bass, other accompaniment, and vocal stems.
We sum the instrumental stems, then compare that accompaniment with and without
the vocal stem. Both versions use the same decoder/mixing path and are level
normalized, reducing a trivial mastering-volume shortcut. Stereo vocal channel
mapping was also checked independently against FFmpeg's direct vocal decode.

The model only receives the resulting mixture. Vocal stems provide labels for
evaluation, not inputs to detection. No source separation runs on the Pi.

Labels use the preceding 200 ms of stem power: positive when vocal power exceeds
1e-6 and 1% of mixture power; negative below 1e-8 or 0.01% of mixture power.
Intermediate ambiguous windows are excluded. The accompaniment-only version is
negative. The first second is excluded for warm-up. These are **stem-derived
activity labels**, not human annotations of the lead singer. Bleed, vocal samples
in accompaniment, backing vocals, or differing stem conventions may affect them.

Both classifiers use 80 shallow boosted trees. The baseline sees only mid/high
power EMAs at 200 ms and 1 s. The richer model sees spectral shape and temporal
variation. Each threshold was chosen only on validation tracks, targeting at
most 5% false positives there. The deployed model and threshold were saved before
the 50-track test subset was evaluated. The test results did not tune this model.

## Results, including failures

| Held-out test metric | Mid/high EMA baseline | Spectral + temporal model |
| --- | ---: | ---: |
| Vocal-positive windows detected (recall) | 21.7% | 68.0% |
| Vocal-negative windows falsely marked active | 2.7% | 18.7% |
| Active predictions correct (precision) | 87.9% | 76.5% |
| Balanced accuracy | 59.5% | 74.7% |

The richer detector finds substantially more activity but also raises more false
alarms. Its validation false-positive rate was 4.1%; the increase to 18.7% on test
tracks shows that the conservative threshold did not generalize reliably.
Do not treat its score as a calibrated probability of a lead vocalist.

These are time-window metrics after smoothing/hysteresis. Adjacent windows overlap
and are correlated; they are not thousands of independent songs. The data consists
of short excerpts, not full DJ sets. It does not systematically cover the user's
specific modern garage, jerk, hyperpop and techno repertoire, and it has no
ground-truth rap/singing, vocal register, groove, or singer-gender labels.

The [full per-track report](research/vocal_evaluation.json) includes all splits,
thresholds, training-library version, feature hash, counts, and per-track results.
The [example plots](research/vocal_examples.png) deliberately show two useful
distinctions and a failure; they are illustrative selections, not a random sample:

- **AM Contra – Heart Peripheral:** the runtime cue is active for 86% of the
  post-warm-up mixture excerpt and 0% of its accompaniment-only version.
- **M.E.R.C. Music – Knockout:** approximately 77% versus 0% in a 16-bit runtime replay.
- **Detsky Sad – Walkie Talkie:** 100% active in both versions, a clear false
  positive against the accompaniment label.

The example plots run the full analyzer and lighting engine with 16-bit-quantized
audio, not just the training feature extractor. The [runtime measurements](research/vocal_runtime_examples.json)
show roughly 0.39–0.54 seconds of cloud CPU wall time for each approximately
6.8-second decoded excerpt. This excludes audio-device and DMX I/O and is **not
a Raspberry Pi benchmark**. Scores plotted against 0.7 may remain active below
that line because the release threshold is 0.6.

## Runtime design

The existing attack detector remains independent. The additional vocal frontend
uses a 2048-sample window (~46 ms at 44.1 kHz) and updates approximately every
23 ms. It combines channel powers, so antiphase stereo does not disappear.

Features include 24 mel-spaced spectral bands, 12 cepstral coefficients,
bandwise spectral flatness, spectral centroid, cepstral periodicity and change.
Their 200 ms and 1 s means plus 1 s variability give 132 inputs. A roughly 53 KB
JSON model contains 80 small decision trees; inference is implemented in Python
and NumPy. Scikit-learn and downloaded music are **not runtime dependencies**.

The classifier score rises with a 250 ms EMA and falls with a 500 ms EMA.
Activation uses the validation-selected threshold 0.7, release uses 0.6, and
there is a one-second warm-up. Silence forces inactivity. Actual detection delay
varies with the mix and score trajectory; the 23 ms update period is not a
23 ms vocal-onset latency claim.

The tracker additionally exposes cautious acoustic cues:

- **Envelope:** recent midrange energy relative to its slower average, gated by
  vocal-like activity. It still contains instruments.
- **Articulation / delivery:** observed envelope variation, described as
  `sustained`, `articulated`, or `uncertain`. These are not trained singing/rap labels.
- **Tonal pitch / register:** a dominant periodic component, exposed only when
  both activity and periodicity are strong. It may belong to an instrument,
  may have octave errors, and does not identify the singer's pitch or gender.
- **Phrase pulse:** a provisional 1–8 Hz envelope-modulation estimate, requiring
  at least three seconds of history and mostly active windows within a rolling
  five seconds. It is not word counting, vocal isolation, BPM, or a reliable
  measurement of vocal swing. Percussion can contribute, and octave ambiguity
  remains. This estimate is logged; it does not drive a free-running light chase.

Pitch processing, harmonizers, doubles and overlapping voices make male/female
inference particularly unreliable. No such classifier or demographic label is
implemented. The lead/backing distinction also remains unresolved.

## Lighting behavior

The experimental layer is enabled by default, with intentionally limited effect:

- Since version 0.4, persistent vocal-like activity makes palette choices smaller
  and slower. The minimum wait for an attack-timed change grows from 8 to 16
  audible seconds, the hue step shrinks by up to 55%, and the transition time
  constant grows from 2.5 to 6 seconds. A new target is chosen after at most
  24 audible seconds even if no attacks arrive. Silence pauses this timer.
- The outer fixtures move toward a closer color relationship and soften their
  saturation slightly.
- A small outer-fixture glow follows the observed envelope. Sustained passages
  tend to hold that glow; articulated passages vary it more.
- Low/mid/high attack routes remain available. Independent percussion evidence
  now softens ambiguous attacks and adds a shared bloom (see [ATTACKS.md](ATTACKS.md)). Brightness stays bounded,
  and the extra glow scales with overall loudness so silence still becomes black.
- On uncertain/inactive passages, the layer smoothly fades away.

Disable both the extra analysis cost and its lighting influence with `--no-vocals`.
The effect is deliberately usable even when the detector confuses an instrument
for a voice: it gently changes the wash rather than triggering a dramatic scene.
The vocal detector and trained model are unchanged in version 0.4; the new palette
policy limits the visual consequences of persistent predictions. It does not
improve the vocal accuracy numbers above.

## Try it and inspect the measurements

Run normally to include the new layer, or add `--no-vocals` for comparison. For
live SSL input without DMX output, replace the device identifier:

```sh
.venv/bin/rated-rip --device plughw:CARD=SSL_CARD_ID,DEV=0 \
  --duration 30 --vocal-log vocals.jsonl
```

Logs contain numerical cues, not audio. Existing files are preserved; use a new
filename for each run. The console also prints `vocal_score` and `vocal_active`.
For an existing 16-bit PCM mono/stereo WAV at 44.1 or 48 kHz:

```sh
.venv/bin/python -m rated_rip.analyze your-mix.wav \
  --output attacks.jsonl --vocal-output vocals.jsonl
```

## Reproduce the research

The music is retained outside the checkout in the cloud research workspace and
is not included in the software ZIP, wheel, or repository. The provider offers
these excerpts for research/prototyping; its software license is not a blanket
license for the music. Consult the dataset provider's terms for other uses.

On a research machine with FFmpeg available:

```sh
.venv/bin/python -m pip install -e '.[research]'
.venv/bin/python tools/download_vocal_examples.py --directory /path/to/musdb7
.venv/bin/python tools/evaluate_vocals.py --dataset /path/to/musdb7 \
  --cache /path/to/features --fit /path/to/new-model.json --report /path/to/new-report.json
.venv/bin/python tools/plot_vocal_examples.py --dataset /path/to/musdb7 \
  --output-dir /path/to/new-plots
```

The evaluator caches features, keeps track-level splits separate, checks exported
model predictions against scikit-learn, and refuses to replace existing model or
report files. The plot script uses the bundled model; it does not automatically
activate a newly fitted model. Repeated experimentation should use a new untouched
test corpus before claiming further improvements; the current test results are
now known. No download, training, or model update occurs during a performance.
