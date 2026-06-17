from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil, pi, sqrt
from pathlib import Path

import numpy as np


VACUUM_C = 299_792_458.0
VACUUM_MU0 = 4.0e-7 * pi
VACUUM_ETA0 = VACUUM_MU0 * VACUUM_C


@dataclass(frozen=True)
class Tags3D:
    air: int = 1
    x_min: int = 11
    x_max: int = 12
    y_min: int = 13
    y_max: int = 14
    z_min: int = 15
    z_max: int = 16


@dataclass
class AirBox3DConfig:
    """Configuration for the stage-1 3D uniform-air Maxwell verification."""

    case_name: str = "airbox3d_normal"
    lambda0: float = 0.633
    n_air: complex = 1.0 + 0.0j
    mu_r: complex = 1.0 + 0.0j

    x_min: float = 0.0
    x_max: float = 0.60
    y_min: float = 0.0
    y_max: float = 0.50
    z_min: float = -0.55
    z_max: float = 0.35

    # Unit propagation direction and transverse polarization.  The solver
    # validates k dot p = 0 instead of silently changing the requested wave.
    propagation_direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    polarization: tuple[complex, complex, complex] = (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j)
    incident_amplitude: complex = 1.0 + 0.0j

    nedelec_degree: int = 2
    visualization_degree: int = 2
    mesh_target_size: float = 0.14
    unique_output: bool = True
    tags: Tags3D = field(default_factory=Tags3D)

    @property
    def eps_r(self) -> complex:
        return complex(self.n_air**2)

    @property
    def k0(self) -> float:
        return 2.0 * pi / self.lambda0

    @property
    def omega(self) -> float:
        return 2.0 * pi * VACUUM_C / (self.lambda0 * 1.0e-6)

    @property
    def box_lengths(self) -> tuple[float, float, float]:
        return (
            self.x_max - self.x_min,
            self.y_max - self.y_min,
            self.z_max - self.z_min,
        )

    @property
    def mesh_cells(self) -> tuple[int, int, int]:
        return tuple(max(1, int(ceil(length / self.mesh_target_size))) for length in self.box_lengths)

    @property
    def direction_vector(self) -> np.ndarray:
        direction = np.asarray(self.propagation_direction, dtype=np.float64)
        norm = float(np.linalg.norm(direction))
        if norm <= 0.0:
            raise ValueError("propagation_direction must be nonzero.")
        return direction / norm

    @property
    def polarization_vector(self) -> np.ndarray:
        polarization = np.asarray(self.polarization, dtype=np.complex128)
        norm = float(np.linalg.norm(polarization))
        if norm <= 0.0:
            raise ValueError("polarization must be nonzero.")
        polarization = polarization / norm
        dot_k_p = np.dot(self.wavevector, polarization)
        if abs(dot_k_p) > 1.0e-10 * max(abs(self.k0), 1.0):
            raise ValueError(
                "The 3D incident polarization must be transverse: k dot p must be zero. "
                f"Current k dot p = {dot_k_p!r}."
            )
        return polarization

    @property
    def wavevector(self) -> np.ndarray:
        return self.k0 * complex(self.n_air) * self.direction_vector.astype(np.complex128)

    @property
    def kx(self) -> complex:
        return complex(self.wavevector[0])

    @property
    def ky(self) -> complex:
        return complex(self.wavevector[1])

    @property
    def kz(self) -> complex:
        return complex(self.wavevector[2])

    def as_jsonable(self) -> dict[str, object]:
        data = asdict(self)
        data["n_air"] = [complex(self.n_air).real, complex(self.n_air).imag]
        data["mu_r"] = [complex(self.mu_r).real, complex(self.mu_r).imag]
        data["eps_r"] = [self.eps_r.real, self.eps_r.imag]
        data["incident_amplitude"] = [complex(self.incident_amplitude).real, complex(self.incident_amplitude).imag]
        data["propagation_direction"] = list(self.direction_vector)
        data["polarization"] = [[value.real, value.imag] for value in self.polarization_vector]
        data["wavevector"] = [[value.real, value.imag] for value in self.wavevector]
        data["k0"] = self.k0
        data["omega"] = self.omega
        data["mesh_cells"] = list(self.mesh_cells)
        data["vacuum_eta0_ohm"] = VACUUM_ETA0
        return data


def normal_incidence_airbox_config(**updates) -> AirBox3DConfig:
    values = {
        "case_name": "airbox3d_normal",
        "propagation_direction": (0.0, 0.0, -1.0),
        "polarization": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
    }
    values.update(updates)
    return AirBox3DConfig(**values)


def oblique_incidence_airbox_config(**updates) -> AirBox3DConfig:
    sx = 0.30
    sy = 0.20
    sz = -sqrt(max(0.0, 1.0 - sx * sx - sy * sy))
    polarization = np.asarray((sy, -sx, 0.0), dtype=np.complex128)
    polarization = polarization / np.linalg.norm(polarization)
    values = {
        "case_name": "airbox3d_oblique",
        "propagation_direction": (sx, sy, sz),
        "polarization": tuple(polarization),
    }
    values.update(updates)
    return AirBox3DConfig(**values)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
