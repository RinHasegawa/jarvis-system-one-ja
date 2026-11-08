"""Dictation-to-Jev prototype: explicit submission and confirmed app launches."""
import json
import math
import os
import re
import subprocess
import threading
import time
import tkinter as tk
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent
TARGETS = {'CHROME': Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),
           'NOTEPAD': Path(r'C:\Windows\System32\notepad.exe')}
QUESTIONS = {
    'action': {'type': 'choice', 'instructions': 'Classify the requested action.',
               'criteria': {'OPEN_APP': 'Explicit request to launch an application.',
                            'UNKNOWN': 'No clear supported action, a question, or a negated request.'}},
    'target': {'type': 'choice', 'instructions': 'Choose the explicitly named application.',
               'criteria': {'CHROME': 'Google Chrome application', 'NOTEPAD': 'Windows Notepad application',
                            'NONE': 'No single explicit supported app'}}}


def permitted_phrase(text):
    text = re.sub(r'[.!?,]+', '', text.lower()).strip()
    pattern = r'(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?(google\s+chrome|chrome|notepad)(?:\s+please)?'
    match = re.fullmatch(pattern, text)
    if not match:
        return None
    return 'NOTEPAD' if match.group(1) == 'notepad' else 'CHROME'


def validate(response, target):
    answers = response['answers']
    for name in QUESTIONS:
        answer = answers[name]
        choices = QUESTIONS[name]['criteria']
        probs = answer['probabilities']
        if answer.get('type') != 'choice' or answer.get('choice') not in choices or set(probs) != set(choices):
            raise ValueError('Invalid Jev response')
        values = list(probs.values())
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values) or abs(sum(values)-1) > .02:
            raise ValueError('Invalid Jev probabilities')
    return answers['action']['choice'] == 'OPEN_APP' and answers['target']['choice'] == target


def ask_jev(text, key):
    data = json.dumps({'model': 'jev-1.13.0', 'state': text, 'questions': QUESTIONS}, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=data,
          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode('utf-8'))


class App:
    def __init__(self, root):
        self.root = root
        root.title('JARVIS - Dictation Commands')
        root.geometry('730x600')
        self.revision = 0
        self.pending = False
        self.proposal = None
        self.session = None
        self.key = tk.StringVar(value=os.environ.get('TYPESAFE_API_KEY', ''))
        self.status = tk.StringVar(value='Focus the box and use Ctrl+I to dictate. Submit when finished.')
        self.result = tk.StringVar(value='No action proposed yet.')
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='JARVIS: Dictation Commands', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='1. Dictate and review  →  2. Ask Jev  →  3. Confirm action', wraplength=670).pack(anchor='w', pady=8)
        ttk.Label(panel, text='TypeSafe API key (masked; kept only for this session)').pack(anchor='w')
        ttk.Entry(panel, textvariable=self.key, show='*').pack(fill='x')
        ttk.Label(panel, text='Your command').pack(anchor='w', pady=(12, 0))
        self.box = tk.Text(panel, height=5, wrap='word', font=('Segoe UI', 12))
        self.box.pack(fill='x')
        self.box.bind('<<Modified>>', self.edited)
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=10)
        ttk.Button(row, text='Focus input', command=self.box.focus_set).pack(side='left')
        self.submit_button = ttk.Button(row, text='Ask Jev', command=self.submit)
        self.submit_button.pack(side='left', padx=8)
        ttk.Button(row, text='Cancel', command=self.cancel).pack(side='left')
        self.execute_button = ttk.Button(row, text='Execute proposed action', command=self.execute, state='disabled')
        self.execute_button.pack(side='left', padx=8)
        ttk.Label(panel, textvariable=self.status, wraplength=670).pack(anchor='w', pady=8)
        ttk.Label(panel, textvariable=self.result, font=('Segoe UI', 12, 'bold'), wraplength=670).pack(anchor='w', pady=8)
        ttk.Label(panel, text='Text and results are saved locally and sent to Jev when you press Ask Jev. Audio is not saved by JARVIS.', wraplength=670).pack(anchor='w', pady=10)
        self.box.focus_set()

    def log(self, event, **data):
        folder = ROOT / 'diagnostic_results'
        folder.mkdir(exist_ok=True)
        if self.session is None:
            self.session = folder / ('command_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
        with self.session.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'time': datetime.now().astimezone().isoformat(), 'event': event, **data}, ensure_ascii=False) + '\n')
            f.flush()

    def invalidate(self):
        self.revision += 1
        self.proposal = None
        self.execute_button.configure(state='disabled')

    def edited(self, event=None):
        if self.box.edit_modified():
            self.box.edit_modified(False)
            self.invalidate()
            self.result.set('Text changed. Submit it again before executing.')

    def cancel(self):
        self.invalidate()
        self.status.set('Cancelled. Any pending response will be ignored.')
        self.result.set('No action proposed.')
        try:
            self.log('cancelled')
        except OSError:
            self.status.set('Cancelled, but the local log could not be saved.')

    def submit(self):
        if self.pending:
            self.status.set('A request is already in progress. Please wait.')
            return
        self.invalidate()
        text = self.box.get('1.0', 'end-1c').strip()
        target = permitted_phrase(text)
        if not target:
            self.status.set('Use one clear command: Open Google Chrome or Open Notepad.')
            try:
                self.log('rejected_locally', text=text)
            except OSError:
                self.status.set('Could not save the local result log.')
            return
        key = self.key.get().strip()
        if not key:
            self.status.set('Enter your TypeSafe API key above. Do not paste it into chat.')
            return
        try:
            self.log('submitted', text=text, target=target, model='jev-1.13.0')
        except OSError:
            self.status.set('Cannot save the result log. No request was sent.')
            return
        rev = self.revision
        self.pending = True
        self.submit_button.configure(state='disabled')
        self.status.set('Asking Jev... You can cancel while waiting.')
        def work():
            start = time.perf_counter()
            try:
                response = ask_jev(text, key)
                result = validate(response, target)
                outcome = ('ok', result, round(time.perf_counter()-start, 3))
            except Exception as exc:
                outcome = ('error', type(exc).__name__, round(time.perf_counter()-start, 3))
            self.root.after(0, lambda: self.receive(rev, target, text, outcome))
        threading.Thread(target=work, daemon=True).start()

    def receive(self, rev, target, text, outcome):
        self.pending = False
        self.submit_button.configure(state='normal')
        if rev != self.revision or self.box.get('1.0', 'end-1c').strip() != text:
            self.status.set('An outdated response was ignored. Submit the current text again.')
            try: self.log('stale_response_ignored')
            except OSError: self.status.set('Outdated response ignored, but logging failed.')
            return
        try:
            self.log('decision', target=target, outcome=outcome[0], accepted=outcome[1] if outcome[0] == 'ok' else False, seconds=outcome[2])
        except OSError:
            self.status.set('Cannot save the decision; action is blocked.')
            return
        if outcome[0] == 'error':
            self.status.set(f'Jev request failed ({outcome[1]}). Check your key and internet connection.')
        elif not outcome[1]:
            self.status.set('Jev did not agree on the action and app. Nothing will open.')
        else:
            self.proposal = (rev, target, text)
            self.result.set(f'Proposed: open {target}.')
            self.status.set(f'Jev responded in {outcome[2]} seconds. Confirm by pressing Execute.')
            self.execute_button.configure(state='normal')

    def execute(self):
        proposal = self.proposal
        self.invalidate()
        if not proposal or proposal[0] != self.revision - 1 or self.box.get('1.0', 'end-1c').strip() != proposal[2]:
            self.status.set('Proposal expired. Submit the command again.')
            return
        path = TARGETS[proposal[1]]
        try:
            if not path.is_file():
                raise FileNotFoundError('The allowed application is not installed at the expected path.')
            self.log('launch_attempt', target=proposal[1])
            subprocess.Popen([str(path)], shell=False)
            self.log('launch_requested', target=proposal[1])
            self.status.set('Launch requested. Check that the app window appeared.')
        except Exception as exc:
            try: self.log('launch_error', error=type(exc).__name__)
            except OSError: pass
            self.status.set(f'Could not launch the app: {type(exc).__name__}')


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
