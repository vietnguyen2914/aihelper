# Example: Parse Screenshot with Vision

## Goal
Extract UI state from a screenshot using minicpm-v.

## Step 1: Call vision model
```bash
ollama run minicpm-v:latest "Describe this screenshot in detail" --image screenshot.png
```

## Step 2: OCR text extraction
```bash
paddleocr --image screenshot.png --lang en
```

## Step 3: Route extracted info
```bash
aihelper route "fix the UI button position issue based on the screenshot analysis"
```

## Step 4: Analyze impact
```bash
aihelper impact-graph "ButtonComponent" --max-depth 2
```
