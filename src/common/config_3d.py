from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil, cos, pi, sin
from pathlib import Path

import numpy as np

from .units import VACUUM_C, VACUUM_ETA0


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
    stage_case: str = "stage1_airbox"
    geometry_kind: str = "airbox"
    lambda0: float = 633.0
    n_air: complex = 1.0 + 0.0j
    mu_r: complex = 1.0 + 0.0j

    # All geometry, mesh, and wavelength values are in nm.
    # Future 3D periodic-cell dimensions.  Stage 1 treats them as the air-box
    # x/y sizes; later stages will use them as the two Floquet periods.
    period_x: float = 600.0
    period_y: float = 500.0
    z_min: float = -550.0
    z_max: float = 350.0

    # Future layered/grating parameters.  They are inactive for airbox runs.
    air_height: float = 350.0
    substrate_thickness: float = 0.0
    grating_height: float = 0.0
    grating_width_x: float = 0.0
    grating_width_y: float = 0.0
    n_substrate: complex | None = None
    n_grating: complex | None = None
    interface_z: float = 0.0
    scattering_background: str = "layered"
    stage4_boundary_model: str = "dtn_port"  # "dtn_port", diagnostic "pml", or diagnostic "robin0"
    stage4_dtn_order_policy: str = "auto_propagating"  # "auto_propagating", "zero_order", or "manual"
    stage4_dtn_assembly: str = "auxiliary"  # 3D v1 supports only sparse auxiliary modal unknowns.
    stage4_pml_outer_bc: str = "natural"  # "natural" or "zero_tangential"
    use_floquet_xy: bool = False
    use_pml: bool = False
    pml_top_thickness: float = 0.0
    pml_bottom_thickness: float = 0.0
    pml_alpha: float = 5.0

    # Incident direction uses spherical angles relative to the height axis:
    # theta = tilt away from downward -z propagation, phi = azimuth in x-y.
    incident_theta_deg: float = 0.0
    incident_phi_deg: float = 0.0
    polarization_kind: str = "custom"  # "s", "p", or "custom"
    custom_polarization: tuple[complex, complex, complex] | None = (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j)
    # incident_e0_v_per_m only controls physical-unit visualization.
    # The finite-element solve still uses incident_amplitude as the normalized field amplitude.
    incident_amplitude: complex = 1.0 + 0.0j
    incident_e0_v_per_m: float = 1.0

    nedelec_degree: int = 2
    visualization_degree: int = 2
    mesh_target_size: float = 140.0
    mesh_cell_type: str = "auto"  # "auto", "tetrahedron", or "hexahedron"
    mesh_spacing_mode: str = "auto"  # Stage 4 hexa: "auto", "uniform_strict", "boundary_fitted", or "local_refined"
    mesh_refined_size: float | None = None
    mesh_refinement_radius: float | None = None
    floquet_constraint_mode: str = "auto"  # auto / topological_edges_p1 / topological_trace_p2
    divergence_penalty: float = 0.0
    diffraction_zero_order_only: bool = True
    diffraction_order_max_m: int | None = None
    diffraction_order_max_n: int | None = None
    diffraction_sample_count_x: int = 24
    diffraction_sample_count_y: int = 24
    diffraction_top_probe_z: float | None = None
    diffraction_bottom_probe_z: float | None = None
    diffraction_probe_fraction: float = 0.75
    diffraction_compute_modal_diagnostic: bool = False
    diffraction_rayleigh_tol: float = 1.0e-6
    # Direct LU setting.  Keep the public choice narrow: default direct LU, or
    # MUMPS out-of-core for memory-pressure diagnostics.
    petsc_direct_solver_profile: str = "default"  # "default" or "mumps_ooc"
    petsc_ksp_view: bool = False
    petsc_log_view: bool = False
    petsc_extra_options: dict[str, object] = field(default_factory=dict)
    matrix_diagnostics_assemble_unconstrained: bool = False
    matrix_diagnostics_assemble_only: bool = False
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
        return 2.0 * pi * VACUUM_C / (self.lambda0 * 1.0e-9)

    @property
    def electric_field_scale_V_per_m(self) -> float:
        return float(self.incident_e0_v_per_m)

    @property
    def magnetic_field_scale_A_per_m(self) -> float:
        return self.electric_field_scale_V_per_m / VACUUM_ETA0

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
    def physical_z_min(self) -> float:
        return self.z_min

    @property
    def physical_z_max(self) -> float:
        return self.z_max

    @property
    def domain_z_min(self) -> float:
        return self.physical_z_min - self.pml_bottom_thickness if self.use_pml else self.physical_z_min

    @property
    def domain_z_max(self) -> float:
        return self.physical_z_max + self.pml_top_thickness if self.use_pml else self.physical_z_max

    @property
    def box_lengths(self) -> tuple[float, float, float]:
        return (
            self.x_max - self.x_min,
            self.y_max - self.y_min,
            self.domain_z_max - self.domain_z_min,
        )

    @property
    def mesh_cells(self) -> tuple[int, int, int]:
        return tuple(max(1, int(ceil(length / self.mesh_target_size))) for length in self.box_lengths)

    @property
    def mesh_cell_type_resolved(self) -> str:
        mode = self.mesh_cell_type.lower()
        if mode == "auto":
            return "hexahedron" if self.use_floquet_xy else "tetrahedron"
        if mode not in {"tetrahedron", "hexahedron"}:
            raise ValueError("mesh_cell_type must be 'auto', 'tetrahedron', or 'hexahedron'.")
        return mode

    @property
    def mesh_spacing_mode_requested(self) -> str:
        mode = self.mesh_spacing_mode.lower()
        if mode not in {"auto", "uniform_strict", "boundary_fitted", "local_refined"}:
            raise ValueError(
                "mesh_spacing_mode must be 'auto', 'uniform_strict', 'boundary_fitted', or 'local_refined'."
            )
        return mode

    @property
    def mesh_refined_size_resolved(self) -> float:
        if self.mesh_refined_size is None:
            return 0.5 * float(self.mesh_target_size)
        if self.mesh_refined_size <= 0.0:
            raise ValueError("mesh_refined_size must be positive when it is set.")
        return float(self.mesh_refined_size)

    @property
    def mesh_refinement_radius_resolved(self) -> float:
        if self.mesh_refinement_radius is None:
            return 2.0 * self.mesh_refined_size_resolved
        if self.mesh_refinement_radius < 0.0:
            raise ValueError("mesh_refinement_radius must be non-negative when it is set.")
        return float(self.mesh_refinement_radius)

    @property
    def floquet_constraint_mode_requested(self) -> str:
        mode = self.floquet_constraint_mode.lower()
        if mode == "dense_side_fit":
            raise ValueError(
                "floquet_constraint_mode='dense_side_fit' is disabled. "
                "Use 'auto', 'topological_edges_p1', or 'topological_trace_p2'."
            )
        if mode not in {
            "auto",
            "topological_edges",
            "topological_edges_p1",
            "topological_trace_p2",
            "sparse_facet",
        }:
            raise ValueError(
                "floquet_constraint_mode must be 'auto', 'topological_edges_p1', "
                "'topological_trace_p2', or legacy aliases 'topological_edges'/'sparse_facet'."
            )
        return mode

    @property
    def petsc_direct_solver_profile_requested(self) -> str:
        profile = self.petsc_direct_solver_profile.lower()
        if profile not in {"default", "mumps_ooc"}:
            raise ValueError(
                "petsc_direct_solver_profile must be 'default' or 'mumps_ooc'. "
                "Old diagnostic profiles were removed from the public code path; "
                "see notes/test/3d_direct_solver_profile_h2p5_report.md."
            )
        return profile

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

    @property
    def floquet_phase_x(self) -> complex:
        return np.exp(1j * self.kx * (self.x_max - self.x_min))

    @property
    def floquet_phase_y(self) -> complex:
        return np.exp(1j * self.ky * (self.y_max - self.y_min))

    @property
    def substrate_index(self) -> complex:
        return complex(self.n_air if self.n_substrate is None else self.n_substrate)

    @property
    def grating_index(self) -> complex:
        return complex(self.n_air if self.n_grating is None else self.n_grating)

    @property
    def eps_air(self) -> complex:
        return complex(self.n_air**2)

    @property
    def eps_substrate(self) -> complex:
        return complex(self.substrate_index**2)

    @property
    def eps_grating(self) -> complex:
        return complex(self.grating_index**2)

    @property
    def grating_x_min(self) -> float:
        return 0.5 * (self.x_min + self.x_max) - 0.5 * self.grating_width_x

    @property
    def grating_x_max(self) -> float:
        return 0.5 * (self.x_min + self.x_max) + 0.5 * self.grating_width_x

    @property
    def grating_y_min(self) -> float:
        return 0.5 * (self.y_min + self.y_max) - 0.5 * self.grating_width_y

    @property
    def grating_y_max(self) -> float:
        return 0.5 * (self.y_min + self.y_max) + 0.5 * self.grating_width_y

    @property
    def grating_z_min(self) -> float:
        return self.interface_z

    @property
    def grating_z_max(self) -> float:
        return self.interface_z + self.grating_height

    @property
    def has_grating_block(self) -> bool:
        return (
            self.geometry_kind == "rectangular_block_grating"
            and self.grating_width_x > 0.0
            and self.grating_width_y > 0.0
            and self.grating_height > 0.0
        )

    @property
    def grating_background_eps(self) -> complex:
        center_z = 0.5 * (self.grating_z_min + self.grating_z_max)
        return self.eps_air if center_z >= self.interface_z else self.eps_substrate

    def as_jsonable(self) -> dict[str, object]:
        """Return a JSON-friendly snapshot used by run_summary.json.

        Keep this as the single place where derived 3D quantities are exposed
        to reports: wave vector, Floquet phases, domain extents, and field
        units all come from the same config used by the solver.
        """
        data = asdict(self)
        for key in ("n_air", "mu_r", "n_substrate", "n_grating", "incident_amplitude"):
            data[key] = _complex_or_none(data[key])
        data["custom_polarization"] = _vector_or_none(self.custom_polarization)
        data["eps_r"] = _complex_or_none(self.eps_r)
        data["x_min"] = self.x_min
        data["x_max"] = self.x_max
        data["y_min"] = self.y_min
        data["y_max"] = self.y_max
        data["physical_z_min"] = self.physical_z_min
        data["physical_z_max"] = self.physical_z_max
        data["domain_z_min"] = self.domain_z_min
        data["domain_z_max"] = self.domain_z_max
        data["mesh_cell_type_resolved"] = self.mesh_cell_type_resolved
        data["mesh_spacing_mode_requested"] = self.mesh_spacing_mode_requested
        data["mesh_refined_size_resolved"] = self.mesh_refined_size_resolved
        data["mesh_refinement_radius_resolved"] = self.mesh_refinement_radius_resolved
        data["floquet_constraint_mode_requested"] = self.floquet_constraint_mode_requested
        data["propagation_direction"] = list(self.direction_vector)
        data["polarization"] = [[value.real, value.imag] for value in self.polarization_vector]
        data["wavevector"] = [[value.real, value.imag] for value in self.wavevector]
        data["floquet_phase_x"] = _complex_or_none(self.floquet_phase_x)
        data["floquet_phase_y"] = _complex_or_none(self.floquet_phase_y)
        data["eps_air"] = _complex_or_none(self.eps_air)
        data["eps_substrate"] = _complex_or_none(self.eps_substrate)
        data["eps_grating"] = _complex_or_none(self.eps_grating)
        data["grating_index"] = _complex_or_none(self.grating_index)
        data["grating_bounds"] = {
            "x_min": self.grating_x_min,
            "x_max": self.grating_x_max,
            "y_min": self.grating_y_min,
            "y_max": self.grating_y_max,
            "z_min": self.grating_z_min,
            "z_max": self.grating_z_max,
        }
        data["grating_background_eps"] = _complex_or_none(self.grating_background_eps)
        data["stage4_dtn_order_policy"] = self.stage4_dtn_order_policy
        data["stage4_dtn_assembly"] = self.stage4_dtn_assembly
        data["k0"] = self.k0
        data["omega"] = self.omega
        data["mesh_cells"] = list(self.mesh_cells)
        data["length_unit"] = "nm"
        data["electric_field_unit"] = "V/m"
        data["magnetic_field_unit"] = "A/m"
        data["magnetic_field_scale_A_per_m"] = self.magnetic_field_scale_A_per_m
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
    """Preset for downward normal incidence with Ex normalized to E0=1."""
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
    """Preset for an oblique TE-like plane wave used in Stage-1/2 checks."""
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
