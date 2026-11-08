"""Local streaming English recognition with saved text results, not audio."""
import argparse
import queue
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import sherpa_onnx
from voice_test import resample_audio

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / '.cache' / 'sherpa-onnx-streaming-zipformer-en-20M-2023-02-17'


def create_recognizer():
    return sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(MODEL / 'tokens.txt'),
        encoder=str(MODEL / 'encoder-epoch-99-avg-1.int8.onnx'),
        decoder=str(MODEL / 'decoder-epoch-99-avg-1.onnx'),
        joiner=str(MODEL / 'joiner-epoch-99-avg-1.int8.onnx'),
        num_threads=2, sample_rate=16000, feature_dim=80,
        enable_endpoint_detection=True, decoding_method='greedy_search')


def main():
    parser = argparse.ArgumentParser(description='Local Sherpa English streaming test')
    parser.add_argument('--device', type=int, help='Microphone device number')
    parser.add_argument('--list-devices', action='store_true')
    args = parser.parse_args()
    if args.list_devices:
        print(sd.query_devices())
        return
    import msvcrt
    logs = ROOT / 'diagnostic_results'
    logs.mkdir(exist_ok=True)
    path = logs / ('sherpa_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.log')
    with path.open('x', encoding='utf-8', buffering=1) as log:
        def emit(message):
            print(message, flush=True)
            log.write(message + '\n')
            log.flush()
        emit(f'Text results and errors: {path}. Audio is not saved.')
        try:
            emit('Loading local Sherpa model...')
            recognizer = create_recognizer()
            stream = recognizer.create_stream()
            info = sd.query_devices(args.device, 'input')
            rate = int(info['default_samplerate'])
            emit(f'Microphone: {info["name"]}; {rate} Hz. Speak now; press q to stop.')
            blocks = queue.Queue(maxsize=30)
            errors = queue.Queue()
            def callback(indata, frames, timing, status):
                if status:
                    errors.put(str(status))
                try:
                    blocks.put_nowait(indata[:, 0].copy())
                except queue.Full:
                    errors.put('Audio blocks lost: recognition did not keep up.')
            previous = ''
            with sd.InputStream(device=args.device, samplerate=rate, channels=1, dtype='float32',
                                blocksize=round(rate * .2), callback=callback):
                while True:
                    if msvcrt.kbhit() and msvcrt.getwch().lower() == 'q':
                        break
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
                        emit('Partial: ' + text)
                        previous = text
                    if recognizer.is_endpoint(stream):
                        if text:
                            emit('Final: ' + text)
                        recognizer.reset(stream)
                        previous = ''
            stream.input_finished()
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)
            text = recognizer.get_result(stream).strip()
            if text:
                emit('Final: ' + text)
            emit('Stopped.')
        except KeyboardInterrupt:
            emit('Stopped by user.')
        except Exception as exc:
            emit(f'Error: {type(exc).__name__}: {exc}')
            raise


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit(1)
