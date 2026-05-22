#!/usr/bin/env bash
# Demo: Diagnostics → Patch
set -euo pipefail

AIHELPER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bin/aihelper"
DEMO="$AIHELPER/demo"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   aihelper Diagnostics → Patch Demo  ║"
echo "║   Diagnostics-aware retrieval        ║"
echo "║   Semantic context slicing           ║"
echo "║   Patch-first editing                ║"
echo "╚══════════════════════════════════════╝"
echo ""

echo "$ aihelper diagnostics --file-path src/PaymentService.java"
sleep 0.3

echo ""
echo "File: src/PaymentService.java"
echo "  3 issue(s) found"
echo ""
echo "  Error: NullPointerException risk at processPayment() line 23"
echo "    → orderId may be null"
echo "    → severity: HIGH"
echo ""
echo "  Warning: Race condition at transactions.put() line 26"
echo "    → HashMap is not thread-safe"
echo "    → severity: MEDIUM"
echo ""
echo "  Warning: Unused import java.util.HashMap"
echo "    → severity: LOW"
echo ""
sleep 0.5

echo ""
echo "──────────────────────────────────────────"
echo "  Semantic Routing with Diagnostics Context"
echo "──────────────────────────────────────────"
echo ""

echo "$ aihelper route \"fix compiler diagnostics in PaymentService\""
sleep 0.2
echo "→ Intent detected: bugfix"
echo "→ Priority: HIGH (NPE at runtime)"
echo "→ Scope: PaymentService.java (1 file, 39 lines)"
echo "→ Context: error_traces + callers + test coverage"
echo "→ Token budget: 750"
sleep 0.3

echo ""
echo "──────────────────────────────────────────"
echo "  Compact Context Assembly"
echo "──────────────────────────────────────────"
echo ""

echo "$ aihelper context \"compiler diagnostics for PaymentService\""
sleep 0.2
echo ""
echo "Compiled context (750 tokens):"
echo "  ├── File: PaymentService.java (39 lines)"
echo "  ├── Symbols: processPayment, validateTransaction, rollback"
echo "  ├── Dependencies: HashMap, Map"
echo "  └── Diagnostics: 3 issues (1 HIGH, 1 MEDIUM, 1 LOW)"
echo ""
echo "--- Without aihelper: 50,000+ tokens (full repo scan)"
echo "--- With aihelper:    750 tokens (sliced context)"
echo "--- Reduction:        98.5%"
sleep 0.3

echo ""
echo "──────────────────────────────────────────"
echo "  Generate Targeted Patch"
echo "──────────────────────────────────────────"
echo ""

echo "$ aihelper patch-plan --task \"fix null pointer and race condition\" --files src/PaymentService.java"
sleep 0.3

echo ""
echo "Generated patch plan:"
echo "--- a/src/PaymentService.java"
echo "+++ b/src/PaymentService.java"
echo "@@ -1,5 +1,6 @@"
echo " package com.example.payment;"
echo " "
echo "-import java.util.HashMap;"
echo "+import java.util.concurrent.ConcurrentHashMap;"
echo " import java.util.Map;"
echo " "
echo " public class PaymentService {"
echo "@@ -17,6 +18,9 @@ public boolean processPayment(String orderId, double amount) {"
echo "     if (amount <= 0) {"
echo "         throw new IllegalArgumentException(\"Amount must be positive\");"
echo "     }"
echo "+    if (orderId == null || orderId.isEmpty()) {"
echo "+        throw new IllegalArgumentException(\"Order ID required\");"
echo "+    }"
echo "     if (transactions.containsKey(orderId)) {"
echo ""
echo "---"
echo "Changes: 1 file, +6 lines, -1 line"
echo "Confidence: 0.94 → AUTO-APPLY SAFE"
echo ""
sleep 0.3

echo "──────────────────────────────────────────"
echo "  Without aihelper: manual debug → 15 min"
echo "  With aihelper:    diagnostics → patch → 8 seconds"
echo "──────────────────────────────────────────"
echo ""
