from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from common import (
    ACTION_OPTIONS,
    MODEL_REVISION,
    ROOT,
    TARGET_OPTIONS,
    classification_metrics,
    deterministic_stop,
    load_cases,
    percentile,
    questions_for_case,
)


DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "results" / "jev_latest_action_target_v2.json"


def request_jev(endpoint: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "jarvis-phase-2.5-benchmark/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_choice_answer(answer: dict[str, Any], expected_options: dict[str, str], name: str) -> None:
    if answer.get("type") != "choice" or answer.get("choice") not in expected_options:
        raise ValueError(f"Invalid {name} answer: {answer!r}")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(expected_options):
        raise ValueError(f"Invalid {name} probability keys: {probabilities!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional Jev fair-comparison benchmark for JARVIS Phase 2.5")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--endpoint", default=os.environ.get("TYPESAFE_BASE_URL", DEFAULT_ENDPOINT))
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true", help="Validate and display metadata without calling the API")
    args = parser.parse_args()

    cases = load_cases()
    if args.dry_run:
        print(json.dumps({
            "ready": True,
            "endpoint": args.endpoint,
            "model": args.model,
            "case_count": len(cases),
            "semantic_action_count": sum(case["expected_action"] != "STOP" for case in cases),
            "target_count": sum(case["target_applicable"] for case in cases),
            "api_key_present": bool(os.environ.get("TYPESAFE_API_KEY")),
            "note": "Dry run only; no API request was made.",
        }, ensure_ascii=False, indent=2))
        return 0

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        print("TYPESAFE_API_KEY is not set; no Jev request was made.", file=sys.stderr)
        return 2

    predictions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    usage_totals = {"input_tokens": 0, "output_tokens": 0}
    reported_costs: list[float] = []
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    for case in cases:
        payload = {
            "state": case["transcript"],
            "model": args.model,
            "questions": questions_for_case(case),
        }
        started = time.perf_counter()
        try:
            response = request_jev(args.endpoint, api_key, payload, args.timeout_seconds)
            latency_ms = (time.perf_counter() - started) * 1000.0
            answers = response["answers"]
            action = answers["action"]
            validate_choice_answer(action, ACTION_OPTIONS, "action")
            target = answers.get("target")
            if case["target_applicable"]:
                if target is None:
                    raise ValueError("Target answer is missing")
                validate_choice_answer(target, TARGET_OPTIONS, "target")

            usage = response.get("usage") or {}
            for key in usage_totals:
                if isinstance(usage.get(key), (int, float)):
                    usage_totals[key] += int(usage[key])
            for cost_key in ("cost", "cost_usd", "estimated_cost_usd"):
                if isinstance(usage.get(cost_key), (int, float)):
                    reported_costs.append(float(usage[cost_key]))
                    break

            predictions.append({
                "id": case["id"],
                "transcript": case["transcript"],
                "expected_action": case["expected_action"],
                "expected_target": case["expected_target"],
                "target_applicable": case["target_applicable"],
                "predicted_action": action["choice"],
                "action_probabilities": {key: float(action["probabilities"][key]) for key in ACTION_OPTIONS},
                "action_top_probability": float(action["probabilities"][action["choice"]]),
                "action_entropy_confidence": action.get("confidence"),
                "predicted_target": target["choice"] if target else None,
                "target_probabilities": (
                    {key: float(target["probabilities"][key]) for key in TARGET_OPTIONS} if target else None
                ),
                "target_top_probability": float(target["probabilities"][target["choice"]]) if target else None,
                "target_entropy_confidence": target.get("confidence") if target else None,
                "semantic_action_scored": case["expected_action"] != "STOP",
                "semantic_action_correct": action["choice"] == case["expected_action"],
                "target_correct": target["choice"] == case["expected_target"] if target else None,
                "deterministic_stop_match": deterministic_stop(case["transcript"]),
                "latency_ms": round(latency_ms, 3),
            })
            print(f"{case['id']}: {latency_ms:.1f} ms", flush=True)
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            failures.append({"id": case["id"], "latency_ms": round(latency_ms, 3), "error": repr(exc)})
            print(f"{case['id']}: FAILED {exc!r}", file=sys.stderr, flush=True)

    if failures:
        # Accuracy/calibration over a partial dataset would not be comparable to local 70-case runs.
        metrics = None
    else:
        metrics = classification_metrics(predictions)
    latencies = [row["latency_ms"] for row in predictions]
    result = {
        "schema_version": 2,
        "benchmark_mode": "action_target_v2",
        "timestamp_local": started_at,
        "model": {"provider": "TypeSafe AI", "id": args.model, "endpoint": args.endpoint},
        "comparison_note": "Latency is full network plus hosted inference plus response time, not local model-only inference.",
        "experiment": {
            "frozen_case_count": len(cases),
            "successful_case_count": len(predictions),
            "same_ground_truth_and_scoring_as_laya": True,
            "laya_reference_revision": MODEL_REVISION,
            "target_question_only_when_explicit": True,
            "policy_note": "STOP remains deterministic and is excluded from the semantic ACTION options.",
        },
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 3) if latencies else None,
            "p95": round(percentile(latencies, 95), 3) if latencies else None,
            "mean": round(statistics.fmean(latencies), 3) if latencies else None,
        },
        "metrics": metrics,
        "failures": failures,
        "usage": {
            **usage_totals,
            "reported_cost_total": round(sum(reported_costs), 8) if reported_costs else None,
            "cost_currency": "USD" if reported_costs else None,
            "note": "Cost is only reported when returned by the API; no price is guessed.",
        },
        "predictions": predictions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
