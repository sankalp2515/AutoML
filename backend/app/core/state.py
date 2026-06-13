from typing import Any, TypedDict


class DecisionLogEntry(TypedDict):
    agent: str
    timestamp: str
    decision: str
    reasoning: str
    code_executed: str
    result_summary: str


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str
    mlflow_run_id: str

    # User inputs
    dataset_path: str
    user_goal: str
    exclude_columns: list[str]
    fp_fn_preference: str
    interpretability_required: bool
    data_dir: str

    # Problem Framer outputs
    task_type: str                  # binary_classification | multiclass | regression
    target_column: str
    primary_metric: str
    good_enough_threshold: float
    inference_features: list[str]

    # Data Auditor outputs
    data_audit: dict[str, Any]
    audit_verdict: str

    # Baseline Builder outputs
    baseline_score: float
    baseline_model: str
    baseline_errors: dict[str, Any]

    # EDA + Error Agent outputs
    eda_insights: dict[str, Any]
    prioritized_issues: list[str]

    # Preprocessing Agent outputs
    preprocessing_decisions: list[dict[str, Any]]
    preprocessor_path: str
    processed_data_path: str        # path to processed.csv for downstream agents
    target_classes: list[str]       # original class labels when target was label-encoded

    # Feature Engineer outputs
    features_created: list[dict[str, Any]]
    features_dropped: list[dict[str, Any]]
    enriched_data_path: str         # path to enriched.csv (with new features)

    # Model Selector + Tuner outputs
    models_evaluated: dict[str, Any]
    winner_model: str
    winner_model_path: str          # path to winner_model.pkl
    winner_model_class: str         # e.g. "xgb.XGBClassifier"
    best_hyperparams: dict[str, Any]
    tuned_model_path: str           # path to tuned_model.pkl
    tuned_score: float

    # Evaluator outputs
    evaluation_report: dict[str, Any]
    slice_performance: dict[str, Any]
    recommended_threshold: float
    shap_top_features: list[str]

    # Iteration control
    iteration: int
    max_iterations: int
    iteration_scores: list[float]
    prev_score: float
    current_score: float

    # Export outputs
    artifact_paths: dict[str, str]

    # Full audit trail
    decision_log: list[DecisionLogEntry]

    # Evidence notebook cells: each agent appends one entry with its actual
    # executed code + result summary so the exporter can build the notebook
    # via LLM-driven narrative (no hardcoded structure).
    # Schema per entry:
    #   agent: str          — agent name (matches AGENT_ORDER)
    #   title: str          — human-readable section title
    #   iteration: int      — 0 for one-time agents; N for per-iteration agents
    #   code: str           — full executed sandbox code (what actually ran)
    #   stdout: str         — captured stdout from the sandbox
    #   result_summary: dict — key metrics / findings passed to the LLM
    notebook_cells: list[dict[str, Any]]

    # Runtime
    error: str | None
    status: str
