import pickle
from pathlib import Path
from typing import Any


class ModelProvider:
    def __init__(self, artifacts_path: Path | None = None) -> None:
        if artifacts_path is None:
            artifacts_path = Path(__file__).parent.parent / "artifacts"
        self.artifacts_path = artifacts_path
        self._cache: dict[str, Any] = {}

    def get_model(self, name: str) -> Any:
        if name in self._cache:
            return self._cache[name]
        
        model_path = self.artifacts_path / f"{name}.pkl"
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        
        self._cache[name] = model
        return model
