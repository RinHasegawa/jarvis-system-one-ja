from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "benchmarks" / "laya_cases.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "laya_baseline.json"
DEFAULT_SUMMARY = ROOT / "benchmarks" / "laya_baseline_summary.md"
DEFAULT_HF_HOME = ROOT / ".cache" / "huggingface"

MODEL_ID = "convaiinnovations/laya"
MODEL_REVISION = "c5d78730f3493e4fe16d61507ef4b78eef7318cf"
MODEL_SUBFOLDER = "multilingual"

ACTIONS = {
    "OPEN_APP": "Open or launch an installed application. Japanese: アプリを開く、起動する、立ち上げる。",
    "OPEN_URL": "Open or navigate to a known website or URL. Japanese: サイト、ページ、URLを開く、アクセスする。",
    "VOLUME_UP": "Increase system audio volume. Japanese: 音量を上げる、音を大きくする。",
    "VOLUME_DOWN": "Decrease system audio volume. Japanese: 音量を下げる、音を小さくする。",
    "MEDIA_PLAY_PAUSE": "Toggle media play or pause. Japanese: 再生、一時停止、動画や音楽を止める。",
    "WAIT": "Pause or defer execution but keep the session. Japanese: 待つ、待機、保留。",
    "STOP": "Cancel or abort the current pending operation. Japanese: 中止、キャンセル、取り消し。",
    "UNKNOWN": "No supported action is clearly requested, the request is incomplete, or it is outside the allowed actions.",
}

TARGETS = {
    "CHROME": "Google Chrome application; Chrome, クローム。",
    "EDGE": "Microsoft Edge application; Edge, エッジ。",
    "SPOTIFY": "Spotify application; Spotify, スポティファイ。",
    "NOTEPAD": "Windows Notepad application; Notepad, メモ帳, ノートパッド。",
    "VS_CODE": "Visual Studio Code application; VS Code, Visual Studio Code, コードエディタ。",
    "GOOGLE": "Google website, https://google.com, グーグルのページ。",
    "YOUTUBE": "YouTube website, YouTube, ユーチューブ。",
    "GITHUB": "GitHub website or generic GitHub page, GitHub, ギットハブ。",
    "LAYA_GITHUB": "The official Laya source repository on GitHub, LayaのGitHubまたは公式コード。",
    "NONE": "No specific allowlisted application or website target is stated or required.",
}

QUESTIONS = {
    "action": {
        "type": "choice",
        "instructions": "Classify the user's Japanese utterance into exactly one allowed computer-control action.",
        "criteria": ACTIONS,
    },
    "target": {
        "type": "choice",
        "instructions": "Choose the single allowlisted target explicitly named by the user. Choose NONE if no target is named or required.",
        "criteria": TARGETS,
    },
    "execute_now": {
        "type": "noul",
        "instructions": "Is the utterance complete and explicit enough to execute a supported action immediately?",
        "criteria": {
            "true": "a complete, explicit, supported command, including WAIT or STOP",
            "false": "incomplete, ambiguous, unsupported, informational, destructive, or requiring missing details",
        },
    },
    "risk": {
        "type": "choice",
        "instructions": "Classify the requested operation's execution risk.",
        "criteria": {
            "LOW": "reversible local V0 action, wait, stop, or harmless informational utterance",
            "HIGH": "destructive action, external communication, credential use, purchase, or other excluded high-impact operation",
        },
    },
}


class ResourceSampler:
    def __init__(self, process: psutil.Process, interval_seconds: float = 0.1) -> None:
        self.process = process
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.rss_bytes: list[int] = []
        self.system_cpu_percent: list[float] = []
        self.available_memory_bytes: list[int] = []

    def start(self) -> None:
        psutil.cpu_percent(interval=None)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.rss_bytes.append(self.process.memory_info().rss)
                self.system_cpu_percent.append(psutil.cpu_percent(interval=None))
                self.available_memory_bytes.append(psutil.virtual_memory().available)
            except (psutil.Error, OSError):
                pass
            self.stop_event.wait(self.interval_seconds)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if len(cases) < 50:
        raise ValueError(f"At least 50 cases are required; found {len(cases)}")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Case IDs must be unique")
    return cases


def render_summary(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    resource = result["resources"]
    accuracy = metrics["accuracy"]
    status = metrics["decision_rule"]["status"]
    recommendation = metrics["decision_rule"]["recommendation"]
    predictions = result["predictions"]
    action_order = [
        "OPEN_APP",
        "OPEN_URL",
        "VOLUME_UP",
        "VOLUME_DOWN",
        "MEDIA_PLAY_PAUSE",
        "WAIT",
        "STOP",
        "UNKNOWN",
    ]
    per_action_rows = []
    for expected in action_order:
        rows = [row for row in predictions if row["expected_action"] == expected]
        correct = sum(row["action_correct"] for row in rows)
        wrong_counts: dict[str, int] = {}
        for row in rows:
            if not row["action_correct"]:
                predicted = row["predicted_action"]
                wrong_counts[predicted] = wrong_counts.get(predicted, 0) + 1
        dominant_failure = max(wrong_counts, key=wrong_counts.get) if wrong_counts else "none"
        per_action_rows.append(
            f"| `{expected}` | {correct}/{len(rows)} | {correct / len(rows) * 100:.1f}% | `{dominant_failure}` |"
        )
    gate_passes = [
        row
        for row in predictions
        if row["action_probability"][row["predicted_action"]] >= 0.90
        and (
            not row["target_applicable"]
            or row["target_probability"][row["predicted_target"]] >= 0.90
        )
        and row["execute_now_probability"] >= 0.90
        and row["predicted_risk"] == "LOW"
    ]
    gate_correct = sum(row["action_correct"] for row in gate_passes)
    lines = [
        "# Laya Japanese feasibility benchmark",
        "",
        f"- Timestamp: `{result['timestamp_local']}`",
        f"- Official package: `laya=={result['software']['laya']}`",
        f"- Official model: `{result['model']['id']}` / `{result['model']['subfolder']}` at `{result['model']['revision']}`",
        f"- Device: `{result['model']['device']}`",
        f"- Cases: **{metrics['case_count']}** Japanese utterances",
        f"- Decision bundle: action + target + execute-now + risk in one Laya call",
        "",
        "## Result",
        "",
        f"**{status}** — {recommendation}",
        "",
        "| Metric | Measured value |",
        "|---|---:|",
        f"| Local cold model load | {metrics['cold_start']['model_load_ms']:.1f} ms |",
        f"| First inference after load | {metrics['cold_start']['first_inference_ms']:.1f} ms |",
        f"| Warm inference p50 | {metrics['latency_ms']['p50']:.1f} ms |",
        f"| Warm inference p95 | {metrics['latency_ms']['p95']:.1f} ms |",
        f"| Warm inference mean | {metrics['latency_ms']['mean']:.1f} ms |",
        f"| Action accuracy | {accuracy['action'] * 100:.1f}% ({accuracy['action_correct']}/{metrics['case_count']}) |",
        f"| Target accuracy, applicable cases | {accuracy['target_applicable'] * 100:.1f}% ({accuracy['target_applicable_correct']}/{accuracy['target_applicable_count']}) |",
        f"| Target accuracy, all cases | {accuracy['target_all'] * 100:.1f}% ({accuracy['target_all_correct']}/{metrics['case_count']}) |",
        f"| Execute-now accuracy at 0.5 | {accuracy['execute_now'] * 100:.1f}% |",
        f"| Risk accuracy | {accuracy['risk'] * 100:.1f}% |",
        f"| Peak process RSS | {resource['peak_process_rss_mib']:.1f} MiB |",
        f"| RSS increase after load | {resource['rss_increase_after_load_mib']:.1f} MiB |",
        f"| Average process CPU, one-core basis | {resource['average_process_cpu_percent_one_core_basis']:.1f}% |",
        f"| Average process CPU, machine capacity | {resource['average_process_cpu_percent_machine_capacity']:.1f}% |",
        f"| Average system CPU during measured cases | {resource['average_system_cpu_percent']:.1f}% |",
        "",
        "## Semantic behavior by expected action",
        "",
        "| Expected action | Correct | Accuracy | Dominant wrong prediction |",
        "|---|---:|---:|---|",
        *per_action_rows,
        "",
        f"At the proposed initial probability gate, {len(gate_passes)}/{metrics['case_count']} cases passed and "
        f"{gate_correct}/{metrics['case_count']} had a correct action. Consecutive partial-transcript stability "
        "was not tested because these are independent utterances.",
        "",
        "## Interpretation",
        "",
        "This is a closed-set semantic classification benchmark over Japanese text, not a speech-to-text benchmark. "
        "The official multilingual checkpoint is used without third-party quantized weights. STOP results are diagnostic only: "
        "the JARVIS design still requires deterministic emergency matching outside Laya.",
        "",
        "The peak process RSS and minimum available system memory should be reviewed for pressure on the 8 GB target. "
        "The raw per-case predictions, probabilities, latencies, and resource measurements are in "
        "`benchmarks/laya_baseline.json`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark official Laya on Japanese JARVIS V0 commands.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--hf-home", type=Path, default=DEFAULT_HF_HOME)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--torch-threads", type=int, default=0, help="0 preserves the PyTorch default.")
    args = parser.parse_args()

    args.hf_home.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(args.hf_home.resolve())
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"

    from huggingface_hub import snapshot_download

    snapshot_path = snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        allow_patterns=[f"{MODEL_SUBFOLDER}/*"],
        local_files_only=args.offline,
    )
    if args.prepare_only:
        print(json.dumps({"snapshot_path": snapshot_path, "revision": MODEL_REVISION}, ensure_ascii=False))
        return 0

    import laya
    import torch

    cases = load_cases(args.cases)
    if args.torch_threads > 0:
        torch.set_num_threads(args.torch_threads)

    process = psutil.Process()
    sampler = ResourceSampler(process)
    rss_before_load = process.memory_info().rss
    sampler.start()

    load_started = time.perf_counter()
    agent = laya.load(snapshot_path, device="cpu", subfolder=MODEL_SUBFOLDER)
    model_load_ms = (time.perf_counter() - load_started) * 1000.0
    rss_after_load = process.memory_info().rss

    first_started = time.perf_counter()
    agent.predict("Chromeを開いて", QUESTIONS)
    first_inference_ms = (time.perf_counter() - first_started) * 1000.0

    cpu_before = process.cpu_times()
    measured_started = time.perf_counter()
    predictions: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        output = agent.predict(case["transcript"], QUESTIONS)
        latency_ms = (time.perf_counter() - started) * 1000.0
        answers = output["answers"]
        action = answers["action"]
        target = answers["target"]
        execute_now = answers["execute_now"]
        risk = answers["risk"]
        execute_probability = float(execute_now["noul"])
        row = {
            **case,
            "latency_ms": round(latency_ms, 3),
            "predicted_action": action["choice"],
            "action_probability": action["probabilities"],
            "action_confidence": action["confidence"],
            "predicted_target": target["choice"],
            "target_probability": target["probabilities"],
            "target_confidence": target["confidence"],
            "execute_now_probability": execute_probability,
            "predicted_execute_now": execute_probability >= 0.5,
            "predicted_risk": risk["choice"],
            "risk_probability": risk["probabilities"],
            "risk_confidence": risk["confidence"],
            "action_correct": action["choice"] == case["expected_action"],
            "target_correct": target["choice"] == case["expected_target"],
            "execute_now_correct": (execute_probability >= 0.5) == case["expected_execute_now"],
            "risk_correct": risk["choice"] == case["expected_risk"],
            "usage": output.get("usage", {}),
        }
        predictions.append(row)
        print(
            f"{case['id']}: {latency_ms:.1f} ms | "
            f"action={row['predicted_action']} target={row['predicted_target']}",
            flush=True,
        )

    measured_wall_seconds = time.perf_counter() - measured_started
    cpu_after = process.cpu_times()
    sampler.stop()

    latencies = [row["latency_ms"] for row in predictions]
    action_correct = sum(row["action_correct"] for row in predictions)
    target_all_correct = sum(row["target_correct"] for row in predictions)
    applicable = [row for row in predictions if row["target_applicable"]]
    target_applicable_correct = sum(row["target_correct"] for row in applicable)
    execute_correct = sum(row["execute_now_correct"] for row in predictions)
    risk_correct = sum(row["risk_correct"] for row in predictions)
    case_count = len(predictions)

    process_cpu_seconds = (
        (cpu_after.user - cpu_before.user) + (cpu_after.system - cpu_before.system)
    )
    logical_cpus = psutil.cpu_count(logical=True) or 1
    one_core_cpu_percent = process_cpu_seconds / measured_wall_seconds * 100.0
    machine_cpu_percent = one_core_cpu_percent / logical_cpus
    p50 = percentile(latencies, 50)
    if p50 <= 250.0:
        status = "ACCEPTABLE FOR V0"
        recommendation = "The initial p50 latency rule passes; proceed only after reviewing semantic accuracy."
    elif p50 <= 500.0:
        status = "OPTIMIZATION REQUIRED"
        recommendation = "Investigate lightweight CPU tuning before application work."
    else:
        status = "NOT YET VIABLE"
        recommendation = "Investigate first-party ONNX/OpenVINO export and INT8 quantization before application work."

    result = {
        "schema_version": 1,
        "timestamp_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "subfolder": MODEL_SUBFOLDER,
            "snapshot_path": str(snapshot_path),
            "device": str(agent.device),
            "third_party_quantization_used": False,
        },
        "software": {
            "python": platform.python_version(),
            "laya": package_version("laya"),
            "torch": package_version("torch"),
            "transformers": package_version("transformers"),
            "huggingface_hub": package_version("huggingface-hub"),
            "psutil": package_version("psutil"),
            "platform": platform.platform(),
            "torch_num_threads": torch.get_num_threads(),
            "torch_num_interop_threads": torch.get_num_interop_threads(),
        },
        "benchmark": {
            "cases_file": str(args.cases.resolve()),
            "question_ids": list(QUESTIONS),
            "notes": [
                "Closed-set Japanese text semantic benchmark; STT is not measured.",
                "Bilingual option descriptions are supplied to the official multilingual Laya checkpoint.",
                "STOP classification is diagnostic; production emergency matching must bypass Laya.",
            ],
        },
        "metrics": {
            "case_count": case_count,
            "cold_start": {
                "model_load_ms": round(model_load_ms, 3),
                "first_inference_ms": round(first_inference_ms, 3),
                "total_to_first_result_ms": round(model_load_ms + first_inference_ms, 3),
            },
            "latency_ms": {
                "min": round(min(latencies), 3),
                "p50": round(p50, 3),
                "p95": round(percentile(latencies, 95), 3),
                "max": round(max(latencies), 3),
                "mean": round(statistics.fmean(latencies), 3),
            },
            "accuracy": {
                "action": action_correct / case_count,
                "action_correct": action_correct,
                "target_applicable": target_applicable_correct / len(applicable),
                "target_applicable_correct": target_applicable_correct,
                "target_applicable_count": len(applicable),
                "target_all": target_all_correct / case_count,
                "target_all_correct": target_all_correct,
                "execute_now": execute_correct / case_count,
                "execute_now_correct": execute_correct,
                "risk": risk_correct / case_count,
                "risk_correct": risk_correct,
            },
            "decision_rule": {
                "thresholds_ms": {"acceptable_max": 250, "lightweight_optimization_max": 500},
                "status": status,
                "recommendation": recommendation,
            },
        },
        "resources": {
            "logical_cpu_count": logical_cpus,
            "physical_cpu_count": psutil.cpu_count(logical=False),
            "total_ram_mib": round(psutil.virtual_memory().total / 1024**2, 3),
            "rss_before_load_mib": round(rss_before_load / 1024**2, 3),
            "rss_after_load_mib": round(rss_after_load / 1024**2, 3),
            "rss_increase_after_load_mib": round((rss_after_load - rss_before_load) / 1024**2, 3),
            "peak_process_rss_mib": round(max(sampler.rss_bytes, default=rss_after_load) / 1024**2, 3),
            "minimum_available_system_memory_mib": round(min(sampler.available_memory_bytes, default=0) / 1024**2, 3),
            "measured_wall_seconds": round(measured_wall_seconds, 3),
            "process_cpu_seconds": round(process_cpu_seconds, 3),
            "average_process_cpu_percent_one_core_basis": round(one_core_cpu_percent, 3),
            "average_process_cpu_percent_machine_capacity": round(machine_cpu_percent, 3),
            "average_system_cpu_percent": round(statistics.fmean(sampler.system_cpu_percent), 3) if sampler.system_cpu_percent else None,
        },
        "predictions": predictions,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(render_summary(result), encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
