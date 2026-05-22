#!/usr/bin/env bash
# Demo: Patch Planning with Confidence Scoring
set -euo pipefail

AIHELPER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bin/aihelper"
DEMO="$AIHELPER/demo"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   aihelper Patch Planning Demo       ║"
echo "║   AST-aware patch planning           ║"
echo "║   Confidence scoring                 ║"
echo "║   Safe apply workflow                ║"
echo "╚══════════════════════════════════════╝"
echo ""

echo "$ aihelper patch-plan --task \"fix null pointer in PaymentService\" --files src/PaymentService.java"
sleep 0.3

# Simulate patch-plan output
echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Patch Plan                         ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Task: fix null pointer in PaymentService"
echo "---"
echo "--- a/src/PaymentService.java"
echo "+++ b/src/PaymentService.java"
echo "@@ -15,6 +15,9 @@ public boolean processPayment(String orderId, double amount) {"
echo "     if (amount <= 0) {"
echo "         throw new IllegalArgumentException(\"Amount must be positive\");"
echo "     }"
echo "+    // Guard against null orderId"
echo "+    if (orderId == null || orderId.isEmpty()) {"
echo "+        throw new IllegalArgumentException(\"Order ID must not be null\");"
echo "+    }"
echo "     if (transactions.containsKey(orderId)) {"
echo "         throw new IllegalStateException(\"Order already processed\");"
echo ""
echo "---"
echo "Changes: 1 file, +5 lines, -0 lines"
sleep 0.5

echo ""
echo "──────────────────────────────────────────"
echo "  Confidence Scoring"
echo "──────────────────────────────────────────"
echo ""

echo "$ aihelper confidence --patch-file patch.diff --files src/PaymentService.java"
sleep 0.3

echo ""
echo "Factor              │ Score  │ Detail"
echo "────────────────────┼────────┼──────────────────────────"
echo "syntax              │ 1.0    │ Patch applies cleanly"
echo "file_count          │ 1.0    │ Single file change"
echo "symbol_ambiguity    │ 1.0    │ No naming conflicts"
echo "api_changes         │ 1.0    │ No public API broken"
echo "tests_affected      │ 0.8    │ No test file modified"
echo "────────────────────┼────────┼──────────────────────────"
echo "overall             │ 0.96   │ AUTO-APPLY SAFE ⚡"
echo ""

sleep 0.3

echo "──────────────────────────────────────────"
echo "  Apply (with safeguards)"
echo "──────────────────────────────────────────"
echo ""

echo "$ aihelper safe-apply --patch-file patch.diff --auto-apply"
sleep 0.2

echo "  ✅ Git snapshot created"
echo "  ✅ Patch applied via git apply"
echo "  ✅ Syntax validated"
echo "  ✅ Rollback ready"
echo ""
echo "  aihelper Safe Apply: 0.3ms planning → 0.96 confidence → safe apply"
echo ""
