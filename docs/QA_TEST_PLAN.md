# QA Test Plan — AutoML Orchestrator (Phases 0–4)

**Audience:** a tester with NO prior knowledge of this product. Follow top to bottom.
Every test states exactly what to do and exactly what "pass" looks like. If the
"Expected result" does not happen, the test FAILS — log it (see §8).

---

## 1. What this product does (read once)

You upload a spreadsheet (CSV) and type a goal in plain English (e.g. "predict which
customers will churn"). The system runs **10 automated "agents"** that look at the
data, build a model, tune it, evaluate it, and give you back: a trained model you can
get live predictions from, charts, and a notebook that explains every decision.

You will test (a) that this core flow works, and (b) a set of recent reliability,
correctness, security, and "no-hardcoding" fixes.

## 2. Glossary (terms used below)

| Term | Meaning |
|---|---|
| **Run** | One end-to-end attempt: one uploaded CSV + goal → one trained model. Has a unique ID. |
| **Agent** | One automated step (e.g. "Data Auditor", "Evaluator"). 10 run in order. |
| **Holdout** | Rows set aside and NEVER used for training, so the final score is honest. |
| **Sandbox** | A locked-down container where the data-crunching code actually runs. |
| **Tenant** | A customer/account. Multi-tenant = multiple customers, isolated from each other. |
| **Score** | A number 0–1 (higher usually better) measuring model quality. |

## 3. Environment setup (do this first)

**Prerequisites:** Docker Desktop installed and running; a terminal; the Chrome/Edge browser.

1. Open a terminal in the project folder `automl-orchestrator`.
2. Start everything:
   ```
   docker compose up -d
   ```
   Wait ~1–2 minutes. Check all are running (no "exited"):
   ```
   docker compose ps
   ```
   ✅ Expect: `backend`, `sandbox`, `postgres`, `redis`, `mlflow`, `prometheus`, `grafana`, `frontend` all "running"/"healthy". (`worker` is OFF on purpose — only Test 4.4 uses it.)
3. Apply the database setup:
   ```
   docker compose exec backend alembic upgrade head
   ```
   ✅ Expect: no error; ends at revision `0002_tenant_id`.
4. Confirm the apps open in a browser:
   - App UI → http://localhost:3002  (you should see the home page)
   - API docs → http://localhost:8000/docs
   - Charts (MLflow) → http://localhost:5000
5. Run the automated test suite once (sanity that the build is healthy):
   ```
   docker compose exec backend pytest -q
   ```
   ✅ Expect: `96 passed`.

**If any step above fails, stop and report it — later tests depend on this.**

## 4. Generate test data

In the terminal (any Python 3, no installs needed):
```
python scripts/make_test_data.py
```
✅ Expect: a `test_data/` folder with `iris.csv`, `churn.csv`, `house.csv`, `fraud.csv`, `tiny.csv`.
You will upload these during tests.

## 5. How to "look at results" (you'll use these spots repeatedly)

- **App UI run page** (http://localhost:3002 → open a run): tabs for **Progress** (live agent log), **Results** (scores), **Notebook**, **Deploy** (predictions), **Decision Log**.
- **Database** (for deep checks):
  ```
  docker compose exec postgres psql -U automl -d automl -c "SELECT ...;"
  ```
- **Backend logs:** `docker compose logs backend --tail=100`
- **API directly:** http://localhost:8000/docs (click an endpoint → "Try it out").

---

## 6. PART A — Core product smoke tests (verify the product works at all)

### A1 — Reject a non-CSV upload
- **Purpose:** basic input validation.
- **Steps:** On the home page, start a new model, try to upload a non-CSV file (e.g. a `.txt`). Type a goal of at least 10 characters.
- **Expected:** Upload is rejected with a clear "Only CSV files are supported" message. **Pass/Fail.**

### A2 — Full run end-to-end (Iris, multiclass)
- **Purpose:** the whole pipeline works.
- **Steps:**
  1. Home page → upload `test_data/iris.csv`.
  2. Goal: `Classify the iris flower species from its measurements`.
  3. Submit. Open the run; watch the **Progress** tab.
- **Expected:**
  - ✅ Agents appear and complete in order, ending with the run status **completed** (typically 1–3 minutes).
  - ✅ **Results** tab shows a task type of *multiclass classification*, a winning model name, and a score (~0.9+).
  - ✅ **Notebook** tab renders text + code sections.
  - **Pass/Fail.** (Note the run ID — you'll reuse it.)

### A3 — Deploy and predict
- **Purpose:** the trained model serves live predictions.
- **Steps:** On the completed Iris run → **Deploy** tab → click **Deploy**. A small form appears (one box per input column). Enter plausible numbers (e.g. 5.1, 3.5, 1.4, 0.2) → **Predict**.
- **Expected:** ✅ Returns a predicted species (e.g. "setosa") with a confidence. **Pass/Fail.**

### A4 — Regression run (house prices)
- **Steps:** Upload `test_data/house.csv`, goal `Predict the house price`. Run it.
- **Expected:** ✅ Completes; Results show task type *regression* and an error metric like **RMSE** (a large-ish number, not 0–1). **Pass/Fail.**

---

## 7. PART B — Verify each fix/feature (Phases 0–4)

> Each test names the fix, says what it proves in plain words, then gives steps.

### Phase 0.1 — Two runs at once don't corrupt each other's records
- **Fix:** cost/decision tracking was getting mixed up when two runs overlapped.
- **Type:** UI + DB.
- **Preconditions:** stack running.
- **Steps:**
  1. Open the app in **two browser tabs**.
  2. In tab 1 upload `iris.csv` (goal: classify species). In tab 2 upload `churn.csv` (goal: `Predict whether a customer churns`). Submit both within a few seconds of each other.
  3. Wait for both to finish. Note both run IDs.
  4. In the terminal (`-P pager=off` stops the `--More--` paging you may have seen):
     ```
     docker compose exec postgres psql -U automl -d automl -P pager=off -c "SELECT run_id, agent_name, COUNT(*) FROM llm_calls GROUP BY 1,2 ORDER BY 1;"
     ```
- **Expected:** ✅ Each `run_id` lists only its own agents; no row attributes one run's work to the other run's ID. **Pass/Fail.**

### Phase 0.2a — Honest score uses a real holdout
- **Fix:** the reported final score used to be optimistic (the same data picked the model AND scored it). Now a holdout is reserved before any training.
- **Type:** UI.
- **Steps:**
  1. Run `iris.csv` (if A2 still open, reuse it).
  2. Open the **Decision Log** (or the Evaluator entry in the notebook/results).
- **Expected:**
  - ✅ There is a **"data_splitter"** step early on that reserved a holdout (e.g. "120 train / 30 holdout").
  - ✅ The Evaluator entry says the score is on a **holdout** ("carved from raw data BEFORE any fitting").
  - ✅ The final score is **not suspiciously perfect**; a small drop vs. cross-validation is expected and correct. **Pass/Fail.**

### Phase 0.2b — Tiny datasets fall back safely (no crash)
- **Fix:** with too few rows a holdout would be meaningless; the system must fall back to cross-validation instead of breaking.
- **Steps:** Upload `test_data/tiny.csv` (40 rows), goal `Predict the label`. Run it.
- **Expected:** ✅ Run **completes** (does not error). Decision log notes "dataset too small for a holdout → cross-validation". **Pass/Fail.**

### Phase 0.2c — "Fraud" framing picks the right metric
- **Fix / feature:** the system should choose a metric suited to rare-event detection.
- **Steps:** Upload `test_data/fraud.csv`, goal `Catch fraudulent transactions (fraud is rare)`. Run it. Open Results/Decision Log.
- **Expected:** ✅ The chosen primary metric is **recall** or **pr_auc** (NOT plain accuracy). **Pass/Fail.**

### Phase 0.3 / Phase 1a — Sandbox cannot reach the internet (security)
- **Fix:** the code-execution sandbox is network-isolated, so untrusted code can't phone home.
- **Type:** CLI (one line). **This command is SUPPOSED TO FAIL.**
- **Steps:**
  ```
  docker compose exec sandbox python -c "import urllib.request as u; u.urlopen('https://example.com', timeout=5); print('REACHED INTERNET - FAIL')"
  ```
- **Expected:** ✅ It errors/times out (e.g. "Network is unreachable" / timeout) and does NOT print "REACHED INTERNET". If it prints that line, the test FAILS. **Pass/Fail.**

### Phase 1b — Sandbox not exposed to the host, but reachable internally
- **Steps (Windows cmd — single lines; the backend image has no `curl`, so use python):**
  ```
  curl http://localhost:8001/health
  docker compose exec backend python -c "import urllib.request as u; print(u.urlopen('http://sandbox:8001/health', timeout=5).read())"
  ```
- **Expected:** ✅ First command **fails** (connection refused — no host port). Second prints `{"status":"ok",...}`. **Pass/Fail.**

### Phase 1c — Runaway code is force-killed, service survives
- **Fix:** an infinite loop / crash in generated code can no longer hang or kill the sandbox.
- **Steps (run each as ONE line in Windows cmd):**
  ```
  docker compose exec backend python -c "import httpx; print(httpx.post('http://sandbox:8001/execute', json={'code':'while True: pass','run_id':'qa','timeout':3,'restricted':False}, timeout=60).json().get('error','')[:60])"
  docker compose exec backend python -c "import httpx; print(httpx.post('http://sandbox:8001/execute', json={'code':'RESULT = 2+2','run_id':'qa','timeout':5,'restricted':False}, timeout=60).json())"
  ```
- **Expected:** ✅ First prints a **timeout/killed** message within a few seconds. Second returns a success result with `2+2` → the sandbox is still healthy after the kill. **Pass/Fail.**

### Phase 2 — An agent fixes its own error instead of failing the run
- **Fix:** if a step's built-in recipe hits an edge case, the agent writes and runs a corrected version automatically.
- **Type:** UI + (one-time code edit to force the error path).
- **Steps (happy path first):**
  1. Run `iris.csv` normally → ✅ completes with **no** "writing a fix" messages (the normal path is unaffected).
- **Steps (forced failure — proves self-repair):**
  2. Edit `backend/app/agents/eda_agent.py`: inside the big `EDA_CODE_TEMPLATE` text, add a broken line near the top of the template body, e.g. `this_is_broken_variable + 1`.
  3. Restart backend: `docker compose restart backend` (wait ~15s).
  4. Run `iris.csv` again. Watch the **Progress** tab during the "EDA" step.
- **Expected:** ✅ You see a message like **"Agent writing a fix (1/3)…"**, and the run **continues past EDA and completes** instead of failing.
  5. **Revert** your edit (remove the broken line) and `docker compose restart backend`.
  - **Pass/Fail.**

### Phase 3a — Metric choice adapts to the goal (no hardcoding)
- **Fix:** the metric isn't fixed in code; the system chooses it from your goal.
- **Steps:** Run these three goals (any small CSV that fits) and check the chosen metric in Results/Decision Log:
  - `house.csv` → "Predict the price" → ✅ an error metric (**rmse**/mae).
  - `fraud.csv` → "Catch rare fraud" → ✅ **recall**/pr_auc.
  - `iris.csv` → "Classify the species" → ✅ **f1**/accuracy (a multiclass-appropriate metric).
- **Expected:** ✅ Different, sensible metrics per goal. **Pass/Fail.**

### Phase 3b — Honest marketing copy
- **Steps:** Open the home page (http://localhost:3002). Read the first feature/pillar description.
- **Expected:** ✅ It does **NOT** claim "No templates, no fixed recipes." It describes agents that decide and verify, and write fixes on edge cases. **Pass/Fail.**

### Phase 4a — Default mode unchanged (no login required)
- **Purpose:** with multi-tenant turned OFF (the default), nothing changed for a normal user.
- **Steps:** Confirm `.env` has no `TENANT_API_KEYS` line (or it's empty). Do a normal run with no API key. 
- **Expected:** ✅ Works exactly like Part A (no key needed). **Pass/Fail.**

### Phase 4b — Tenant isolation (customers can't see each other's runs)
- **Type:** config change + API.
- **Steps:**
  1. Add this line to `.env`:
     ```
     TENANT_API_KEYS={"key_a":"acme","key_b":"globex"}
     ```
  2. `docker compose restart backend` (wait ~15s).
  3. Create a run as tenant **acme** (note the returned `id`):
     ```
     curl -H "X-API-Key: key_a" -F "file=@test_data/iris.csv" -F "user_goal=classify the species please" http://localhost:8000/api/v1/runs
     ```
  4. Read it as acme (allowed), then as globex (must be denied), then with no key:
     ```
     curl -H "X-API-Key: key_a" http://localhost:8000/api/v1/runs/<id>      # expect 200 / JSON
     curl -H "X-API-Key: key_b" http://localhost:8000/api/v1/runs/<id>      # expect 404
     curl http://localhost:8000/api/v1/runs/<id>                            # expect 401
     ```
- **Expected:** ✅ acme sees it (HTTP 200); globex gets **404** (as if it doesn't exist); no key gets **401**. ✅ `GET /api/v1/runs` with `key_a` lists only acme's runs. 
  - **Cleanup:** remove the `TENANT_API_KEYS` line from `.env`, `docker compose restart backend`.
  - **Pass/Fail.**

### Phase 4c — Per-tenant active-run limit (quota)
- **Steps:**
  1. In `.env` set `QUOTA_MAX_ACTIVE_RUNS_PER_TENANT=1` (and keep TENANT_API_KEYS from 4b, or use public). `docker compose restart backend`.
  2. Start one run, then **immediately** start a second one (same tenant) before the first finishes.
- **Expected:** ✅ The second request is rejected with **HTTP 429** ("Active-run quota reached"). 
  - **Cleanup:** set the value back to `0`, restart. **Pass/Fail.**

### Phase 4d — Durable queue survives an API restart (opt-in)
- **Purpose:** with the durable queue on, a run keeps going even if the API restarts.
- **Steps:**
  1. In `.env` set `USE_JOB_QUEUE=true`. Start the worker:
     ```
     docker compose --profile worker up -d worker
     ```
  2. Start a run (e.g. `house.csv`). While it's mid-run, restart the API:
     ```
     docker compose restart backend
     ```
  3. Wait and refresh the run page.
- **Expected:** ✅ The run still **completes**. `docker compose logs worker` shows it processed the job.
  - **Cleanup:** set `USE_JOB_QUEUE=false`, `docker compose stop worker`, restart backend. **Pass/Fail.**

### Drift monitoring (Phase 3 product feature)
- **Steps:** On a deployed run (A3), make a few predictions with **unusual** values (far outside training ranges), then open the **Deploy/Drift** view and refresh.
- **Expected:** ✅ Drift indicators update; large shifts are flagged (PSI rising). **Pass/Fail.**

---

## 8. How to report a failure (bug template)

For every FAIL, capture:
```
Test ID:            (e.g. Phase 4b)
What I did:         (exact steps / command)
Expected:           (from this doc)
Actual:             (what happened, exact error text)
Evidence:           run ID, screenshot, and: docker compose logs backend --tail=80
Severity:           blocker / major / minor
```

## 9. Teardown

```
docker compose down            # stop everything (keeps data)
docker compose down -v         # stop AND wipe all data/volumes (clean slate)
```

## 10. Coverage summary

| Area | Tests |
|---|---|
| Core product | A1–A4 |
| Concurrency correctness (0.1) | Phase 0.1 |
| Honest evaluation (0.2) | 0.2a, 0.2b, 0.2c |
| Sandbox security & robustness (0.3/1) | 1a, 1b, 1c |
| Self-healing agents (2) | Phase 2 |
| No hardcoded decisions (3) | 3a, 3b |
| Multi-tenant & queue (4) | 4a, 4b, 4c, 4d |
| Product features | Deploy/Predict (A3), Drift |
