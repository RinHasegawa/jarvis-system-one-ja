import queue
import unittest
from unittest.mock import Mock, patch
from composition_native_probe import NativeCompositionProbe


class NativeProbeTests(unittest.TestCase):
    def make_probe(self):
        probe = NativeCompositionProbe.__new__(NativeCompositionProbe)
        probe.phase = 'waiting_text'
        probe.ready = True
        probe.text_seen = False
        probe.text_before_stop = False
        probe.stop_started_ns = 100
        probe.observed = False
        probe.trial = 1
        probe.hwnd = 123
        probe.status = Mock()
        probe.result = Mock()
        probe.finish_button = Mock()
        probe.log = Mock()
        return probe

    def test_shortcut_does_not_restart_while_waiting_for_text(self):
        probe = self.make_probe()
        probe.on_shortcut()
        self.assertEqual(probe.phase, 'waiting_text')
        self.assertEqual(probe.trial, 1)

    def test_shortcut_retries_after_text_arrives(self):
        probe = self.make_probe()
        probe.text_seen = True
        probe.last_length = 15
        probe.window = Mock()
        probe.wait_release = Mock()
        with patch('composition_native_probe.user32.SetWindowTextW'), patch('composition_native_probe.user32.SetFocus'), patch('composition_native_probe.user32.GetWindowTextLengthW', return_value=0):
            probe.on_shortcut()
        self.assertEqual(probe.phase, 'starting')
        self.assertEqual(probe.trial, 2)
        probe.wait_release.assert_called_once_with('start')

    def test_finish_requires_text_and_saves_precise_result(self):
        probe = self.make_probe()
        probe.finish_trial()
        probe.log.assert_not_called()
        probe.text_seen = True
        with patch('composition_native_probe.user32.GetWindowTextLengthW', return_value=20):
            probe.finish_trial()
        probe.log.assert_called_once_with('trial_finished', text_received=True, finalized_observed=False,
                                          final_character_count=20, ended_for_retry=False)
        self.assertEqual(probe.phase, 'ready')

    def test_empty_box_cannot_be_finished_as_complete(self):
        probe = self.make_probe()
        probe.text_seen = True
        with patch('composition_native_probe.user32.GetWindowTextLengthW', return_value=0):
            probe.finish_trial()
        self.assertEqual(probe.phase, 'waiting_text')
        probe.finish_button.configure.assert_called_with(state='disabled')
        probe.log.assert_not_called()

    def test_input_monitor_records_type_without_character(self):
        probe = self.make_probe()
        probe.input_events = queue.Queue()
        with patch('composition_native_probe.comctl32.DefSubclassProc', return_value=0), patch('composition_native_probe.user32.GetWindowTextLengthW', return_value=1):
            probe.window_message(None, 0x0102, ord('Q'), 123, 1, 0)
        item = probe.input_events.get_nowait()
        self.assertEqual(item['message'], 'character')
        self.assertEqual(item['character_count'], 1)
        self.assertNotIn('wparam', item)
        self.assertTrue(probe.input_events.empty())

    def test_text_before_stop_is_not_counted_as_new_result(self):
        probe = self.make_probe()
        probe.observe_input_message({'message': 'edit_change', 'character_count': 20,
                                     'phase_at_event': 'recording', 'trial_at_event': 1, 'monotonic_ns': 90})
        self.assertTrue(probe.text_before_stop)
        self.assertFalse(probe.text_seen)

    def test_only_current_trial_edit_after_stop_enables_finish(self):
        probe = self.make_probe()
        probe.observe_input_message({'message': 'edit_change', 'character_count': 20,
                                     'phase_at_event': 'waiting_text', 'trial_at_event': 0, 'monotonic_ns': 120})
        self.assertFalse(probe.text_seen)
        probe.observe_input_message({'message': 'edit_change', 'character_count': 20,
                                     'phase_at_event': 'waiting_text', 'trial_at_event': 1, 'monotonic_ns': 120})
        self.assertTrue(probe.text_seen)
        probe.finish_button.configure.assert_called_with(state='normal')


if __name__ == '__main__': unittest.main()
