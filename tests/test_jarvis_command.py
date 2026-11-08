import tkinter as tk
import unittest
from unittest.mock import patch
from jarvis_command import permitted_phrase, validate, App


def response(action='OPEN_APP', target='CHROME'):
    return {'answers': {'action': {'type':'choice','choice':action,'probabilities':{'OPEN_APP':.9,'UNKNOWN':.1}},
                        'target': {'type':'choice','choice':target,'probabilities':{'CHROME':.9,'NOTEPAD':.05,'NONE':.05}}}}


class CommandsTest(unittest.TestCase):
    def test_narrow_commands_and_rejections(self):
        self.assertEqual(permitted_phrase('Open Google Chrome.'), 'CHROME')
        self.assertEqual(permitted_phrase('Please open Notepad'), 'NOTEPAD')
        for value in ('open google', "don't open chrome", 'open chrome and notepad', 'open chrome; delete files'):
            self.assertIsNone(permitted_phrase(value))

    def test_jev_validation_rejects_wrong_or_broken(self):
        self.assertTrue(validate(response(), 'CHROME'))
        self.assertFalse(validate(response(target='NOTEPAD'), 'CHROME'))
        bad = response()
        bad['answers']['action']['probabilities']['OPEN_APP'] = float('nan')
        with self.assertRaises(ValueError): validate(bad, 'CHROME')

    def test_edit_and_cancel_invalidate_proposal(self):
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        try:
            app.box.insert('1.0', 'open chrome')
            root.update()
            app.proposal = (app.revision, 'CHROME', 'open chrome')
            app.box.insert('end', ' please')
            root.update()
            self.assertIsNone(app.proposal)
            app.proposal = (app.revision, 'CHROME', 'open chrome please')
            with patch.object(app, 'log'):
                app.cancel()
            self.assertIsNone(app.proposal)
        finally:
            root.destroy()

    def test_response_proposal_can_be_executed_only_once(self):
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        try:
            app.box.insert('1.0', 'open chrome')
            root.update()
            with patch.object(app, 'log'), patch('jarvis_command.subprocess.Popen') as launch:
                app.receive(app.revision, 'CHROME', 'open chrome', ('ok', True, .1))
                self.assertIsNotNone(app.proposal)
                app.execute()
                app.execute()
                self.assertEqual(launch.call_count, 1)
        finally:
            root.destroy()

    def test_stale_reply_cannot_propose(self):
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        try:
            app.box.insert('1.0', 'open chrome')
            root.update()
            old = app.revision
            with patch.object(app, 'log'):
                app.cancel()
                app.receive(old, 'CHROME', 'open chrome', ('ok', True, .1))
            self.assertIsNone(app.proposal)
        finally:
            root.destroy()


if __name__ == '__main__': unittest.main()
