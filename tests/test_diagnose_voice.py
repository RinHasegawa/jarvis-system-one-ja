import unittest
import numpy as np
from diagnose_voice import normalize, word_errors, evaluate


class DiagnosticTests(unittest.TestCase):
    def test_word_error_distance(self):
        self.assertEqual(word_errors('Open Google Chrome', 'open google chrome'), (0, 3))
        self.assertEqual(word_errors('open google chrome', 'open chrome'), (1, 3))
        self.assertEqual(word_errors('open spotify', ''), (2, 2))
        self.assertEqual(normalize("What's up?"), ["what's", 'up'])

    def test_silence_does_not_produce_nonfinite_metrics(self):
        class FakeRecognizer:
            def AcceptWaveform(self, data): return False
            def PartialResult(self): return '{"partial":""}'
            def FinalResult(self): return '{"text":""}'
        from unittest.mock import patch
        with patch('diagnose_voice.KaldiRecognizer', return_value=FakeRecognizer()):
            text, _, first, diff, signal, _ = evaluate(None, np.zeros(44100, dtype=np.float32), 44100)
        self.assertEqual((text, first, diff, signal), ('', None, 0, 0))


if __name__ == '__main__':
    unittest.main()
