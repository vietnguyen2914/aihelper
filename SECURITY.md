# Security Policy

## Supported Versions

aihelper is under active development. Security patches are provided for the latest stable release.

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < latest | :x:               |

To check your version:

```bash
git rev-parse HEAD
```

We recommend always running the latest commit from `main`.

---

## Reporting a Vulnerability

aihelper is a **local-first development tool**. It does not phone home, collect telemetry, or
transmit code to external servers unless you explicitly configure a cloud model endpoint.

If you discover a security issue — local injection, credential leakage in cache, unsafe patch
application, or anything else — **please report it privately** so we can fix it before disclosure.

### How to report

1. **Email:** [viet.nguyen2914@gmail.com](mailto:viet.nguyen2914@gmail.com)
2. **Subject prefix:** `[aihelper-security]`
3. **Include:**
   - A concise description of the issue
   - Steps to reproduce (command, input, OS, Python version)
   - Affected component (daemon, cache, patch planner, MCP bridge, etc.)
   - Any proof-of-concept or log output (omit sensitive/personal data)

If you use GitHub's private vulnerability disclosure:

1. Go to [github.com/vietnguyen2914/aihelper/security/advisories](https://github.com/vietnguyen2914/aihelper/security/advisories)
2. Click **New draft security advisory**
3. Fill in the details — it stays private until you publish

### Response timeline

| Timeframe | What to expect |
|-----------|----------------|
| **48 hours** | Acknowledgment of receipt |
| **3–5 days** | Initial triage and severity assessment |
| **7–14 days** | Patch development (depends on complexity) |
| **Day of patch** | Release with CVE assignment if applicable |

If you do not receive a response within 48 hours, please follow up via email.

---

## Scope

### In scope

- The `context_engine/` Python package
- Daemon IPC (Unix socket on macOS/Linux, TCP loopback on Windows)
- Cache persistence layer (`~/.aihelper/`)
- Patch planner and safe-apply logic
- MCP integration endpoints
- Editor context detection
- Shell launchers (`bin/aihelper`, `bin/aihelper.ps1`, `bin/aihelper.cmd`)

### Out of scope

- Third-party models (Ollama, cloud API providers) — report to their maintainers
- Editor plugins (Zed, VSCode, Codex, etc.) — report to the respective project
- Operating system vulnerabilities
- Dependency CVEs — we track these via automated Dependabot alerts

---

## Security-relevant features

aihelper includes several design decisions that reduce attack surface:

### Local-first by default

All core operations — routing, cache building, symbol indexing, patch planning, diagnostics,
confidence scoring — run **entirely offline**. No data leaves your machine.

Cloud model endpoints (DeepSeek, GPT, Gemini) are opt-in and require explicit configuration
of an API key. See [docs/INSTALLATION.md](docs/INSTALLATION.md) for secure key management.

### Isolated daemon transport

| Platform | Transport | Visibility |
|----------|-----------|------------|
| macOS / Linux | Unix socket (`~/.aihelper/aihelperd.sock`) | Owner-only |
| Windows | TCP loopback (`127.0.0.1`) | Localhost-only, not exposed externally |

The daemon **never** listens on external interfaces. Windows TCP metadata is written to
`%USERPROFILE%\.aihelper\aihelper.tcp.json` and is not shared with other users.

### Safe patch application

- Unified diff generation with `git apply` validation
- Rollback snapshots are taken before any auto-apply
- Confidence scoring prevents low-confidence patches from applying automatically
- Structural diff adds AST-level verification before file writes

### Cache isolation

The project cache (`<project-root>/.ai-cache/`) is scoped per-repository and never shared
across projects. Cache files contain symbol names, file paths, and dependency graphs — no
credentials, secrets, or personal data are indexed.

If your repository contains secrets in file paths or symbol names (discouraged), the cache
will reflect that. Practice standard secret hygiene regardless of tooling.

---

## Security best practices for users

1. **Run `aihelper doctor`** — it validates environment integrity and flags misconfigurations.
2. **Use credential-free path names** — avoid embedding API keys or passwords in file/directory names.
3. **Review patches before applying** — even with auto-apply, inspect the diff when working on sensitive code.
4. **Keep Python updated** — Python 3.9+; prefer 3.11+ for the latest security fixes.
5. **Verify file permissions** — `~/.aihelper/` should be readable only by you (`chmod 700` on macOS/Linux; NTFS ACLs on Windows).
6. **Pin Ollama versions** — if using local models, pin them in your bootstrap config to avoid unexpected model updates.

---

## Coordinated disclosure

We follow a standard 90-day coordinated disclosure window:

1. Reporter submits vulnerability (private)
2. Maintainer acknowledges and triages
3. Patch is developed and tested
4. Patch is released with a CVE (if applicable)
5. 90 days after patch release, full details are published

We will credit reporters in the release notes and changelog unless they request anonymity.

---

## Recognition

We maintain a list of security researchers who have helped improve aihelper's security posture.
To be credited in our acknowledgments, include your preferred name/handle in your report.

---

## Contact

- **Security email:** [viet.nguyen2914@gmail.com](mailto:viet.nguyen2914@gmail.com)
- **GitHub advisories:** [github.com/vietnguyen2914/aihelper/security/advisories](https://github.com/vietnguyen2914/aihelper/security/advisories)
- **PGP key:** Not yet provisioned — reachable via email + GitHub for now

---

*This policy will evolve as aihelper matures. Last updated: 2026-05-25.*
