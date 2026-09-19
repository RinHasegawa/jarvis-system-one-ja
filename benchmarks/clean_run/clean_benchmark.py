from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "benchmarks" / "phase_2_5" / "run_laya_benchmark.py"
REFERENCE = ROOT / "benchmarks" / "results" / "laya_pt_fp32_action_target_v2.json"
CLEAN_DIR = ROOT / "benchmarks" / "clean_run"
ENVIRONMENT = CLEAN_DIR / "clean_run_environment.json"

BACKENDS = (
    {
        "id": "onnx_fp32",
        "label": "ONNX Runtime FP32 CPU",
        "backend": "onnx",
        "precision": "fp32",
        "threads": 4,
        "result": CLEAN_DIR / "laya_onnx_fp32_clean.json",
        "log": CLEAN_DIR / "laya_onnx_fp32_clean.log",
    },
    {
        "id": "openvino_fp32",
        "label": "OpenVINO FP32 CPU (4 threads)",
        "backend": "openvino",
        "precision": "fp32",
        "threads": 4,
        "result": CLEAN_DIR / "laya_openvino_fp32_clean.json",
        "log": CLEAN_DIR / "laya_openvino_fp32_clean.log",
    },
)


def process_summary(limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            rows.append(
                {
                    "pid": info["pid"],
                    "name": info["name"],
                    "rss_mib": round(info["memory_info"].rss / 1024**2, 3),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return sorted(rows, key=lambda row: row["rss_mib"], reverse=True)[:limit]


def snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    pagefile = psutil.swap_memory()
    return {
        "timestamp_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_ram_mib": round(memory.total / 1024**2, 3),
        "available_ram_mib": round(memory.available / 1024**2, 3),
        "ram_percent": memory.percent,
        "pagefile_total_mib": round(pagefile.total / 1024**2, 3),
        "pagefile_used_mib": round(pagefile.used / 1024**2, 3),
        "pagefile_percent": pagefile.percent,
        "cpu_percent": psutil.cpu_percent(interval=1.0),
        "top_processes_by_rss": process_summary(),
    }


def write_environment(payload: dict[str, Any]) -> None:
    ENVIRONMENT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_and_summarize_result(path: Path, expected_backend: str) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("benchmark_mode") != "action_target_v2":
        raise ValueError(f"Unexpected benchmark mode in {path}")
    experiment = result.get("experiment", {})
    if experiment.get("frozen_case_count") != 70 or len(result.get("predictions", [])) != 70:
        raise ValueError(f"Expected exactly 70 frozen cases in {path}")
    model = result.get("model", {})
    backend_names = {"onnx": "onnxruntime", "openvino": "openvino"}
    if model.get("backend") != backend_names[expected_backend] or model.get("precision") != "fp32":
        raise ValueError(f"Unexpected backend or precision in {path}")
    metrics = result["metrics"]
    latency = result["latency_ms"]
    resources = result["resources"]
    return {
        "action_accuracy": metrics["semantic_action_accuracy"],
        "target_accuracy": metrics["target_accuracy"],
        "latency_ms": {
            "p50": latency["p50"],
            "p95": latency["p95"],
            "mean": latency["mean"],
        },
        "peak_process_rss_mib": resources["peak_process_rss_mib"],
        "available_ram_before_mib": resources["before"]["available_ram_mib"],
        "available_ram_after_mib": resources["after"]["available_ram_mib"],
        "pagefile_before": {
            "used_mib": resources["before"]["pagefile_used_mib"],
            "percent": resources["before"]["pagefile_percent"],
        },
        "pagefile_after": {
            "used_mib": resources["after"]["pagefile_used_mib"],
            "percent": resources["after"]["pagefile_percent"],
        },
        "average_system_cpu_percent": resources["average_system_cpu_percent"],
        "average_process_cpu_percent_machine_capacity": resources[
            "average_process_cpu_percent_machine_capacity"
        ],
    }


def main() -> int:
    if not RUNNER.exists():
        raise FileNotFoundError(f"Benchmark runner is missing: {RUNNER}")
    if not REFERENCE.exists():
        raise FileNotFoundError(f"Reference benchmark is missing: {REFERENCE}")

    environment: dict[str, Any] = {
        "schema_version": 2,
        "purpose": "Manual clean-environment comparison; this script never closes Codex or other applications.",
        "benchmark_mode": "action_target_v2",
        "frozen_case_count": 70,
        "execution_order": [backend["id"] for backend in BACKENDS],
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "physical_cpu_count": psutil.cpu_count(logical=False),
            "logical_cpu_count": psutil.cpu_count(logical=True),
        },
        "suite_before": snapshot(),
        "runs": [],
        "suite_after": None,
        "overall_exit_code": None,
    }
    write_environment(environment)

    child_environment = os.environ.copy()
    child_environment["PYTHONIOENCODING"] = "utf-8"
    child_environment["OPENVINO_TELEMETRY_LEVEL"] = "0"
    overall_exit_code = 0

    for backend in BACKENDS:
        run_record: dict[str, Any] = {
            "id": backend["id"],
            "label": backend["label"],
            "backend": backend["backend"],
            "precision": backend["precision"],
            "threads": backend["threads"],
            "before": snapshot(),
            "after": None,
            "exit_code": None,
            "result_file": str(backend["result"].resolve()),
            "log_file": str(backend["log"].resolve()),
            "result_written_this_run": False,
            "summary": None,
            "validation_error": None,
        }
        environment["runs"].append(run_record)
        write_environment(environment)

        command = [
            sys.executable,
            str(RUNNER),
            "--backend",
            backend["backend"],
            "--precision",
            backend["precision"],
            "--threads",
            str(backend["threads"]),
            "--reference",
            str(REFERENCE),
            "--output",
            str(backend["result"]),
        ]
        run_started_ns = time.time_ns()
        with backend["log"].open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=child_environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run_record["exit_code"] = completed.returncode
        run_record["after"] = snapshot()
        was_written = backend["result"].exists() and backend["result"].stat().st_mtime_ns >= run_started_ns
        run_record["result_written_this_run"] = was_written
        if completed.returncode == 0 and was_written:
            try:
                run_record["summary"] = validate_and_summarize_result(
                    backend["result"], backend["backend"]
                )
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                run_record["validation_error"] = repr(exc)
                overall_exit_code = overall_exit_code or 3
        else:
            overall_exit_code = overall_exit_code or completed.returncode or 2
            if completed.returncode == 0 and not was_written:
                run_record["validation_error"] = "The benchmark exited successfully but did not write a fresh result file."
        write_environment(environment)
        print(
            f"{backend['label']}: exit={completed.returncode}, result={backend['result']}",
            flush=True,
        )

    environment["suite_after"] = snapshot()
    environment["overall_exit_code"] = overall_exit_code
    write_environment(environment)
    print(f"Environment: {ENVIRONMENT}")
    return overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
