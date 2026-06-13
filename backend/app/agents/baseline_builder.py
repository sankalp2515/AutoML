from typing import Any

from app.agents.base_agent import BaseAgent
from app.core import mlflow_tracker as mlflow
from app.core.state import AgentState

BASELINE_CODE_TEMPLATE = '''
import pandas as pd
import numpy as np
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import LabelEncoder, StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import cross_val_score, StratifiedKFold, KFold
from sklearn.metrics import (roc_auc_score, f1_score, mean_squared_error,
                              r2_score, accuracy_score)
from sklearn.dummy import DummyClassifier, DummyRegressor
import joblib
import os

df = pd.read_csv(dataset_path)

target_col = "{target_column}"
task_type = "{task_type}"
exclude_cols = {exclude_cols}

# Drop excluded and non-feature columns
drop_cols = [c for c in exclude_cols if c in df.columns]
df = df.drop(columns=drop_cols)
df = df.dropna(subset=[target_col])

X = df.drop(columns=[target_col])
y = df[target_col]

# Encode target for classification
if task_type != "regression":
    le = LabelEncoder()
    y = le.fit_transform(y.astype(str))

# Identify numeric and categorical columns
num_cols = X.select_dtypes(include=["number"]).columns.tolist()
cat_cols = X.select_dtypes(exclude=["number"]).columns.tolist()

# Minimal preprocessing pipeline
preprocessor = ColumnTransformer([
    ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                      ("scale", StandardScaler())]), num_cols),
    ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                      ("enc", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]),
     cat_cols),
], remainder="drop")

# Baseline model
if task_type == "regression":
    model = Ridge()
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    scoring = "neg_root_mean_squared_error"
else:
    model = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scoring = "roc_auc" if task_type == "binary_classification" else "f1_weighted"

pipeline = Pipeline([("prep", preprocessor), ("model", model)])
scores = cross_val_score(pipeline, X, y, cv=cv, scoring=scoring, n_jobs=1)

if task_type == "regression":
    baseline_score = float(-scores.mean())
else:
    baseline_score = float(scores.mean())

# Dummy baseline for comparison
if task_type == "regression":
    dummy = DummyRegressor(strategy="mean")
    dummy_scores = cross_val_score(dummy, X, y, cv=cv,
                                   scoring=scoring, n_jobs=1)
    dummy_score = float(-dummy_scores.mean())
else:
    dummy = DummyClassifier(strategy="most_frequent")
    dummy_scores = cross_val_score(dummy, X, y, cv=cv,
                                   scoring=scoring, n_jobs=1)
    dummy_score = float(dummy_scores.mean())

# Fit on full data and save the baseline pipeline for error analysis
pipeline.fit(X, y)

os.makedirs(artifacts_dir, exist_ok=True)
baseline_path = os.path.join(artifacts_dir, "baseline_pipeline.pkl")
joblib.dump(pipeline, baseline_path)

# Error analysis: find hard samples (where baseline is most wrong)
if task_type != "regression":
    try:
        y_pred_proba = pipeline.predict_proba(X)[:, 1] if task_type == "binary_classification" \
            else pipeline.predict_proba(X).max(axis=1)
        y_pred = pipeline.predict(X)
        error_mask = (y_pred != y)
        hard_sample_profile = df[error_mask].describe().to_dict() if error_mask.any() else {{}}
        error_rate = float(error_mask.mean())
    except Exception:
        hard_sample_profile = {{}}
        error_rate = 0.0
else:
    y_pred = pipeline.predict(X)
    residuals = np.abs(y - y_pred)
    error_mask = residuals > residuals.quantile(0.75)
    hard_sample_profile = df[error_mask].describe().to_dict() if error_mask.any() else {{}}
    error_rate = float(error_mask.mean())

RESULT = {{
    "baseline_score": baseline_score,
    "dummy_score": dummy_score,
    "baseline_model": "LogisticRegression" if task_type != "regression" else "Ridge",
    "score_std": float(scores.std()),
    "n_features": X.shape[1],
    "n_samples": X.shape[0],
    "baseline_path": baseline_path,
    "error_rate_on_train": error_rate,
    "metric_used": "{scoring}",
}}
'''


class BaselineBuilderAgent(BaseAgent):
    name = "baseline_builder"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Training baseline model first — this establishes our performance floor...")

        scoring_map = {
            "auc_roc": "roc_auc", "recall": "recall", "precision": "precision",
            "f1": "f1", "accuracy": "accuracy", "rmse": "neg_root_mean_squared_error",
            "mae": "neg_mean_absolute_error", "r2": "r2",
        }
        if state["task_type"] == "regression":
            default_scoring = "neg_root_mean_squared_error"
        elif state["task_type"] == "multiclass_classification":
            default_scoring = "f1_weighted"
        else:
            default_scoring = "roc_auc"
        scoring = scoring_map.get(state.get("primary_metric", ""), default_scoring)

        # Binary-only scorers produce NaN on multiclass — remap to weighted variants
        if state["task_type"] == "multiclass_classification":
            scoring = {
                "roc_auc": "roc_auc_ovr_weighted",
                "recall": "recall_weighted",
                "precision": "precision_weighted",
                "f1": "f1_weighted",
            }.get(scoring, scoring)

        code = BASELINE_CODE_TEMPLATE.format(
            target_column=state["target_column"],
            task_type=state["task_type"],
            exclude_cols=repr(state.get("exclude_columns", [])),
            scoring=scoring,
        )

        result = await self.execute_code(code, run_id, timeout=180)
        if not result["success"]:
            await self._mark_step(run_id, "failed", result["error"])
            return {"error": f"Baseline training failed: {result['error']}", "status": "failed"}

        data = result["result"]
        baseline_score = data["baseline_score"]
        dummy_score = data["dummy_score"]
        lift = ((baseline_score - dummy_score) / abs(dummy_score)) * 100 if dummy_score else 0

        entry = await self._log_decision(
            run_id=run_id,
            decision=f"Baseline established: {data['baseline_model']} achieves {baseline_score:.4f} {data['metric_used']}",
            reasoning=(
                f"Trained simplest possible model ({data['baseline_model']}) with minimal preprocessing "
                f"to establish a performance floor. Dummy score: {dummy_score:.4f}. "
                f"Baseline lifts {lift:.1f}% over naive baseline. "
                f"Every subsequent step is measured against {baseline_score:.4f}."
            ),
            code_executed=code[:300],
            result_summary=f"baseline={baseline_score:.4f}, dummy={dummy_score:.4f}, n_samples={data['n_samples']}",
        )

        mlflow.log_metric("baseline_score", baseline_score)
        mlflow.log_metric("dummy_score", dummy_score)
        mlflow.log_params({"baseline_model": data["baseline_model"], "n_features": data["n_features"]})

        await self._update_run_field(run_id, baseline_score=baseline_score)

        await self.emit(
            run_id,
            f"Baseline: {baseline_score:.4f} ({data['metric_used']}). Dummy: {dummy_score:.4f}. Lift: +{lift:.1f}%",
            {"baseline_score": baseline_score, "dummy_score": dummy_score},
        )
        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        new_cell = {
            "agent": self.name,
            "title": "Baseline Model Benchmark",
            "iteration": 0,
            "code": code,
            "stdout": result.get("stdout", ""),
            "result_summary": {
                "baseline_model": data["baseline_model"],
                "baseline_score": round(baseline_score, 4),
                "dummy_score": round(dummy_score, 4),
                "lift_over_dummy_pct": round(lift, 1),
                "metric_used": data["metric_used"],
                "n_samples": data["n_samples"],
                "n_features": data["n_features"],
                "error_rate_on_train": round(data.get("error_rate_on_train", 0), 4),
            },
        }
        return {
            "baseline_score": baseline_score,
            "baseline_model": data["baseline_model"],
            "baseline_errors": {
                "error_rate_on_train": data.get("error_rate_on_train"),
                "baseline_path": data.get("baseline_path"),
            },
            "current_score": baseline_score,
            "prev_score": 0.0,
            "iteration": 0,
            "max_iterations": state.get("max_iterations", 3),
            "iteration_scores": [baseline_score],
            "decision_log": existing_log + [entry],
            "notebook_cells": existing_cells + [new_cell],
        }
