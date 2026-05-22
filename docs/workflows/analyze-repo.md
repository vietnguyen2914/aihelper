# Analyze Repository

## Flow
```
Cache build → Symbol graph → Intent routing → Compact context
```

## Steps
```bash
# 1. Build project index
aihelper cache build

# 2. Check freshness
aihelper cache status

# 3. Explore symbols
aihelper symbol find "PaymentService"
aihelper symbol context "processPayment"

# 4. Route analysis intent
aihelper route "understand payment flow architecture"

# 5. Get compact context
aihelper context "payment flow"

# 6. Browse dependencies
aihelper deps "PaymentService"
```
