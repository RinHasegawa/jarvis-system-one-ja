# Can ChatGPT desktop dictation provide streaming input to JARVIS?

Research and implementation note — November 4, 2026.

## Conclusion

Calling this universally impossible would be too strong. However, the Windows cross-app dictation workflow demonstrated by the user currently exposes completed text after recording is stopped. We have not found a supported interface that delivers its partial transcripts to JARVIS during recording. A change to JARVIS can receive text sooner after it is exposed; it cannot recover words that the dictation app has not exposed.

There are three separate meanings of streaming: audio captured continuously, transcription computed incrementally inside a service, and partial text delivered continuously to our application. Only the third enables JARVIS to interpret your words while you speak. The demonstration establishes final-text insertion, not the internal processing mode or partial-text interface.

## Evidence and its limits

1. The user's Windows demonstration shows a global shortcut, a recording indicator, and text insertion in Firefox, YouTube search and a terminal after stopping. It also shows an unintended address-bar target. This is direct evidence for cross-app insertion and focus sensitivity on this PC. It does not reveal the implementation, streaming transport, underlying model, or an end-of-transcription event available to JARVIS.
2. OpenAI's desktop prompting documentation describes speech becoming editable text in the composer. It does not promise a public cross-app partial transcript subscription. [Official guide](https://learn.chatgpt.com/docs/prompting).
3. A firsthand user report describes global hold/toggle dictation into selected text fields, with a commenter reporting it on Windows too. This supports the user's demonstrated behavior but is not an official compatibility specification. [User report](https://www.reddit.com/r/ChatGPT/comments/1us2ia6/dictation_into_any_text_field_in_the_new/).
4. A reporter on OpenAI's GitHub issue tracker measured post-stop waits of 3–17 seconds in a specific macOS composer configuration and inferred batch processing. That is evidence about their test, not proof of the internal path on this user's Windows app. [Reported desktop timing](https://github.com/openai/codex/issues/36803).
5. Other users report incremental, word-by-word dictation in ChatGPT's web interface. Another thread reports web behavior changing while the app retained its previous behavior. These are reports of web/composer experiences, not evidence that the Windows global shortcut exports streaming text. They demonstrate why we should not generalize across surfaces or rollouts. [Web partial-text report](https://www.reddit.com/r/ChatGPT/comments/1xcijen/upgraded_voice_dictation_on_web_shows_words_as/), [Web/app difference report](https://www.reddit.com/r/ChatGPT/comments/1xc17o9/transcription_feature_changed_can_i_put_it_back/).
6. A historical global-hotkey regression report includes Windows observations and subsequent resolution reports. This indicates version/activation behavior can change; it does not show a partial transcript interface. [Original issue](https://github.com/openai/codex/issues/27296).

User reports are observations, not guarantees, and the web reports do not establish availability for this account or Windows version. No review establishes the current hidden internal model or a supported way to reuse subscription authentication from a separate application.

## First-principles limit

Suppose the spoken commands are "Open Chrome" and "Open Notepad". If the text field remains empty during both recordings, the observable input to JARVIS is identical. JARVIS cannot reliably distinguish the commands before the first text arrives. Faster polling, clipboard checks or Jev calls do not add the missing information.

For the demonstrated workflow:

Earliest informed decision = text exposed after dictation stop + handoff time + decision-request time.

We can reduce the handoff and decision overhead. We cannot remove the recording boundary by modifying the receiver alone. Sound-level indicators show activity, not words. Insertion arriving one character at a time can be synthetic typing of an already-completed transcript; many edit events therefore do not prove live recognition. Likewise, text that stays unchanged for a second is not proof that dictation has ended.

## Architecture choices

| Choice | What it enables | Judgment |
|---|---|---|
| Receive final dictation in JARVIS | Accurate completed commands using the current shortcut; optional faster post-insertion preview | Feasible to test now; prioritize for November 6 delivery. |
| Short repeated dictation turns | A sequence of completed command chunks | Can feel more responsive, but remains turn-based; adds shortcut and finalization overhead. |
| Subscribe to a documented future partial-text output | Genuine streaming into JARVIS if the app exposes it | Possible conditionally; no such supported interface established in this research. |
| Read live text displayed in a web/composer UI | Potentially access some visible partial words | Requires separate investigation and permissions; fragile and not equivalent to the global Windows shortcut. Do not rely on it for this deadline. |
| Local streaming recognizer plus final desktop dictation | Local speculative preview, accurate final-text review | Technically possible as two paths; accuracy differences, microphone sharing and cancellation add complexity. Not selected for the deadline. |
| Direct streaming speech API | A different service integration | Not the user's requested desktop-dictation route. It should not be substituted without an explicit decision. |

Even genuine partial text should not directly launch apps. "Open Chrome ... actually don't" illustrates why interpretation can change. Partial decisions can be previews, while execution waits for a committed command and a valid action proposal. The existing Jev benchmark accepts completed text requests; it does not prove this full product connection is implemented.

## Added experiment: Dictation Probe

Run `Open Dictation Probe.cmd`. This lightweight Tk window imports no speech-recognition model and makes no network requests. It does not capture microphone audio. The desktop dictation app still has its own audio/network behavior, which this probe does not change.

1. Set the optional reference phrase, then press Start trial. The JARVIS input receives focus.
2. Use the same dictation shortcut from the demonstration. Speak, pause for several seconds, continue speaking, then end dictation.
3. Observe whether any actual words entered the JARVIS field before you stopped. Select Yes, No or Not sure.
4. Press Save trial. Repeat at least three times with short and longer utterances. An optional screen recording can provide a more precise shared timeline; this tool does not record one automatically.

The probe saves timestamped text changes, focus events, final text, reference phrase and the user's observation in diagnostic_results/dictation_*.jsonl, flushing each event. Closing a trial records an interrupted outcome. The probe observes only its own field; it does not monitor arbitrary clipboard contents, other windows or global keys.

Timings are relative to pressing Start trial, not to actual microphone capture or shortcut release. Text-change callbacks can group multiple underlying character changes. Manual observations are required to distinguish after-stop insertion from before-stop output; they are not a calibrated latency measurement. Keyboard typing and paste also trigger the same events and are not automatically labeled as dictation.

Verification: automated synthetic text insertion checks incremental logging and final snapshots; another check closes a trial before Save and checks that partial results remain. These checks cannot establish real desktop dictation compatibility, latency or live streaming. The user's actual shortcut trial is still needed.

If the trial shows only after-stop output, proceed with the completed-command path and optimize its delay. If it shows words before stopping, preserve the logs and observed sequence, then test revisions and completion behavior before claiming streaming support. If nothing arrives, test focus and field compatibility first; this is not evidence that the microphone failed.

## Delivery recommendation

Keep the existing November 6 plan: prove text handoff, validate Jev decisions, then add controlled Windows actions. Do not make undocumented partial-output access a prerequisite. Reassess streaming only if the probe or a supported feature exposes real partial words before the stop action.
