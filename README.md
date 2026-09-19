# JARVIS System One (Japanese)

日本語の音声PC操作を題材に、**System One / semantic decision model** を低遅延・精度・確率校正の観点から比較する個人実験です。

これは実運用のPC操作アプリではありません。音声認識、GUI操作、PowerShell生成、任意コマンド実行、購入・送信・認証情報入力は実装していません。

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
