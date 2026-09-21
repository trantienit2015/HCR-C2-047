# HCR-C2-047 — Elderly Care Vital Anomaly & Family Notification Agent

> **Category**: Cat 2 (orchestrates a specific multi-step use case)
> **Industry**: HCR

## Overview

A care-facility monitoring system submits a resident's vital sign readings (heart rate, BP, SpO2, temperature, respiration). The agent validates the payload, loads the per-resident baseline **from InvocationContext only** (APPI Article 17 — 要配慮個人情報 is never persisted in State), detects anomalies (deterministic thresholds + statistical deviation), classifies severity (CRITICAL / WARNING / NORMAL; NORMAL exits with no notification), drafts a severity-appropriate family notification, dispatches it to the registered contact channel, and emits an anonymized audit summary with PHI stripped from the final response. Primary beneficiaries: care-facility staff and residents' families, addressing Japan's 介護士 workforce shortage and 介護保険制度 2025 monitoring mandates. Source of truth for scope / Cat: the corresponding scaffold proposal issue (tracked internally; not linked here so the repository stays publication-safe).

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and operational documentation
```

See `docs/` for the proposal, design, test specification, release notes and operation guide.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.

---

