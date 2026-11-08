import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest

from dictation_probe import DictationProbe, ROOT


class ProbePersistenceTests(unittest.TestCase):
    def test_incremental_text_and_final_snapshot_are_saved(self):
        with TemporaryDirectory(dir=ROOT / '.cache') as folder:
            root = tk.Tk()
            root.withdraw()
            app = DictationProbe(root, Path(folder))
            try:
                app.start()
                app.text.insert('end', 'open')
                root.update()
                app.text.insert('end', ' chrome')
                root.update()
                events = [json.loads(x) for x in app.path.read_text(encoding='utf-8').splitlines()]
                self.assertEqual([e['text'] for e in events if e['event'] == 'text_changed'], ['open', 'open chrome'])
                app.save()
                final = json.loads(app.path.read_text(encoding='utf-8').splitlines()[-1])
                self.assertEqual(final['event'], 'trial_finished')
                self.assertEqual(final['text'], 'open chrome')
                self.assertEqual(final['text_changes'], 2)
            finally:
                app.close()

    def test_closing_preserves_an_incomplete_trial(self):
        with TemporaryDirectory(dir=ROOT / '.cache') as folder:
            root = tk.Tk()
            root.withdraw()
            app = DictationProbe(root, Path(folder))
            app.start()
            app.text.insert('end', 'unfinished')
            path = app.path
            app.close()
            final = json.loads(path.read_text(encoding='utf-8').splitlines()[-1])
            self.assertEqual(final['event'], 'trial_interrupted')
            self.assertEqual(final['text'], 'unfinished')


if __name__ == '__main__':
    unittest.main()
