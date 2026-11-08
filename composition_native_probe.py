"""Isolated Windows Rich Edit composition probe; never sends text or executes actions."""
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

from jarvis_shortcut import send_dictation_shortcut, user32

BG = '#10151f'
FG = '#edf4f7'
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
comctl32 = ctypes.WinDLL('comctl32', use_last_error=True)
kernel32.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
kernel32.LoadLibraryW.restype = wintypes.HMODULE
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wintypes.HWND
user32.SetFocus.argtypes = [wintypes.HWND]
user32.SetFocus.restype = wintypes.HWND
user32.GetFocus.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user32.SetWindowTextW.restype = wintypes.BOOL
user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LPARAM
SUBCLASSPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t)
comctl32.SetWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
comctl32.SetWindowSubclass.restype = wintypes.BOOL
comctl32.RemoveWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t]
comctl32.RemoveWindowSubclass.restype = wintypes.BOOL
comctl32.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
comctl32.DefSubclassProc.restype = wintypes.LPARAM
INPUT_MESSAGES = {0x0302: 'paste', 0x000C: 'set_text', 0x0102: 'character',
                  0x010D: 'ime_start', 0x010E: 'ime_end', 0x010F: 'ime_composition',
                  0x00C2: 'replace_selection', 0x0449: 'stream_in'}


class NativeCompositionProbe:
    def __init__(self, app):
        self.app = app
        self.phase = 'ready'
        self.ready = False
        self.observed = False
        self.closed = False
        self.trial = 0
        self.last_length = 0
        self.text_seen = False
        self.text_before_stop = False
        self.stop_started_ns = None
        self.events = queue.Queue()
        self.input_events = queue.Queue()
        self.log_path = Path(__file__).resolve().parent / 'diagnostic_results' / (
            'composition_native_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
        self.window = tk.Toplevel(app.root)
        self.window.title('JARVIS - Composition test')
        self.window.configure(bg=BG)
        self.window.geometry('510x390')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        body = tk.Frame(self.window, bg=BG, padx=18, pady=12); body.pack(fill='both', expand=True)
        tk.Label(body, text='COMPOSITION EVENT TEST', bg=BG, fg='#a7f3d0',
                 font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        tk.Label(body, text='Ctrl + Shift + J: start and stop dictation', bg=BG, fg=FG,
                 font=('Segoe UI', 10)).pack(anchor='w', pady=(4, 8))
        frame = tk.Frame(body, width=465, height=90, bg='white'); frame.pack(fill='x'); frame.pack_propagate(False)
        self.window.update_idletasks()
        self.library = kernel32.LoadLibraryW('Msftedit.dll')
        if not self.library: raise OSError('Windows Rich Edit is unavailable')
        self.hwnd = user32.CreateWindowExW(0, 'RICHEDIT50W', '', 0x500100C4,
            0, 0, frame.winfo_width(), frame.winfo_height(), frame.winfo_id(), None, None, None)
        if not self.hwnd: raise ctypes.WinError(ctypes.get_last_error())
        self.host_hwnd = frame.winfo_id()
        self.subclass_callback = SUBCLASSPROC(self.window_message)
        self.subclass_registered = bool(comctl32.SetWindowSubclass(self.hwnd, self.subclass_callback, 1, 0))
        self.parent_callback = SUBCLASSPROC(self.parent_message)
        self.parent_subclass_registered = bool(comctl32.SetWindowSubclass(self.host_hwnd, self.parent_callback, 2, 0))
        previous_mask = user32.SendMessageW(self.hwnd, 0x043B, 0, 0)  # EM_GETEVENTMASK
        user32.SendMessageW(self.hwnd, 0x0445, 0, previous_mask | 1)  # EM_SETEVENTMASK, ENM_CHANGE
        self.change_notifications_enabled = bool(user32.SendMessageW(self.hwnd, 0x043B, 0, 0) & 1)
        frame.bind('<Configure>', lambda e: user32.MoveWindow(self.hwnd, 0, 0, e.width, e.height, True))
        self.status = tk.StringVar(value='Starting Windows event sensor…')
        self.result = tk.StringVar(value='No finalized event observed yet.')
        tk.Label(body, textvariable=self.status, bg=BG, fg=FG, font=('Segoe UI', 9),
                 wraplength=465, justify='left').pack(anchor='w', pady=(10, 3))
        tk.Label(body, textvariable=self.result, bg=BG, fg='#a7f3d0', font=('Segoe UI', 10, 'bold'),
                 wraplength=465, justify='left').pack(anchor='w')
        tk.Label(body, text='Diagnostic only: no text is sent to Jev and no action is run.',
                 bg=BG, fg='#a6b6c4', font=('Segoe UI', 8)).pack(anchor='w', pady=(12, 0))
        buttons = tk.Frame(body, bg=BG); buttons.pack(fill='x', side='bottom')
        self.finish_button = tk.Button(buttons, text='Finish trial', command=self.finish_trial, state='disabled')
        self.finish_button.pack(side='left')
        tk.Button(buttons, text='Reset', command=self.reset_trial).pack(side='left', padx=8)
        tk.Button(buttons, text='Close test', command=self.close).pack(side='right')
        self.log('sensor_started', audio_saved=False, text_payload_saved=False, scope='native_probe_input_only')
        self.log('input_message_sensor_ready' if self.subclass_registered else 'input_message_sensor_error')
        self.log('edit_notification_sensor_ready' if self.parent_subclass_registered and self.change_notifications_enabled
                 else 'edit_notification_sensor_error')
        helper = Path(__file__).resolve().parent / 'composition_sensor.py'
        self.process = subprocess.Popen([sys.executable, str(helper), str(self.hwnd)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=self.app.read_sensor, args=(self.process, self.events), daemon=True).start()
        self.window.after(50, self.poll)

    def log(self, event, **fields):
        self.log_path.parent.mkdir(exist_ok=True)
        with self.log_path.open('a', encoding='utf-8') as out:
            out.write(json.dumps({'time': datetime.now().astimezone().isoformat(), 'event': event,
                                  'trial': self.trial, 'phase': self.phase, **fields}) + '\n')
            out.flush()

    def window_message(self, hwnd, message, wparam, lparam, subclass_id, data):
        # Never record wParam/lParam: they can contain dictated characters or pointers to text.
        result = comctl32.DefSubclassProc(hwnd, message, wparam, lparam)
        if message in INPUT_MESSAGES:
            self.input_events.put({'message': INPUT_MESSAGES[message], 'monotonic_ns': time.monotonic_ns(),
                                   'trial_at_event': self.trial, 'phase_at_event': self.phase,
                                   'character_count': user32.GetWindowTextLengthW(self.hwnd)})
        return result

    def parent_message(self, hwnd, message, wparam, lparam, subclass_id, data):
        # EN_CHANGE is emitted by this Rich Edit control, not a global keyboard hook.
        if message == 0x0111 and ((wparam >> 16) & 0xffff) == 0x0300 and lparam == self.hwnd:
            self.input_events.put({'message': 'edit_change', 'monotonic_ns': time.monotonic_ns(),
                                   'trial_at_event': self.trial, 'phase_at_event': self.phase,
                                   'character_count': user32.GetWindowTextLengthW(self.hwnd)})
        return comctl32.DefSubclassProc(hwnd, message, wparam, lparam)

    def poll(self):
        if self.closed: return
        try:
            while True:
                event, detail = self.events.get_nowait()
                self.log(event, **detail)
                if event == 'sensor_ready':
                    self.ready = bool(detail.get('text_edit_pattern_available'))
                    if self.ready and self.subclass_registered and self.parent_subclass_registered and self.change_notifications_enabled:
                        self.status.set('Sensors ready. Press Ctrl + Shift + J to begin.')
                    elif self.ready:
                        self.status.set('Composition sensor ready; input-message sensor unavailable.')
                    else:
                        self.status.set('TextEdit support unavailable; this test would be inconclusive.')
                elif event == 'composition_finalized':
                    if self.phase in ('recording', 'stopping', 'waiting_text'):
                        self.observed = True
                        self.result.set('Finalized event observed. Check its timing in the trial log.')
                elif event in ('sensor_error', 'sensor_exited'):
                    self.ready = False
                    self.status.set('Sensor unavailable. See the saved diagnostic log.')
        except queue.Empty: pass
        except OSError:
            self.ready = False
            self.status.set('Could not save the diagnostic log; test stopped.')
        try:
            while True:
                message_details = self.input_events.get_nowait()
                self.log('input_message', **message_details)
                self.observe_input_message(message_details)
        except queue.Empty: pass
        except OSError:
            self.ready = False
            self.status.set('Could not save the diagnostic log; test stopped.')
        if self.phase in ('recording', 'waiting_text'):
            length = user32.GetWindowTextLengthW(self.hwnd)
            if length != self.last_length:
                self.last_length = length
                try: self.log('input_text_changed', character_count=length)
                except OSError: self.status.set('Could not save the diagnostic log.')
                if length > 0 and self.phase == 'recording':
                    self.text_before_stop = True
                    self.status.set('Text appeared before stop. Press the shortcut to stop dictation.')
                elif length == 0 and self.phase == 'waiting_text' and self.text_seen:
                    self.finish_button.configure(state='disabled')
                    self.status.set('Text was removed. Press the shortcut to retry, or Reset.')
        self.window.after(50, self.poll)

    def observe_input_message(self, details):
        if details.get('message') != 'edit_change' or details.get('character_count', 0) <= 0:
            return
        event_phase = details.get('phase_at_event')
        if event_phase == 'recording':
            self.text_before_stop = True
        elif (event_phase in ('stopping', 'waiting_text') and self.stop_started_ns is not None
              and details.get('monotonic_ns', 0) >= self.stop_started_ns
              and details.get('trial_at_event') == self.trial):
            self.text_seen = True
            if self.phase == 'waiting_text':
                self.finish_button.configure(state='normal')
                self.status.set('Text arrived after stop. Check it, then finish or retry.')

    def on_shortcut(self):
        try: self.log('shortcut_received', sensor_ready=self.ready, text_received=self.text_seen)
        except OSError:
            self.status.set('Could not save the diagnostic log; shortcut not processed.')
            return
        if not self.ready:
            self.status.set('Sensor is not ready. Wait or close this test.')
            return
        if self.phase in ('starting', 'stopping'):
            return
        if self.phase == 'waiting_text':
            if not self.text_seen:
                try: self.log('retry_blocked_waiting_for_first_text')
                except OSError: pass
                self.status.set('Still waiting for text. Wait, or click Reset to abandon this trial.')
                return
            # An intentional new shortcut after text arrived ends the prior observation
            # and starts a fresh trial; it does not assert that dictation was complete.
            try: self.log('retry_requested', text_received=True, finalized_observed=self.observed)
            except OSError:
                self.status.set('Could not save the previous trial; retry stopped.')
                return
            self.finish_trial(allow_empty=True)
            if self.phase != 'ready': return
        if self.phase == 'recording':
            self.phase = 'stopping'; action = 'stop'
        else:
            self.trial += 1; self.observed = False; self.last_length = 0; self.text_seen = False
            self.text_before_stop = False; self.stop_started_ns = None
            self.finish_button.configure(state='disabled')
            user32.SetWindowTextW(self.hwnd, '')
            self.result.set('No finalized event observed yet.')
            try:
                self.log('trial_started')
            except OSError:
                self.status.set('Could not save the diagnostic log; test stopped.')
                return
            self.phase = 'starting'; action = 'start'
        self.window.deiconify(); self.window.lift(); self.window.focus_force()
        user32.SetFocus(self.hwnd)
        self.wait_release(action)

    def wait_release(self, action, attempts=0):
        if self.closed or self.phase != ('starting' if action == 'start' else 'stopping'): return
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x11, 0x10, 0x4A, 0x49)):
            if attempts < 100: self.window.after(30, lambda: self.wait_release(action, attempts + 1))
            else: self.phase = 'ready'; self.status.set('Release the keys and retry.')
            return
        self.window.update_idletasks(); user32.SetFocus(self.hwnd)
        if user32.GetFocus() != self.hwnd or user32.GetForegroundWindow() != user32.GetAncestor(self.hwnd, 2):
            try: self.log('focus_failed', step=action)
            except OSError: pass
            self.phase = 'ready'; self.status.set('Could not focus the test field. Retry.')
            return
        try:
            self.log('dictation_shortcut_attempt', step=action)
            if action == 'stop': self.stop_started_ns = time.monotonic_ns()
            send_dictation_shortcut()
            self.log('dictation_shortcut_sent', step=action)
        except (OSError, RuntimeError):
            try: self.log('dictation_shortcut_error', step=action)
            except OSError: pass
            self.phase = 'ready'; self.status.set('Could not start or stop dictation. Retry.')
            return
        self.phase = 'recording' if action == 'start' else 'waiting_text'
        self.status.set('Speak, then press Ctrl + Shift + J again.' if action == 'start'
                        else 'Waiting for text. This can take several seconds; please keep this window open.')
        if action == 'stop' and self.text_seen:
            self.finish_button.configure(state='normal')
            self.status.set('Text is in the box. Wait for the full text, then click Finish trial.')
        elif action == 'stop' and self.text_before_stop:
            self.status.set('Earlier text appeared before stop. Waiting for new text; Reset to retry if needed.')

    def finish_trial(self, allow_empty=False):
        if self.phase != 'waiting_text' or not self.text_seen:
            return
        current_length = user32.GetWindowTextLengthW(self.hwnd)
        if current_length == 0 and not allow_empty:
            self.finish_button.configure(state='disabled')
            self.status.set('Text was removed. Press the shortcut to retry, or Reset.')
            return
        try: self.log('trial_finished', text_received=True, finalized_observed=self.observed,
                      final_character_count=current_length, ended_for_retry=allow_empty)
        except OSError:
            self.status.set('Could not save the trial result.')
            return
        self.phase = 'ready'
        self.finish_button.configure(state='disabled')
        self.status.set('Trial saved. Press the shortcut to start another, or close the test.')
        if not self.observed:
            self.result.set('No finalized event observed by the time the trial was finished.')

    def reset_trial(self):
        if self.phase in ('starting', 'recording', 'stopping'):
            self.status.set('Stop dictation before resetting the trial.')
            return
        try: self.log('trial_reset', text_received=self.text_seen, finalized_observed=self.observed)
        except OSError:
            self.status.set('Could not save the reset. Try again.')
            return
        self.phase = 'ready'
        self.finish_button.configure(state='disabled')
        self.status.set('Trial reset. Press Ctrl + Shift + J to try again.')

    def close(self):
        if self.closed: return
        self.closed = True
        if self.phase in ('starting', 'recording', 'stopping'):
            self.app.status.set('If ChatGPT is still dictating, stop it with Ctrl+I.')
        try:
            self.log('test_closed', text_received=self.text_seen, finalized_observed=self.observed)
            if self.process.poll() is None: self.process.stdin.close()
        except OSError: pass
        if self.subclass_registered:
            comctl32.RemoveWindowSubclass(self.hwnd, self.subclass_callback, 1)
            self.subclass_registered = False
        if self.parent_subclass_registered:
            comctl32.RemoveWindowSubclass(self.host_hwnd, self.parent_callback, 2)
            self.parent_subclass_registered = False
        self.window.destroy()
