from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from common import (
    ARTIFACTS_DIR,
    MODEL_REVISION,
    MODEL_SUBFOLDER,
    decode_outputs,
    load_model_config,
    load_tokenizer,
    model_dir,
    numpy_inputs,
    prepare_inputs,
    questions_for_case,
    resolve_snapshot,
    sha256,
)


CALIBRATION_PATH = Path(__file__).with_name("calibration_phrases.json")
ONNX_FP32 = ARTIFACTS_DIR / "laya_action_target_v2_fp32.onnx"
ONNX_INT8 = ARTIFACTS_DIR / "laya_action_target_v2_int8.onnx"
OV_FP32 = ARTIFACTS_DIR / "laya_action_target_v2_openvino_fp32.xml"
OV_INT8 = ARTIFACTS_DIR / "laya_action_target_v2_openvino_int8.xml"
MANIFEST = ARTIFACTS_DIR / "conversion_manifest.json"


def example_batch(agent):
    case = {
        "transcript": "ChromeでYouTubeを開いて",
        "target_applicable": True,
    }
    return prepare_inputs(agent.tok, agent.cfg, case["transcript"], questions_for_case(case))


def export_onnx(snapshot: Path, manifest: dict[str, Any]) -> None:
    import laya
    import onnx
    import onnxruntime as ort
    import torch

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    agent = laya.load(snapshot, device="cpu", subfolder=MODEL_SUBFOLDER)
    batch = example_batch(agent)
    inputs = (
        batch["input_ids"],
        batch["attention_mask"],
        batch["marker_pos"],
        batch["marker_mask"],
        batch["qtype"],
    )
    input_names = ["input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype"]
    output_names = ["logits", "act"]
    dynamic_axes = {
        "input_ids": {0: "question_batch", 1: "sequence"},
        "attention_mask": {0: "question_batch", 1: "sequence"},
        "marker_pos": {0: "question_batch", 1: "options"},
        "marker_mask": {0: "question_batch", 1: "options"},
        "qtype": {0: "question_batch"},
        "logits": {0: "question_batch", 1: "options"},
        "act": {0: "question_batch"},
    }
    export_started = time.perf_counter()
    export_mode = "dynamo"
    dynamo_error = None
    try:
        torch.onnx.export(
            agent.model,
            inputs,
            str(ONNX_FP32),
            input_names=input_names,
            output_names=output_names,
            opset_version=18,
            dynamo=True,
            dynamic_shapes={
                "input_ids": {0: "question_batch", 1: "sequence"},
                "attention_mask": {0: "question_batch", 1: "sequence"},
                "marker_pos": {0: "question_batch", 1: "options"},
                "marker_mask": {0: "question_batch", 1: "options"},
                "qtype": {0: "question_batch"},
            },
            external_data=True,
            optimize=True,
        )
    except Exception:
        dynamo_error = traceback.format_exc()
        export_mode = "legacy"
        torch.onnx.export(
            agent.model,
            inputs,
            str(ONNX_FP32),
            input_names=input_names,
            output_names=output_names,
            opset_version=18,
            dynamo=False,
            dynamic_axes=dynamic_axes,
            do_constant_folding=True,
        )
    export_seconds = time.perf_counter() - export_started
    onnx.checker.check_model(str(ONNX_FP32))

    with torch.no_grad():
        pt_logits, pt_act = agent.model(*inputs)
    session = ort.InferenceSession(str(ONNX_FP32), providers=["CPUExecutionProvider"])
    ort_logits, ort_act = session.run(output_names, numpy_inputs(batch))
    logits_diff = float(np.max(np.abs(pt_logits.detach().numpy() - ort_logits)))
    act_diff = float(np.max(np.abs(pt_act.detach().numpy() - ort_act)))
    external_data = Path(str(ONNX_FP32) + ".data")
    manifest["onnx_fp32"] = {
        "status": "ok",
        "export_mode": export_mode,
        "dynamo_error": dynamo_error,
        "export_seconds": round(export_seconds, 3),
        "path": str(ONNX_FP32.resolve()),
        "files": [
            {"path": str(ONNX_FP32.resolve()), "bytes": ONNX_FP32.stat().st_size, "sha256": sha256(ONNX_FP32)},
            {"path": str(external_data.resolve()), "bytes": external_data.stat().st_size, "sha256": sha256(external_data)},
        ],
        "total_bytes": ONNX_FP32.stat().st_size + external_data.stat().st_size,
        "smoke_max_abs_logit_difference": logits_diff,
        "smoke_max_abs_act_difference": act_diff,
    }
    del session, agent


def quantize_onnx(manifest: dict[str, Any]) -> None:
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic

    started = time.perf_counter()
    quantizer_path = "quantize_dynamic"
    shape_inference_error = None
    try:
        quantize_dynamic(
            model_input=str(ONNX_FP32),
            model_output=str(ONNX_INT8),
            per_channel=True,
            reduce_range=False,
            weight_type=QuantType.QInt8,
            op_types_to_quantize=["MatMul", "Gemm"],
            use_external_data_format=True,
            extra_options={"MatMulConstBOnly": True, "DefaultTensorType": onnx.TensorProto.FLOAT},
        )
    except onnx.shape_inference.InferenceError:
        shape_inference_error = traceback.format_exc()
        quantizer_path = "ONNXQuantizer_without_shape_inference"
        import onnxruntime.quantization.onnx_quantizer as onnx_quantizer_module
        from onnxruntime.quantization.onnx_quantizer import ONNXQuantizer
        from onnxruntime.quantization.quant_utils import QuantizationMode

        model = onnx.load(str(ONNX_FP32), load_external_data=True)
        original_shape_reload = onnx_quantizer_module.save_and_reload_model_with_shape_infer
        onnx_quantizer_module.save_and_reload_model_with_shape_infer = lambda model_proto: model_proto
        quantizer = ONNXQuantizer(
            model,
            per_channel=True,
            reduce_range=False,
            mode=QuantizationMode.IntegerOps,
            static=False,
            weight_qType=QuantType.QInt8,
            activation_qType=QuantType.QUInt8,
            tensors_range=None,
            nodes_to_quantize=[],
            nodes_to_exclude=[],
            op_types_to_quantize=["MatMul", "Gemm"],
            extra_options={"MatMulConstBOnly": True, "DefaultTensorType": onnx.TensorProto.FLOAT},
        )
        try:
            quantizer.quantize_model()
            quantizer.model.save_model_to_file(ONNX_INT8, use_external_data_format=True)
        finally:
            onnx_quantizer_module.save_and_reload_model_with_shape_infer = original_shape_reload
    external_data = Path(str(ONNX_INT8) + ".data")
    files = [ONNX_INT8] + ([external_data] if external_data.exists() else [])
    manifest["onnx_int8"] = {
        "status": "ok",
        "quantization": "dynamic QInt8 weights for MatMul/Gemm, per-channel",
        "quantizer_path": quantizer_path,
        "shape_inference_error": shape_inference_error,
        "conversion_seconds": round(time.perf_counter() - started, 3),
        "files": [
            {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in files
        ],
        "total_bytes": sum(path.stat().st_size for path in files),
    }


def convert_openvino(manifest: dict[str, Any]) -> None:
    os.environ.setdefault("OPENVINO_TELEMETRY_LEVEL", "0")
    import openvino as ov

    started = time.perf_counter()
    model = ov.convert_model(str(ONNX_FP32))
    ov.save_model(model, OV_FP32, compress_to_fp16=False)
    bin_path = OV_FP32.with_suffix(".bin")
    manifest["openvino_fp32"] = {
        "status": "ok",
        "conversion_seconds": round(time.perf_counter() - started, 3),
        "xml_path": str(OV_FP32.resolve()),
        "xml_bytes": OV_FP32.stat().st_size,
        "xml_sha256": sha256(OV_FP32),
        "bin_path": str(bin_path.resolve()),
        "bin_bytes": bin_path.stat().st_size,
        "bin_sha256": sha256(bin_path),
        "compress_to_fp16": False,
    }


def quantize_openvino(snapshot: Path, manifest: dict[str, Any]) -> None:
    os.environ.setdefault("OPENVINO_TELEMETRY_LEVEL", "0")
    import nncf
    import openvino as ov

    config = load_model_config(snapshot)
    tokenizer = load_tokenizer(snapshot)
    calibration_rows = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    calibration_inputs = []
    for item in calibration_rows:
        case = {
            "transcript": item["transcript"],
            "target_applicable": item["target_applicable"],
        }
        batch = prepare_inputs(tokenizer, config, case["transcript"], questions_for_case(case))
        calibration_inputs.append(numpy_inputs(batch))
    dataset = nncf.Dataset(calibration_inputs)
    model = ov.Core().read_model(OV_FP32)
    started = time.perf_counter()
    quantized = nncf.quantize(model, dataset, subset_size=len(calibration_inputs))
    ov.save_model(quantized, OV_INT8, compress_to_fp16=False)
    bin_path = OV_INT8.with_suffix(".bin")
    manifest["openvino_int8"] = {
        "status": "ok",
        "quantization": "NNCF post-training INT8",
        "calibration_cases": len(calibration_inputs),
        "calibration_source": str(CALIBRATION_PATH.resolve()),
        "evaluation_cases_used_for_calibration": False,
        "conversion_seconds": round(time.perf_counter() - started, 3),
        "xml_path": str(OV_INT8.resolve()),
        "xml_bytes": OV_INT8.stat().st_size,
        "xml_sha256": sha256(OV_INT8),
        "bin_path": str(bin_path.resolve()),
        "bin_bytes": bin_path.stat().st_size,
        "bin_sha256": sha256(bin_path),
    }


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Export the pinned official Laya model to JARVIS-owned runtimes")
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=["onnx-fp32", "onnx-int8", "openvino-fp32", "openvino-int8", "all"],
        default=["all"],
    )
    args = parser.parse_args()
    steps = {"onnx-fp32", "onnx-int8", "openvino-fp32", "openvino-int8"} if "all" in args.steps else set(args.steps)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = resolve_snapshot(offline=True)
    manifest: dict[str, Any] = {
        "model_revision": MODEL_REVISION,
        "model_subfolder": MODEL_SUBFOLDER,
        "source_weights": str((model_dir(snapshot) / "model.safetensors").resolve()),
        "third_party_converted_weights_used": False,
    }
    if MANIFEST.exists():
        manifest.update(json.loads(MANIFEST.read_text(encoding="utf-8")))
    try:
        if "onnx-fp32" in steps:
            export_onnx(snapshot, manifest)
            manifest.pop("last_error", None)
            save_manifest(manifest)
        if "onnx-int8" in steps:
            quantize_onnx(manifest)
            manifest.pop("last_error", None)
            save_manifest(manifest)
        if "openvino-fp32" in steps:
            convert_openvino(manifest)
            manifest.pop("last_error", None)
            save_manifest(manifest)
        if "openvino-int8" in steps:
            quantize_openvino(snapshot, manifest)
            manifest.pop("last_error", None)
            save_manifest(manifest)
    except Exception:
        manifest["last_error"] = traceback.format_exc()
        save_manifest(manifest)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
