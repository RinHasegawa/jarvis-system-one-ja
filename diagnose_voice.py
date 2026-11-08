"""Interactive, in-memory microphone and Vosk diagnostic; no saved audio."""
import argparse
import json
import queue
import re
import time
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import psutil
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from voice_test import resample_audio

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / '.cache' / 'vosk-model-small-en-us-0.15'
PHRASES = ['open google chrome', 'open spotify', 'what time is it']


def normalize(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def word_errors(expected, actual):
    a, b = normalize(expected), normalize(actual)
    row = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        next_row = [i]
        for j, other in enumerate(b, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (word != other)))
        row = next_row
    return row[-1], len(a)


def capture(device, seconds):
    info = sd.query_devices(device, 'input')
    rate = int(info['default_samplerate'])
    block = round(rate * .2)
    chunks = queue.Queue(maxsize=64)
    status_flags = []
    dropped = [0]
    def callback(indata, frames, timing, status):
        if status:
            status_flags.append(str(status))
        try:
            chunks.put_nowait(indata[:, 0].copy())
        except queue.Full:
            dropped[0] += 1
    frames = []
    wanted = int(rate * seconds)
    count = 0
    with sd.InputStream(device=device, samplerate=rate, channels=1, dtype='float32',
                        blocksize=block, callback=callback):
        print('Listening now...', flush=True)
        deadline = time.monotonic() + seconds + 5
        while count < wanted:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Microphone did not provide audio in time.')
            try:
                chunk = chunks.get(timeout=min(1, remaining))
            except queue.Empty:
                continue
            frames.append(chunk)
            count += len(chunk)
    return np.concatenate(frames)[:wanted], rate, status_flags, dropped[0]


def evaluate(model, audio, rate):
    whole = resample_audio(audio, rate)
    block = round(rate * .2)
    split = np.concatenate([resample_audio(audio[i:i+block], rate) for i in range(0, len(audio), block)])
    n = min(len(whole), len(split))
    diff = float(np.sqrt(np.mean((whole[:n] - split[:n]) ** 2))) if n else 0
    signal = float(np.sqrt(np.mean(whole[:n] ** 2))) if n else 0
    recognizer = KaldiRecognizer(model, 16000)
    results, first_partial, previous = [], None, ''
    start = time.perf_counter()
    for i in range(0, len(split), 3200):
        pcm = (np.clip(split[i:i+3200], -1, 1) * 32767).astype('<i2').tobytes()
        if recognizer.AcceptWaveform(pcm):
            results.append(json.loads(recognizer.Result()).get('text', ''))
        else:
            partial = json.loads(recognizer.PartialResult()).get('partial', '')
            if partial and first_partial is None:
                first_partial = min((i + 3200) / 16000, len(split) / 16000)
            previous = partial or previous
    results.append(json.loads(recognizer.FinalResult()).get('text', ''))
    return ' '.join(x for x in results if x), time.perf_counter() - start, first_partial, diff, signal, previous


def main():
    parser = argparse.ArgumentParser(description='Compare two microphones using short English phrases; no recordings are saved.')
    parser.add_argument('--list-devices', action='store_true')
    args = parser.parse_args()
    devices = sd.query_devices()
    if args.list_devices:
        print(devices)
        return
    print('LOCAL DIAGNOSTIC: audio stays in memory and is not saved or sent. Text results are saved locally.\n'
          'We capture then replay each short phrase through the model; this does NOT measure live end-to-end latency.\n'
          'Close voice chat or other apps using the microphone if they interfere.\n')
    print(devices)
    selected = []
    for label in ('AirPods microphone', 'laptop microphone'):
        while True:
            try:
                index = int(input(f'Enter the device number for {label}: '))
                info = sd.query_devices(index, 'input')
                if info['max_input_channels'] < 1:
                    raise ValueError('Not an input device')
                selected.append((index, info['name']))
                break
            except (ValueError, sd.PortAudioError) as exc:
                print(f'Choose a valid input device: {exc}')
    if selected[0][0] == selected[1][0]:
        print('Both choices are the same device; select two different inputs to compare.')
        return
    if not MODEL.is_dir():
        raise FileNotFoundError('English model not found. See README for setup.')
    SetLogLevel(-1)
    start = time.perf_counter()
    model = Model(str(MODEL))
    print(f'\nModel loaded in {time.perf_counter()-start:.2f} s; process RAM now {psutil.Process().memory_info().rss / 2**20:.0f} MiB.')
    rows = []
    for index, name in selected:
        print(f'\n=== {name} ===')
        input('Press Enter, then stay quiet for 2 seconds. ')
        quiet, rate, flags, lost = capture(index, 2)
        quiet_rms = float(np.sqrt(np.mean(quiet ** 2)))
        print(f'Quiet RMS: {quiet_rms:.5f}; input status events: {len(flags)}; lost blocks: {lost}.')
        for phrase in PHRASES:
            input(f'\nPress Enter, then say: "{phrase}"  ')
            audio, rate, flags, lost = capture(index, 4)
            rms = float(np.sqrt(np.mean(audio ** 2)))
            peak = float(np.max(np.abs(audio)))
            clipped = float(np.mean(np.abs(audio) >= .999) * 100)
            text, elapsed, first, diff, signal, _ = evaluate(model, audio, rate)
            errors, words = word_errors(phrase, text)
            ratio = diff / signal if signal else 0
            print(f'Heard: "{text or "(nothing)"}" | word errors: {errors}/{words}')
            print(f'Audio RMS: {rms:.5f}; peak: {peak:.3f}; clipped samples: {clipped:.3f}%; '
                  f'input status events: {len(flags)}; lost blocks: {lost}')
            print(f'Decode: {elapsed:.2f} s for 4 s of audio; first partial after {first if first is not None else "none"} s of audio; '
                  f'chunk-vs-whole conversion difference: {ratio:.3%} of signal RMS')
            if flags:
                print('Input status: ' + '; '.join(flags))
            rows.append((name, phrase, text, errors, words, elapsed, len(flags), lost))
    print('\n=== SUMMARY ===')
    for _, name in selected:
        group = [r for r in rows if r[0] == name]
        print(f'{name}: {sum(r[3] for r in group)}/{sum(r[4] for r in group)} word errors; '
              f'{sum(r[6] for r in group)} status events; {sum(r[7] for r in group)} lost blocks.')
    print('A small sample is directional, not a statistically reliable accuracy score.\n'
          'Different takes are not identical audio; a device difference is evidence to investigate, not proof.\n'
          'Review word errors, signal levels, clipping and status events together; no single metric proves the cause.\n'
          'Jev and app execution are not implemented and cannot be evaluated here.')


if __name__ == '__main__':
    class Tee:
        def __init__(self, console, log):
            self.console, self.log = console, log
        def write(self, text):
            self.console.write(text)
            self.console.flush()
            self.log.write(text)
            self.log.flush()
            return len(text)
        def flush(self):
            self.console.flush()
            self.log.flush()

    log_dir = ROOT / 'diagnostic_results'
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.log')
    log_file = log_path.open('x', encoding='utf-8', buffering=1)
    sys.stdout = Tee(sys.stdout, log_file)
    print(f'Text results will be saved to: {log_path}\nAudio is not saved.')
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nStopped; partial text results are saved. No audio was saved.')
    except Exception as exc:
        print(f'Error: {exc}')
        raise SystemExit(1)
