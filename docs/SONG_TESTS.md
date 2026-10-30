# Eight-track lighting replay: version 0.3

All eight user-provided MP3s were processed in full: **26.6 minutes**. This is a
replay of the existing version 0.3 behavior; the detector/model and lighting rules
were not tuned against these tracks. There are no isolated stems or hand-labeled
onsets, so the table reports model behavior, not detection accuracy.

Each track starts with fresh state, seed 7, a 65% DMX ceiling, and fixtures at
1/5/9. FFmpeg decodes the source at its existing gain into 44.1 kHz stereo PCM16,
matching the default live-input format. There is no loudness normalization.
Only a partial final hop (under 6 ms) is omitted. The output is sampled at 30 fps
without allowing future audio samples into a rendered frame.

The comparison disables only the vocal-driven lighting layer while reusing the
same audio features. Differences in later random palette choices follow naturally
from the different timings of palette changes. These are commanded RGB values,
not calibrated brightness or a model of beams, room surfaces, USB/DMX latency,
or the Raspberry Pi's CPU. Separate-track runs do not test DJ transitions.

## Measurements

Vocal cue percentages use frames with adaptive loudness above 5%. Attack rates
count all detected transients, not just drums. Palette changes count new target
hues; changes in brightness and color spread still occur between those targets.

| Track | Attacks/s | Vocal cue active | Palette changes: on / off | Longest palette hold |
| --- | ---: | ---: | ---: | ---: |
| EsDeeKid, fakemink - LV Sandals | 4.23 | 98% | 0 / 12 | 111.2 s |
| underscores - Innuendo (I Get U) | 3.87 | 89% | 4 / 22 | 68.1 s |
| NOTION - UNCONDITIONAL ft Nate Sib | 4.32 | 51% | 13 / 18 | 24.0 s |
| Kettama - Comes and Goes | 4.47 | 68% | 14 / 28 | 46.4 s |
| Aaron Hibell - i think i'm in love | 4.67 | 39% | 14 / 20 | 28.1 s |
| Skrillex - Fuji Opener | 5.62 | 91% | 2 / 18 | 148.2 s |
| Olivia Rodrigo - stupid song | 4.13 | 82% | 8 / 22 | 46.5 s |
| Imogen Heap - Hide and Seek | 2.46 | 91% | 5 / 26 | 113.4 s |

## Findings

- **LV Sandals:** 470 attacks, but no palette changes throughout the 111-second
  track. With the vocal layer off, there are 12. This exposes the indefinite
  palette-hold behavior caused by vocal activity, independent of whether the
  vocal prediction is correct.
- **Innuendo:** the cue is active for 89% of audible frames; palette changes drop
  from 22 to four, with a maximum hold of 68 seconds. Transient accents continue.
- **UNCONDITIONAL:** the vocal state varies more, and the scheme retains 13 of the
  18 palette changes seen with the vocal layer off. The diagnostic timeline shows
  clear changes in attack activity around 40–67 seconds and 125–140 seconds;
  these are measurable texture changes, not automatically labeled song sections.
- **Comes and Goes:** the scheme produces 1,171 attacks and 14 palette changes;
  the vocal layer roughly halves palette activity compared with its disabled state.
- **i think i'm in love:** the vocal cue is least active here (39%), leaving 14
  palette changes. The center fixture has the highest average commanded brightness
  (0.29 versus 0.24 for the outer fixtures), consistent with substantial low-band
  accent routing. This does not establish which instruments made those attacks.
- **Fuji Opener:** the highest average attack rate (5.62/s) coincides with a 91%
  vocal-active prediction and just two palette changes. A target hue holds for
  148 seconds. This makes the vocal gate visually dominant despite busy attack
  activity and is a priority for review; the activity percentage is not a vocal
  accuracy score.
- **stupid song:** 866 attacks and eight palette changes, compared with 22 without
  the vocal layer; its longest palette hold is 46 seconds.
- **Hide and Seek:** the vocal cue is active for 91% of audible playback, producing
  relatively stable color families. There are nevertheless 660 detected attacks.
  For this user-described vocal/vocoder ballad, those events must not be taken as
  evidence of drum hits. Frequency-based attack routing still applies to them.

The strongest design issue is the **hard veto on new palettes during vocal-like
activity**. The cue should be allowed to influence scene cohesion without freezing
hue indefinitely. A second design question is how strongly to accent changes in
sustained vocal/harmonic music versus percussion. The current detector recognizes
attacks; it does not reliably identify their source. More palette changes are not
inherently better: the disabled comparison is a diagnostic, not a recommendation
that every track should run through colors faster.

## Preview and reproduction

The generated report contains a full-song interactive HTML viewer, per-song
plots, and eight 45-second audio/video comparisons. The preview window is chosen
by a change in measured loudness/attack rate, after full-song analysis. It is not
a hand-picked best moment. Select the original MP3 files in the viewer to hear
full-song synchronized playback; they remain local to the browser.

```sh
.venv/bin/python tools/replay_show.py --output-dir /tmp/rated-rip-song-tests --clips
RATED_RIP_FULL_AUDIO_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_full_audio.py -v
```

The source fixtures, checksums and recorded numerical baseline are under
`tests/audio/`. The large full-song check is optional during ordinary unit testing.
The recordings are included in the repository with the owner's authorization.
The evaluation was completed before repository publication.
