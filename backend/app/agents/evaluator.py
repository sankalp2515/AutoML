from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState

EVALUATION_CODE_TEMPLATE = '''
import pandas as pd
import numpy as np
import joblib
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split, cross_val_predict, StratifiedKFold, KFold
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, classification_report, mean_absolute_error,
    mean_squared_error, r2_score
)
from sklearn.calibration import calibration_curve

enriched_path = "{enriched_path}"
tuned_path = "{tuned_path}"
task_type = "{task_type}"
primary_metric = "{primary_metric}"
fp_fn_preference = "{fp_fn_preference}"

df = pd.read_csv(enriched_path)
y = df["__target__"].values
X = df.drop(columns=["__target__"])

model = joblib.load(tuned_path)

# Hold-out test split for unbiased evaluation
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42,
    stratify=y if task_type != "regression" else None
)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

metrics = {{}}
os.makedirs(artifacts_dir, exist_ok=True)

if task_type == "regression":
    mae = mean_absolute_error(y_test, y_pred)
    mse = mean_squared_error(y_test, y_pred)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_test, y_pred)
    metrics = {{"mae": round(mae,4), "mse": round(mse,4), "rmse": round(rmse,4), "r2": round(r2,4)}}

    # Residual plot
    residuals = y_test - y_pred
    fig, ax = plt.subplots(figsize=(8,5))
    ax.scatter(y_pred, residuals, alpha=0.3, s=10)
    ax.axhline(0, color="red", linestyle="--")
    ax.set_xlabel("Predicted"); ax.set_ylabel("Residual")
    ax.set_title("Residual Plot")
    plt.tight_layout()
    fig.savefig(os.path.join(artifacts_dir, "residual_plot.png"), dpi=100)
    plt.close()

    final_score = rmse if primary_metric == "rmse" else (mae if primary_metric == "mae" else r2)
    recommended_threshold = None
    calibration_result = None

else:
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    rec = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    metrics = {{
        "accuracy": round(acc,4), "precision": round(prec,4),
        "recall": round(rec,4), "f1": round(f1,4),
    }}

    try:
        y_proba = model.predict_proba(X_test)
        if task_type == "binary_classification":
            y_proba_pos = y_proba[:, 1]
            auc = roc_auc_score(y_test, y_proba_pos)
            metrics["auc_roc"] = round(auc,4)

            # Threshold selection based on FP/FN preference
            thresholds = np.arange(0.1, 0.9, 0.05)
            best_thresh = 0.5
            if "recall" in fp_fn_preference.lower() or "fn" in fp_fn_preference.lower():
                # Maximize recall at acceptable precision
                best_thresh = float(thresholds[np.argmax([
                    recall_score(y_test, (y_proba_pos >= t).astype(int), zero_division=0)
                    for t in thresholds
                ])])
            elif "precision" in fp_fn_preference.lower() or "fp" in fp_fn_preference.lower():
                best_thresh = float(thresholds[np.argmax([
                    precision_score(y_test, (y_proba_pos >= t).astype(int), zero_division=0)
                    for t in thresholds
                ])])
            else:
                # F1-maximising threshold
                best_thresh = float(thresholds[np.argmax([
                    f1_score(y_test, (y_proba_pos >= t).astype(int), zero_division=0)
                    for t in thresholds
                ])])

            recommended_threshold = best_thresh
            y_pred_final = (y_proba_pos >= best_thresh).astype(int)
            metrics["recall_at_threshold"] = round(recall_score(y_test, y_pred_final, zero_division=0), 4)
            metrics["precision_at_threshold"] = round(precision_score(y_test, y_pred_final, zero_division=0), 4)

            # Calibration
            fraction_pos, mean_pred = calibration_curve(y_test, y_proba_pos, n_bins=10)
            calibration_error = float(np.mean(np.abs(fraction_pos - mean_pred)))
            calibration_result = {{"mean_calibration_error": round(calibration_error, 4),
                                    "well_calibrated": bool(calibration_error < 0.05)}}
        else:
            auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="weighted")
            metrics["auc_roc_weighted"] = round(auc,4)
            recommended_threshold = None
            calibration_result = None
    except Exception:
        recommended_threshold = 0.5
        calibration_result = None

    # Confusion matrix plot
    cm = confusion_matrix(y_test, y_pred)
    fig, ax = plt.subplots(figsize=(6,5))
    import seaborn as sns
    sns.heatmap(cm, annot=True, fmt="d", ax=ax, cmap="Blues")
    ax.set_title("Confusion Matrix"); ax.set_ylabel("True"); ax.set_xlabel("Predicted")
    plt.tight_layout()
    fig.savefig(os.path.join(artifacts_dir, "confusion_matrix.png"), dpi=100)
    plt.close()

    metric_map = {{"auc_roc": metrics.get("auc_roc", metrics.get("auc_roc_weighted", acc)),
                   "recall": rec, "precision": prec, "f1": f1, "accuracy": acc}}
    final_score = metric_map.get(primary_metric, acc)

# SHAP analysis
shap_top_features = []
try:
    import shap
    if hasattr(model, "predict_proba") or hasattr(model, "predict"):
        explainer = shap.TreeExplainer(model) if hasattr(model, "feature_importances_") \
            else shap.LinearExplainer(model, X_train)
        sample = X_test.iloc[:min(200, len(X_test))]
        shap_values = explainer.shap_values(sample)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
        feature_names = X.columns.tolist()
        mean_abs_shap = np.abs(shap_values).mean(axis=0)
        top_idx = np.argsort(mean_abs_shap)[::-1][:15]
        shap_top_features = [feature_names[i] for i in top_idx]

        # SHAP summary plot
        fig, ax = plt.subplots(figsize=(10, 6))
        shap.summary_plot(shap_values, sample, feature_names=feature_names,
                          max_display=15, show=False, plot_type="bar")
        plt.tight_layout()
        fig.savefig(os.path.join(artifacts_dir, "shap_summary.png"), dpi=100, bbox_inches="tight")
        plt.close()
except Exception as e:
    shap_top_features = list(X.columns[:10])

# Slice analysis on top categorical column
slice_performance = {{}}
try:
    df_test = pd.DataFrame(X_test, columns=X.columns)
    df_test["__y_true__"] = y_test
    df_test["__y_pred__"] = y_pred
    cat_cols = X.select_dtypes(exclude=["number"]).columns.tolist()
    if cat_cols:
        col = cat_cols[0]
        for val in df_test[col].value_counts().head(5).index:
            mask = df_test[col] == val
            if mask.sum() > 20:
                slice_y = df_test[mask]["__y_true__"]
                slice_pred = df_test[mask]["__y_pred__"]
                if task_type == "regression":
                    slice_performance[str(val)] = {{"rmse": round(float(np.sqrt(mean_squared_error(slice_y, slice_pred))), 4)}}
                else:
                    slice_performance[str(val)] = {{
                        "recall": round(float(recall_score(slice_y, slice_pred, average="weighted", zero_division=0)), 4),
                        "n": int(mask.sum()),
                    }}
except Exception:
    pass

RESULT = {{
    "metrics": metrics,
    "final_score": round(final_score, 4),
    "recommended_threshold": float(recommended_threshold) if recommended_threshold else 0.5,
    "calibration": calibration_result,
    "shap_top_features": shap_top_features,
    "slice_performance": slice_performance,
    "plots": ["confusion_matrix.png", "shap_summary.png"],
}}
'''


class EvaluatorAgent(BaseAgent):
    name = "evaluator"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Running full evaluation: metrics, slices, calibration, SHAP...")

        code = EVALUATION_CODE_TEMPLATE.format(
            enriched_path=state.get("enriched_data_path", ""),
            tuned_path=state.get("tuned_model_path", state.get("winner_model_path", "")),
            task_type=state["task_type"],
            primary_metric=state["primary_metric"],
            fp_fn_preference=state.get("fp_fn_preference") or "",
        )

        result = await self.execute_code(code, run_id, timeout=400)
        if not result["success"]:
            await self._mark_step(run_id, "failed", result["error"])
            return {"error": f"Evaluation failed: {result['error']}", "status": "failed"}

        data = result["result"]
        final_score = data["final_score"]
        metrics = data["metrics"]

        entry = await self._log_decision(
            run_id=run_id,
            decision=f"Final evaluation: {state['primary_metric']} = {final_score:.4f}",
            reasoning=(
                f"Hold-out test set evaluation (20%). "
                f"All metrics: {metrics}. "
                f"Threshold: {data.get('recommended_threshold')}. "
                f"Calibration: {data.get('calibration')}."
            ),
            result_summary=f"final_score={final_score:.4f}",
        )

        from app.core import mlflow_tracker as mlflow
        mlflow.log_metrics({f"final_{k}": v for k, v in metrics.items() if isinstance(v, (int, float))})
        mlflow.log_metric("final_score", final_score)
        mlflow.log_dict(data.get("slice_performance", {}), "slice_analysis.json")

        import os
        artifact_dir = os.path.join("/data", run_id, "artifacts")
        for plot in data.get("plots", []):
            mlflow.log_artifact(os.path.join(artifact_dir, plot))

        # Persist the score NOW — if a later iteration crashes (e.g. LLM outage),
        # the run record still shows the best completed result.
        await self._update_run_field(
            run_id,
            final_score=final_score,
            iteration_count=state.get("iteration", 0) + 1,
        )

        scores = state.get("iteration_scores", []) + [final_score]
        await self.emit(
            run_id,
            f"Evaluation complete: {final_score:.4f} {state['primary_metric']} | SHAP top: {data['shap_top_features'][:3]}",
            {"final_score": final_score, "metrics": metrics},
        )
        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        iteration = state.get("iteration", 0)
        new_cell = {
            "agent": self.name,
            "title": f"Model Evaluation — Iteration {iteration + 1}",
            "iteration": iteration + 1,
            "code": code,
            "stdout": result.get("stdout", ""),
            "result_summary": {
                "iteration": iteration + 1,
                "final_score": round(final_score, 4),
                "metric": state["primary_metric"],
                "all_metrics": metrics,
                "recommended_threshold": data.get("recommended_threshold", 0.5),
                "calibration": data.get("calibration"),
                "shap_top_features": data.get("shap_top_features", [])[:10],
                "slice_performance": data.get("slice_performance", {}),
                "baseline_score": round(state.get("baseline_score", 0.0), 4),
                "improvement_vs_baseline": round(
                    final_score - state.get("baseline_score", 0.0), 4
                ),
            },
        }
        return {
            "evaluation_report": {"metrics": metrics, "calibration": data.get("calibration")},
            "slice_performance": data.get("slice_performance", {}),
            "recommended_threshold": data.get("recommended_threshold", 0.5),
            "shap_top_features": data.get("shap_top_features", []),
            "current_score": final_score,
            "iteration_scores": scores,
            "decision_log": existing_log + [entry],
            "notebook_cells": existing_cells + [new_cell],
        }
