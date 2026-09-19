# Laya Japanese feasibility benchmark

- Timestamp: `2026-09-19T21:04:50+0900`
- Official package: `laya==0.3.3`
- Official model: `convaiinnovations/laya` / `multilingual` at `c5d78730f3493e4fe16d61507ef4b78eef7318cf`
- Device: `cpu`
- Cases: **70** Japanese utterances
- Decision bundle: action + target + execute-now + risk in one Laya call

## Result

**NOT YET VIABLE** — Investigate first-party ONNX/OpenVINO export and INT8 quantization before application work.

| Metric | Measured value |
|---|---:|
| Local cold model load | 73677.1 ms |
| First inference after load | 3526.0 ms |
| Warm inference p50 | 2417.9 ms |
| Warm inference p95 | 2768.0 ms |
| Warm inference mean | 2475.1 ms |
| Action accuracy | 37.1% (26/70) |
| Target accuracy, applicable cases | 96.0% (24/25) |
| Target accuracy, all cases | 67.1% (47/70) |
| Execute-now accuracy at 0.5 | 71.4% |
| Risk accuracy | 48.6% |
| Peak process RSS | 3152.0 MiB |
| RSS increase after load | 1063.7 MiB |
| Average process CPU, one-core basis | 393.8% |
| Average process CPU, machine capacity | 49.2% |
| Average system CPU during measured cases | 64.4% |

## Semantic behavior by expected action

| Expected action | Correct | Accuracy | Dominant failure |
|---|---:|---:|---|
| `OPEN_APP` | 5/15 | 33.3% | Usually predicted `WAIT` |
| `OPEN_URL` | 3/10 | 30.0% | Usually predicted `WAIT` |
| `VOLUME_UP` | 3/8 | 37.5% | Usually predicted `WAIT` |
| `VOLUME_DOWN` | 3/8 | 37.5% | Usually predicted `WAIT` |
| `MEDIA_PLAY_PAUSE` | 1/8 | 12.5% | Predicted `WAIT` or `STOP` |
| `WAIT` | 6/6 | 100.0% | None in this set |
| `STOP` | 5/6 | 83.3% | One `WAIT` prediction |
| `UNKNOWN` | 0/9 | 0.0% | Predicted `WAIT` or `STOP` |

The target classifier recognized explicitly named allowlisted targets well, but the action classifier was strongly biased toward `WAIT`. At the proposed initial gate (`action >= 0.90`, target >= 0.90 when applicable, `execute_now >= 0.90`, risk `LOW`), only 3/70 cases passed with a correct action: two `WAIT` commands and one `STOP` command. No app-open, URL-open, volume, or media command passed. Consecutive partial-transcript stability was not tested because this benchmark contains independent utterances rather than streaming sequences.

## Interpretation

This is a closed-set semantic classification benchmark over Japanese text, not a speech-to-text benchmark. The official multilingual checkpoint is used without third-party quantized weights. STOP results are diagnostic only: the JARVIS design still requires deterministic emergency matching outside Laya.

The peak 3.15 GiB process RSS and momentary near-zero available system memory indicate serious pressure on this 8 GB machine. The raw per-case predictions, probabilities, latencies, and resource measurements are in `benchmarks/laya_baseline.json`. The next backend options are documented in `benchmarks/laya_optimization_investigation.md`; no conversion was performed in this phase.
