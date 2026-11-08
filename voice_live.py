"""Continuous local speech recognition using the Vosk streaming decoder."""
import argparse
import json
import queue
import sys
from pathlib import Path

from voice_test import resample_audio

ROOT = Path(__file__).resolve().parent
MODELS = {"en": "vosk-model-small-en-us-0.15", "ja": "vosk-model-small-ja-0.22"}


def main():
    parser = argparse.ArgumentParser(description="Local real-time speech recognition")
    parser.add_argument("--language", choices=MODELS, default="en", help="Recognition language (default: en)")
    parser.add_argument("--device", type=int, help="Microphone device number")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices")
    args = parser.parse_args()
    import numpy as np
    import sounddevice as sd
    if args.list_devices:
        print(sd.query_devices())
        return 0
    from vosk import Model, KaldiRecognizer, SetLogLevel
    import msvcrt
    model_path = ROOT / ".cache" / MODELS[args.language]
    if not model_path.is_dir():
        print(f"Model not found: {model_path}. See README for setup.", file=sys.stderr)
        return 1
    SetLogLevel(-1)
    print(f"Loading {MODELS[args.language]}...", flush=True)
    model = Model(str(model_path))
    recognizer = KaldiRecognizer(model, 16000)
    info = sd.query_devices(args.device, "input")
    rate = int(info["default_samplerate"])
    blocks = queue.Queue(maxsize=30)
    errors = queue.Queue()

    def callback(indata, frames, timing, status):
        if status:
            errors.put(str(status))
        try:
            blocks.put_nowait(indata[:, 0].copy())
        except queue.Full:
            errors.put("Audio was lost because recognition could not keep up.")

    print(f"Microphone: {info['name']} / Speak now. Press q to stop.", flush=True)
    previous = ""
    with sd.InputStream(device=args.device, samplerate=rate, channels=1, dtype="float32",
                        blocksize=round(rate * 0.2), callback=callback):
        while True:
            if msvcrt.kbhit() and msvcrt.getwch().lower() == "q":
                break
            if not errors.empty():
                raise RuntimeError(errors.get())
            try:
                audio = blocks.get(timeout=0.2)
            except queue.Empty:
                continue
            pcm = (np.clip(resample_audio(audio, rate), -1, 1) * 32767).astype("<i2").tobytes()
            if recognizer.AcceptWaveform(pcm):
                text = json.loads(recognizer.Result()).get("text", "")
                if text:
                    print("Final: " + text, flush=True)
                previous = ""
            else:
                text = json.loads(recognizer.PartialResult()).get("partial", "")
                if text and text != previous:
                    print("Partial: " + text, flush=True)
                    previous = text
    final = json.loads(recognizer.FinalResult()).get("text", "")
    if final:
        print("Final: " + final)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
