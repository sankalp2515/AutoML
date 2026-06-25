# Testing Guide — Phases 0–4 (production hardening)

How to verify every fix from the strict-review hardening work. Two kinds of check:
- **[AUTO]** — already proven by the test suite (`cd backend && pytest`). 96 tests.
- **[LIVE]** — needs the running stack / GPU / a real run; do these yourself.

## 0. Prep

```bash
cd automl-orchestrator
docker compose up -d                 # 8 services (worker is opt-in, see 4.4)
docker compose exec backend alembic upgrade head    # applies 0001 baseline + 0002 tenant_id
docker compose exec backend pytest -q                # expect: 96 passed
# UI http://localhost:3002 · API http://localhost:8000/docs · MLflow :5000 · Grafana :3001
```
For an existing DB created before Alembic: `alembic stamp 0001_baseline` first, then `alembic upgrade head` (see docs/MIGRATIONS.md).

---

## Phase 0.1 — Concurrency attribution race

**What was fixed:** run/agent identity moved from shared singletons to `contextvars`, so concurrent runs no longer cross-contaminate cost/decision attribution.

- **[AUTO]** `pytest tests/test_context.py` — proves isolation across interleaved tasks.
- **[LIVE]** Start **two runs at nearly the same time** (upload two datasets in two browser tabs). When both finish, open each run's **LLM Stats** tab and the `llm_calls` table:
  ```bash
  docker compose exec postgres psql -U automl -d automl -c \
    "select run_id, agent_name, count(*) from llm_calls group by 1,2 order by 1;"
  ```
  ✅ Pass: every `llm_calls` row's `run_id` matches a real agent in *that* run; no run shows another run's agents. Before the fix, attribution bled across the two runs.

---

## Phase 0.2 — Honest evaluation (true holdout + significance gate)

**What was fixed:** a real holdout is carved from raw data *before* any fitting/selection/tuning (new `data_splitter`), so the headline score is a genuine generalization estimate, not the selection CV. Iteration only continues if the gain beats the CV noise floor.

- **[AUTO]** `pytest tests/test_agents/test_iteration_gate.py tests/test_agents/test_templates.py` — gate logic + holdout-transform template (incl. multilabel) compile.
- **[LIVE] Holdout is real:** run **Iris**. On the run page → decision log / results:
  - ✅ The evaluator decision says **`(holdout)`** and "carved from raw data BEFORE any fitting".
  - ✅ The headline `final_score` is **≤** the old selection-CV number (~0.967). A modest drop is the bug being fixed.
- **[LIVE] Splitter ran:** the run shows a **data_splitter** step that reserved e.g. "120 train / 30 holdout (stratified)".
- **[LIVE] Small-data fallback:** run a tiny CSV (<60 rows). ✅ decision log says "dataset too small for a holdout → cross-validation"; `evaluation_basis = in_sample_split`; run still completes.
- **[LIVE] Significance gate:** on a run where iteration 2's gain is tiny, confirm it **stops** instead of iterating to the max (check `iteration_count`). 
- **[LIVE] Watch for fallbacks:** `docker compose logs backend | grep HOLDOUT_FALLBACK`. Any hit on a normal tabular/regression/binary run = a transform bug to report (multilabel may legitimately fall back).

---

## Phase 0.3 / Phase 1 — Sandbox is a real boundary

**What was fixed:** each execution runs in an isolated **spawn** child process with a hard wall-clock kill (no more main-thread `signal.alarm`); the container has no internet, no host port, dropped capabilities.

- **[AUTO]** `pytest tests/test_sandbox/test_screen.py` — AST screen blocks os/eval/dunder-walks, allows ML imports.
- **[LIVE] No internet egress (the key security check)** — this must **FAIL/hang**, proving isolation:
  ```bash
  docker compose exec sandbox python -c "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)"
  ```
  ✅ Pass: connection error / timeout (sandbox cannot reach the internet).
- **[LIVE] Not exposed to host:** `curl http://localhost:8001/health` → ✅ connection refused (no host port). Backend still reaches it internally: `docker compose exec backend curl -s http://sandbox:8001/health` → `{"status":"ok"...}`.
- **[LIVE] Hard timeout / crash isolation:**
  ```bash
  docker compose exec backend python - <<'PY'
  import asyncio, httpx
  async def call(code, t): 
      async with httpx.AsyncClient(timeout=60) as c:
          r = await c.post("http://sandbox:8001/execute", json={"code":code,"run_id":"t","timeout":t,"restricted":False})
          print(r.json()["error"][:60] or "ok")
  asyncio.run(call("while True: pass", 3))    # ✅ "Execution timed out ... (process killed)"
  asyncio.run(call("RESULT=1+1", 5))          # ✅ ok — service still alive after the kill
  PY
  ```
- **[LIVE] GPU + plots still work under cap_drop:** run a normal pipeline → ✅ completes, XGBoost trains, evaluation plots (confusion matrix / PR curve) appear in the artifacts. If matplotlib errors, check the `MPLCONFIGDIR`/`HOME` env in compose.
- **[LIVE] /health stays responsive during a long run** (loop no longer blocked): while a run is mid-evaluation, `docker compose exec backend curl -s http://sandbox:8001/health` returns promptly.

---

## Phase 2 — Universal agentic self-repair

**What was fixed:** when a template fails, the *failing agent writes and runs its own corrected code* (template-first, agentic fallback) — no agent dies on a template error. Happy path makes zero extra LLM calls.

- **[AUTO]** `pytest tests/test_agents/test_agentic_fallback.py` — success = no-op/no-LLM; failure = correct delegation.
- **[LIVE] Happy path unchanged:** a normal Iris/Titanic run completes with no "writing a fix" messages and the same LLM-call count as before.
- **[LIVE] Fault injection (the real test):** temporarily break one template to force the repair path. E.g. in `backend/app/agents/eda_agent.py` inside `EDA_CODE_TEMPLATE`, introduce a deliberate error (e.g. reference an undefined var), restart backend, run a dataset. Expected:
  - ✅ Live log shows "**Agent writing a fix (1/3)…**".
  - ✅ The run **continues past EDA** instead of failing.
  - ✅ A decision-log/cookbook entry records the working fix (`backend/cookbook/`).
  - Revert your deliberate break afterward.
- **[LIVE] TS leakage guard:** if a time-series run triggers repair, inspect the generated code in the notebook/decision log → ✅ it uses `TimeSeriesSplit`/temporal split, never random `KFold`.

---

## Phase 3 — No hardcoded ML decisions (metric registry + doctrine)

**What was fixed:** the metric vocabulary is a single source (`core/metric_registry.py`); the framer prompt is derived from it (not hand-typed); baseline scorer resolution uses it. UI copy corrected.

- **[AUTO]** `pytest tests/test_agents/test_metric_registry.py` — scorer parity with the old map + framer prompt is registry-derived.
- **[LIVE] Metric choice still adapts:** run three goals and check the framer's chosen `primary_metric`:
  - "predict fraud (rare)" → ✅ `recall` or `pr_auc`; "predict house price" → ✅ `rmse`/`mae`; an Iris-style 3-class goal → ✅ `f1`/`accuracy` (never a binary-only metric).
- **[LIVE] Single source works:** (sanity) add a metric to `metric_registry._METRICS`, restart, open `/docs` or the framer prompt — the new metric appears in the framer's allowed list with **no prompt edit**. Revert.
- **[LIVE] Honesty:** homepage pillar I no longer says "No templates, no fixed recipes" — it now describes template-first execution with agent-written fixes.

---

## Phase 4 — Multi-tenant foundation

**What was fixed:** opt-in per-tenant API keys; runs owned by a tenant; cross-tenant access denied; per-tenant active-run quota; opt-in durable job queue. **Default (no keys) = unchanged single-tenant behavior.**

- **[AUTO]** `pytest tests/test_api/test_tenancy.py` — public-mode default, key resolution, malformed-map ignored, cross-tenant query isolation, quota counts only active.
- **[LIVE] Default mode unchanged:** with no `TENANT_API_KEYS`, everything works exactly as before (no API key needed).
- **[LIVE] Tenant isolation:** set in `.env`:
  ```
  TENANT_API_KEYS={"key_a":"acme","key_b":"globex"}
  ```
  restart backend. Then:
  - Create a run as acme: `curl -H "X-API-Key: key_a" -F file=@iris.csv -F user_goal="classify species please" http://localhost:8000/api/v1/runs` → 201, note the id.
  - ✅ acme can read it: `curl -H "X-API-Key: key_a" http://localhost:8000/api/v1/runs/<id>` → 200.
  - ✅ globex **cannot**: `curl -H "X-API-Key: key_b" http://localhost:8000/api/v1/runs/<id>` → **404**.
  - ✅ no/invalid key on create → **401**.
  - ✅ `GET /api/v1/runs` returns only the caller's runs.
- **[LIVE] Quota:** set `QUOTA_MAX_ACTIVE_RUNS_PER_TENANT=1`, restart. Start one run, immediately start a second for the same tenant → ✅ second returns **429**.
- **[LIVE] Durable queue (opt-in):** set `USE_JOB_QUEUE=true` in `.env`, then:
  ```bash
  docker compose --profile worker up -d worker
  ```
  Start a run, then `docker compose restart backend` mid-run → ✅ the run still completes (the worker, not the API process, is executing it). `docker compose logs worker` shows it picked up the job.

---

## Quick regression checklist (run after any change)

```bash
cd backend && pytest -q          # 96 passed
docker compose exec sandbox python -c "import urllib.request;urllib.request.urlopen('https://example.com',timeout=5)"  # must fail
# one full Iris run → completes, evaluation_basis=holdout, plots present
```
