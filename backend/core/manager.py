import os
import pickle
import tempfile
from pathlib import Path
from typing import Any


class ModelProvider:
    # Backward-compatible aliases: existing call sites can keep old local ids.
    DEFAULT_MODEL_REGISTRY_MAP = {
        "azca_demand_v1": "azca-services-model",
        "azca_menu_starter_v2": "azca-menus-model",
        "azca_menu_main_v2": "azca-menus-model",
        "azca_menu_dessert_v2": "azca-menus-model",
    }

    def __init__(
        self,
        artifacts_path: Path | None = None,
        prefer_azure: bool | None = None,
        model_registry_map: dict[str, str] | None = None,
    ) -> None:
        if artifacts_path is None:
            artifacts_path = self._default_artifacts_path()

        disable_azure = (
            os.getenv("AZCA_DISABLE_AZURE_ML_MODELS", "0").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        self.artifacts_path = artifacts_path
        self.prefer_azure = (not disable_azure) if prefer_azure is None else prefer_azure
        self.model_registry_map = {
            **self.DEFAULT_MODEL_REGISTRY_MAP,
            **(model_registry_map or {}),
        }

        self._cache: dict[str, Any] = {}
        self._resolved_refs: dict[str, str] = {}
        self._workspace: Any | None = None
        self._workspace_bootstrap_error: Exception | None = None
        self._azure_warning_printed = False
        self._registered_artifact_cache: dict[str, Path] = {}
        self._registered_version_cache: dict[str, str] = {}

    @staticmethod
    def _default_artifacts_path() -> Path:
        base_path = Path(__file__).parent.parent
        azca_artifacts = base_path / "azca" / "artifacts"
        if azca_artifacts.exists():
            return azca_artifacts
        return base_path / "artifacts"

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        return {
            token
            for token in value.replace("-", "_").lower().split("_")
            if token
        }

    def _get_workspace(self) -> Any:
        if self._workspace is not None:
            return self._workspace

        if self._workspace_bootstrap_error is not None:
            raise RuntimeError("Azure ML workspace no disponible") from self._workspace_bootstrap_error

        try:
            from azureml.core import Workspace
        except ImportError as exc:
            self._workspace_bootstrap_error = exc
            raise RuntimeError(
                "Falta dependencia 'azureml-core'. Instalala para cargar modelos desde Azure ML."
            ) from exc

        subscription_id = os.getenv("AZUREML_SUBSCRIPTION_ID") or os.getenv("AML_SUBSCRIPTION_ID")
        resource_group = os.getenv("AZUREML_RESOURCE_GROUP") or os.getenv("AML_RESOURCE_GROUP")
        workspace_name = os.getenv("AZUREML_WORKSPACE_NAME") or os.getenv("AML_WORKSPACE_NAME")
        config_path = os.getenv("AZUREML_CONFIG_PATH") or os.getenv("AML_WORKSPACE_CONFIG_PATH")

        try:
            if subscription_id and resource_group and workspace_name:
                self._workspace = Workspace.get(
                    name=workspace_name,
                    subscription_id=subscription_id,
                    resource_group=resource_group,
                )
            elif config_path:
                self._workspace = Workspace.from_config(path=config_path)
            else:
                self._workspace = Workspace.from_config()
        except Exception as exc:
            self._workspace_bootstrap_error = exc
            raise RuntimeError(
                "No se pudo inicializar Azure ML Workspace. "
                "Configura AZUREML_SUBSCRIPTION_ID/AZUREML_RESOURCE_GROUP/AZUREML_WORKSPACE_NAME "
                "o un config.json valido (AZUREML_CONFIG_PATH)."
            ) from exc

        return self._workspace

    @staticmethod
    def _model_sort_key(model: Any) -> tuple[int, str]:
        version_text = str(getattr(model, "version", ""))
        numeric_version = int(version_text) if version_text.isdigit() else -1
        created_time = str(getattr(model, "created_time", ""))
        return numeric_version, created_time

    def _get_latest_registered_model(self, registered_name: str) -> tuple[str, Path]:
        if registered_name in self._registered_artifact_cache:
            version = self._registered_version_cache.get(registered_name, "unknown")
            return version, self._registered_artifact_cache[registered_name]

        try:
            from azureml.core.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "Falta dependencia 'azureml-core'. Instalala para consultar modelos registrados."
            ) from exc

        workspace = self._get_workspace()
        models = Model.list(workspace=workspace, name=registered_name)
        if not models:
            raise FileNotFoundError(
                f"No se encontro el modelo registrado '{registered_name}' en Azure ML."
            )

        latest_model = max(models, key=self._model_sort_key)
        version = str(latest_model.version)

        download_root = (
            Path(tempfile.gettempdir())
            / "azca_aml_models"
            / workspace.name
            / registered_name
            / version
        )
        download_root.mkdir(parents=True, exist_ok=True)

        downloaded = Path(latest_model.download(target_dir=str(download_root), exist_ok=True))
        artifact_root = downloaded if downloaded.is_dir() else downloaded.parent

        self._registered_artifact_cache[registered_name] = artifact_root
        self._registered_version_cache[registered_name] = version

        return version, artifact_root

    def _resolve_pickle_from_artifacts(
        self,
        artifact_root: Path,
        logical_name: str,
        registered_name: str,
    ) -> Path:
        expected_filename = f"{logical_name}.pkl"
        pickles = sorted(artifact_root.rglob("*.pkl"))
        if not pickles:
            raise FileNotFoundError(
                f"No hay archivos .pkl en artefactos descargados para '{registered_name}' ({artifact_root})."
            )

        exact_match = next((p for p in pickles if p.name == expected_filename), None)
        if exact_match:
            return exact_match

        registered_match = next((p for p in pickles if p.name == f"{registered_name}.pkl"), None)
        if registered_match:
            return registered_match

        logical_tokens = self._tokenize(logical_name)
        scored_candidates: list[tuple[int, Path]] = []

        for candidate in pickles:
            score = len(logical_tokens.intersection(self._tokenize(candidate.stem)))
            if score > 0:
                scored_candidates.append((score, candidate))

        if scored_candidates:
            scored_candidates.sort(key=lambda item: (-item[0], item[1].name))
            return scored_candidates[0][1]

        if len(pickles) == 1:
            return pickles[0]

        candidate_names = [path.name for path in pickles]
        raise FileNotFoundError(
            f"No se pudo resolver el .pkl para '{logical_name}' en '{registered_name}'. "
            f"Pickles disponibles: {candidate_names}"
        )

    def _load_model_from_azure(self, logical_name: str) -> Any:
        registered_name = self.model_registry_map.get(logical_name, logical_name)
        version, artifact_root = self._get_latest_registered_model(registered_name)

        model_path = self._resolve_pickle_from_artifacts(
            artifact_root=artifact_root,
            logical_name=logical_name,
            registered_name=registered_name,
        )

        print(
            f"Cargando modelo Azure ML '{registered_name}:{version}' desde {model_path}"
        )
        with open(model_path, "rb") as model_file:
            model = pickle.load(model_file)

        self._resolved_refs[logical_name] = f"{registered_name}:{version}"
        return model

    def _load_model_from_local_artifacts(self, name: str) -> Any:
        model_path = self.artifacts_path / f"{name}.pkl"

        if not model_path.exists():
            available_models = list(self.artifacts_path.glob("*.pkl")) if self.artifacts_path.exists() else []
            available_names = [m.stem for m in available_models]
            raise FileNotFoundError(
                f"Modelo local '{name}.pkl' no encontrado en {self.artifacts_path}. "
                f"Modelos disponibles: {available_names}"
            )

        print(f"Cargando modelo local desde {model_path}")
        with open(model_path, "rb") as model_file:
            model = pickle.load(model_file)

        self._resolved_refs[name] = model_path.name
        return model

    def get_model_reference(self, name: str) -> str:
        if name in self._resolved_refs:
            return self._resolved_refs[name]

        mapped_name = self.model_registry_map.get(name, name)
        version = self._registered_version_cache.get(mapped_name)
        if version:
            return f"{mapped_name}:{version}"
        return mapped_name

    def get_model(self, name: str) -> Any:
        if name in self._cache:
            return self._cache[name]

        azure_error: Exception | None = None

        if self.prefer_azure:
            try:
                model = self._load_model_from_azure(name)
                self._cache[name] = model
                print(f"Modelo cargado correctamente: {type(model).__name__}")
                return model
            except Exception as exc:
                azure_error = exc
                if not self._azure_warning_printed:
                    print(
                        "Azure ML no disponible, se intenta fallback local. "
                        f"Detalle: {type(exc).__name__}: {exc}"
                    )
                    self._azure_warning_printed = True

        try:
            model = self._load_model_from_local_artifacts(name)
            self._cache[name] = model
            print(f"Modelo cargado correctamente: {type(model).__name__}")
            return model
        except Exception as local_error:
            if azure_error is not None:
                raise RuntimeError(
                    "Error cargando modelo desde Azure ML y desde artifacts locales. "
                    f"Azure: {type(azure_error).__name__}: {azure_error}. "
                    f"Local: {type(local_error).__name__}: {local_error}"
                ) from local_error
            raise
