# JARVIS environment audit

Audit date: 2026-09-19 (Asia/Tokyo)

## Host

| Item | Observed value |
|---|---|
| Windows | Windows 11 Home, version 25H2, build 26200.9457 |
| Registry naming caveat | `ProductName` still reports `Windows 10 Home`; build 26200 and display version 25H2 identify Windows 11 25H2 |
| CPU | Intel Core i5-1035G1 @ 1.00 GHz |
| CPU topology | 4 physical cores / 8 logical processors |
| PyTorch CPU capability | AVX512, MKL and oneDNN available |
| Physical RAM | 8,155,983,872 bytes (7.59 GiB) |
| Free RAM at initial audit | 944,787,456 bytes (about 0.88 GiB; this is a point-in-time value) |
| System disk C: | 254,270,238,720 bytes total (236.81 GiB) |
| Free C: before setup | 25,105,715,200 bytes (23.38 GiB) |
| Free C: after dependencies and checkpoint | 23,343,489,024 bytes (21.74 GiB) |
| Capture endpoint | `マイク配列 (Realtek High Definition Audio(SST))`, status `OK` |

Microsoft's release documentation identifies build 26200 as Windows 11 version 25H2, which resolves the stale registry product-name string: https://learn.microsoft.com/en-us/windows-insider/release-notes/release-preview-24h2-25h2/build-26100-9539-26200-9539

## Toolchain

| Tool | Observed value |
|---|---|
| System `python` command | Not present on `PATH` |
| System `py` launcher | Not present on `PATH` |
| Project `.venv` Python | 3.12.14 |
| Project `.venv` pip | 26.2.1 |
| Git | 2.54.0.windows.1 |
| PowerShell | 7.6.5 Core |
| Laya | 0.3.3 |
| PyTorch | 2.14.0 CPU build |
| Transformers | 5.17.0 |
| psutil | 7.0.0 |

The virtual environment is project-local. No system-wide package or administrator-level change was made.

## Repository state

The `JARVIS` directory was empty at the start of the audit and had no `.git` directory. It is therefore a project folder, not currently a Git repository. No useful existing implementation was present to merge or preserve.

Current intentional source/report structure (excluding `.venv` and `.cache`):

```text
JARVIS/
  AGENTS.md
  README.md
  pyproject.toml
  .gitignore
  benchmarks/
    benchmark_laya.py
    environment_audit.md
    laya_cases.json
    laya_baseline.json
    laya_baseline_summary.md
    laya_optimization_investigation.md
```

No JARVIS application modules were created.
