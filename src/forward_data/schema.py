"""Fail-closed Task000 parameter and execution schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PARAMETER_SCHEMA_VERSION = "task000.forward-parameters.v1"
OBSERVABLE_SCHEMA_VERSION = "task000.forward-observables.v1"

MODEL_PRESETS = {
    "euv_2d_complex_absorption_v1": "2d_complex_absorption",
    "euv_3d_target_grating_v1": "3d_target_grating_direct_h5",
}


def parameter_catalog() -> dict[str, Any]:
    """Return the explicit v1 parameter contract; no implied solver support."""

    return {
        "schema_version": PARAMETER_SCHEMA_VERSION,
        "physics": {
            "wavelength_nm": {
                "type": "number", "unit": "nm", "allowed": [13.5],
                "invertible": False, "source": "tracked src/main.py preset",
            }
        },
        "geometry": {
            "model_id": {
                "type": "enum", "allowed": sorted(MODEL_PRESETS),
                "invertible": False, "source": "tracked src/main.py preset",
            }
        },
        "materials": {
            "source": "fixed by selected tracked preset", "invertible": False,
        },
        "illumination": {
            "source": "fixed by selected tracked preset", "invertible": False,
        },
        "discretization": {
            "preset": {
                "type": "derived enum", "allowed": sorted(MODEL_PRESETS.values()),
                "source": "model_id mapping", "invertible": False,
            }
        },
        "solver": {
            "source": "fixed by selected tracked preset", "invertible": False,
        },
        "observables": {
            "names": ["R_total", "T_total", "A_balance", "A_volume", "true_residual"],
            "availability": "only fields emitted by the authoritative runner",
        },
        "execution": {
            "mpi_ranks": {"type": "integer", "allowed": [1]},
            "threads_per_rank": {"type": "integer", "allowed": [1]},
        },
        "note": (
            "v1 intentionally exposes no invertible variable until a later task "
            "freezes justified ranges; runner CLI capability is not a range authority"
        ),
    }


@dataclass(frozen=True)
class ForwardParameters:
    model_id: str
    wavelength_nm: float = 13.5
    schema_version: str = PARAMETER_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ForwardParameters":
        allowed = {"model_id", "wavelength_nm", "schema_version"}
        extra = sorted(set(value) - allowed)
        if extra:
            raise ValueError(f"unsupported parameter fields: {extra}")
        result = cls(**dict(value))
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != PARAMETER_SCHEMA_VERSION:
            raise ValueError("unsupported parameter schema version")
        if self.model_id not in MODEL_PRESETS:
            raise ValueError(f"unsupported model_id: {self.model_id}")
        if float(self.wavelength_nm) != 13.5:
            raise ValueError("Task000 v1 supports only wavelength_nm=13.5")

    @property
    def preset(self) -> str:
        self.validate()
        return MODEL_PRESETS[self.model_id]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "wavelength_nm": float(self.wavelength_nm),
            "resolved_preset": self.preset,
        }


@dataclass(frozen=True)
class RunConfig:
    output: Path
    dry_run: bool = False
    formal: bool = False
    timeout_seconds: int = 1800
    mpi_ranks: int = 1
    threads_per_rank: int = 1

    def validate(self) -> None:
        if self.mpi_ranks != 1 or self.threads_per_rank != 1:
            raise ValueError("Task000 allows one serial forward solve with one thread")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.output.is_absolute():
            raise ValueError("output must be an absolute path")
