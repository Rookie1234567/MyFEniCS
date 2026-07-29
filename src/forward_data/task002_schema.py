"""Fail-closed Task002 S-only continuous-illumination parameter contract."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

import numpy as np

from .schema import Task001ForwardParameters


TASK002_PARAMETER_SCHEMA_VERSION = "task002.s-p5-production-parameters.v2"
TASK002_OBSERVABLE_SCHEMA_VERSION = "task002.fixed-n0-orders.v3"
TASK002_DATASET_SCHEMA_VERSION = "task002.s-p5-single-fidelity-dataset.v2"
TASK002_SAMPLE_SCHEMA_VERSION = "task002.s-p5-single-fidelity-sample.v2"
TASK002_FIXED_M_ORDERS = tuple(range(-7, 4))

TASK002_PRODUCTION_FIDELITIES = {
    "S_PROD_FULL3D_STATIC_P5_H10": {
        "solver_route_id": "full3d_static_uniform_n1curl_p5_h10",
        "degree": 5, "h_nm": 10.0, "axis_counts": (6, 3, 14),
        "element_family": "uniform_N1curl",
        "fidelity_semantics": "best_available_operational_high_fidelity",
    },
}

TASK002_DIAGNOSTIC_FIDELITIES = {
    "S_DIAG_FULL3D_STATIC_P4_H10": {
        "solver_route_id": "full3d_static_uniform_n1curl_p4_h10",
        "degree": 4, "h_nm": 10.0, "axis_counts": (6, 3, 14),
        "element_family": "uniform_N1curl", "role": "diagnostic_only",
    },
    "P4_H7P5_DISCRETIZATION_AUDIT": {
        "solver_route_id": "full3d_static_uniform_n1curl_p4_h7p5",
        "degree": 4, "h_nm": 7.5, "axis_counts": None,
        "element_family": "uniform_N1curl", "role": "discretization_audit_only",
    },
}

# Compatibility name for imports only; it deliberately contains production p5 alone.
TASK002_FIDELITIES = TASK002_PRODUCTION_FIDELITIES

TASK002_HISTORICAL_HYBRID_FIDELITIES = {
    "S_LF_HYBRID_P4_H10_M120": {
        "task001_model_id": "LF4", "degree": 4, "h_nm": 10.0,
        "modes": 120, "axis_counts": (6, 3, 14),
    },
    "S_HF_HYBRID_P6_H10_M120": {
        "task001_model_id": "HF10", "degree": 6, "h_nm": 10.0,
        "modes": 120, "axis_counts": (6, 3, 14),
        "element_family": "uniform_N1curl",
        "actual_element_identity": "uniform N1curl p6",
        "identity_correction": (
            "historical labels describing p5-trace/p6-interior were incorrect; "
            "raw evidence is unchanged"
        ),
    },
}


def task002_parameter_catalog() -> dict[str, Any]:
    return {
        "schema_version": TASK002_PARAMETER_SCHEMA_VERSION,
        "forward_inputs": {
            "height_nm": {"range": [115.0, 125.0], "role": "geometry"},
            "width_x_nm": {"range": [16.0, 18.0], "role": "geometry"},
            "grazing_deg": {"range": [0.5, 10.0], "role": "configuration"},
            "azimuth_deg": {"range": [0.0, 90.0], "role": "configuration"},
        },
        "fixed": {"wavelength_nm": 13.5, "incident_polarization": "S"},
        "fidelity": {
            "production_allowed": sorted(TASK002_PRODUCTION_FIDELITIES),
            "diagnostic_only": sorted(TASK002_DIAGNOSTIC_FIDELITIES),
            "hard_quarantined_historical": sorted(TASK002_HISTORICAL_HYBRID_FIDELITIES),
        },
        "zero_grazing_status": "zero_grazing_limit_not_defined",
        "out_of_domain_status": "out_of_training_domain",
        "solver_conversion": (
            "incident_theta_deg = 90 - grazing_deg; "
            "incident_phi_deg = azimuth_deg"
        ),
    }


def classify_task002_request(value: Mapping[str, Any]) -> dict[str, Any]:
    """Classify user input without clipping or silently extrapolating."""

    try:
        wavelength = float(value.get("wavelength_nm", 13.5))
        polarization = str(value.get("incident_polarization", "S")).upper()
        height = float(value["height_nm"])
        width = float(value["width_x_nm"])
        grazing = float(value["grazing_deg"])
        azimuth = float(value["azimuth_deg"])
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "invalid_input", "reason": str(exc)}
    if wavelength != 13.5:
        return {"status": "unsupported_wavelength", "wavelength_nm": wavelength}
    if polarization != "S":
        return {"status": "polarization_not_trained", "incident_polarization": polarization}
    if grazing == 0.0:
        return {"status": "zero_grazing_limit_not_defined", "grazing_deg": grazing}
    if not (
        115.0 <= height <= 125.0
        and 16.0 <= width <= 18.0
        and 0.5 <= grazing <= 10.0
        and 0.0 <= azimuth <= 90.0
    ):
        return {"status": "out_of_training_domain"}
    return {"status": "in_domain"}


@dataclass(frozen=True)
class Task002ForwardParameters:
    height_nm: float
    width_x_nm: float
    grazing_deg: float
    azimuth_deg: float
    model_id: str
    wavelength_nm: float = 13.5
    incident_polarization: str = "S"
    mpi_ranks: int = 2
    threads_per_rank: int = 1
    order_schema_id: str = TASK002_OBSERVABLE_SCHEMA_VERSION
    schema_version: str = TASK002_PARAMETER_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Task002ForwardParameters":
        allowed = {
            "height_nm", "width_x_nm", "grazing_deg", "azimuth_deg",
            "model_id", "wavelength_nm", "incident_polarization", "mpi_ranks",
            "threads_per_rank", "order_schema_id", "schema_version",
        }
        extra = sorted(set(value) - allowed)
        if extra:
            raise ValueError(f"unsupported Task002 parameter fields: {extra}")
        result = cls(**dict(value))
        result.validate()
        return result

    def validate(self) -> None:
        request = classify_task002_request(self.__dict__)
        if request["status"] != "in_domain":
            raise ValueError(request["status"])
        if self.schema_version != TASK002_PARAMETER_SCHEMA_VERSION:
            raise ValueError("unsupported Task002 parameter schema version")
        if self.model_id not in TASK002_PRODUCTION_FIDELITIES:
            raise ValueError(f"Task002 production accepts p5-only model_id: {self.model_id}")
        if self.mpi_ranks != 2 or self.threads_per_rank != 1:
            raise ValueError("Task002 FEM requires MPI2 and one thread per rank")
        if self.order_schema_id != TASK002_OBSERVABLE_SCHEMA_VERSION:
            raise ValueError("unsupported Task002 observable schema")

    @property
    def fidelity(self) -> dict[str, Any]:
        self.validate()
        return dict(TASK002_PRODUCTION_FIDELITIES[self.model_id])

    @property
    def theta_deg(self) -> float:
        return 90.0 - float(self.grazing_deg)

    @property
    def phi_deg(self) -> float:
        return float(self.azimuth_deg)

    def normalized_features(self) -> np.ndarray:
        self.validate()
        grazing = math.radians(float(self.grazing_deg))
        azimuth = math.radians(float(self.azimuth_deg))
        return np.asarray([
            (float(self.height_nm) - 120.0) / 5.0,
            (float(self.width_x_nm) - 17.0) / 1.0,
            math.cos(grazing) * math.cos(azimuth),
            math.cos(grazing) * math.sin(azimuth),
        ], dtype=np.float64)

    def to_task001(self) -> Task001ForwardParameters:
        raise ValueError(
            "Task002 production Full3D parameters cannot be routed through Task001 Hybrid"
        )

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        fidelity = self.fidelity
        fidelity["axis_counts"] = list(fidelity["axis_counts"])
        return {
            "schema_version": self.schema_version,
            "configuration": {
                "wavelength_nm": 13.5, "incident_polarization": "S",
                "grazing_deg": float(self.grazing_deg),
                "azimuth_deg": float(self.azimuth_deg),
                "solver_theta_deg": self.theta_deg, "solver_phi_deg": self.phi_deg,
            },
            "geometry": {
                "height_nm": float(self.height_nm),
                "width_x_nm": float(self.width_x_nm),
            },
            "fidelity": {"model_id": self.model_id, **fidelity},
            "normalized_features": self.normalized_features().tolist(),
            "observable_schema_version": self.order_schema_id,
            "execution": {"mpi_ranks": 2, "threads_per_rank": 1},
        }


@dataclass(frozen=True)
class Task002HistoricalHybridParameters(Task002ForwardParameters):
    """Read-only compatibility identity for immutable Case112/113 evidence."""

    def validate(self) -> None:
        request = classify_task002_request(self.__dict__)
        if request["status"] != "in_domain":
            raise ValueError(request["status"])
        if self.model_id not in TASK002_HISTORICAL_HYBRID_FIDELITIES:
            raise ValueError("historical identity accepts only quarantined Hybrid IDs")
        if self.mpi_ranks != 2 or self.threads_per_rank != 1:
            raise ValueError("historical Task002 evidence identity is MPI2/thread1")
        if self.order_schema_id != TASK002_OBSERVABLE_SCHEMA_VERSION:
            raise ValueError("unsupported Task002 observable schema")

    @property
    def fidelity(self) -> dict[str, Any]:
        self.validate()
        return dict(TASK002_HISTORICAL_HYBRID_FIDELITIES[self.model_id])

    def to_task001(self) -> Task001ForwardParameters:
        self.validate()
        return Task001ForwardParameters(
            height_nm=self.height_nm, width_x_nm=self.width_x_nm,
            grazing_deg=self.grazing_deg, azimuth_deg=self.azimuth_deg,
            incident_polarization="S", model_id=self.fidelity["task001_model_id"],
            mpi_ranks=2, threads_per_rank=1,
        )
