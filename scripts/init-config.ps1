param(
    [switch]$All,
    [string]$Path = "",
    [switch]$DryRun,
    [switch]$Verbose,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host "Usage: pwsh scripts/init-config.ps1 [options]"
    Write-Host ""
    Write-Host "Generate local AI agent configs per machine."
    Write-Host ""
    Write-Host "Modes:"
    Write-Host "  (default)     Configure the current Git repo (CWD)"
    Write-Host "  -All [root]   Scan all repos under a root directory"
    Write-Host "  -Path <dir>   Configure a specific project"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -DryRun       Preview without writing"
    Write-Host "  -Verbose      Detailed output"
    Write-Host "  -Help         This help"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  pwsh scripts/init-config.ps1"
    Write-Host "  pwsh scripts/init-config.ps1 -All"
    Write-Host "  pwsh scripts/init-config.ps1 -All C:\projects"
    Write-Host "  pwsh scripts/init-config.ps1 -Path C:\my-project"
    Write-Host "  pwsh scripts/init-config.ps1 -DryRun -Verbose"
    Write-Host "  `$env:REGISTRY_FILE='C:\projects.md'; pwsh scripts/init-config.ps1 -All"
    exit 0
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$AihelperRoot = $RepoRoot
$ScriptName = "init-config.ps1"

function Log {
    param([string]$Level, [string]$Message)
    $color = switch ($Level) {
        "OK"    { "Green" }
        "ERROR" { "Red" }
        "SKIP"  { "Yellow" }
        "INFO"  { "Cyan" }
        default { "White" }
    }
    if ($Verbose -or @("OK","ERROR","SKIP") -contains $Level) {
        Write-Host ("[{0}] {1}" -f $Level, $Message) -ForegroundColor $color
    }
}

function Write-IfChanged {
    param([string]$FilePath, [string]$Content)
    if ($DryRun) {
        Write-Host "  [DRY-RUN] Would write: $FilePath"
        return
    }
    $parent = Split-Path $FilePath -Parent
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path $FilePath) {
        $current = Get-Content $FilePath -Raw -ErrorAction SilentlyContinue
        if ($current -eq $Content) {
            Log "SKIP" "  No change: $FilePath"
            return
        }
    }
    Set-Content -Path $FilePath -Value $Content -NoNewline
    Log "OK" "  Written: $FilePath"
}

function Run-IntegrationScript {
    param([string]$ScriptName, [string[]]$ScriptArgs)
    $scriptPath = Join-Path $RepoRoot "scripts" $ScriptName
    $pyArgs = @()
    if ($DryRun) {
        $pyArgs += "--dry-run"
    }
    $pyArgs += $ScriptArgs
    $pythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
    if ($DryRun) {
        Write-Host "  [DRY-RUN] Would run: $pythonCmd $scriptPath $($pyArgs -join ' ')"
        return
    }
    if (-not (Test-Path $scriptPath)) {
        Log "WARN" "  Script not found: $scriptPath"
        return
    }
    try {
        & $pythonCmd $scriptPath @pyArgs
        if ($LASTEXITCODE -ne 0) {
            Log "WARN" "  Integration script exited with code $LASTEXITCODE: $ScriptName"
        }
    } catch {
        Log "WARN" "  Integration script failed: $ScriptName -- $_"
    }
}

function Is-ValidProject {
    param([string]$Dir)
    if (-not (Test-Path $Dir)) { return $false }
    $gitDir = Join-Path $Dir ".git"
    if (-not (Test-Path $gitDir)) { return $false }
    $fileCount = (Get-ChildItem -Path $Dir -File | Measure-Object).Count
    if ($fileCount -lt 1) { return $false }
    $absDir = (Resolve-Path $Dir).Path
    $absAihelper = (Resolve-Path $AihelperRoot).Path
    if ($absDir -eq $absAihelper) { return $false }
    return $true
}

# ── Banner ──
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "  aihelper -- Local Config Initializer" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

Log "INFO" "aihelper root: $AihelperRoot"

# ── Determine mode ──
$Mode = "cwd"
$ScanRoot = ""
$TargetDirs = @()

if ($All) {
    $Mode = "all"
    if ($Path -and (Test-Path $Path)) {
        $ScanRoot = $Path
    }
} elseif ($Path) {
    $Mode = "path"
    $TargetDirs += $Path
}

if ($Mode -eq "cwd") {
    $TargetDirs += (Get-Location).Path
} elseif ($Mode -eq "all") {
    if (-not $ScanRoot) {
        $candidates = @(
            Join-Path $HOME "github",
            Join-Path $HOME "code",
            Join-Path $HOME "dev",
            Join-Path $HOME "src",
            Join-Path $HOME "projects"
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) {
                $items = Get-ChildItem $c | Measure-Object | Select-Object -ExpandProperty Count
                if ($items -gt 0) {
                    $ScanRoot = $c
                    break
                }
            }
        }
        if (-not $ScanRoot) {
            Write-Host "  --all mode needs a root directory." -ForegroundColor Yellow
            $ScanRoot = Read-Host "Projects root (e.g. C:\Users\$env:USERNAME\github)"
        }
    }
    Log "INFO" "Scanning: $ScanRoot"
    $TargetDirs = Get-ChildItem -Path $ScanRoot -Directory | Select-Object -ExpandProperty FullName
}

# ── Validate projects ──
$Projects = @()
foreach ($dir in $TargetDirs) {
    if (Is-ValidProject $dir) {
        $Projects += $dir
    }
}

if ($Projects.Count -eq 0) {
    if ($Mode -eq "cwd") {
        Write-Host "[ERROR] Current directory is not a Git project or has no source files." -ForegroundColor Red
        Write-Host "        Run from inside a Git repository, or use:" -ForegroundColor Red
        Write-Host "          .\bin\aihelper.ps1 init-config -Path C:\path\to\project" -ForegroundColor Red
        Write-Host "          .\bin\aihelper.ps1 init-config -All" -ForegroundColor Red
    } else {
        Write-Host "[ERROR] No valid Git projects found." -ForegroundColor Red
    }
    exit 1
}

Log "OK" "Valid projects: $($Projects.Count)"

# ── Generate global config ──
Write-Host ""
Write-Host "-- Generating config files -------------------------------" -ForegroundColor Cyan
Write-Host ""

$globalCopilotFile = Join-Path $HOME ".github" "copilot-instructions.md"
$globalCopilotContent = @"
# Global Agent Instructions: Token Budget Protocol

Applies to ALL agents: Claude, Gemini, DeepSeek, Codex, Copilot, Ollama.

## Mandatory: Use aihelper context compression FIRST

Before scanning repos, running grep, or reading multiple files:

1. `aihelper route "<task>"` — identify tools + token budget
2. `aihelper context --max-context-chars 2000` — compact project overview
3. `aihelper symbol_lookup <symbol>` — instead of grep
4. `aihelper diff_summary` — instead of full git diffs

## Token Budget

| Operation | Max Context Chars | Max Tokens |
|-----------|------------------:|-----------:|
| Quick lookup / autocomplete | 500 | ~125 |
| Single-file change | 2,000 | ~500 |
| Multi-file change | 4,000 | ~1,000 |
| Architecture / design | 8,000 | ~2,000 |
| Debugging | 5,000 | ~1,250 |

## NEVER
- Run `find .`, `grep -r`, `rg -r` on a full project without aihelper first
- Read >3 raw files without `aihelper_context` first
- Send raw file dumps to cloud models without aihelper compression
- Exceed token budget — aihelper engine hard-enforces it
"@
Write-IfChanged $globalCopilotFile $globalCopilotContent

# ── Generate Codex config ──
$codexConfigDir = Join-Path $HOME ".codex"
$codexConfigFile = Join-Path $codexConfigDir "config.json"
$codexConfigContent = @"
{
  "developer_instructions": "CRITICAL: Before every response, run aihelper_route and aihelper_context tools first to compress project context. Never scan full repos. Use symbol lookups instead of grep. Respect the token budget from aihelper_route. Default to 2000 max_context_chars for context tool calls. Only escalate to full file reads when aihelper context is insufficient. This applies regardless of which model is being used.",
  "model_auto_compact_token_limit": 4000,
  "model_context_window": 32000,
  "model_verbosity": "concise"
}
"@
Write-IfChanged $codexConfigFile $codexConfigContent

# ── Per-project configs ──
foreach ($projDir in $Projects) {
    $projName = Split-Path $projDir -Leaf
    $projFile = Join-Path $projDir ".github" "copilot-instructions.md"

    $extraRules = ""
    $agentsFile = Join-Path $projDir "AGENTS.md"
    if (Test-Path $agentsFile) {
        $agentsContent = Get-Content $agentsFile -Raw
        if ($agentsContent -match "php|legacy|wordpress") {
            $extraRules = "- Legacy codebase: prefer targeted edits, avoid reformatting entire files"
        }
        if ($agentsContent -match "spring|boot|java") {
            $extraRules = "$extraRules`n- Java project: use Maven/Gradle for builds, respect existing code style"
        }
        if ($agentsContent -match "node|react|angular|vue") {
            $extraRules = "$extraRules`n- Node/frontend project: default to pnpm"
        }
    }

    $projContent = @"
# $projName — Local Project Instructions

## Context Budget
- Use `aihelper context --max-context-chars 2000` for most tasks
- Extend to `--max-context-chars 4000` only for multi-file changes
- Never exceed 5000 chars without explicit user permission
"@
    if ($extraRules) {
        $projContent += @"

## Project Notes
$extraRules
"@
    }

    Write-IfChanged $projFile $projContent
}

# ── Editor and agent integration scripts ──
# Each script generates config for its target editor/agent.
# All scripts are failsafe: they write configs even if the editor
# is not installed, and skip if no changes are needed.

# Per-project scripts (VS Code Copilot, Claude)
foreach ($projDir in $Projects) {
    Run-IntegrationScript "vscode-copilot-integration.py" @("--path", $projDir)
}

# Global/agent scripts (MCP config for editors)
Run-IntegrationScript "codex-integration.py" @()
Run-IntegrationScript "zed-integration.py" @()
Run-IntegrationScript "gemini-integration.py" @()
Run-IntegrationScript "opencode-integration.py" @()

# Per-project scripts (Claude)
foreach ($projDir in $Projects) {
    Run-IntegrationScript "claude-integration.py" @("--path", $projDir)
}

# ── Optional registry ──
$registryFile = [Environment]::GetEnvironmentVariable("REGISTRY_FILE")
if ($registryFile) {
    $registryLines = @()
    $registryLines += "# Local Project Registry"
    $registryLines += ""
    $registryLines += "> Auto-generated by scripts/init-config.ps1."
    $registryLines += "> Lists all Git projects detected on this machine."
    $registryLines += ""
    $registryLines += "## Configuration"
    $registryLines += ""
    $registryLines += "| Variable | Value |"
    $registryLines += "|----------|-------|"
    $registryLines += "| AIHELPER_ROOT | `` $AihelperRoot`` |"
    if ($ScanRoot) {
        $registryLines += "| SCAN_ROOT | `` $ScanRoot`` |"
    }
    $registryLines += ""
    $registryLines += "## Detected Projects"
    $registryLines += ""
    $registryLines += "| # | Project | Path | Type |"
    $registryLines += "|---|---------|------|------|"
    $pIdx = 1
    foreach ($proj in $Projects) {
        $pName = Split-Path $proj -Leaf
        $pType = "Unknown"
        if (Test-Path (Join-Path $proj "pom.xml")) { $pType = "Java/Maven" }
        elseif (Test-Path (Join-Path $proj "build.gradle")) { $pType = "Java/Gradle" }
        elseif (Test-Path (Join-Path $proj "package.json")) {
            $pkg = Get-Content (Join-Path $proj "package.json") -Raw
            if ($pkg -match '"react"') { $pType = "React/Node" }
            elseif ($pkg -match '"next"') { $pType = "Next.js/Node" }
            elseif ($pkg -match '"angular"') { $pType = "Angular/Node" }
            elseif ($pkg -match '"vue"') { $pType = "Vue/Node" }
            else { $pType = "Node.js" }
        }
        elseif ((Get-ChildItem (Join-Path $proj "*.py") -ErrorAction SilentlyContinue).Count -gt 0) { $pType = "Python" }
        elseif ((Get-ChildItem (Join-Path $proj "*.php") -ErrorAction SilentlyContinue).Count -gt 0) { $pType = "PHP" }
        $registryLines += "| $pIdx | $pName | `` $proj`` | $pType |"
        $pIdx++
    }
    $registryLines += ""
    $registryLines += "---"
    $registryLines += ""
    $registryLines += "_Generated by init-config.ps1 on $(Get-Date -Format yyyy-MM-dd)._"
    $registryLines += "_Re-run after cloning new projects to refresh._"
    $registryLines -join "`r`n" | Set-Content $registryFile
    Log "OK" "  Written: $registryFile"
}

# ── Summary ──
Write-Host ""
Write-Host ("-" * 70) -ForegroundColor Cyan
if ($Mode -eq "cwd") {
    Write-Host "   Done. Configs generated for $($Projects.Count) project(s)" -ForegroundColor Green
    Write-Host "      (current directory: $(Get-Location))" -ForegroundColor Green
} elseif ($Mode -eq "all") {
    Write-Host "   Done. Configs generated for $($Projects.Count) project(s)" -ForegroundColor Green
    Write-Host "      (scan root: $ScanRoot)" -ForegroundColor Green
} else {
    Write-Host "   Done. Configs generated for $($Projects.Count) project(s)" -ForegroundColor Green
}
Write-Host ""
Write-Host "   Run 'aihelper init-config' from any Git repo to add config." -ForegroundColor Cyan
Write-Host "   Run 'aihelper init-config -All' to configure ALL repos." -ForegroundColor Cyan
Write-Host ""
Write-Host "   Optional: `$env:REGISTRY_FILE to generate project registry." -ForegroundColor Cyan
Write-Host ("-" * 70) -ForegroundColor Cyan
Write-Host ""
