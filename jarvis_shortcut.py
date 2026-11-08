"""Shortcut-driven dictation popup; retains the existing confirmed action gate."""
import ctypes
from ctypes import wintypes
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from jarvis_command import App
from jarvis_key_store import load_key, save_key, remove_key

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

ULONG_PTR = wintypes.WPARAM
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]
class INPUT_UNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', wintypes.DWORD), ('data', INPUT_UNION)]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

def send_dictation_shortcut():
    """Send Ctrl+I after the physical shortcut keys are released."""
    for vk in (0x11, 0x49):
        if user32.GetAsyncKeyState(vk) & 0x8000:
            raise RuntimeError('Release Ctrl and I before continuing.')
    def key(vk, up=False):
        item = INPUT(); item.type = 1
        item.ki = KEYBDINPUT(vk, 0, 2 if up else 0, 0, 0)
        return item
    events = (INPUT * 4)(key(0x11), key(0x49), key(0x49, True), key(0x11, True))
    if user32.SendInput(4, events, ctypes.sizeof(INPUT)) != 4:
        # A partial send may leave a generated modifier held down.
        releases = (INPUT * 2)(key(0x49, True), key(0x11, True))
        user32.SendInput(2, releases, ctypes.sizeof(INPUT))
        raise RuntimeError('Windows did not accept the dictation shortcut.')

class ShortcutApp(App):
    def __init__(self, root):
        super().__init__(root)
        root.title('JARVIS - Shortcut Dictation')
        root.geometry('680x610')
        self.phase = 'ready'
        self.wait_started = 0
        self.last_text = ''
        self.changed_at = 0
        self.events = queue.Queue()
        self.stopping = threading.Event()
        self.status.set('Ctrl+Shift+J: start/stop. ChatGPT dictation must use Ctrl+I. Review actions before execution.')
        for child in root.winfo_children():
            for widget in child.winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget('text').startswith('TypeSafe API key'):
                    widget.configure(text='TypeSafe API key (masked; save securely below if desired)')
        controls = ttk.Frame(root, padding=(20, 0, 20, 8)); controls.pack(fill='x')
        ttk.Button(controls, text='Hide until shortcut', command=root.withdraw).pack(side='left')
        ttk.Button(controls, text='Save key securely', command=self.save_key).pack(side='left', padx=6)
        ttk.Button(controls, text='Forget saved key', command=self.forget_key).pack(side='left')
        try:
            stored = load_key()
            if stored: self.key.set(stored)
        except (OSError, ValueError, UnicodeError):
            self.status.set('Could not unlock the saved key. Enter it again and save it securely.')
        root.bind('<Escape>', lambda e: self.cancel_shortcut())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.hotkey_thread = threading.Thread(target=self.hotkey_loop, args=(self.events, self.stopping), daemon=True)
        self.hotkey_thread.start()
        self._poll_id = root.after(50, self.poll)

    def save_key(self):
        try:
            save_key(self.key.get())
            self.status.set('Key saved with Windows user encryption on this PC.')
        except (OSError, ValueError):
            self.status.set('Could not save the key. Check the field and try again.')

    def forget_key(self):
        try:
            remove_key()
            self.key.set('')
            self.status.set('Saved key removed and current key cleared.')
        except OSError:
            self.status.set('Could not remove the saved key.')

    @staticmethod
    def hotkey_loop(events, stopping):
        # Thread-specific global hotkey: Ctrl+Shift+J, with no key-repeat.
        reported_error = False
        while not user32.RegisterHotKey(None, 1, 0x0002 | 0x0004 | 0x4000, 0x4A):
            error = ctypes.get_last_error()
            message = ('Windows denied shortcut registration. Try launching normally on your desktop.' if error == 5
                       else 'Shortcut in use. Close the older JARVIS window; this app will retry automatically.')
            if not reported_error:
                events.put(('error', message))
                reported_error = True
            if stopping.wait(2): return
        events.put(('registered', reported_error))
        msg = wintypes.MSG()
        try:
            while not stopping.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312 and msg.wParam == 1:
                        events.put(('shortcut', None))
                time.sleep(.025)
        finally:
            user32.UnregisterHotKey(None, 1)

    def poll(self):
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        try:
            while True:
                event, detail = self.events.get_nowait()
                if event == 'shortcut': self.on_shortcut()
                elif event == 'registered' and detail:
                    self.status.set('Shortcut is ready. Press Ctrl+Shift+J to start dictation.')
                elif event == 'error':
                    self.status.set(detail)
                    self.root.deiconify()
                    self.root.lift()
                elif event in ('sensor_ready', 'sensor_error', 'composition_finalized', 'sensor_exited'):
                    handler = getattr(self, 'handle_sensor_event', None)
                    if handler is not None: handler(event, detail)
                elif event == 'event_test_reply':
                    handler = getattr(self, 'handle_event_test_reply', None)
                    if handler is not None: handler(detail)
        except queue.Empty:
            pass
        self.process_waiting_text()
        if not self.stopping.is_set(): self._poll_id = self.root.after(50, self.poll)

    def process_waiting_text(self):
        if self.phase == 'waiting_text':
            text = self.box.get('1.0', 'end-1c').strip()
            now = time.monotonic()
            if text != self.last_text:
                self.last_text, self.changed_at = text, now
            # Heuristic, not a ChatGPT completion event. Later edits invalidate proposals.
            if text and self.changed_at and now - self.changed_at >= 1.5:
                self.phase = 'review'
                try:
                    self.log('dictation_text_received', text=text)
                except OSError:
                    self.status.set('Text received, but saving the local log failed. Nothing was sent.')
                else:
                    self.submit()
            elif now - self.wait_started > 30:
                self.phase = 'review'
                self.status.set('No text arrived yet. Check ChatGPT dictation, then retry or enter text.')

    def on_shortcut(self):
        if self.phase in ('starting', 'stopping', 'waiting_text'):
            self.status.set('Please wait for the current dictation step.')
            return
        if self.pending:
            self.status.set('A Jev request is in progress. Cancel it before starting another command.')
            return
        if self.phase == 'recording':
            self.phase = 'stopping'
            self.root.deiconify(); self.root.lift(); self.root.focus_force(); self.box.focus_force()
            self.status.set('Stopping dictation...')
            self.wait_release_and_send('stop')
            return
        self.cancel()
        self.box.delete('1.0', 'end')
        self.phase = 'starting'
        self.root.deiconify(); self.root.lift(); self.root.focus_force(); self.box.focus_force()
        self.status.set('Opening command box and starting ChatGPT dictation...')
        self.wait_release_and_send('start')

    def wait_release_and_send(self, action, attempts=0):
        if self.stopping.is_set(): return
        if self.phase != ('starting' if action == 'start' else 'stopping'): return
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x11, 0x10, 0x4A, 0x49)):
            if attempts >= 100:
                self.phase = 'ready'; self.status.set('Release the shortcut keys and try again.')
            else: self.root.after(30, lambda: self.wait_release_and_send(action, attempts + 1))
            return
        self.root.update_idletasks()
        window = user32.GetAncestor(self.root.winfo_id(), 2)
        if self.root.focus_get() != self.box or user32.GetForegroundWindow() != window:
            self.phase = 'ready'
            self.status.set('Command box could not receive focus. Stop dictation with Ctrl+I if needed, then retry.')
            return
        try:
            self.log('dictation_shortcut_attempt', step=action)
            send_dictation_shortcut()
            self.log('dictation_shortcut_sent', step=action)
        except (OSError, RuntimeError):
            self.phase = 'ready'; self.status.set('Could not send or log the dictation shortcut. Try again.')
            return
        if action == 'start':
            self.phase = 'recording'
            self.status.set('Dictation shortcut sent. Speak, then press Ctrl+Shift+J again to stop.')
        else:
            self.phase = 'waiting_text'; self.wait_started = time.monotonic()
            self.last_text = ''; self.changed_at = 0
            self.status.set('Stop shortcut sent. Waiting for text; keep this window open.')

    def cancel_shortcut(self):
        self.cancel()

    def cancel(self):
        # Cancellation never guesses whether ChatGPT is still recording.
        previous = getattr(self, 'phase', 'ready')
        super().cancel()
        self.phase = 'ready'
        if previous in ('recording', 'starting', 'stopping', 'waiting_text'):
            self.status.set('JARVIS cancelled. Stop ChatGPT dictation with Ctrl+I if still active.')

    def close(self):
        self.stopping.set()
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        self.hotkey_thread.join(timeout=.3)
        self.root.destroy()

if __name__ == '__main__':
    window = tk.Tk()
    ShortcutApp(window)
    window.mainloop()
