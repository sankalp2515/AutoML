# AutoML Orchestrator — Project Journal

> **Living document.** Updated alongside every feature, fix, and architecture change.
> Read this top-to-bottom and you understand the entire project without opening code.

Last updated: **2026-06-13** (Tier-1 self-repair micro-loop + pip-extras baked into image)

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
