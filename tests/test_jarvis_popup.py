import gc
import tkinter as tk
import unittest
from unittest.mock import patch

from jarvis_popup import PopupApp


class PopupTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        with patch.dict('os.environ', {'JARVIS_SENSOR_DISABLED': '1'}), patch('jarvis_shortcut.load_key', return_value=''), patch.object(PopupApp, 'hotkey_loop'):
            self.app = PopupApp(self.root)
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.app = None
        self.root = None
        gc.collect()

    def test_command_and_confirm_controls_are_visible(self):
        self.assertTrue(self.app.box.winfo_ismapped())
        self.assertTrue(self.app.execute_button.winfo_ismapped())
        self.assertEqual(str(self.app.execute_button['state']), 'disabled')
        bottom = self.app.execute_button.winfo_rooty() + self.app.execute_button.winfo_height()
        self.assertLessEqual(bottom, self.root.winfo_rooty() + self.root.winfo_height())
        self.assertEqual(self.root.winfo_width(), 400)
        self.assertEqual(self.root.winfo_height(), 390)
        self.assertFalse(self.app.submit_button.winfo_ismapped())
        self.assertTrue(self.app.sensor_label.winfo_ismapped())

    def test_settings_uses_masked_key_field(self):
        self.app.show_settings()
        self.root.update()
        entries = []
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Entry): entries.append(child)
                visit(child)
        visit(self.app.settings_window)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].cget('show'))

    def test_shortcut_registration_error_shows_hidden_window(self):
        self.root.withdraw()
        self.app.events.put(('error', 'Shortcut unavailable'))
        self.app.poll()
        self.root.update()
        self.assertEqual(self.root.state(), 'normal')
        self.assertIn('unavailable', self.app.status.get())

    def test_sensor_distinguishes_unsupported_and_finalized(self):
        with patch.object(self.app, 'sensor_log'):
            self.app.handle_sensor_event('sensor_ready', {'text_edit_pattern_available': False})
            self.assertIn('inconclusive', self.app.sensor_status.get())
            self.assertFalse(self.app.sensor_observed)
            self.app.handle_sensor_event('composition_finalized', {'change_type': 3})
            self.assertTrue(self.app.sensor_observed)
            self.assertIn('observed', self.app.sensor_status.get())

    def test_shortcut_routes_to_active_diagnostic(self):
        from unittest.mock import Mock
        probe = Mock()
        probe.closed = False
        self.app.native_probe = probe
        self.app.on_shortcut()
        probe.on_shortcut.assert_called_once()
        self.app.native_probe = None

    def test_test_window_can_open_after_dictation_is_stopped(self):
        self.app.phase = 'waiting_text'
        with patch.object(self.app, 'log'), patch('composition_native_probe.NativeCompositionProbe') as probe:
            self.app.show_native_probe()
            probe.assert_called_once_with(self.app)
            self.assertEqual(self.app.phase, 'ready')
        self.app.native_probe = None

    def test_partial_text_is_never_sent_automatically(self):
        self.app.phase = 'waiting_text'
        self.app.box.insert('1.0', 'Open Google')
        self.root.update()
        with patch.object(self.app, 'submit') as submit:
            for _ in range(5): self.app.process_waiting_text()
            submit.assert_not_called()
        self.assertEqual(str(self.app.execute_button['state']), 'normal')

    def test_confirmed_text_runs_only_after_accepted_response(self):
        self.app.box.insert('1.0', 'Open Google Chrome.')
        self.root.update()
        self.app.phase = 'waiting_text'
        with patch.object(self.app, 'log'), patch.object(self.app, 'submit') as submit:
            self.app.run_command()
            submit.assert_called_once()
        with patch.object(self.app, 'log'), patch.object(self.app, 'execute') as execute:
            self.app.receive(self.app.revision, 'CHROME', 'Open Google Chrome.', ('ok', True, .1))
            execute.assert_called_once()

    def test_changed_or_rejected_request_does_not_auto_execute(self):
        self.app.box.insert('1.0', 'Open Chrome')
        self.root.update()
        revision = self.app.revision
        self.app.run_when_ready = True
        self.app.box.insert('end', ' and delete files')
        self.root.update()
        with patch.object(self.app, 'log'), patch.object(self.app, 'execute') as execute:
            self.app.receive(revision, 'CHROME', 'Open Chrome', ('ok', True, .1))
            execute.assert_not_called()
            self.app.run_when_ready = True
            self.app.receive(self.app.revision, 'CHROME', self.app.box.get('1.0', 'end-1c'), ('ok', False, .1))
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
