# Version 0.5 full-song checks

The eight owner-provided songs (26.6 minutes) were each replayed continuously
through automatic rotation and all four fixed schemes, at seed 7, 44.1 kHz stereo,
a 65% ceiling and 30 fps output sampling. Source audio was not normalized. The
reference is the saved version 0.4 replay with the same parameters.

All eight automatic traces and 32 fixed-scheme traces passed finite/range and
frame-coverage checks. Every saved onset record and every vocal, loudness,
density and attack-count frame matched version 0.4. These are lighting changes;
there is no new detection-accuracy claim.

| Track | Automatic brightness variation vs. 0.4 | Palette targets | Scheme changes |
| --- | ---: | ---: | ---: |
| EsDeeKid, fakemink - LV Sandals | 1.80× | 10 | 0 |
| underscores - Innuendo (I Get U) | 2.10× | 20 | 1 |
| NOTION - UNCONDITIONAL ft Nate Sib | 1.77× | 21 | 1 |
| Kettama - Comes and Goes | 2.15× | 29 | 1 |
| Aaron Hibell - i think i'm in love | 2.33× | 23 | 1 |
| Skrillex - Fuji Opener | 2.26× | 17 | 1 |
| Olivia Rodrigo - stupid song | 2.12× | 21 | 1 |
| Imogen Heap - Hide and Seek | 2.06× | 23 | 1 |

Variation means the mean absolute step in each fixture's maximum RGB channel at
30 fps. This is a command-space contrast measure, not a measured perception or
fixture-brightness ratio. The comparison keeps the same ceiling. The darker
backgrounds make the average level lower in many passages while increasing the
size of the musical accents. Values at the user's 35% ceiling are proportionally
smaller, apart from integer rounding.

These tracks are each shorter than two complete default scheme intervals, so
short recordings remain in Pulse and longer ones make one transition. Separate
rotation tests cover all four schemes, repeated cycles, silence, continuous
vocals, the three-second deadline and crossfade continuity. Every full song was
also run with each scheme held fixed to exercise all four on the same material.

The attack/vocal heuristics remain imperfect: a vocoder or synth entrance can
still trigger an accent. Greater contrast makes both valid and mistaken cues more
visible. Physical Pi timing, fixture response and preference need a live audition.

Fast validation: 41 tests passed, with the optional full-audio unittest skipped;
the complete eight-song replay above was run separately. The report viewer allows
selection of Auto/Pulse/Chase/Split/Bloom, using the original MP3s locally for sound.
Numeric results, checksums and per-scheme metrics are in
`tests/audio/baseline-v0.5.json`. Reproduction commands and deployment instructions
are in [SCHEMES.md](SCHEMES.md).
