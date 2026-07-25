from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, geometry
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import SimulationConfig3D
from ..modes.cross_section_spaces import CrossSectionMesh, CrossSectionSpaces
from ..modes.mode_classification import BiorthogonalModeBasis
from ..solvers.dtn_port_3d import _assign_fe_solution_from_augmented
from ..solvers.hybrid_local_dtn import HybridLocalDtnSystem
from .full3d_reference import _sample_distributed_function
from .rta_3d import _region_absorbed_power


@dataclass(frozen=True)
class ModalPlaneSamples:
    """Bounded selected-plane reconstruction; no middle volume is retained."""

    x_nm: np.ndarray
    y_nm: np.ndarray
    z_nm: np.ndarray
    electric_V_per_m: np.ndarray
    magnetic_A_per_m: np.ndarray


def relative_sample_error(actual: np.ndarray, expected: np.ndarray) -> dict[str, float]:
    """Return scale-symmetric errors for two bounded complex sample arrays."""

    first = np.asarray(actual, dtype=np.complex128)
    second = np.asarray(expected, dtype=np.complex128)
    if first.shape != second.shape:
        raise ValueError(f"Sample shapes differ: {first.shape} != {second.shape}.")
    difference = first - second
    scale = max(float(np.linalg.norm(first)), float(np.linalg.norm(second)), 1.0e-30)
    point_norm = np.linalg.norm(difference, axis=-1) if difference.ndim > 1 else np.abs(difference)
    return {
        "relative_l2": float(np.linalg.norm(difference) / scale),
        "absolute_l2": float(np.linalg.norm(difference)),
        "max_pointwise_absolute": float(np.max(point_norm, initial=0.0)),
        "comparison_scale_l2": scale,
    }


def _interpolation_points(space) -> np.ndarray:
    points = space.element.interpolation_points
    return points() if callable(points) else points


def _sample_distributed_2d(function, points_xy: np.ndarray) -> np.ndarray:
    """Evaluate a distributed 2D function on a small replicated point set."""

    msh = function.function_space.mesh
    comm = msh.comm
    points_xy = np.asarray(points_xy, dtype=np.float64).reshape((-1, 2))
    # DOLFINx geometry queries always use three-coordinate points, including
    # meshes whose geometric dimension is two.
    points = np.zeros((len(points_xy), 3), dtype=np.float64)
    points[:, :2] = points_xy
    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    owned_cells = msh.topology.index_map(msh.topology.dim).size_local

    local_indices: list[int] = []
    local_cells: list[int] = []
    local_owned: list[bool] = []
    for point_index in range(len(points)):
        links = collisions.links(point_index)
        if len(links):
            owned = links[links < owned_cells]
            selected = int(owned[0] if len(owned) else links[0])
            local_indices.append(point_index)
            local_cells.append(selected)
            local_owned.append(selected < owned_cells)

    if local_indices:
        local_values = np.asarray(
            function.eval(
                points[np.asarray(local_indices, dtype=np.int32)],
                np.asarray(local_cells, dtype=np.int32),
            ),
            dtype=np.complex128,
        )
        if local_values.ndim == 1:
            local_values = local_values.reshape((len(local_indices), -1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_owned, local_values))
    width = next((int(values.shape[1]) for _, _, values in packets if values.size), 0)
    if width == 0:
        raise RuntimeError("No rank returned a value for the modal sample points.")
    values = np.zeros((len(points), width), dtype=np.complex128)
    filled = np.zeros(len(points), dtype=bool)
    filled_from_owned = np.zeros(len(points), dtype=bool)
    for indices, owned_flags, packet_values in packets:
        for row, point_index in enumerate(indices):
            if not filled[point_index] or (owned_flags[row] and not filled_from_owned[point_index]):
                values[point_index] = packet_values[row]
                filled[point_index] = True
                filled_from_owned[point_index] = owned_flags[row]
    if not np.all(filled):
        missing = np.flatnonzero(~filled)
        raise RuntimeError(
            f"No cross-section cell found for {len(missing)} sample points; "
            f"first missing point={points_xy[int(missing[0])].tolist()}."
        )
    return values


def assign_local_total_electric_field(
    system: HybridLocalDtnSystem,
    augmented_solution: PETSc.Vec,
):
    """Back-substitute one local MPC solution into its physical H(curl) field."""

    if augmented_solution.getSize() != system.global_size:
        raise ValueError("Local augmented solution and Hybrid local system sizes differ.")
    return _assign_fe_solution_from_augmented(
        augmented_solution,
        system.floquet_data,
        system.n_external_aux,
    )


def local_magnetic_field_A_per_m(
    cfg: SimulationConfig3D,
    electric_field,
):
    """Interpolate physical H=curl(E)/(i*k0*mu_r) for bounded sampling."""

    msh = electric_field.function_space.mesh
    space = fem.functionspace(
        msh,
        element(
            "DG",
            msh.basix_cell(),
            int(cfg.visualization_degree),
            shape=(3,),
            dtype=default_real_type,
        ),
    )
    expression = (
        cfg.magnetic_field_scale_A_per_m
        / (1j * cfg.k0 * cfg.mu_r)
        * ufl.curl(electric_field)
    )
    magnetic = fem.Function(space, name="task032_hybrid_H_A_per_m")
    magnetic.interpolate(fem.Expression(expression, _interpolation_points(space)))
    magnetic.x.scatter_forward()
    return magnetic


class ModalFieldReconstructor:
    """Reconstruct selected middle planes and modal absorption from distributed modes."""

    def __init__(
        self,
        cfg: SimulationConfig3D,
        cross_section: CrossSectionMesh,
        spaces: CrossSectionSpaces,
        positive: BiorthogonalModeBasis,
        negative: BiorthogonalModeBasis,
        *,
        bottom_z_nm: float = 10.0,
        top_z_nm: float = 110.0,
    ) -> None:
        if len(positive.modes) != len(negative.modes):
            raise ValueError("Positive and negative modal bases must have equal sizes.")
        self.cfg = cfg
        self.cross_section = cross_section
        self.spaces = spaces
        self.positive = positive
        self.negative = negative
        self.bottom_z_nm = float(bottom_z_nm)
        self.top_z_nm = float(top_z_nm)
        if self.top_z_nm <= self.bottom_z_nm:
            raise ValueError("The modal interval must have positive length.")
        self._modes = tuple([*positive.modes, *negative.modes])
        msh = self.cross_section.mesh
        self._magnetic_space = fem.functionspace(
            msh,
            element(
                "DG",
                msh.basix_cell(),
                int(self.cfg.visualization_degree),
                shape=(3,),
                dtype=default_real_type,
            ),
        )
        # Reuse one mixed source, its collapsed component scratch fields, one
        # beta Constant, one Expression and one DG magnetic target for every
        # mode. Creating/scattering three Functions plus one Expression per
        # mode exhausts MPICH context IDs near M=120 despite the small payload.
        self._sample_source = fem.Function(
            spaces.mixed, name="task032_middle_mode_sample_source"
        )
        self._sample_transverse = fem.Function(
            spaces.transverse, name="task032_middle_mode_sample_Et"
        )
        self._sample_longitudinal = fem.Function(
            spaces.longitudinal, name="task032_middle_mode_sample_Ez"
        )
        self._magnetic_beta = fem.Constant(
            msh, PETSc.ScalarType(0.0 + 0.0j)
        )
        source_Et, source_Ez = ufl.split(self._sample_source)
        inverse_i_k_mu = self.cfg.magnetic_field_scale_A_per_m / (
            1j * self.cfg.k0 * self.cfg.mu_r
        )
        magnetic_expression = inverse_i_k_mu * ufl.as_vector(
            (
                source_Ez.dx(1) - 1j * self._magnetic_beta * source_Et[1],
                1j * self._magnetic_beta * source_Et[0] - source_Ez.dx(0),
                source_Et[1].dx(0) - source_Et[0].dx(1),
            )
        )
        self._magnetic_expression = fem.Expression(
            magnetic_expression, _interpolation_points(self._magnetic_space)
        )
        self._magnetic_scratch = fem.Function(
            self._magnetic_space, name="task032_middle_mode_H_A_per_m"
        )
        self._total = fem.Function(spaces.mixed, name="task032_middle_modal_E_total")
        Et, Ez = ufl.split(self._total)
        electric = ufl.as_vector((Et[0], Et[1], Ez))
        density = (
            0.5
            * float(cfg.k0)
            * ufl.imag(cross_section.epsilon_r)
            * ufl.real(ufl.inner(electric, electric))
        )
        self._absorption_form = fem.form(density * ufl.dx)

    @property
    def mode_count_per_direction(self) -> int:
        return len(self.positive.modes)

    def _sample_mode_bases(
        self, points: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        electric_rows = []
        magnetic_rows = []
        for mode in self._modes:
            mode.right.right_full.copy(self._sample_source.x.petsc_vec)
            self._sample_source.x.scatter_forward()
            self._sample_transverse.x.array[:] = self._sample_source.x.array[
                self.spaces.transverse_to_mixed
            ]
            self._sample_longitudinal.x.array[:] = self._sample_source.x.array[
                self.spaces.longitudinal_to_mixed
            ]
            self._sample_transverse.x.scatter_forward()
            self._sample_longitudinal.x.scatter_forward()
            electric_rows.append(
                np.column_stack(
                    (
                        _sample_distributed_2d(
                            self._sample_transverse, points
                        )[:, :2],
                        _sample_distributed_2d(
                            self._sample_longitudinal, points
                        )[:, 0],
                    )
                )
            )
            try:
                self._magnetic_beta.value[...] = PETSc.ScalarType(mode.beta)
            except Exception:
                self._magnetic_beta.value = PETSc.ScalarType(mode.beta)
            self._magnetic_scratch.interpolate(self._magnetic_expression)
            self._magnetic_scratch.x.scatter_forward()
            magnetic_rows.append(
                _sample_distributed_2d(self._magnetic_scratch, points)[:, :3]
            )
        return (
            np.asarray(electric_rows, dtype=np.complex128),
            np.asarray(magnetic_rows, dtype=np.complex128),
        )

    def coefficients_at_z(
        self,
        modal_amplitudes: Sequence[complex],
        z_nm: float,
    ) -> np.ndarray:
        modal = np.asarray(modal_amplitudes, dtype=np.complex128)
        count = self.mode_count_per_direction
        if modal.shape != (2 * count,):
            raise ValueError(f"Modal amplitudes must have shape ({2 * count},).")
        positive_beta = np.asarray(
            [mode.beta for mode in self.positive.modes], dtype=np.complex128
        )
        negative_beta = np.asarray(
            [mode.beta for mode in self.negative.modes], dtype=np.complex128
        )
        return np.concatenate(
            (
                modal[:count]
                * np.exp(1j * positive_beta * (float(z_nm) - self.bottom_z_nm)),
                modal[count:]
                * np.exp(1j * negative_beta * (float(z_nm) - self.top_z_nm)),
            )
        )

    def selected_planes(
        self,
        modal_amplitudes: Sequence[complex],
        x_nm: Sequence[float],
        y_nm: Sequence[float],
        z_nm: Sequence[float],
    ) -> ModalPlaneSamples:
        x_values = np.asarray(x_nm, dtype=np.float64)
        y_values = np.asarray(y_nm, dtype=np.float64)
        z_values = np.asarray(z_nm, dtype=np.float64)
        if x_values.ndim != 1 or y_values.ndim != 1 or z_values.ndim != 1:
            raise ValueError("Selected-plane coordinates must be one-dimensional.")
        yy, xx = np.meshgrid(y_values, x_values, indexing="ij")
        points = np.column_stack((xx.ravel(), yy.ravel()))
        electric_basis, magnetic_basis = self._sample_mode_bases(points)
        electric = []
        magnetic = []
        for value in z_values:
            coefficients = self.coefficients_at_z(modal_amplitudes, float(value))
            electric.append(np.einsum("m,mnc->nc", coefficients, electric_basis))
            magnetic.append(np.einsum("m,mnc->nc", coefficients, magnetic_basis))
        shape = (len(z_values), len(y_values), len(x_values), 3)
        return ModalPlaneSamples(
            x_nm=x_values,
            y_nm=y_values,
            z_nm=z_values,
            electric_V_per_m=(
                self.cfg.electric_field_scale_V_per_m
                * np.asarray(electric, dtype=np.complex128).reshape(shape)
            ),
            magnetic_A_per_m=np.asarray(magnetic, dtype=np.complex128).reshape(shape),
        )

    def absorbed_power_code_units(
        self,
        modal_amplitudes: Sequence[complex],
        *,
        gauss_order: int = 4,
    ) -> dict[str, float | int]:
        """Integrate middle material loss with composite Gauss-Legendre in z."""

        if gauss_order < 2:
            raise ValueError("At least second-order Gauss quadrature is required.")
        axis = np.asarray(self.cross_section.axis_plan.z_values, dtype=np.float64)
        interior = axis[
            (axis > self.bottom_z_nm + 1.0e-12)
            & (axis < self.top_z_nm - 1.0e-12)
        ]
        breaks = np.concatenate(([self.bottom_z_nm], interior, [self.top_z_nm]))
        nodes, weights = np.polynomial.legendre.leggauss(int(gauss_order))
        local_integral = 0.0
        evaluations = 0
        for start, stop in zip(breaks[:-1], breaks[1:]):
            half = 0.5 * (stop - start)
            center = 0.5 * (stop + start)
            for node, weight in zip(nodes, weights):
                z_value = center + half * node
                coefficients = self.coefficients_at_z(modal_amplitudes, z_value)
                self._total.x.petsc_vec.set(0.0)
                for coefficient, mode in zip(coefficients, self._modes):
                    self._total.x.petsc_vec.axpy(
                        PETSc.ScalarType(coefficient), mode.right.right_full
                    )
                self._total.x.scatter_forward()
                cross_section_power = complex(fem.assemble_scalar(self._absorption_form))
                local_integral += half * float(weight) * float(cross_section_power.real)
                evaluations += 1
        total = float(
            self.cross_section.mesh.comm.allreduce(local_integral, op=MPI.SUM)
        )
        return {
            "absorbed_power_code_units": max(total, 0.0),
            "z_cell_count": int(len(breaks) - 1),
            "gauss_order_per_z_cell": int(gauss_order),
            "z_evaluation_count": int(evaluations),
        }


def interface_field_continuity(
    cfg: SimulationConfig3D,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    bottom_solution: PETSc.Vec,
    top_solution: PETSc.Vec,
    modal_samples: ModalPlaneSamples,
) -> dict[str, object]:
    """Compare local-FEM and modal one-sided physical traces on both interfaces."""

    if modal_samples.z_nm.shape != (2,) or not np.allclose(
        modal_samples.z_nm,
        [bottom_system.local_mesh.interface_z_nm, top_system.local_mesh.interface_z_nm],
    ):
        raise ValueError("Interface continuity requires modal samples at bottom and top interfaces.")
    yy, xx = np.meshgrid(modal_samples.y_nm, modal_samples.x_nm, indexing="ij")
    reports: dict[str, object] = {}
    for index, (side, system, vector, z_side) in enumerate(
        (
            ("bottom", bottom_system, bottom_solution, -1),
            ("top", top_system, top_solution, +1),
        )
    ):
        z_value = system.local_mesh.interface_z_nm
        points = np.column_stack(
            (xx.ravel(), yy.ravel(), np.full(xx.size, z_value, dtype=np.float64))
        )
        selectors = np.full(len(points), z_side, dtype=np.int8)
        electric = assign_local_total_electric_field(system, vector)
        magnetic = local_magnetic_field_A_per_m(cfg, electric)
        local_e = (
            cfg.electric_field_scale_V_per_m
            * _sample_distributed_function(electric, points, selectors)
        ).reshape((len(modal_samples.y_nm), len(modal_samples.x_nm), 3))
        local_h = _sample_distributed_function(magnetic, points, selectors).reshape(
            (len(modal_samples.y_nm), len(modal_samples.x_nm), 3)
        )
        modal_e = modal_samples.electric_V_per_m[index]
        modal_h = modal_samples.magnetic_A_per_m[index]
        reports[side] = {
            "local_trace_side": "negative_z" if z_side < 0 else "positive_z",
            "modal_trace_side": "positive_z" if side == "bottom" else "negative_z",
            "electric_tangential": relative_sample_error(local_e[..., :2], modal_e[..., :2]),
            "magnetic_tangential": relative_sample_error(local_h[..., :2], modal_h[..., :2]),
        }
    return reports


def hybrid_volume_absorption(
    cfg: SimulationConfig3D,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    bottom_solution: PETSc.Vec,
    top_solution: PETSc.Vec,
    reconstructor: ModalFieldReconstructor,
    modal_amplitudes: Sequence[complex],
    *,
    incident_power: float,
    gauss_order: int = 4,
) -> dict[str, object]:
    """Combine both local FEM material losses with the modal middle loss."""

    if incident_power <= 0.0:
        raise ValueError("Incident power must be positive.")
    local_payload: dict[str, object] = {}
    local_total = 0.0
    for side, system, vector in (
        ("bottom", bottom_system, bottom_solution),
        ("top", top_system, top_solution),
    ):
        electric = assign_local_total_electric_field(system, vector)
        grating = _region_absorbed_power(
            system.local_mesh.mesh_data,
            cfg,
            electric,
            cfg.tags.grating,
            cfg.eps_grating,
        )
        substrate = _region_absorbed_power(
            system.local_mesh.mesh_data,
            cfg,
            electric,
            cfg.tags.substrate,
            cfg.eps_substrate,
        )
        subtotal = float(grating + substrate)
        local_total += subtotal
        local_payload[side] = {
            "grating_absorbed_power_code_units": float(grating),
            "substrate_absorbed_power_code_units": float(substrate),
            "total_absorbed_power_code_units": subtotal,
        }
    middle = reconstructor.absorbed_power_code_units(
        modal_amplitudes, gauss_order=gauss_order
    )
    middle_power = float(middle["absorbed_power_code_units"])
    total = float(local_total + middle_power)
    return {
        "method": "local_FEM_volume_plus_middle_modal_selected_z_quadrature",
        "formula_code_units": "integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV",
        "incident_power_code_units": float(incident_power),
        "local_regions": local_payload,
        "middle_modal_region": middle,
        "absorbed_power_code_units": total,
        "A_volume_total": float(total / incident_power),
    }


def compare_selected_planes_to_reference(
    modal_samples: ModalPlaneSamples,
    reference_npz: Path,
) -> dict[str, object]:
    """Compare a bounded modal reconstruction with the pinned full-3D archive."""

    with np.load(reference_npz) as archive:
        x_ref = np.asarray(archive["x_nm"], dtype=np.float64)
        y_ref = np.asarray(archive["y_nm"], dtype=np.float64)
        z_ref = np.asarray(archive["z_nm"], dtype=np.float64)
        electric_ref = np.asarray(archive["E_V_per_m"], dtype=np.complex128)
        magnetic_ref = np.asarray(archive["H_A_per_m"], dtype=np.complex128)
    if not (
        np.allclose(modal_samples.x_nm, x_ref)
        and np.allclose(modal_samples.y_nm, y_ref)
        and np.allclose(modal_samples.z_nm, z_ref)
    ):
        raise ValueError("Modal and full-3D selected-plane grids differ.")
    planes = []
    for index, z_value in enumerate(z_ref):
        planes.append(
            {
                "z_nm": float(z_value),
                "electric": relative_sample_error(
                    modal_samples.electric_V_per_m[index], electric_ref[index]
                ),
                "magnetic": relative_sample_error(
                    modal_samples.magnetic_A_per_m[index], magnetic_ref[index]
                ),
                "electric_tangential": relative_sample_error(
                    modal_samples.electric_V_per_m[index, ..., :2],
                    electric_ref[index, ..., :2],
                ),
                "magnetic_tangential": relative_sample_error(
                    modal_samples.magnetic_A_per_m[index, ..., :2],
                    magnetic_ref[index, ..., :2],
                ),
            }
        )
    return {
        "reference_npz": str(reference_npz),
        "sample_shape_z_y_x_component": list(electric_ref.shape),
        "planes": planes,
        "max_middle_plane_electric_relative_l2": max(
            plane["electric"]["relative_l2"] for plane in planes[1:-1]
        ),
        "max_middle_plane_magnetic_relative_l2": max(
            plane["magnetic"]["relative_l2"] for plane in planes[1:-1]
        ),
    }
