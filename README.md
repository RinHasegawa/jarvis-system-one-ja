# JARVIS — Voice Commands for Windows

JARVIS is a Windows prototype that turns a spoken command into a computer action. It connects ChatGPT desktop dictation to TypeSafe's Jev decision model and a local, restricted action executor. The prototype currently supports opening **Google Chrome** or **Notepad** with a single English command.

```text
Ctrl+Shift+J → Open JARVIS and start dictation
Speak → Ctrl+Shift+J to stop dictation
Text change → Jev classification → Local checks → Open the app
```

The goal is a voice interface for computer work. The current implementation is an early, narrow demonstration: it does not perform arbitrary computer tasks, search the web, send messages, make purchases, or enter credentials.

## How it works

1. JARVIS registers a global shortcut, opens its input window, focuses the text field, and sends the configured ChatGPT dictation shortcut.
2. After the user stops dictation, JARVIS watches for the first non-empty text change and sends a snapshot to Jev over HTTPS.
3. Jev classifies the action and target. Local code checks the response, the complete supported phrase, the current text, and whether the request was cancelled.
4. If all checks pass, JARVIS launches Chrome or Notepad from a fixed Windows path. Supported commands run automatically; model output cannot run arbitrary shell commands.

**Completion limitation:** A text-change event does not prove that dictation has finished inserting all text. The approach worked in the demonstrated trials, but a future update or a multi-part insertion could change the result. The application does not rely on a verified `CompositionFinalized` event. A later edit can block an action while a request is pending, but cannot undo an app launch that has already occurred.

See the [architecture presentation](JARVIS_Architecture_Janick.html) for diagrams; download the HTML file and open it in a browser.

## Getting started

Requirements:

- Windows and Python 3.12 with Tkinter.
- ChatGPT desktop with cross-app dictation configured to start and stop using `Ctrl+I`.
- A TypeSafe API key and an internet connection. ChatGPT dictation and Jev are separate services.
- Chrome at `C:\Program Files\Google\Chrome\Application\chrome.exe` and Notepad at `C:\Windows\System32\notepad.exe` for the respective actions.

The voice-command path uses Python's standard library; the local speech models and benchmark dependencies are not required for it.

```powershell
git clone https://github.com/RinHasegawa/jarvis-system-one-ja.git
cd jarvis-system-one-ja
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe .\jarvis_event_actions.py
```

Enter your TypeSafe API key in the masked field under Settings. You may save it locally using Windows DPAPI encryption. To start without a terminal window later, open `Open JARVIS Quiet.vbs`. The shortcut works while JARVIS is running. Press `Ctrl+Shift+J`, say “Open Google Chrome” or “Open Notepad,” then press the shortcut again. Use Escape to cancel a pending request; use **Quit** in Settings to stop the background app.

The [voice app guide](docs/VOICE_APP.md) contains setup, optional sign-in startup, implementation details, and limitations. It is currently in Japanese.

## Data and privacy

- JARVIS sends dictated text to TypeSafe's Jev API. ChatGPT handles its own audio processing and storage separately.
- JARVIS saves text, events, decisions, timing, and error types locally under `diagnostic_results/`; it does not save audio in the command flow. These logs may contain personal information and are excluded from Git.
- The optional saved API key is encrypted for the current Windows user and excluded from Git. Other programs running as that user may still be able to access it.
- Recordings, local databases, virtual environments, model weights, caches, and secrets are excluded from the repository. See [repository contents](docs/REPOSITORY_CONTENTS.md) (Japanese).

## Tests

Run the Windows application tests in a desktop environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_jarvis*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_composition*.py' -v
```

These tests use mocks for API requests and app launches. They do not establish live microphone accuracy or production API reliability. The full suite also includes local speech-recognition tests and needs the relevant optional dependencies.

## Local speech recognition experiments

The repository also contains separate recognition-only experiments. They do not execute PC actions:

- `Open Dictation Probe.cmd` records text changes and timing for the desktop dictation handoff. It does not capture audio or call an API.
- `Open JARVIS Voice Test.cmd` opens the Sherpa-ONNX streaming English test. It saves recognized text and errors locally, not audio. The model and optional dependencies must be installed separately.
- `Start_Microphone_Diagnostic.cmd` runs a Vosk microphone comparison. See [the evaluation plan](Voice_Diagnostic_Evaluation_Plan.md).
- `voice_live.py` provides Vosk streaming experiments; `voice_test.py` is an earlier Whisper-based, recorded-phrase test. See [the English recognition report](English_Speech_Recognition_Report.html).

## Japanese System One benchmark

The original research compares local Laya and hosted Jev on 70 fixed Japanese utterances, using the same action/target questions and scoring. STOP is handled separately by deterministic matching. Jev latency includes network and hosted inference time, so it should not be interpreted as local inference latency.

| Backend | ACTION | TARGET | p50 | p95 | Mean | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|
| Laya / ONNX Runtime FP32 (clean) | 31/64 (48.44%) | 23/25 (92.0%) | 504.725 ms | 686.024 ms | 541.365 ms | 1046.734 MiB |
| Laya / OpenVINO FP32, 4 threads (clean) | 31/64 (48.44%) | 23/25 (92.0%) | 423.338 ms | 932.707 ms | 574.771 ms | 2299.270 MiB |
| Jev 1.13.0 / direct API | 61/64 (95.3125%) | 25/25 (100%) | 557.695 ms | 645.263 ms | 566.140 ms | N/A (hosted) |

The Jev run completed 70/70 requests. Its ACTION Brier score was `0.0602875` and ECE was `0.02125`. Changing Laya's FP32 execution backend did not change semantic accuracy, and its ACTION accuracy did not meet the project's acceptance criterion for real actions. These historical results do not establish accuracy for the current voice-command flow. See the [benchmark report](docs/benchmark_report_ja.md) (Japanese) for methods and limitations.

To reproduce the local Laya benchmark with Python 3.12, install the project dependencies and obtain the official model. Model weights and caches are not included in this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe .\benchmarks\benchmark_laya.py --prepare-only
.\.venv\Scripts\python.exe .\benchmarks\benchmark_laya.py --offline
```

Phase 2.5 code, fixed cases, result JSON, and clean-run scripts are under `benchmarks/`. The Jev benchmark reads its API key from an environment variable.

## License

[MIT](LICENSE)
