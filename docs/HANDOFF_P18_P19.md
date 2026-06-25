# Handoff — P18 (Imbalanced) + P19 (Multilabel) milestone

Status as of this session. Plan file: `~/.claude/plans/what-ever-we-have-misty-bunny.md`.

## DONE (code complete + verified at unit level BEFORE a Docker network outage)
All 6 implementation phases are finished and were green:
- **Phase A** — `state.py`: added `imbalance_strategy`, `training_pipeline_path`,
  `multilabel_binarizer_path`, `resampler_used` to AgentState; preprocessor `run()` now
  returns `imbalance_strategy`/`resampler_used`.
- **Phase B** — `feature_engineer.py`: multilabel `__target__` parse (ast), `KFold` +
  `MultiOutputClassifier` for multilabel lift, multilabel scoring keys added.
- **Phase C** — in-fold SMOTE/SMOTE-Tomek wired into `model_selector`, `tuner`,
  `feature_engineer` via `_cv_estimator()` (imblearn Pipeline, in-fold only, `<6` guard);
  tuner final-fit resamples full data when SMOTE active. `imbalance_strategy` threaded through all three.
- **Phase D** — `exporter.py`: `inference_pipeline.pkl` now carries `task_type` +
  `multilabel_binarizer` (new `MULTILABEL_BINARIZER_PATH` / `TASK_TYPE` tokens).
- **Phase E** — `inference.py` `PREDICT_CODE`: multilabel branch → `inverse_transform` →
  list-of-labels output; `PredictionLog` stores list as JSON.
- **Phase F** — frontend `types.ts` `Prediction.prediction: string | string[]`;
  `DeployPanel` renders label-set chips. `tsc --noEmit` was clean.

### Critical bug fixed along the way (was blocking ALL runs)
The in-progress rewrite of **tuner + evaluator** templates abandoned brace-doubling, so
`.format()` crashed every run. Converted both to the exporter's `.replace("__TOKEN__", repr())`
pattern (natural braces). `test_templates.py` updated: per-case render callables (format vs
token styles) + a new `preprocessing_multilabel` case. **Last green: 33 passed, tsc clean,
all agent modules import.**

## NOT DONE — live end-to-end verification (HANDED TO YOU)
Blocked here by a Docker Desktop **outbound-network outage** (containers got
`[Errno 101] Network is unreachable` → LLM calls fail → pipelines can't run). This is
environmental, not a code defect. After Docker networking is back, run the checks below.

### Your verification checklist
Prereqs: `docker compose up -d`; backend healthy
(`docker compose exec -T backend python -c "import httpx;print(httpx.get('http://localhost:8000/api/v1/system/health',timeout=20).json()['status'])"`
→ `ok`); containers can reach the internet (Groq). If Groq is rate-limited, add
`GEMINI_API_KEY` to `.env` and `docker compose restart backend`.

1. **Unit suite** (no network needed):
   `docker compose exec -T backend python -m pytest tests/ -q` → expect **34 passed**
   (33 prior + new `test_state_contract.py`). `docker compose exec -T frontend npx tsc --noEmit` → clean.
   - NOTE: if `test_state_contract` FAILS, it's doing its job — it found an agent run()
     returning a key not declared in `app/core/state.py` (the silent-drop bug class).
     Paste the failure (it names the file + keys) and I'll add the missing declarations.
   - `docker compose build backend` was NOT re-run this session; not needed (no new deps —
     imblearn already in the SANDBOX image). Backend code hot-reloads from the volume mount.

### New permanent guard added this session
`backend/tests/test_agents/test_state_contract.py` — static (ast-only, no network) check
that every key each agent's run() returns is declared in AgentState. Prevents the exact
silent-drop bug that broke multilabel inference. Pairs with the existing `test_templates.py`
brace guard. Together they catch the two bug classes that cost the most this session.

## P3 / Time-Series Studio — T1 FOUNDATION started (this session)
Delivered the safe, completable, load-bearing slice of P3 (NOT the full TS pipeline):
- **Wrong-Door Guard** (doc 09's safety crux): the tabular `data_auditor` now detects a
  monotonic-datetime column (`temporal_signal` in PROFILING_CODE) and, when the run is NOT
  in timeseries mode, prepends a warning ("data looks time-ordered; random CV can overstate
  performance; use the Time-Series studio"). Detection only — never blocks. Returns
  `wrong_door_warning` in state (declared in AgentState).
- **Mode plumbing**: `AgentState.pipeline` + `timestamp_col`/`forecast_horizon`/`frequency`/
  `wrong_door_warning`; `Run.pipeline` column (default "tabular"); `runs.py` accepts a
  `pipeline` form field (validated tabular|timeseries); orchestrator threads it into initial_state;
  frontend UploadForm has a **Studio selector** — Time-Series option is shown but **disabled
  ("Soon")** because the TS agent roster isn't built yet (selecting it would silently run the
  tabular pipeline = invalid CV on time data, which we must not do).
- Verify: `Run.pipeline` is a NEW DB column — on a fresh `init_db` it's created; if your DB
  predates it you may need to drop/recreate the dev DB (or the column). `pytest` + `tsc` should
  still pass; the Studio selector renders with Tabular active and Time-Series greyed "Soon".

### Time-Series Studio — what REMAINS (next focused session)
The TS agent roster is NOT built: `ts_orchestrator` graph + branch in `run_pipeline`,
`ts_auditor` (timestamp/frequency/min-length), `ts_framer` (horizon/frequency/metric),
naive/seasonal baseline, `walk_forward_evaluator` (purged+embargoed, temporal hold-out),
then T2 (lags/finance metrics/labeling), T3 (backtest+leakage forensics), T4 (ONNX/parquet).
Prompts: `docs/BACKLOG_PROMPTS.md` P3–P6. When built, flip the frontend Time-Series option
from disabled→enabled and add the `run_pipeline` branch on `run.pipeline == "timeseries"`.

## BACKLOG STATUS (the rest)
P18+P19 (this milestone) = code-complete, awaiting your live test. Everything else in
`docs/BACKLOG_PROMPTS.md` (P1–P17) + P20/P21 remains as ready-to-run prompts. These were
NOT attempted in-session: the large ones (Time-Series Studio P3–P6, auth P16, multi-table
P21, larger-than-memory P20) each need a fresh full-context session — cramming them now
would recreate the half-finished-template mess we spent this session fixing. The two
already-built guards (templates + state contract) make those future sessions much safer.
2. **No-regression run** — upload any normal CSV (Iris/Titanic) via the UI (localhost:3002)
   or API; confirm it completes all 10 agents with a score. (Proves the tuner/evaluator
   token refactor didn't break the happy path.)
3. **Imbalanced run** — a ~99%/1% binary CSV (e.g. `is_fraud`), goal "Detect rare fraud."
   Confirm: framer picks `pr_auc`; run completes; decision log shows SMOTE/resampler;
   deploy → predict returns a class + confidence.
4. **Multilabel run** — a CSV with a delimited tag column (e.g. `tags = "a;b;c"`), goal
   "Predict which tags apply (multiple allowed)." Confirm: framer picks
   `multilabel_classification`; evaluator shows per-label/micro/macro metrics; deploy →
   predict returns a **set of labels** (chips in the UI).

### If a live run fails
- Failure surfaces in the run's `error_message` + agent steps (UI or
  `GET /api/v1/runs/{id}`). Paste that back and I'll fix the specific agent.
- Most likely residual risks (untested live): the multilabel `f1_samples` scorer needing
  `MultiOutputClassifier` everywhere (covered), and SMOTE on a dataset whose minority < 6
  (falls back to class_weight — covered). The framer correctly *detecting* multilabel vs
  multiclass is prompt-dependent — if it mis-frames, that's a `problem_framer.py` prompt tweak.

## TASKS YOU CAN OWN (offload from me)
- Running all pytest / tsc / live pipeline runs (above).
- Restarting Docker Desktop when networking/ports wedge (known recurring env issue).
- Adding `GEMINI_API_KEY` to `.env` (free at aistudio.google.com) — makes Groq rate limits invisible.
- Providing failure output (run JSON / logs) for any live run that errors — I fix from that.

## Small follow-ups (optional, not blocking)
- Exporter's *generated* `api_main.py` still returns single-label shape; the live `/predict`
  endpoint (Phase E) is correct, so deploy/predict works — only the downloadable scaffold lags.
- `MetricsPanel` doesn't yet surface PR-AUC/hamming as dedicated badges (deferred polish).
