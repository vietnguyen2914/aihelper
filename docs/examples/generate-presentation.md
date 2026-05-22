# Example: Generate Architecture Presentation

## Goal
Generate a PPTX presentation from project context.

## Step 1: Get project context
```bash
aihelper context "architecture overview"
```

## Step 2: Generate Mermaid diagram
```bash
cat << 'DIAGRAM' | aihelper generate_mermaid
graph TD
    A[Client] --> B[API Gateway]
    B --> C[Service A]
    B --> D[Service B]
    C --> E[(Database)]
DIAGRAM
```

## Step 3: Generate Vega-Lite chart
```bash
cat << 'CHART' | aihelper vega_chart
{
  "data": [{"module":"A","latency":1.2},{"module":"B","latency":0.3}]
}
CHART
```

## Step 4: Generate presentation
```bash
aihelper generate_presentation \
  --title "Architecture Review Q2" \
  --slides '[
    {"title":"Overview","bullets":["Microservices","Event-driven"]},
    {"title":"Latency","content":"Average: 0.3ms via daemon"}
  ]' \
  --output /tmp/architecture-review.pptx
```
Uses Marp to render markdown → PPTX.

## Step 5: Convert if needed
```bash
pandoc /tmp/output.md -t pptx -o /tmp/deck.pptx
# or
soffice --headless --convert-to pdf /tmp/deck.pptx
```
