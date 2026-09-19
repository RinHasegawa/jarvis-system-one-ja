from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import psutil


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "benchmarks" / "laya_cases.json"
RESULTS_DIR = ROOT / "benchmarks" / "results"
ARTIFACTS_DIR = ROOT / "benchmarks" / "artifacts"
HF_HOME = ROOT / ".cache" / "huggingface"

MODEL_ID = "convaiinnovations/laya"
MODEL_REVISION = "c5d78730f3493e4fe16d61507ef4b78eef7318cf"
MODEL_SUBFOLDER = "multilingual"

ACTION_OPTIONS = {
    "OPEN_APP": "インストール済みアプリを開く、起動する、立ち上げる操作。ウェブサイトを開く操作ではない。",
    "OPEN_URL": "既知のウェブサイト、ウェブページ、URLをブラウザで開く、表示する、アクセスする操作。アプリ自体の起動ではない。",
    "VOLUME_UP": "Windows全体の音量を上げる、音を大きくする操作。",
    "VOLUME_DOWN": "Windows全体の音量を下げる、音を小さくする操作。",
    "MEDIA_PLAY_PAUSE": "現在の音楽または動画を再生、一時停止、再開する操作。JARVIS全体の中止ではない。",
    "WAIT": "現在の処理を少し待たせる、待機または保留にする指示。",
    "UNKNOWN": "上記のどの対応操作にも明確に該当しない、不完全、質問、または対象外の依頼。",
}

TARGET_OPTIONS = {
    "CHROME": "Google Chrome アプリ。Chrome、クローム。",
    "EDGE": "Microsoft Edge アプリ。Edge、エッジ。",
    "SPOTIFY": "Spotify アプリ。Spotify、スポティファイ。",
    "NOTEPAD": "Windows メモ帳アプリ。メモ帳、Notepad、ノートパッド。",
    "VS_CODE": "Visual Studio Code アプリ。VS Code、Visual Studio Code。",
    "GOOGLE": "Google ウェブサイト、google.com、グーグルのページ。",
    "YOUTUBE": "YouTube ウェブサイト、YouTube、ユーチューブ。",
    "GITHUB": "一般的な GitHub ウェブサイトまたはページ。GitHub、ギットハブ。",
    "LAYA_GITHUB": "Laya の公式 GitHub ソースリポジトリ、LayaのGitHub、Layaの公式コード。",
    "NONE": "明示された許可対象がない。",
}

ACTION_QUESTION = {
    "type": "choice",
    "instructions": "日本語の発話でユーザーが主に要求しているコンピュータ操作を1つ選んでください。安全性や実行可否は判断せず、意味だけを分類してください。",
    "criteria": ACTION_OPTIONS,
}

TARGET_QUESTION = {
    "type": "choice",
    "instructions": "ユーザーが明示した許可対象を1つ選んでください。候補名を自由生成せず、最も具体的に一致するものを選んでください。",
    "criteria": TARGET_OPTIONS,
}


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if len(cases) != 70:
        raise ValueError(f"The frozen Phase 0-2 dataset must contain 70 cases, found {len(cases)}")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Case IDs must remain unique")
    return cases


def questions_for_case(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    questions = {"action": ACTION_QUESTION}
    if case["target_applicable"]:
        questions["target"] = TARGET_QUESTION
    return questions


def deterministic_stop(text: str) -> bool:
    normalized = "".join(text.split())
    exact = {"止めて", "ストップ", "キャンセル"}
    phrases = ("操作を中止", "実行を取り消", "やっぱりやめ")
    return normalized in exact or any(phrase in normalized for phrase in phrases)


def resolve_snapshot(*, offline: bool = True) -> Path:
    os.environ["HF_HOME"] = str(HF_HOME.resolve())
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            allow_patterns=[f"{MODEL_SUBFOLDER}/*"],
            local_files_only=offline,
        )
    )


def model_dir(snapshot: Path) -> Path:
    return snapshot / MODEL_SUBFOLDER


def load_model_config(snapshot: Path) -> dict[str, Any]:
    return json.loads((model_dir(snapshot) / "rl_agent_config.json").read_text(encoding="utf-8"))


def load_tokenizer(snapshot: Path):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_dir(snapshot) / "tokenizer", local_files_only=True)


def prepare_inputs(tokenizer, config: dict[str, Any], state: str, questions: dict[str, dict[str, Any]]):
    from laya.common import QTYPES, build_sequence, collate_items, render_options

    items = []
    for question in questions.values():
        qtype = question["type"]
        criteria = question.get("criteria")
        internal = {"t": qtype, "ins": question["instructions"], "crit": criteria}
        sequence, markers = build_sequence(
            tokenizer,
            state,
            internal,
            config.get("max_len", 512),
            config.get("head_max_len", 192),
        )
        if len(markers) != len(render_options(internal)):
            raise ValueError("Question options exceeded the Laya head token budget")
        items.append({"ids": sequence, "markers": markers, "qtype": QTYPES[qtype]})
    return collate_items([items], tokenizer.pad_token_id)


def decode_outputs(
    config: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    logits: np.ndarray,
    act_logits: np.ndarray | None = None,
) -> dict[str, Any]:
    from laya.common import QTYPES, confidence_from_probs, temp_bucket

    answers: dict[str, Any] = {}
    temperatures = config.get("temperature", [1.0, 1.0, 1.0])
    by_options = config.get("temperature_by_options", {})
    for row_index, (question_id, question) in enumerate(questions.items()):
        keys = list(question["criteria"].keys())
        qtype_index = QTYPES[question["type"]]
        scale = by_options.get(temp_bucket(qtype_index, len(keys)), temperatures[qtype_index])
        row = logits[row_index, : len(keys)].astype(np.float64) / max(1e-3, float(scale))
        probabilities = np.exp(row - row.max())
        probabilities /= probabilities.sum()
        winner = int(probabilities.argmax())
        answers[question_id] = {
            "type": "choice",
            "choice": keys[winner],
            "probabilities": {
                key: round(float(value), 7) for key, value in zip(keys, probabilities)
            },
            "confidence": round(confidence_from_probs(probabilities, len(keys)), 7),
        }
    return {"model": "laya-rl-agent", "answers": answers}


def numpy_inputs(batch: dict[str, Any]) -> dict[str, np.ndarray]:
    return {
        "input_ids": batch["input_ids"].cpu().numpy().astype(np.int64),
        "attention_mask": batch["attention_mask"].cpu().numpy().astype(np.int64),
        "marker_pos": batch["marker_pos"].cpu().numpy().astype(np.int64),
        "marker_mask": batch["marker_mask"].cpu().numpy().astype(np.bool_),
        "qtype": batch["qtype"].cpu().numpy().astype(np.int64),
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=np.float64), pct))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ResourceSampler:
    def __init__(self, interval_seconds: float = 0.1) -> None:
        self.process = psutil.Process()
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.rss_bytes: list[int] = []
        self.available_bytes: list[int] = []
        self.system_cpu_percent: list[float] = []

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
                self.available_bytes.append(psutil.virtual_memory().available)
                self.system_cpu_percent.append(psutil.cpu_percent(interval=None))
            except (OSError, psutil.Error):
                pass
            self.stop_event.wait(self.interval_seconds)


def reliability_metrics(rows: Iterable[dict[str, Any]], field: str, expected_field: str) -> dict[str, Any]:
    selected = list(rows)
    if not selected:
        return {"count": 0, "brier_score": None, "ece": None, "bins": []}
    confidences: list[float] = []
    correctness: list[float] = []
    brier_values: list[float] = []
    for row in selected:
        probabilities = row[field]
        predicted = max(probabilities, key=probabilities.get)
        expected = row[expected_field]
        confidences.append(float(probabilities[predicted]))
        correctness.append(float(predicted == expected))
        brier_values.append(
            sum((float(probability) - float(option == expected)) ** 2 for option, probability in probabilities.items())
        )
    bins = []
    ece = 0.0
    for index in range(10):
        lower = index / 10.0
        upper = (index + 1) / 10.0
        members = [
            i
            for i, confidence in enumerate(confidences)
            if confidence >= lower and (confidence < upper or (index == 9 and confidence <= upper))
        ]
        if not members:
            continue
        avg_confidence = statistics.fmean(confidences[i] for i in members)
        accuracy = statistics.fmean(correctness[i] for i in members)
        ece += len(members) / len(selected) * abs(accuracy - avg_confidence)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(members),
                "average_confidence": round(avg_confidence, 7),
                "accuracy": round(accuracy, 7),
            }
        )
    return {
        "count": len(selected),
        "brier_score": round(statistics.fmean(brier_values), 7),
        "ece": round(ece, 7),
        "bins": bins,
    }


def classification_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    semantic_rows = [row for row in rows if row["expected_action"] != "STOP"]
    target_rows = [row for row in rows if row["target_applicable"]]
    stop_rows = [row for row in rows if row["expected_action"] == "STOP"]

    per_class: dict[str, Any] = {}
    confusion: dict[str, dict[str, int]] = {}
    for expected in ACTION_OPTIONS:
        class_rows = [row for row in semantic_rows if row["expected_action"] == expected]
        correct = sum(row["predicted_action"] == expected for row in class_rows)
        per_class[expected] = {
            "correct": correct,
            "count": len(class_rows),
            "accuracy": correct / len(class_rows) if class_rows else None,
        }
        confusion[expected] = {
            predicted: sum(row["predicted_action"] == predicted for row in class_rows)
            for predicted in ACTION_OPTIONS
        }

    semantic_correct = sum(row["predicted_action"] == row["expected_action"] for row in semantic_rows)
    target_correct = sum(row["predicted_target"] == row["expected_target"] for row in target_rows)
    stop_correct = sum(row["deterministic_stop_match"] for row in stop_rows)
    routed_correct = semantic_correct + stop_correct

    return {
        "semantic_action_accuracy": semantic_correct / len(semantic_rows),
        "semantic_action_correct": semantic_correct,
        "semantic_action_count": len(semantic_rows),
        "routed_action_accuracy_including_deterministic_stop": routed_correct / len(rows),
        "routed_action_correct": routed_correct,
        "routed_action_count": len(rows),
        "deterministic_stop_accuracy": stop_correct / len(stop_rows),
        "deterministic_stop_correct": stop_correct,
        "deterministic_stop_count": len(stop_rows),
        "target_accuracy": target_correct / len(target_rows),
        "target_correct": target_correct,
        "target_count": len(target_rows),
        "per_class": per_class,
        "confusion_matrix": confusion,
        "calibration": {
            "action": reliability_metrics(semantic_rows, "action_probabilities", "expected_action"),
            "target": reliability_metrics(target_rows, "target_probabilities", "expected_target"),
        },
    }


def compare_to_reference(rows: list[dict[str, Any]], reference_path: Path | None) -> dict[str, Any] | None:
    if reference_path is None:
        return None
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference_rows = {row["id"]: row for row in reference["predictions"]}
    action_agree = 0
    target_agree = 0
    target_count = 0
    action_diffs: list[float] = []
    target_diffs: list[float] = []
    for row in rows:
        baseline = reference_rows[row["id"]]
        action_agree += row["predicted_action"] == baseline["predicted_action"]
        for option in ACTION_OPTIONS:
            action_diffs.append(
                abs(row["action_probabilities"][option] - baseline["action_probabilities"][option])
            )
        if row["target_applicable"]:
            target_count += 1
            target_agree += row["predicted_target"] == baseline["predicted_target"]
            for option in TARGET_OPTIONS:
                target_diffs.append(
                    abs(row["target_probabilities"][option] - baseline["target_probabilities"][option])
                )
    return {
        "reference": str(reference_path.resolve()),
        "action_prediction_agreement": action_agree / len(rows),
        "target_prediction_agreement": target_agree / target_count,
        "action_probability_mean_absolute_difference": statistics.fmean(action_diffs),
        "action_probability_max_absolute_difference": max(action_diffs),
        "target_probability_mean_absolute_difference": statistics.fmean(target_diffs),
        "target_probability_max_absolute_difference": max(target_diffs),
    }


def system_memory_snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total_ram_mib": round(memory.total / 1024**2, 3),
        "available_ram_mib": round(memory.available / 1024**2, 3),
        "ram_percent": memory.percent,
        "pagefile_total_mib": round(swap.total / 1024**2, 3),
        "pagefile_used_mib": round(swap.used / 1024**2, 3),
        "pagefile_percent": swap.percent,
        "system_cpu_percent": psutil.cpu_percent(interval=0.25),
    }


def process_cpu_summary(before, after, wall_seconds: float) -> dict[str, float]:
    cpu_seconds = (after.user - before.user) + (after.system - before.system)
    logical = psutil.cpu_count(logical=True) or 1
    one_core = cpu_seconds / wall_seconds * 100.0
    return {
        "process_cpu_seconds": round(cpu_seconds, 3),
        "average_process_cpu_percent_one_core_basis": round(one_core, 3),
        "average_process_cpu_percent_machine_capacity": round(one_core / logical, 3),
    }
