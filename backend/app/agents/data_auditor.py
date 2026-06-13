from typing import Any

from app.agents.base_agent import BaseAgent
from app.core import mlflow_tracker as mlflow
from app.core.state import AgentState

PROFILING_CODE = '''
import pandas as pd
import numpy as np
import json

df = pd.read_csv(dataset_path)

# Basic profile — never send raw rows to the agent
null_counts = df.isnull().sum().to_dict()
null_pct = (df.isnull().mean() * 100).round(2).to_dict()

describe_raw = df.describe(include='all').to_dict()
# Convert non-serialisable types
describe_clean = {}
for col, stats in describe_raw.items():
    describe_clean[col] = {k: (None if pd.isna(v) else (float(v) if hasattr(v, 'item') else v))
                           for k, v in stats.items()}

# Target distribution (filled after ProblemFramer sets target_column)
target_col = target_column  # injected into globals by orchestrator
target_dist = {}
if target_col and target_col in df.columns:
    vc = df[target_col].value_counts(normalize=True).round(4)
    target_dist = vc.to_dict()

# Cardinality
cardinality = df.nunique().to_dict()

# Sample rows (5 only)
sample = df.sample(min(5, len(df)), random_state=42).to_dict(orient='records')

RESULT = {
    "shape": list(df.shape),
    "dtypes": df.dtypes.astype(str).to_dict(),
    "null_counts": null_counts,
    "null_pct": null_pct,
    "describe": describe_clean,
    "cardinality": cardinality,
    "target_distribution": target_dist,
    "sample_rows": sample,
    "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
}
'''

SYSTEM_PROMPT = """You are a data quality auditor for ML pipelines.
Given a dataset profile (statistics, NOT raw data), assess data quality and decide if the pipeline can proceed.

You MUST respond with valid JSON:
{
  "verdict": "usable" | "warn" | "abort",
  "warnings": ["<list of issues found>"],
  "decisions": [{"decision": "...", "reasoning": "..."}]
}

verdict rules:
- "usable": data looks clean enough, proceed
- "warn": issues found but pipeline can continue (warn user)
- "abort": data is fundamentally broken (e.g. <50 rows, target column missing, >80% nulls in target)
"""


class DataAuditorAgent(BaseAgent):
    name = "data_auditor"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Running data quality audit (30-second sanity check)...")

        # Inject target_column as a literal assignment at the top of the code
        # (sandbox globals already have target_column="", this overrides it)
        target_col_value = state.get("target_column") or ""
        code = f'target_column = "{target_col_value}"\n' + PROFILING_CODE

        sandbox_result = await self.execute_code(code, run_id, timeout=60)
        if not sandbox_result["success"]:
            await self._mark_step(run_id, "failed", sandbox_result["error"])
            return {"error": f"Data profiling failed: {sandbox_result['error']}", "status": "failed"}

        profile = sandbox_result["result"]

        import json
        user_message = f"""
Dataset profile:
- Shape: {profile['shape']}
- Memory: {profile['memory_mb']} MB
- Target column: {state.get('target_column')}
- Target distribution: {json.dumps(profile.get('target_distribution', {}))}
- Null percentages (top 10 worst): {json.dumps(dict(sorted(profile['null_pct'].items(), key=lambda x: -x[1])[:10]))}
- Cardinality (top 10): {json.dumps(dict(sorted(profile['cardinality'].items(), key=lambda x: -x[1])[:10]))}
- Sample rows: {json.dumps(profile.get('sample_rows', [])[:3])}

Task type: {state.get('task_type')}
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)

        verdict = response.get("verdict", "warn")
        warnings = response.get("warnings", [])

        decision_log_entries = []
        for d in response.get("decisions", []):
            entry = await self._log_decision(
                run_id=run_id,
                decision=d["decision"],
                reasoning=d["reasoning"],
                code_executed=PROFILING_CODE[:200],
                result_summary=f"Shape: {profile['shape']}, Verdict: {verdict}",
            )
            decision_log_entries.append(entry)

        mlflow.log_params({"data_shape_rows": profile["shape"][0], "data_shape_cols": profile["shape"][1]})
        mlflow.set_tag("audit_verdict", verdict)

        await self.emit(
            run_id,
            f"Audit complete. Verdict: {verdict}. Warnings: {len(warnings)}",
            {"verdict": verdict, "warnings": warnings},
        )

        if verdict == "abort":
            await self._mark_step(run_id, "failed", "; ".join(warnings))
            return {"error": "; ".join(warnings), "status": "failed", "audit_verdict": "abort"}

        await self._mark_step(run_id, "completed")
        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        new_cell = {
            "agent": self.name,
            "title": "Data Quality Audit",
            "iteration": 0,
            "code": code,
            "stdout": sandbox_result.get("stdout", ""),
            "result_summary": {
                "shape": profile["shape"],
                "memory_mb": profile["memory_mb"],
                "verdict": verdict,
                "warnings": warnings[:5],
                "null_pct_top5": dict(
                    sorted(profile["null_pct"].items(), key=lambda x: -x[1])[:5]
                ),
                "target_distribution": profile.get("target_distribution", {}),
                "cardinality_top5": dict(
                    sorted(profile["cardinality"].items(), key=lambda x: -x[1])[:5]
                ),
                "dtypes_summary": dict(list(profile["dtypes"].items())[:10]),
            },
        }
        return {
            "data_audit": profile,
            "audit_verdict": verdict,
            "decision_log": existing_log + decision_log_entries,
            "notebook_cells": existing_cells + [new_cell],
        }
