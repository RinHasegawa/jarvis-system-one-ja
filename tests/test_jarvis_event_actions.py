import gc
import os
import tkinter as tk
import unittest
from unittest.mock import patch
from jarvis_event_actions import EventActionApp


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        with patch.dict(os.environ, {'JARVIS_SENSOR_DISABLED': '1'}), patch('jarvis_shortcut.load_key', return_value=''), patch.object(EventActionApp, 'hotkey_loop'):
            self.app = EventActionApp(self.root)
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.app = None
        self.root = None
        gc.collect()

    def prepare(self, text='Open Google Chrome.'):
        self.app.box.insert('1.0', text)
        self.root.update()
        self.app.pending = True
        return {'ok': True, 'text': text, 'action': 'OPEN_APP', 'target': 'CHROME',
                'agrees': True, 'revision': self.app.revision, 'seconds': .1}

    def test_allowed_action_runs_once(self):
        outcome = self.prepare()
        with patch.object(self.app, 'log'), patch('jarvis_command.subprocess.Popen') as launch:
            self.app.handle_event_test_reply(outcome)
            self.app.handle_event_test_reply(outcome)
        self.assertEqual(launch.call_count, 1)

    def test_long_request_cannot_silently_run_only_one_part(self):
        outcome = self.prepare('Open Google Chrome and search for AI news.')
        with patch.object(self.app, 'log'), patch('jarvis_command.subprocess.Popen') as launch:
            self.app.handle_event_test_reply(outcome)
        launch.assert_not_called()

    def test_cancel_blocks_old_reply(self):
        outcome = self.prepare()
        with patch.object(self.app, 'log'), patch('jarvis_command.subprocess.Popen') as launch:
            self.app.cancel()
            self.app.handle_event_test_reply(outcome)
        launch.assert_not_called()

    def test_changed_text_blocks_launch(self):
        outcome = self.prepare()
        with patch.object(self.app, 'log'), patch('jarvis_command.subprocess.Popen') as launch:
            self.app.box.insert('end', ' and Notepad')
            self.root.update()
            self.app.handle_event_test_reply(outcome)
        launch.assert_not_called()

    def test_wrong_target_and_failed_log_block_launch(self):
        outcome = self.prepare()
        outcome['target'] = 'NOTEPAD'
        with patch.object(self.app, 'log'), patch('jarvis_command.subprocess.Popen') as launch:
            self.app.handle_event_test_reply(outcome)
        launch.assert_not_called()
        self.app.pending = True
        outcome['target'] = 'CHROME'
        with patch.object(self.app, 'log', side_effect=OSError), patch('jarvis_command.subprocess.Popen') as launch:
            self.app.handle_event_test_reply(outcome)
        launch.assert_not_called()


if __name__ == '__main__': unittest.main()
