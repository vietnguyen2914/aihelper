#!/usr/bin/env bash
# aihelper Bootstrap Script
# Usage: bash scripts/bootstrap.sh [--full] [--models] [--help]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
MODE="${1:-minimal}"
AIHELPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   aihelper Bootstrap                 ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

HAS_ERROR=false; OPTIONAL_MISSING=""

check_cmd() { if command -v "$1" &>/dev/null; then echo -e "  ${GREEN}✅${NC} $1"; else echo -e "  ${RED}❌${NC} $1 -- $2"; HAS_ERROR=true; fi; }
check_optional() { if command -v "$1" &>/dev/null; then echo -e "  ${GREEN}✅${NC} $1"; else echo -e "  ${YELLOW}⚠️${NC} $1 (optional) -- $2"; OPTIONAL_MISSING="$OPTIONAL_MISSING  - $1 ($2)\n"; fi; }

echo -e "${YELLOW}Checking prerequisites...${NC}"
check_cmd python3 "Install: brew install python3"
check_cmd git "Install: brew install git"
check_optional watchman "Install: brew install watchman"
check_optional ollama "Install: brew install ollama"

echo ""; echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p "$HOME/.aihelper/logs" "$HOME/.aihelper/persist"
echo -e "  ${GREEN}✅${NC} ~/.aihelper/"

echo ""; echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. ${GREEN}cd $AIHELPER_DIR${NC}"
echo -e "  2. ${GREEN}python3 bin/aihelper cache build --project-root .${NC}"
echo -e "  3. ${GREEN}python3 bin/aihelper daemon start${NC}"
echo -e "  4. ${GREEN}python3 bin/aihelper daemon status${NC}"
