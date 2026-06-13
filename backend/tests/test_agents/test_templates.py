"""
Render every sandbox code template with dummy values and compile the result.

Catches the recurring bug class: a literal `{...}` added to a .format() template
without doubled braces raises KeyError at runtime (e.g. the text_cols dict that
broke the Boston housing run). Also catches syntax errors in rendered code.
"""

import pytest

from app.agents.baseline_builder import BASELINE_CODE_TEMPLATE
from app.agents.eda_agent import EDA_CODE_TEMPLATE
from app.agents.evaluator import EVALUATION_CODE_TEMPLATE
from app.agents.feature_engineer import FEATURE_CODE_TEMPLATE
from app.agents.model_selector import TRAINING_CODE_TEMPLATE
from app.agents.preprocessor import PREPROCESSING_CODE_TEMPLATE
from app.agents.tuner import TUNING_CODE_TEMPLATE

TEMPLATE_CASES = [
    (
        "eda",
        EDA_CODE_TEMPLATE,
        {"target_column": "t", "task_type": "regression"},
    ),
    (
        "baseline",
        BASELINE_CODE_TEMPLATE,
        {"target_column": "t", "task_type": "binary_classification",
         "exclude_cols": "[]", "scoring": "roc_auc"},
    ),
    (
        "preprocessing",
        PREPROCESSING_CODE_TEMPLATE,
        {"target_column": "t", "task_type": "multiclass_classification",
         "drop_columns": "[]", "exclude_cols": "[]", "datetime_cols": "[]",
         "imputation_strategy": "{}", "num_imputer_default": "median",
         "encoding_strategy": "{}", "scaling_strategy": "standard"},
    ),
    (
        "feature_engineering",
        FEATURE_CODE_TEMPLATE,
        {"processed_path": "/x.csv", "target_column": "t",
         "task_type": "regression", "proposed_features": "[]"},
    ),
    (
        "model_training",
        TRAINING_CODE_TEMPLATE,
        {"enriched_path": "/x.csv", "task_type": "binary_classification",
         "primary_metric": "recall", "class_imbalance": "True",
         "models_config": "[]"},
    ),
    (
        "tuning",
        TUNING_CODE_TEMPLATE,
        {"enriched_path": "/x.csv", "task_type": "regression",
         "primary_metric": "rmse", "winner_class": "Ridge",
         "winner_path": "/w.pkl", "n_trials": 5},
    ),
    (
        "evaluation",
        EVALUATION_CODE_TEMPLATE,
        {"enriched_path": "/x.csv", "tuned_path": "/t.pkl",
         "task_type": "regression", "primary_metric": "rmse",
         "fp_fn_preference": ""},
    ),
]


@pytest.mark.parametrize("name,template,kwargs", TEMPLATE_CASES, ids=[c[0] for c in TEMPLATE_CASES])
def test_template_renders_and_compiles(name, template, kwargs):
    # .format() raises KeyError/IndexError on any unescaped literal brace
    code = template.format(**kwargs)
    # compile() catches syntax errors in the rendered sandbox code
    compile(code, f"<{name}_template>", "exec")
