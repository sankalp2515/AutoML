# AutoML Orchestrator — Project Journal

> **Living document.** Updated alongside every feature, fix, and architecture change.
> Read this top-to-bottom and you understand the entire project without opening code.

Last updated: **2026-06-19** (Bug fixes from live QA + LLM cooldown + guardrails + Supabase auth backend)

### Phase 5 — live-QA fixes, reliability, guardrails, auth (2026-06-19)
From the user's first live test pass.
- **Bug: arq worker crash** (`'staticmethod' object has no attribute 'host'`) — `WorkerSettings.redis_settings`
  must be a `RedisSettings` INSTANCE, not a method. Fixed in `app/worker.py`.
- **Bug: pytest collection** `FileNotFoundError /sandbox/main.py` in the backend container — the sandbox
  source isn't mounted there. `test_screen.py` now `pytest.skip(allow_module_level=True)` when absent.
- **Bug/latency: LLM fallback storm** (the likely cause of "2nd concurrent run didn't finish") — every
  agent re-tried Groq (2 retries + Retry-After) THEN fell back, per agent, exhausting the free TPM budget
  and serializing concurrent runs. **Fixed:** process-wide provider **cooldown circuit-breaker** in
  `core/llm.py` — a 429 cools that provider (Retry-After or 60s) so all subsequent agents/runs skip
  straight to the fallback; if all providers are cooling, wait once for the soonest. `test_llm_cooldown.py`.
  **User action still recommended:** add a free `GEMINI_API_KEY` so the cooldown has a fallback with headroom.
- **Guardrails** `core/guardrails.py`: `sanitize_user_goal` (strip control chars, collapse ws, cap 2000 —
  wired into create_run) and `validate_and_fix_framing` (clamps LLM framing: invalid task→binary, metric
  not-valid-for-task→registry default, threshold→[0,1], flags missing target) — wired into problem_framer.
  Prevents a bad LLM decision from crashing/NaN-ing a scorer downstream. `test_guardrails.py`.
- **Supabase auth (backend)** `core/auth.py`: opt-in `SUPABASE_JWT_SECRET` → verify `Authorization: Bearer`
  access tokens (HS256, signature+exp+audience), map user `sub` → tenant `user:<uuid>`; integrated into
  `current_tenant` + `enforce_run_ownership` alongside the API-key path. pyjwt added. `test_supabase_auth.py`
  (6 tests: valid/expired/wrong-secret/wrong-aud/missing/disabled — all pass).
- **Supabase auth (frontend, UNVERIFIED — needs your project + npm i):** `frontend/lib/supabase.ts`,
  `app/login/page.tsx`, token attached at the `apiRequest` choke point, `@supabase/supabase-js` in package.json.
- **Production audit** `docs/PRODUCTION_AUDIT.md` — full severity/status table; top open items: real SECRET_KEY
  + secrets manager, move inference `eval` into the sandbox, add fallback LLM key, CI integration harness,
  dataset retention/encryption, Grafana creds.
### Frontend UX overhaul + Supabase auth fix (2026-06-26)
From user feedback (palette/naming/layout + auth not working). UNVERIFIED (no Next build locally).
- **Auth fix (backend, VERIFIED):** Supabase JWT verification now supports BOTH legacy HS256 (shared
  secret) AND new-project asymmetric RS256/ES256 via JWKS (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`).
  `_supabase_enabled` true if SUPABASE_JWT_SECRET or SUPABASE_URL set. cryptography added. JWKS RS256 test
  (mocked client) + conftest now isolates tests from dev .env (forces public mode). 170 tests pass.
- **Palette:** re-themed via CSS-variable VALUES only (no class renames) — warm gold/cream "Obsidian Atelier"
  → technical **slate surfaces + indigo accent** (emerald success, red error), dark + light. btn-gold text→white;
  Navbar underline + favicon → indigo.
- **Naming (de-luxury):** Commission→New Model, Gallery→Runs, "Atelier · ten agents"→"Automated ML pipeline",
  "Commission a Model"→"Train a Model", "Begin the Work"→"Run Pipeline", "The Studio"→"Pipeline Type",
  "i. The Dataset/ii. The Intention"→"1. Dataset/2. Goal", "The Process—Ten Hands"→"The Pipeline—10 Agents",
  "Instruments"→"Dashboards", runs-page "Commissioned Works"→"Your Runs", ThemeToggle titles.
- **Layout:** landing hero restructured to a **two-column grid** (headline left, upload card right) so the
  primary action is ABOVE THE FOLD (was: scroll past a huge centered hero).
- **Auth UX:** new `AuthGate` (redirects to /login when auth enabled + not signed in; no-op in public mode) wired
  into layout; new `AuthMenu` (Navbar email + Sign out / Sign in link). @opentelemetry/api added (supabase optional dep).
- **NEEDS LIVE VERIFY:** `npm install` + frontend rebuild; confirm it compiles (I can't run next build); login→redirect,
  profile/logout, palette, layout. If tsc errors appear, they'll be small typing fixes.

### Observability — 5-layer LLM-app coverage (2026-06-26)
Audited against the standard 5 layers; closed the gaps:
- **Layer 1 (request logging):** request-id middleware in main.py — assigns/propagates `X-Request-ID`,
  binds it to a contextvar, logs every request (method/path/status/latency_ms/request_id), records
  `http_requests_total` + `http_request_duration_seconds` (path normalized to avoid label-cardinality blowup).
- **Layer 2 (prompt/context):** `llm.complete` logs `llm_request` with a **prompt_version** (sha256 of the
  system prompt → changes when the template changes), system/user char counts + a 200-char preview;
  agentic path logs `context_retrieved` (cookbook RAG chunks + provenance).
- **Layer 4 (cache metrics):** `llm_cache_requests_total` + `llm_cache_hits_total` → hit-ratio. (first-token
  latency = N/A, non-streaming; hallucination feedback = empirical validation, no user-feedback loop yet.)
- **Layer 5 (correlation):** `request_id` threaded through `llm_request`/`llm_call` logs → a request is
  traceable across API→orchestrator→sandbox→LLM. (Full OpenTelemetry exporter = documented follow-on.)
- **Layer 3** was already strong (AgentStep, decision_logs, repair counters, sandbox timing).
- `test_observability.py` (5 tests). **169 tests pass.**

### DL-0 — PyTorch foundation (2026-06-26)
Deep-learning integrated as registry entries, NOT a new graph (per docs/analysis/12).
- **`sandbox/automl_dl/`** — sklearn-compatible PyTorch estimators `TorchMLPClassifier` /
  `TorchMLPRegressor` (configurable MLP, GPU + AMP, internal val split + early stopping,
  internal input/target standardization). Because inference also runs in the sandbox image,
  the **existing joblib pipeline serializes/serves them with zero changes** — no state_dict path.
  **Key simplification:** the training loop lives INSIDE the estimator, so it rides the existing
  model_selector/tuner/evaluator templates — no separate DL training template.
- **Verified locally on GPU** (`test_automl_dl.py`, 5 tests): fit/predict/proba, sklearn clone +
  get_params, runs under `cross_val_score`, and the **joblib round-trip serves identically** (regressor
  R²≈0.99 at 300 epochs — standardization works). torch 2.6.0+cu124, CUDA available on this box.
- **Registry**: `TorchMLP` entry (`installed=False` until image baked; gpu=True) + `_TORCHMLP_SPACE`
  (lr/dropout/weight_decay). Correctly excluded from the installed menu, shown in recommendations.
- **Wiring**: model_selector template guarded-imports the estimators; sandbox `requirements.txt` adds
  torch (CUDA index); Dockerfile copies `automl_dl` + sets PYTHONPATH; AST whitelist adds torch/automl_dl.
- **164 tests pass.**
- **NEEDS LIVE VERIFY (Docker/GPU):** rebuild sandbox image with torch (~2GB) → flip `installed=True` →
  scout picks TorchMLP on a suitable dataset → trains on GPU → tuner tunes → deploy → predict (joblib).
  Watch CV cost (MLP × k-folds on a 1660 Ti); early stopping mitigates. Next: DL-1 sequence models (TS), DL-2 LOB.

### P1 complete — Ray + typed OpenAPI client (2026-06-26)
- **Ray parallelism** (#1): `app/core/parallel.py` `parallel_map(fn, items)` — fans independent tasks
  across Ray when `USE_RAY` is on, else sequential; degrades gracefully if Ray is missing/init fails
  (never breaks a run). Wired into the research toolkit's model-variant training via a top-level
  `_evaluate_variant` worker. **Verified end-to-end with real Ray installed locally** (3 variants trained
  in parallel → winner + Sharpe). `test_parallel.py` (4 tests incl. real-Ray + fallback).
- **Typed OpenAPI client** (contract-drift fix): generated `backend/openapi.json` from FastAPI (24 paths)
  + `frontend/lib/api-schema.ts` (1576 lines) via openapi-typescript; added `npm run gen:api` + the
  devDependency. **CI drift guard** (2 jobs in ci.yml): backend regenerates openapi.json and fails on diff
  (route drift); frontend regenerates api-schema.ts and fails on diff (stale types). Schema+types verified in sync.
  Follow-on (optional, needs `npm install` + tsc): migrate `lib/types.ts` consumers to the generated types.
- **159 tests pass.** Projects #5 and #1 complete; AI-Engineer-lens + Tower platform pieces all landed.

### P1 cont. — research toolkit (#5) + DVC (#1) (2026-06-25)
- **Reproducible research toolkit** `app/research/toolkit.py` + CLI (`python -m app.research.toolkit run
  --config params.yaml`): CSV + YAML → backward-looking TS features → N model variants → leakage-safe CV
  (walk-forward or PurgedKFold) → temporal hold-out + transaction-cost backtest → JSON report. Self-contained,
  reuses backtest.py + cv.py. `test_research_toolkit.py` (5 tests). Maps directly to Tier-1 #5.
- **DVC** (#1 data lineage): `dvc.yaml` (research stage runs the toolkit), `params.yaml` (tracked params),
  `.dvcignore`, `docs/DVC.md`; dvc+pyyaml added to requirements. `dvc repro` = reproducible runs;
  `dvc push` ships data/outputs to a remote. (Scaffolded + YAML-validated; needs `dvc init` + a dataset to run live.)
- **155 tests pass.** Remaining P1: Ray (parallel training) + typed OpenAPI client — steps documented; need user env to verify.

### P1 — prev_score fix + purged/embargoed CV (2026-06-25)
- **Bug fix:** `node_evaluator` now captures the prior iteration's score as `prev_score`
  BEFORE the evaluator overwrites `current_score`. Previously prev_score was never set, so
  the iteration gate always compared against 0 → "improvement" equalled the raw score and the
  loop never converged (only the max-iteration cap stopped it). Now a flat score converges
  after the 2nd evaluation. Integration harness updated + regression test added.
- **Purged/embargoed K-fold** `app/core/cv.py` (`PurgedKFold` + `purged_kfold_indices`) —
  López de Prado financial CV: contiguous time-ordered test folds, purge a window around each
  test block, embargo bars immediately after (serial-correlation leakage). sklearn-style
  splitter. `test_cv.py` (7 tests: disjoint, full coverage, contiguity, embargo, purge-gap, wrapper).
  Follow-on: inline into the TS sandbox template as the finance-mode CV (needs live verify).
- **150 tests pass.**

### Tower track — #5/#1 kickoff: quant backtest metrics (2026-06-25)
Toward the "Reproducible Research Toolkit" (#5) + "Distributed ML Research Platform" (#1) extensions
for quant-finance relevance (Tower Research). First verifiable slice landed:
- `app/core/backtest.py` — pure-numpy quant metrics: transaction-cost-aware equity curve,
  Sharpe/Sortino, max drawdown, turnover, hit-rate, buy-&-hold benchmark; `backtest_summary()`
  takes (actual_returns, pred_returns) → full performance dict. Designed to plug into the TS
  evaluator so forecasts are judged on Sharpe/drawdown, not just RMSE. `test_backtest.py` (8 tests).
- Remaining for #5: CLI + YAML config wrapper; wire backtest_summary into ts_modeler/evaluator;
  PDF report export. For #1: DVC (data lineage), Ray (parallel candidate/Optuna training).

### Phase 5.2 — AI-Engineering hardening (2026-06-19)
Closed the "AI Engineer lens" gaps from the audit (ML-Eng + AI-PM lenses deferred). 132 tests pass.
- **LLM completion cache** (opt-in `LLM_CACHE_ENABLED`): identical (system,user,model,temp) → stored
  text, saving tokens+latency on retries/duplicate framing. `test_llm_cache.py`.
- **Per-tenant LLM cost budget** (`TENANT_BUDGET_USD`, 0=unlimited): create_run sums the tenant's
  `llm_calls` cost and 402s when the cap is hit. DB-level test in `test_tenancy.py`.
- **Prompt-injection guardrail** `core/guardrails.py`: `scan_for_injection`/`neutralize_injection`
  (regex set for override/exfiltration/jailbreak patterns); create_run strips + logs (or 400s if
  `INJECTION_GUARD_STRICT`). The goal is only ever used as DATA + output is validated, so risk is low —
  this is defense-in-depth. `test_injection_and_eval.py`.
- **LLM-output robustness eval harness**: feeds adversarial/malformed framings through
  `validate_and_fix_framing`, asserting it never crashes and always yields a task-valid metric.
- **Tracing**: one structured `llm_call` log line per call (run_id-correlated; tokens/cost/latency/
  provider) — OTel/LangSmith-ready via the log pipeline.

### Phase 5.1 — audit fixes + CI integration harness (2026-06-19)
- **CI INTEGRATION HARNESS** `tests/test_integration/test_pipeline_graph.py` — drives the REAL compiled
  LangGraph end-to-end with each agent's run() stubbed (no LLM/sandbox/DB). Asserts: agent order +
  data_splitter sits between framer and baseline; **fail-fast** (a failed agent routes to END, no zombie
  cascade); **significance gate** stops iteration when gain < score_std; **iteration cap** terminates the
  loop. Closes the long-standing "no end-to-end test of the orchestration" gap. 4 tests.
- **Audit fixes (code, verifiable):** `MAX_RUN_SECONDS` wall-clock budget wraps `graph.ainvoke` (R6);
  `MAX_DATASET_COLUMNS` guard rejects absurdly wide CSVs at upload (D3); CORS origins now
  `CORS_ALLOW_ORIGINS` env (S8); Grafana creds/anon now env-driven (`GRAFANA_USER/PASSWORD/ANON_ENABLED`)
  (O2); startup warning if `SECRET_KEY` is the default in non-DEBUG (S4).
- **Audit correction:** S6 was WRONG — the inference `eval()` runs INSIDE the sandbox template
  (`PREDICT_CODE`) within the isolated container, not the backend. Marked not-a-bug.
- **QA doc fixed for Windows cmd:** replaced Linux heredoc + in-container `curl` (backend image has no curl)
  with `python -c` one-liners; added `psql -P pager=off` (the `--More--` you hit).
- **Verified (unit): 117 backend tests pass.**

### Phase 5 — live-QA fixes, reliability, guardrails, auth (2026-06-19)
- **Honest limit:** I cannot run Docker/the live stack
  in my environment, so live end-to-end QA remains the user's (see docs/QA_TEST_PLAN.md); these fixes are
  unit-proven + reasoned, and the cooldown directly targets the observed concurrent-run failure.

### Phase 4 — Multi-tenant production foundation (2026-06-18)

### Phase 4 — Multi-tenant production foundation (2026-06-18)
Toward the revenue product. Safe-by-default: with no tenant keys configured, behavior is identical
to before (single "public" tenant). Pieces needing live infra are OPT-IN so they can't break the app.
- **Auth + tenancy** `core/auth.py`: `TENANT_API_KEYS` (JSON api-key→tenant) drives `resolve_tenant`,
  the `current_tenant` dependency (401 on bad/missing key in tenant mode), and `enforce_run_ownership`
  — a single ROUTER-LEVEL dependency applied to all run-scoped routers in main.py, so every endpoint
  is covered with no per-endpoint hole (cross-tenant access → 404). Empty keys = "public" mode = no-op.
- **Tenant column**: `Run.tenant_id` (indexed, default "public"); Alembic `0002_tenant_id`. create_run
  stamps the caller's tenant; list_runs filters by it; child tables authorize via their run.
- **Quota**: `QUOTA_MAX_ACTIVE_RUNS_PER_TENANT` (0=unlimited) — create_run 429s when the tenant's
  queued+running count hits the cap.
- **Durable job queue (opt-in)** `core/job_queue.submit_run()`: default = in-process background task
  (unchanged); `USE_JOB_QUEUE=true` → enqueue to **arq** (Redis) processed by `app/worker.py`
  (`arq app.worker.WorkerSettings`). Compose `worker` service gated behind `profiles: [worker]` so a
  normal `docker compose up` never starts it. Enqueue fails safe (falls back to inline) so a run is
  never stranded. arq added to requirements.
- **Data isolation**: run_id is an unguessable UUID and access is tenant-authorized, so artifacts stay
  at /data/{run_id}; physical per-tenant namespacing of the path is a documented future hardening.
- **Verified (unit): full suite green** — new `test_tenancy.py` (public-mode default, key resolution,
  malformed-map ignored, cross-tenant query isolation, quota counts only active); existing API tests
  updated to the new `submit_run` seam.
- **DEFERRED (genuinely need live infra / ops, documented):** persistent inference server (kills ~1s
  predict latency); HTTPS/TLS (reverse-proxy/ingress concern, not app code); the OpenML CI
  integration harness (in-process executor + deterministic LLM mocks — high-value next build).
- **NEEDS LIVE VERIFICATION (offloaded):** run `alembic upgrade head` (applies 0002); confirm normal
  single-tenant runs unchanged; with `TENANT_API_KEYS` set, tenant A cannot GET tenant B's run (404);
  with `USE_JOB_QUEUE=true` + `--profile worker`, runs execute via the worker and survive an API restart.

### Phase 3 — De-hardcode audit + dynamic doctrine (2026-06-18)

### Phase 3 — De-hardcode audit + dynamic doctrine (2026-06-18)
Instruction #1 ("no predefining under prompts, everything dynamic") realized per the agreed doctrine
(LLM owns ML *decisions*; code owns contracts/mechanics/rails).
- **Doctrine doc** `docs/analysis/11-dynamic-doctrine.md` — authoritative classification table
  (decision vs mechanic vs guardrail); supersedes the now-stale "what's hardcoded" list in doc 01.
- **Metric registry** `core/metric_registry.py` — single source of truth for metric → sklearn scorer
  (incl. the multiclass remap), per-task allowed menu, defaults, higher_is_better. Mirrors model_registry.
- **Framer prompt is now registry-DERIVED**: the 13-metric vocabulary + per-task menu are generated
  from `metric_registry` (`all_metrics()` / `framer_menu_text()`), not hand-typed. Adding a metric =
  one registry line, no prompt edit. Selection heuristics (fraud→recall, etc.) kept as LLM *guidance*.
- **baseline_builder** now resolves its scorer via `metric_registry.sklearn_scorer()` — deleted ~25
  lines of duplicated scoring_map + multiclass-remap dicts. Parity-tested (identical behavior).
- **Honesty fix**: homepage pillar copy no longer falsely claims "No templates, no fixed recipes" —
  now describes template-first execution with agent-written fixes on edge cases (the long-pending debt).
- **Tracked residual:** the scoring maps INSIDE the feature_engineer/evaluator/model_selector/tuner
  sandbox *templates* still inline the mapping (they execute in the sandbox); parity-covered by tests,
  migrate to a registry-rendered token later.
- **Verified (unit): full suite green** — new `test_metric_registry.py` proves scorer parity with the
  old baseline map + that the framer prompt is registry-derived; `test_prompts`/`test_templates` pass.

### Phase 2 — Universal agentic self-repair (2026-06-18)

### Phase 2 — Universal agentic self-repair (2026-06-18)
User requirement: no agent should die on a template error — the failing agent must WRITE its own fix.
Now safe because Phase 1 made the sandbox a real boundary (generated code runs restricted, inside the jail).
- **Uniform helper** `BaseAgent.try_agentic_repair(run_id, code, failed_result, *, result_keys, goal,
  task_type, tags, timeout)`: a NO-OP when the result already succeeded (happy path = zero LLM cost),
  else delegates to the existing `execute_code_agentic` (cookbook-seeded, restricted sandbox, retries,
  validates RESULT keys, records the working fix).
- **Wired into every template-running agent** (template-first, agentic fallback): data_auditor,
  eda_agent, baseline_builder, model_selector (after its Tier-1 param-revision exhausts), tuner,
  evaluator, exporter — plus TS: ts_auditor, ts_feature_builder, ts_modeler. (preprocessor +
  feature_engineer already had it.) Each passes the minimal `result_keys` its run() actually consumes
  + a goal describing the artifacts to produce.
- **TS leakage guard:** the agentic goals for ts_feature_builder / ts_modeler FORCEFULLY mandate
  strictly-backward-looking features and TimeSeriesSplit/walk-forward/temporal-holdout ONLY (never
  random KFold) — a free-form LLM rewrite must not silently reintroduce look-ahead leakage.
- **Note:** the agentic path is `restricted=True`, whose whitelist excludes matplotlib/seaborn/shap,
  so a self-written fix may skip optional PLOTS — `result_keys` never require plots, only the data the
  pipeline needs, so recovery still advances the run.
- **Verified (unit): 68 backend tests pass** (was 65): new `test_agentic_fallback.py` proves the
  success no-op (no LLM call) + correct delegation args; `test_state_contract` confirms the wiring
  added no undeclared return keys.
- **NEEDS LIVE VERIFICATION (offloaded):** (1) normal runs still complete unchanged (happy path);
  (2) ideally inject a template fault in one agent and confirm it self-repairs and the run continues;
  (3) for a TS run that triggers repair, confirm the generated code used temporal validation (no leakage).

### Phase 1 — Real sandbox boundary (2026-06-18)

### Phase 1 — Real sandbox boundary (2026-06-18)
The sandbox executes untrusted/LLM-written code; Phase 2 makes that the norm, so the boundary
had to become real BEFORE generalizing agentic-repair.
- **Boundary model decided:** the CONTAINER is the primary boundary; the in-process AST screen +
  restricted builtins are secondary defense for generated code. Consequence: vetted TEMPLATES keep
  running with full builtins (`restricted=False`) INSIDE the jail — so the planned high-risk rewrite
  of all 7 templates to `restricted=True` was **avoided** (it would have destabilized verified code
  and needed matplotlib/seaborn/shap whitelisting + an os-replacement shim). Generated code stays
  `restricted=True`.
- **1.2 Process isolation (also the 0.3 deferral)** — `sandbox/main.py` rewritten: each `/execute`
  runs in a dedicated **spawn** child process (spawn, never fork → kills the documented fork-deadlock
  class). Parent enforces a HARD wall-clock timeout via `join`+`terminate`/`kill`; a runaway loop,
  segfault, or OOM kills only the child, service stays up. `signal.alarm` removed entirely (was
  main-thread-only) → cross-platform + thread-safe. Exec runs via `run_in_executor` so the event loop
  (and `/health`) stays responsive and independent executions can run concurrently. AST screen
  hardened (locals/breakpoint/help/classmethod/staticmethod added to the banned set).
- **1.1 Container hardening (`docker-compose.yml`)** — new `sandbox_net` with `internal: true` (no
  internet egress); sandbox host port REMOVED (reachable only by backend via internal DNS
  `sandbox:8001`); `cap_drop: [ALL]`, `security_opt: [no-new-privileges]`, `pids_limit: 256`
  (fork-bomb guard); env for writable matplotlib/home + no-pyc. Backend joined to `default` +
  `sandbox_net` (keeps DB/cache/MLflow + LLM internet). `read_only` / `tmpfs` / non-root `user` left
  as **commented opt-ins** to enable+verify one at a time (FS-write/volume-ownership breakage risk).
- **Verified (local, Windows-spawn): process isolation works** — normal run OK; infinite loop
  HARD-KILLED at the timeout; crash survived; restricted screen blocks os/eval. **65 backend tests
  pass** (was 48): +17 AST-screen/exec tests (`test_sandbox/test_screen.py`).
- **NEEDS LIVE VERIFICATION (offloaded — Docker/GPU):** `docker compose up -d` boots; backend↔sandbox
  reachable; **sandbox has NO internet** (`docker compose exec sandbox python -c "import urllib.request,sys; urllib.request.urlopen('https://example.com',timeout=5)"` should FAIL); a full pipeline run still
  completes (GPU XGBoost + matplotlib plots write OK under cap_drop); confirm `/health` responds during
  a long exec. If matplotlib/GPU breaks, the env vars or cap_drop are the suspects (rollback notes in compose).

### Phase 0.2–0.5 — honest evaluation + safety + hygiene (2026-06-18)

### Phase 0.2–0.5 — honest evaluation + safety + hygiene (2026-06-18)
**0.2 True holdout (the big one — reported scores will now DROP, correctly).**
- Root cause: the evaluator's old 20% "holdout" had already leaked into feature selection,
  model selection, and tuning (all ran on the full dataset) → reported `final_score` was the
  selection CV (user-confirmed), i.e. optimistic.
- Fix: new `data_splitter` agent runs after problem_framer, BEFORE any fit/select/tune. It
  physically carves `train.csv` + `holdout.csv` from raw data and repoints `dataset_path` →
  **every upstream agent becomes train-only with ZERO template changes** (they all read
  `dataset_path`). Stratified for single-label classification; random otherwise; skipped (CV
  fallback) under 60 rows. Time-series uses its own graph and never hits this node.
- Evaluator rewritten (surgically): scores the untouched holdout by reproducing the EXACT
  inference transform (`api/routes/inference.py`: align → preprocessor.transform → engineered
  formulas from raw cols → reindex to trained columns), fits on ALL train, no refit-on-subset.
  Wrapped in try/except → on any failure degrades to the legacy in-sample split and sets
  `evaluation_basis="in_sample_split"` (never breaks a run). Reuses the verified per-task
  metrics block unchanged. Handles regression/binary/multiclass/multilabel(labelcols+delimiter).
- Significance-gated iteration: evaluator computes `score_std` (3-fold CV std on train);
  `route_after_evaluator` now requires improvement ≥ max(IMPROVEMENT_THRESHOLD, score_std) —
  a gain within fold noise no longer triggers another (overfitting) iteration.
- New state: `holdout_path`, `holdout_frac`, `evaluation_basis`, `score_std`.
- Residual debt (documented, smaller): binary threshold is still picked on the holdout (affects
  only reported recall/precision@threshold, NOT the headline final_score) — clean up later.
**0.3 Sandbox single-flight lock.** Added an `asyncio.Lock` around `/execute` so overlapping
  requests can't stomp the shared `signal.alarm` timer. NOTE: the full signal.alarm→worker-PROCESS
  rewrite (true parallelism + non-loop-blocking timeout) is **deliberately deferred to Phase 1**,
  where the sandbox container is rebuilt (non-root, network=none) and live GPU-verified together —
  doing it blind now (documented past multiprocessing-deadlock + GPU re-init) would risk breakage.
**0.4 Alembic adopted.** `backend/alembic/` + `alembic.ini`, sync engine off `DATABASE_URL_SYNC`,
  `Base.metadata` wired for autogenerate, no-op `0001_baseline`. `create_all` kept for fresh DBs.
  Workflow + one-time `alembic stamp` adoption in `docs/MIGRATIONS.md`. No more hand-run ALTER TABLE.
**0.5 Hygiene.** Deleted tracked `frontend-backup-phase3/`; untracked 96 `.pyc`/`__pycache__` +
  `tsbuildinfo`; real `.gitignore`. (Changes staged, NOT committed — awaiting user.)
- **Verified (unit, no network): 48 backend tests pass** (was 41): added holdout-transform template
  renders (incl. multilabel), splitter template, and 5 significance-gate routing tests.
- **NEEDS LIVE VERIFICATION (offloaded to user — checklist provided):** run Iris/Titanic/regression/
  imbalanced/multilabel end-to-end; confirm `evaluation_basis="holdout"` and holdout final_score ≤ old
  CV score (expected drop). If any task logs `HOLDOUT_FALLBACK`, capture the repr for follow-up.

### Phase 0.1 — Request-scoped context: concurrency attribution race FIXED (2026-06-18)

### Phase 0.1 — Request-scoped context: concurrency attribution race FIXED (2026-06-18)
Part of the strict-review production-hardening plan (P0→P1→P2; target = multi-tenant hosted product).
- **Bug:** run/agent attribution was stored as *mutable attributes on singletons* —
  `llm._current_agent`/`_current_run_id` (the process-global `LLMClient`) and
  `BaseAgent._agent_start_time`. Two concurrent runs clobbered each other → LLM cost/token
  attribution logged against the wrong run, corrupted durations, cross-contaminated decision
  logs. Directly undermines the "every decision is auditable" value prop. The multi-tenant blocker.
- **Fix:** new `app/core/context.py` holds `contextvars` (`run_id`, `agent_name`, `agent_start`).
  contextvars are copied per asyncio task, and each pipeline run is its own `graph.ainvoke` task,
  so concurrent runs are isolated with zero cross-talk. Bound once in `BaseAgent._mark_step("running")`;
  read in `LLMClient._record` + the rate-limit/fallback log lines. Removed all singleton `_current_*`
  / `_agent_start_time` state.
- **Doctrine note:** this is a *mechanic/rail*, not an ML decision — stays in code.
- **Verified (unit, no network):** new `tests/test_context.py` proves isolation across interleaved
  concurrent tasks + safe defaults outside a run. **41 backend tests pass** (was 39).
- **Next in P0:** 0.2 held-out/nested-CV scoring + significance-gated iteration (selection-CV is
  optimistic, confirmed); 0.3 process-isolated sandbox exec (replace signal.alarm); 0.4 Alembic;
  0.5 delete tracked `frontend-backup-phase3/`.


### Phase 3.8 — Imbalanced (P18) + Multilabel (P19) finished & stabilized (2026-06-16)
- **AgentState contract** fixed: added `imbalance_strategy`, `training_pipeline_path`,
  `multilabel_binarizer_path`, `resampler_used` (LangGraph silently drops undeclared keys).
- **feature_engineer** multilabel-safe (ast target parse, KFold + MultiOutputClassifier, multilabel scoring).
- **In-fold SMOTE/SMOTE-Tomek** in model_selector/tuner/feature_engineer via `_cv_estimator()`
  (imblearn Pipeline, in-fold only; `<6` minority → class_weight fallback); tuner final-fit resamples full data.
- **Exporter + inference** carry `task_type` + `multilabel_binarizer`; predict decodes multilabel → label SET;
  PredictionLog stores lists as JSON; frontend renders label chips (`Prediction.prediction: string|string[]`).
- **Critical fix**: in-progress rewrite broke tuner+evaluator templates (abandoned brace-doubling →
  `.format()` crashed EVERY run). Converted both to exporter `.replace("__TOKEN__", repr())` pattern.
- **New guards** (static, no network): `test_state_contract.py` (agent run() keys ⊆ AgentState) +
  extended `test_templates.py` (format vs token render styles + multilabel case).
- **DB migration gotcha**: `Run.pipeline` is a new column; `create_all` won't ALTER an existing table →
  POST /runs 500s until `ALTER TABLE runs ADD COLUMN pipeline VARCHAR(20) DEFAULT 'tabular'` is run.
- **Verified: 34 backend tests pass, tsc clean**; live multilabel/imbalanced/tabular runs executed for confirmation.

### Phase 4.0 — Time-Series studio BUILT & live-verified (2026-06-16)
Full working forecasting pipeline (P3 + core P4), separate graph on shared chassis:
- Agents (`app/agents/ts_agents.py`): **ts_framer** (timestamp/target/horizon/freq/metric) →
  **ts_auditor** (ordering/frequency/gaps/min-length) → **ts_feature_builder** (lags 1-7,
  shifted rolling mean/std, calendar — strictly backward-looking) → **ts_modeler**
  (walk-forward `TimeSeriesSplit` over Ridge/RF/GBR, naive seasonal baseline, temporal
  hold-out, forecast plot, refit-on-all) → reuse **exporter**.
- `app/agents/ts_orchestrator.py`: `build_ts_graph()` with fail-fast edges; `run_pipeline`
  branches on `pipeline=="timeseries"`. Frontend Studio toggle enabled.
- **Validity by construction**: only TimeSeriesSplit/temporal splits exist in TS templates —
  no random K-fold path for time data. Templates use token-replace style (no brace-doubling).
- **Live-verified**: synthetic daily series (trend+weekly seasonality) → completed,
  task=time_series_forecasting, winner=RandomForest, RMSE 9.58, walk-forward validated.
- **Remaining (T3/T4)**: backtest equity-curve-with-costs, ONNX export, history-based TS deploy.

### Baseline multilabel fix + frontend integration (2026-06-17)
- **Bug**: a multilabel run whose labels live in `label_columns` (no single target) crashed the
  baseline with `KeyError: ['None']` — `dropna(subset=[target_col])` used target_col="None".
  Fixed: baseline resolves target(s) per task (label_columns / delimiter / single-label) and now
  guards a missing target with a clear ValueError instead of KeyError.
- **Frontend integration**: new `ModelToolsPanel.tsx` wired as a run-page **Tools** tab, surfacing
  P12 retrain · P13 batch-score · P14 ask-your-model · P15 fairness audit (all via lib/api.ts).
  P10 compare / P11 per-prediction explain have working backends + api clients (gallery/deploy
  wiring is the remaining thin follow-up). tsc clean, 39 tests pass.

### Self-debugging execution engine + Code Cookbook (2026-06-17) — see docs/analysis/10
Answer to "let agents truly handle their own errors, keep templates, RAG-without-vectors".
Confirmed scope: brittle agents only · JSONL store · E1→E2→E3 · template fallback.
- **E1 sandbox hardening** (`sandbox/main.py`): generated code runs with `restricted=True` →
  AST safety screen (block os/subprocess/eval/open/network/dunder-escapes) + restricted builtins
  + controlled `__import__` (whitelist: pandas/numpy/sklearn/xgboost/scipy/imblearn/joblib/…) + `os`
  removed. Trusted templates run unchanged (`restricted=False`, full builtins). Executor + BaseAgent
  thread the flag. Sandbox image rebuilt.
- **E2 Code Cookbook** (`app/core/code_cookbook.py`, JSONL at `backend/cookbook/`): stores code that
  ran successfully; retrieval = exact tag filter + keyword overlap + success-health (NO vectors →
  deterministic, auditable, no hallucinated relevance). Upsert by md5 checksum; fail_count demotes.
- **E3 agentic loop** (`BaseAgent.execute_code_agentic`): template-first (cheap/deterministic) → on
  failure the agent WRITES corrected code (seeded by cookbook fixes + the traceback), runs it under
  the restricted sandbox, reads the new traceback, retries (cap 3), validates the RESULT contract,
  and records the working fix. Wired into preprocessor + feature_engineer; templates remain the
  fallback. The happy path is unchanged (no LLM cost unless a template actually fails).
- **Honesty fix still pending**: correct the homepage's false "No templates, no fixed recipes" copy.

### P7–P17 backlog completed (2026-06-17) — see docs/HANDOFF_P7_P17.md
One pass, code-only (user tests). 39 backend tests pass, tsc clean.
- **P8** Tier-2 diagnostic router (bounded: preprocessor failure → EDA once); new `diagnostic`
  node + `backjumps_used`/`repair_hint` state.
- **P10–P15** new `app/api/routes/extras.py`: run compare, batch-predict (CSV in→scored CSV out),
  per-prediction SHAP (`/explain`), grounded ask (`/ask`), fairness audit (disparate impact),
  champion/challenger retrain. All reuse the sandbox executor / LLM / DB; sandbox code via token-replace.
- **P16** opt-in API-key + Redis rate-limit middleware in main.py (default OFF via empty `API_KEY`/0).
- **P17** `tests/test_agents/test_prompts.py` pins prompts to the JSON keys their agents parse.
- Frontend: all endpoints added to `lib/api.ts` (callable); dedicated panels are fast-follow.

### Model Registry — dynamic models, no hardcoded menu (2026-06-17)
Replaced the two hardcoded tiers with a single source of truth, `app/core/model_registry.py`:
- **The source/catalog**: each entry declares name, per-task class strings, task compatibility,
  GPU/class_weight flags, `installed` (sandbox availability), and its **Optuna search_space**.
- **model_selector is now a scout**: its prompt menu is RETRIEVED from `registry.menu_text(task)`
  (not hardcoded); the LLM's chosen classes are validated against the registry all-list before
  `eval()` (safety); not-installed models can be RECOMMENDED via `discovery_notes` but never train
  (doc 04: we don't execute code for uninstalled/web-fetched libs on mounted data).
- **tuner is generic**: search space comes from `registry.search_space_for(winner_class)`
  injected as a token; the `if/elif` per-family Optuna blocks (objective + refit) collapsed into
  `_suggest`/`_build`. Adding a model's hyperparameters = a registry entry.
- **Proof + free P7**: HistGradientBoosting added as one registry entry (now selectable & tunable).
  CatBoost/LightGBM registered as `installed=False` recommendations (need sandbox rebuild).
- Gotcha fixed: `"GradientBoosting"` is a substring of `"HistGradientBoosting"` → `search_space_for`
  now matches the LONGEST family first. 34 tests green.
- **"Retrieve models from a source"**: the registry IS the curated source the scout retrieves from.
  Live web *code* retrieval remains deliberately excluded (doc 04); web *knowledge* enrichment is a
  future opt-in. Adding a model = one registry entry (+ sandbox install if a new lib).

### Churn dataset fix — NaN targets (2026-06-17)
"All model candidates failed — Input y contains NaN": the churn target had missing values and the
preprocessor didn't drop NaN-target rows (baseline did, preprocessor didn't). Fixed: drop rows with
a missing target on every read of the source so X and y stay aligned. Not a complexity limit — a hygiene gap.

### Live verification — ALL milestones green (2026-06-17)
Final end-to-end runs (real pipelines, not just unit tests):
- **Tabular** (Iris): completed, f1 0.97 — no regression from the tuner/evaluator token refactor.
- **P18 Imbalanced** (synthetic 1.5% fraud): completed, framer chose **pr_auc**, SMOTE applied in-fold.
- **P19 Multilabel** (delimited tags): completed all 10 agents, **deploy→predict returns a label SET
  `['sports','tech']`**. Four bugs found & fixed live, each advancing the pipeline one stage:
  (1) `Run.pipeline` missing DB column → `ALTER TABLE`; (2) baseline dummy `constant=0` invalid on 2-D
  target → `MultiOutputClassifier(most_frequent)`; (3) multilabel `__target__` stored as variable-length
  label lists → fixed-width binary vectors; (4) evaluator multilabel branch never set `final_score` → added.
- **P3–P6 Time-Series** (daily seasonal series): completed, task=time_series_forecasting, walk-forward
  RMSE 9.58, RandomForest winner, forecast plot produced.
Final state: **34 backend tests pass, tsc clean.**

### data_auditor abort-flakiness fixed (2026-06-16)
The auditor runs BEFORE the framer, so target/task are always unset at audit time. Its prompt
listed "target column missing" as an abort criterion → the LLM nondeterministically aborted
runs (killed a multilabel run). Fixed: prompt now assesses DATA QUALITY only and is told
target/task are assigned later; user-message no longer presents them as missing.

### Phase 3.9 — Time-Series studio: T1 foundation only (2026-06-16, superseded by 4.0)
- **Wrong-Door Guard**: tabular `data_auditor` flags a monotonic-datetime column (`temporal_signal`) and warns
  (never blocks) that random CV overstates performance on time-ordered data.
- **Mode plumbing**: `AgentState.pipeline` (+ timestamp_col/forecast_horizon/frequency/wrong_door_warning),
  `Run.pipeline` column, `runs.py` pipeline field, orchestrator threading, frontend Studio selector
  (Time-Series shown **disabled "Soon"** — roster not built; selecting it would silently run tabular = invalid).
- **Remaining**: ts_orchestrator graph + run_pipeline branch, ts_auditor/ts_framer/naive-baseline/
  walk_forward_evaluator (T1), then T2–T4. Prompts: BACKLOG_PROMPTS.md P3–P6.

### Phase 3.8 — First-class severe class imbalance support (2026-06-14)

**Goal**: Proper handling of fraud-like datasets (minority < 5%, e.g. 0.1%) where accuracy/AUC mislead and the minority class is the whole point.

- **Data Auditor / EDA Agent**: Already computed `class_imbalance.ratio` and `imbalance_severity` ("severe" if minority < 5%). Now properly escalated into state and passed through the pipeline.
- **Problem Framer**: When severe imbalance detected for classification, prefers `primary_metric = "pr_auc"` (average_precision) or recall, NOT roc_auc. Added `pr_auc` to metric vocabulary.
- **Scoring maps updated** in baseline_builder, model_selector, tuner, feature_engineer, evaluator: `pr_auc` → `average_precision` with multiclass remap (stays as-is since PR-AUC not defined for multiclass in sklearn). Mirrors existing `*_weighted` / `roc_auc_ovr_weighted` pattern.
- **Preprocessor**: Added optional resampling step via `imbalanced-learn` (already in sandbox requirements.txt). LLM chooses `imbalance_strategy`: `"class_weight"` | `"smote"` | `"smote_tomek"` | `"none"`. SMOTE applied **inside CV folds only** via `imblearn.pipeline.Pipeline` — never touches validation fold (prevents leakage). Guard: SMOTE needs `k_neighbors < minority_count`; falls back to `class_weight` for tiny minorities (< 6).
- **Inference pipeline**: Resampler is **train-time only** — saved `inference_pipeline.pkl` contains preprocessor + model + threshold + engineered features, NOT the SMOTE step.
- **Evaluator**: Reports PR-AUC, precision/recall at chosen threshold, and **precision-recall curve plot** (`precision_recall_curve.png`) alongside confusion matrix. Threshold selection honors `fp_fn_preference` — biases toward recall when severe.
- **Template guard**: All 7 sandbox templates render and compile cleanly (test_templates.py passes).
- **End-to-end verified**: Synthetic fraud dataset (5000 rows, 0.1% fraud = 5 positives) ran full 10-agent pipeline. Artifacts generated include `precision_recall_curve.png`, `inference_pipeline.pkl` (no resampler), PR-AUC logged (0.0256), recall=0.998 on hold-out. All 32 tests pass.

**Gotchas avoided**:
- imblearn Pipeline ≠ sklearn Pipeline — resampler only acts during `fit()`, so inference pickle excludes it.
- Doubled braces `{{ }}` in all template code — template guard test catches any unescaped brace.
- SMOTE `k_neighbors` guard prevents crash on tiny minority classes.
- Multiclass remap for `average_precision` mirrors existing pattern (keeps as-is since sklearn doesn't define multiclass PR-AUC).

### Phase 3.7 — Tier-1 self-repair micro-loop (2026-06-13)

The first step of the doc-06 plan to close the MLE-STAR "dynamic jump-back" gap.

- **What**: when a sandbox execution fails, the agent no longer fails immediately.
  `BaseAgent.execute_code_with_repair(render_fn, params, repair_goal)` asks the LLM
  to revise the *decision parameters* (never to write code), re-renders the SAME
  vetted template, and retries — capped at `MAX_REPAIRS = 2`, then fails fast as before.
- **Why it's safe**: repairs stay inside the template vocabulary, so the sandbox
  safety model (no arbitrary code execution) is untouched. Worst-case extra cost is
  +2 LLM calls per agent.
- **Wired into**: preprocessor (encoding/imputation/scaling/drop fixes) and
  model_selector (drop/swap a model that errored, fix bad initial_params). Pattern
  is generic — other agents can adopt by passing a render_fn.
- **Observability**: every repair is written to the decision log (diagnosis +
  change summary) so it shows in the evidence trail; new Prometheus counter
  `automl_agent_repairs_total{agent_name, outcome=recovered|exhausted}`.
- **Tests**: `tests/test_agents/test_self_repair.py` — recovers / exhausts-at-cap /
  no-repair-on-success. Suite now 32 passing.
- **End-to-end verified**: Iris multiclass run completed all 10 agents clean
  (final 0.9667 accuracy, LogisticRegression winner) after both regressions below
  were fixed — confirming the repair wiring doesn't break the happy path.
- **Also fixed**: pip-extras (aiosqlite, structlog, prometheus-client, instrumentator)
  were already in requirements.txt but the running image was stale, so they vanished
  on every container recreate and were reinstalled by hand. Rebuilt the backend image
  — they're baked in now. Lesson restated: the image is the source of truth, not
  `pip install` into a running container.
- **Latent bug surfaced by the rebuild**: with the instrumentator now actually
  installed, `Instrumentator().instrument(app)` ran *inside* the lifespan → FastAPI
  raised "Cannot add middleware after an application has started" and startup crashed.
  It had been silently skipped for weeks because the package was missing and the
  ImportError was swallowed. Moved instrumentation to import time (before startup).
  Lesson: a swallowed-ImportError fallback hides bugs until the dependency arrives.
- **Second regression from the refactor**: replacing `code = TEMPLATE.format(...)` with
  a `render()` closure left the notebook-cell builders referencing an undefined `code`
  → `NameError` at runtime, only caught by a live run (preprocessor + model_selector).
  Fixed by reconstructing `code = render(final_params)` after the repair call.
  **Process gap noted:** unit tests cover templates and the repair loop in isolation,
  but agent `run()` methods have no fast smoke test — both regressions this session
  needed a full ~minutes-long pipeline run to surface. Candidate next hardening:
  a mocked-sandbox smoke test per agent that runs `.run()` against a tiny fixture.

> **Convention:** critical strategic discussions live as separate docs in
> [`docs/analysis/`](analysis/README.md) (one topic per file); this journal records
> the build history.

> **Convention:** critical strategic discussions live as separate docs in
> [`docs/analysis/`](analysis/README.md) (one topic per file); this journal records
> the build history. Current analysis docs: hardcoded-vs-agentic audit, control-flow
> classification, vs-Google-AutoML, web-search verdict, multi-agent/observability/
> LLM-evaluation, vs-MLE-STAR + micro-loop roadmap, quant-finance fit.
>
> **Backlog:** every remaining feature/fix has a ready-to-run prompt in
> [`docs/BACKLOG_PROMPTS.md`](BACKLOG_PROMPTS.md) (P1–P17, tiered).

---

## 1. What This Project Is

**One sentence:** Upload a CSV and describe your goal in plain English — ten AI agents
autonomously audit, explore, engineer, train, tune, and evaluate, then hand you a
deployed model with a live prediction endpoint, drift monitoring, and a narrated
Jupyter notebook proving every step.

**Who it's for:** Anyone who has tabular data and a prediction goal but doesn't want
to (or can't) hand-write an ML pipeline. The system makes the same decisions a senior
data scientist would — and *explains every one of them*.

---

## 2. Core Architecture

```
                       ┌─────────────────────────────────────────────┐
 Browser (Next.js) ───►│  BACKEND (FastAPI)                          │
   localhost:3002      │  - REST API + WebSocket progress            │
                       │  - LangGraph orchestrator (10 agents)       │
                       │  - Agents call the LLM for decisions        │
                       └──────┬──────────────┬───────────────────────┘
                              │              │
                   writes code▼              ▼ tracks everything
                       ┌────────────┐  ┌──────────────────────────┐
                       │  SANDBOX   │  │ Postgres · Redis · MLflow│
                       │ (executes  │  │ Prometheus · Grafana     │
                       │  ML code,  │  └──────────────────────────┘
                       │  GPU 1660Ti│
                       └────────────┘
```

### The Golden Rules (decided at project start, never violated)

| Rule | Why |
|---|---|
| **Agents write code, the sandbox executes it** | The LLM never sees raw data rows — only statistical profiles. Privacy + token cost + reliability. |
| **Baseline model FIRST, before deep EDA** | A 30-second LogisticRegression establishes the floor. Every later step must justify itself against this number. |
| **sklearn Pipeline is the contract** | The exact same preprocessor object used in training is serialized and used at inference. No train/serve skew. |
| **Every decision is logged with reasoning** | `decision_logs` table + MLflow + the evidence notebook. Stakeholders can audit everything. |
| **No hardcoded ML logic** | The LLM decides metrics, preprocessing strategies, features, models. Code templates only provide the *mechanics*. |

### The 10 Agents (run in this order)

1. **Data Auditor** — profiles the CSV (nulls, cardinality, distributions), verdict: usable/warn/abort
2. **Problem Framer** — LLM reads your goal → task type, target column, primary metric
3. **Baseline Builder** — simplest possible model (LogReg/Ridge), 5-fold CV → the floor
4. **EDA + Error Analysis** — targeted EDA focused on *why the baseline fails*
5. **Preprocessor** — LLM designs per-column imputation/encoding/scaling → sklearn ColumnTransformer
6. **Feature Engineer** — LLM proposes ≤6 hypothesis-driven features; each is CV-tested; only positive lift survives
7. **Model Selector** — LLM picks 2-3 candidates from data characteristics; all trained; best wins
8. **Tuner** — Optuna Bayesian search (30 trials) on the winner — **runs on GPU for XGBoost**
9. **Evaluator** — hold-out metrics, SHAP, calibration, threshold selection, slice analysis
10. **Exporter** — packages everything + LLM writes the evidence notebook

**Iteration loop:** Evaluator → Feature Engineer (again) if score improved > threshold, max 3 iterations.

**Fail-fast:** any agent failure routes the graph straight to END — no zombie cascades (learned the hard way; see §6).

---

## 3. Technology Choices and Why

| Choice | Alternative considered | Why we chose it |
|---|---|---|
| **LangGraph** | Raw async orchestration | Stateful graph with conditional edges fits the iterate-on-improvement loop naturally |
| **Groq (llama-3.3-70b)** | Claude / GPT-4 | Free tier for development; one env var swaps to Claude later |
| **Separate sandbox container** | exec() in backend | Resource isolation (CPU/RAM limits), security, independent ML deps |
| **MLflow** | W&B, custom tracking | Self-hosted, free, model registry built in |
| **Prometheus + Grafana** | Cloud APM | Self-hosted, standard, stakeholder-friendly dashboards |
| **PSI + KS test for drift (hand-rolled)** | Evidently library | scipy is already in the sandbox; ~60 lines of transparent math beats a heavyweight dependency |
| **Next.js 14 + pure Tailwind** | Component library (shadcn/MUI) | Zero UI deps = small image; full design control |
| **Predictions execute in the sandbox** | Load model in backend | The backend has no ML libs; the sandbox is the project's "computer". ~1s/prediction is fine for v1 |

---

## 4. Phase History

### Phase 1 — Backend pipeline + observability (complete)
- 10-agent LangGraph pipeline, end-to-end on Titanic (binary) and Iris (multiclass)
- Full observability: structured JSON logs (structlog), 19 Prometheus metrics, Grafana
  dashboard, per-LLM-call token/cost/latency tracking (`llm_calls` table)
- MLflow: every metric/param/artifact + Model Registry promotion endpoint
- REST + WebSocket API, 22 tests

### Phase 1.5 — Agentic evidence notebook (complete)
**User requirement:** *"no hard coded part... a brain should handle everything, each problem will have different approach"*
- Every agent appends its **actually-executed code + results** to `notebook_cells` state
- The Exporter sends step summaries to the LLM → LLM decides notebook structure,
  writes narrative adapted to the problem type (classification vs regression), insights, conclusion
- Verified: Iris run produced "Iris Species Classification using RandomForestClassifier",
  29 cells, 8 sections — fully different from the Titanic notebook

### Phase 2 — Frontend (complete)
- Next.js 14 at **localhost:3002**: upload page, run history, live run dashboard
- Live WebSocket agent log, pipeline timeline, results metrics, artifact downloads, LLM cost stats
- Premium design pass: animated gradient-orb background, glassmorphism, glow effects

### Phase 3 — Inference + drift monitoring (complete, this update)
- **One-click deploy:** `POST /runs/{id}/deploy` → model live at `POST /runs/{id}/predict`
- **Prediction logging:** every prediction stored (`prediction_logs` table) with features, confidence, latency
- **Drift monitoring:** `GET /runs/{id}/drift` compares live traffic vs training data —
  PSI per feature (<0.1 stable, 0.1-0.25 moderate, >0.25 drifted) + Kolmogorov-Smirnov test
- **Schema endpoint** auto-generates the prediction form in the UI from the training CSV
- **GPU training:** GTX 1660 Ti passed into the sandbox; XGBoost trains with `device="cuda"`
- **In-browser notebook preview:** pipeline.ipynb rendered with markdown + syntax-highlighted code
- **Prediction playground UI:** auto-generated form → predict → confidence bar → drift refresh

---

## 5. Architecture Decisions Made in Phase 3 (and why)

### 5.1 The engineered-features inference gap (major fix)
**Problem discovered:** the model trains on *preprocessed + LLM-engineered* columns, but
`inference_pipeline.pkl` only contained the preprocessor + model. Prediction crashed with
a feature-count mismatch.

**Decision:** the pipeline pickle now carries the complete transformation recipe:
```python
{
  "preprocessor":        <fitted ColumnTransformer>,
  "model":               <tuned model>,
  "threshold":           0.35,
  "target_classes":      ["Iris-setosa", ...],   # decode int → label
  "engineered_features": [{"name", "formula", "fill_value"}, ...],
  "version": "1.1",
}
```
At inference: raw input → align columns → preprocess → re-evaluate each engineered
formula (with the **training-time median** as fill value — no train/serve skew) → predict
→ decode label. Both the live endpoint and the generated `api_main.py` artifact do this.

### 5.2 Label-encode string targets at preprocessing
**Problem:** XGBoost rejects string labels ('Iris-setosa') outright — it silently lost
every classification run with a text target. **Decision:** the Preprocessor now
label-encodes non-numeric targets and saves the class names; inference decodes back.

### 5.3 Input alignment at the predict endpoint
Real traffic has extra columns (IDs) and missing ones. The predict code aligns incoming
rows to `preprocessor.feature_names_in_`: drop extras, add missing as NaN (the pipeline's
imputers absorb NaN). Without this, every request had to match the training CSV exactly.

### 5.4 GPU: sandbox-only, XGBoost-only, auto-detected
- `docker-compose.yml` reserves the NVIDIA GPU for the **sandbox** container only
- Templates detect GPU at runtime (`nvidia-smi` present?) → add `device="cuda"` to XGBoost
- sklearn models (RandomForest, GradientBoosting, LogReg) are CPU-only by design — no GPU support exists
- Honest note: on small datasets (<100k rows) GPU transfer overhead can make XGBoost
  *slower* than CPU. The win comes on large datasets. It's enabled because it costs nothing.

### 5.5 Drift math from first principles
PSI (Population Stability Index) over 10 quantile bins for numerics / category
frequencies for categoricals, plus a KS two-sample test for numerics. ~60 lines in the
sandbox, fully visible in the API response. Evidently would have added a 100MB+
dependency we can't even install (sandbox image rebuild constraints).

---

### Phase 3.5 — "Obsidian Atelier" redesign (2026-06-11, same day)

**User feedback:** rejected the violet/glassmorphism direction. Brief: *luxury & futuristic;
sophisticated, technical, organic. Change palette, typography, spacing, and components completely.*

**Safety first:** the previous frontend was backed up to `frontend-backup-phase3/`
(node_modules and .next excluded) before any redesign work. Restoring it = copy the
folder contents back over `frontend/`.

**The design system (defined in `tailwind.config.ts` + `globals.css`):**

| Token | Choice | Rationale |
|---|---|---|
| Surfaces | `obsidian` scale — warm near-black (#0a0908…) | Luxury is warm, never cold slate; futurism is restraint |
| Text | `bone` ivory scale (#e9e4d8…) | Pure white is harsh; bone reads editorial/printed |
| Accent | `gold` champagne (#c8a96e) used *sparingly* | One precious accent = sophistication; gold on near-black is the luxury axiom |
| Secondary | `jade` (#5fb3a1) for live/success | The "organic" note; avoids tech-green cliché |
| Error | `terra` terracotta (#c4756b) | Errors without alarm-red vulgarity |
| Display type | **Cormorant Garamond** (serif, italic accents) | Fashion-house headline voice |
| Body type | **Manrope** light weights | Quiet, refined grotesk |
| Data type | **JetBrains Mono**, uppercase `tracking-luxe` (0.28em) eyebrows | The "technical" instrument-panel voice |
| Background | Slow aurora ribbon + film grain + faint 72px grid | Organic (aurora/grain) × technical (grid), replaces the loud orbs |
| Components | Hairline borders, corner ticks, gold-filled buttons w/ black text, `lux-card` vocabulary | Technical-drawing details; high-contrast CTA |

**Voice:** the UI now speaks atelier language — "Commission a Model", "The Gallery",
"Commissioned Works", "Begin the Work", numbered sections (i. The Dataset, ii. The Intention).

**Mechanics:** major surfaces (layout, navbar, home, upload form, gallery, run-page chrome)
were rewritten; the seven data panels were migrated by a systematic class-vocabulary swap
(slate→obsidian/bone, violet/fuchsia→gold, emerald→jade, rose→terra) plus hand-polish
(LiveLog's rainbow agent colors → restrained gold/jade/bone alternation).

**Build fix shipped together:** `marked` (notebook markdown renderer) was installed into a
running container whose anonymous `node_modules` volume was later recreated from the old
image → "Module not found: marked". Fix: rebuilt the frontend image so the dependency is
baked in (it was already in package.json). Lesson: container-exec installs are ephemeral;
the image is the source of truth.

**Infra incident:** during the rebuild, Docker Desktop's Windows port relay (`wslrelay`)
leaked bindings for 6379/3001 — ports stayed "allocated" with zero containers running.
Resolution: restart Docker Desktop. Known Docker-on-Windows failure mode; documented here
because it *will* happen again.

### Phase 3.6 — Dual theme · LLM resilience · readability · text columns (2026-06-11)

**1. Dark/light theme.** The entire palette was converted to CSS-variable RGB triplets
(`--obsidian-950: 10 9 8`, consumed by Tailwind as `rgb(var(--x) / <alpha>)`), so the
existing class vocabulary renders correctly in both themes with zero component changes.
Light theme = "Ivory Atelier": warm paper surfaces, ink text, gold deepened for contrast
(the gold scale is *luminance-inverted* in light mode so `gold-300` stays readable).
Toggle in the navbar; choice persists in localStorage; an inline `<head>` script applies
it before paint (no flash of wrong theme).

**2. LLM rate-limit resilience (`core/llm.py` rewrite).** Two layers:
- *Retry*: 3 attempts per provider, exponential backoff with jitter, honours `Retry-After`.
- *Fallback chain*: `groq → gemini → openrouter → deepseek → ollama` (then Anthropic if
  keyed). Providers without keys are skipped automatically; non-retryable errors (401/400)
  skip to the next provider immediately. All providers speak the OpenAI dialect — Gemini
  and Ollama both expose OpenAI-compatible endpoints — so one HTTP code path serves all.
  Every call records *which provider actually answered* (llm_calls table + Prometheus).
- Verified live: Groq returned a real 429 → retried with 20s Retry-After → fell back to
  Ollama (connection refused, not installed) → aggregate error naming every provider tried.
  New keys activate by adding env vars — no code change: `GEMINI_API_KEY` (free at
  aistudio.google.com), `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, or local `ollama serve`.

**3. Readability pass (user: "text is not fully visible").** Root causes: Cormorant
Garamond's hairline strokes at screen sizes + 9-10px labels + over-tracked (0.28em)
uppercase + low-contrast text steps. Fixes: display font → **Playfair Display** (same
luxury voice, sturdier x-height); all text-color steps brightened (~12% more contrast);
micro-label floor raised 8-10px → 10-11px; tracking 0.28em → 0.22em; `font-light` body
text → regular weight; notebook prose 13.5px → 14.5px.

**4. Free-text column support (first "complex ML" expansion).** EDA now detects columns
with avg length > 30 chars; the Preprocessor LLM can choose `text_tfidf` per column; the
sandbox builds a `TfidfVectorizer(max_features=200, ngram_range=(1,2))` inside the same
ColumnTransformer — so text features serialize into the inference pipeline like everything
else. Unlocks: spam detection, review classification, support-ticket routing.

## 6. Bug Post-Mortems (what broke and what we learned)

| Bug | Root cause | Lesson institutionalized |
|---|---|---|
| MLflow `INVALID_PARAMETER_VALUE` on iteration 2 | MLflow params are immutable; re-logging `feature_kept_0` with a new value crashes | Any param logged in a loop gets an `i{iteration}_` prefix |
| `PicklingError: InferencePipeline` | Classes defined inside `exec()` have no importable module path | Pipeline saved as a plain dict, never a custom class |
| "No Artifacts Recorded" in MLflow | Missing `--serve-artifacts`: client wrote files into *its own* container | MLflow server proxies artifact uploads over HTTP |
| Iris run crash chain (3 bugs) | String target broke EDA `.corr()`; binary-only scorer silently NaN'd on multiclass (sklearn ≥1.4 swallows scorer errors!); NaN→null over JSON → `f"{None:.4f}"` crash | Targets are encoded before correlation; every scoring map is multiclass-aware; fail-fast edges in the graph; never format un-validated numbers |
| Zombie pipeline | Agent failure didn't stop the graph — unconditional edges | `_make_failfast_router` on every mid-pipeline edge |
| Live Progress always dead | Frontend hit `/ws/{id}`; backend serves `/ws/runs/{id}/progress` → 403 | Frontend/backend contracts are hand-duplicated — candidate for OpenAPI-generated types |
| LLM Stats tab broken | Same class: response shape mismatch | Same lesson |
| Predict 500 on extra `Id` column | ColumnTransformer requires exact fit-time columns | §5.3 input alignment |
| Predict 500 feature-count mismatch | Engineered features missing at inference | §5.1 complete pipeline recipe |
| `KeyError: '"column"'` killed the first regression run (Boston) | Text-column detection added to the EDA template with *single* braces — `.format()` ate them | **Permanent fix:** `tests/test_agents/test_templates.py` renders all 7 sandbox templates with dummy values and compiles the output — any unescaped brace now fails CI, not a user's run |
| Groq rate limit hit MID-RUN (Boston rerun, iteration 2) — run failed with the chain's aggregate error after groq→ollama→anthropic all failed | Free-tier burst limits; no fallback key configured | The chain worked as designed (clean error, fail-fast). Hardening added: (1) Evaluator persists final_score + iteration_count to the run record after EVERY iteration, so a later crash never erases a completed result; (2) the orchestrator's exception handler closes out any agent step left in "running" state. **User action still needed: add a GEMINI_API_KEY (free) to .env so mid-run limits are absorbed instead of fatal.** |
| Rate limits kept recurring even after the fallback chain | **Measured the actual quota: Groq free tier = 12,000 tokens/MINUTE** (header `x-ratelimit-limit-tokens: 12000`). Our agents fire 600–6,000-token calls back-to-back; the exporter alone ≈ half the minute budget. The 429's Retry-After says "wait 30–60s" — but our retry capped all waits at 20s, giving up moments before the quota returned | Retry-After is now honoured up to 75s (authoritative server signal beats our own backoff guess). A TPM throttle now costs a run ~1 min of waiting instead of failing it |

**The meta-lesson:** every one of these came from testing only the happy path (Titanic
binary classification). Multiclass, string targets, and real prediction traffic each
exposed a class of bugs within minutes of being tried.

---

## 7. Environment Constraints (this machine)

- **Port 80 outbound blocked** → `apt-get` fails → sandbox image cannot add system libs
  (this is why LightGBM is excluded — needs libgomp1)
- PyPI/npm work fine (port 443) → pip/npm installs OK
- **Backend code is volume-mounted** (`./backend:/app`) → edits apply on restart, no rebuild
- **Container recreation wipes pip extras** — after `docker compose up` recreates backend,
  re-run: `docker compose exec backend pip install aiosqlite structlog prometheus-client`
- Host port 3000 occupied → frontend published on **3002**

## 8. How to Run Everything

```bash
docker compose up -d          # all 8 services
# UI        → http://localhost:3002
# API docs  → http://localhost:8000/docs
# MLflow    → http://localhost:5000
# Grafana   → http://localhost:3001  (admin/automl)
# Prometheus→ http://localhost:9090
```

Upload a CSV on the home page, describe the goal, watch the agents work, then from the
run page: read the **Notebook** tab, hit **Deploy**, and use the **Prediction Playground**.

## 9. Verified Runs

| Dataset | Task | Baseline | Final | Winner | Notes |
|---|---|---|---|---|---|
| Titanic | binary classification | 0.872 (CV) | 0.810 (hold-out recall) | GradientBoosting | 3 iterations; different eval methods explain the "drop" |
| Iris | multiclass classification | 0.953 | 0.967 accuracy | RandomForest | First multiclass run; exposed + fixed the bug chain in §6 |

## 9.5 Strategic Positioning (analysis session, 2026-06-12)

**Brain vs hands:** LLM decides (framing, metrics, per-column strategies, feature formulas,
model picks, narrative); templates execute. Action space is bounded by design — the trade
opposite to MLE-STAR. The LLM is evaluated *empirically*, not judged: features must show
CV lift, model picks must win measured CV. "The LLM proposes; sklearn disposes."

**Graph shape:** sequential DAG + one bounded feedback cycle (Evaluator→FeatureEngineer,
max 3) + fail-fast edges. No micro-loops inside agents yet (weakest axis vs MLE-STAR).

**vs Vertex AutoML:** we win on glass-box transparency, ~$0 cost, minutes-not-hours,
data sovereignty, no lock-in. They win on scale, modalities, SLAs. Feature gaps to close:
per-prediction SHAP attribution (cheap), scheduled/drift-triggered retraining (Phase 4),
persistent model server (kills 1s predict latency).

**Web-searching architectures (MLE-STAR style): REJECTED for tabular runtime** — GBDTs +
features beat exotic architectures on tabular (Grinsztajn et al. 2022); pulling unvetted
web code breaks our security invariant (only templates + builtins-stripped eval execute).
Instead: curated technique registry (vetted, versioned model/encoder menu) + domain-knowledge
text retrieval for feature hypotheses. Revisit only if we enter vision/NLP.

**Quant-finance wedge (future):** the research loop, never execution. Needs: purged/embargoed
time-series CV, walk-forward eval, Sharpe/turnover objectives, regime-stability checks.
Selling points: self-hosted (alpha never leaves), auditable hypothesis lineage, minutes-fast.

**Roadmap to beat MLE-STAR micro-loops while staying cheap/predictable:**
1. Self-healing sandbox retries (traceback → LLM fix → retry ≤2, inside agent)
2. Diagnostic router on failure (triage call → jump-back / micro-fix / degrade)
3. Hard budgets on all loops — their adaptability, our predictability
4. Already ahead inline: per-feature CV-lift testing is a free ablation study

## 10. What's Next

**Phase 4 — Production hardening:** API-key auth, rate limiting, dataset versioning,
scheduled retraining triggers on drift, HTTPS, generated OpenAPI client for the frontend
(kills the contract-drift bug class).

**Known gaps / honest debts:**
- `requirements.txt` drift vs running containers (pip extras not in image)
- Old runs (pre-Phase 3) have v1.0 pickles without `engineered_features` — predictions
  on them fail if features were engineered; re-run the pipeline to regenerate
- One prediction ≈ 1s (sandbox exec overhead) — a persistent model server is the Phase 4 fix
- No test coverage yet for inference routes (deploy/predict/drift)
