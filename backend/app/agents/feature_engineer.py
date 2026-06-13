import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState

SYSTEM_PROMPT = """You are an expert feature engineer.
You design new features based on EDA insights and baseline error analysis.
Every feature you propose MUST have a hypothesis — a reason why it will help the model.
Do NOT propose exhaustive polynomial features.

Respond with JSON:
{
  "proposed_features": [
    {
      "name": "<feature_name>",
      "formula": "<pandas expression using existing columns>",
      "hypothesis": "<why this will help the model>",
      "source_columns": ["<col1>", "<col2>"]
    }
  ],
  "decisions": [{"decision": "...", "reasoning": "..."}]
}

STRICT Rules:
- Maximum 6 proposed features
- Every feature MUST produce a numeric (float/int) output — NO string labels
- Use np.log1p() NOT np.log() for log transforms (avoids infinity on zero values)
- For age/value binning: use integer codes — pd.cut(..., labels=False) — NOT string labels
- For boolean flags: use (condition).astype(int) — NOT True/False
- Reference only the ORIGINAL raw column names that exist in source_columns
- Prefer ratio and interaction features (numeric / numeric)
- Do NOT propose features that require columns that may have been dropped
"""

FEATURE_CODE_TEMPLATE = '''
import pandas as pd
import numpy as np
import joblib
import json
import os
import warnings
warnings.filterwarnings("ignore")

from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import cross_val_score, StratifiedKFold, KFold

# Load processed data
processed_path = "{processed_path}"
df = pd.read_csv(processed_path)
y = df["__target__"].values
X_base = df.drop(columns=["__target__"])

# Also load raw CSV for original columns (for feature engineering)
df_raw = pd.read_csv(dataset_path)
target_col = "{target_column}"
task_type = "{task_type}"

results = []
proposed = {proposed_features}

for feat in proposed:
    name = feat["name"]
    formula = feat["formula"]
    try:
        # Evaluate formula with column names as variables + pd/np available
        eval_ctx = {{col: df_raw[col] for col in df_raw.columns}}
        eval_ctx.update({{"pd": pd, "np": np, "df": df_raw}})
        new_col = eval(formula, {{"__builtins__": {{}}}}, eval_ctx)
        if not hasattr(new_col, "__len__"):
            new_col = pd.Series([new_col] * len(df_raw))
        new_col = pd.Series(new_col).reset_index(drop=True)

        # Force numeric — drop if non-numeric (e.g. string labels from pd.cut)
        new_col = pd.to_numeric(new_col, errors="coerce")
        # Replace infinity (e.g. log(0))
        new_col = new_col.replace([np.inf, -np.inf], np.nan)

        if new_col.isnull().mean() > 0.5:
            results.append({{"name": name, "kept": False, "reason": "non-numeric or too many nulls after coercion"}})
            continue

        # Fill remaining nulls with column median (always numeric)
        fill_val = float(new_col.median()) if not new_col.isna().all() else 0.0
        new_col = new_col.fillna(fill_val)

        # Measure cross-val lift vs base
        X_aug = pd.concat([X_base.reset_index(drop=True),
                           new_col.reset_index(drop=True).rename(name)], axis=1)

        if task_type == "regression":
            cv = KFold(n_splits=3, shuffle=True, random_state=42)
            model = Ridge()
            scoring = "neg_root_mean_squared_error"
            base_score = float(-cross_val_score(model, X_base, y, cv=cv, scoring=scoring).mean())
            aug_score = float(-cross_val_score(model, X_aug, y, cv=cv, scoring=scoring).mean())
            lift = base_score - aug_score  # lower RMSE is better
        else:
            cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            model = LogisticRegression(max_iter=500, random_state=42)
            scoring = "roc_auc" if task_type == "binary_classification" else "f1_weighted"
            base_score = float(cross_val_score(model, X_base, y, cv=cv, scoring=scoring).mean())
            aug_score = float(cross_val_score(model, X_aug, y, cv=cv, scoring=scoring).mean())
            lift = aug_score - base_score

        kept = lift > 0.002  # keep only if meaningful lift
        results.append({{
            "name": name,
            "kept": kept,
            "cv_lift": round(lift, 5),
            "reason": "positive lift" if kept else f"insufficient lift ({{lift:.5f}})",
            "formula": formula,
            "fill_value": fill_val,  # training-time median — reused at inference
        }})
    except Exception as e:
        results.append({{"name": name, "kept": False, "reason": str(e)}})

# Build enriched dataset with kept features
kept_features = [r for r in results if r["kept"]]
for feat in kept_features:
    try:
        eval_ctx2 = {{col: df_raw[col] for col in df_raw.columns}}
        eval_ctx2.update({{"pd": pd, "np": np, "df": df_raw}})
        col = eval(feat["formula"], {{"__builtins__": {{}}}}, eval_ctx2)
        col = pd.Series(col).reset_index(drop=True)
        col = pd.to_numeric(col, errors="coerce")
        col = col.replace([np.inf, -np.inf], np.nan)
        fill_val = float(col.median()) if not col.isna().all() else 0.0
        col = col.fillna(fill_val)
        df = pd.concat([df, col.reset_index(drop=True).rename(feat["name"])], axis=1)
    except Exception:
        pass

# Save enriched dataset
enriched_path = os.path.join(artifacts_dir, "enriched.csv")
df.to_csv(enriched_path, index=False)

RESULT = {{
    "features_evaluated": results,
    "features_kept": [r for r in results if r["kept"]],
    "features_dropped": [r for r in results if not r["kept"]],
    "enriched_path": enriched_path,
    "n_features_total": df.shape[1] - 1,
}}
'''


class FeatureEngineerAgent(BaseAgent):
    name = "feature_engineer"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Engineering hypothesis-driven features — each one tested for actual lift...")

        eda = state.get("eda_insights", {})
        audit = state.get("data_audit", {})
        issues = state.get("prioritized_issues", [])
        iteration = state.get("iteration", 0)

        shap_context = ""
        if iteration > 0 and state.get("shap_top_features"):
            shap_context = f"\nSHAP top features from previous iteration: {state['shap_top_features']}"

        user_message = f"""
Task: {state['task_type']} | Target: {state['target_column']}
Baseline score: {state.get('baseline_score')} | Current score: {state.get('current_score')}
Iteration: {iteration + 1}

Original columns: {json.dumps(list(audit.get('dtypes', {}).keys())[:30])}
Numeric columns: {json.dumps(eda.get('num_cols', [])[:20])}
Categorical columns: {json.dumps(eda.get('cat_cols', [])[:10])}
Datetime columns: {json.dumps(eda.get('datetime_cols', []))}
High cardinality categoricals: {json.dumps(eda.get('high_cardinality_cols', {}))}

Top correlations with target: {json.dumps(dict(sorted(eda.get('corr_with_target', {}).items(), key=lambda x: -abs(x[1]))[:8]))}
High correlation pairs (multicollinearity risk): {json.dumps(eda.get('high_corr_pairs', [])[:5])}{shap_context}

Top EDA issues:
{chr(10).join(f'- {i}' for i in issues[:5])}

Propose new features with business hypotheses.
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)
        proposed = response.get("proposed_features", [])

        if not proposed:
            await self.emit(run_id, "No new features proposed — moving forward with existing features")
            await self._mark_step(run_id, "completed")
            processed_path = state.get("processed_data_path", "")
            existing_cells = state.get("notebook_cells", [])
            no_feat_cell = {
                "agent": self.name,
                "title": f"Feature Engineering — Iteration {iteration + 1}",
                "iteration": iteration + 1,
                "code": "# LLM determined no hypothesis-driven features were applicable\n# for this iteration. Proceeding with existing engineered features.",
                "stdout": "",
                "result_summary": {
                    "iteration": iteration + 1,
                    "n_proposed": 0,
                    "n_kept": 0,
                    "reason": "LLM found no actionable feature hypotheses given current data and EDA insights",
                },
            }
            return {
                "features_created": [],
                "features_dropped": [],
                "enriched_data_path": processed_path,
                "notebook_cells": existing_cells + [no_feat_cell],
            }

        code = FEATURE_CODE_TEMPLATE.format(
            processed_path=state.get("processed_data_path", ""),
            target_column=state["target_column"],
            task_type=state["task_type"],
            proposed_features=repr(proposed),
        )

        result = await self.execute_code(code, run_id, timeout=300)
        if not result["success"]:
            await self._mark_step(run_id, "failed", result["error"])
            return {"error": f"Feature engineering failed: {result['error']}", "status": "failed"}

        data = result["result"]
        kept = data.get("features_kept", [])
        dropped = data.get("features_dropped", [])

        decision_log_entries = []
        for feat in data.get("features_evaluated", []):
            hypothesis = next((p.get("hypothesis", "") for p in proposed if p.get("name") == feat["name"]), "")
            entry = await self._log_decision(
                run_id=run_id,
                decision=f"Feature '{feat['name']}': {'KEPT' if feat['kept'] else 'DROPPED'}",
                reasoning=f"Hypothesis: {hypothesis}. CV lift: {feat.get('cv_lift', 0):.5f}. Reason: {feat.get('reason')}",
                result_summary=f"lift={feat.get('cv_lift', 0):.5f}",
            )
            decision_log_entries.append(entry)

        from app.core import mlflow_tracker as mlflow
        # Prefix with iteration — MLflow forbids changing a param's value
        mlflow.log_params({
            f"i{iteration}_feature_kept_{i}": f["name"]
            for i, f in enumerate(kept[:5])
        })
        mlflow.log_metric("n_features_engineered_kept", len(kept), step=iteration)

        await self.emit(
            run_id,
            f"Feature engineering: {len(kept)} kept, {len(dropped)} dropped. Total features: {data['n_features_total']}",
            {"kept": [f["name"] for f in kept], "dropped": [f["name"] for f in dropped]},
        )
        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        new_cell = {
            "agent": self.name,
            "title": f"Feature Engineering — Iteration {iteration + 1}",
            "iteration": iteration + 1,
            "code": code,
            "stdout": result.get("stdout", ""),
            "result_summary": {
                "iteration": iteration + 1,
                "n_proposed": len(proposed),
                "n_kept": len(kept),
                "n_dropped": len(dropped),
                "n_features_total": data["n_features_total"],
                "kept_features": [
                    {"name": f["name"], "cv_lift": round(f.get("cv_lift", 0), 5),
                     "formula": f.get("formula", "")}
                    for f in kept
                ],
                "dropped_features": [
                    {"name": f["name"], "reason": f.get("reason", "")}
                    for f in dropped
                ],
                "feature_hypotheses": {
                    p["name"]: p.get("hypothesis", "")
                    for p in proposed
                },
            },
        }
        return {
            "features_created": kept,
            "features_dropped": dropped,
            "enriched_data_path": data.get("enriched_path", state.get("processed_data_path")),
            "decision_log": existing_log + decision_log_entries,
            "notebook_cells": existing_cells + [new_cell],
        }
