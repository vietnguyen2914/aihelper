# Example: Fix PHP Bug with Semantic Routing

## Goal
Fix a null pointer exception in a PHP UserService.

## Step 1: Build cache
```bash
cd /path/to/your/project
aihelper cache build
```

## Step 2: Route the task
```bash
aihelper route "fix null pointer in UserService.getUser when userId is empty"
```
The router detects the intent as `bugfix` and sets up context focusing on error traces, recent changes, and test files.

## Step 3: Symbol lookup
```bash
aihelper symbol find "getUser"
```
Returns: file location, line number, signature, and all callers.

## Step 4: Generate patch plan
```bash
aihelper patch-plan "add null check for userId before database query" --file src/UserService.php
```
Creates a unified diff patch.

## Step 5: Analyze structural impact
```bash
aihelper structural-diff --patch-file /tmp/aihelper-patch.diff
```
Detects: function signature unchanged, new return type added, no SQL changes. Risk level: LOW.

## Step 6: Score confidence
```bash
aihelper confidence --patch-file /tmp/aihelper-patch.diff --files src/UserService.php
```
Scores: syntax=1.0, file_count=1.0, symbol_ambiguity=1.0 → overall=0.95 → **auto-apply safe**.

## Step 7: Apply
```bash
aihelper safe-apply --patch-file /tmp/aihelper-patch.diff --files src/UserService.php --auto-apply
```
A snapshot is created before applying. Post-apply validation runs.
