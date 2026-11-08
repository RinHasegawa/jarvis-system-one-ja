"""Compact JARVIS surface using the existing shortcut and action backend."""
import gc
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk

from jarvis_shortcut import ShortcutApp

BG = '#10151f'
PANEL = '#1a2330'
TEXT = '#edf4f7'
MUTED = '#a6b6c4'
ACCENT = '#a7f3d0'


class PopupApp(ShortcutApp):
    def __init__(self, root):
        super().__init__(root)
        # Keep the already-initialized backend; replace only its visual surface.
        for child in root.winfo_children():
            child.destroy()
        root.title('JARVIS')
        root.configure(bg=BG)
        root.resizable(False, False)
        root.protocol('WM_DELETE_WINDOW', root.withdraw)
        width, height = 400, 390
        x = max(0, root.winfo_screenwidth() - width - 35)
        y = max(0, (root.winfo_screenheight() - height) // 3)
        root.geometry(f'{width}x{height}+{x}+{y}')
        self.settings_window = None
        self.native_probe = None
        self.run_when_ready = False
        self.sensor_status = tk.StringVar(value='Composition sensor: starting…')
        self.sensor_process = None
        self.sensor_ready = False
        self.sensor_pattern_available = None
        self.sensor_observed = False
        self.sensor_trial = 0
        self.sensor_log_path = (Path(__file__).resolve().parent / 'diagnostic_results' /
            ('composition_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl'))
        self.result.set('')

        outer = tk.Frame(root, bg=BG, padx=18, pady=12)
        outer.pack(fill='both', expand=True)
        header = tk.Frame(outer, bg=BG)
        header.pack(fill='x')
        tk.Label(header, text='●', bg=BG, fg=ACCENT, font=('Segoe UI', 12)).pack(side='left', padx=(0, 8))
        tk.Label(header, text='JARVIS', bg=BG, fg=TEXT, font=('Segoe UI', 16, 'bold')).pack(side='left')
        tk.Button(header, text='Settings', command=self.show_settings, bg=BG, fg=MUTED,
                  activebackground=PANEL, activeforeground=TEXT, relief='flat', cursor='hand2',
                  font=('Segoe UI', 9)).pack(side='right')

        tk.Label(outer, text='SPEAK YOUR COMMAND', bg=BG, fg=ACCENT,
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', pady=(12, 7))
        self.box = tk.Text(outer, height=2, wrap='word', font=('Segoe UI', 12),
                           bg=PANEL, fg=TEXT, insertbackground=TEXT, relief='flat',
                           highlightthickness=1, highlightbackground='#334353',
                           highlightcolor=ACCENT, padx=10, pady=9)
        self.box.pack(fill='x')
        self.box.bind('<<Modified>>', self.edited)

        tk.Label(outer, text='Ctrl + Shift + J  ·  Start / stop    |    Esc  ·  Cancel', bg=BG, fg=MUTED,
                 font=('Segoe UI', 9)).pack(anchor='w', pady=(7, 10))
        tk.Frame(outer, height=1, bg='#303b49').pack(fill='x')
        tk.Label(outer, text='STATUS', bg=BG, fg=ACCENT, font=('Segoe UI', 8, 'bold')).pack(anchor='w', pady=(10, 4))
        tk.Label(outer, textvariable=self.status, bg=BG, fg=TEXT, justify='left',
                 anchor='nw', wraplength=355, font=('Segoe UI', 9), height=2).pack(fill='x')
        tk.Label(outer, textvariable=self.result, bg=BG, fg=TEXT, justify='left',
                 anchor='w', wraplength=355, font=('Segoe UI', 10, 'bold'), height=2).pack(fill='x', pady=(4, 4))
        self.sensor_label = tk.Label(outer, textvariable=self.sensor_status, bg=BG, fg=MUTED, justify='left',
                 anchor='w', wraplength=355, font=('Segoe UI', 8), height=2)
        self.sensor_label.pack(fill='x')

        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill='x', side='bottom', pady=(5, 0))
        self.execute_button = tk.Button(actions, text='Run command  →', state='disabled', command=self.run_command,
                 bg=ACCENT, fg='#10251f', activebackground='#c0f9dd', activeforeground='#10251f',
                 disabledforeground='#687f78', relief='flat', padx=11, pady=7,
                 font=('Segoe UI', 9, 'bold'), cursor='hand2')
        self.execute_button.pack(fill='x')
        self.submit_button = tk.Button(actions, text='Ask Jev', command=self.submit,
                 bg=PANEL, fg=TEXT, activebackground='#344454', activeforeground=TEXT,
                 disabledforeground=MUTED, relief='flat', padx=10, pady=7, font=('Segoe UI', 9), cursor='hand2')
        self.box.focus_set()
        if os.environ.get('JARVIS_SENSOR_DISABLED') != '1':
            root.after(200, self.start_sensor)
        # Destroyed Tk widgets must be collected on the Tk thread, not a worker.
        gc.collect()

    def sensor_log(self, event, **fields):
        self.sensor_log_path.parent.mkdir(exist_ok=True)
        with self.sensor_log_path.open('a', encoding='utf-8') as log:
            log.write(json.dumps({'time': datetime.now().astimezone().isoformat(), 'event': event,
                                  'trial': self.sensor_trial, **fields}, ensure_ascii=False) + '\n')
            log.flush()

    def start_sensor(self):
        if self.stopping.is_set(): return
        try:
            self.root.update_idletasks()
            helper = Path(__file__).resolve().parent / 'composition_sensor.py'
            self.sensor_process = subprocess.Popen(
                [sys.executable, str(helper), str(self.box.winfo_id())],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            threading.Thread(target=self.read_sensor, args=(self.sensor_process, self.events), daemon=True).start()
            self.sensor_log('sensor_started', scope='jarvis_input_only', audio_saved=False, text_payload_saved=False)
        except (OSError, ValueError) as exc:
            self.handle_sensor_event('sensor_error', {'detail': type(exc).__name__})

    @staticmethod
    def read_sensor(process, events):
        try:
            for line in process.stdout:
                try:
                    item = json.loads(line)
                    event = item.pop('event', '')
                    if event in ('sensor_ready', 'sensor_error', 'composition_finalized'):
                        events.put((event, item))
                except (ValueError, TypeError):
                    events.put(('sensor_error', {'detail': 'Invalid sensor response'}))
        finally:
            events.put(('sensor_exited', {}))

    def handle_sensor_event(self, event, detail):
        try:
            self.sensor_log(event, **detail)
        except OSError:
            self.sensor_status.set('Composition sensor: log could not be saved.')
            self.sensor_ready = False
            return
        if event == 'sensor_ready':
            self.sensor_ready = True
            self.sensor_pattern_available = detail.get('text_edit_pattern_available')
            if self.sensor_pattern_available:
                self.sensor_status.set('Composition sensor: listening. No finalized event observed yet.')
            else:
                self.sensor_status.set('Composition sensor: input does not expose TextEdit. Result may be inconclusive.')
        elif event == 'composition_finalized':
            self.sensor_observed = True
            self.sensor_status.set('Composition sensor: finalized event observed.')
        elif event == 'sensor_error':
            self.sensor_ready = False
            self.sensor_status.set('Composition sensor: unavailable. See local diagnostic log.')
        elif event == 'sensor_exited' and not self.stopping.is_set():
            self.sensor_ready = False
            self.sensor_status.set('Composition sensor: stopped. See local diagnostic log.')

    def on_shortcut(self):
        if self.native_probe is not None and not self.native_probe.closed:
            self.native_probe.on_shortcut()
            return
        before = self.phase
        if before not in ('recording', 'starting', 'stopping', 'waiting_text') and not self.pending:
            self.sensor_trial += 1
            self.sensor_observed = False
            try: self.sensor_log('trial_started', sensor_ready=self.sensor_ready,
                                 text_edit_pattern_available=self.sensor_pattern_available)
            except OSError: self.sensor_status.set('Composition sensor: log could not be saved.')
            if self.sensor_ready and self.sensor_pattern_available:
                self.sensor_status.set('Composition sensor: listening. No finalized event observed yet.')
        elif before == 'recording':
            try: self.sensor_log('stop_shortcut_pressed')
            except OSError: self.sensor_status.set('Composition sensor: log could not be saved.')
        super().on_shortcut()

    def close(self):
        if self.native_probe is not None and not self.native_probe.closed:
            self.native_probe.close()
        if self.sensor_process and self.sensor_process.poll() is None:
            try: self.sensor_process.stdin.close()
            except OSError: pass
        super().close()

    def process_waiting_text(self):
        # There is no confirmed end-of-dictation signal: never submit on a timer.
        if self.phase != 'waiting_text':
            return
        text = self.box.get('1.0', 'end-1c').strip()
        if text:
            self.execute_button.configure(state='normal')
            self.status.set('When the full text appears, press Run command.')
        else:
            self.execute_button.configure(state='disabled')
            self.status.set('Waiting for dictation text. Keep this window open.')

    def run_command(self):
        if self.phase == 'waiting_text':
            text = self.box.get('1.0', 'end-1c').strip()
            if not text:
                return
            try:
                self.log('dictation_text_confirmed', text=text)
            except OSError:
                self.status.set('Cannot save the result. Nothing was sent.')
                return
            self.phase = 'review'
            self.run_when_ready = True
            self.submit()
        elif self.proposal:
            self.execute()

    def receive(self, rev, target, text, outcome):
        should_run = self.run_when_ready
        self.run_when_ready = False
        super().receive(rev, target, text, outcome)
        if should_run and self.proposal:
            self.execute()

    def cancel(self):
        self.run_when_ready = False
        super().cancel()

    def edited(self, event=None):
        if self.box.edit_modified():
            self.box.edit_modified(False)
            if getattr(self, 'phase', 'ready') in ('starting', 'recording', 'stopping', 'waiting_text'):
                try: self.sensor_log('input_text_changed', character_count=len(self.box.get('1.0', 'end-1c')))
                except OSError: self.sensor_status.set('Composition sensor: log could not be saved.')
            self.invalidate()
            if getattr(self, 'phase', 'ready') in ('starting', 'recording', 'stopping', 'waiting_text'):
                self.result.set('')
            else:
                self.result.set('Text changed. Submit it again before executing.')

    def show_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title('JARVIS settings')
        win.configure(bg=BG)
        win.geometry('440x390')
        win.resizable(False, False)
        body = tk.Frame(win, bg=BG, padx=22, pady=20)
        body.pack(fill='both', expand=True)
        tk.Label(body, text='Your Jev key', bg=BG, fg=TEXT, font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        tk.Label(body, text='Saved locally using Windows account encryption.', bg=BG, fg=MUTED,
                 font=('Segoe UI', 9), wraplength=390, justify='left').pack(anchor='w', pady=(4, 14))
        tk.Entry(body, textvariable=self.key, show='•', bg=PANEL, fg=TEXT, insertbackground=TEXT,
                 relief='flat', font=('Segoe UI', 11)).pack(fill='x', ipady=6)
        row = tk.Frame(body, bg=BG); row.pack(fill='x', pady=(14, 0))
        tk.Button(row, text='Save key securely', command=self.save_key, bg=ACCENT, fg='#10251f',
                  relief='flat', padx=10, pady=6, font=('Segoe UI', 9, 'bold')).pack(side='left')
        tk.Button(row, text='Forget saved key', command=self.forget_key, bg=PANEL, fg=TEXT,
                  relief='flat', padx=10, pady=6, font=('Segoe UI', 9)).pack(side='left', padx=8)
        tk.Button(body, text='Retry current command', command=self.submit, bg=PANEL, fg=TEXT,
                  relief='flat', padx=10, pady=6, font=('Segoe UI', 9)).pack(anchor='w', pady=(10, 0))
        tk.Button(body, text='Open composition event test', command=self.show_native_probe, bg=PANEL, fg=TEXT,
                  relief='flat', padx=10, pady=6, font=('Segoe UI', 9)).pack(anchor='w', pady=(6, 0))
        tk.Label(body, textvariable=self.status, bg=BG, fg=MUTED, wraplength=390,
                 justify='left', font=('Segoe UI', 9)).pack(anchor='w', pady=(12, 0))
        tk.Button(body, text='Quit JARVIS', command=self.close, bg=BG, fg=MUTED,
                  activebackground=PANEL, activeforeground=TEXT, relief='flat',
                  font=('Segoe UI', 9)).pack(anchor='e', side='bottom')

    def show_native_probe(self):
        if self.native_probe is not None and not self.native_probe.closed:
            self.native_probe.window.lift()
            return
        if self.phase in ('starting', 'recording', 'stopping') or self.pending:
            self.status.set('Cancel the current command before starting the test.')
            return
        if self.phase == 'waiting_text':
            self.cancel()
        try:
            from composition_native_probe import NativeCompositionProbe
            self.native_probe = NativeCompositionProbe(self)
            if self.settings_window and self.settings_window.winfo_exists(): self.settings_window.withdraw()
        except OSError:
            self.status.set('Could not start the composition test.')


if __name__ == '__main__':
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\JARVISVoicePopup')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        sys.exit(0)
    try:
        window = tk.Tk()
        if '--background' in sys.argv:
            window.withdraw()
        app = PopupApp(window)
        if '--composition-test' in sys.argv:
            window.after(300, app.show_native_probe)
        window.mainloop()
    finally:
        kernel.CloseHandle(mutex)
