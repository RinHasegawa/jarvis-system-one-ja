# JARVIS: from desktop dictation to Windows actions

Prepared November 4, 2026. Deadline: **November 6, 2026, 4 p.m. Japan time**.

## 1. The delivery decision

Build a small English voice-command application using the desktop dictation feature you demonstrated. Focus a JARVIS text field, use your existing shortcut to speak and finish, review the inserted text, then submit it. JARVIS sends that text to Jev, displays its decision, validates the result, and opens an allowed app when you press Execute.

The first release supports opening **Chrome and Notepad**, plus rejecting unsupported or unclear requests and cancelling pending work. Both executables were found on this PC during planning. Start with Notepad; Chrome follows after the same path passes. Other applications can be added after delivery using the same registry, but each needs its own verification.

This is a focused, user-initiated, turn-based assistant. Dictation delivers completed text, so real-time partial recognition is not a release requirement. The demonstrated dictation and Jev are external dependencies; this release cannot promise offline operation or zero runtime cost. We are changing the earlier local-only project direction for this prototype at the user's request. Record that decision in the implementation documentation and reconcile the existing AGENTS guidance before runtime integration.

## 2. Current evidence and remaining gaps

| Component | Evidence today | What it does not prove |
|---|---|---|
| Desktop dictation | Your supplied video demonstrates insertion into Firefox, YouTube search, and a terminal after ending dictation. Settings show Ctrl+I as the one-tap shortcut. | Compatibility with a Tk/JARVIS input field, reliable focus, or an automatic completion signal. |
| Dictation quality | The demonstrated phrases are much more intelligible than the earlier local-model results; a proper name was still mistranscribed. | An accuracy score, guaranteed correct commands, or a known underlying speech model. |
| JARVIS GUI | Python/Tk window, launchers, microphone selection, Sherpa output and incremental text logs exist. | An editable command input, Jev integration or PC execution. |
| Jev adapter | Existing benchmark sends UTF-8 JSON text to the TypeSafe API. Stored historical run reports 70/70 successful requests and 61/64 semantic action decisions correct. | Current credentials, current availability, performance with new English questions, or end-to-end action success. |
| Credentials | No TypeSafe key was found in this process environment during planning. | Whether you hold a valid key elsewhere. Check securely; do not paste a key into chat. |
| Windows actions | Chrome and Notepad executables are present. | That the new executor launches them or handles existing windows correctly. |
| Logs | Existing voice programs save timestamped text/error results locally. | Complete traces for the new chain; these still need implementation. |

We should stop spending the deadline window on replacing or tuning local speech models. Preserve Sherpa/Vosk as comparison tools. Their problems do not have to be solved to validate this dictation-based path.

## 3. Concrete architecture and program boundaries

**Voice → desktop dictation → editable JARVIS command box → explicit Submit → frozen command snapshot → Jev → validated action proposal → Execute → fixed Windows launcher → observed result.**

Yes, additional JARVIS programming is required. Dictation only inserts text. It does not itself construct a Jev request or execute its result. JARVIS is the application that owns this connection and its state, not an extra model that must be trained.

| Proposed module | Responsibility |
|---|---|
| command_app.py | Lightweight Tk command UI: input, Submit, proposed action, Execute, Cancel, result, and log location. |
| command_session.py | State transitions, immutable text revision, one pending request, cancellation generation, duplicate-click protection. |
| jev_client.py | Authenticated HTTPS request, pinned model, bounded timeout, response parsing, usage/latency recording. Adapt the existing transport; keep frozen benchmark files unchanged. |
| command_policy.py | Validate action and target, uncertainty handling, allowlist and cancellation checks. |
| windows_actions.py | Resolve fixed executable paths and launch approved apps. No model-generated command strings. |
| result_log.py | Incremental JSONL evidence plus a simple readable session summary. |
| tests and evals | Deterministic failure tests and a separate English command evaluation dataset. |

The GUI should not load Sherpa, Vosk, Torch, or Whisper for this mode. Keep network work off the GUI thread. This reduces local load and prevents a slow API call freezing Cancel or the window.

The UI states should be **Ready → Text received → Request pending → Proposal ready → Executing → Outcome**. Cancel, edit, timeout or error invalidates the pending proposal. Editing text while a response is in flight makes that response stale; it must never become executable. Disable duplicate submission/Execute clicks and consume a proposal after one launch attempt.

## 4. Model and interface specifications

### Desktop dictation

Use the installed feature exactly as demonstrated. Its implementation, audio transport and underlying model have not been established by the video. Local history visible in settings is not proof that recognition itself runs locally. Existing account access, microphone settings and shortcut configuration remain prerequisites.

The integration boundary is ordinary editable text. Do not start by intercepting global keystrokes, monitoring the clipboard, scraping ChatGPT history, or extracting session credentials. The simplest complete test uses a focused JARVIS field. Explicit Submit establishes completion without guessing whether text is still being inserted. A quiet period or unchanged text alone is not a reliable dictation-finished signal.

### Jev

Official TypeSafe documentation specifies POST https://api.typesafe.ai/v1/systemone with bearer authentication and UTF-8 JSON containing model, state and questions. The state accepts text. Choice questions define a fixed set of options and return a choice, a probability distribution and confidence. It is an inference service; it does not launch programs on this PC. [API specification](https://docs.typesafe.ai/api/system-one), [Choice](https://docs.typesafe.ai/primitives/choice).

Use a **versioned model ID**. Begin with jev-1.13.0, matching the historical adapter evidence, if current account access permits. The official model page also lists jev-1.14.0 and says jev-latest points to it. A version change requires its own validation; do not silently inherit an alias change. [Model specification](https://docs.typesafe.ai/models).

For this small command set, use two questions: ACTION = OPEN_APP / WAIT / UNKNOWN and TARGET = CHROME / NOTEPAD / NONE. Both are asked for every submitted command. Unlike the old benchmark, live code must not rely on ground-truth knowledge of whether a target is applicable. Use English question descriptions, reject missing targets, conflicting multiple targets, negated requests and unsupported instructions. Test the exact question configuration used at runtime.

Keep stop/cancel handling deterministic and outside Jev. Cancel must invalidate outstanding work before a delayed response can trigger execution. It cannot undo an application already launched, and we should not imply it can.

Probability and confidence are different fields; neither is a safety guarantee. Choose any rejection threshold using a development set, freeze it, then evaluate held-out examples. Confirmation remains enabled for delivery even for confident answers. [Confidence explanation](https://docs.typesafe.ai/confidence).

Credentials: use the process environment or a masked session-only input. Do not persist keys in source or logs. API usage is paid/subject to account access. Display the external-text submission clearly. Bound requests to a short command (proposed application limit: 500 characters), one request at a time and a proposed 10-second network timeout. Treat these as our application choices, not vendor limits. Handle invalid keys, rate limits, service failures, timeout and malformed response by blocking execution and preserving a useful error. [Request errors](https://docs.typesafe.ai/api/errors).

### Windows executor

Map CHROME and NOTEPAD to checked, fixed absolute executable paths. Use argument lists and shell=False. Do not accept arbitrary executable paths, URLs, shell text or extra arguments from dictation or a model. Python recommends fully qualified executable paths for reliable process creation. [Python 3.12 subprocess documentation](https://docs.python.org/3.12/library/subprocess.html).

A returned process handle proves a launch request, not that a visible window appeared. Validate the observed result separately. Chrome may reuse an existing process; Notepad may redirect to a packaged app. For the demo, visually confirm the requested app appears. Do not promise automatic foregrounding or create a general GUI agent within this deadline.

## 5. Phases and pass criteria

All criteria below are proposed release gates, not completed tests or guarantees about untested inputs.

| Phase | Build / work | Verification and exit gate | Approximate focused effort |
|---|---|---|---|
| 0. Freeze scope and preflight | Confirm deadline, document hybrid direction, verify launch paths, inspect key availability securely, create run manifest/log writer. | GUI can open from the supplied launcher; an intentional startup error and interrupted run leave useful logs; no keys leak into logs. | 0.5–1 hour |
| 1. Prove dictation handoff | Add editable box, clear/focus controls, visible text-change status, explicit Submit and local snapshot. No network required. | User dictates 10 short inputs: exact wording, punctuation, empty input, clear/retry, focus change, and a proper name. Every actual insertion into JARVIS must be captured exactly once in the committed snapshot. Record intended words separately to distinguish recognition errors from handoff corruption. | 1–2 hours plus user test |
| 2. Establish Jev transport | Adapt existing HTTP client and pinned model; test a typed command before using dictation. | 5 small live requests yield valid schema and expected choices; missing/invalid key, timeout and malformed JSON tests never reach an executor. Logs contain model, latency and outcome. | 1–2 hours |
| 3. Validate English decisions | Build 60 labeled text cases: 30 supported, 20 explicitly unsupported/negated, 10 ambiguous or multiple-target inputs. Use 20 for development and 40 held out. | Freeze questions/thresholds before held-out evaluation; require at least 18/20 held-out supported requests routed correctly and 0 executable proposals among the 20 held-out rejection cases. Count all failures and uncertainty; do not discard errors. Keep confirmation enabled. | 1.5–2.5 hours |
| 4. Validate policy and cancellation | Implement proposal revisions, allowlist validation, local Cancel, request invalidation and one-time execution. | At least 12 deterministic cases: bad labels, missing/NONE target, NaN/out-of-range probabilities, incompatible choices, stale reply after edit, Cancel during request, double-click, late reply, empty input and overlong input. Zero unauthorized launches in tests. | 1–2 hours |
| 5. Verify real Windows launch | Implement fixed Notepad launch, then Chrome. Display proposal and require Execute. | Each app opens on 3 attempts including an already-open condition. A missing path fails clearly. Duplicate clicks yield at most one launch attempt per committed command. Inspect actual windows, not just return codes. | 1–1.5 hours |
| 6. End-to-end user evaluation | Combine dictation, Jev, policy and launch. User performs 20 trials: 10 clear app commands, 5 rejection requests and 5 cancellation/race cases. | At least 9/10 supported trials produce the intended app after Execute; 0 launches in rejected/cancelled cases. Save intended phrase, dictated text, decision and observed app outcome for each trial. Report every failure and stage. | 1–2 hours plus user test |
| 7. Delivery rehearsal and freeze | Cold-start/reopen test, disconnect/reconnect microphone, offline Jev failure, expired key path, closing during request, log retrieval, short usage guide. | 3 successful cold starts; no UI freeze during failure cases; partial logs survive; no auto-replay after restart; final user rehearsal and known-limitations list. Freeze 2 hours before deadline. | 1–2 hours |

Estimated total: about **9–16 focused engineering hours plus user participation and contingency**. This is a planning estimate, not a guaranteed completion time. Phase 1 and credentials are the early blockers; do them first rather than building the whole action pipeline around an untested handoff.

## 6. Evaluation design: isolate the cause

For every real trial record: intended command (user-provided), inserted text, committed snapshot, Jev model/question version, action/target probabilities, validation outcome, request latency, execution attempt and observed application. Give the trial and each submission a unique local ID. Flush events as they occur; incomplete trials remain visible.

Report four distinct outcomes: **dictation accuracy** (intended vs inserted), **handoff integrity** (inserted vs committed), **semantic accuracy** (committed text vs correct action), and **actual task success** (intended app visibly opened). Also report rejection accuracy, unwanted launches, duplicates and cancellation failures. A correct decision on incorrectly dictated text is not a successful voice command.

Measure separately: user dictation time, shortcut-stop to insertion (manual observation initially), Submit to Jev response, response to displayed proposal, and Execute to visible app (manual observation initially). Initial performance target: median Submit-to-proposal under 2 seconds and 95th percentile under 5 seconds on at least 20 trials; failed and timed-out trials must also be reported. These are targets to evaluate, not a promise. Prefer a slower correct confirmed action over a fast wrong one. Do not claim a confidence threshold is calibrated from this small sample.

Logs should be incremental JSONL plus a human-readable result table under diagnostic_results. Persist committed transcripts, decisions, timings, device/shortcut description, model version, app version and sanitized errors. Do not log secrets, authorization headers, or unrelated clipboard/window content. Audio is not saved by JARVIS without a separate explicit request. Explain that ChatGPT's own recording history/settings are managed separately. Keep logs out of Git, show their location, and allow the user to delete them.

## 7. Schedule to November 6, 4 p.m. Japan time

| Date / checkpoint | Planned outcome | If it fails |
|---|---|---|
| November 4, next work block | Phases 0–1; prove dictation insertion and preserve results. Check Jev access immediately. | Fix focus/input compatibility before live integration. User-approved copy/paste into JARVIS can be a disclosed fallback, not claimed automatic dictation. |
| November 5, first half | Phases 2–3: valid live Jev responses and English evaluation results. | If access is unavailable, deliver input capture and recorded decisions only; explicitly mark voice-to-action goal incomplete. |
| November 5, second half | Phases 4–5: policy, Cancel, Notepad and Chrome confirmed launches. | Reduce to Notepad if Chrome proves unreliable; keep errors visible. Do not silently bypass Jev to claim success. |
| November 6, morning | Phase 6 user trials, investigate failing stages, repeat only affected checks. | Reduce scope rather than add untested features. |
| November 6, 2 p.m. | Feature freeze; Phase 7, launch instructions and demo rehearsal. | Fix only release-blocking defects and rerun affected gates. |
| November 6, 4 p.m. | Deliver runnable prototype, saved results, short instructions, model/config versions and remaining limitations. | Report incomplete gates honestly rather than claim a complete product. |

The user needs to be present for the actual dictation handoff and final voice trials. No synthetic sample can replace those gates. If only one user session is available, use it first for Phase 1 and reserve a short final session before freeze.

## 8. Concrete risks and choices

- **Wrong text field:** the video already shows address-bar insertion. Use a visible focus indicator and reviewable command text; submit only from JARVIS. Focus changes invalidate any armed flow.
- **No official dictation-completion event:** explicit Submit solves this for the first release. Auto-submit, background interception and global command routing are later work.
- **Recognition mistakes:** allow editing, show exactly what will be sent, and test names separately. Do not silently turn a near-match into a different action.
- **Model forced-choice errors:** include UNKNOWN and NONE; reject invalid combinations and uncertain cases; require Execute confirmation.
- **Repeated or delayed results:** immutable request IDs, revision checks, Cancel invalidation, one pending request and consume-once proposals.
- **Dependency on network/account:** startup status, bounded timeout, actionable errors and no automatic execution retry. Key entry remains local and masked.
- **PC load:** no local ASR model in dictation mode; responsive GUI worker; measure actual latency and process memory rather than extrapolate old benchmarks.
- **Recording evidence:** save text/metrics/errors incrementally before asking the user to test; retain interrupted sessions. If logging cannot start, display the problem before continuing the evaluation.
- **Deadline pressure:** keep one command per submission and only two applications. No wake word, continuous listening, custom speech training, package installer, arbitrary browsing or general computer control in this release.

## 9. The immediate next deliverable

An editable JARVIS dictation input screen with **Focus input**, **Save test**, a reference phrase field, a visible committed snapshot and persistent trial logs. You use Ctrl+I as in the video, speak and stop dictation, and confirm what actually appeared. This gate is local and needs no new speech download or Jev call.

After that succeeds, connect the same committed snapshot to the decision-only Jev path; then add the validated executable registry. This preserves a concrete chain of evidence from your voice all the way to an observed Windows action.
