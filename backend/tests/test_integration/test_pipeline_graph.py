"""CI integration harness — drive the REAL compiled LangGraph end-to-end.

This is the integration coverage the audit flagged as missing: it exercises the
actual graph wiring — node order, the data_splitter placement, fail-fast routers,
the diagnostic back-jump, and the significance-gated iteration loop — WITHOUT
needing the LLM, the sandbox, or a database. Each agent's run() is replaced by a
deterministic stub that returns the state delta the real agent would; the graph,
edges, and routing functions under test are the real ones.

Catches the regression class that previously needed a full live run to surface
(zombie pipeline on unconditional edges, broken routing, wrong agent order).
"""

import pytest

from app.agents import orchestrator


class _FakeAgent:
    """Stands in for a real agent: records that it ran, returns a fixed delta."""
    def __init__(self, name, order_log, delta=None):
        self.name = name
        self._order = order_log
        self._delta = delta or {}

    async def run(self, state):
        self._order.append(self.name)
        return dict(self._delta)


def _install(monkeypatch, order, overrides=None):
    """Patch every orchestrator agent singleton with a stub. `overrides` maps an
    agent attr → delta dict to simulate failures / scores."""
    overrides = overrides or {}
    # attr name on the orchestrator module → agent name
    agents = {
        "_data_auditor": ("data_auditor", {"audit_verdict": "usable"}),
        "_problem_framer": ("problem_framer", {"task_type": "binary_classification",
                                               "target_column": "y", "primary_metric": "auc_roc"}),
        "_data_splitter": ("data_splitter", {"holdout_path": "/d/holdout.csv",
                                             "dataset_path": "/d/train.csv"}),
        "_baseline_builder": ("baseline_builder", {"baseline_score": 0.70}),
        "_eda_agent": ("eda_agent", {}),
        "_preprocessor": ("preprocessor", {}),
        "_feature_engineer": ("feature_engineer", {}),
        "_model_selector": ("model_selector", {"winner_model": "RandomForest"}),
        "_tuner": ("tuner", {"tuned_score": 0.82}),
        "_evaluator": ("evaluator", {"current_score": 0.80, "score_std": 0.9,
                                     "evaluation_basis": "holdout"}),
        "_exporter": ("exporter", {"artifact_paths": {"inference_pipeline": "/d/p.pkl"}}),
    }
    for attr, (name, delta) in agents.items():
        if attr in overrides:
            delta = overrides[attr]
        monkeypatch.setattr(orchestrator, attr, _FakeAgent(name, order, delta))


def _initial_state(run_id="itest"):
    return {
        "run_id": run_id, "pipeline": "tabular", "status": "running",
        "iteration": 0, "max_iterations": 3, "iteration_scores": [],
        "decision_log": [], "notebook_cells": [], "dataset_path": "/d/raw.csv",
        "user_goal": "predict y", "data_dir": "/d",
    }


@pytest.mark.asyncio
async def test_happy_path_runs_all_agents_in_order(monkeypatch):
    order = []
    _install(monkeypatch, order)
    # Force a freshly-built graph so it closes over the patched globals.
    orchestrator._compiled_graph = None
    graph = orchestrator.get_graph()

    final = await graph.ainvoke(_initial_state())

    # data_splitter MUST sit between framing and the baseline (train-only downstream).
    assert order.index("problem_framer") < order.index("data_splitter") < order.index("baseline_builder")
    # Reached the end with a result; no failure.
    assert "exporter" in order
    assert final.get("status") != "failed"
    assert final.get("current_score") == 0.80
    assert final.get("evaluation_basis") == "holdout"
    assert final.get("holdout_path") == "/d/holdout.csv"


@pytest.mark.asyncio
async def test_fail_fast_stops_the_pipeline(monkeypatch):
    order = []
    # EDA fails → the graph must route straight to END, NOT cascade downstream.
    _install(monkeypatch, order, overrides={"_eda_agent": {"status": "failed", "error": "boom"}})
    orchestrator._compiled_graph = None
    graph = orchestrator.get_graph()

    await graph.ainvoke(_initial_state())

    assert "eda_agent" in order
    for downstream in ("preprocessor", "feature_engineer", "model_selector", "tuner", "evaluator", "exporter"):
        assert downstream not in order, f"{downstream} ran after a fail-fast — zombie pipeline!"


@pytest.mark.asyncio
async def test_significance_gate_stops_iteration(monkeypatch):
    order = []
    # Evaluator reports a gain (0.80) smaller than the noise floor (score_std 0.9)
    # → must NOT loop back to feature_engineer; goes straight to exporter.
    _install(monkeypatch, order)
    orchestrator._compiled_graph = None
    graph = orchestrator.get_graph()

    await graph.ainvoke(_initial_state())

    assert order.count("evaluator") == 1          # evaluated once
    assert order.count("feature_engineer") == 1   # the first pass only — no extra iteration
    assert "exporter" in order


@pytest.mark.asyncio
async def test_iteration_loops_then_caps(monkeypatch):
    order = []
    # Real improvement above the noise floor → it should iterate, but the
    # max_iterations cap must terminate the loop (no infinite cycle).
    _install(monkeypatch, order, overrides={
        "_evaluator": {"current_score": 0.95, "score_std": 0.0, "evaluation_basis": "holdout"},
    })
    orchestrator._compiled_graph = None
    graph = orchestrator.get_graph()

    final = await graph.ainvoke(_initial_state())

    assert order.count("feature_engineer") > 1          # it iterated
    assert final.get("iteration", 0) <= final.get("max_iterations", 3) + 1  # but capped
    assert "exporter" in order                           # and terminated cleanly


@pytest.fixture(autouse=True)
def _reset_graph_cache():
    yield
    orchestrator._compiled_graph = None  # don't leak the stubbed graph to other tests
