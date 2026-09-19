# JARVIS project guidance

## Project identity

- Project name: **JARVIS**.
- Purpose: a Windows-first, local voice computer-control experiment that turns streaming speech into bounded semantic decisions and then trusted deterministic actions.
- Core architecture: microphone -> local streaming STT -> partial transcript -> Laya typed probabilistic decision -> configurable stability/confidence gate -> deterministic Windows action registry.
- Current V0 action scope: `OPEN_APP`, `OPEN_URL`, `VOLUME_UP`, `VOLUME_DOWN`, `MEDIA_PLAY_PAUSE`, `WAIT`, `STOP`, and `UNKNOWN`. Application targets must come from an allowlist.
- Current milestone: Phase 2.5 isolates semantic quality, runtime performance, and benchmark-environment pressure before implementing the live JARVIS loop.
- Preserve the original 70-case Phase 0-2 baseline and its scoring. Phase 2.5 results must be written separately.
- In `action_target_v2`, Laya selects only ACTION and an explicit allowlisted TARGET. `STOP` stays in the frozen labels but is handled and scored by deterministic matching outside Laya.

## Safety and non-goals

- Semantic models may choose bounded actions but may never generate arbitrary PowerShell, cmd, shell, or other commands for direct execution.
- Emergency stop/cancel detection must be deterministic and must not depend on Laya.
- V0 does not include browser agents, GUI automation, screenshots/vision, paid runtime APIs, generative-model fallbacks, autonomous loops, arbitrary shell generation, deletion, email, purchases, message posting, or credential entry.

## Constraints

- Target: Windows Surface Laptop Go, Intel Core i5 with 4 physical / 8 logical cores, 8 GB RAM, integrated graphics only.
- Optimize in this order: latency, reliability, low RAM use, CPU efficiency, simplicity.
- Normal V0 runtime cost must remain 0 yen and run locally.
- Preserve interfaces around replaceable external systems, and prefer measured results over assumptions.
- Do not run the prepared clean benchmark from Codex. The user closes Codex and starts it manually from PowerShell.
- Jev is evaluation-only: never use its outputs for training/distillation and never store an API key in source files.
