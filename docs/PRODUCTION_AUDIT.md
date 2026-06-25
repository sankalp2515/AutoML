# Production-Readiness Audit (2026-06-18)

Strict pass over the system for a multi-tenant hosted product. Severity: 🔴 blocker
· 🟠 important · 🟡 nice-to-have. Status reflects work through Phases 0–5.

## Security

| # | Finding | Sev | Status |
|---|---|---|---|
| S1 | Sandbox ran as root, no network isolation, exposed on host | 🔴 | ✅ Fixed P1: `network internal`, no host port, `cap_drop ALL`, no-new-privileges, pids cap |
| S2 | No tenant isolation — any caller could read any run | 🔴 | ✅ Fixed P4: `tenant_id` + router-level `enforce_run_ownership` |
| S3 | No real user auth | 🟠 | ✅ Backend done P5 (Supabase JWT verify, sig+exp+aud). Frontend wired (needs your project) |
| S4 | `SECRET_KEY` default is a placeholder | 🟠 | ✅ Startup warning added (non-DEBUG); still SET a real value + secrets manager in prod |
| S5 | `read_only` rootfs / non-root user for sandbox | 🟠 | OPEN (opt-in stubs in compose) — enable + verify per lib |
| S6 | `eval()` of LLM feature formulas at inference | 🟢 | NOT A BUG — runs INSIDE the sandbox template (`PREDICT_CODE`) within the isolated container, with `{"__builtins__": {}}`. No backend-process risk |
| S7 | No HTTPS/TLS termination | 🟠 | OPEN — deploy behind a TLS reverse proxy / ingress (ops, not app code) |
| S8 | CORS hardcoded to localhost origins | 🟡 | ✅ Now `CORS_ALLOW_ORIGINS` env-configurable |

## Reliability

| # | Finding | Sev | Status |
|---|---|---|---|
| R1 | Concurrent-run attribution race (singletons) | 🔴 | ✅ Fixed P0.1 (contextvars) |
| R2 | `signal.alarm` sandbox timeout (main-thread only, blocked loop) | 🟠 | ✅ Fixed P1 (process isolation + hard kill) |
| R3 | Fire-and-forget runs die with the API process | 🟠 | ✅ Addressed P4 (opt-in durable arq queue) |
| R4 | LLM rate-limit storms: every agent re-tried Groq then fell back | 🟠 | ✅ Fixed: provider cooldown circuit-breaker |
| R5 | Single free-tier LLM key = no headroom for concurrent runs | 🟠 | ✅ `GEMINI_API_KEY` added by user; cooldown now falls back to it |
| R6 | No global per-run wall-clock budget (a run can loop on retries) | 🟡 | ✅ `MAX_RUN_SECONDS` cap (0=off) wraps `graph.ainvoke` |

## ML / data correctness

| # | Finding | Sev | Status |
|---|---|---|---|
| M1 | Reported score was the selection CV (optimistic) | 🔴 | ✅ Fixed P0.2 (true holdout + significance gate) |
| M2 | Bad LLM framing could crash/NaN a scorer | 🟠 | ✅ Fixed P5 (framing guardrail) |
| M3 | Binary decision threshold still picked on the holdout | 🟡 | OPEN (tracked) — select on a train validation split |
| M4 | Metric→scorer maps duplicated inside sandbox templates | 🟡 | OPEN (tracked) — migrate to a registry-rendered token (baseline already uses the registry) |
| M5 | No automated end-to-end test on real datasets | 🟠 | OPEN — build the OpenML CI integration harness |

## Data management

| # | Finding | Sev | Status |
|---|---|---|---|
| D1 | Hand-run `ALTER TABLE` migrations | 🟠 | ✅ Fixed P0.4 (Alembic) |
| D2 | Uploaded datasets stored unencrypted on a shared volume; no retention/TTL | 🟠 | OPEN — per-tenant prefix + retention policy + at-rest encryption for hosted |
| D3 | No dataset size guard beyond 500MB; very wide CSVs untested | 🟡 | ✅ `MAX_DATASET_COLUMNS` guard at upload (0=off) |
| D4 | Tracked build artifacts (`.pyc`) in git | 🟡 | ✅ Fixed P0.5 |

## Observability / ops

| # | Finding | Sev | Status |
|---|---|---|---|
| O1 | Prometheus + Grafana + structured logs + per-LLM-call cost | — | ✅ Strong already |
| O2 | Grafana ships with default admin creds + anonymous viewer | 🟠 | ✅ Creds + anon now env-driven (`GRAFANA_USER/PASSWORD/ANON_ENABLED`); set them in prod |
| O3 | No alerting (error rate, queue depth, quota breaches) | 🟡 | OPEN — add Prometheus alert rules |
| O4 | No health/readiness split; no graceful shutdown draining in-flight runs | 🟡 | OPEN |

## Top priorities before charging customers
1. **S4** real `SECRET_KEY` + secrets manager; **S6** move inference `eval` into the sandbox.
2. **R5** add a fallback LLM key; **M5** CI integration harness on real datasets.
3. **D2** dataset retention + encryption; **O2** Grafana creds.
4. Enable **S5** (read-only/non-root sandbox) and verify.
