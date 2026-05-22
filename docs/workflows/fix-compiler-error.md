# Fix Compiler Error

## Flow
```
Diagnostics → Semantic routing → Patch plan → Confidence scoring → Safe apply
```

## Steps
```bash
# 1. Collect diagnostics
aihelper diagnostics --file-path src/UserService.php

# 2. Route the error context
aihelper route "fix TypeError in UserService.getUser"

# 3. Generate patch
aihelper patch-plan "add null check" --file src/UserService.php

# 4. Analyze impact
aihelper structural-diff --patch-file /tmp/patch.diff

# 5. Score confidence
aihelper confidence --patch-file /tmp/patch.diff --files src/UserService.php

# 6. Apply (auto if score >= 0.85)
aihelper safe-apply --patch-file /tmp/patch.diff --files src/UserService.php --auto-apply
```
