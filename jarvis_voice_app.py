"""Small Windows interface for the local Sherpa speech-recognition test."""
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent


class VoiceApp:
    def __init__(self, root):
        self.root = root
        self.root.title('JARVIS - English Voice Test')
        self.root.geometry('720x570')
        self.root.minsize(560, 440)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.devices = []
        self.status = tk.StringVar(value='Choose a microphone, then press Start.')
        self.partial = tk.StringVar(value='Your words will appear here.')
        main = ttk.Frame(root, padding=20)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='JARVIS English Voice Test', font=('Segoe UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(main, text='Speak in English. Recognition runs locally on this PC.').pack(anchor='w', pady=(2, 14))
        ttk.Label(main, text='Microphone').pack(anchor='w')
        row = ttk.Frame(main)
        row.pack(fill='x', pady=(3, 12))
        self.selector = ttk.Combobox(row, state='readonly')
        self.selector.pack(side='left', fill='x', expand=True)
        self.refresh_button = ttk.Button(row, text='Refresh', command=self.refresh)
        self.refresh_button.pack(side='left', padx=(8, 0))
        buttons = ttk.Frame(main)
        buttons.pack(fill='x')
        self.start_button = ttk.Button(buttons, text='Start listening', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(buttons, text='Stop', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        ttk.Label(main, textvariable=self.status, wraplength=650).pack(anchor='w', pady=(12, 8))
        ttk.Label(main, text='Currently hearing', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        ttk.Label(main, textvariable=self.partial, wraplength=650).pack(anchor='w', pady=(0, 10))
        ttk.Label(main, text='Final recognized text', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.output = tk.Text(main, height=8, wrap='word', state='disabled', font=('Segoe UI', 11))
        self.output.pack(fill='both', expand=True, pady=(4, 8))
        ttk.Label(main, text='Text results and errors are saved locally. Audio is not saved.', wraplength=650).pack(anchor='w')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        root.after(100, self.poll)

    def refresh(self):
        try:
            import sounddevice as sd
            all_devices = sd.query_devices()
            hosts = sd.query_hostapis()
            default = sd.default.device[0]
            self.devices = [(i, d['name'], hosts[d['hostapi']]['name']) for i, d in enumerate(all_devices)
                            if d['max_input_channels'] > 0]
            self.selector['values'] = [f'{name} ({host})' for _, name, host in self.devices]
            if self.devices:
                self.selector.current(next((i for i, d in enumerate(self.devices) if d[0] == default), 0))
                self.status.set('Choose a microphone, then press Start.')
            else:
                self.status.set('No microphone found. Connect one and press Refresh.')
        except Exception as exc:
            self.status.set(f'Could not list microphones: {exc}')

    def start(self):
        index = self.selector.current()
        if index < 0:
            self.status.set('Choose a microphone first.')
            return
        self.stop_event.clear()
        self.start_button.configure(state='disabled')
        self.refresh_button.configure(state='disabled')
        self.selector.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('Loading the local speech model...')
        self.partial.set('')
        self.worker = threading.Thread(target=self.run, args=(self.devices[index][0],), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.status.set('Stopping...')
        self.stop_button.configure(state='disabled')

    def close(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.status.set('Stopping before closing...')
            self.root.after(100, self.close)
        else:
            self.root.destroy()

    def poll(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'status':
                self.status.set(value)
            elif kind == 'partial':
                self.partial.set(value)
            elif kind == 'final':
                self.output.configure(state='normal')
                self.output.insert('end', value + '\n')
                self.output.see('end')
                self.output.configure(state='disabled')
            elif kind == 'done':
                self.start_button.configure(state='normal')
                self.refresh_button.configure(state='normal')
                self.selector.configure(state='readonly')
                self.stop_button.configure(state='disabled')
        self.root.after(100, self.poll)

    def run(self, device):
        try:
            import numpy as np
            import sounddevice as sd
            from voice_test import resample_audio
            from voice_sherpa import create_recognizer
            folder = ROOT / 'diagnostic_results'
            folder.mkdir(exist_ok=True)
            path = folder / ('sherpa_gui_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.log')
            with path.open('x', encoding='utf-8', buffering=1) as log:
                def record(message):
                    log.write(message + '\n')
                    log.flush()
                try:
                    record('Loading local Sherpa model.')
                    recognizer = create_recognizer()
                    stream = recognizer.create_stream()
                    info = sd.query_devices(device, 'input')
                    rate = int(info['default_samplerate'])
                    record(f'Microphone: {info["name"]}; {rate} Hz')
                    if self.stop_event.is_set():
                        record('Stopped before listening.')
                        self.events.put(('status', 'Stopped.'))
                        return
                    blocks = queue.Queue(maxsize=30)
                    errors = queue.Queue()
                    def callback(indata, frames, timing, status):
                        if status:
                            errors.put(str(status))
                        try:
                            blocks.put_nowait(indata[:, 0].copy())
                        except queue.Full:
                            errors.put('Audio was lost because processing could not keep up.')
                    previous = ''
                    with sd.InputStream(device=device, samplerate=rate, channels=1, dtype='float32',
                                        blocksize=round(rate * .2), callback=callback):
                        self.events.put(('status', f'Listening on {info["name"]}. Speak now.'))
                        record('Listening started.')
                        while not self.stop_event.is_set():
                            if not errors.empty():
                                raise RuntimeError(errors.get())
                            try:
                                audio = blocks.get(timeout=.2)
                            except queue.Empty:
                                continue
                            stream.accept_waveform(16000, resample_audio(audio, rate))
                            while recognizer.is_ready(stream):
                                recognizer.decode_stream(stream)
                            text = recognizer.get_result(stream).strip()
                            if text and text != previous:
                                self.events.put(('partial', text))
                                record('Partial: ' + text)
                                previous = text
                            if recognizer.is_endpoint(stream):
                                if text:
                                    self.events.put(('final', text))
                                    record('Final: ' + text)
                                recognizer.reset(stream)
                                previous = ''
                    stream.input_finished()
                    while recognizer.is_ready(stream):
                        recognizer.decode_stream(stream)
                    text = recognizer.get_result(stream).strip()
                    if text:
                        self.events.put(('final', text))
                        record('Final: ' + text)
                    record('Stopped.')
                    self.events.put(('status', f'Stopped. Text saved in {path.name}.'))
                except Exception as exc:
                    record(f'Error: {type(exc).__name__}: {exc}')
                    raise
        except Exception as exc:
            self.events.put(('status', f'Could not start or continue: {exc}'))
        finally:
            self.events.put(('done', ''))


if __name__ == '__main__':
    app = tk.Tk()
    VoiceApp(app)
    app.mainloop()
