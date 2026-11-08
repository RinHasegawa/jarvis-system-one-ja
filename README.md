# JARVIS — Voice commands for Windows

現在の試作は **ChatGPTデスクトップの音声入力 → JARVIS → TypeSafe Jev → Windowsアプリ起動** をつなぎます。英語の単一命令 `Open Google Chrome` / `Open Notepad` に対応し、条件を満たした命令は自動実行します。元の日本語System Oneベンチマークも保存しています。

```text
Ctrl+Shift+J → 小さな入力画面・音声入力を開始
話す → Ctrl+Shift+Jで停止
文字変更イベント → Jevの分類 → ローカルの許可チェック → アプリ起動
```

**Windows / Python 3.12 が必要です。** このアプリ経路はPython標準ライブラリだけで動作し、下記の重いベンチマーク用ライブラリや音声モデルの導入は不要です。ChatGPTデスクトップのアプリ外音声入力を `Ctrl+I` に設定し、別途TypeSafeのAPIキーとインターネット接続を用意します。

```powershell
git clone https://github.com/RinHasegawa/jarvis-system-one-ja.git
cd jarvis-system-one-ja
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe .\jarvis_event_actions.py
```

Settingsの伏字欄に自分のAPIキーを入力し、必要なら保存します。以後 `Open JARVIS Quiet.vbs` で端末画面なしで起動できます。常駐中にショートカットが有効です。サインイン時の起動設定、終了方法、テストは [音声アプリの手順と制約](docs/VOICE_APP.md) を参照してください。

**重要な制約:** 文字変更は「音声入力がすべて完了した」という保証ではありません。現実の入力で動作した試作ですが、分割挿入への一般的な保証はなく、UI AutomationのCompositionFinalized検知にも依存していません。長い複合命令や任意のPC操作は実行しません。Jevへのテキスト送信は外部APIを利用します。

- [アーキテクチャ資料（HTML）](JARVIS_Architecture_Janick.html) — ダウンロードしてブラウザで開けます。
- [保存するもの・GitHubに含めないもの](docs/REPOSITORY_CONTENTS.md)

## 元の日本語ベンチマークと音声認識の研究

日本語の音声PC操作を題材に、**System One / semantic decision model** を低遅延・精度・確率校正の観点から比較する個人実験です。

以下は元のベンチマークと独立したローカル音声認識テストの記録です。ローカル音声認識テスト自身はPC操作を実行しません。上記の音声アプリは別の入口です。購入・送信・認証情報入力・任意コマンド実行は対応していません。

## 音声認識を試す

To test your existing ChatGPT desktop dictation shortcut, open `Open Dictation Probe.cmd`. Press Start trial, dictate into the focused field, then Save trial. Text changes, focus events and observations are saved to `diagnostic_results/*.jsonl`. The probe does not capture audio or call an API. See `Desktop_Dictation_Streaming_Feasibility.md` for evidence and limitations.

For the graphical English test, double-click `Open JARVIS Voice Test.cmd`, choose a microphone and press **Start listening**. This local window uses Sherpa and saves text results and errors in `diagnostic_results/`, but does not save audio. Press **Stop** when finished. This is a speech-recognition prototype and does not run PC commands.

`Start_English_Voice_Test.cmd` now runs Sherpa-ONNX streaming English recognition. Text output and errors are saved incrementally under `diagnostic_results/` (ignored by Git); audio is not saved. The model is stored locally under `.cache/`. `Start_Microphone_Diagnostic.cmd` still runs the Vosk microphone comparison and saves its text results in the same folder. The two programs use different recognizers.

For the first microphone comparison, open `Start_Microphone_Diagnostic.cmd`. It compares the AirPods and laptop inputs with short English phrases and does not save recordings. See `Voice_Diagnostic_Evaluation_Plan.md` for the stages, measurements, and limits.

**リアルタイム試作:** `音声認識テスト.cmd` は英語モデルを起動します。準備完了後に話し、`q` キーで停止します。Vosk の英語モデルをローカルで実行します。詳しくは `English_Speech_Recognition_Report.html` を参照してください。日本語版を使う場合は `.\.venv\Scripts\python.exe -X utf8 .\voice_live.py --language ja` を実行します。

別環境でのリアルタイム版の準備（インターネット接続が必要）:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install vosk==0.3.45 sounddevice==0.5.3 scipy==1.18.1
New-Item -ItemType Directory -Force .cache | Out-Null
Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile .cache\vosk-model-small-en-us-0.15.zip
Expand-Archive .cache\vosk-model-small-en-us-0.15.zip -DestinationPath .cache
```

従来の Whisper テストは `.\.venv\Scripts\python.exe -X utf8 .\voice_test.py` で起動します。Enter を押してから5秒間録音し、後から結果を表示します。アプリ自身は音声や認識結果をファイル保存・送信しません。ただし、画面表示や OS・他ソフトによる記録まで制御するものではありません。どちらも認識だけのテストで、アプリは起動しません。

初回セットアップ（Python 3.12、インターネットが必要）:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install faster-whisper==1.2.1 sounddevice==0.5.3 av==16.1.0 scipy==1.18.1
.\.venv\Scripts\python.exe -X utf8 .\voice_test.py --download-model
```

セットアップ時に Whisper `small` モデルをダウンロードし、通常は `.cache/huggingface` に保存します（環境変数で変更される場合があります）。通常起動はローカルにあるモデルだけを使用し、モデル取得のための通信はしません。`--download-model` はモデルの取得・更新時だけ指定してください。ダウンロード後は `q` + Enter で終了できます。CPUの負荷や認識時間、精度は環境や声によって変わります。

PowerShell から調整する場合:

```powershell
.\.venv\Scripts\python.exe -X utf8 .\voice_test.py --seconds 8
.\.venv\Scripts\python.exe -X utf8 .\voice_test.py --list-devices
.\.venv\Scripts\python.exe -X utf8 .\voice_test.py --device 9
```

デバイス番号は一覧で確認してください。マイクが反応しなければ Windows のマイク許可と既定の入力デバイスも確認してください。モデルを変えて試す場合は、まず `--model base --download-model` のように取得し、以後 `--model base` で起動します。`medium` なども同様ですが、速度と精度のバランスが変わります。

## 問題設定

固定した70件の日本語発話を、次の閉集合へ分類します。

- ACTION: `OPEN_APP`、`OPEN_URL`、`VOLUME_UP`、`VOLUME_DOWN`、`MEDIA_PLAY_PAUSE`、`WAIT`、`UNKNOWN`
- TARGET: 明示された場合のみ、事前定義したアプリ／サイト候補から選択
- `STOP`: モデル分類から外し、決定的な文字列一致で扱う安全ポリシー

同一70ケース、同一 `action_target_v2` 質問、同一スコアリングで、ローカルLayaとホスト型Jevを比較します。Jevのレイテンシはネットワーク往復とホスト側推論を含む、利用可能な意思決定までの時間です。ローカル推論時間と同一視しません。

## 主な結果

| Backend | ACTION | TARGET | p50 | p95 | Mean | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|
| Laya / ONNX Runtime FP32 (clean) | 31/64 (48.44%) | 23/25 (92.0%) | 504.725 ms | 686.024 ms | 541.365 ms | 1046.734 MiB |
| Laya / OpenVINO FP32, 4 threads (clean) | 31/64 (48.44%) | 23/25 (92.0%) | 423.338 ms | 932.707 ms | 574.771 ms | 2299.270 MiB |
| Jev 1.13.0 / direct API | 61/64 (95.3125%) | 25/25 (100%) | 557.695 ms | 645.263 ms | 566.140 ms | N/A (hosted) |

Jev direct API は70/70 request成功です。JevのACTION Brier scoreは `0.0602875`、ECEは `0.02125` でした。LayaのFP32バックエンドは実行形式を変えても意味精度は同一で、現時点ではACTION精度が実操作の採用基準に届いていません。

詳しい方法・結果・限界は [日本語ベンチマーク報告書](docs/benchmark_report_ja.md) を参照してください。

## 再現

Python 3.12環境で依存関係を導入し、公式Layaモデルを取得してから実行します。Hugging FaceキャッシュおよびONNX/OpenVINO変換済み重みはこのリポジトリに含めません。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe .\benchmarks\benchmark_laya.py --prepare-only
.\.venv\Scripts\python.exe .\benchmarks\benchmark_laya.py --offline
```

Phase 2.5 のコード、固定ケース、結果JSON、クリーン環境ランチャーは `benchmarks/` にあります。Jevの評価アダプターは環境変数からのみAPIキーを読み、キーをソースへ保存しません。

## 公開範囲と安全性

- 公開するのは小さなコード、固定ベンチマーク、レポート、結果JSONです。
- 仮想環境、モデル重み、Hugging Faceキャッシュ、Node依存関係、ログ、ZIP、ローカル共有コピー、秘密情報はGit管理しません。
- 既知の制約と公開前確認項目は [PUBLIC_RELEASE_CHECKLIST](docs/PUBLIC_RELEASE_CHECKLIST.md) にまとめています。

## License

[MIT](LICENSE)
