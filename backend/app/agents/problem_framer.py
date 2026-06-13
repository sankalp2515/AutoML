import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core import mlflow_tracker as mlflow
from app.core.state import AgentState

SYSTEM_PROMPT = """You are an expert ML problem framing specialist.
Given a user's business goal and dataset information, you determine the precise ML task definition.

You MUST respond with a valid JSON object containing exactly these fields:
{
  "task_type": "binary_classification" | "multiclass_classification" | "regression",
  "target_column": "<best guess at target column name from the columns list>",
  "primary_metric": "recall" | "precision" | "f1" | "auc_roc" | "accuracy" | "rmse" | "mae" | "r2",
  "good_enough_threshold": <float between 0 and 1>,
  "reasoning": "<your chain of thought>",
  "decisions": [
    {"decision": "<what you decided>", "reasoning": "<why>"}
  ]
}

Rules for metric selection:
- If goal mentions fraud/churn/disease/default → prioritize recall (missing a positive is costly)
- If goal mentions spam filtering → prioritize precision
- If goal mentions price/sales/demand → use rmse or mae
- Default for BINARY classification: auc_roc
- For MULTICLASS classification: use f1 or accuracy — NEVER auc_roc/recall/precision
  (those are binary-only metrics; weighted variants are applied automatically)
- Default for regression: rmse
"""


class ProblemFramerAgent(BaseAgent):
    name = "problem_framer"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Analyzing your business goal and framing the ML problem...")

        audit = state.get("data_audit", {})
        columns = list(audit.get("dtypes", {}).keys()) if audit else []

        user_message = f"""
Business goal: {state['user_goal']}

Dataset columns available: {json.dumps(columns)}
Exclude columns (user specified): {json.dumps(state.get('exclude_columns', []))}
FP/FN preference: {state.get('fp_fn_preference', 'not specified')}
Interpretability required: {state.get('interpretability_required', False)}

Determine the ML task type, target column, and primary metric.
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)

        task_type = response.get("task_type", "binary_classification")
        target_column = response.get("target_column", "")
        primary_metric = response.get("primary_metric", "auc_roc")
        good_enough = response.get("good_enough_threshold", 0.80)

        decisions = response.get("decisions", [])
        decision_log_entries = []
        for d in decisions:
            entry = await self._log_decision(
                run_id=run_id,
                decision=d.get("decision", ""),
                reasoning=d.get("reasoning", ""),
            )
            decision_log_entries.append(entry)

        await self.emit(
            run_id,
            f"Task identified: {task_type} | Target: {target_column} | Metric: {primary_metric}",
            {"task_type": task_type, "target_column": target_column, "primary_metric": primary_metric},
        )

        mlflow.log_params({
            "task_type": task_type,
            "target_column": target_column,
            "primary_metric": primary_metric,
            "user_goal": state["user_goal"][:250],
        })

        # Persist framing immediately — if the pipeline fails later, the run
        # record still shows what problem was being solved.
        await self._update_run_field(
            run_id,
            task_type=task_type,
            target_column=target_column,
            primary_metric=primary_metric,
        )

        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        return {
            "task_type": task_type,
            "target_column": target_column,
            "primary_metric": primary_metric,
            "good_enough_threshold": float(good_enough),
            "decision_log": existing_log + decision_log_entries,
        }
