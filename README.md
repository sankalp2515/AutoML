<div align="center">

# 🧠 AutoML Orchestrator

**Upload a CSV, describe your goal in plain English — ten LLM-driven agents audit, frame, engineer, train, tune, and evaluate a model, then hand you a deployed prediction endpoint, drift monitoring, and a notebook that explains every decision.**

*The LLM proposes; sklearn disposes.* Every agent decision is verified by execution — never trusted on the model's word.

![CI](https://github.com/sankalp2515/AutoML/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![LangGraph](https://img.shields.io/badge/LangGraph-stateful%20agents-orange)
![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen)
![Docker](https://img.shields.io/badge/docker--compose-9%20services-2496ED)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

---

## Table of Contents
- [Why this exists](#why-this-exists)
- [What makes it different](#what-makes-it-different)
- [Architecture](#architecture)
- [The 10 agents](#the-10-agents)
- [Design principles (the golden rules)](#design-principles-the-golden-rules)
- [Tech stack](#tech-stack)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Production hardening](#production-hardening)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Project layout](#project-layout)

## Why this exists

Most "AutoML" tools are black boxes: they hand you a model and a score, and you have
to trust it. Most "LLM agent" demos are the opposite: impressive autonomy, zero
reliability, and a habit of hallucinating results. This project takes a deliberate
middle path — **agentic decisions, deterministic execution, and empirical verification
at every step** — to produce a model a stakeholder can actually audit.

You give it a spreadsheet and a sentence. It gives you a trained, deployable model,
honest hold-out metrics, SHAP explanations, drift monitoring, and a narrated Jupyter
notebook proving how it got there.

## What makes it different

| | This project | Typical AutoML | Typical LLM-agent demo |
|---|---|---|---|
| **Decisions** | LLM, from the data + your goal | Fixed heuristics | LLM |
| **Execution** | Vetted code in a locked-down sandbox | Library internals | LLM-written, unsandboxed |
| **Trust model** | Every claim verified by measured CV / hold-out | "Trust the score" | "Trust the model" |
| **Honesty** | Score on an untouched hold-out carved *before* any fitting | Often leaks selection into the score | N/A |
| **Auditability** | Per-decision log + MLflow + evidence notebook | Limited | None |
| **Failure handling** | The failing agent rewrites and re-runs its own code | Crash | Crash / hallucinate |

Inspired by agentic ML-engineering systems like **MLE-STAR**, but with the opposite
trade-off: instead of letting agents write arbitrary code (maximal novelty, minimal
reliability), the action space is bounded by vetted templates and a curated model/metric
registry — **floor reliability over ceiling novelty** — with an agentic self-repair path
for the edge cases templates don't cover.

## Architecture

```
                       ┌─────────────────────────────────────────────┐
 Browser (Next.js) ───►│  BACKEND (FastAPI)                          │
   localhost:3002      │  - REST + WebSocket live progress           │
                       │  - LangGraph orchestrator (10 agents)       │
                       │  - Multi-provider LLM client (retry +       │
                       │    fallback + rate-limit cooldown)          │
                       └──────┬──────────────┬───────────────────────┘
                writes code   │              │  tracks everything
                              ▼              ▼
                       ┌────────────┐  ┌──────────────────────────┐
                       │  SANDBOX   │  │ Postgres · Redis · MLflow │
                       │ isolated:  │  │ Prometheus · Grafana      │
                       │ no network,│  └──────────────────────────┘
                       │ non-root,  │
                       │ GPU, hard  │   Agents emit DECISIONS (JSON); the sandbox
                       │ timeouts   │   EXECUTES vetted code. The LLM never sees raw
                       └────────────┘   data rows — only statistical profiles.
```

## The 10 agents

Run as a stateful LangGraph DAG with one bounded feedback loop and fail-fast edges:

1. **Data Auditor** — profiles the CSV; verdict usable / warn / abort
2. **Problem Framer** — goal → task type, target, primary metric (from a registry-derived menu)
3. **Data Splitter** — carves a true hold-out from raw data *before* any fitting (honest evaluation)
4. **Baseline Builder** — simplest model first → the performance floor everything justifies itself against
5. **EDA + Error Analysis** — targeted EDA focused on *why the baseline fails*
6. **Preprocessor** — per-column impute/encode/scale → a serialized sklearn `ColumnTransformer`
7. **Feature Engineer** — hypothesis-driven features; each CV-tested; only positive lift survives
8. **Model Selector** — picks 2–3 candidates from the model registry; all trained; best CV wins
9. **Tuner** — Optuna search on the winner (GPU for XGBoost)
10. **Evaluator** — hold-out metrics, SHAP, calibration, threshold selection, slice analysis
11. **Exporter** — packages the inference pipeline + LLM-written evidence notebook + model card + API scaffold

*Iteration:* Evaluator → Feature Engineer again, but only if the gain exceeds the
measured CV noise floor (no chasing fold noise), capped at 3 iterations.

## Design principles (the golden rules)

| Rule | Why |
|---|---|
| **Agents decide, the sandbox executes** | LLM sees only statistical profiles — privacy, cost, reliability |
| **Baseline first** | A 30-second LogReg is the floor every later step must beat |
| **The sklearn Pipeline is the contract** | Same object trains and serves — no train/serve skew |
| **Hold-out carved before fitting** | The reported score is a true generalization estimate, not the selection CV |
| **Every decision logged with reasoning** | `decision_logs` + MLflow + the evidence notebook |
| **No hardcoded ML decisions** | The LLM picks metrics/strategies/features/models; code owns only contracts & mechanics |

## Tech stack

**Backend:** Python 3.11, FastAPI, LangGraph, SQLAlchemy (async) + Alembic, Postgres, Redis, arq (durable queue)
**ML (sandbox):** scikit-learn, XGBoost, imbalanced-learn, SHAP, SciPy, pandas/numpy
**LLM:** provider-agnostic OpenAI-compatible client — Groq / Gemini / OpenRouter / DeepSeek / Ollama / Anthropic, with retry + fallback chain + rate-limit cooldown
**Tracking & ops:** MLflow (experiments + model registry), Prometheus + Grafana, structlog
**Frontend:** Next.js 14, Tailwind, optional Supabase auth
**Infra:** Docker Compose (9 services), GPU passthrough to the sandbox

## Quickstart

```bash
git clone <your-repo-url> && cd automl-orchestrator
cp .env.example .env          # add at least one LLM key (GROQ_API_KEY is free)

docker compose up -d          # backend, sandbox, postgres, redis, mlflow, prometheus, grafana, frontend
docker compose exec backend alembic upgrade head

# UI         → http://localhost:3002
# API docs   → http://localhost:8000/docs
# MLflow     → http://localhost:5000
# Grafana    → http://localhost:3001
```

Upload a CSV on the home page, describe your goal, watch the agents work, then deploy
the model and call its prediction endpoint.

## Configuration

Key `.env` settings (all optional unless noted):

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` (+ `GEMINI_API_KEY`, …) | LLM providers; the fallback chain skips unconfigured ones |
| `TENANT_API_KEYS` | JSON `{api_key: tenant}` to enable multi-tenant isolation (empty = single-tenant) |
| `SUPABASE_JWT_SECRET` / `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Enable user login/signup |
| `USE_JOB_QUEUE` | Route runs through a durable arq worker (survives API restarts) |
| `QUOTA_MAX_ACTIVE_RUNS_PER_TENANT` | Per-tenant concurrency cap |
| `MAX_RUN_SECONDS` / `MAX_DATASET_COLUMNS` | Resource guardrails |
| `CORS_ALLOW_ORIGINS` / `GRAFANA_USER` / `GRAFANA_PASSWORD` | Deployment hardening |

## Production hardening

This is a research-grade system that has been deliberately hardened toward a
multi-tenant product. Highlights:

- **Honest evaluation** — a hold-out is split from raw data before any agent fits, selects, or
  tunes; iteration is gated on statistical significance, not point estimates.
- **Sandbox is a real boundary** — generated code runs in a network-isolated, non-root,
  capability-dropped container, in a dedicated process with a hard wall-clock kill.
- **Concurrency-safe** — request-scoped context (no shared mutable state) so concurrent runs
  never cross-contaminate cost/decision attribution.
- **Self-healing agents** — on a template failure the agent writes corrected code, runs it in
  the restricted sandbox, validates the result contract, and records the fix.
- **Resilient LLM layer** — retry + multi-provider fallback + a rate-limit cooldown circuit-breaker.
- **Multi-tenancy** — per-tenant API keys / Supabase JWT, row-level ownership enforced uniformly,
  per-tenant quotas.
- **Observability** — Prometheus metrics, Grafana dashboards, per-LLM-call token/cost/latency tracking.

See `docs/PRODUCTION_AUDIT.md` for the full severity-ranked readiness assessment.

## Testing

```bash
docker compose exec backend pytest -q          # 117 unit + integration tests
```

Coverage includes a **graph-level integration harness** that drives the real LangGraph
end-to-end (agent ordering, fail-fast, the significance gate, the iteration cap), template
render/compile guards, the state-contract guard, the metric-registry parity suite, auth/tenant
isolation, the sandbox safety screen, and the provider-cooldown circuit-breaker.

A zero-knowledge QA test plan (`docs/QA_TEST_PLAN.md`) covers live end-to-end verification.

## Roadmap

- [ ] Automated CI on real OpenML datasets with held-out scoring
- [ ] Persistent model server (kill the ~1s/prediction sandbox overhead)
- [ ] Scheduled / drift-triggered retraining
- [ ] HTTPS, secrets manager, dataset retention + at-rest encryption
- [ ] Quant-finance pipeline (purged/embargoed CV, walk-forward, Sharpe objectives)

## Project layout

```
backend/      FastAPI app — agents/, core/ (llm, registries, auth, guardrails), api/, sandbox/, tests/
sandbox/      Isolated code-execution service (AST safety screen + process isolation)
frontend/     Next.js 14 UI (upload, live run dashboard, notebook, deploy playground)
docs/         Project journal, architecture analyses, production audit, QA plan
docker-compose.yml
```

---

<div align="center">
<sub>Built as a study in trustworthy, agentic machine-learning automation.</sub>
</div>
