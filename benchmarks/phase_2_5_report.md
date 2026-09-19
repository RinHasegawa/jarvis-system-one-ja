# JARVIS Phase 2.5 — Laya optimization and comparison preparation

## Executive result

The simplified `action_target_v2` task improves semantic ACTION accuracy from the old multi-question baseline's 37.1% to 48.4%, but remains far below the 95% acceptance target. Runtime conversion helps substantially, yet no tested configuration reaches the 250 ms warm-p50 target in this normal desktop environment.

ONNX Runtime FP32 is the current best-balanced candidate: it exactly preserves PyTorch predictions, stays below the preferred 1.5 GiB process-RSS ceiling in this run, and improves p50 latency. OpenVINO FP32 has the fastest p50 among accuracy-preserving configurations but uses materially more RAM. Both INT8 variants change semantics; OpenVINO INT8 collapses to uniform probabilities and is invalid for use.

Completed clean-run and Jev direct-API results are summarized in `docs/benchmark_report_ja.md`.

## Experimental controls

- The original 70 Japanese cases and labels are unchanged.
- The original Phase 0-2 result remains `benchmarks/laya_baseline.json` and was not overwritten.
- Laya receives only ACTION plus TARGET when an explicit target is present.
- `STOP` remains in the frozen labels but is detected and scored deterministically outside Laya (6/6 in every run).
- All converted artifacts originate from the pinned official `convaiinnovations/laya` multilingual checkpoint at revision `c5d78730f3493e4fe16d61507ef4b78eef7318cf`; no third-party quantized weights were used.
- The five local backends use the same questions, ground truth, scoring, and 70-case ordering.

## Local backend matrix (normal desktop environment)

| Backend | ACTION accuracy | TARGET accuracy | p50 (ms) | p95 (ms) | Mean (ms) | Peak RSS (MiB) | Cost | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| PyTorch FP32 | 48.4% | 92.0% | 1366.0 | 2580.8 | 1724.9 | 3080.3 | ¥0 local | Reference for action_target_v2 |
| ONNX Runtime FP32 | 48.4% | 92.0% | 1152.5 | 3900.9 | 1651.0 | 1056.8 | ¥0 local | 100% prediction agreement with PyTorch; current best balance |
| OpenVINO FP32 | 48.4% | 92.0% | 948.9 | 4323.5 | 1573.0 | 2007.1 | ¥0 local | 100% prediction agreement; fastest accuracy-preserving p50; higher RAM |
| ONNX Runtime INT8 | 42.2% | 92.0% | 672.1 | 2351.8 | 978.1 | 695.4 | ¥0 local | Faster/smaller, but ACTION accuracy and agreement regress |
| OpenVINO INT8 | 23.4% | 20.0% | 643.8 | 2908.5 | 955.2 | 1455.5 | ¥0 local | Invalid: probabilities become uniform and argmax collapses to OPEN_APP |

> These runs occurred sequentially in a memory-constrained normal desktop session. Available RAM and paging differed between runs, so small backend timing differences are provisional until the manual clean run is complete.

### Cold start, environment, and reference agreement

| Backend | Load (ms) | First inference (ms) | RAM before/after (MiB available) | ACTION agreement | Max ACTION probability delta | TARGET agreement |
|---|---:|---:|---:|---:|---:|---:|
| PyTorch FP32 | 121249.6 | 3970.9 | 991.1 / 1091.8 | reference | reference | reference |
| ONNX Runtime FP32 | 26380.1 | 4326.6 | 1868.2 / 1025.1 | 100.0% | 0.0000501 | 100.0% |
| OpenVINO FP32 | 64223.7 | 5953.1 | 2647.9 / 449.8 | 100.0% | 0.0000499 | 100.0% |
| ONNX Runtime INT8 | 17113.7 | 732.2 | 2976.4 / 1895.4 | 60.0% | 0.6126126 | 84.0% |
| OpenVINO INT8 | 60217.8 | 1075.4 | 2936.9 / 1116.6 | 12.9% | 0.8569429 | 12.0% |

## Semantic quality

The simplified PyTorch reference gets 31/64 semantic ACTION cases (48.4%) and 23/25 explicit TARGET cases (92.0%). TARGET narrowly misses 95%; ACTION misses by a wide margin.

| Expected ACTION | Correct | Accuracy |
|---|---:|---:|
| `OPEN_APP` | 2/15 | 13.3% |
| `OPEN_URL` | 1/10 | 10.0% |
| `VOLUME_UP` | 6/8 | 75.0% |
| `VOLUME_DOWN` | 5/8 | 62.5% |
| `MEDIA_PLAY_PAUSE` | 7/8 | 87.5% |
| `WAIT` | 6/6 | 100.0% |
| `UNKNOWN` | 4/9 | 44.4% |

The chief semantic weaknesses are `OPEN_APP` and `OPEN_URL`; simplifying the task removes the original broad WAIT bias but does not make the checkpoint reliable enough for real computer control. Deterministic STOP matching remains 6/6 and also avoids confusing media pause with emergency cancellation.

## Runtime performance

Against the action_target_v2 PyTorch reference, ONNX Runtime FP32 reduces p50 by 15.6% and OpenVINO FP32 by 30.5%. Neither approaches 250 ms. High p95 values and variable per-case times are consistent with current system memory pressure, but only the clean run can quantify how much of the tail is environmental.

## Memory pressure and environment effects

Peak process RSS ranges from 695.4 to 3080.3 MiB. ONNX Runtime FP32 measured 1056.8 MiB, while OpenVINO FP32 measured 2007.1 MiB. The latter ended with only 449.8 MiB available RAM, so its latency tail must not be treated as a clean backend-only measurement.

The completed manual launcher recorded total/available RAM, pagefile use, CPU utilization, and largest processes before and after each run. See the clean-run JSON files and `docs/benchmark_report_ja.md` for the current public interpretation.

## Quantization effects

ONNX INT8 lowers p50 to 672.1 ms and peak RSS to 695.4 MiB, but ACTION accuracy falls to 42.2% and ACTION prediction agreement to 60.0%. OpenVINO NNCF INT8 uses 32 separate calibration utterances (no evaluation cases), but returns uniform choice probabilities and therefore fails semantic validation. Neither INT8 artifact is a JARVIS candidate.

## Calibration

Reliability bins group predictions by top-choice probability and compare mean confidence with observed accuracy. Brier score measures squared probability error across all choices (lower is better). Expected Calibration Error (ECE) is the sample-weighted gap between bin confidence and bin accuracy (lower is better). A probability in [0, 1] is not by itself evidence of calibration.

| Backend | ACTION Brier | ACTION ECE | TARGET Brier | TARGET ECE |
|---|---:|---:|---:|---:|
| PyTorch FP32 | 0.6360 | 0.1539 | 0.1178 | 0.0561 |
| ONNX Runtime FP32 | 0.6360 | 0.1539 | 0.1178 | 0.0561 |
| OpenVINO FP32 | 0.6360 | 0.1539 | 0.1178 | 0.0561 |
| ONNX Runtime INT8 | 0.7398 | 0.1336 | 0.1218 | 0.0620 |
| OpenVINO INT8 | 0.8571 | 0.0915 | 0.9000 | 0.1000 |

## CPU thread probe

The probe repeats a fixed 14-case balanced subset twice. It is a relative scheduling test, not a replacement for the full 70-case scores. Eight logical threads were intentionally not saturated so the desktop remains responsive.

| OpenVINO FP32 threads | Samples | p50 (ms) | p95 (ms) | Mean (ms) | Machine CPU |
|---:|---:|---:|---:|---:|---:|
| 1 | 28 | 1068.0 | 3312.8 | 1501.0 | 12.2% |
| 2 | 28 | 1092.2 | 2720.6 | 1385.2 | 23.3% |
| 4 | 28 | 707.7 | 1619.8 | 930.7 | 46.6% |

OpenVINO detects both `CPU` and Intel `GPU`. The optional GPU full benchmark was not run in this already memory-pressured session because the integrated GPU shares system RAM; no claim is made that CPU or GPU is faster.

## Jev fair-comparison status

The canonical Jev result is `benchmarks/clean_run/jev_typesafe_direct_1_13_0.json`: Jev 1.13.0 direct API, 70/70 successful requests, ACTION 61/64 (95.3125%), TARGET 25/25 (100%), p50 557.695 ms, p95 645.263 ms. Jev latency is full request-to-usable-decision time over the network and must not be described as equivalent to local model-only inference.

## Suitability for JARVIS real-time control

No tested Laya configuration is ready for real-time control: FP32 conversions improve runtime without changing the semantic shortfall, while quantization further harms semantics. The completed clean run confirms the local memory-latency trade-off, and the same-case Jev result meets the fixed-set accuracy target. Any backend decision must still consider keeping network latency/cost and local privacy/offline operation explicit.

## Pending manual steps and blockers

1. Review both completed FP32 result JSON files with `clean_run_environment.json`.
2. Treat `jev_typesafe_direct_1_13_0.json` as the Jev authority; do not substitute the non-canonical Vercel attempt.
3. Do not implement STT or Windows actions until the semantic-decision backend is selected.

## Result files

- `benchmarks/results/laya_pt_fp32_action_target_v2.json`
- `benchmarks/results/laya_onnx_fp32.json`
- `benchmarks/results/laya_openvino_fp32.json`
- `benchmarks/results/laya_onnx_int8.json`
- `benchmarks/results/laya_openvino_int8.json`
- `benchmarks/results/openvino_fp32_thread_probe.json`
- `benchmarks/clean_run/laya_onnx_fp32_clean.json`
- `benchmarks/clean_run/laya_openvino_fp32_clean.json`
- `benchmarks/clean_run/jev_typesafe_direct_1_13_0.json`
- `docs/benchmark_report_ja.md`
- `benchmarks/phase_2_5/run_jev_benchmark.py`
