# JARVIS voice pipeline: first-principles evaluation

The outcome we need is a correct, timely transcription of the user's speech. An error can arise before, during, or after decoding. A controlled comparison should change one factor at a time and observe the boundaries between stages. The current voice prototype only displays text: Jev and actions cannot yet be evaluated end to end.

## First test: two microphones, same short phrases

Run `Start_Microphone_Diagnostic.cmd`. Select the AirPods microphone and the laptop microphone from the displayed input-device list. For each one, record two seconds of quiet, then say each of the three displayed phrases once. Start speaking after “Listening now”. Audio stays in memory and is not saved or uploaded. Text results are saved locally as they appear.

The test records each phrase for four seconds and then replays its audio to the same English Vosk model. Text results are saved as they appear in the local `diagnostic_results` folder, including incomplete runs. The log contains recognized text and device names; audio is not saved. It prints the final text, word errors versus the displayed phrase, microphone signal levels, clipping fraction, callback errors and lost blocks, decoding time, and a numerical comparison of block-by-block versus whole-utterance resampling. It also shows the point in the supplied audio at which a partial result first appeared. This is not a live end-to-end latency test.

## Stage-by-stage measurements

| Boundary | Question | First evaluation | Interpretation and limitation |
|---|---|---|---|
| Speaker and room | Is there background noise or a different speaking distance? | Same quiet room, distance and natural volume for both inputs; capture quiet RMS. | Quiet RMS is only signal level, not a full noise or intelligibility assessment. |
| AirPods/Bluetooth vs laptop hardware | Does one input produce consistently worse signal or text? | Compare both inputs across the same phrases. | Different live utterances are not identical; a difference suggests investigation, not proof of cause. |
| Windows selection | Did the app open the intended input? | Choose explicit input numbers and display the opened device and sample rate. | Device numbers can change on reconnect; names may be truncated. |
| Capture/buffering | Were blocks lost or were input errors reported? | Count callback status events and queue drops. | Zero events does not prove Bluetooth audio is clear or complete upstream. |
| Preprocessing | Does independent block conversion differ from whole-signal conversion? | Compare RMS difference after both resampling paths on the captured phrase. | Difference is a signal diagnostic, not proof of an audible issue or a recognition failure. |
| Model | Are final words correct? | Compare final output with the expected phrase using word edit distance. | Three phrases are a pilot, not a reliable population accuracy score; actual speaking can differ from the prompt. |
| Streaming workload | Is processing fast enough in this replay? | Decode time for four seconds; first partial's position in the audio. | Audio is captured before replay; these are not actual live microphone-to-display latency or peak RAM. |
| Display and actions | Is the outcome shown, and can an action happen? | Inspect output and later test actions separately. | Current diagnostic only prints text; no Jev, STOP, safety gate, or app execution exists here. |

## Decision rules for the pilot

- If a device has input errors, dropped blocks, near-zero speech level, or severe clipping, resolve input first and repeat. There are no universal RMS pass thresholds here.
- If one device repeatedly produces worse words under comparable conditions, investigate microphone selection, level and Bluetooth quality before blaming the model.
- If both devices receive speech cleanly but both mistranscribe similar phrases, evaluate alternate models using the same audio. For a true same-audio comparison, first obtain explicit user permission to save or retain a short sample; establish its location and deletion policy before doing so.
- If block conversion differs materially from whole conversion, investigate stateful resampling and determine its effect on word accuracy with a controlled test. The present metric does not prove such an effect.
- If replay processing consistently takes longer than audio duration, live backlog is plausible; measure the actual live path before concluding. If replay is faster, real-time performance still is not guaranteed.
- Once the pilot points to a cause, expand to more phrases and repeat takes in quiet and normal conditions. Track reference words, substitutions, insertions and deletions, exact command match, time to first useful partial, finalization delay, peak process RAM and CPU, and input errors. Record model, device, settings, environment and test date. Decide acceptance thresholds with the user's real usage in mind; do not treat published dataset accuracy as this PC's accuracy.

Privacy: this tool saves text results and device names locally, but does not intentionally save or send captured audio. Console output is visible on screen, and OS memory management and other applications are outside its control. It does not inspect or modify existing private conversation data.
