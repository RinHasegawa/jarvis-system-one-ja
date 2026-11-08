import gc
import os
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from jarvis_event_test import EventTestApp


def response():
    return {'answers': {
        'action': {'type': 'choice', 'choice': 'OPEN_APP', 'probabilities': {'OPEN_APP': .9, 'UNKNOWN': .1}},
        'target': {'type': 'choice', 'choice': 'CHROME', 'probabilities': {'CHROME': .9, 'NOTEPAD': .05, 'NONE': .05}}}}


class EventTestTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        with patch.dict(os.environ, {'JARVIS_SENSOR_DISABLED': '1'}), patch('jarvis_shortcut.load_key', return_value=''), patch.object(EventTestApp, 'hotkey_loop'):
            self.app = EventTestApp(self.root)
        self.root.update()
        self.app.key.set('synthetic-test-key')

    def tearDown(self):
        self.app.close()
        self.app = None
        self.root = None
        gc.collect()

    def test_change_after_stop_sends_once_without_action(self):
        self.app.phase = 'waiting_text'
        with patch.object(self.app, 'log'), patch('jarvis_event_test.ask_jev', return_value=response()) as ask, patch.object(self.app, 'execute') as execute:
            self.app.box.insert('1.0', 'Open Google Chrome please')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                self.root.update()
                if ask.called and not self.app.pending: break
                time.sleep(.01)
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(ask.call_args.args[0], 'Open Google Chrome please')
            self.assertIn('OPEN_APP', self.app.result.get())
            execute.assert_not_called()

    def test_edit_before_stop_does_not_send(self):
        self.app.phase = 'recording'
        with patch.object(self.app, 'log'), patch('jarvis_event_test.ask_jev') as ask:
            self.app.box.insert('1.0', 'Open Google Chrome')
            self.root.update()
            ask.assert_not_called()
            self.assertFalse(self.app.event_triggered)

    def test_later_text_change_marks_trial_as_uncertain(self):
        self.app.phase = 'review'
        self.app.event_triggered = True
        self.app.event_snapshot = 'Open Chrome'
        with patch.object(self.app, 'log'):
            self.app.box.insert('1.0', 'Open Chrome and Notepad')
            self.root.update()
            self.app.handle_event_test_reply({'ok': True, 'action': 'OPEN_APP', 'target': 'CHROME',
                                              'seconds': .1, 'text': 'Open Chrome'})
        self.assertTrue(self.app.changed_after_send)
        self.assertIn('risk', self.app.result.get())


if __name__ == '__main__': unittest.main()
