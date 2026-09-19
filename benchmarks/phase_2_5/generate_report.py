from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import ROOT


RESULTS = ROOT / "benchmarks" / "results"
REPORT = ROOT / "benchmarks" / "phase_2_5_report.md"
# This generator preserves the original normal-environment local matrix. The
# current public authority additionally includes completed clean runs and the
# Jev 1.13.0 direct-API result in docs/benchmark_report_ja.md.
BASELINE = ROOT / "benchmarks" / "laya_baseline.json"
RESULT_FILES = [
    ("PyTorch FP32", "laya_pt_fp32_action_target_v2.json"),
    ("ONNX Runtime FP32", "laya_onnx_fp32.json"),
    ("OpenVINO FP32", "laya_openvino_fp32.json"),
    ("ONNX Runtime INT8", "laya_onnx_int8.json"),
    ("OpenVINO INT8", "laya_openvino_int8.json"),
]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def number(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> int:
    baseline = load(BASELINE)
    results = [(label, load(RESULTS / filename), filename) for label, filename in RESULT_FILES]
    thread_path = RESULTS / "openvino_fp32_thread_probe.json"
    thread_probe = load(thread_path) if thread_path.exists() else None
    pt = results[0][1]

    lines = [
        "# JARVIS Phase 2.5 — Laya optimization and comparison preparation",
        "",
        "## Executive result",
        "",
        "The simplified `action_target_v2` task improves semantic ACTION accuracy from the old multi-question baseline's "
        f"{baseline['metrics']['accuracy']['action'] * 100:.1f}% to {pt['metrics']['semantic_action_accuracy'] * 100:.1f}%, "
        "but remains far below the 95% acceptance target. Runtime conversion helps substantially, yet no tested configuration "
        "reaches the 250 ms warm-p50 target in this normal desktop environment.",
        "",
        "ONNX Runtime FP32 is the current best-balanced candidate: it exactly preserves PyTorch predictions, stays below the "
        "preferred 1.5 GiB process-RSS ceiling in this run, and improves p50 latency. OpenVINO FP32 has the fastest p50 among "
        "accuracy-preserving configurations but uses materially more RAM. Both INT8 variants change semantics; OpenVINO INT8 "
        "collapses to uniform probabilities and is invalid for use.",
        "",
        "Completed clean-run and Jev direct-API results are summarized in `docs/benchmark_report_ja.md`.",
        "",
        "## Experimental controls",
        "",
        "- The original 70 Japanese cases and labels are unchanged.",
        "- The original Phase 0-2 result remains `benchmarks/laya_baseline.json` and was not overwritten.",
        "- Laya receives only ACTION plus TARGET when an explicit target is present.",
        "- `STOP` remains in the frozen labels but is detected and scored deterministically outside Laya (6/6 in every run).",
        "- All converted artifacts originate from the pinned official `convaiinnovations/laya` multilingual checkpoint at revision "
        f"`{pt['model']['revision']}`; no third-party quantized weights were used.",
        "- The five local backends use the same questions, ground truth, scoring, and 70-case ordering.",
        "",
        "## Local backend matrix (normal desktop environment)",
        "",
        "| Backend | ACTION accuracy | TARGET accuracy | p50 (ms) | p95 (ms) | Mean (ms) | Peak RSS (MiB) | Cost | Notes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    notes = {
        "PyTorch FP32": "Reference for action_target_v2",
        "ONNX Runtime FP32": "100% prediction agreement with PyTorch; current best balance",
        "OpenVINO FP32": "100% prediction agreement; fastest accuracy-preserving p50; higher RAM",
        "ONNX Runtime INT8": "Faster/smaller, but ACTION accuracy and agreement regress",
        "OpenVINO INT8": "Invalid: probabilities become uniform and argmax collapses to OPEN_APP",
    }
    for label, result, _ in results:
        metrics = result["metrics"]
        latency = result["latency_ms"]
        resources = result["resources"]
        lines.append(
            f"| {label} | {pct(metrics['semantic_action_accuracy'])} | {pct(metrics['target_accuracy'])} | "
            f"{number(latency['p50'])} | {number(latency['p95'])} | {number(latency['mean'])} | "
            f"{number(resources['peak_process_rss_mib'])} | ¥0 local | {notes[label]} |"
        )

    lines += [
        "",
        "> These runs occurred sequentially in a memory-constrained normal desktop session. Available RAM and paging differed "
        "between runs, so small backend timing differences are provisional until the manual clean run is complete.",
        "",
        "### Cold start, environment, and reference agreement",
        "",
        "| Backend | Load (ms) | First inference (ms) | RAM before/after (MiB available) | ACTION agreement | Max ACTION probability delta | TARGET agreement |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, result, _ in results:
        cold = result["cold_start"]
        resource = result["resources"]
        comparison = result.get("reference_comparison")
        lines.append(
            f"| {label} | {number(cold['backend_load_ms'])} | {number(cold['first_inference_ms'])} | "
            f"{number(resource['before']['available_ram_mib'])} / {number(resource['after']['available_ram_mib'])} | "
            f"{pct(comparison['action_prediction_agreement']) if comparison else 'reference'} | "
            f"{number(comparison['action_probability_max_absolute_difference'], 7) if comparison else 'reference'} | "
            f"{pct(comparison['target_prediction_agreement']) if comparison else 'reference'} |"
        )

    lines += [
        "",
        "## Semantic quality",
        "",
        f"The simplified PyTorch reference gets {pt['metrics']['semantic_action_correct']}/{pt['metrics']['semantic_action_count']} "
        f"semantic ACTION cases ({pct(pt['metrics']['semantic_action_accuracy'])}) and "
        f"{pt['metrics']['target_correct']}/{pt['metrics']['target_count']} explicit TARGET cases "
        f"({pct(pt['metrics']['target_accuracy'])}). TARGET narrowly misses 95%; ACTION misses by a wide margin.",
        "",
        "| Expected ACTION | Correct | Accuracy |",
        "|---|---:|---:|",
    ]
    for label, item in pt["metrics"]["per_class"].items():
        lines.append(f"| `{label}` | {item['correct']}/{item['count']} | {pct(item['accuracy'])} |")

    lines += [
        "",
        "The chief semantic weaknesses are `OPEN_APP` and `OPEN_URL`; simplifying the task removes the original broad WAIT bias "
        "but does not make the checkpoint reliable enough for real computer control. Deterministic STOP matching remains 6/6 and "
        "also avoids confusing media pause with emergency cancellation.",
        "",
        "## Runtime performance",
        "",
        "Against the action_target_v2 PyTorch reference, ONNX Runtime FP32 reduces p50 by "
        f"{(1 - results[1][1]['latency_ms']['p50'] / pt['latency_ms']['p50']) * 100:.1f}% and OpenVINO FP32 by "
        f"{(1 - results[2][1]['latency_ms']['p50'] / pt['latency_ms']['p50']) * 100:.1f}%. "
        "Neither approaches 250 ms. High p95 values and variable per-case times are consistent with current system memory pressure, "
        "but only the clean run can quantify how much of the tail is environmental.",
        "",
        "## Memory pressure and environment effects",
        "",
        f"Peak process RSS ranges from {min(r['resources']['peak_process_rss_mib'] for _, r, _ in results):.1f} to "
        f"{max(r['resources']['peak_process_rss_mib'] for _, r, _ in results):.1f} MiB. ONNX Runtime FP32 measured "
        f"{results[1][1]['resources']['peak_process_rss_mib']:.1f} MiB, while OpenVINO FP32 measured "
        f"{results[2][1]['resources']['peak_process_rss_mib']:.1f} MiB. The latter ended with only "
        f"{results[2][1]['resources']['after']['available_ram_mib']:.1f} MiB available RAM, so its latency tail must not be "
        "treated as a clean backend-only measurement.",
        "",
        "The completed manual launcher recorded total/available RAM, pagefile use, CPU utilization, and largest processes before "
        "and after each run. See the clean-run JSON files and `docs/benchmark_report_ja.md` for the current public interpretation.",
        "",
        "## Quantization effects",
        "",
        f"ONNX INT8 lowers p50 to {results[3][1]['latency_ms']['p50']:.1f} ms and peak RSS to "
        f"{results[3][1]['resources']['peak_process_rss_mib']:.1f} MiB, but ACTION accuracy falls to "
        f"{pct(results[3][1]['metrics']['semantic_action_accuracy'])} and ACTION prediction agreement to "
        f"{pct(results[3][1]['reference_comparison']['action_prediction_agreement'])}. OpenVINO NNCF INT8 uses 32 separate "
        "calibration utterances (no evaluation cases), but returns uniform choice probabilities and therefore fails semantic "
        "validation. Neither INT8 artifact is a JARVIS candidate.",
        "",
        "## Calibration",
        "",
        "Reliability bins group predictions by top-choice probability and compare mean confidence with observed accuracy. Brier score "
        "measures squared probability error across all choices (lower is better). Expected Calibration Error (ECE) is the "
        "sample-weighted gap between bin confidence and bin accuracy (lower is better). A probability in [0, 1] is not by itself "
        "evidence of calibration.",
        "",
        "| Backend | ACTION Brier | ACTION ECE | TARGET Brier | TARGET ECE |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, result, _ in results:
        calibration = result["metrics"]["calibration"]
        lines.append(
            f"| {label} | {number(calibration['action']['brier_score'], 4)} | "
            f"{number(calibration['action']['ece'], 4)} | {number(calibration['target']['brier_score'], 4)} | "
            f"{number(calibration['target']['ece'], 4)} |"
        )

    lines += ["", "## CPU thread probe"]
    if thread_probe:
        lines += [
            "",
            "The probe repeats a fixed 14-case balanced subset twice. It is a relative scheduling test, not a replacement for the "
            "full 70-case scores. Eight logical threads were intentionally not saturated so the desktop remains responsive.",
            "",
            "| OpenVINO FP32 threads | Samples | p50 (ms) | p95 (ms) | Mean (ms) | Machine CPU |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for run in thread_probe["configurations"]:
            lines.append(
                f"| {run['threads']} | {run['sample_count']} | {number(run['latency_ms']['p50'])} | "
                f"{number(run['latency_ms']['p95'])} | {number(run['latency_ms']['mean'])} | "
                f"{number(run['average_process_cpu_percent_machine_capacity'])}% |"
            )
        lines += [
            "",
            "OpenVINO detects both `CPU` and Intel `GPU`. The optional GPU full benchmark was not run in this already "
            "memory-pressured session because the integrated GPU shares system RAM; no claim is made that CPU or GPU is faster.",
        ]
    else:
        lines += ["", "Thread-probe result was not available when this report was generated."]

    lines += [
        "",
        "## Jev fair-comparison status",
        "",
        "The canonical Jev result is `benchmarks/clean_run/jev_typesafe_direct_1_13_0.json`: Jev 1.13.0 direct API, 70/70 "
        "successful requests, ACTION 61/64 (95.3125%), TARGET 25/25 (100%), p50 557.695 ms, p95 645.263 ms. Jev latency is "
        "full request-to-usable-decision time over the network and must not be described as equivalent to local model-only inference.",
        "",
        "## Suitability for JARVIS real-time control",
        "",
        "No tested Laya configuration is ready for real-time control: FP32 conversions improve runtime without changing the "
        "semantic shortfall, while quantization further harms semantics. The completed clean run confirms the local memory-latency "
        "trade-off, and the same-case Jev result meets the fixed-set accuracy target. Any backend decision must still consider "
        "keeping network latency/cost and local privacy/offline operation explicit.",
        "",
        "## Pending manual steps and blockers",
        "",
        "1. Review both completed FP32 result JSON files with `clean_run_environment.json`.",
        "2. Treat `jev_typesafe_direct_1_13_0.json` as the Jev authority; do not substitute the non-canonical Vercel attempt.",
        "3. Do not implement STT or Windows actions until the semantic-decision backend is selected.",
        "",
        "## Result files",
        "",
    ]
    for _, _, filename in results:
        lines.append(f"- `benchmarks/results/{filename}`")
    lines += [
        "- `benchmarks/results/openvino_fp32_thread_probe.json`",
        "- `benchmarks/clean_run/laya_onnx_fp32_clean.json`",
        "- `benchmarks/clean_run/laya_openvino_fp32_clean.json`",
        "- `benchmarks/clean_run/jev_typesafe_direct_1_13_0.json`",
        "- `docs/benchmark_report_ja.md`",
        "- `benchmarks/phase_2_5/run_jev_benchmark.py`",
    ]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
