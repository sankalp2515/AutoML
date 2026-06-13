import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState

SYSTEM_PROMPT = """You are an expert ML preprocessing engineer.
Based on the EDA insights, dataset audit, and prioritized issues, generate a sklearn Pipeline preprocessing strategy.

Respond with JSON:
{
  "decisions": [
    {
      "column": "<col_name>",
      "issue": "<what was found>",
      "strategy": "<what to do>",
      "reasoning": "<why this strategy>",
      "sklearn_step": "<imputer/encoder/scaler choice>"
    }
  ],
  "drop_columns": ["<cols to drop entirely with reason>"],
  "imputation_strategy": {
    "<col>": "median" | "mean" | "most_frequent" | "constant" | "knn"
  },
  "encoding_strategy": {
    "<col>": "onehot" | "ordinal" | "target" | "frequency" | "text_tfidf"
  },
  "scaling_strategy": "standard" | "minmax" | "robust" | "none",
  "handle_imbalance": true | false,
  "imbalance_strategy": "class_weight" | "smote" | "none"
}

Use "text_tfidf" for FREE-TEXT columns (reviews, descriptions, messages — avg length > 30 chars).
TF-IDF extracts up to 200 n-gram features per text column. Never one-hot a free-text column.
"""

PREPROCESSING_CODE_TEMPLATE = '''
import pandas as pd
import numpy as np
import joblib
import json
import os
import warnings
warnings.filterwarnings("ignore")

from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer, KNNImputer
from sklearn.preprocessing import (StandardScaler, MinMaxScaler, RobustScaler,
                                    OneHotEncoder, OrdinalEncoder, LabelEncoder)
from sklearn.compose import ColumnTransformer

df = pd.read_csv(dataset_path)
target_col = "{target_column}"
task_type = "{task_type}"
drop_cols = {drop_columns}
exclude_cols = {exclude_cols}

# Drop user-excluded and agent-flagged columns
all_drop = list(set(drop_cols + exclude_cols + [target_col]))
drop_existing = [c for c in all_drop if c in df.columns]
df = df.drop(columns=drop_existing, errors="ignore")
df = df.dropna(subset=[]) # keep all rows, imputer handles nulls

# Parse datetime columns
datetime_cols = {datetime_cols}
for c in datetime_cols:
    if c in df.columns:
        dt = pd.to_datetime(df[c], errors="coerce")
        df[c + "_year"] = dt.dt.year
        df[c + "_month"] = dt.dt.month
        df[c + "_day"] = dt.dt.day
        df[c + "_dayofweek"] = dt.dt.dayofweek
        df = df.drop(columns=[c])

# Final feature columns
feature_cols = df.columns.tolist()
num_cols = df.select_dtypes(include=["number"]).columns.tolist()
cat_cols = df.select_dtypes(exclude=["number"]).columns.tolist()

# Imputation
imputation = {imputation_strategy}
num_imputer_default = "{num_imputer_default}"
cat_imputer_default = "most_frequent"

num_imputers = []
cat_imputers = []

# Build column-level imputers
for c in num_cols:
    strategy = imputation.get(c, num_imputer_default)
    if strategy == "knn":
        num_imputers.append((c, KNNImputer(n_neighbors=5), [c]))
    # else handled in global imputer

num_global_imputer = SimpleImputer(strategy=num_imputer_default)
cat_global_imputer = SimpleImputer(strategy=cat_imputer_default, fill_value="missing")

# Encoding
encoding = {encoding_strategy}

# Free-text columns → TF-IDF (handled as dedicated ColumnTransformer entries).
# Must be removed from cat_cols BEFORE the onehot/ordinal splits below.
tfidf_cols = [c for c in cat_cols if encoding.get(c) == "text_tfidf"]
for c in tfidf_cols:
    df[c] = df[c].fillna("").astype(str)   # TfidfVectorizer rejects NaN
    cat_cols = [x for x in cat_cols if x != c]

onehot_cols = [c for c in cat_cols if encoding.get(c, "onehot") == "onehot"]
ordinal_cols = [c for c in cat_cols if encoding.get(c) == "ordinal"]
freq_cols = [c for c in cat_cols if encoding.get(c) == "frequency"]

# Frequency encoding applied before ColumnTransformer
for c in freq_cols:
    freq_map = df[c].value_counts(normalize=True).to_dict()
    df[c + "_freq"] = df[c].map(freq_map).fillna(0)
    df = df.drop(columns=[c])
    num_cols.append(c + "_freq")
    cat_cols = [x for x in cat_cols if x != c]

onehot_cols = [c for c in cat_cols if encoding.get(c, "onehot") == "onehot"]
ordinal_cols_remaining = [c for c in cat_cols if encoding.get(c) == "ordinal"]

# Scaling
scaling = "{scaling_strategy}"
if scaling == "standard":
    scaler = StandardScaler()
elif scaling == "minmax":
    scaler = MinMaxScaler()
elif scaling == "robust":
    scaler = RobustScaler()
else:
    scaler = "passthrough"

# Build ColumnTransformer
transformers = []
if num_cols:
    transformers.append((
        "num",
        Pipeline([("imp", num_global_imputer), ("scale", scaler)]),
        num_cols
    ))
if onehot_cols:
    transformers.append((
        "cat_onehot",
        Pipeline([("imp", cat_global_imputer),
                  ("enc", OneHotEncoder(handle_unknown="ignore", sparse_output=False, max_categories=50))]),
        onehot_cols
    ))
if ordinal_cols_remaining:
    transformers.append((
        "cat_ordinal",
        Pipeline([("imp", cat_global_imputer),
                  ("enc", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1))]),
        ordinal_cols_remaining
    ))

# TF-IDF for free-text columns — note: column selector is a STRING (1-D input),
# which is what TfidfVectorizer requires inside a ColumnTransformer.
from sklearn.feature_extraction.text import TfidfVectorizer
for c in tfidf_cols:
    transformers.append((
        f"tfidf_{{c}}",
        TfidfVectorizer(max_features=200, ngram_range=(1, 2), min_df=2,
                        sublinear_tf=True, strip_accents="unicode"),
        c
    ))

preprocessor = ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.0)

# Read original df with target for saving
df_full = pd.read_csv(dataset_path)
df_full = df_full.drop(columns=[c for c in drop_existing if c != target_col], errors="ignore")
y = df_full[target_col]

# Label-encode non-numeric targets so ALL downstream models train on integer
# classes — XGBoost rejects string labels outright. Class names are preserved
# so inference can decode integer predictions back to the original labels.
target_classes = []
if task_type != "regression" and not pd.api.types.is_numeric_dtype(y):
    le_target = LabelEncoder()
    y = pd.Series(le_target.fit_transform(y.astype(str)))
    target_classes = [str(c) for c in le_target.classes_]

# Fit preprocessor
X_transformed = preprocessor.fit_transform(df)

# Save preprocessor
os.makedirs(artifacts_dir, exist_ok=True)
preprocessor_path = os.path.join(artifacts_dir, "preprocessor.pkl")
joblib.dump(preprocessor, preprocessor_path)

# Save processed dataset for next agents
feature_names = preprocessor.get_feature_names_out().tolist() if hasattr(preprocessor, "get_feature_names_out") else [f"f_{{i}}" for i in range(X_transformed.shape[1])]
df_processed = pd.DataFrame(X_transformed, columns=feature_names)
df_processed["__target__"] = y.values
processed_path = os.path.join(artifacts_dir, "processed.csv")
df_processed.to_csv(processed_path, index=False)

RESULT = {{
    "preprocessor_path": preprocessor_path,
    "processed_path": processed_path,
    "n_features_out": X_transformed.shape[1],
    "n_samples": X_transformed.shape[0],
    "feature_names_sample": feature_names[:20],
    "dropped_columns": drop_existing,
    "datetime_cols_expanded": datetime_cols,
    "target_classes": target_classes,
}}
'''


class PreprocessorAgent(BaseAgent):
    name = "preprocessor"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Building sklearn preprocessing pipeline — decisions per column...")

        audit = state.get("data_audit", {})
        eda = state.get("eda_insights", {})
        issues = state.get("prioritized_issues", [])

        user_message = f"""
Task: {state['task_type']}
Target: {state['target_column']}
Primary metric: {state['primary_metric']}

Null percentages: {json.dumps(dict(sorted(audit.get('null_pct', {}).items(), key=lambda x: -x[1])[:15]))}
Numeric columns: {json.dumps(eda.get('num_cols', [])[:20])}
Categorical columns: {json.dumps(eda.get('cat_cols', [])[:20])}
High cardinality categoricals: {json.dumps(eda.get('high_cardinality_cols', {}))}
Skewed columns: {json.dumps({k:v for k,v in eda.get('skewness', {}).items() if abs(v) > 1})}
Outlier pct (top): {json.dumps(dict(sorted(eda.get('outlier_pct', {}).items(), key=lambda x:-x[1])[:8]))}
Class imbalance: {json.dumps(eda.get('class_imbalance'))}
Datetime columns: {json.dumps(eda.get('datetime_cols', []))}
Free-text columns (use text_tfidf for these): {json.dumps(eda.get('text_cols', []))}

Prioritized issues from EDA:
{chr(10).join(f'- {i}' for i in issues[:8])}

Design the preprocessing pipeline. For each column specify the strategy and reasoning.
Use RobustScaler if significant outliers detected. Use median imputation for skewed numerics.
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)

        decisions = response.get("decisions", [])
        drop_columns = response.get("drop_columns", [])
        imputation = response.get("imputation_strategy", {})
        encoding = response.get("encoding_strategy", {})
        scaling = response.get("scaling_strategy", "standard")
        handle_imbalance = response.get("handle_imbalance", False)

        # Infer default imputer for numeric cols
        skewed = {k: v for k, v in eda.get("skewness", {}).items() if abs(v) > 0.5}
        num_imputer_default = "median" if skewed else "mean"

        # Repairable decision params — the LLM may revise these on failure.
        # Fixed params (target, datetime cols, etc.) are closed over in render().
        def render(p: dict) -> str:
            return PREPROCESSING_CODE_TEMPLATE.format(
                target_column=state["target_column"],
                task_type=state["task_type"],
                drop_columns=repr(p["drop_columns"]),
                exclude_cols=repr(state.get("exclude_columns", [])),
                datetime_cols=repr(eda.get("datetime_cols", [])),
                imputation_strategy=repr(p["imputation"]),
                num_imputer_default=num_imputer_default,
                encoding_strategy=repr(p["encoding"]),
                scaling_strategy=p["scaling"],
            )

        repairable = {
            "drop_columns": drop_columns,
            "imputation": imputation,
            "encoding": encoding,
            "scaling": scaling,
        }
        result = await self.execute_code_with_repair(
            run_id, render, repairable,
            repair_goal=(
                "Build a sklearn ColumnTransformer. drop_columns=list of columns to drop; "
                "imputation={col: median|mean|most_frequent|constant|knn}; "
                "encoding={col: onehot|ordinal|frequency|text_tfidf}; "
                "scaling=standard|minmax|robust|none. Fix errors like unknown columns, "
                "wrong encoder for a column type, or text columns sent to onehot."
            ),
            timeout=180,
        )
        if not result["success"]:
            await self._mark_step(run_id, "failed", result["error"])
            return {"error": f"Preprocessing failed: {result['error']}", "status": "failed"}

        # Adopt any repaired params so downstream logging reflects what actually ran
        final_params = result.get("final_params", repairable)
        scaling = final_params.get("scaling", scaling)
        code = render(final_params)  # the exact code that ran (post-repair) — for the notebook cell
        data = result["result"]

        decision_log_entries = []
        for d in decisions:
            entry = await self._log_decision(
                run_id=run_id,
                decision=f"Column '{d.get('column')}': {d.get('strategy')}",
                reasoning=d.get("reasoning", ""),
                code_executed=f"sklearn strategy: {d.get('sklearn_step')}",
                result_summary=f"n_features_out={data['n_features_out']}",
            )
            decision_log_entries.append(entry)

        from app.core import mlflow_tracker as mlflow
        mlflow.log_params({
            "scaling_strategy": scaling,
            "n_features_after_preprocessing": data["n_features_out"],
            "handle_imbalance": handle_imbalance,
        })

        await self.emit(
            run_id,
            f"Preprocessing complete: {data['n_samples']} samples × {data['n_features_out']} features",
            {"n_features": data["n_features_out"], "dropped_columns": data["dropped_columns"]},
        )
        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        new_cell = {
            "agent": self.name,
            "title": "Data Preprocessing Pipeline",
            "iteration": 0,
            "code": code,
            "stdout": result.get("stdout", ""),
            "result_summary": {
                "n_samples": data["n_samples"],
                "n_features_out": data["n_features_out"],
                "feature_names_sample": data.get("feature_names_sample", [])[:15],
                "dropped_columns": data["dropped_columns"],
                "datetime_cols_expanded": data.get("datetime_cols_expanded", []),
                "scaling_strategy": scaling,
                "handle_imbalance": handle_imbalance,
                "per_column_decisions": [
                    {"column": d.get("column"), "strategy": d.get("strategy"),
                     "reasoning": d.get("reasoning", "")[:100]}
                    for d in decisions[:10]
                ],
            },
        }
        return {
            "preprocessor_path": data["preprocessor_path"],
            "preprocessing_decisions": decisions,
            "processed_data_path": data["processed_path"],
            "target_classes": data.get("target_classes", []),
            "decision_log": existing_log + decision_log_entries,
            "notebook_cells": existing_cells + [new_cell],
        }
