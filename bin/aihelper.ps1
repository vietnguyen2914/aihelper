param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AihelperArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

if (-not $env:AIHELPER_TARGET_ROOT) {
    $env:AIHELPER_TARGET_ROOT = (Get-Location).Path
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $Python) {
    Write-Error "Python 3.9+ is required. Install from https://www.python.org/downloads/windows/ or winget install Python.Python.3.12"
    exit 1
}

if (-not $AihelperArgs -or $AihelperArgs.Count -eq 0) {
    if (-not [Console]::IsInputRedirected) {
        & $Python.Source (Join-Path $RepoRoot "context_engine/main.py") --help
        exit $LASTEXITCODE
    }

    $stdinPrompt = [Console]::In.ReadToEnd()
    if ($stdinPrompt.Trim().Length -gt 0) {
        & $Python.Source (Join-Path $RepoRoot "context_engine/main.py") analyze $stdinPrompt
        exit $LASTEXITCODE
    }

    & $Python.Source (Join-Path $RepoRoot "context_engine/main.py") --help
    exit $LASTEXITCODE
}

if ($AihelperArgs[0] -eq "init-config") {
    $initArgs = $AihelperArgs[1..$AihelperArgs.Count]
    & powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts" "init-config.ps1") @initArgs
    exit $LASTEXITCODE
}

if ($AihelperArgs[0] -notin @(
    "analyze", "feedback", "feedback-summary", "feedback_summary", "rebuild-index", "rebuild_index",
    "cache", "prompt-blocks", "prompt_blocks", "diff-summary", "diff_summary", "memory", "symbol",
    "deps", "route", "patch-plan", "patch_plan", "patch-apply", "patch_apply", "validate-files",
    "validate_files", "ollama", "daemon", "doctor", "editor-context", "editor_context", "lsp",
    "confidence", "structural-diff", "structural_diff", "hierarchical-context", "hierarchical_context",
    "scheduler", "intent-route", "intent_route", "capability-route", "capability_route", "telemetry",
    "health", "diagnostics", "impact-graph", "impact_graph", "classify-op", "classify_op",
    "degradation", "warmup", "init-config", "upgrade", "graph", "affected",
    "-h", "--help", "help"
)) {
    $AihelperArgs = @("analyze") + $AihelperArgs
}

& $Python.Source (Join-Path $RepoRoot "context_engine/main.py") @AihelperArgs
exit $LASTEXITCODE
