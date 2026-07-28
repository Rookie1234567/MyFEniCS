"""Fail-closed Task000 parameter and execution schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PARAMETER_SCHEMA_VERSION = "task000.forward-parameters.v1"
OBSERVABLE_SCHEMA_VERSION = "task000.forward-observables.v1"
TASK001_PARAMETER_SCHEMA_VERSION = "task001.forward-parameters.v3"
TASK001_OBSERVABLE_SCHEMA_VERSION = "task001.fixed-n0-orders.v1"
TASK001_MANIFEST_SCHEMA_VERSION = "task001.forward-manifest.v3"

TASK001_FIDELITIES = {
    "HF10": {"degree": 6, "h_nm": 10.0, "modes": 120, "axis_counts": (6, 3, 14)},
    "HF7P5": {"degree": 6, "h_nm": 7.5, "modes": 120, "axis_counts": (9, 4, 20)},
    "LF4": {"degree": 4, "h_nm": 10.0, "modes": 120, "axis_counts": (6, 3, 14)},
    "LF5": {"degree": 5, "h_nm": 10.0, "modes": 120, "axis_counts": (6, 3, 14)},
}

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


def task001_parameter_catalog() -> dict[str, Any]:
    """Return the explicit two-parameter Task001 contract."""

    return {
        "schema_version": TASK001_PARAMETER_SCHEMA_VERSION,
        "configuration": {
            "role": "DOE-controlled experimental configuration; not inverted",
            "physics": {
                "wavelength_nm": {
                    "type": "number", "unit": "nm", "allowed": [13.5],
                    "invertible": False, "source": "target_stage4_config",
                },
            },
            "illumination": {
                "grazing_deg": {
                    "type": "number", "unit": "degree", "range": [0.5, 10.0],
                    "reference": "angle above the sample surface",
                },
                "azimuth_deg": {
                    "type": "number", "unit": "degree", "range": [0.0, 90.0],
                },
                "incident_polarization": {"type": "enum", "allowed": ["S", "P"]},
                "solver_conversion": "incident_theta_deg = 90 - grazing_deg; incident_phi_deg = azimuth_deg",
            },
        },
        "geometry": {
            "role": "invertible specimen parameters",
            "height_nm": {"type": "number", "unit": "nm", "range": [115.0, 125.0], "invertible": True},
            "width_x_nm": {"type": "number", "unit": "nm", "range": [16.0, 18.0], "invertible": True},
        },
        "fidelity": {"model_id": {"type": "enum", "allowed": sorted(TASK001_FIDELITIES)}},
        "observables": {"order_schema_id": {"allowed": [TASK001_OBSERVABLE_SCHEMA_VERSION]}},
        "execution": {
            "mpi_ranks": {"type": "integer", "allowed": [1, 2]},
            "threads_per_rank": {"type": "integer", "allowed": [1]},
            "max_parallel_forward_solves": 1,
        },
    }


@dataclass(frozen=True)
class Task001ForwardParameters:
    height_nm: float
    width_x_nm: float
    grazing_deg: float
    azimuth_deg: float
    incident_polarization: str
    model_id: str
    mpi_ranks: int = 2
    threads_per_rank: int = 1
    wavelength_nm: float = 13.5
    order_schema_id: str = TASK001_OBSERVABLE_SCHEMA_VERSION
    schema_version: str = TASK001_PARAMETER_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Task001ForwardParameters":
        allowed = {
            "height_nm", "width_x_nm", "grazing_deg", "azimuth_deg",
            "incident_polarization", "model_id", "mpi_ranks",
            "threads_per_rank", "wavelength_nm", "order_schema_id",
            "schema_version",
        }
        extra = sorted(set(value) - allowed)
        if extra:
            raise ValueError(f"unsupported Task001 parameter fields: {extra}")
        result = cls(**dict(value))
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != TASK001_PARAMETER_SCHEMA_VERSION:
            raise ValueError("unsupported Task001 parameter schema version")
        if self.model_id not in TASK001_FIDELITIES:
            raise ValueError(f"unsupported Task001 model_id: {self.model_id}")
        if float(self.wavelength_nm) != 13.5:
            raise ValueError("Task001 supports only wavelength_nm=13.5")
        if not 115.0 <= float(self.height_nm) <= 125.0:
            raise ValueError("height_nm must lie in [115, 125]")
        if not 16.0 <= float(self.width_x_nm) <= 18.0:
            raise ValueError("width_x_nm must lie in [16, 18]")
        if not 0.5 <= float(self.grazing_deg) <= 10.0:
            raise ValueError("grazing_deg must lie in [0.5, 10]")
        if not 0.0 <= float(self.azimuth_deg) <= 90.0:
            raise ValueError("azimuth_deg must lie in [0, 90]")
        if self.incident_polarization.upper() not in {"S", "P"}:
            raise ValueError("incident_polarization must be S or P")
        if self.mpi_ranks not in {1, 2}:
            raise ValueError("Task001 mpi_ranks must be 1 or 2")
        if self.threads_per_rank != 1:
            raise ValueError("Task001 threads_per_rank must equal 1")
        if self.order_schema_id != TASK001_OBSERVABLE_SCHEMA_VERSION:
            raise ValueError("unsupported Task001 order_schema_id")

    @property
    def fidelity(self) -> dict[str, Any]:
        self.validate()
        return dict(TASK001_FIDELITIES[self.model_id])

    @property
    def theta_deg(self) -> float:
        """Solver angle measured from the downward surface normal."""

        return 90.0 - float(self.grazing_deg)

    @property
    def phi_deg(self) -> float:
        """Solver azimuth; identical to the user-facing azimuth convention."""

        return float(self.azimuth_deg)

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "configuration": {
                "physics": {"wavelength_nm": float(self.wavelength_nm)},
                "illumination": {
                    "grazing_deg": float(self.grazing_deg),
                    "azimuth_deg": float(self.azimuth_deg),
                    "solver_theta_from_downward_normal_deg": self.theta_deg,
                    "solver_phi_deg": self.phi_deg,
                    "incident_polarization": self.incident_polarization.upper(),
                },
            },
            "geometry": {"height_nm": float(self.height_nm), "width_x_nm": float(self.width_x_nm)},
            "fidelity": {"model_id": self.model_id, **self.fidelity},
            "observables": {"order_schema_id": self.order_schema_id},
            "execution": {"mpi_ranks": self.mpi_ranks, "threads_per_rank": self.threads_per_rank},
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
