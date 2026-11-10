import ctypes
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from jarvis_shortcut import INPUT, ShortcutApp


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        with patch.object(ShortcutApp, 'hotkey_loop'):
            self.app = ShortcutApp(self.root)
        self.root.update()

    def tearDown(self):
        self.app.close()

    def test_one_shortcut_starts_then_stops(self):
        with patch.object(self.app, 'log'), patch.object(self.app, 'wait_release_and_send') as send:
            self.app.on_shortcut()
            self.assertEqual(self.app.phase, 'starting')
            send.assert_called_once_with('start')
            self.app.phase = 'recording'
            self.app.on_shortcut()
            self.assertEqual(self.app.phase, 'stopping')
            self.assertEqual(send.call_args.args, ('stop',))

    def test_cancel_blocks_scheduled_input(self):
        self.app.phase = 'starting'
        with patch.object(self.app, 'log'), patch('jarvis_shortcut.send_dictation_shortcut') as send:
            self.app.cancel()
            self.app.wait_release_and_send('start')
            send.assert_not_called()

    def test_text_arrival_submits_once_after_settling(self):
        with patch.object(self.app, 'log'), patch.object(self.app, 'submit') as submit:
            self.app.box.insert('1.0', 'Open Chrome')
            self.root.update()
            self.app.phase = 'waiting_text'
            self.app.wait_started = 1
            self.app.last_text = 'Open Chrome'
            self.app.changed_at = 2
            with patch('jarvis_shortcut.time.monotonic', return_value=4):
                self.app.poll()
                self.app.poll()
            submit.assert_called_once()
            self.assertEqual(self.app.phase, 'review')

    def test_windows_input_structure_has_native_size(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_health_records_registration_failure_and_received_hotkey_without_text(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'diagnostic_results') as folder:
            self.app.health_path = Path(folder) / 'health.jsonl'
            self.app.box.insert('1.0', 'private dictated words')
            self.app.events.put(('registration_failed', 1409))
            self.app.events.put(('shortcut', None))
            with patch.object(self.app, 'on_shortcut'):
                self.app.poll()
            contents = self.app.health_path.read_text(encoding='utf-8')
            entries = [json.loads(line) for line in contents.splitlines()]
            self.assertEqual([e['event'] for e in entries[:2]], ['hotkey_registration_failed', 'hotkey_received'])
            self.assertEqual(entries[0]['windows_error'], 1409)
            self.assertNotIn('private dictated words', contents)


if __name__ == '__main__':
    unittest.main()
