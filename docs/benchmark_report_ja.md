# JARVIS System One 日本語ベンチマーク報告書

## 概要

本実験は、日本語のPC操作発話を安全に限定した意味決定問題として扱う。実装済みなのはテキスト入力に対する分類評価であり、STT、Windows操作、任意シェル実行は対象外である。

`action_target_v2` では、ACTIONを7分類し、TARGETは発話が明示的な対象を要求する25件だけで評価する。元の70ケースとラベルは固定した。`STOP` の6件はモデルの選択肢に含めず、決定的なキャンセル一致で別途6/6を確認した。そのためACTIONの意味精度の分母は64である。

## 環境と方法

- 端末: Surface Laptop Go、Intel Core i5、4 physical / 8 logical CPU、8 GB RAM、Intel内蔵GPU
- ローカルモデル: 公式 `convaiinnovations/laya` multilingual checkpoint、固定revision `c5d78730f3493e4fe16d61507ef4b78eef7318cf`
- ローカル比較: PyTorch FP32、ONNX Runtime FP32、OpenVINO FP32、ONNX Runtime INT8、OpenVINO INT8
- クリーン環境: Codex Desktopと不要アプリを閉じ、ONNX Runtime FP32とOpenVINO FP32（4 threads）を独立した子プロセスとして同一70ケースで順次実行
- ホスト型比較: Jev `1.13.0` direct API。70/70 request成功。レイテンシは送信から利用可能な意思決定が返るまでのエンドツーエンド時間

確率の校正にはBrier scoreとExpected Calibration Error（ECE）を用いた。どちらも低いほど望ましい。ECEは確信度binごとの平均確信度と実測正解率の差を標本比率で重み付けした値である。

## クリーン環境のローカル結果

| Backend | ACTION | TARGET | p50 | p95 | Mean | Peak RSS | Available RAM before/after | Pagefile before/after | Avg. system CPU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ONNX Runtime FP32 | 31/64 (48.44%) | 23/25 (92.0%) | 504.725 ms | 686.024 ms | 541.365 ms | 1046.734 MiB | 3837.586 / 3861.852 MiB | 746.359 / 704.188 MiB | 42.142% |
| OpenVINO FP32, 4 threads | 31/64 (48.44%) | 23/25 (92.0%) | 423.338 ms | 932.707 ms | 574.771 ms | 2299.270 MiB | 3864.027 / 3934.250 MiB | 703.516 / 656.715 MiB | 45.072% |

OpenVINO FP32はp50が低い一方、Peak RSSが約2.3 GiBで、8 GB端末におけるメモリ余裕はONNX Runtime FP32より小さい。ONNX Runtime FP32はp95とRSSのバランスがよく、現時点のローカル候補として扱う。ただし、どちらもACTION精度は実操作の採用基準には届いていない。

## Jev direct API 正式結果

このリポジトリでのJevの正本は `benchmarks/clean_run/jev_typesafe_direct_1_13_0.json` である。

| Model | Requests | ACTION | TARGET | p50 | p95 | Mean | ACTION Brier / ECE | TARGET Brier / ECE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Jev 1.13.0, direct API | 70/70 success | 61/64 (95.3125%) | 25/25 (100%) | 557.695 ms | 645.263 ms | 566.140 ms | 0.0602875 / 0.02125 | 0.00052 / 0.006 |

Jevは固定70ケース上でACTIONとTARGETの目標を満たした。ただし、この時間にはネットワーク、ホスト側推論、レスポンス受信が含まれる。ローカルLayaのモデル単体性能と直接比較するものではなく、JARVISで重要な「要求から利用可能な意思決定まで」の利用時レイテンシとして読む必要がある。

## 通常環境での変換実験

| Backend | ACTION | TARGET | p50 | Peak RSS | 解釈 |
|---|---:|---:|---:|---:|---|
| PyTorch FP32 | 48.44% | 92.0% | 1366.011 ms | 3080.250 MiB | `action_target_v2` 参照実装 |
| ONNX Runtime FP32 | 48.44% | 92.0% | 1152.510 ms | 1056.790 MiB | PyTorchとの予測一致率100% |
| OpenVINO FP32 | 48.44% | 92.0% | 948.882 ms | 2007.090 MiB | PyTorchとの予測一致率100% |
| ONNX Runtime INT8 | 42.19% | 92.0% | 672.052 ms | 695.440 MiB | 速度・RAMは改善、ACTION意味精度は低下 |
| OpenVINO INT8 | 23.44% | 20.0% | 643.795 ms | 1455.450 MiB | 出力が一様化し、評価対象から除外 |

FP32変換は速度またはメモリを改善しても、意味精度を改善しない。量子化はこのチェックポイントと校正条件では意味精度をさらに損なった。

## 再現物と公開方針

- 固定ケース: `benchmarks/laya_cases.json`
- Phase 2.5コード: `benchmarks/phase_2_5/`
- ローカル結果: `benchmarks/results/` と `benchmarks/clean_run/laya_*_clean.json`
- Jev正本: `benchmarks/clean_run/jev_typesafe_direct_1_13_0.json`
- 除外物: モデル重み、Hugging Faceキャッシュ、仮想環境、Node依存関係、ログ、APIキー、ローカル共有コピー

結果JSONは数値・確率・予測・ハッシュを残し、公開前にローカル絶対パスだけを相対パスへ置換している。
