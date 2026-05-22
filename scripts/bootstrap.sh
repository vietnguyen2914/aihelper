#!/usr/bin/env bash
# aihelper Bootstrap Script
# Usage: bash scripts/bootstrap.sh [--full] [--models] [--help]
#
# Modes:
#   minimal (default) — deepseek-coder:1.3b + phi4-mini + qwen3.5:4b-16k
#   full              — + multimodal, OCR, rerankers, vision, office stack
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
MODE="${1:-minimal}"
AIHELPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   aihelper Bootstrap                 ║${NC}"
echo -e "${CYAN}║   Mode: ${MODE}                        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

HAS_ERROR=false; OPTIONAL_MISSING=""

check_cmd() { if command -v "$1" &>/dev/null; then echo -e "  ${GREEN}✅${NC} $1"; else echo -e "  ${RED}❌${NC} $1 -- $2"; HAS_ERROR=true; fi; }
check_optional() { if command -v "$1" &>/dev/null; then echo -e "  ${GREEN}✅${NC} $1"; else echo -e "  ${YELLOW}⚠️${NC} $1 (optional) -- $2"; OPTIONAL_MISSING="$OPTIONAL_MISSING  - $1 ($2)\n"; fi; }

# ── Step 1: Prerequisites ────────────────────────────────────────
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"
check_cmd python3 "Install: brew install python3"
PYTHON_OK=false
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    if awk "BEGIN {exit !($PY_VER >= 3.9)}" 2>/dev/null; then
        echo -e "  ${GREEN}✅${NC} python3 ≥ 3.9 ($PY_VER)"
        PYTHON_OK=true
    else
        echo -e "  ${RED}❌${NC} python3 $PY_VER — need 3.9+"
        HAS_ERROR=true
    fi
fi
check_cmd git "Install: brew install git"
check_optional watchman "Install: brew install watchman"
check_optional ollama "Install: brew install ollama"

# ── Step 2: Environment directories ──────────────────────────────
echo ""; echo -e "${YELLOW}[2/6] Creating environment directories...${NC}"
mkdir -p "$HOME/.aihelper/logs" "$HOME/.aihelper/persist" "$HOME/.aihelper/models"
echo -e "  ${GREEN}✅${NC} ~/.aihelper/{logs, persist, models}"

# ── Step 3: Install Python dependencies ──────────────────────────
echo ""; echo -e "${YELLOW}[3/6] Installing Python dependencies...${NC}"
if [ -f "$AIHELPER_DIR/requirements.txt" ]; then
    python3 -m pip install --quiet -r "$AIHELPER_DIR/requirements.txt" 2>/dev/null && \
        echo -e "  ${GREEN}✅${NC} pip packages installed" || \
        echo -e "  ${YELLOW}⚠️${NC} pip install had warnings (non-critical)"
else
    echo -e "  ${YELLOW}⚠️${NC} No requirements.txt found, skipping"
fi

# ── Step 4: Pull Ollama models ───────────────────────────────────
echo ""; echo -e "${YELLOW}[4/6] Pulling Ollama models...${NC}"
if command -v ollama &>/dev/null; then
    # Minimal set (hot tier)
    MINIMAL_MODELS=(
        "deepseek-coder:1.3b"
        "phi4-mini:latest"
        "qwen3.5:4b-16k"
    )
    # Full set adds multimodal + embeddings + vision
    FULL_MODELS=(
        "minicpm-v:latest"
        "nomic-embed-text:latest"
        "bge-m3:latest"
    )

    if [ "$MODE" = "full" ] || [ "$MODE" = "--full" ]; then
        ALL_MODELS=("${MINIMAL_MODELS[@]}" "${FULL_MODELS[@]}")
        echo -e "  ${CYAN}Full mode: pulling ${#ALL_MODELS[@]} models${NC}"
    else
        ALL_MODELS=("${MINIMAL_MODELS[@]}")
        echo -e "  ${CYAN}Minimal mode: pulling ${#ALL_MODELS[@]} models${NC}"
        echo -e "  ${YELLOW}  Pass --full for multimodal + embedding models${NC}"
    fi

    for model in "${ALL_MODELS[@]}"; do
        echo -e "  Pulling ${model}..."
        if ollama pull "$model" 2>/dev/null; then
            echo -e "    ${GREEN}✅${NC} ${model}"
        else
            echo -e "    ${RED}❌${NC} ${model} — pull failed (will retry later)"
        fi
    done
else
    echo -e "  ${YELLOW}⚠️${NC} Ollama not installed — skipping model pull"
    echo -e "  ${YELLOW}  Install: brew install ollama && ollama serve${NC}"
fi

# ── Step 5: Setup LaunchAgent (macOS auto-start) ────────────────
echo ""; echo -e "${YELLOW}[5/6] Setting up LaunchAgent (macOS)...${NC}"
if [[ "$(uname)" == "Darwin" ]]; then
    LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
    PLIST_PATH="$LAUNCH_AGENTS_DIR/com.aihelper.daemon.plist"
    mkdir -p "$LAUNCH_AGENTS_DIR"

    cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.aihelper.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>${AIHELPER_DIR}/bin/aihelper</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${AIHELPER_DIR}</string>
    <key>StandardOutPath</key>
    <string>${HOME}/.aihelper/logs/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/.aihelper/logs/launchd.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLIST

    # Load the LaunchAgent
    if launchctl list com.aihelper.daemon &>/dev/null 2>&1; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
    fi
    launchctl load "$PLIST_PATH" 2>/dev/null && \
        echo -e "  ${GREEN}✅${NC} LaunchAgent installed + loaded" || \
        echo -e "  ${YELLOW}⚠️${NC} LaunchAgent installed (load on next login)"
else
    echo -e "  ${YELLOW}⚠️${NC} Not macOS — skipping LaunchAgent"
    echo -e "  ${YELLOW}  Auto-start via systemd/cron: see docs/installation.md${NC}"
fi

# ── Step 6: Validate environment ─────────────────────────────────
echo ""; echo -e "${YELLOW}[6/6] Validating environment...${NC}"

# Build cache for self
if $PYTHON_OK; then
    echo -e "  Building aihelper cache..."
    python3 "$AIHELPER_DIR/bin/aihelper" cache build --project-root "$AIHELPER_DIR" 2>/dev/null && \
        echo -e "  ${GREEN}✅${NC} Cache built" || \
        echo -e "  ${YELLOW}⚠️${NC} Cache build incomplete (non-critical)"
fi

# Try daemon start
echo -e "  Starting daemon..."
python3 "$AIHELPER_DIR/bin/aihelper" daemon start 2>/dev/null && \
    echo -e "  ${GREEN}✅${NC} Daemon started" || \
    echo -e "  ${YELLOW}⚠️${NC} Daemon start deferred"

# Run doctor
echo -e "  Running doctor..."
python3 "$AIHELPER_DIR/bin/aihelper" doctor 2>/dev/null && \
    echo -e "  ${GREEN}✅${NC} Health check passed" || \
    echo -e "  ${YELLOW}⚠️${NC} Doctor reported issues"

# ── Summary ──────────────────────────────────────────────────────
echo ""; echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Bootstrap Complete                    ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}📁${NC} aihelper:  $AIHELPER_DIR"
echo -e "  ${GREEN}🔧${NC} Mode:     ${MODE}"
echo -e "  ${GREEN}🏠${NC} Home:     ~/.aihelper/"

if $HAS_ERROR; then
    echo ""; echo -e "  ${RED}❌ Critical items failed — fix above and re-run${NC}"
    exit 1
fi

if [ -n "$OPTIONAL_MISSING" ]; then
    echo ""; echo -e "  ${YELLOW}Optional tools not found:${NC}"
    echo -e "$OPTIONAL_MISSING"
fi

echo ""; echo -e "  ${GREEN}Quick start for any project:${NC}"
echo -e "  ${CYAN}  cd /path/to/your/project${NC}"
echo -e "  ${CYAN}  aihelper cache build${NC}"
echo -e "  ${CYAN}  aihelper route \"fix bug\"${NC}"
echo ""
