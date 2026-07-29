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
from ..coupling.hybrid_internal_modes import (
    HybridInternalModeCoupling,
    _ReusableInterfaceLifter,
    _ReusableModeTractionEvaluator,
)
from ..modes.cross_section_spaces import CrossSectionMesh, CrossSectionSpaces
from ..modes.mode_classification import BiorthogonalModeBasis
from ..modes.stable_propagation import TwoSidedPropagation
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
    augmented_solution,
):
    """Back-substitute one local MPC solution into its physical H(curl) field."""

    if isinstance(augmented_solution, fem.Function):
        if augmented_solution.function_space.mesh is not system.V.mesh:
            raise ValueError(
                "Recovered Hybrid field belongs to a different local mesh."
            )
        return augmented_solution
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
        propagation: TwoSidedPropagation | None = None,
        positive_traction_beta_per_nm: Sequence[complex] | None = None,
        negative_traction_beta_per_nm: Sequence[complex] | None = None,
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
        if propagation is None:
            self.propagation_model = "continuous_beta"
            self._positive_propagation_beta = np.asarray(
                [mode.beta for mode in positive.modes],
                dtype=np.complex128,
            )
            self._negative_propagation_beta = np.asarray(
                [mode.beta for mode in negative.modes],
                dtype=np.complex128,
            )
        else:
            count = len(positive.modes)
            if (
                propagation.forward.mode_count != count
                or propagation.backward.mode_count != count
            ):
                raise ValueError(
                    "Propagation and modal reconstruction sizes differ."
                )
            self.propagation_model = propagation.propagation_model
            self._positive_propagation_beta = np.asarray(
                propagation.forward.effective_beta_per_nm,
                dtype=np.complex128,
            )
            self._negative_propagation_beta = np.asarray(
                propagation.backward.effective_beta_per_nm,
                dtype=np.complex128,
            )
        if (positive_traction_beta_per_nm is None) != (
            negative_traction_beta_per_nm is None
        ):
            raise ValueError(
                "Positive and negative traction betas must be supplied together."
            )
        if positive_traction_beta_per_nm is None:
            self.traction_model = "continuous_qep_beta"
            self._positive_traction_beta = np.asarray(
                [mode.beta for mode in positive.modes], dtype=np.complex128
            )
            self._negative_traction_beta = np.asarray(
                [mode.beta for mode in negative.modes], dtype=np.complex128
            )
        else:
            self.traction_model = "selected_coupling_traction_beta"
            self._positive_traction_beta = np.asarray(
                positive_traction_beta_per_nm, dtype=np.complex128
            )
            self._negative_traction_beta = np.asarray(
                negative_traction_beta_per_nm, dtype=np.complex128
            )
            count = len(positive.modes)
            if self._positive_traction_beta.shape != (count,) or (
                self._negative_traction_beta.shape != (count,)
            ):
                raise ValueError(
                    "Traction beta arrays must match each directional modal basis."
                )
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
        self._magnetic_total = fem.Function(
            self._magnetic_space, name="task001_middle_modal_H_total_A_per_m"
        )
        self._total = fem.Function(spaces.mixed, name="task032_middle_modal_E_total")
        Et, Ez = ufl.split(self._total)
        middle_power_density = 0.5 * (
            Et[0] * ufl.conj(self._magnetic_total[1])
            - Et[1] * ufl.conj(self._magnetic_total[0])
        ) / float(cfg.magnetic_field_scale_A_per_m)
        self._middle_power_form = fem.form(middle_power_density * ufl.dx)
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

    def _effective_propagation_betas(
        self,
    ) -> tuple[np.ndarray, np.ndarray]:
        positive = getattr(self, "_positive_propagation_beta", None)
        negative = getattr(self, "_negative_propagation_beta", None)
        if positive is None:
            positive = np.asarray(
                [mode.beta for mode in self.positive.modes],
                dtype=np.complex128,
            )
        if negative is None:
            negative = np.asarray(
                [mode.beta for mode in self.negative.modes],
                dtype=np.complex128,
            )
        return (
            np.asarray(positive, dtype=np.complex128),
            np.asarray(negative, dtype=np.complex128),
        )

    def _effective_traction_betas(self) -> tuple[np.ndarray, np.ndarray]:
        positive = getattr(self, "_positive_traction_beta", None)
        negative = getattr(self, "_negative_traction_beta", None)
        if positive is None:
            positive = np.asarray(
                [mode.beta for mode in self.positive.modes],
                dtype=np.complex128,
            )
        if negative is None:
            negative = np.asarray(
                [mode.beta for mode in self.negative.modes],
                dtype=np.complex128,
            )
        return (
            np.asarray(positive, dtype=np.complex128),
            np.asarray(negative, dtype=np.complex128),
        )

    def _sample_mode_bases(
        self, points: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        electric_rows = []
        magnetic_rows = []
        positive_traction_beta, negative_traction_beta = (
            self._effective_traction_betas()
        )
        magnetic_betas = np.concatenate(
            (positive_traction_beta, negative_traction_beta)
        )
        for mode, magnetic_beta in zip(self._modes, magnetic_betas):
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
                self._magnetic_beta.value[...] = PETSc.ScalarType(magnetic_beta)
            except Exception:
                self._magnetic_beta.value = PETSc.ScalarType(magnetic_beta)
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
        positive_beta, negative_beta = self._effective_propagation_betas()
        return np.concatenate(
            (
                modal[:count]
                * np.exp(
                    1j
                    * positive_beta
                    * (float(z_nm) - self.bottom_z_nm)
                ),
                modal[count:]
                * np.exp(
                    1j
                    * negative_beta
                    * (float(z_nm) - self.top_z_nm)
                ),
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

    def full3d_trace_modal_oracle(
        self,
        reference_npz: Path,
    ) -> dict[str, object]:
        """Project both Full3D interface traces onto one sampled modal basis.

        Electric-only projection cannot distinguish counter-propagating modes
        that share a tangential trace.  The joint normalized E/H fit resolves
        both directions and lets us compare continuous and selected propagation
        independently of the local Hybrid solve.
        """

        with np.load(reference_npz) as archive:
            x_nm = np.asarray(archive["x_nm"], dtype=np.float64)
            y_nm = np.asarray(archive["y_nm"], dtype=np.float64)
            z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
            electric = np.asarray(
                archive["E_V_per_m"],
                dtype=np.complex128,
            )
            magnetic = np.asarray(
                archive["H_A_per_m"],
                dtype=np.complex128,
            )
        bottom_matches = np.flatnonzero(
            np.isclose(z_nm, self.bottom_z_nm, rtol=0.0, atol=1.0e-10)
        )
        top_matches = np.flatnonzero(
            np.isclose(z_nm, self.top_z_nm, rtol=0.0, atol=1.0e-10)
        )
        if len(bottom_matches) != 1 or len(top_matches) != 1:
            raise ValueError(
                "Full3D trace oracle requires exactly one sample plane at "
                "each Hybrid interface."
            )
        yy, xx = np.meshgrid(y_nm, x_nm, indexing="ij")
        points = np.column_stack((xx.ravel(), yy.ravel()))
        electric_basis, magnetic_basis = self._sample_mode_bases(points)
        electric_basis = (
            self.cfg.electric_field_scale_V_per_m
            * electric_basis[..., :2]
        )
        magnetic_basis = magnetic_basis[..., :2]
        electric_matrix = electric_basis.reshape(
            len(electric_basis), -1
        ).T
        magnetic_matrix = magnetic_basis.reshape(
            len(magnetic_basis), -1
        ).T
        interface_indices = {
            "bottom": int(bottom_matches[0]),
            "top": int(top_matches[0]),
        }

        def fit(index: int) -> tuple[np.ndarray, dict[str, object]]:
            electric_target = electric[index, ..., :2].reshape(-1)
            magnetic_target = magnetic[index, ..., :2].reshape(-1)
            electric_scale = max(
                float(np.linalg.norm(electric_target)),
                1.0e-30,
            )
            magnetic_scale = max(
                float(np.linalg.norm(magnetic_target)),
                1.0e-30,
            )
            joint_matrix = np.vstack(
                (
                    electric_matrix / electric_scale,
                    magnetic_matrix / magnetic_scale,
                )
            )
            joint_target = np.concatenate(
                (
                    electric_target / electric_scale,
                    magnetic_target / magnetic_scale,
                )
            )
            coefficients, _residuals, rank, singular_values = np.linalg.lstsq(
                joint_matrix,
                joint_target,
                rcond=1.0e-10,
            )
            reconstructed_electric = (
                electric_matrix @ coefficients
            ).reshape(electric[index, ..., :2].shape)
            reconstructed_magnetic = (
                magnetic_matrix @ coefficients
            ).reshape(magnetic[index, ..., :2].shape)
            condition = (
                float(singular_values[0] / singular_values[-1])
                if len(singular_values) and singular_values[-1] > 0.0
                else float("inf")
            )
            return coefficients, {
                "joint_fit_rank": int(rank),
                "joint_fit_columns": int(joint_matrix.shape[1]),
                "joint_fit_condition": condition,
                "electric_tangential": relative_sample_error(
                    reconstructed_electric,
                    electric[index, ..., :2],
                ),
                "magnetic_tangential": relative_sample_error(
                    reconstructed_magnetic,
                    magnetic[index, ..., :2],
                ),
                "coefficient_l2": float(np.linalg.norm(coefficients)),
            }

        comm = self.cross_section.mesh.comm
        payload = None
        if comm.rank == 0:
            bottom_coefficients, bottom_fit = fit(
                interface_indices["bottom"]
            )
            top_coefficients, top_fit = fit(interface_indices["top"])
            original_beta = np.asarray(
                [mode.beta for mode in self._modes],
                dtype=np.complex128,
            )
            positive_beta, negative_beta = (
                self._effective_propagation_betas()
            )
            effective_beta = np.concatenate(
                (
                    positive_beta,
                    negative_beta,
                )
            )
            length_nm = self.top_z_nm - self.bottom_z_nm
            count = self.mode_count_per_direction
            forward_factors = np.exp(
                1j * original_beta[:count] * length_nm
            )
            backward_factors = np.exp(
                -1j * original_beta[count:] * length_nm
            )
            predicted_top_forward = (
                bottom_coefficients[:count] * forward_factors
            )
            predicted_bottom_backward = (
                top_coefficients[count:] * backward_factors
            )
            stable_top_coefficients = np.concatenate(
                (predicted_top_forward, top_coefficients[count:])
            )
            stable_bottom_coefficients = np.concatenate(
                (bottom_coefficients[:count], predicted_bottom_backward)
            )
            predicted_top_electric = (
                electric_matrix @ stable_top_coefficients
            ).reshape(electric[interface_indices["top"], ..., :2].shape)
            predicted_top_magnetic = (
                magnetic_matrix @ stable_top_coefficients
            ).reshape(magnetic[interface_indices["top"], ..., :2].shape)
            predicted_bottom_electric = (
                electric_matrix @ stable_bottom_coefficients
            ).reshape(electric[interface_indices["bottom"], ..., :2].shape)
            predicted_bottom_magnetic = (
                magnetic_matrix @ stable_bottom_coefficients
            ).reshape(magnetic[interface_indices["bottom"], ..., :2].shape)

            def coefficient_error(
                predicted: np.ndarray,
                observed: np.ndarray,
            ) -> float:
                scale = max(
                    float(np.linalg.norm(predicted)),
                    float(np.linalg.norm(observed)),
                    1.0e-30,
                )
                return float(np.linalg.norm(predicted - observed) / scale)

            def largest_mode_diagnostics(
                predicted: np.ndarray,
                observed: np.ndarray,
                mode_beta: np.ndarray,
                *,
                direction: str,
                offset: int,
            ) -> list[dict[str, object]]:
                significant = np.argsort(
                    np.maximum(np.abs(predicted), np.abs(observed))
                )[-12:][::-1]
                diagnostics = []
                for local_index in significant:
                    predicted_value = predicted[int(local_index)]
                    observed_value = observed[int(local_index)]
                    diagnostics.append(
                        {
                            "mode_index": int(offset + local_index),
                            "direction": direction,
                            "beta_per_nm": [
                                float(mode_beta[local_index].real),
                                float(mode_beta[local_index].imag),
                            ],
                            "predicted_coefficient_abs": float(
                                abs(predicted_value)
                            ),
                            "projected_coefficient_abs": float(
                                abs(observed_value)
                            ),
                            "phase_delta_rad": float(
                                np.angle(observed_value / predicted_value)
                                if abs(predicted_value) > 1.0e-30
                                else np.nan
                            ),
                        }
                    )
                return diagnostics

            forward_report = {
                "coefficient_relative_l2": coefficient_error(
                    predicted_top_forward,
                    top_coefficients[:count],
                ),
                "largest_projected_modes": largest_mode_diagnostics(
                    predicted_top_forward,
                    top_coefficients[:count],
                    original_beta[:count],
                    direction="forward",
                    offset=0,
                ),
            }
            backward_report = {
                "coefficient_relative_l2": coefficient_error(
                    predicted_bottom_backward,
                    bottom_coefficients[count:],
                ),
                "largest_projected_modes": largest_mode_diagnostics(
                    predicted_bottom_backward,
                    bottom_coefficients[count:],
                    original_beta[count:],
                    direction="backward",
                    offset=count,
                ),
            }
            max_stable_factor = max(
                float(np.max(np.abs(forward_factors), initial=0.0)),
                float(np.max(np.abs(backward_factors), initial=0.0)),
                1.0e-30,
            )
            selected_forward_factors = np.exp(
                1j * effective_beta[:count] * length_nm
            )
            selected_backward_factors = np.exp(
                -1j * effective_beta[count:] * length_nm
            )
            selected_top_forward = (
                bottom_coefficients[:count] * selected_forward_factors
            )
            selected_bottom_backward = (
                top_coefficients[count:] * selected_backward_factors
            )
            selected_top_coefficients = np.concatenate(
                (selected_top_forward, top_coefficients[count:])
            )
            selected_bottom_coefficients = np.concatenate(
                (bottom_coefficients[:count], selected_bottom_backward)
            )
            selected_top_electric = (
                electric_matrix @ selected_top_coefficients
            ).reshape(electric[interface_indices["top"], ..., :2].shape)
            selected_top_magnetic = (
                magnetic_matrix @ selected_top_coefficients
            ).reshape(magnetic[interface_indices["top"], ..., :2].shape)
            selected_bottom_electric = (
                electric_matrix @ selected_bottom_coefficients
            ).reshape(electric[interface_indices["bottom"], ..., :2].shape)
            selected_bottom_magnetic = (
                magnetic_matrix @ selected_bottom_coefficients
            ).reshape(magnetic[interface_indices["bottom"], ..., :2].shape)
            selected_propagation = {
                "length_nm": float(length_nm),
                "forward_bottom_to_top": {
                    "coefficient_relative_l2": coefficient_error(
                        selected_top_forward,
                        top_coefficients[:count],
                    ),
                    "largest_projected_modes": largest_mode_diagnostics(
                        selected_top_forward,
                        top_coefficients[:count],
                        effective_beta[:count],
                        direction="forward",
                        offset=0,
                    ),
                },
                "backward_top_to_bottom": {
                    "coefficient_relative_l2": coefficient_error(
                        selected_bottom_backward,
                        bottom_coefficients[count:],
                    ),
                    "largest_projected_modes": largest_mode_diagnostics(
                        selected_bottom_backward,
                        bottom_coefficients[count:],
                        effective_beta[count:],
                        direction="backward",
                        offset=count,
                    ),
                },
                "stable_two_sided_reconstruction": {
                    "top_electric_tangential": relative_sample_error(
                        selected_top_electric,
                        electric[interface_indices["top"], ..., :2],
                    ),
                    "top_magnetic_tangential": relative_sample_error(
                        selected_top_magnetic,
                        magnetic[interface_indices["top"], ..., :2],
                    ),
                    "bottom_electric_tangential": relative_sample_error(
                        selected_bottom_electric,
                        electric[interface_indices["bottom"], ..., :2],
                    ),
                    "bottom_magnetic_tangential": relative_sample_error(
                        selected_bottom_magnetic,
                        magnetic[interface_indices["bottom"], ..., :2],
                    ),
                },
                "max_stable_factor_magnitude": max(
                    float(
                        np.max(np.abs(selected_forward_factors), initial=0.0)
                    ),
                    float(
                        np.max(np.abs(selected_backward_factors), initial=0.0)
                    ),
                    1.0e-30,
                ),
                "diagnostic_uses_growing_inverse_factors": False,
            }
            payload = {
                "schema_version": (
                    "task035c.sampled-full3d-trace-modal-oracle.v2"
                ),
                "status": "measured_sampled_oracle",
                "reference_npz": str(reference_npz),
                "sample_grid_shape_y_x": [len(y_nm), len(x_nm)],
                "mode_count_per_direction": self.mode_count_per_direction,
                "fit_uses_joint_normalized_tangential_E_H": True,
                "interfaces": {
                    "bottom": bottom_fit,
                    "top": top_fit,
                },
                "continuous_propagation": {
                    "length_nm": float(length_nm),
                    "forward_bottom_to_top": forward_report,
                    "backward_top_to_bottom": backward_report,
                    "stable_two_sided_reconstruction": {
                        "top_electric_tangential": relative_sample_error(
                            predicted_top_electric,
                            electric[interface_indices["top"], ..., :2],
                        ),
                        "top_magnetic_tangential": relative_sample_error(
                            predicted_top_magnetic,
                            magnetic[interface_indices["top"], ..., :2],
                        ),
                        "bottom_electric_tangential": relative_sample_error(
                            predicted_bottom_electric,
                            electric[interface_indices["bottom"], ..., :2],
                        ),
                        "bottom_magnetic_tangential": relative_sample_error(
                            predicted_bottom_magnetic,
                            magnetic[interface_indices["bottom"], ..., :2],
                        ),
                    },
                    "max_stable_factor_magnitude": max_stable_factor,
                    "diagnostic_uses_growing_inverse_factors": False,
                },
                "selected_propagation_model": getattr(
                    self, "propagation_model", "continuous_beta"
                ),
                "selected_propagation": selected_propagation,
                "authority_boundary": (
                    "bounded 40x20 sampled interface oracle; not an exact "
                    "FE mass/Riesz projection"
                ),
            }
        return comm.bcast(payload, root=0)

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
        bottom_flux = self.cross_section_power_code_units(
            modal_amplitudes, self.bottom_z_nm
        )
        top_flux = self.cross_section_power_code_units(
            modal_amplitudes, self.top_z_nm
        )
        flux_loss = float(bottom_flux - top_flux)
        return {
            "absorbed_power_code_units": max(total, 0.0),
            "z_cell_count": int(len(breaks) - 1),
            "gauss_order_per_z_cell": int(gauss_order),
            "z_evaluation_count": int(evaluations),
            "bottom_positive_z_power_code_units": float(bottom_flux),
            "top_positive_z_power_code_units": float(top_flux),
            "poynting_flux_loss_code_units": flux_loss,
            "volume_minus_poynting_flux_loss_code_units": float(total - flux_loss),
        }

    def cross_section_power_code_units(
        self,
        modal_amplitudes: Sequence[complex],
        z_nm: float,
    ) -> float:
        """Assemble the total modal positive-z Poynting flux on one plane."""

        coefficients = self.coefficients_at_z(modal_amplitudes, float(z_nm))
        positive_beta, negative_beta = self._effective_traction_betas()
        magnetic_betas = np.concatenate((positive_beta, negative_beta))
        self._total.x.petsc_vec.set(0.0)
        self._magnetic_total.x.petsc_vec.set(0.0)
        for coefficient, mode, beta in zip(
            coefficients, self._modes, magnetic_betas
        ):
            self._total.x.petsc_vec.axpy(
                PETSc.ScalarType(coefficient), mode.right.right_full
            )
            mode.right.right_full.copy(self._sample_source.x.petsc_vec)
            self._sample_source.x.scatter_forward()
            try:
                self._magnetic_beta.value[...] = PETSc.ScalarType(beta)
            except Exception:
                self._magnetic_beta.value = PETSc.ScalarType(beta)
            self._magnetic_scratch.interpolate(self._magnetic_expression)
            self._magnetic_scratch.x.scatter_forward()
            self._magnetic_total.x.petsc_vec.axpy(
                PETSc.ScalarType(coefficient),
                self._magnetic_scratch.x.petsc_vec,
            )
        self._total.x.scatter_forward()
        self._magnetic_total.x.scatter_forward()
        local = complex(fem.assemble_scalar(self._middle_power_form))
        total = complex(
            self.cross_section.mesh.comm.allreduce(local, op=MPI.SUM)
        )
        return float(total.real)


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


def _assembled_surface_relative_error(
    system: HybridLocalDtnSystem,
    actual,
    expected,
    *,
    quadrature_degree: int,
) -> dict[str, object]:
    """Return an MPI-global interface mass norm without point sampling."""

    ds = ufl.Measure(
        "ds",
        domain=system.local_mesh.mesh,
        subdomain_data=system.local_mesh.mesh_data.facet_tags,
        metadata={"quadrature_degree": int(quadrature_degree)},
    )
    measure = ds(system.local_mesh.interface_facet_tag)
    options = {"quadrature_degree": int(quadrature_degree)}
    comm = system.local_mesh.mesh.comm

    def norm(values) -> float:
        form = fem.form(ufl.inner(values, values) * measure, form_compiler_options=options)
        local = complex(fem.assemble_scalar(form))
        total = complex(comm.allreduce(local, op=MPI.SUM))
        return float(np.sqrt(max(total.real, 0.0)))

    difference = actual - expected
    actual_l2 = norm(actual)
    expected_l2 = norm(expected)
    absolute_l2 = norm(difference)
    scale = max(actual_l2, expected_l2, 1.0e-30)
    component_absolute_l2 = [
        norm(ufl.as_vector((difference[index],))) for index in range(2)
    ]
    return {
        "absolute_l2": absolute_l2,
        "actual_l2": actual_l2,
        "expected_l2": expected_l2,
        "comparison_scale_l2": scale,
        "relative_l2": float(absolute_l2 / scale),
        "component_absolute_l2": component_absolute_l2,
    }


def assembled_interface_field_continuity(
    cfg: SimulationConfig3D,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    bottom_solution,
    top_solution,
    coupling: HybridInternalModeCoupling,
    modal_amplitudes: Sequence[complex],
) -> dict[str, object]:
    """Compare exact assembled E-trace and traction densities at each interface.

    The diagnostic uses the same modal coefficients, discrete propagation
    factors, selected traction symbols, lifted coefficient space and surface
    quadrature as the coupling.  It is independent of the sampled interface
    grid and of one-sided point-location choices.
    """

    count = coupling.mode_count_per_direction
    modal = np.asarray(modal_amplitudes, dtype=np.complex128)
    if modal.shape != (2 * count,):
        raise ValueError("Modal amplitudes have the wrong assembled-trace shape.")
    forward = np.asarray(coupling.propagation.forward.factors, dtype=np.complex128)
    backward = np.asarray(coupling.propagation.backward.factors, dtype=np.complex128)
    coefficient_sets = {
        "bottom": np.concatenate((modal[:count], backward * modal[count:])),
        "top": np.concatenate((forward * modal[:count], modal[count:])),
    }
    modes = (*coupling.positive_basis.modes, *coupling.negative_basis.modes)
    traction_betas = (
        *coupling.positive_traction_beta_per_nm,
        *coupling.negative_traction_beta_per_nm,
    )
    reports: dict[str, object] = {
        "schema_version": "myfenics.hybrid-assembled-interface.v2",
        "method": "surface_mass_E_and_separate_raw_traction_density_proxy",
        "quadrature_degree": int(coupling.interface_quadrature_degree),
        "lifted_coefficient_degree": int(
            coupling.interface_quadrature_coefficient_degree
        ),
        "propagation_model": coupling.propagation.propagation_model,
        "traction_model": coupling.modal_traction_model,
    }
    for side, system, solution in (
        ("bottom", bottom_system, bottom_solution),
        ("top", top_system, top_solution),
    ):
        coefficients = coefficient_sets[side]
        mixed_total = fem.Function(coupling.spaces.mixed)
        mixed_total.x.petsc_vec.set(0.0)
        for coefficient, mode in zip(coefficients, modes):
            mixed_total.x.petsc_vec.axpy(
                PETSc.ScalarType(coefficient), mode.right.right_full
            )
        mixed_total.x.scatter_forward()
        transverse_total = fem.Function(coupling.spaces.transverse)
        transverse_total.x.array[:] = mixed_total.x.array[
            coupling.spaces.transverse_to_mixed
        ]
        transverse_total.x.scatter_forward()
        electric_lifter = _ReusableInterfaceLifter(system, target_space=system.V)
        modal_electric, _queries = electric_lifter.lift(transverse_total)
        local_electric = assign_local_total_electric_field(system, solution)

        traction_evaluator = _ReusableModeTractionEvaluator(coupling.spaces)
        traction_total = fem.Function(traction_evaluator.traction_space)
        traction_total.x.petsc_vec.set(0.0)
        normal_sign = system.local_mesh.local_interface_outward_normal_sign
        for coefficient, mode, beta in zip(coefficients, modes, traction_betas):
            traction = traction_evaluator.evaluate(
                mode,
                local_outward_normal_sign=normal_sign,
                beta_override=beta,
            )
            traction_total.x.petsc_vec.axpy(
                PETSc.ScalarType(coefficient), traction.x.petsc_vec
            )
        traction_total.x.scatter_forward()
        modal_traction, _queries = _ReusableInterfaceLifter(system).lift(
            traction_total
        )
        normal = ufl.as_vector((0.0, 0.0, float(normal_sign)))
        local_traction = ufl.cross(ufl.curl(local_electric), normal)
        reports[side] = {
            "electric_tangential": _assembled_surface_relative_error(
                system,
                ufl.as_vector((local_electric[0], local_electric[1])),
                ufl.as_vector((modal_electric[0], modal_electric[1])),
                quadrature_degree=coupling.interface_quadrature_degree,
            ),
            "traction_density_l2_proxy": _assembled_surface_relative_error(
                system,
                ufl.as_vector((local_traction[0], local_traction[1])),
                ufl.as_vector((modal_traction[0], modal_traction[1])),
                quadrature_degree=coupling.interface_quadrature_degree,
            ),
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

    def outward_surface_power(system, electric, facet_tag: int) -> float:
        normal = ufl.FacetNormal(system.local_mesh.mesh)
        magnetic = ufl.curl(electric) / (1j * cfg.k0 * complex(cfg.mu_r))
        density = 0.5 * ufl.real(
            ufl.dot(ufl.cross(electric, ufl.conj(magnetic)), normal)
        )
        ds = ufl.Measure(
            "ds", domain=system.local_mesh.mesh,
            subdomain_data=system.local_mesh.mesh_data.facet_tags,
            metadata={"quadrature_degree": 2 * int(system.cfg.nedelec_degree) + 4},
        )
        local = complex(fem.assemble_scalar(fem.form(density * ds(facet_tag))))
        return float(system.local_mesh.mesh.comm.allreduce(local, op=MPI.SUM).real)

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
        external_flux = outward_surface_power(
            system, electric, system.local_mesh.external_facet_tag,
        )
        interface_flux = outward_surface_power(
            system, electric, system.local_mesh.interface_facet_tag,
        )
        local_total += subtotal
        local_payload[side] = {
            "grating_absorbed_power_code_units": float(grating),
            "substrate_absorbed_power_code_units": float(substrate),
            "total_absorbed_power_code_units": subtotal,
            "external_outward_poynting_flux_code_units": external_flux,
            "interface_outward_poynting_flux_code_units": interface_flux,
            "discrete_balance_residual_code_units": float(
                external_flux + interface_flux + subtotal
            ),
            "discrete_balance_residual_over_incident_power": float(
                (external_flux + interface_flux + subtotal) / incident_power
            ),
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
