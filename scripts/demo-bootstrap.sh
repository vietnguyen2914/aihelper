#!/usr/bin/env bash
# Demo: bootstrap + doctor
# Simulated fast demo (no actual install)
set -euo pipefail

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   aihelper Bootstrap Demo            ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Step 1: Clone
echo "$ git clone https://github.com/vietnguyen2914/aihelper.git"
echo "Cloning into 'aihelper'..."
sleep 0.3
echo "Receiving objects: 100% (147/147), 1.2 MiB | 2.3 MiB/s"
echo "Resolving deltas: 100% (64/64)"
sleep 0.2
cd /tmp/aihelper-demo 2>/dev/null || mkdir -p /tmp/aihelper-demo && cd /tmp/aihelper-demo

echo ""
echo "$ cd aihelper && bash scripts/bootstrap.sh"
sleep 0.3

# Simulate bootstrap output
echo ""
echo "╔══════════════════════════════════════╗"
echo "║   aihelper Bootstrap                 ║"
echo "║   Mode: minimal                      ║"
echo "╚══════════════════════════════════════╝"
echo ""

echo "[1/6] Checking prerequisites..."
echo "  ✅ python3"
echo "  ✅ python3 ≥ 3.9 (3.12)"
echo "  ✅ git"
echo "  ⚠️  watchman (optional) -- Install: brew install watchman"
echo "  ✅ ollama"
echo ""

echo "[2/6] Creating environment directories..."
echo "  ✅ ~/.aihelper/{logs, persist, models}"
echo ""

echo "[3/6] Installing Python dependencies..."
echo "  ✅ pip packages installed"
echo ""

echo "[4/6] Pulling Ollama models..."
echo "  Pulling deepseek-coder:1.3b..."
sleep 0.5
echo "    ✅ deepseek-coder:1.3b"
echo "  Pulling phi4-mini:latest..."
sleep 0.3
echo "    ✅ phi4-mini:latest"
echo "  Pulling qwen3.5:4b-16k..."
sleep 0.4
echo "    ✅ qwen3.5:4b-16k"
echo ""

echo "[5/6] Setting up LaunchAgent (macOS)..."
echo "  ✅ LaunchAgent installed + loaded"
echo ""

echo "[6/6] Validating environment..."
echo "  Building aihelper cache..."
sleep 0.3
echo "  ✅ Cache built"
echo "  Starting daemon..."
sleep 0.2
echo "  ✅ Daemon started"
echo "  Running doctor..."
sleep 0.3
echo "  ✅ Health check passed"
echo ""

echo "╔══════════════════════════════════════╗"
echo "║   Bootstrap Complete                 ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  📁 aihelper:  /Users/user/aihelper"
echo "  🔧 Mode:     minimal"
echo "  🏠 Home:     ~/.aihelper/"
echo ""
echo "Quick start for any project:"
echo "  cd /path/to/your/project"
echo "  aihelper cache build"
echo "  aihelper route \"fix bug\""
echo ""

# Now run doctor
echo "──────────────────────────────────────────"
echo "  Running: aihelper doctor"
echo "──────────────────────────────────────────"
sleep 0.3

echo ""
echo "python3          ✅"
echo "git              ✅"
echo "watchman         ⚠️  (optional)"
echo "ollama           ✅"
echo "socket_dir       ✅"
echo "daemon_socket    ✅"
echo "daemon_health    ✅ ok"
echo "cache_writable   ✅"
echo "mcp_server       ✅"
echo "models_pulled    ✅"
echo "ramdisk          ⚠️  (optional)"
echo "permissions      ✅"
echo "log_dir          ✅"
echo ""
echo "overall: ok"
echo ""
echo "All systems ready."
