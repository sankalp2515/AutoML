# Handoff — P7–P17 (code complete; testing is yours)

Backend **39 tests pass**, frontend **tsc clean**, graph builds with the new node.
All endpoints are also wired into `frontend/lib/api.ts` (callable from UI code).
Backend hot-reloads from the volume mount — no rebuild needed except where noted.

## What shipped

| # | Feature | How to test |
|---|---|---|
| **P7** | Dynamic model registry (`app/core/model_registry.py`); model_selector retrieves the menu from it; tuner reads search spaces from it; **HistGradientBoosting** added as one entry | Run any tabular dataset; winner may be HistGradientBoosting. Add a model = one registry entry. |
| **P8** | Tier-2 diagnostic router: a **preprocessor** failure jumps back to EDA **once** (then fails fast). New `diagnostic` graph node + `backjumps_used` state. | Feed a dataset that trips preprocessing; check the run shows an extra EDA pass before failing/recovering. |
| **P9** | What-if: the Deploy tab's prediction playground already does form→predict; `explainPrediction()` adds per-feature SHAP. | Deploy a run, use the playground; call `/explain` for contributions. |
| **P10** | Run-vs-run compare | `GET /api/v1/runs/compare?a=<id>&b=<id>` → metric delta + decision diffs. |
| **P11** | Per-prediction SHAP | `POST /api/v1/runs/{id}/explain` `{"rows":[{...}]}` → top-8 signed contributions/row. |
| **P12** | Champion/challenger retrain | `POST /api/v1/runs/{id}/retrain` → starts a challenger on the same dataset; compare via P10; promote only if it wins. |
| **P13** | Batch scoring | `POST /api/v1/runs/{id}/batch-predict` (multipart CSV) → downloads the CSV with `prediction`,`confidence` columns. |
| **P14** | Ask-your-model (grounded Q&A) | `POST /api/v1/runs/{id}/ask` `{"question":"why drop X?"}` → answer grounded ONLY in that run's decisions/metrics/SHAP. |
| **P15** | Fairness audit | `GET /api/v1/runs/{id}/fairness?columns=Sex,Age` → per-group selection rate/accuracy + disparate-impact ratio (80% rule). |
| **P16** | Opt-in auth + rate limiting (middleware, default OFF) | Set `API_KEY=secret` in `.env` + restart → mutating calls need `X-API-Key`. Set `RATE_LIMIT_PER_MIN=60` for per-IP limiting (Redis). |
| **P17** | Prompt-regression guard (`tests/test_agents/test_prompts.py`) | Pins each prompt to the JSON keys its agent parses — edit a prompt to drop a key → test fails. |

## Quick verify (yours to run)
```
docker compose exec -T backend python -m pytest tests/ -q          # expect 39 passed
docker compose exec -T frontend npx tsc --noEmit                    # clean
# example: compare two completed runs
docker compose exec -T backend python -c "import httpx;print(httpx.get('http://localhost:8000/api/v1/runs/compare?a=<A>&b=<B>',timeout=10).json())"
```

## Notes / scope honesty
- **P7 CatBoost/LightGBM**: registered as `installed=False` recommendations. To make them
  trainable, add to `backend/sandbox/requirements.txt` and `docker compose build sandbox`,
  then flip `installed=True` in the registry. HistGradientBoosting needed no install (sklearn).
- **P9/P10/P11/P14/P15 UI**: backend + `api.ts` client functions are done and callable; only
  the Deploy playground is wired into the page today. Dedicated panels (compare page, ask box,
  fairness view) are thin React wrappers over the existing client functions — fast follow.
- **P16** is intentionally opt-in so it can't break local dev; enable via env vars.
- **P8** is deliberately bounded to one back-jump on preprocessor (the highest-value failure
  point) to avoid graph cycles.
