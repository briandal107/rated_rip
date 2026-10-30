# Listening to attacks

Version 0.2 added causal attack evidence with immediate lighting feedback and
30/90 ms refinements. Attack analysis itself uses no trained model. Version 0.3
adds a separate, small bundled model for [experimental vocal activity](VOCALS.md).
No genre labels, song files, OLA, SciPy, librosa, or madmom runtime dependencies
are required.

## Research and design

Positive spectral differences reveal newly arriving frequency energy. Both
[librosa's onset-strength implementation](https://github.com/librosa/librosa/blob/main/librosa/onset.py)
and [madmom's onset detectors](https://github.com/CPJKU/madmom/blob/main/madmom/features/onsets.py)
describe this approach. Their discussion of Böck and Widmer's *Maximum Filter
Vibrato Suppression for Onset Detection* (DAFx 2013) is particularly relevant:
pitch movement should not automatically produce repeated attacks.

This implementation uses log-magnitude positive differences and a three-bin
frequency-neighbour maximum reference, plus adaptive thresholds, level-rise
checks and minimum band energy. It is a small custom detector, **not a faithful
implementation of SuperFlux**: that algorithm uses an appropriately spaced
filterbank, whereas this prototype uses linear FFT bins and three broad regions.
No source code from those libraries was copied into this project.

The scientific constraint is the time/frequency tradeoff: a 10 ms slice contains
only half of one 50 Hz cycle. It can locate an attack but cannot completely
describe that sound's bass content. A 90 ms observation gives much better bass
and decay context, at the cost of waiting for those samples. We do both:

1. Audio arrives every 256 samples: 5.80 ms at 44.1 kHz or 5.33 ms at 48 kHz.
2. Overlapping 1024-sample Hann-window FFTs cover about 23.2/21.3 ms.
   Channel powers are averaged; waveform channels are never summed or switched.
3. Onsets are detected separately in **35–250 Hz**, **250–4000 Hz**, and
   **4000–16000 Hz**. A local spectral-change peak is confirmed one hop later.
4. Each band has a 55 ms minimum retrigger interval. Different-band peaks within
   20 ms of the first detection are grouped; this is an intentional timing
   ambiguity, not proof that they belong to the same drum. There is no global
   quarter-second lockout.
5. An `onset` report starts the light response immediately. Its estimated onset
   timestamp backdates the detection by half the FFT window plus one hop. This
   is an approximation, not an exact sample-level drum boundary. Startup needs
   one analysis window, so an attack at the very start of capture may be missed.
6. `body` and `tail` reports describe the first 30 and 90 ms from that estimate,
   using the same event ID. They refine existing lighting envelopes without
   restarting them. They do not delay the first response by 90 ms.
   Optional `bands` reports add a newly confirmed coincident band immediately,
   so lighting need not wait for the next scheduled description.

The onset report describes the recent detection window. The body/tail reports
describe windows aligned to the estimated onset. Low-frequency estimates from
the short window are less reliable than the longer description. There is no
source separation: background sounds are still in those windows.

## What each descriptor means

| Descriptor | Meaning and limits |
| --- | --- |
| `bands` | Regions with detected attack activity; not instrument names. Nearby band peaks may be added in later reports. |
| `energy` | Low/mid/high power shares in the observed window, within 35–16000 Hz. The backing track contributes. |
| `centroid_hz` | Spectral center of mass, useful for describing brightness. |
| `flatness` | How noise-like the spectrum is. A deliberately distorted sound can score higher without containing extra instruments. |
| `crest_db` | Peak-to-RMS ratio, averaged over active channels. Low crest can accompany limiting, but also a clean sustained tone or a dense mix. It does not measure compressor ratio or gain reduction. |
| `plateau_fraction` | Fraction of adjacent near-peak samples that barely change. Can reveal a flat-topped waveform even after its gain has been reduced. Synth wave shapes can produce the same evidence. |
| `near_full_scale_fraction` | Fraction of received samples at or above 99.5% of digital full scale. Not proof of clipping inside the original track; analog clipping or attenuated digital clipping may not reach this level. |
| `tail_ratio` | Last-20-ms versus first-20-ms RMS ratio, bounded at 4. More informative in the 90 ms report. |
| `layered_evidence` | Coincident low and higher-band onsets with substantial energy in both regions. A kick plus snare may cause this; so can one drum with a tonal body and a noisy attack. |
| `overlapped` | Another detected event's observation window overlaps this event. Descriptions can be contaminated. Only overlaps known by the time of reporting can be flagged. |
| `rise_db` | RMS change from the 20 ms before the estimated onset to the available post-onset window, bounded to ±24 dB. Measured across channel powers; the mix and an imperfect onset boundary contribute. |
| `noisiness` | Spectral concentration relative to neighboring FFT bins, mapped to 0–1. Describes diffuse versus concentrated energy, including band-limited noise. Short windows and abrupt tonal entrances can appear noisy. |
| `percussiveness` | Heuristic 0–1 evidence from level rise, noisiness, and later decay. It is not a trained probability or an instrument label. |

An unusual hyperpop snare might therefore look like a bright, noisy attack with
a low crest factor, flat peaks, and a sustained tail. We can react to that
character without claiming to know its genre, sample layers, or production chain.

## Lighting choices

The former shared pulse is replaced by transient envelopes over a quieter color
wash. Assuming fixtures are placed left/center/right in address order:

- **Low-band attack:** a centered pulse with approximately 120–200 ms decay,
  depending on the observed tail.
- **Mid-band attack:** a stronger outer-fixture accent, alternating sides, with
  roughly 75–115 ms decay. Higher crest factors make that accent shorter.
- **High-band attack:** a smaller accent on the opposite outer fixture with
  about 65 ms decay; hat-like activity does not dominate the entire room.
- **Coincident bands:** several roles can participate in one combined gesture.
- **Noisy/flat-peaked texture:** a small reduction in saturation within the
  accent, while maintaining the surrounding palette.

Durations above are exponential time constants, not hard on/off durations.
Late descriptions adjust an envelope that is already aging. Accents are bounded,
retain the user brightness ceiling, and decay away; no strobe channels are used.
Slow coordinated palette changes remain; the counter is detected attacks, not BPM
or bars. The JSON summary now says `attacks` rather than `beats`.

Version 0.4 scales these spatial accents by percussion evidence. Low evidence
gives a softer onset (about 45 ms easing) and a small bloom shared by all three
fixtures (240 ms decay), instead of a full-strength snap. High evidence retains
the faster band-specific gestures. The bloom is bounded separately and shares
the overall brightness limit; it does not create a constant glow during silence.

The initial score combines level rise and spectral noisiness. At 30/90 ms,
observed decay refines that same event; a sustained tonal window tends to reduce
its score, while a fast decaying tonal kick can retain strong evidence. Crest
factor is not used as a mandatory percussion gate, so compression alone does
not disqualify a hit. Known overlapping events reduce the influence of negative
decay evidence, because another sound can fill an older hit's tail. Score changes
are smoothed over 30 ms without resetting the envelope's age.

An abrupt chord entrance can resemble a drum in the first window and gets a
provisional response. Later evidence cannot undo that already-emitted response.
Long boomy drums, reverb, distortion and mixed sources remain ambiguous. The
detector still reports all attacks; the change is in their descriptors and
lighting emphasis, not in claiming that fewer detected events means fewer drums.
This works with `--no-vocals` too and adds no trained model or runtime dependency.

## Inspect live audio without sending DMX

From the project directory on the Pi, replace the SSL device name:

```sh
.venv/bin/rated-rip --device plughw:CARD=SSL_CARD_ID,DEV=0 \
  --duration 30 --attack-log attacks.jsonl
```

The log records numbers and event metadata, not audio. Use a new filename each
time; existing files are not overwritten. Each completed event has onset/body/tail
rows with the same ID, plus any intermediate `bands` updates. The immediate row
is provisional. Events near shutdown can
lack body/tail rows because those future samples were never captured.

For a synthetic kick/snare/hat demonstration:

```sh
.venv/bin/rated-rip --simulate --duration 10 --seed 7 --attack-log demo.jsonl
```

For an existing **16-bit PCM WAV**, mono or stereo, at 44.1 or 48 kHz:

```sh
.venv/bin/python -m rated_rip.analyze your-mix.wav --output mix-attacks.jsonl
```

This offline command does not play audio or drive lights. It prints processing
time and report counts. A partial final hop is left unanalyzed (at most 255
samples), and pending reports at EOF are not completed with invented silence.
MP3, float WAV, and 24-bit WAV require conversion before using this command.

## Validation and remaining limits

The suite covers isolated low/mid/high attacks, timing at both sample rates,
100 ms repeated hits, simultaneous low/high content, different-band attacks
40 ms apart, sustained/vibrato tones, steady noise, stereo antiphase and channel
swaps, scaled clipping, lighting routing, no retrigger on refinements, output
bounds, silence, WAV replay, and DMX packet framing.

Run the separate synthetic evaluation from the project directory:

```sh
.venv/bin/python tools/evaluate_attacks.py
```

In the measured cloud run, each of eight cases contained 72 labeled hits at
125 ms spacing: low/mid/high events at 44.1 and 48 kHz, each in isolation, 20 dB
quieter, over a steady tone, and after hard limiting. All 72 matched in each case,
with no extra events. Matching uses a ±25 ms tolerance around the estimated
onset. The longest detection delay was about 20 ms. Processing ten seconds took
roughly 0.27–0.40 seconds on the cloud x86 machine, excluding hardware and logging.
These results are reproducible synthetic checks, **not an accuracy estimate for
commercial music or a Raspberry Pi performance measurement**.

Real mixes can contain vocals, synth stabs, sidechain modulation, EQ moves and
noise bursts that also trigger attacks. Dense backing audio can mask real hits.
Two hits closer than the grouping/retrigger intervals can merge or be missed.
Noise-like crescendos can produce provisional events while thresholds adapt.
Short-window waveform statistics cannot recover an isolated drum's compressor
settings or prove which sound layers were combined.

DMX is still sent at up to 30 Hz. ALSA requests 50 ms buffers and 10 ms periods;
the actual device may negotiate other values. Audio I/O, DMX scheduling, the
adapter and the lights add latency beyond the measured detector delay. Live
timing, appearance and CPU load still require testing on the Pi and fixtures.
