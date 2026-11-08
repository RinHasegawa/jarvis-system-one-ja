"""Local, push-to-start Japanese speech recognition test (no PC actions)."""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日本語の音声認識テスト（音声は外部送信しません）")
    parser.add_argument("--model", default="small", help="Whisper モデル名（初期値: small）")
    parser.add_argument("--download-model", action="store_true", help="モデルのダウンロード・更新を許可")
    parser.add_argument("--seconds", type=float, default=5, help="録音秒数（初期値: 5）")
    parser.add_argument("--device", type=int, help="入力デバイス番号")
    parser.add_argument("--list-devices", action="store_true", help="入力デバイス一覧を表示")
    parser.add_argument("--audio", type=Path, help="マイクの代わりに音声ファイルを認識")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 30:
        parser.error("録音秒数は 1〜30 秒にしてください")
    return args


def resample_audio(recording, sample_rate: int):
    """Convert to 16 kHz with an anti-aliasing filter."""
    if sample_rate == 16000:
        return recording
    from scipy.signal import resample_poly

    divisor = math.gcd(sample_rate, 16000)
    return resample_poly(recording, 16000 // divisor, sample_rate // divisor).astype("float32")


def record_audio(sd, np, seconds: float, device: int | None):
    info = sd.query_devices(device, "input")
    if info["max_input_channels"] < 1:
        raise RuntimeError("入力できるマイクが見つかりません。")
    # Recording at the device's native sample rate works with more Windows microphones.
    sample_rate = int(info["default_samplerate"])
    print(f"録音中... {seconds:g} 秒間話してください（{info['name']}）", flush=True)
    recording = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1,
                       dtype="float32", device=device, blocking=True).reshape(-1)
    peak = float(np.max(np.abs(recording))) if recording.size else 0.0
    print(f"録音終了（入力レベル最大: {peak:.3f}）")
    if peak < 0.001:
        print("マイク入力がほぼありません。入力デバイスや Windows のマイク許可を確認してください。")
        return None
    # faster-whisper expects a 16 kHz mono float waveform.
    return resample_audio(recording, sample_rate)


def transcribe(model, audio) -> str:
    segments, _ = model.transcribe(audio, language="ja", beam_size=5,
                                    vad_filter=True, condition_on_previous_text=False)
    return "".join(segment.text for segment in segments).strip()


def resolve_model_path(model_name: str, allow_download: bool, download_model) -> str:
    """Resolve locally by default and forbid the library's tokenizer fallback."""
    path = Path(model_name)
    if not path.is_dir():
        path = Path(download_model(model_name, local_files_only=not allow_download))
    if not (path / "tokenizer.json").is_file():
        raise FileNotFoundError("モデルに tokenizer.json がありません。完全なモデルを用意してください。")
    return str(path)


def main() -> int:
    args = parse_args()
    try:
        import numpy as np
        import sounddevice as sd
        import scipy.signal
        if args.list_devices:
            print(sd.query_devices())
            return 0
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
    except ImportError as exc:
        print(f"必要なライブラリがありません: {exc}\nREADME のセットアップを実行してください。", file=sys.stderr)
        return 1

    try:
        print(f"モデル {args.model} を準備中...", flush=True)
        if args.download_model:
            print("モデルの取得・更新のためネットワークに接続します。", flush=True)
        try:
            model_path = resolve_model_path(args.model, args.download_model, download_model)
            model = WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=4,
                                 local_files_only=True)
        except Exception:
            if not args.download_model:
                print("モデルが未取得の場合は --download-model を指定して準備してください（README 参照）。", file=sys.stderr)
            raise
        print("準備完了。アプリは音声・認識結果のファイル保存や送信を行いません。", flush=True)
        if args.audio:
            print("認識結果: " + (transcribe(model, str(args.audio)) or "（音声を認識できませんでした）"))
            return 0
        print("Enter で録音開始、q + Enter で終了します。")
        while True:
            if input("\n録音するには Enter > ").strip().lower() == "q":
                break
            audio = record_audio(sd, np, args.seconds, args.device)
            if audio is None:
                continue
            print("認識中...", flush=True)
            start = time.perf_counter()
            result = transcribe(model, audio)
            print(f"認識結果: {result or '（音声を認識できませんでした）'}")
            print(f"認識時間: {time.perf_counter() - start:.1f} 秒")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\n終了しました。")
        return 0
    except Exception as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
