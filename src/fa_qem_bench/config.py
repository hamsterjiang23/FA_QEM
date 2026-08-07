from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .util import sha256_file

SUPPORTED_METHODS = ("qem", "qem4vr", "robustlpm", "ice", "stmw", "cwf")
SUPPORTED_TRACKS = ("research", "asset")


@dataclass(frozen=True)
class ExperimentConfig:
    root: Path
    path: Path
    data: dict[str, Any]

    @property
    def source(self) -> Path:
        return (self.root / str(self.data["source"]["path"])).resolve()

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def seed(self) -> int:
        return int(self.data["random_seed"])

    @property
    def tolerance(self) -> float:
        return float(self.data["target_tolerance"])

    def target(self, ratio: str | float) -> int:
        key = str(ratio)
        aliases = {"0.50": "0.5", "0.10": "0.1", "0.010": "0.01"}
        key = aliases.get(key, key)
        try:
            return int(self.data["targets"][key])
        except KeyError as error:
            raise ValueError(f"unsupported ratio: {ratio}") from error

    def ratio_key(self, ratio: str | float) -> str:
        target = self.target(ratio)
        for key, value in self.data["targets"].items():
            if int(value) == target:
                return str(key)
        raise AssertionError("validated target disappeared")


def load_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path).resolve()
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("experiment config must be a mapping")
    config = ExperimentConfig(root=config_path.parent, path=config_path, data=data)
    validate_config(config)
    return config


def validate_config(config: ExperimentConfig) -> None:
    if not config.source.is_file():
        raise FileNotFoundError(config.source)
    actual_hash = sha256_file(config.source)
    expected_hash = str(config.data["source"]["sha256"]).lower()
    if actual_hash != expected_hash:
        raise ValueError(f"source SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")
    methods = tuple(config.data.get("methods", ()))
    if methods != SUPPORTED_METHODS:
        raise ValueError(f"methods must be exactly {SUPPORTED_METHODS}")
    tracks = tuple(config.data.get("tracks", ()))
    if tracks != SUPPORTED_TRACKS:
        raise ValueError(f"tracks must be exactly {SUPPORTED_TRACKS}")
    if set(config.data["targets"]) != {"0.5", "0.1", "0.01"}:
        raise ValueError("targets must contain exactly 0.5, 0.1, and 0.01")
    if not 0 <= config.tolerance <= 0.1:
        raise ValueError("target_tolerance must be in [0, 0.1]")
