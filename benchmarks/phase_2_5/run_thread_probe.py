from __future__ import annotations

import json
import statistics
import time

import psutil

from common import ROOT, load_cases, percentile, questions_for_case, resolve_snapshot, system_memory_snapshot
from run_laya_benchmark import OpenVinoEngine


OUTPUT = ROOT / "benchmarks" / "results" / "openvino_fp32_thread_probe.json"
CASE_IDS = {
    "open_app_01", "open_app_05", "open_url_01", "open_url_06",
    "volume_up_01", "volume_up_08", "volume_down_01", "volume_down_08",
    "media_01", "media_08", "wait_01", "stop_01", "unknown_01", "unknown_06",
}


def main() -> int:
    cases = [case for case in load_cases() if case["id"] in CASE_IDS]
    if len(cases) != len(CASE_IDS):
        raise RuntimeError("Thread-probe case selection is incomplete")
    snapshot = resolve_snapshot(offline=True)
    runs = []
    for threads in (1, 2, 4):
        memory_before = system_memory_snapshot()
        process = psutil.Process()
        load_started = time.perf_counter()
        engine = OpenVinoEngine(snapshot, threads, "fp32", device="CPU")
        load_ms = (time.perf_counter() - load_started) * 1000.0
        engine.predict(cases[0]["transcript"], questions_for_case(cases[0]))
        latencies = []
        cpu_before = process.cpu_times()
        wall_started = time.perf_counter()
        for _ in range(2):
            for case in cases:
                started = time.perf_counter()
                engine.predict(case["transcript"], questions_for_case(case))
                latencies.append((time.perf_counter() - started) * 1000.0)
        wall_seconds = time.perf_counter() - wall_started
        cpu_after = process.cpu_times()
        cpu_seconds = (cpu_after.user - cpu_before.user) + (cpu_after.system - cpu_before.system)
        logical = psutil.cpu_count(logical=True) or 1
        one_core_percent = cpu_seconds / wall_seconds * 100.0
        runs.append({
            "threads": threads,
            "backend_load_ms": round(load_ms, 3),
            "sample_count": len(latencies),
            "latency_ms": {
                "p50": round(percentile(latencies, 50), 3),
                "p95": round(percentile(latencies, 95), 3),
                "mean": round(statistics.fmean(latencies), 3),
                "raw": [round(value, 3) for value in latencies],
            },
            "measured_wall_seconds": round(wall_seconds, 3),
            "average_process_cpu_percent_one_core_basis": round(one_core_percent, 3),
            "average_process_cpu_percent_machine_capacity": round(one_core_percent / logical, 3),
            "memory_before": memory_before,
            "memory_after": system_memory_snapshot(),
        })
        print(f"threads={threads}: p50={runs[-1]['latency_ms']['p50']} ms", flush=True)
        del engine

    result = {
        "schema_version": 1,
        "purpose": "Relative CPU thread-count probe for OpenVINO FP32; not a replacement for the frozen 70-case benchmark.",
        "backend": "openvino",
        "precision": "fp32",
        "device": "CPU",
        "case_ids": [case["id"] for case in cases],
        "rounds": 2,
        "configurations": runs,
        "responsiveness_guard": "Only 1, 2, and 4 inference threads were tested; 8 logical threads were intentionally not saturated.",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
