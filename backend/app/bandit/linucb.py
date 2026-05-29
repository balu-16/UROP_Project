import json
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.config import Settings
from app.retrieval.strategies import RetrievalOrchestrator


@dataclass
class ArmState:
    a: np.ndarray
    b: np.ndarray


class LinUCB:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.resolved_storage_dir / "linucb_policy.json"
        self.arms = RetrievalOrchestrator.arms
        self.dimension = settings.bandit_feature_dim
        self.alpha = settings.linucb_alpha
        self.states: dict[str, ArmState] = {}
        self.history: list[dict[str, Any]] = []
        self._dirty = False
        self._last_save = 0.0
        self._save_interval = 30.0  # save at most once per 30 seconds

    def startup(self) -> None:
        if self.path.exists():
            payload = json.loads(self.path.read_text())
            self.history = payload.get("history", [])
            self.states = {
                arm: ArmState(
                    a=np.array(state["a"], dtype="float64"),
                    b=np.array(state["b"], dtype="float64"),
                )
                for arm, state in payload.get("states", {}).items()
            }
        for arm in self.arms:
            self.states.setdefault(
                arm,
                ArmState(
                    a=np.eye(self.dimension, dtype="float64"),
                    b=np.zeros(self.dimension, dtype="float64"),
                ),
            )
        # Apply initial regularization to all arm matrices
        for state in self.states.values():
            state.a += 1e-6 * np.eye(self.dimension, dtype="float64")

    def save(self) -> None:
        payload = {
            "history": self.history[-1000:],
            "states": {
                arm: {"a": state.a.tolist(), "b": state.b.tolist()}
                for arm, state in self.states.items()
            },
        }
        self.path.write_text(json.dumps(payload))
        self._dirty = False
        self._last_save = time.monotonic()

    def select(self, features: list[float]) -> tuple[str, dict[str, float]]:
        x = np.array(features, dtype="float64")
        scores: dict[str, float] = {}
        for arm, state in self.states.items():
            # Use solve() instead of inv() for numerical stability
            theta = np.linalg.solve(state.a, state.b)
            a_inv_x = np.linalg.solve(state.a, x)
            exploit = float(theta @ x)
            explore = float(self.alpha * np.sqrt(x @ a_inv_x))
            scores[arm] = exploit + explore
        selected = max(scores, key=lambda arm: scores[arm])
        return selected, scores

    def update(self, arm: str, features: list[float], reward: float) -> None:
        if arm not in self.states:
            return
        x = np.array(features, dtype="float64")
        state = self.states[arm]
        state.a += np.outer(x, x) + 1e-6 * np.eye(self.dimension)
        state.b += reward * x
        self.history.append({"arm": arm, "features": features, "reward": reward})
        # Cap in-memory history to prevent unbounded growth
        if len(self.history) > 2000:
            self.history = self.history[-1000:]
        self._dirty = True
        now = time.monotonic()
        if now - self._last_save >= self._save_interval:
            self.save()

    def shutdown(self) -> None:
        if self._dirty:
            self.save()
