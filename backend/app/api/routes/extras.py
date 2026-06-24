"""
Backlog P10–P15 — endpoints that reuse the existing sandbox executor, LLM client,
and DB. Each is self-contained; sandbox code uses token-replace (repr) injection.

  GET  /runs/compare?a=&b=            P10 — run-vs-run diff
  POST /runs/{id}/batch-predict       P13 — score an uploaded CSV
  POST /runs/{id}/explain             P11 — per-prediction SHAP attribution
  POST /runs/{id}/ask                 P14 — grounded Q&A over a run
  GET  /runs/{id}/fairness?columns=   P15 — sliced metrics + disparate impact
  POST /runs/{id}/retrain             P12 — champion/challenger retrain
"""

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.routes.inference import PREDICT_CODE
from app.config import settings
from app.core.llm import get_llm
from app.database import AsyncSessionLocal
from app.models.run import DecisionLog, Deployment, PredictionLog, Run
from app.redis_client import get_run_state
from app.sandbox.executor import get_executor

router = APIRouter(prefix="/api/v1", tags=["extras"])


async def _run_or_404(db, run_id: str) -> Run:
    r = (await db.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Run not found")
    return r


# ── P10: run-vs-run comparison ────────────────────────────────────────────────
@router.get("/runs/compare")
async def compare_runs(a: str, b: str) -> dict:
    async with AsyncSessionLocal() as db:
        ra, rb = await _run_or_404(db, a), await _run_or_404(db, b)

        def summary(r: Run) -> dict:
            return {
                "run_id": r.id, "dataset": r.dataset_filename, "task_type": r.task_type,
                "target": r.target_column, "metric": r.primary_metric,
                "baseline": r.baseline_score, "final": r.final_score,
                "winner": r.winner_model, "iterations": r.iteration_count, "status": r.status,
            }

        async def decisions(run_id: str) -> list[dict]:
            rows = (await db.execute(
                select(DecisionLog).where(DecisionLog.run_id == run_id)
                .order_by(DecisionLog.timestamp)
            )).scalars().all()
            return [{"agent": d.agent_name, "decision": d.decision} for d in rows]

        sa, sb = summary(ra), summary(rb)
        delta = None
        if ra.final_score is not None and rb.final_score is not None:
            delta = round(rb.final_score - ra.final_score, 4)
        return {
            "a": sa, "b": sb,
            "final_score_delta": delta,
            "decisions_a": await decisions(a),
            "decisions_b": await decisions(b),
        }


# ── P13: batch scoring ────────────────────────────────────────────────────────
@router.post("/runs/{run_id}/batch-predict")
async def batch_predict(run_id: str, file: UploadFile = File(...)) -> StreamingResponse:
    async with AsyncSessionLocal() as db:
        await _run_or_404(db, run_id)
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)[:5000]
    if not rows:
        raise HTTPException(400, "CSV is empty")

    code = PREDICT_CODE.replace("INPUT_ROWS", repr(rows))
    result = await get_executor().execute(code, run_id, timeout=120)
    if not result.get("success"):
        raise HTTPException(500, f"Batch scoring failed: {str(result.get('error',''))[:300]}")
    preds = result["result"]["predictions"]

    out = io.StringIO()
    fields = list(rows[0].keys()) + ["prediction", "confidence"]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for row, p in zip(rows, preds):
        pv = p["prediction"]
        row["prediction"] = json.dumps(pv) if isinstance(pv, list) else pv
        row["confidence"] = p.get("confidence")
        w.writerow(row)
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scored_{run_id[:8]}.csv"'},
    )


# ── P11: per-prediction SHAP ──────────────────────────────────────────────────
class ExplainRequest(BaseModel):
    rows: list[dict[str, Any]]


_EXPLAIN_CODE = '''
import joblib, os, numpy as np, pandas as pd
data = joblib.load(os.path.join(artifacts_dir, "inference_pipeline.pkl"))
prep, model = data["preprocessor"], data["model"]
rows = INPUT_ROWS
X = pd.DataFrame(rows)
if prep is not None and hasattr(prep, "feature_names_in_"):
    for c in prep.feature_names_in_:
        if c not in X.columns: X[c] = np.nan
    X = X[list(prep.feature_names_in_)]
    for c in X.columns:
        if X[c].dtype == object: X[c] = X[c].fillna("")
Xt = prep.transform(X) if prep is not None else X.values
try:
    names = list(prep.get_feature_names_out())
except Exception:
    names = [f"f_{i}" for i in range(Xt.shape[1])]
out = []
try:
    import shap
    expl = shap.TreeExplainer(model) if hasattr(model, "feature_importances_") else shap.Explainer(model, Xt)
    sv = expl.shap_values(Xt) if hasattr(expl, "shap_values") else expl(Xt).values
    if isinstance(sv, list): sv = sv[1] if len(sv) > 1 else sv[0]
    sv = np.asarray(sv)
    for i in range(sv.shape[0]):
        contrib = sorted(zip(names, sv[i].tolist()), key=lambda t: -abs(t[1]))[:8]
        out.append([{"feature": n, "contribution": round(float(v), 5)} for n, v in contrib])
except Exception as e:
    out = [{"error": str(e)[:120]}]
RESULT = {"explanations": out}
'''


@router.post("/runs/{run_id}/explain")
async def explain(run_id: str, req: ExplainRequest) -> dict:
    if not req.rows:
        raise HTTPException(400, "rows required")
    code = _EXPLAIN_CODE.replace("INPUT_ROWS", repr(req.rows[:20]))
    result = await get_executor().execute(code, run_id, timeout=90)
    if not result.get("success"):
        raise HTTPException(500, f"Explain failed: {str(result.get('error',''))[:300]}")
    return {"run_id": run_id, **result["result"]}


# ── P14: ask-your-model (grounded Q&A) ────────────────────────────────────────
class AskRequest(BaseModel):
    question: str


@router.post("/runs/{run_id}/ask")
async def ask(run_id: str, req: AskRequest) -> dict:
    async with AsyncSessionLocal() as db:
        run = await _run_or_404(db, run_id)
        logs = (await db.execute(
            select(DecisionLog).where(DecisionLog.run_id == run_id).order_by(DecisionLog.timestamp)
        )).scalars().all()
    state = await get_run_state(run_id)
    context = {
        "task_type": run.task_type, "target": run.target_column, "metric": run.primary_metric,
        "baseline": run.baseline_score, "final": run.final_score, "winner": run.winner_model,
        "shap_top_features": (state or {}).get("shap_top_features"),
        "decisions": [{"agent": d.agent_name, "decision": d.decision, "why": d.reasoning} for d in logs],
    }
    system = (
        "You answer questions about a completed AutoML run STRICTLY from the provided JSON "
        "context (decisions, metrics, SHAP). Never invent numbers. If the context lacks the "
        'answer, say so. Respond as JSON: {"answer": "...", "cited_agents": ["..."]}'
    )
    user = f"Run context:\n{json.dumps(context, default=str)[:6000]}\n\nQuestion: {req.question}"
    try:
        resp = await get_llm().complete_json(system, user)
    except Exception as e:
        raise HTTPException(500, f"Ask failed: {str(e)[:200]}")
    return {"run_id": run_id, **resp}


# ── P15: fairness audit ───────────────────────────────────────────────────────
_FAIRNESS_CODE = '''
import joblib, os, numpy as np, pandas as pd
from sklearn.metrics import accuracy_score, recall_score
data = joblib.load(os.path.join(artifacts_dir, "inference_pipeline.pkl"))
prep, model = data["preprocessor"], data["model"]
df = pd.read_csv(dataset_path)
target_col = TARGET_COL
sensitive = SENSITIVE_COLS
groups = {}
for col in sensitive:
    if col not in df.columns: continue
    col_out = {}
    for val in df[col].dropna().astype(str).value_counts().head(8).index:
        sub = df[df[col].astype(str) == val]
        if len(sub) < 20: continue
        X = sub.drop(columns=[c for c in [target_col] + sensitive if c in sub.columns], errors="ignore")
        try:
            if prep is not None and hasattr(prep, "feature_names_in_"):
                for c in prep.feature_names_in_:
                    if c not in X.columns: X[c] = np.nan
                X = X[list(prep.feature_names_in_)]
                for c in X.columns:
                    if X[c].dtype == object: X[c] = X[c].fillna("")
            Xt = prep.transform(X) if prep is not None else X.values
            pred = model.predict(Xt)
            y = sub[target_col]
            if not pd.api.types.is_numeric_dtype(y):
                y = y.astype("category").cat.codes
            col_out[str(val)] = {
                "n": int(len(sub)),
                "selection_rate": round(float(np.mean(np.asarray(pred).astype(float) > 0)), 4),
                "accuracy": round(float(accuracy_score(y, pred)), 4),
            }
        except Exception as e:
            col_out[str(val)] = {"error": str(e)[:80]}
    # disparate impact: min/max selection rate ratio (80% rule)
    rates = [v["selection_rate"] for v in col_out.values() if "selection_rate" in v]
    di = round(min(rates) / max(rates), 3) if rates and max(rates) > 0 else None
    groups[col] = {"by_group": col_out, "disparate_impact_ratio": di,
                   "passes_80pct_rule": (di is not None and di >= 0.8)}
RESULT = {"fairness": groups}
'''


@router.get("/runs/{run_id}/fairness")
async def fairness(run_id: str, columns: str) -> dict:
    cols = [c.strip() for c in columns.split(",") if c.strip()]
    if not cols:
        raise HTTPException(400, "columns query param required (comma-separated)")
    async with AsyncSessionLocal() as db:
        run = await _run_or_404(db, run_id)
    code = (_FAIRNESS_CODE
            .replace("TARGET_COL", repr(run.target_column or ""))
            .replace("SENSITIVE_COLS", repr(cols)))
    result = await get_executor().execute(code, run_id, timeout=120)
    if not result.get("success"):
        raise HTTPException(500, f"Fairness audit failed: {str(result.get('error',''))[:300]}")
    return {"run_id": run_id, **result["result"]}


# ── P12: champion/challenger retrain ──────────────────────────────────────────
@router.post("/runs/{run_id}/retrain")
async def retrain(run_id: str, background_tasks: BackgroundTasks) -> dict:
    async with AsyncSessionLocal() as db:
        champ = await _run_or_404(db, run_id)
        new_id = str(uuid.uuid4())
        challenger = Run(
            id=new_id, status="queued",
            dataset_filename=champ.dataset_filename, dataset_path=champ.dataset_path,
            user_goal=champ.user_goal, exclude_columns=champ.exclude_columns or [],
            fp_fn_preference=champ.fp_fn_preference, interpretability_required=champ.interpretability_required,
            pipeline=getattr(champ, "pipeline", "tabular"),
        )
        db.add(challenger)
        await db.flush()

    from app.agents.orchestrator import run_pipeline
    background_tasks.add_task(run_pipeline, new_id)
    return {
        "champion_run_id": run_id, "challenger_run_id": new_id,
        "note": "Challenger training started. Compare via GET /runs/compare?a={champ}&b={challenger}; "
                "promote only if the challenger's final score beats the champion.",
    }
