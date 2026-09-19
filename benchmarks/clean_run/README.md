# Manual clean-environment benchmark

This launcher compares ONNX Runtime FP32 and OpenVINO FP32 (4 CPU threads) under the same frozen 70-case `action_target_v2` conditions. Each backend runs in its own child process. It records RAM, available RAM, pagefile use, CPU load, and the largest processes before and after each run as well as before and after the complete suite.

Before starting, close Codex Desktop and preferably close browsers, Teams/Discord, media editors, games, and other memory- or CPU-heavy applications. Do not close Windows security or system processes.

From PowerShell in the JARVIS project directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\benchmarks\clean_run\run_clean_benchmark.ps1
```

The launcher does not close applications. It writes:

- `laya_onnx_fp32_clean.json`: complete ONNX Runtime FP32 result
- `laya_openvino_fp32_clean.json`: complete OpenVINO FP32 result
- `clean_run_environment.json`: suite-level and per-backend before/after environment snapshots and comparable metric summaries
- `laya_onnx_fp32_clean.log`: ONNX console output
- `laya_openvino_fp32_clean.log`: OpenVINO console output

Both result JSON files use the same benchmark schema and include ACTION/TARGET accuracy, p50/p95/mean latency, peak process RSS, available RAM and pagefile snapshots, and CPU measurements.

Reopen Codex only after PowerShell reports completion.
