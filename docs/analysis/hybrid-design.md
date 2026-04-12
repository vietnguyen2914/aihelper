# Hybrid Design Findings

## Source comparison

### Mindforme

- Strongest pieces:
  - richer prompt rewriting
  - flow-oriented planning
  - cross-project keyword concepts
- Weaknesses:
  - less portable root handling
  - simpler index compatibility

### SignServer

- Strongest pieces:
  - disciplined documentation structure
  - adaptive keyword storage
  - clear operating model around prompt generation
- Weaknesses:
  - main runtime was narrower and less structured than `lms`

### LMS

- Strongest pieces:
  - best orchestration spine
  - root-aware target repo handling
  - structured JSON output
  - cleaner context bundling
- Weaknesses:
  - weaker docs and less expressive planning language

## Final synthesis used here

- Base orchestration: `lms`
- Planning and prompt framing: `mindforme`
- Docs and operating model: `signserver`

