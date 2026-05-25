# Changelog

All notable changes to aihelper will be documented here.

This project follows a lightweight release-note style. Dates use `YYYY-MM-DD`.

## Unreleased

### Added

- Windows support foundation: PowerShell/CMD launchers, PowerShell bootstrap,
  Windows CI smoke job, and Windows install docs.
- Portable daemon IPC: Unix sockets remain on macOS/Linux; Windows uses an
  auto-detected TCP loopback endpoint.
- Contributor guide for focused workflow-driven pull requests.
- Release notes for v0.0.6.
- Blog draft explaining semantic routing versus giant prompts.

### Changed

- README positioning now leads with the "Stop sending giant prompts" narrative.
- Demo workflow previews use a wider table layout for better GitHub readability.
- OCR and diagnostics GIF demos were regenerated at a shorter, more readable size.
- Diagnostics and document-pipeline temp paths are more portable across platforms.

## v0.0.6 - 2026-05-23

### Added

- OSS onboarding assets: README visuals, demo GIFs, benchmark charts, issue templates,
  PR template, funding metadata, installation docs, and workflow examples.
- Architecture SVG plus runtime map.
- Benchmark visuals for daemon latency, token reduction, and local model memory tiers.
- Contributor guide and changelog.

### Highlights

- Semantic routing replaces broad repo scans with compact context.
- Daemonized runtime removes repeated Python startup overhead.
- Patch-first workflows connect diagnostics, context, confidence scoring, and safe apply.
