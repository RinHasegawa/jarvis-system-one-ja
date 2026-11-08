"""Measure text delivered to JARVIS; no microphone capture or network calls."""
import json
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent


class DictationProbe:
    def __init__(self, root, results=None):
        self.root = root
        self.results = results or ROOT / 'diagnostic_results'
        self.log = None
        self.started = None
        self.changes = []
        self.path = None
        self.previous = ''
        root.title('JARVIS - Desktop Dictation Probe')
        root.geometry('820x680')
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Test your existing dictation shortcut', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='1. Start trial.  2. Use Ctrl+I to speak and stop.  3. Save trial.', wraplength=760).pack(anchor='w', pady=8)
        ttk.Label(panel, text='Only this input field and your test observations are logged locally. Audio is not captured.\nThis probe makes no network calls and performs no PC actions.', wraplength=760).pack(anchor='w')
        ttk.Label(panel, text='Reference phrase (optional; what you intend to say)').pack(anchor='w', pady=(12, 0))
        self.reference = ttk.Entry(panel)
        self.reference.pack(fill='x')
        self.reference.insert(0, 'Open Google Chrome')
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=12)
        self.start_button = ttk.Button(buttons, text='Start trial', command=self.start)
        self.start_button.pack(side='left')
        ttk.Button(buttons, text='Focus input', command=lambda: self.text.focus_set()).pack(side='left', padx=8)
        self.save_button = ttk.Button(buttons, text='Save trial', command=self.save, state='disabled')
        self.save_button.pack(side='left')
        self.text = tk.Text(panel, height=8, wrap='word', font=('Segoe UI', 12), undo=True)
        self.text.pack(fill='both', expand=True)
        self.text.bind('<<Modified>>', self.changed)
        self.text.bind('<FocusIn>', lambda e: self.event('input_focus_in') if self.log else None)
        self.text.bind('<FocusOut>', lambda e: self.event('input_focus_out') if self.log else None)
        ttk.Label(panel, text='Did words appear BEFORE you pressed the shortcut to stop dictation?').pack(anchor='w', pady=(12, 3))
        self.observation = ttk.Combobox(panel, state='readonly', values=['Not sure', 'Yes - before stopping', 'No - only after stopping'])
        self.observation.current(0)
        self.observation.pack(fill='x')
        self.status = tk.StringVar(value='Ready. Press Start trial before dictating.')
        ttk.Label(panel, textvariable=self.status, wraplength=760).pack(anchor='w', pady=10)
        ttk.Label(panel, text='Timing is relative to Start trial, not actual recording start. Multiple edits or paste events\ndo not by themselves prove streaming. Repeat with short and long utterances.', wraplength=760).pack(anchor='w')
        root.protocol('WM_DELETE_WINDOW', self.close)

    def event(self, kind, **fields):
        if self.log:
            data = {'time': datetime.now().astimezone().isoformat(), 'elapsed_s': round(time.perf_counter()-self.started, 4), 'event': kind, **fields}
            self.log.write(json.dumps(data, ensure_ascii=False) + '\n')
            self.log.flush()

    def start(self):
        if self.log:
            return
        try:
            self.results.mkdir(parents=True, exist_ok=True)
            self.path = self.results / ('dictation_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
            self.log = self.path.open('x', encoding='utf-8', buffering=1)
            self.started = time.perf_counter()
            self.text.delete('1.0', 'end')
            self.text.edit_modified(False)
            self.previous = ''
            self.changes = []
            self.observation.current(0)
            self.event('trial_started', reference=self.reference.get(), audio_saved=False, network_used=False)
            self.start_button.configure(state='disabled')
            self.save_button.configure(state='normal')
            self.reference.configure(state='disabled')
            self.text.focus_set()
            self.status.set(f'Trial active. Use your dictation shortcut. Saving to {self.path.name}')
        except Exception as exc:
            self.failure(exc)

    def changed(self, _=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        value = self.text.get('1.0', 'end-1c')
        if self.log and value != self.previous:
            try:
                elapsed = round(time.perf_counter()-self.started, 4)
                self.event('text_changed', text=value, characters=len(value))
                self.changes.append(elapsed)
                self.previous = value
                self.status.set(f'{len(self.changes)} text changes observed; latest at {elapsed:.2f} s. Log: {self.path.name}')
            except Exception as exc:
                self.failure(exc)

    def save(self, completed=True):
        if not self.log:
            return
        try:
            self.changed()
            self.event('trial_finished' if completed else 'trial_interrupted', text=self.text.get('1.0', 'end-1c'),
                       reference=self.reference.get(), observation=self.observation.get(), text_changes=len(self.changes),
                       first_text_change_s=self.changes[0] if self.changes else None,
                       last_text_change_s=self.changes[-1] if self.changes else None)
            self.log.close()
            self.log = None
            self.start_button.configure(state='normal')
            self.save_button.configure(state='disabled')
            self.reference.configure(state='normal')
            self.status.set(f'Trial saved: {self.path}')
        except Exception as exc:
            self.failure(exc)

    def failure(self, exc):
        if self.log:
            self.log.close()
            self.log = None
        self.start_button.configure(state='normal')
        self.save_button.configure(state='disabled')
        self.reference.configure(state='normal')
        self.status.set(f'Logging failed; stop this trial: {exc}')
        messagebox.showerror('Trial could not be saved', str(exc), parent=self.root)

    def close(self):
        if self.log:
            self.save(completed=False)
        self.root.destroy()


if __name__ == '__main__':
    window = tk.Tk()
    DictationProbe(window)
    window.mainloop()
