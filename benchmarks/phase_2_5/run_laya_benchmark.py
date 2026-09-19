from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from common import (
    ACTION_OPTIONS,
    ARTIFACTS_DIR,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SUBFOLDER,
    RESULTS_DIR,
    ResourceSampler,
    classification_metrics,
    compare_to_reference,
    decode_outputs,
    deterministic_stop,
    load_cases,
    load_model_config,
    load_tokenizer,
    model_dir,
    numpy_inputs,
    percentile,
    prepare_inputs,
    process_cpu_summary,
    questions_for_case,
    resolve_snapshot,
    sha256,
    system_memory_snapshot,
)


class PyTorchEngine:
    backend = "pytorch"
    precision = "fp32"

    def __init__(self, snapshot: Path, threads: int) -> None:
        import laya
        import torch

        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        self.torch = torch
        self.agent = laya.load(snapshot, device="cpu", subfolder=MODEL_SUBFOLDER)
        self.artifact_path = model_dir(snapshot) / "model.safetensors"
        self.artifact_files = [self.artifact_path]

    def predict(self, state: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return self.agent.predict(state, questions)

    def metadata(self) -> dict[str, Any]:
        return {
            "torch_num_threads": self.torch.get_num_threads(),
            "torch_num_interop_threads": self.torch.get_num_interop_threads(),
            "torch_cpu_capability": self.torch.backends.cpu.get_cpu_capability(),
        }


class OnnxEngine:
    backend = "onnxruntime"

    def __init__(self, snapshot: Path, threads: int, precision: str) -> None:
        import onnxruntime as ort

        self.precision = precision
        self.config = load_model_config(snapshot)
        self.tokenizer = load_tokenizer(snapshot)
        filename = "laya_action_target_v2_fp32.onnx" if precision == "fp32" else "laya_action_target_v2_int8.onnx"
        self.artifact_path = ARTIFACTS_DIR / filename
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"Missing ONNX artifact: {self.artifact_path}")
        external_data = Path(str(self.artifact_path) + ".data")
        self.artifact_files = [self.artifact_path] + ([external_data] if external_data.exists() else [])
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(self.artifact_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.threads = threads

    def predict(self, state: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        batch = prepare_inputs(self.tokenizer, self.config, state, questions)
        logits, act = self.session.run(["logits", "act"], numpy_inputs(batch))
        return decode_outputs(self.config, questions, logits, act)

    def metadata(self) -> dict[str, Any]:
        import onnxruntime as ort

        return {
            "onnxruntime_version": ort.__version__,
            "providers": self.session.get_providers(),
            "intra_op_threads": self.threads,
            "inter_op_threads": 1,
        }


class OpenVinoEngine:
    backend = "openvino"

    def __init__(self, snapshot: Path, threads: int, precision: str, device: str = "CPU") -> None:
        import openvino as ov

        self.precision = precision
        self.config = load_model_config(snapshot)
        self.tokenizer = load_tokenizer(snapshot)
        suffix = "fp32" if precision == "fp32" else "int8"
        self.artifact_path = ARTIFACTS_DIR / f"laya_action_target_v2_openvino_{suffix}.xml"
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"Missing OpenVINO artifact: {self.artifact_path}")
        self.artifact_files = [self.artifact_path, self.artifact_path.with_suffix(".bin")]
        self.core = ov.Core()
        compile_config = {
            "PERFORMANCE_HINT": "LATENCY",
            "INFERENCE_NUM_THREADS": str(threads),
            "NUM_STREAMS": "1",
        }
        self.compiled = self.core.compile_model(str(self.artifact_path), device, compile_config)
        self.threads = threads
        self.device = device

    def predict(self, state: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        batch = prepare_inputs(self.tokenizer, self.config, state, questions)
        output = self.compiled(numpy_inputs(batch))
        logits = output[self.compiled.output("logits")]
        act = output[self.compiled.output("act")]
        return decode_outputs(self.config, questions, logits, act)

    def metadata(self) -> dict[str, Any]:
        import openvino as ov

        return {
            "openvino_version": ov.__version__,
            "device": self.device,
            "inference_num_threads": self.threads,
            "num_streams": 1,
            "available_devices": self.core.available_devices,
        }


def installed_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def create_engine(backend: str, precision: str, snapshot: Path, threads: int, device: str):
    if backend == "pt":
        if precision != "fp32":
            raise ValueError("PyTorch benchmark supports the official FP32 checkpoint only")
        return PyTorchEngine(snapshot, threads)
    if backend == "onnx":
        return OnnxEngine(snapshot, threads, precision)
    if backend == "openvino":
        return OpenVinoEngine(snapshot, threads, precision, device=device)
    raise ValueError(backend)


def default_output(backend: str, precision: str) -> Path:
    if backend == "pt":
        return RESULTS_DIR / "laya_pt_fp32_action_target_v2.json"
    return RESULTS_DIR / f"laya_{backend}_{precision}.json"


def run(args: argparse.Namespace) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    snapshot = resolve_snapshot(offline=True)
    memory_before = system_memory_snapshot()
    process = psutil.Process()
    rss_before = process.memory_info().rss
    sampler = ResourceSampler()
    sampler.start()

    load_started = time.perf_counter()
    engine = create_engine(args.backend, args.precision, snapshot, args.threads, args.device)
    load_ms = (time.perf_counter() - load_started) * 1000.0
    rss_after_load = process.memory_info().rss

    warmup_case = next(case for case in cases if case["target_applicable"])
    first_started = time.perf_counter()
    engine.predict(warmup_case["transcript"], questions_for_case(warmup_case))
    first_inference_ms = (time.perf_counter() - first_started) * 1000.0

    predictions: list[dict[str, Any]] = []
    cpu_before = process.cpu_times()
    measured_started = time.perf_counter()
    for case in cases:
        questions = questions_for_case(case)
        started = time.perf_counter()
        response = engine.predict(case["transcript"], questions)
        latency_ms = (time.perf_counter() - started) * 1000.0
        action = response["answers"]["action"]
        target = response["answers"].get("target")
        row = {
            "id": case["id"],
            "transcript": case["transcript"],
            "expected_action": case["expected_action"],
            "expected_target": case["expected_target"],
            "target_applicable": case["target_applicable"],
            "predicted_action": action["choice"],
            "action_probabilities": action["probabilities"],
            "action_top_probability": action["probabilities"][action["choice"]],
            "action_entropy_confidence": action.get("confidence"),
            "predicted_target": target["choice"] if target else None,
            "target_probabilities": target["probabilities"] if target else None,
            "target_top_probability": target["probabilities"][target["choice"]] if target else None,
            "target_entropy_confidence": target.get("confidence") if target else None,
            "semantic_action_scored": case["expected_action"] != "STOP",
            "semantic_action_correct": action["choice"] == case["expected_action"],
            "target_correct": target["choice"] == case["expected_target"] if target else None,
            "deterministic_stop_match": deterministic_stop(case["transcript"]),
            "latency_ms": round(latency_ms, 3),
        }
        predictions.append(row)
        print(
            f"{case['id']}: {latency_ms:.1f} ms action={row['predicted_action']} "
            f"target={row['predicted_target']}",
            flush=True,
        )

    measured_wall = time.perf_counter() - measured_started
    cpu_after = process.cpu_times()
    sampler.stop()
    memory_after = system_memory_snapshot()
    latencies = [row["latency_ms"] for row in predictions]
    metrics = classification_metrics(predictions)
    reference_path = args.reference if args.reference and args.reference.exists() else None
    comparison = compare_to_reference(predictions, reference_path)

    artifact = engine.artifact_path
    artifact_files = [
        {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in engine.artifact_files
    ]
    result = {
        "schema_version": 2,
        "benchmark_mode": "action_target_v2",
        "timestamp_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "subfolder": MODEL_SUBFOLDER,
            "backend": engine.backend,
            "precision": engine.precision,
            "device": args.device,
            "artifact_path": str(artifact.resolve()),
            "artifact_bytes": sum(item["bytes"] for item in artifact_files),
            "artifact_sha256": sha256(artifact),
            "artifact_files": artifact_files,
            "third_party_converted_weights_used": False,
        },
        "experiment": {
            "threads": args.threads,
            "action_options": list(ACTION_OPTIONS),
            "target_question_only_when_explicit": True,
            "frozen_case_count": len(cases),
            "semantic_action_count": sum(case["expected_action"] != "STOP" for case in cases),
            "deterministic_stop_count": sum(case["expected_action"] == "STOP" for case in cases),
            "policy_note": "STOP labels are preserved and evaluated through deterministic matching; STOP is intentionally absent from Laya action options.",
        },
        "software": {
            "python": platform.python_version(),
            "laya": installed_version("laya"),
            "torch": installed_version("torch"),
            "onnxruntime": installed_version("onnxruntime"),
            "openvino": installed_version("openvino"),
            "nncf": installed_version("nncf"),
            **engine.metadata(),
        },
        "cold_start": {
            "backend_load_ms": round(load_ms, 3),
            "first_inference_ms": round(first_inference_ms, 3),
            "total_to_first_result_ms": round(load_ms + first_inference_ms, 3),
        },
        "latency_ms": {
            "min": round(min(latencies), 3),
            "p50": round(percentile(latencies, 50), 3),
            "p95": round(percentile(latencies, 95), 3),
            "max": round(max(latencies), 3),
            "mean": round(statistics.fmean(latencies), 3),
        },
        "metrics": metrics,
        "reference_comparison": comparison,
        "resources": {
            "before": memory_before,
            "after": memory_after,
            "rss_before_load_mib": round(rss_before / 1024**2, 3),
            "rss_after_load_mib": round(rss_after_load / 1024**2, 3),
            "peak_process_rss_mib": round(max(sampler.rss_bytes, default=rss_after_load) / 1024**2, 3),
            "minimum_available_system_ram_mib": round(min(sampler.available_bytes, default=0) / 1024**2, 3),
            "average_system_cpu_percent": round(statistics.fmean(sampler.system_cpu_percent), 3) if sampler.system_cpu_percent else None,
            "measured_wall_seconds": round(measured_wall, 3),
            **process_cpu_summary(cpu_before, cpu_after, measured_wall),
        },
        "predictions": predictions,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS Phase 2.5 Laya action_target_v2 benchmark")
    parser.add_argument("--backend", choices=["pt", "onnx", "openvino"], default="pt")
    parser.add_argument("--precision", choices=["fp32", "int8"], default="fp32")
    parser.add_argument("--threads", type=int, choices=[1, 2, 4], default=4)
    parser.add_argument("--device", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    output = args.output or default_output(args.backend, args.precision)
    result = run(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "latency_ms": result["latency_ms"], "metrics": result["metrics"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
