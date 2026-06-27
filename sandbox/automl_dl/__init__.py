"""automl_dl — sklearn-compatible PyTorch estimators baked into the SANDBOX image.

Deep-learning models plug into the existing pipeline as ordinary registry entries
(class strings like "TorchMLPClassifier"): the model_selector instantiates them, CV
/ the tuner / the evaluator treat them like any sklearn estimator, and because
inference also runs in this sandbox image, the standard joblib pipeline serializes
and reloads them with no special handling.
"""

from automl_dl.estimators import TorchMLPClassifier, TorchMLPRegressor

__all__ = ["TorchMLPClassifier", "TorchMLPRegressor"]
