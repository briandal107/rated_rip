# Version 0.5: stronger response and four shows

The first physical test found version 0.4 too subtle. Its sustained background
and gentle percussion weighting left little visible contrast, especially with
the 35% brightness ceiling. Version 0.5 changes the lighting policy; audio attack
and vocal detection remain unchanged. There are no new runtime dependencies.

## The four schemes

| Name | Spatial behavior | Timing and color |
| --- | --- | --- |
| Pulse | Low-frequency attacks hit all three lights, strongest in the center. Mid/high accents pick out the sides. | Dim background, fast hits and short decays; contrasting side accents. |
| Chase | Low/mid attacks step left → center → right → center. High-only attacks decorate a neighbor. | Short trails and a changing accent color every four qualifying steps. It stops stepping when attacks stop. |
| Split | Low attacks drive the center. Mids light the outside pair with alternating emphasis; highs pick out a side. | Complementary center/outside colors and independent short envelopes. |
| Bloom | Broad swells across all fixtures, with slowly moving emphasis and more vocal glow. | Slower attack and longer decay, using a wider palette. |

These are acoustic cues, not reliable kick/snare/stem labels. Weak percussion
evidence still gives a gentler rise. The 30/90 ms event refinements never restart
a gesture or advance the chase. The strongest gesture at each fixture wins,
preventing dense mixes from accumulating into a constant bright wash.

The three punchier schemes have lower background levels than version 0.4.
Stronger accents and a faster level follower make the rise and fall more visible.
More saturated colors, complementary relationships and faster palette transitions
make color changes clearer. The existing `--brightness` value remains a hard
ceiling on every emitted RGB channel; start by keeping it at 0.35 for comparison.
All schemes fade to black on silence. UV remains off; there are no hardware
strobe or macro commands.

## Rotation and controls

The default is `--scheme auto --scheme-seconds 150`. Pulse starts first, followed
by the other three in shuffled order. Each cycle visits all four once; consecutive
cycles cannot repeat the same scheme at their boundary. `--seed 7` makes the
choices reproducible; omitting it varies the choices between runs.

The timer counts audible seconds and pauses in silence. After 150 seconds it
waits for a detected attack, for at most three additional audible seconds, then
starts the next scheme. Both schemes keep responding to audio during a 1.2-second
crossfade. This is not a beat-grid or phrase-boundary detector. Palette choices
within a scheme occur more often, and vocal cues cannot block scheme rotation.

- `--scheme pulse`, `--scheme chase`, `--scheme split`, or `--scheme bloom` holds
  that scheme for the whole run.
- `--scheme-seconds 20` gives a fast audition of automatic rotation. Restore 150
  or omit the flag for the show. Minimum supported interval: five seconds.
- The terminal reports `scheme` and `scheme_changes` alongside audio/RGB values.
- `--version` reports the application source version.

## Upgrade the already installed Pi

Stop the running program with Ctrl-C. These commands run **on the Pi over SSH**.
The backup excludes the existing Python environment, which the update preserves.
Paste the entire block, including the parentheses. It stops if any step fails.

```sh
(
  set -e
  cd "$HOME"
  curl -fL --retry 3 --connect-timeout 15 \
    https://github.com/briandal107/rated_rip/raw/refs/heads/main/downloads/rated-rip-pi-v0.5.zip \
    -o rated-rip-pi-v0.5.zip
  tar --exclude='rated_rip/.venv' --exclude='rated_rip/.git' \
    -czf "rated-rip-before-v05-$(date +%Y%m%d-%H%M%S).tar.gz" rated_rip
  unzip -o rated-rip-pi-v0.5.zip -d "$HOME"
  cd rated_rip
  .venv/bin/rated-rip --version
)
```

Expect `rated-rip 0.5.0`. The original installation used `pip install -e`, so the
existing entry point reads the updated source immediately. No dependency download,
microSD reflash or virtual-environment rebuild is needed. Installed package metadata
may still report 0.4.0 until reinstalled; `--version` reports the executing source.

For the confirmed SSL 2+, ENTTEC Pro and three Profile Plus fixtures:

```sh
.venv/bin/rated-rip --device plughw:CARD=S2,DEV=0 \
  --dmx-port /dev/serial/by-id/usb-ENTTEC_DMX_USB_PRO_EN544721-if00-port0 \
  --addresses 1 5 9 --brightness 0.35
```

Keep every fixture in **Ch04**, with addresses **d.001, d.005, d.009**. Use the same
working sample rate as before (`--rate 48000` if you needed it). This release still
uses manual startup; it does not install an automatic-start service.

To roll back, stop the program and extract your backup into your home directory.
The extra `lighting.py` file from 0.5 can remain: the restored 0.4 engine does not
import it. Your existing `.venv` remains usable.

## Validation and replay

The fast tests exercise attack contrast at 35%, different routing/decay behavior,
onset-only chase movement, bounded output and zero UV, silence, full rotation,
fixed-scheme selection, deterministic seeds and crossfade continuity. The existing
attack and vocal tests still apply.

`tools/replay_show.py` processes each complete supplied MP3 through automatic
rotation and all four fixed schemes, without normalizing the audio. The dashboard
lets you select a scheme and compare it to a saved earlier report. These previews
show RGB commands; fixture optics, perception and Pi processing latency still
require a physical rehearsal.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/replay_show.py --output-dir /tmp/rated-rip-v05 \
  --reference-dir /path/to/v04-report
```
