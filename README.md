# rated_rip

Live, song-independent lighting for a Raspberry Pi 3 B+, an SSL USB audio
interface, and three ADJ Mega TriPar fixtures. Python analyzes incoming audio;
an ENTTEC **DMX USB Pro-compatible** adapter sends a continuous DMX universe.
No playlists, YAML, pre-recorded tracks, cloud services, or song metadata.

**New to Raspberry Pi?** Follow [the first-boot guide](docs/FIRST_BOOT.md) to
flash the microSD, copy this program to the Pi, and run the first checks.
[Download the small Pi installation ZIP](https://github.com/briandal107/rated_rip/raw/refs/heads/main/downloads/rated-rip-pi.zip)
directly from GitHub. It includes version 0.4, the bundled model, documentation
and fast tests; the large MP3 fixtures stay in the repository.
OLA is not required: this version uses the ENTTEC USB Pro serial protocol directly.

Version 0.4 includes an **experimental vocal-activity layer**, evaluated on
real MUSDB excerpts with separate vocal stems. It is enabled by default and can
be disabled with `--no-vocals`. The held-out results are mixed: 68% recall of
vocal-positive windows and 19% false positives on vocal-negative windows. It
estimates vocal-like content, not reliably lead vocals, gender, singing, or rap.
Read [the vocal experiment and results](docs/VOCALS.md) before relying on it.

The [original eight-track replay](docs/SONG_TESTS.md) exposed excessive palette
holds during vocal-like activity. Version 0.4 adds bounded palette holds and
gentler accents for weak percussion evidence; see the
[before/after evaluation](docs/SONG_TESTS_V04.md). The owner-provided MP3s are under
`tests/audio/`. They are not vocal/drum detection ground truth.

## Attack-aware lighting

- RMS loudness with adaptive gain and attack/release smoothing drives brightness.
- Separate low-, mid-, and high-frequency onset detectors produce immediate
  accents, then refine each event with 30 ms and 90 ms descriptions.
- Low attacks emphasize the center fixture, mid attacks alternate between the
  outer fixtures, and high attacks add a smaller, shorter accent. The first and
  third DMX addresses are assumed to be the outer fixtures.
- Spectral balance, noisiness, crest factor, and decay shape influence the accent
  envelopes. Noisy/flat-topped attacks soften saturation slightly. These are
  descriptions of the captured mix, not reliable instrument or compressor labels.
- Fast level rise, spectral concentration and observed decay provide a separate
  percussion-evidence score. Weak evidence produces a gentler spatial accent and
  a small shared bloom; strong evidence retains faster low/mid/high accents.
- Spectral entropy (frequency spread, a rough density proxy) slowly widens the palette
  and changes movement speed. This is not a musical complexity measurement.
- Detected attacks occasionally trigger randomized, smoothly blended palette changes.
  A 24-audible-second fallback also works without attacks. Three related colors
  and gentle spatial movement keep the chain coordinated.
- Silence fades to black; default maximum brightness is 65%. No strobe channels.
- When vocal-like activity persists, a small additional layer steadies the
  palette and lets the outer fixtures breathe together. Palette changes become
  smaller and slower, with an 8–16-second minimum opportunity and 2.5–6-second
  transition time constant. Vocals never veto palette changes indefinitely.
  The layer uses an observed envelope, not invented syllable timing.

This is an onset detector, not a BPM tracker or Serato/Rekordbox-style offline beat
analysis. Dense mixes and quiet passages can produce missed or extra accents.
See [attack analysis, research, and limitations](docs/ATTACKS.md) for the design,
measured synthetic results, and instructions for inspecting your own audio.
Hardware timing, input levels, and fixture behavior still need testing on the Pi.

## Hardware and wiring

1. Connect a spare **line-level** master/booth output from the DJ controller to
   the SSL's line inputs, using appropriate cables. Select line mode, turn phantom
   power off, and adjust gain to avoid clipping. Do not connect speaker-level output.
2. Connect the SSL and ENTTEC to the Pi's USB ports. Use a reliable Pi supply;
   a powered USB hub may be needed if bus power is unstable.
3. Connect ENTTEC DMX OUT → fixture 1 IN → fixture 2 IN → fixture 3 IN using DMX
   cable. Terminate the final fixture's DMX OUT with a 120-ohm DMX terminator.
4. Keep the fixtures at **d.001, d.005, d.009** (start addresses **1, 5, 9**),
   which match the program defaults. Set each fixture to **3-channel RGB DMX mode**.
   Confirm the exact fixture manual says these channels are red, green, blue.
   This program does not support the other fixture modes or their macros/strobe.
   Addresses select independent fixtures; the cables carry the whole universe.
   In this mode, RGB occupies channels 1–3, 5–7, and 9–11; the gaps are unused.
   The `d.xxx` address display alone does not identify the channel mode. Four-channel
   spacing also works with three-channel fixtures, but a fixture actually set to
   four-channel mode needs a different channel mapping that is not yet supported.

ENTTEC's **Open DMX USB** is NOT supported by this driver. Confirm the adapter's
label identifies a USB Pro-compatible model before using `--dmx-port`.

## Install on Raspberry Pi OS

Use a current **64-bit Raspberry Pi OS** on the Pi 3 B+ with Python 3.9 or newer.
A 64-bit OS is recommended for readily available NumPy wheels.

```sh
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip alsa-utils
cd /path/to/rated_rip
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dmx]'
```

If the user cannot access audio/serial devices, add that user to the `audio` and
`dialout` groups using `sudo usermod -aG audio,dialout "$USER"`, then log out/in.
Avoid running the program as root. Use `arecord -l` / `arecord -L` to find the SSL
capture device, and `ls /dev/serial/by-id/` to find a stable ENTTEC device path.

## Run and validate

First run entirely without hardware (JSON lighting output once per second):

```sh
.venv/bin/python -m rated_rip.cli --simulate --duration 10 --seed 7
.venv/bin/python -m unittest discover -s tests -v
```

Then test the real audio input **without DMX output**. Replace the ALSA device
with the name shown by `arecord -L`:

```sh
.venv/bin/python -m rated_rip.cli --device plughw:CARD=USB,DEV=0 --duration 15
```

The JSON RMS/loudness should follow the music, attack count should advance, and
silence should fade RGB to zero. Stereo channels are combined by spectral power,
so antiphase audio does not cancel and the analyzer never switches between inputs.
Capture uses signed 16-bit PCM, stereo, 44.1 kHz. ALSA `plughw` can convert the SSL's
native format; `--rate 48000` and `--channels 1` are also supported.

Once the adapter model and fixture modes are confirmed, enable output explicitly:

```sh
.venv/bin/python -m rated_rip.cli --device plughw:CARD=USB,DEV=0 \
  --dmx-port /dev/serial/by-id/REPLACE_WITH_ENTTEC_DEVICE --brightness 0.35
```

Start at low brightness and check each fixture's colors. `--addresses 1 5 9`
explicitly selects your current addresses; these are also the defaults.
Fixtures must still use RGB three-channel mode.
Omit `--duration` to run until Ctrl-C. SIGINT/SIGTERM and capture errors attempt a
blackout on exit. A power loss, unplugged USB cable, or killed process cannot
send blackout; configure the fixtures' DMX-loss behavior appropriately.

Audio arrives in 256-sample hops (~5.8 ms at 44.1 kHz), with an overlapping
1024-sample analysis window (~23 ms). DMX USB updates are limited to 30 Hz.
The capture command requests a 50 ms ALSA buffer and 10 ms periods; actual
latency includes device negotiation, audio buffering, USB/DMX and fixture response.
The small FFT is intended for Pi 3 hardware but has not yet been benchmarked there.

## Development environment

The cloud checkout is `/workspace/rated_rip`. Use the existing isolated checkout;
no additional Git worktree is needed. There is no audio/DMX hardware in the cloud.
Simulation, unit tests, and protocol framing can be checked here; live operation
requires the physical Pi, SSL, adapter, and fixtures. No audio is recorded to disk.
