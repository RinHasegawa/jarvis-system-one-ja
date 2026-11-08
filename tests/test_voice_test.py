import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from voice_test import record_audio, resample_audio, resolve_model_path, transcribe


class VoiceTest(unittest.TestCase):
    def test_model_resolution_requires_tokenizer_and_defaults_to_local(self):
        calls = []
        def download(name, **kwargs):
            calls.append((name, kwargs))
            return "fake_model"
        with patch.object(Path, "is_dir", return_value=False), patch.object(Path, "is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                resolve_model_path("small", False, download)
            self.assertTrue(calls[0][1]["local_files_only"])
        with patch.object(Path, "is_dir", return_value=False), patch.object(Path, "is_file", return_value=True):
            self.assertEqual(resolve_model_path("small", False, download), "fake_model")

    def test_model_resolution_only_downloads_when_requested(self):
        options = {}
        def download(name, **kwargs):
            options.update(kwargs)
            return "fake_model"
        with patch.object(Path, "is_dir", return_value=False), patch.object(Path, "is_file", return_value=True):
            resolve_model_path("small", True, download)
            self.assertFalse(options["local_files_only"])

    def test_resampling_filters_frequencies_above_new_nyquist(self):
        rate = 44100
        time = np.arange(rate, dtype=np.float64) / rate
        low = resample_audio(np.sin(2 * np.pi * 1000 * time).astype(np.float32), rate)
        high = resample_audio(np.sin(2 * np.pi * 12000 * time).astype(np.float32), rate)
        low_rms = np.sqrt(np.mean(low[100:-100] ** 2))
        high_rms = np.sqrt(np.mean(high[100:-100] ** 2))
        self.assertEqual(len(low), 16000)
        self.assertGreater(low_rms, 0.65)
        self.assertLess(high_rms, 0.01)

    def test_no_input_does_not_reach_transcription(self):
        class SilentDevice:
            def query_devices(self, device, kind):
                return {"max_input_channels": 1, "default_samplerate": 16000, "name": "fake"}

            def rec(self, frames, **kwargs):
                return np.zeros((frames, 1), dtype=np.float32)

        self.assertIsNone(record_audio(SilentDevice(), np, 1, None))

    def test_transcription_joins_returned_segments(self):
        class Segment:
            def __init__(self, text):
                self.text = text

        class FakeModel:
            def transcribe(self, audio, **kwargs):
                self.options = kwargs
                return iter([Segment(" メモ帳を"), Segment("開いて。")]), None

        model = FakeModel()
        self.assertEqual(transcribe(model, np.zeros(1)), "メモ帳を開いて。")
        self.assertEqual(model.options["language"], "ja")
        self.assertTrue(model.options["vad_filter"])


if __name__ == "__main__":
    unittest.main()
