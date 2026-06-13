from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.agents.baseline_builder import BaselineBuilderAgent
from app.agents.data_auditor import DataAuditorAgent
from app.agents.eda_agent import EDAAgent
from app.agents.evaluator import EvaluatorAgent
from app.agents.exporter import ExporterAgent
from app.agents.feature_engineer import FeatureEngineerAgent
from app.agents.model_selector import ModelSelectorAgent
from app.agents.preprocessor import PreprocessorAgent
from app.agents.problem_framer import ProblemFramerAgent
from app.agents.tuner import TunerAgent
from app.config import settings
from app.core import metrics
from app.core import mlflow_tracker as mlflow
from app.core.logging import get_logger
from app.core.state import AgentState

_log = get_logger("orchestrator")
from app.database import AsyncSessionLocal
from app.models.run import Run
from app.redis_client import publish_progress, set_run_state


# ── Agent singletons ──────────────────────────────────────────────────────────
_problem_framer = ProblemFramerAgent()
_data_auditor = DataAuditorAgent()
_baseline_builder = BaselineBuilderAgent()
_eda_agent = EDAAgent()
_preprocessor = PreprocessorAgent()
_feature_engineer = FeatureEngineerAgent()
_model_selector = ModelSelectorAgent()
_tuner = TunerAgent()
_evaluator = EvaluatorAgent()
_exporter = ExporterAgent()


# ── Node wrappers (LangGraph expects sync OR async callables) ─────────────────
async def node_data_auditor(state: AgentState) -> dict:
    return await _data_auditor.run(state)


async def node_problem_framer(state: AgentState) -> dict:
    return await _problem_framer.run(state)


async def node_baseline(state: AgentState) -> dict:
    return await _baseline_builder.run(state)


async def node_eda(state: AgentState) -> dict:
    return await _eda_agent.run(state)


async def node_preprocessor(state: AgentState) -> dict:
    return await _preprocessor.run(state)


async def node_feature_engineer(state: AgentState) -> dict:
    return await _feature_engineer.run(state)


async def node_model_selector(state: AgentState) -> dict:
    return await _model_selector.run(state)


async def node_tuner(state: AgentState) -> dict:
    return await _tuner.run(state)


async def node_evaluator(state: AgentState) -> dict:
    result = await _evaluator.run(state)
    # Increment iteration counter
    result["iteration"] = state.get("iteration", 0) + 1
    return result


async def node_exporter(state: AgentState) -> dict:
    return await _exporter.run(state)


# ── Routing logic ─────────────────────────────────────────────────────────────
def route_after_audit(state: AgentState) -> Literal["problem_framer", END]:
    if state.get("status") == "failed" or state.get("audit_verdict") == "abort":
        return END
    return "problem_framer"


def route_after_baseline(state: AgentState) -> Literal["eda", END]:
    if state.get("status") == "failed":
        return END
    return "eda"


def route_after_evaluator(state: AgentState) -> Literal["feature_engineer", "exporter"]:
    if state.get("status") == "failed":
        return "exporter"

    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", settings.MAX_ITERATIONS)
    current = state.get("current_score", 0.0)
    prev = state.get("prev_score", 0.0)
    improvement = abs(current - prev)

    should_iterate = (
        iteration < max_iter
        and improvement >= settings.IMPROVEMENT_THRESHOLD
    )
    return "feature_engineer" if should_iterate else "exporter"


def _make_failfast_router(next_node: str):
    """Stop the pipeline immediately when an agent reports failure.

    Without this, a failed agent's state flows into the next agent and the
    pipeline runs as a zombie until something crashes on missing data.
    """
    def router(state: AgentState) -> str:
        if state.get("status") == "failed":
            return END
        return next_node
    return router


# ── Build the graph ───────────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("data_auditor", node_data_auditor)
    graph.add_node("problem_framer", node_problem_framer)
    graph.add_node("baseline_builder", node_baseline)
    graph.add_node("eda_agent", node_eda)
    graph.add_node("preprocessor", node_preprocessor)
    graph.add_node("feature_engineer", node_feature_engineer)
    graph.add_node("model_selector", node_model_selector)
    graph.add_node("tuner", node_tuner)
    graph.add_node("evaluator", node_evaluator)
    graph.add_node("exporter", node_exporter)

    graph.set_entry_point("data_auditor")

    graph.add_conditional_edges(
        "data_auditor",
        route_after_audit,
        {"problem_framer": "problem_framer", END: END},
    )
    graph.add_edge("problem_framer", "baseline_builder")
    graph.add_conditional_edges(
        "baseline_builder",
        route_after_baseline,
        {"eda": "eda_agent", END: END},
    )
    # Fail-fast conditional edges: a failed agent ends the run cleanly
    # instead of cascading bad state into downstream agents.
    graph.add_conditional_edges(
        "eda_agent", _make_failfast_router("preprocessor"),
        {"preprocessor": "preprocessor", END: END},
    )
    graph.add_conditional_edges(
        "preprocessor", _make_failfast_router("feature_engineer"),
        {"feature_engineer": "feature_engineer", END: END},
    )
    graph.add_conditional_edges(
        "feature_engineer", _make_failfast_router("model_selector"),
        {"model_selector": "model_selector", END: END},
    )
    graph.add_conditional_edges(
        "model_selector", _make_failfast_router("tuner"),
        {"tuner": "tuner", END: END},
    )
    graph.add_conditional_edges(
        "tuner", _make_failfast_router("evaluator"),
        {"evaluator": "evaluator", END: END},
    )
    graph.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {"feature_engineer": "feature_engineer", "exporter": "exporter"},
    )
    graph.add_edge("exporter", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


# ── Entry point called by the API ─────────────────────────────────────────────
async def run_pipeline(run_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            return

        run.status = "running"
        await db.commit()

    mlflow.setup_mlflow()
    mlflow_run_id = mlflow.start_run(
        run_id=run_id,
        tags={"status": "running"},
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if run:
            run.mlflow_run_id = mlflow_run_id
            await db.commit()

    initial_state: AgentState = {
        "run_id": run_id,
        "mlflow_run_id": mlflow_run_id,
        "dataset_path": run.dataset_path,
        "user_goal": run.user_goal,
        "exclude_columns": run.exclude_columns or [],
        "fp_fn_preference": run.fp_fn_preference or "",
        "interpretability_required": run.interpretability_required,
        "decision_log": [],
        "notebook_cells": [],      # each agent appends its executed code + results
        "iteration": 0,
        "max_iterations": settings.MAX_ITERATIONS,
        "iteration_scores": [],
        "status": "running",
        "data_dir": settings.DATA_DIR,
    }

    pipeline_start = datetime.now(timezone.utc)
    metrics.pipeline_runs_total.labels(status="started").inc()
    metrics.active_pipelines.inc()
    _log.info("pipeline_started", run_id=run_id)

    await publish_progress(run_id, {
        "agent": "orchestrator",
        "message": "Pipeline started",
        "timestamp": pipeline_start.isoformat(),
    })

    try:
        graph = get_graph()
        final_state: AgentState = await graph.ainvoke(initial_state)

        status = "completed" if final_state.get("status") != "failed" else "failed"
        elapsed = (datetime.now(timezone.utc) - pipeline_start).total_seconds()
        metrics.pipeline_runs_total.labels(status=status).inc()
        metrics.pipeline_duration_seconds.observe(elapsed)
        metrics.active_pipelines.dec()

        if final_state.get("baseline_score"):
            metrics.pipeline_baseline_score.observe(final_state["baseline_score"])
        if final_state.get("current_score"):
            metrics.pipeline_final_score.observe(final_state["current_score"])
        if final_state.get("baseline_score") and final_state.get("current_score"):
            improvement = final_state["current_score"] - final_state["baseline_score"]
            metrics.model_score_improvement.observe(improvement)
        if final_state.get("features_created") is not None:
            metrics.features_kept_total.observe(len(final_state.get("features_created", [])))

        _log.info("pipeline_finished", run_id=run_id, status=status, duration_s=round(elapsed, 1))

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                run.status = status
                run.task_type = final_state.get("task_type")
                run.target_column = final_state.get("target_column")
                run.primary_metric = final_state.get("primary_metric")
                run.baseline_score = final_state.get("baseline_score")
                run.final_score = final_state.get("current_score")
                run.winner_model = final_state.get("winner_model")
                run.iteration_count = final_state.get("iteration", 0)
                run.error_message = final_state.get("error")
                await db.commit()

        await set_run_state(run_id, dict(final_state))

        mlflow.log_metric("final_score", final_state.get("current_score") or 0)
        mlflow.set_tag("status", status)
        mlflow.set_tag("winner_model", final_state.get("winner_model") or "")
        mlflow.end_run("FINISHED" if status == "completed" else "FAILED")

        await publish_progress(run_id, {
            "agent": "orchestrator",
            "message": f"Pipeline {status}",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        error_msg = str(exc)
        metrics.pipeline_runs_total.labels(status="failed").inc()
        metrics.active_pipelines.dec()
        _log.error("pipeline_exception", run_id=run_id, error=error_msg)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                run.status = "failed"
                run.error_message = error_msg
                await db.commit()

            # Close out any step left "running" — an exception that escapes an
            # agent (e.g. LLM outage) never reaches its own _mark_step("failed").
            from app.models.run import AgentStep
            steps_q = await db.execute(
                select(AgentStep).where(
                    AgentStep.run_id == run_id, AgentStep.status == "running"
                )
            )
            for step in steps_q.scalars().all():
                step.status = "failed"
                step.completed_at = datetime.now(timezone.utc)
                step.error_message = error_msg[:500]
            await db.commit()

        mlflow.set_tag("status", "failed")
        mlflow.end_run("FAILED")

        await publish_progress(run_id, {
            "agent": "orchestrator",
            "message": f"Pipeline failed: {error_msg}",
            "status": "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raise
