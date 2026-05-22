#!/usr/bin/env bash
# Demo: OCR / Screenshot Parse
set -euo pipefail

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   aihelper OCR Screenshot Demo       ║"
echo "║   Multimodal orchestration           ║"
echo "╚══════════════════════════════════════╝"
echo ""

echo "$ aihelper capability-route \"Extract text from payment-error.png\" --file-path screenshots/payment-error.png"
sleep 0.3

echo ""
echo "Input classification:"
echo "  type: image (confidence: 0.95)"
echo "  pipeline: minicpm-v → PaddleOCR → qwen3.5:4b-16k"
echo ""

echo "──────────────────────────────────────────"
echo "  Step 1: OCR Text Extraction"
echo "──────────────────────────────────────────"
echo ""
echo "$ paddleocr --image screenshots/payment-error.png --lang en"
sleep 0.3
echo ""
echo "Extracted text:"
echo "  ┌─────────────────────────────────────────┐"
echo "  │ Payment Error                           │"
echo "  │                                         │"
echo "  │ Transaction #TX-2024-8912 failed        │"
echo "  │ Error: NullPointerException             │"
echo "  │ at PaymentService.processPayment()      │"
echo "  │                                         │"
echo "  │ [OK]                         [Retry]    │"
echo "  └─────────────────────────────────────────┘"
echo ""

sleep 0.3

echo "──────────────────────────────────────────"
echo "  Step 2: Vision Analysis"
echo "──────────────────────────────────────────"
echo ""
echo "$ ollama run minicpm-v:latest \"Describe this screenshot\" --image screenshots/payment-error.png"
sleep 0.4
echo ""
echo "Vision analysis:"
echo "  → Payment error dialog detected"
echo "  → Transaction ID: TX-2024-8912"
echo "  → Error type: NullPointerException"
echo "  → Source: PaymentService.processPayment()"
echo "  → Action buttons: OK, Retry"
echo ""

sleep 0.3

echo "──────────────────────────────────────────"
echo "  Step 3: Structured Extraction"
echo "──────────────────────────────────────────"
echo ""
echo "Structured result:"
echo "{"
echo "  \"screen\": \"payment_error_dialog\","
echo "  \"transaction_id\": \"TX-2024-8912\","
echo "  \"errors\": ["
echo "    {"
echo "      \"type\": \"NullPointerException\","
echo "      \"source\": \"PaymentService.processPayment()\","
echo "      \"severity\": \"CRITICAL\""
echo "    }"
echo "  ],"
echo "  \"recommended_action\": \"inspect PaymentService.processPayment() for null orderId\""
echo "}"
echo ""

sleep 0.3

echo "──────────────────────────────────────────"
echo "  Step 4: Semantic Routing"
echo "──────────────────────────────────────────"
echo ""
echo "$ aihelper route \"fix NullPointerException in PaymentService based on screenshot analysis\""
sleep 0.2
echo ""
echo "→ Intent: bugfix"
echo "→ Context: PaymentService.java + error trace"
echo "→ Target: add null check for orderId parameter"
echo "→ Confidence: 0.91"
echo ""
echo "Full pipeline: Screenshot → OCR → Vision → Extraction → Route → Fix"
echo ""
