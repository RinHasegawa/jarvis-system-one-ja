# Project changelog

## 2026-11-10 — Startup and shortcut recovery

### Investigation

- A Windows sign-in startup entry was pointing to `jarvis_popup.py`, the older manual-submit interface. The active automatic-action entry point is `jarvis_event_actions.py`. On the test PC, the startup entry was corrected to use that entry point; a new installation must configure its own startup entry as described in the [voice app guide](docs/VOICE_APP.md).
- Local diagnostic records showed that several later `Ctrl+Shift+J` presses reached the old app but were ignored while its state remained `waiting_text`. The screenshot showed the manual version waiting for the user to press Run command. The evidence identifies why those recorded presses did not start another command; it does not establish why Windows was configured to start the older version or explain every possible missed shortcut.

### Changes

- A shortcut press while waiting for dictation text now cancels that attempt. A subsequent press starts a new command. Cancellation does not send the waiting text or immediately start recording; text from the external dictation tool may still arrive late.
- Added a local metadata-only shortcut health log and `Check JARVIS Shortcut.cmd`. It records process startup, registration and registration failures, received shortcuts, current phase, focus failures, generated dictation-shortcut sends, and periodic heartbeats. It does not capture dictated words, audio, clipboard contents, or keystrokes in other applications. Existing command logs can still contain recognized text; all diagnostics remain Git-ignored.
- The app still uses the first non-empty text change as an experimental submission trigger. A change event is not a guaranteed dictation-completion signal, and a delayed edit after launch cannot undo an action.

### Verification and limits

- The corrected automatic-action window was displayed and its shortcut registration was recorded. The user reported a successful live test after the fix.
- Local records show two successive Chrome launch requests after dictated text and successful Jev responses. A launch request is evidence that JARVIS asked Windows to start the application; the user's report supplies the observed-success evidence. These trials are not a comprehensive accuracy or reliability evaluation.
- Fourteen targeted automated tests passed, covering the event-triggered path, action gate, shortcut behavior, and metadata logging. API responses and app launches were mocked in those tests; the waiting-state cancellation case was also tested without submitting delayed text.
- A further Windows reboot after the startup correction and broad long-duration, failure, and microphone testing were not verified as part of this update.
