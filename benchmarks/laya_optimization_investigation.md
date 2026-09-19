# Laya CPU optimization investigation

## Trigger

The baseline full decision bundle measured a 2,417.9 ms p50, exceeding the project's 500 ms investigation threshold. This document records the next technically defensible paths without changing model technology or downloading third-party converted weights.

## Exact model examined

- Package: `laya==0.3.3`
- Repository: `convaiinnovations/laya`
- Revision: `c5d78730f3493e4fe16d61507ef4b78eef7318cf`
- Official subfolder: `multilingual`
- Weights: 643,835,514 bytes
- Encoder: `jhu-clsp/mmBERT-base`, 22 layers, hidden size 768, 12 attention heads
- CPU execution: FP32 in the current Laya runtime
- Decision input: four questions are collated as four model batch rows per utterance

The root model card says the original checkpoint is English-only. The current official repository also contains a multilingual checkpoint, and the current Laya loader explicitly supports selecting it by subfolder. The benchmark used that official multilingual checkpoint.

## Feasible optimization paths

### 1. First-party ONNX export

This is technically plausible but is not supplied by the Laya package. A JARVIS-owned exporter would wrap the exact official `DecisionModel.forward` inputs:

`input_ids`, `attention_mask`, `marker_pos`, `marker_mask`, and `qtype` -> `logits`, `act`

The export must preserve dynamic batch, sequence, and option-marker dimensions. PyTorch's current recommended path is the `torch.export`-based ONNX exporter. A float ONNX model must first pass numeric parity tests against PyTorch on all benchmark cases before any latency claim is accepted.

Official reference: https://docs.pytorch.org/tutorials/beginner/onnx/export_simple_model_to_onnx_tutorial.html

### 2. ONNX Runtime with dynamic INT8

ONNX Runtime recommends dynamic quantization for transformer models and provides `quantize_dynamic()`. The target PyTorch build detects AVX512 on this CPU, making an x86 CPU trial reasonable. The correct experiment order is:

1. export and verify float ONNX;
2. run transformer graph optimization where compatible;
3. produce a JARVIS-owned dynamic INT8 model from the pinned official checkpoint;
4. rerun all semantic accuracy, probability, latency, RAM, and CPU checks;
5. reject the conversion if decisions or calibrated probabilities drift materially.

Official references: https://onnxruntime.ai/docs/performance/transformers-optimization.html and https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html

### 3. OpenVINO and NNCF INT8

OpenVINO can convert PyTorch models from representative example inputs. NNCF can then apply post-training INT8 quantization, but static calibration needs a separate representative Japanese command corpus. The 70-case evaluation set should not also serve as the sole calibration set, because that would contaminate the evaluation.

Official reference: https://docs.openvino.ai/2024/notebooks/pytorch-post-training-quantization-nncf-with-output.html

## Why conversion was not performed in this phase

The requested stopping point is immediately after the environment audit and feasibility benchmark. More importantly, runtime conversion cannot repair the baseline semantic result: action accuracy was 37.1%, risk accuracy was 48.6%, and only 3 of 70 cases passed the proposed 0.90 probability gate with a correct action. A backend speedup must therefore be evaluated alongside a separate, source-preserving question/schema study; latency alone is not sufficient.

No third-party ONNX or quantized checkpoint was downloaded. The next bounded experiment, if approved, should compare pinned PyTorch FP32, self-exported ONNX FP32, ONNX dynamic INT8, OpenVINO FP32, and OpenVINO INT8 on identical cases with output-parity gates.
