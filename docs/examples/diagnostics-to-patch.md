# Example: Generate Patch Plan from Diagnostics

## Goal

Take compiler/linter diagnostics → generate a patch plan automatically.

This demonstrates aihelper's **diagnostics → patch-plan** pipeline, which is one of the highest-leverage workflows.

## Step 1: Collect diagnostics

```bash
# From a file with errors
aihelper diagnostics src/Services/PaymentService.php
```

Output (abbreviated):

```
File: src/Services/PaymentService.php
  1 error(s), 2 warning(s)

  Error: Call to undefined method PaymentService::validateAmount()
    at src/Services/PaymentService.php:42

  Warning: Variable $currency might not be defined
    at src/Services/PaymentService.php:58

  Warning: Unused import CurrencyConverter
    at src/Services/PaymentService.php:3
```

## Step 2: Route with diagnostic context

```bash
aihelper route "fix undefined method validateAmount in PaymentService"
```

The intent router detects:
- **Intent:** `bugfix`
- **Context needed:** `error traces + recent changes + callers`
- **Confidence:** 0.87

It returns:
- The file's symbol graph (methods, properties)
- Related files that reference `PaymentService`
- Recent git changes touching this service

## Step 3: Symbol lookup

```bash
aihelper symbol find "validateAmount"
```

Returns:

```
Not found — method does not exist.
Similar methods in PaymentService:
  - validatePayment($order) at line 35
  - processRefund($amount) at line 78
```

## Step 4: Generate patch plan

```bash
aihelper patch-plan "add validateAmount method with proper signature" \
  --file src/Services/PaymentService.php
```

Creates a unified diff:

```diff
--- a/src/Services/PaymentService.php
+++ b/src/Services/PaymentService.php
@@ -39,6 +39,14 @@
         }
     }

+    /**
+     * Validate that the amount is positive and within allowed range.
+     *
+     * @param float $amount
+     * @return bool
+     */
+    public function validateAmount(float $amount): bool
+    {
+        return $amount > 0 && $amount <= self::MAX_AMOUNT;
+    }
+
     public function processRefund(float $amount): void
     {
```

## Step 5: Score confidence

```bash
aihelper confidence --patch-file /tmp/aihelper-patch.diff \
  --files src/Services/PaymentService.php
```

```
syntax:         1.0  (patch applies cleanly)
file_count:     1.0  (single file)
symbol_ambiguity: 1.0  (no naming conflicts)
api_changes:    1.0  (no public API broken)
tests_affected: 0.8  (no test file modified)

overall:        0.96 → AUTO-APPLY SAFE
```

## Step 6: Apply with safeguards

```bash
aihelper safe-apply --patch-file /tmp/aihelper-patch.diff \
  --files src/Services/PaymentService.php \
  --auto-apply
```

This:
1. Creates a git snapshot (rollback point)
2. Applies the patch via `git apply`
3. Validates syntax (`php -l`)
4. Reports success or rolls back

## Step 7: Fix remaining warnings

```bash
aihelper route "fix unused import CurrencyConverter in PaymentService"
```

The intent router detects `refactor` and generates a targeted removal patch.

## Full automation (one-liner)

```bash
aihelper diagnostics src/Services/PaymentService.php \
  | grep "^  Error:" \
  | while IFS= read -r line; do
      task=$(echo "$line" | sed 's/^  Error: //')
      aihelper patch-plan "$task" --file src/Services/PaymentService.php
    done
```

## Key takeaway

The **diagnostics → patch-plan** pipeline closes the loop between error detection and automated fixing. Instead of manually interpreting diagnostics, let aihelper do the analysis and propose concrete patches.
