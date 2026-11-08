# 音声アプリのセットアップと実装範囲

## 必要なもの

- Windows、Python 3.12（Tkinterを含む通常のWindows版）。この経路にpipライブラリの追加は不要。
- ChatGPTデスクトップ。アプリ外の入力欄へ音声入力できる機能と、開始／停止のショートカット `Ctrl+I` を設定した環境。この外部機能の提供状況は環境による。
- TypeSafeのJev APIキー、インターネット、API利用可能なアカウント。ChatGPTでの音声処理とJevでのテキスト分類は別のサービス。
- Chromeは `C:\Program Files\Google\Chrome\Application\chrome.exe`、Notepadは `C:\Windows\System32\notepad.exe` が存在すること。別のインストール場所は自動探索しない。

リポジトリ直下で `py -3.12 -m venv .venv` を実行し、`.\.venv\Scripts\python.exe .\jarvis_event_actions.py` で起動する。Settingsから自分のキーを入力する。保存は任意で、保存先は `.cache/jarvis_jev_key.dpapi`。Windowsの同じユーザーに結び付いたDPAPI暗号化であり、GitHubや別のPCへ移して再利用するものではない。同じWindowsユーザーで動くプログラムからのアクセスは防げない。

## 操作と状態

```text
待機（JARVIS常駐）
  ↓ Ctrl+Shift+J
画面表示 → 入力欄フォーカス → Ctrl+Iを送出 → 音声入力
  ↓ Ctrl+Shift+J
Ctrl+Iを送出して停止 → 最初の空でない文字変更を待つ
  ↓ Tk <<Modified>> / after_idleでスナップショット確認
テキストをローカル記録 → Jevへ送信（バックグラウンドスレッド）
  ↓ 応答キュー → UIスレッド
応答形式・命令・対象・キャンセル・改訂番号・現在の文字を確認
  ↓ 合格した単一命令だけ
固定パスを shell=False で一度起動 → 待機
```

例は `Open Google Chrome.` と `Open Notepad.`。please、launch、start等の限定した表現にも対応する。長い複合命令、否定、別のアプリ、検索やブラウザ内作業は対象外。

Escで現在の要求をキャンセルする。送信済みの通信自体を取り消す保証はないが、その古い応答では起動しない。起動済みアプリをEscで元に戻す機能はない。XやHideは隠す操作で、終了はSettingsのQuit。常駐していないとショートカットは使えない。別のJARVIS版を同時起動しない。

## 端末画面を出さずに起動／サインイン時に常駐

手動起動は `Open JARVIS Quiet.vbs`。初回にキーを設定した後はHideで隠せる。WindowsでVBScriptが利用できない場合は `.venv\Scripts\pythonw.exe` に `jarvis_event_actions.py --background` を渡して起動する。

以下は必要な場合に**リポジトリ直下**で一度実行する、現在のWindowsユーザーだけの自動起動設定。管理者権限は不要。このファイルを読むだけでは設定は変わらない。

```powershell
$jarvisRoot = (Get-Location).Path
$jarvisPython = Join-Path $jarvisRoot '.venv\Scripts\pythonw.exe'
$jarvisProgram = Join-Path $jarvisRoot 'jarvis_event_actions.py'
if (!(Test-Path -LiteralPath $jarvisPython) -or !(Test-Path -LiteralPath $jarvisProgram)) {
    throw 'リポジトリ直下とPython環境を確認してください。'
}
$jarvisRun = '"' + $jarvisPython + '" "' + $jarvisProgram + '" --background'
New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'JARVIS Voice' -Value $jarvisRun -PropertyType String -Force
```

次のサインインから有効。今すぐ使う場合は通常のランチャーで一度起動する。フォルダ移動後は設定を更新する。無効化は以下（現在動いているJARVISはSettingsのQuitで別途終了）。

```powershell
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'JARVIS Voice' -ErrorAction SilentlyContinue
```

## 通信と保存

- ChatGPTデスクトップがマイクと音声認識を担当する。JARVISからOpenAI APIを呼び出す構成ではない。ChatGPT側の音声処理・保存設定は別管理であり、このアプリの設定では制御しない。
- JARVISは挿入された文字をTypeSafe `https://api.typesafe.ai/v1/systemone` にHTTPSで送る。モデルは `jev-1.13.0`、選択肢はOPEN_APP/UNKNOWNとCHROME/NOTEPAD/NONE。タイムアウトは12秒。
- APIキーの値をログへ書かない。JARVISは音声を保存しない。テキスト、イベント、分類、所要時間、エラー種別は `diagnostic_results/*.jsonl` に追記する。このログは個人情報を含み得るためGit対象外。
- 実行に使うパスはローカル側の固定値。モデルが返すコマンドや任意パスは実行しない。確率の形式は検証するが、校正済みの安全閾値は実装していない。

## 検証と限界

Windows上で以下を実行する。GUIを作るテストがあるためデスクトップ環境が必要。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

テストではAPIや起動を模擬する。GUI・イベント・許可境界の検証であり、実マイクや本番APIの検証とは別。ローカル音声テストの分は対応する任意依存ライブラリが必要。

本番APIを呼ばないアプリ経路だけの検証:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_jarvis*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_composition*.py' -v
```

実機では、短い命令、長い非対応命令、連続する試行、Esc、通信失敗、ショートカット競合、フォーカス移動を個別に試す。送信先と自動起動の挙動を理解してから行う。

文字変更イベントは音声入力の完了通知ではない。最初の変更が完成文だった利用者の試行では動作したが、将来のアプリ更新や分割挿入には保証がない。入力が送信後に変われば起動前のチェックで拒否するが、起動後に来た追記で過去の起動を取り消すことはできない。UI AutomationのCompositionFinalizedは診断対象であり、この経路の起動条件ではない。

## 主なファイル

| 役割 | ファイル |
|---|---|
| 現行の自動起動経路 | `jarvis_event_actions.py` |
| 文字変更からJevへ | `jarvis_event_test.py` |
| コンパクトUI | `jarvis_popup.py` |
| RegisterHotKey・SendInput・状態管理 | `jarvis_shortcut.py` |
| API・応答検証・固定パス実行・ログ | `jarvis_command.py` |
| キーの暗号化保存 | `jarvis_key_store.py` |
| 完了イベント診断 | `composition_sensor.py`, `composition_native_probe.py` |
| 別経路のローカル認識 | `voice_sherpa.py`, `voice_live.py`, `voice_test.py` |

November 4のDelivery Plan等は当時の計画。現在の実装は本手順とコードを優先して読む。
