# Representative full-song integration fixtures

These eight MP3 files were supplied by the repository owner and explicitly
approved for inclusion in this testing suite. `manifest.json` records their
original filename labels, source formats, durations and SHA-256 checksums.
Titles are the supplied labels, not independently verified release metadata.

The fixtures total approximately 64 MiB and 26.6 minutes. They are separate from
fast synthetic tests and are not included in the installed application wheel.
They are not vocal/drum ground truth: there are no isolated stems or manually
annotated event times, so detector activity on these tracks is a prediction,
not an accuracy measurement.

From the project root, with FFmpeg and the `research` extras installed:

```sh
.venv/bin/python tools/replay_show.py --output-dir /tmp/rated-rip-song-tests --clips
```

This analyzes every decoded sample except an incomplete final hop (under 6 ms),
then generates per-song metrics, plots, a 30 fps RGB trace and 45-second video
previews with sound. The excerpts are selected automatically around a large
change in loudness or attack rate; their lighting state comes from the complete
continuous analysis, not a cold start at the excerpt boundary.

`index.html` lets you inspect or play the entire lighting trace, comparing the
current scheme and the vocal layer disabled. Select the corresponding MP3s in
its file picker for synchronized audio. The browser reads those files locally.
The plots/videos work when kept beside the HTML in the report directory.

To compare with a previously generated report of the same audio, add
`--reference-dir /path/to/previous-report`. The lower row then shows that saved
version, and the preview uses its original excerpt timestamps. Use a new output
directory when changing the comparison. `baseline-v0.3.json` and
`baseline-v0.4.json` preserve the measured numerical results; neither supplies
ground-truth vocal/drum labels. Version 0.4 also writes `percussion.json` with
causal event refinements: estimated time, report time, stage, percussion score,
rise dB, noisiness, tail ratio and overlap flag.

Use a fresh output directory after changing runtime code. Existing results are
reused only when both the source checksum and runtime/model/replay-tool fingerprint match.
The default replay settings are 44.1 kHz stereo PCM16, no loudness normalization,
seed 7, a 65% output ceiling and addresses 1/5/9. Display colors approximate DMX
commands; fixture optics, gamma, actual brightness and hardware delay are not
modeled. The MP3s are decoded/resampled to match the default live capture format.

To include the expensive integration checks in unittest discovery:

```sh
RATED_RIP_FULL_AUDIO_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
```

The integration checks assert complete processing, valid finite output, DMX
bounds and reproducibility metadata. They do not assert that a vocal prediction
or a lighting choice is musically correct.
