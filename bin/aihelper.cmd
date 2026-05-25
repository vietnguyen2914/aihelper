@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."

if "%AIHELPER_TARGET_ROOT%"=="" set "AIHELPER_TARGET_ROOT=%CD%"

where python >nul 2>nul
if errorlevel 1 (
  where python3 >nul 2>nul
  if errorlevel 1 (
    echo Python 3.9+ is required. Install from https://www.python.org/downloads/windows/ or winget install Python.Python.3.12 1>&2
    exit /b 1
  )
  set "PYTHON=python3"
) else (
  set "PYTHON=python"
)

if "%~1"=="" (
  "%PYTHON%" "%REPO_ROOT%\context_engine\main.py" --help
  exit /b %ERRORLEVEL%
)

set "FIRST_ARG=%~1"
set "KNOWN= analyze feedback feedback-summary feedback_summary rebuild-index rebuild_index cache prompt-blocks prompt_blocks diff-summary diff_summary memory symbol deps route patch-plan patch_plan patch-apply patch_apply validate-files validate_files ollama daemon doctor editor-context editor_context lsp confidence structural-diff structural_diff hierarchical-context hierarchical_context scheduler intent-route intent_route capability-route capability_route telemetry health diagnostics impact-graph impact_graph classify-op classify_op degradation warmup -h --help help "

echo %KNOWN% | findstr /C:" %FIRST_ARG% " >nul
if errorlevel 1 (
  "%PYTHON%" "%REPO_ROOT%\context_engine\main.py" analyze %*
  exit /b %ERRORLEVEL%
)

"%PYTHON%" "%REPO_ROOT%\context_engine\main.py" %*
exit /b %ERRORLEVEL%
