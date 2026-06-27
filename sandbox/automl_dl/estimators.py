"""sklearn-compatible PyTorch MLP estimators (DL-0 foundation).

A configurable feed-forward network wrapped as a scikit-learn estimator
(fit/predict/predict_proba, get_params/set_params via BaseEstimator). It runs on
GPU when available (with mixed precision), uses an internal validation split for
early stopping, and is picklable — so it drops into cross-validation, the Optuna
tuner, and the joblib inference pipeline exactly like XGBoost or RandomForest.

Hyperparameters (all tunable from the model registry's search space):
  hidden_dims, dropout, lr, weight_decay, batch_size, max_epochs, patience.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin


def _device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


class _MLP(nn.Module):
    """Defined at module level so estimators pickle cleanly (joblib at inference)."""

    def __init__(self, in_dim: int, out_dim: int, hidden_dims, dropout: float):
        super().__init__()
        layers, d = [], in_dim
        for h in hidden_dims:
            layers += [nn.Linear(d, h), nn.ReLU(), nn.Dropout(dropout)]
            d = h
        layers.append(nn.Linear(d, out_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class _BaseTorchMLP(BaseEstimator):
    def __init__(self, hidden_dims=(128, 64), dropout=0.1, lr=1e-3, weight_decay=1e-5,
                 batch_size=256, max_epochs=100, patience=10, random_state=42):
        self.hidden_dims = hidden_dims
        self.dropout = dropout
        self.lr = lr
        self.weight_decay = weight_decay
        self.batch_size = batch_size
        self.max_epochs = max_epochs
        self.patience = patience
        self.random_state = random_state

    # ── shared training loop ──────────────────────────────────────────────────
    def _fit_torch(self, X, y, out_dim, loss_fn, y_dtype):
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)
        dev = _device()
        X = np.asarray(X, dtype=np.float32)
        # Standardize inputs internally — MLPs are scale-sensitive, and this makes
        # the estimator robust whether or not upstream scaling was applied.
        self._x_mean = X.mean(axis=0)
        self._x_std = X.std(axis=0)
        self._x_std[self._x_std < 1e-8] = 1.0
        X = (X - self._x_mean) / self._x_std
        n = len(X)
        # internal validation split for early stopping (last 15%, time-safe-ish)
        n_val = max(1, int(n * 0.15))
        tr = slice(0, n - n_val)
        va = slice(n - n_val, n)

        model = _MLP(X.shape[1], out_dim, list(self.hidden_dims), self.dropout).to(dev)
        opt = torch.optim.Adam(model.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        use_amp = dev == "cuda"
        scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

        Xt = torch.tensor(X, device=dev)
        yt = torch.tensor(np.asarray(y), device=dev).to(y_dtype)
        idx = np.arange(tr.stop)

        best_val, best_state, bad = float("inf"), None, 0
        for _epoch in range(self.max_epochs):
            model.train()
            np.random.shuffle(idx)
            for i in range(0, len(idx), self.batch_size):
                b = idx[i:i + self.batch_size]
                opt.zero_grad()
                with torch.autocast(device_type="cuda" if use_amp else "cpu", enabled=use_amp):
                    out = model(Xt[b])
                    loss = loss_fn(out, yt[b])
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()
            # validation
            model.eval()
            with torch.no_grad():
                vloss = float(loss_fn(model(Xt[va.start:va.stop]), yt[va.start:va.stop]).item())
            if vloss < best_val - 1e-5:
                best_val, best_state, bad = vloss, {k: v.detach().cpu().clone()
                                                    for k, v in model.state_dict().items()}, 0
            else:
                bad += 1
                if bad >= self.patience:
                    break
        if best_state is not None:
            model.load_state_dict(best_state)
        model.eval()
        self.module_ = model.cpu()   # store on CPU so the pickle is portable
        self.n_features_in_ = X.shape[1]
        return self

    def _forward_np(self, X) -> np.ndarray:
        X = (np.asarray(X, dtype=np.float32) - self._x_mean) / self._x_std
        self.module_.eval()
        with torch.no_grad():
            out = self.module_(torch.tensor(X))
        return out.numpy()


class TorchMLPClassifier(_BaseTorchMLP, ClassifierMixin):
    def fit(self, X, y):
        y = np.asarray(y)
        self.classes_ = np.unique(y)
        self._y_index = {c: i for i, c in enumerate(self.classes_)}
        y_idx = np.array([self._y_index[v] for v in y])
        return self._fit_torch(X, y_idx, out_dim=len(self.classes_),
                               loss_fn=nn.CrossEntropyLoss(), y_dtype=torch.long)

    def predict_proba(self, X):
        logits = self._forward_np(X)
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        return e / e.sum(axis=1, keepdims=True)

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(axis=1)]


class TorchMLPRegressor(_BaseTorchMLP, RegressorMixin):
    def fit(self, X, y):
        y = np.asarray(y, dtype=np.float32)
        # Standardize the target — MLP+MSE trains poorly on arbitrary target scales.
        self._y_mean = float(y.mean())
        self._y_std = float(y.std()) or 1.0
        ys = ((y - self._y_mean) / self._y_std).reshape(-1, 1)
        return self._fit_torch(X, ys, out_dim=1, loss_fn=nn.MSELoss(), y_dtype=torch.float32)

    def predict(self, X):
        return self._forward_np(X).ravel() * self._y_std + self._y_mean
