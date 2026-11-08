"""First-text-change to Jev experiment. It never launches applications."""
import ctypes
from ctypes import wintypes
import os
import sys
import threading
import time
import tkinter as tk

from jarvis_command import ask_jev, validate
from jarvis_popup import PopupApp


class EventTestApp(PopupApp):
    def __init__(self, root):
        self.event_triggered = False
        self.event_snapshot = None
        self.changed_after_send = False
        self.stop_change_pending = None
        super().__init__(root)
        root.title('JARVIS - Event to Jev test')
        self.sensor_status.set('Experiment: first text change → Jev. No app is opened.')
        self.status.set('Ctrl+Shift+J: start and stop. The first text change will be sent to Jev.')
        self.result.set('Test only. No action will be executed.')
        self.execute_button.configure(text='TEST ONLY · no action', state='disabled')

    def process_waiting_text(self):
        # The modified-event handler triggers the test; no timeout or polling trigger.
        if self.phase == 'waiting_text' and not self.event_triggered:
            self.status.set('Stopped. Waiting for the first non-empty text change...')

    def on_shortcut(self):
        if self.phase not in ('starting', 'recording', 'stopping', 'waiting_text') and not self.pending:
            self.event_triggered = False
            self.event_snapshot = None
            self.changed_after_send = False
            self.stop_change_pending = None
        super().on_shortcut()

    def wait_release_and_send(self, action, attempts=0):
        super().wait_release_and_send(action, attempts)
        if (action == 'stop' and self.phase == 'waiting_text' and self.stop_change_pending
                and not self.event_triggered):
            self.schedule_event_trigger(self.stop_change_pending)

    def edited(self, event=None):
        if not self.box.edit_modified():
            return
        self.box.edit_modified(False)
        text = self.box.get('1.0', 'end-1c')
        self.invalidate()
        if self.event_triggered and text.strip() != self.event_snapshot:
            self.changed_after_send = True
            self.status.set('Text changed after the trigger. The sent text may be incomplete.')
            self.result.set('Incomplete-input risk detected. No action executed.')
            try: self.log('event_test_later_edit', character_count=len(text))
            except OSError: self.status.set('Could not save later-edit evidence.')
        if self.phase == 'stopping' and not self.event_triggered and text.strip():
            self.stop_change_pending = text.strip()
        elif self.phase == 'waiting_text' and not self.event_triggered and text.strip():
            self.schedule_event_trigger(text.strip())

    def schedule_event_trigger(self, text):
        self.event_triggered = True
        self.event_snapshot = text
        self.root.after_idle(lambda snapshot=text: self.send_event_snapshot(snapshot))

    def send_event_snapshot(self, text):
        if self.phase != 'waiting_text' or self.stopping.is_set() or self.event_snapshot != text: return
        if self.box.get('1.0', 'end-1c').strip() != text:
            self.status.set('Text changed before sending. Trial stopped; try again.')
            try: self.log('event_test_changed_before_send', character_count=len(text))
            except OSError: pass
            self.phase = 'review'
            return
        if len(text) > 4000:
            self.status.set('Text is over the test limit. No request was sent.')
            self.phase = 'review'
            return
        key = self.key.get().strip()
        if not key:
            self.status.set('Add your TypeSafe key in Settings, then retry.')
            self.phase = 'review'
            return
        try:
            self.log('event_test_sent', text=text, character_count=len(text), model='jev-1.13.0',
                     trigger='first_nonempty_text_change', audio_saved=False)
        except OSError:
            self.status.set('Could not save the test. Nothing was sent.')
            self.phase = 'review'
            return
        self.phase = 'review'
        self.pending = True
        request_revision = self.revision
        self.status.set('Text change detected. Asking Jev...')
        self.result.set('Test only. No action will be executed.')
        events = self.events
        def work():
            started = time.perf_counter()
            try:
                response = ask_jev(text, key)
                target = response['answers']['target']['choice']
                agrees = validate(response, target)
                action = response['answers']['action']['choice']
                outcome = {'ok': True, 'action': action, 'target': target, 'agrees': agrees,
                           'seconds': round(time.perf_counter()-started, 3), 'text': text}
            except Exception as exc:
                outcome = {'ok': False, 'error': type(exc).__name__,
                           'seconds': round(time.perf_counter()-started, 3), 'text': text}
            outcome['revision'] = request_revision
            events.put(('event_test_reply', outcome))
        threading.Thread(target=work, daemon=True).start()

    def handle_event_test_reply(self, outcome):
        self.pending = False
        changed = self.changed_after_send or self.box.get('1.0', 'end-1c').strip() != outcome['text']
        try:
            self.log('event_test_reply', outcome='ok' if outcome['ok'] else 'error',
                     seconds=outcome['seconds'], changed_after_send=changed,
                     **({'action': outcome['action'], 'target': outcome['target']} if outcome['ok']
                        else {'error': outcome['error']}))
        except OSError:
            self.status.set('Jev replied, but the test log could not be saved.')
            return False
        if not outcome['ok']:
            self.status.set('Jev request failed. Check the saved key and internet.')
            self.result.set('No action was executed.')
        elif changed:
            self.status.set('Text changed after sending. Compare the saved test result.')
            self.result.set('Incomplete-input risk detected. No action executed.')
        else:
            self.status.set('Jev received the event-triggered text.')
            self.result.set('Jev: ' + outcome['action'] + ' / ' + outcome['target'] + '. No action executed.')
        return True

    def run_command(self):
        self.status.set('This is a Jev-only experiment. No action will run.')


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
        EventTestApp(window)
        window.mainloop()
    finally:
        kernel.CloseHandle(mutex)
