$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "clean_benchmark.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python was not found: $python"
}
if (-not (Test-Path -LiteralPath $script)) {
    throw "Clean benchmark script was not found: $script"
}

Set-Location -LiteralPath $projectRoot
$env:PYTHONIOENCODING = "utf-8"
$env:OPENVINO_TELEMETRY_LEVEL = "0"
& $python $script
exit $LASTEXITCODE
