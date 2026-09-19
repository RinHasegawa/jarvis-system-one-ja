# Public release checklist

対象リポジトリ名は `jarvis-system-one-ja`、公開設定は **Public**、ライセンスは **MIT** である。ここではGitHubへのpush前に確認する項目を固定する。

## 実施済み（ローカル）

- [x] ルートREADMEを実験の目的、範囲、正本結果、限界に更新した。
- [x] 日本語ベンチマーク報告書を `docs/benchmark_report_ja.md` に配置した。
- [x] MIT `LICENSE` を追加した。
- [x] `.gitignore` に仮想環境、キャッシュ、Node依存関係、環境変数、証明書、巨大モデル、ログ、ローカル共有コピー、ZIPを追加した。
- [x] `benchmarks/laya_cases.json`、`benchmarks/phase_2_5/`、`benchmarks/clean_run/` の再現用コードと小さなJSON、`benchmarks/results/` を公開対象に残した。
- [x] Vercel Gatewayの失敗試行とそのNodeワークスペースは公開対象から外した。Jevの正本は direct API の `jev_typesafe_direct_1_13_0.json` である。
- [x] 結果JSONに含まれていたローカル絶対パスは相対パスへ置換し、数値・予測・確率・ハッシュは保持した。
- [x] APIキー値、Bearerトークン値、秘密鍵、ローカルユーザー絶対パスを追跡予定ファイルで検索した。

## GitHub作成時に行うこと

- [ ] GitHubで `jarvis-system-one-ja` を **Public** として作成する。
- [ ] GitHubのLICENSE表示がMITとして認識されることを確認する。
- [ ] 初回commitを確認し、`git push` は内容を目視してから行う。
- [ ] READMEと `docs/benchmark_report_ja.md` がブラウザ上で正しくレンダリングされることを確認する。
- [ ] GitHubのSecret scanning / push protectionが有効であることを確認する。

## 公開してはいけないもの

- `.venv/`、`.cache/`、`node_modules/`、`.env*`
- APIキー、アクセストークン、Bearerヘッダー値、証明書、秘密鍵
- ONNX、OpenVINO、PyTorch、Hugging Faceの重み・キャッシュ
- ログ、ローカル絶対パスを含む失敗試行、ZIP、共有用の重複コピー

## 正本の数値

Jev `1.13.0` direct API は70/70 requests成功、ACTION `61/64 = 95.3125%`、TARGET `25/25 = 100%`、p50 `557.695 ms`、p95 `645.263 ms` である。数値の変更や別試行への置換は、根拠とともに報告書を更新してから行う。
