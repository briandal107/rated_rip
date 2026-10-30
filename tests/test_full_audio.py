"""Optional mechanical integration checks on owner-provided song fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('RATED_RIP_FULL_AUDIO_TESTS') == '1',
                     'Full-song replay is opt-in; set RATED_RIP_FULL_AUDIO_TESTS=1')
class FullAudioTests(unittest.TestCase):
    def test_all_tracks_complete_with_bounded_dmx(self):
        spec = importlib.util.spec_from_file_location('replay_show', ROOT / 'tools/replay_show.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest = json.loads((ROOT / 'tests/audio/manifest.json').read_text())
        self.assertEqual(len(manifest), 8)
        with tempfile.TemporaryDirectory(prefix='rated-rip-full-audio-') as directory:
            for track in manifest:
                with self.subTest(track=track['id']):
                    result = module.run_track(track, Path(directory), 'integration-test')
                    self.assertLess(abs(result['duration_seconds'] - track['duration']), 0.2)
                    self.assertGreater(result['frames'], result['duration_seconds'] * 29)
                    self.assertLessEqual(result['maximum_dmx_channel'], 166)
                    self.assertGreater(result['attacks'], 0)
                    self.assertLess(result['trailing_samples_not_analyzed'], 256)


if __name__ == '__main__':
    unittest.main()
