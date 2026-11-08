"""Event-driven dictation to bounded, automatic Windows app launches."""
import ctypes
from ctypes import wintypes
import os
import sys
import tkinter as tk

from jarvis_command import permitted_phrase
from jarvis_event_test import EventTestApp


class EventActionApp(EventTestApp):
    def __init__(self, root):
        self.action_attempted = False
        super().__init__(root)
        root.title('JARVIS - Voice Actions')
        self.sensor_status.set('Text change → Jev → app launch. Chrome / Notepad only.')
        self.status.set('Ctrl+Shift+J: start / stop. Supported commands run automatically.')
        self.result.set('Say: Open Google Chrome, or Open Notepad.')
        self.execute_button.configure(text='AUTOMATIC · Chrome / Notepad', state='disabled')

    def log(self, event, **fields):
        super().log(event, mode='automatic_apps', **fields)

    def on_shortcut(self):
        if self.phase not in ('starting', 'recording', 'stopping', 'waiting_text') and not self.pending:
            self.action_attempted = False
        super().on_shortcut()

    def send_event_snapshot(self, text):
        super().send_event_snapshot(text)
        if self.pending:
            self.result.set('Waiting for Jev. Esc cancels this command.')

    def edited(self, event=None):
        was_changed = self.box.edit_modified()
        super().edited(event)
        if was_changed and self.action_attempted and self.changed_after_send:
            self.status.set('Text changed after a launch attempt. No further action will run.')
            self.result.set('The earlier launch cannot be undone automatically.')

    def handle_event_test_reply(self, outcome):
        was_pending = self.pending
        revision = self.revision
        unchanged = (not self.changed_after_send and
                     self.box.get('1.0', 'end-1c').strip() == outcome['text'])
        recorded = super().handle_event_test_reply(outcome)
        # All launch authorization is deterministic, independent of model text.
        target = permitted_phrase(outcome['text'])
        allowed = (recorded and was_pending and not self.action_attempted and outcome.get('ok')
                   and outcome.get('revision') == revision and unchanged
                   and target is not None and outcome.get('agrees') is True
                   and outcome.get('action') == 'OPEN_APP' and outcome.get('target') == target)
        if not allowed:
            if outcome.get('ok'):
                self.status.set('No launch: cancelled, changed, or outside supported commands.')
                self.result.set('Use one command: Open Google Chrome / Open Notepad.')
            return
        try:
            self.log('automatic_launch_authorized', target=target, text=outcome['text'])
        except OSError:
            self.status.set('Cannot save the launch record. Nothing will open.')
            return
        self.action_attempted = True
        self.proposal = (revision, target, outcome['text'])
        self.execute()
        self.result.set('Command processed: ' + target + '. Check the app window.')

    def run_command(self):
        self.status.set('Supported commands run automatically after Jev agrees.')


if __name__ == '__main__':
    os.environ['JARVIS_SENSOR_DISABLED'] = '1'
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\JARVISVoicePopup')
    if not mutex: raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        sys.exit(0)
    try:
        window = tk.Tk()
        if '--background' in sys.argv: window.withdraw()
        EventActionApp(window)
        window.mainloop()
    finally:
        kernel.CloseHandle(mutex)
