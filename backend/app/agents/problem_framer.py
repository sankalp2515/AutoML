import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core import metric_registry
from app.core import mlflow_tracker as mlflow
from app.core.state import AgentState

# The metric vocabulary + per-task menu are DERIVED from metric_registry (the
# single source of truth) — never hand-typed here. Adding a metric = one registry
# line, no prompt edit. The selection heuristics below are LLM *guidance*, not a
# hardcoded choice: the LLM still decides the metric from the user's goal.
_METRIC_ENUM = " | ".join(f'"{m}"' for m in metric_registry.all_metrics())

SYSTEM_PROMPT = f"""You are an expert ML problem framing specialist.
Given a user's business goal and dataset information, you determine the precise ML task definition.

You MUST respond with a valid JSON object containing exactly these fields:
{{
  "task_type": "binary_classification" | "multiclass_classification" | "multilabel_classification" | "regression",
  "target_column": "<best guess at target column name from the columns list>",
  "primary_metric": {_METRIC_ENUM},
  "good_enough_threshold": <float between 0 and 1>,
  "reasoning": "<your chain of thought>",
  "decisions": [
    {{"decision": "<what you decided>", "reasoning": "<why>"}}
  ],
  "label_columns": ["<list of binary target columns if multilabel>"],
  "label_delimiter": "<delimiter if target is a delimited string, e.g. ';' or ','>"
}}

Allowed metrics by task — choose ONE that fits the task you assign:
{metric_registry.framer_menu_text()}

Selecting the metric from the goal (guidance, not rules — reason from the goal):
- fraud/churn/disease/default → recall (missing a positive is costly)
- spam filtering → precision
- price/sales/demand → rmse or mae
- SEVERE class imbalance (minority < 5%) → pr_auc — ROC-AUC misleads when extremely imbalanced
- multiclass: pick from its allowed list above; binary-only metrics' weighted variants are auto-applied

Multilabel detection:
- If target column contains delimited strings (e.g. "tag1;tag2;tag3") → multilabel_classification with label_delimiter
- If multiple binary columns represent labels (e.g. "label_a", "label_b", "label_c" all 0/1) → multilabel_classification with label_columns list
"""


class ProblemFramerAgent(BaseAgent):
    name = "problem_framer"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Analyzing your business goal and framing the ML problem...")

        audit = state.get("data_audit", {})
        columns = list(audit.get("dtypes", {}).keys()) if audit else []
        imbalance_severity = state.get("imbalance_severity", "none")

        user_message = f"""
Business goal: {state['user_goal']}

Dataset columns available: {json.dumps(columns)}
Exclude columns (user specified): {json.dumps(state.get('exclude_columns', []))}
FP/FN preference: {state.get('fp_fn_preference', 'not specified')}
Interpretability required: {state.get('interpretability_required', False)}
Class imbalance severity: {imbalance_severity}  # "none" | "moderate" | "severe" (minority < 5%)

Determine the ML task type, target column, and primary metric.
Also detect if this is a multilabel problem:
- Target column contains delimited strings (e.g. "tag1;tag2;tag3") → multilabel_classification with label_delimiter
- Multiple binary columns represent labels (e.g. "label_a", "label_b", "label_c" all 0/1) → multilabel_classification with label_columns list
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)

        # Guardrail: clamp the framing to valid values before it flows downstream
        # (a bad metric/task would crash or silently NaN a scorer later).
        from app.core.guardrails import validate_and_fix_framing
        response, gnotes = validate_and_fix_framing(response, columns)
        for note in gnotes:
            self._log.warning("framing_guardrail", run_id=run_id, fix=note)
            await self._log_decision(
                run_id=run_id, decision=f"Guardrail corrected framing: {note}",
                reasoning="Validated the LLM's problem framing against the metric/task registry.",
            )

        task_type = response.get("task_type", "binary_classification")
        target_column = response.get("target_column", "")
        primary_metric = response.get("primary_metric", "auc_roc")
        good_enough = response.get("good_enough_threshold", 0.80)
        label_columns = response.get("label_columns", [])
        label_delimiter = response.get("label_delimiter", "")

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
            label_columns=label_columns,
            label_delimiter=label_delimiter,
        )

        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        return {
            "task_type": task_type,
            "target_column": target_column,
            "primary_metric": primary_metric,
            "good_enough_threshold": float(good_enough),
            "label_columns": label_columns,
            "label_delimiter": label_delimiter,
            "decision_log": existing_log + decision_log_entries,
        }
