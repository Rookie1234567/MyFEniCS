from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil, cos, pi, sin
from pathlib import Path

import numpy as np


VACUUM_C = 299_792_458.0


@dataclass(frozen=True)
class Tags3D:
    air: int = 1
    substrate: int = 2
    grating: int = 3
    top_pml: int = 4
    bottom_pml: int = 5
    x_min: int = 11
    x_max: int = 12
    y_min: int = 13
    y_max: int = 14
    z_min: int = 15
    z_max: int = 16


@dataclass
class SimulationConfig3D:
    """Configuration for the staged 3D Maxwell path.

    Stage 1 uses geometry_kind="airbox".  The grating, substrate, and PML
    fields are already present so later stages can grow the same config instead
    of introducing a separate class.
    """

    case_name: str = "airbox3d_normal"
    geometry_kind: str = "airbox"
    lambda0: float = 0.633
    n_air: complex = 1.0 + 0.0j
    mu_r: complex = 1.0 + 0.0j

    # Future 3D periodic-cell dimensions.  Stage 1 treats them as the air-box
    # x/y sizes; later stages will use them as the two Floquet periods.
    period_x: float = 0.60
    period_y: float = 0.50
    z_min: float = -0.55
    z_max: float = 0.35

    # Future layered/grating parameters.  They are inactive for airbox runs.
    air_height: float = 0.35
    substrate_thickness: float = 0.0
    grating_height: float = 0.0
    grating_width_x: float = 0.0
    grating_width_y: float = 0.0
    n_substrate: complex | None = None
    n_grating: complex | None = None
    use_pml: bool = False
    pml_top_thickness: float = 0.0
    pml_bottom_thickness: float = 0.0

    # Incident direction uses spherical angles relative to the height axis:
    # theta = tilt away from downward -z propagation, phi = azimuth in x-y.
    incident_theta_deg: float = 0.0
    incident_phi_deg: float = 0.0
    polarization_kind: str = "custom"  # "s", "p", or "custom"
    custom_polarization: tuple[complex, complex, complex] | None = (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j)
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
    def x_min(self) -> float:
        return 0.0

    @property
    def x_max(self) -> float:
        return self.period_x

    @property
    def y_min(self) -> float:
        return 0.0

    @property
    def y_max(self) -> float:
        return self.period_y

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
    def theta_rad(self) -> float:
        return self.incident_theta_deg * pi / 180.0

    @property
    def phi_rad(self) -> float:
        return self.incident_phi_deg * pi / 180.0

    @property
    def direction_vector(self) -> np.ndarray:
        theta = self.theta_rad
        phi = self.phi_rad
        direction = np.asarray(
            (
                sin(theta) * cos(phi),
                sin(theta) * sin(phi),
                -cos(theta),
            ),
            dtype=np.float64,
        )
        norm = float(np.linalg.norm(direction))
        if norm <= 0.0:
            raise ValueError("The 3D incident direction must be nonzero.")
        return direction / norm

    @property
    def s_polarization_vector(self) -> np.ndarray:
        phi = self.phi_rad
        return np.asarray((-sin(phi), cos(phi), 0.0), dtype=np.complex128)

    @property
    def p_polarization_vector(self) -> np.ndarray:
        return np.cross(self.direction_vector.astype(np.complex128), self.s_polarization_vector)

    @property
    def polarization_vector(self) -> np.ndarray:
        kind = self.polarization_kind.lower()
        if kind == "s":
            polarization = self.s_polarization_vector
        elif kind == "p":
            polarization = self.p_polarization_vector
        elif kind == "custom":
            if self.custom_polarization is None:
                raise ValueError("custom_polarization must be set when polarization_kind='custom'.")
            polarization = np.asarray(self.custom_polarization, dtype=np.complex128)
        else:
            raise ValueError("polarization_kind must be 's', 'p', or 'custom'.")

        norm = float(np.linalg.norm(polarization))
        if norm <= 0.0:
            raise ValueError("The 3D polarization vector must be nonzero.")
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
        for key in ("n_air", "mu_r", "n_substrate", "n_grating", "incident_amplitude"):
            data[key] = _complex_or_none(data[key])
        data["custom_polarization"] = _vector_or_none(self.custom_polarization)
        data["eps_r"] = _complex_or_none(self.eps_r)
        data["x_min"] = self.x_min
        data["x_max"] = self.x_max
        data["y_min"] = self.y_min
        data["y_max"] = self.y_max
        data["propagation_direction"] = list(self.direction_vector)
        data["polarization"] = [[value.real, value.imag] for value in self.polarization_vector]
        data["wavevector"] = [[value.real, value.imag] for value in self.wavevector]
        data["k0"] = self.k0
        data["omega"] = self.omega
        data["mesh_cells"] = list(self.mesh_cells)
        return data


def _complex_or_none(value: complex | None) -> list[float] | None:
    if value is None:
        return None
    number = complex(value)
    return [number.real, number.imag]


def _vector_or_none(values: tuple[complex, complex, complex] | None) -> list[list[float]] | None:
    if values is None:
        return None
    return [_complex_or_none(value) for value in values]


def normal_incidence_airbox_config(**updates) -> SimulationConfig3D:
    values = {
        "case_name": "airbox3d_normal",
        "geometry_kind": "airbox",
        "incident_theta_deg": 0.0,
        "incident_phi_deg": 0.0,
        "polarization_kind": "custom",
        "custom_polarization": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
    }
    values.update(updates)
    return SimulationConfig3D(**values)


def oblique_incidence_airbox_config(**updates) -> SimulationConfig3D:
    values = {
        "case_name": "airbox3d_oblique",
        "geometry_kind": "airbox",
        "incident_theta_deg": 21.131,
        "incident_phi_deg": 33.690,
        "polarization_kind": "s",
        "custom_polarization": None,
    }
    values.update(updates)
    return SimulationConfig3D(**values)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
