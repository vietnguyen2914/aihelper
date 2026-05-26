param(
    [switch]$Full,
    [switch]$Models,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host "Usage: pwsh scripts/bootstrap.ps1 [-Full] [-Models]"
    Write-Host "  default: install Python requirements, create aihelper dirs, build cache, start daemon"
    Write-Host "  -Full: also pull multimodal/embedding Ollama models"
    Write-Host "  -Models: pull model set without implying full optional tools"
    exit 0
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Mode = if ($Full) { "full" } else { "minimal" }

Write-Host "aihelper Bootstrap" -ForegroundColor Cyan
Write-Host "Mode: $Mode" -ForegroundColor Cyan
Write-Host ""

$HasError = $false

function Require-Command {
    param([string]$Name, [string]$InstallHint)
    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Host "  OK  $Name" -ForegroundColor Green
        return $true
    }
    Write-Host "  ERR $Name -- $InstallHint" -ForegroundColor Red
    $script:HasError = $true
    return $false
}

function Optional-Command {
    param([string]$Name, [string]$InstallHint)
    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Host "  OK  $Name" -ForegroundColor Green
        return $true
    }
    Write-Host "  WARN $Name optional -- $InstallHint" -ForegroundColor Yellow
    return $false
}

Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow
$PythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { $null }
if (-not $PythonCmd) {
    Write-Host "  ERR python -- Install: winget install Python.Python.3.12" -ForegroundColor Red
    $HasError = $true
} else {
    $VersionText = & $PythonCmd --version
    Write-Host "  OK  $VersionText" -ForegroundColor Green
}
Require-Command git "Install: winget install Git.Git" | Out-Null
Optional-Command ollama "Install from https://ollama.com/download/windows" | Out-Null
Optional-Command pwsh "Install: winget install Microsoft.PowerShell" | Out-Null

Write-Host ""
Write-Host "[2/6] Creating environment directories..." -ForegroundColor Yellow
$AihelperHome = Join-Path $HOME ".aihelper"
New-Item -ItemType Directory -Force -Path `
    (Join-Path $AihelperHome "logs"), `
    (Join-Path $AihelperHome "persist"), `
    (Join-Path $AihelperHome "models") | Out-Null
Write-Host "  OK  $AihelperHome\{logs,persist,models}" -ForegroundColor Green

if ($PythonCmd) {
    Write-Host ""
    Write-Host "[3/6] Installing Python dependencies..." -ForegroundColor Yellow
    $Req = Join-Path $RepoRoot "requirements.txt"
    if (Test-Path $Req) {
        & $PythonCmd -m pip install --quiet -r $Req
        Write-Host "  OK  pip packages installed" -ForegroundColor Green
    } else {
        Write-Host "  WARN no requirements.txt found" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[4/6] Pulling Ollama models..." -ForegroundColor Yellow
$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($Ollama) {
    $MinimalModels = @("deepseek-coder:1.3b", "phi4-mini:latest", "qwen3.5:4b-16k")
    $FullModels = @("minicpm-v:latest", "nomic-embed-text:latest", "bge-m3:latest")
    $AllModels = if ($Full) { $MinimalModels + $FullModels } else { $MinimalModels }
    foreach ($Model in $AllModels) {
        Write-Host "  Pulling $Model..."
        & ollama pull $Model
    }
} else {
    Write-Host "  WARN Ollama not installed; skipping model pull" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[5/6] Windows daemon autostart..." -ForegroundColor Yellow
Write-Host "  Manual start is supported now: .\bin\aihelper.ps1 daemon start" -ForegroundColor Cyan
Write-Host "  Optional Scheduled Task support can be added after first Windows smoke testing." -ForegroundColor Cyan

Write-Host ""
Write-Host "[6/6] Validating environment..." -ForegroundColor Yellow
if ($PythonCmd) {
    & (Join-Path $RepoRoot "bin/aihelper.ps1") cache build --project-root $RepoRoot
    & (Join-Path $RepoRoot "bin/aihelper.ps1") daemon start
    & (Join-Path $RepoRoot "bin/aihelper.ps1") doctor
    Write-Host "  Generating per-project agent configs..."
    & (Join-Path $RepoRoot "bin/aihelper.ps1") init-config
}

if ($HasError) {
    Write-Host ""
    Write-Host "Critical items failed. Fix them and rerun bootstrap.ps1." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host "Quick start:"
Write-Host "  cd C:\path\to\your\project"
Write-Host "  <aihelper>\bin\aihelper.ps1 cache build"
Write-Host "  <aihelper>\bin\aihelper.ps1 route `"fix bug`""
