"""The fixed V5 BAL_H positive smoother, without the surrounding research routes."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx import fem
from petsc4py import PETSc

from .physical_balanced_mpc_action import FullspaceMpcFormAction
from .physical_balanced_physical_operator import (
    _payload_array_inventory,
    _payload_vector_inventory,
)
from .physical_balanced_positive_kernel import (
    IsotropicPartialAssembly,
    build_quadrature_positive_diagonal,
    same_mesh_positive_form,
)

H6_DEGREE = 3
POWER_STEPS = 10
LAMBDA_HI_FACTOR = 1.10
LAMBDA_LO_FACTOR = 0.10
_MPC_TOLERANCE = 1.0e-12


def _fixed_random_field(coordinates: np.ndarray, cfg: Any) -> np.ndarray:
    """Donor V5 deterministic triangular trigonometric seed."""

    x, y, z = np.asarray(coordinates, dtype=np.float64)
    sx = (x - float(cfg.x_min)) / (float(cfg.x_max) - float(cfg.x_min))
    sy = (y - float(cfg.y_min)) / (float(cfg.y_max) - float(cfg.y_min))
    sz = (z - float(cfg.domain_z_min)) / (
        float(cfg.domain_z_max) - float(cfg.domain_z_min)
    )
    pi = np.pi
    return np.vstack(
        (
            np.sin(2.0 * pi * (1.37 * sx + 0.23))
            * np.cos(2.0 * pi * (0.73 * sy + 0.11))
            * np.sin(2.0 * pi * (1.19 * sz + 0.37)),
            np.cos(2.0 * pi * (0.91 * sx + 0.07))
            * np.sin(2.0 * pi * (1.41 * sy + 0.29))
            * np.cos(2.0 * pi * (0.67 * sz + 0.19)),
            np.sin(2.0 * pi * (1.23 * sx + 0.31))
            * np.sin(2.0 * pi * (0.83 * sy + 0.17))
            * np.cos(2.0 * pi * (1.07 * sz + 0.41)),
        )
    ).astype(np.complex128)


def build_fixed_random_seed(
    space: Any,
    floquet_data: Any,
    cfg: Any,
) -> tuple[PETSc.Vec, dict[str, object]]:
    """Interpolate the fixed analytic seed and zero finalized MPC slaves."""

    mpc = floquet_data.mpc
    if mpc.function_space.mesh is not space.mesh:
        raise ValueError("BAL_H seed and MPC meshes must match")
    field = fem.Function(mpc.function_space)
    field.interpolate(lambda coordinates: _fixed_random_field(coordinates, cfg))
    field.x.scatter_forward()
    mpc.homogenize(field)
    field.x.scatter_forward()
    result = field.x.petsc_vec.copy()
    local_sha = hashlib.sha256(
        np.asarray(result.getArray(readonly=True), dtype=np.complex128).tobytes()
    ).hexdigest()
    del field
    return result, {
        "name": "random",
        "formula": "V5 fixed noninteger trigonometric triangular field",
        "coordinate_normalization": "cfg x/y/domain-z model boundaries",
        "mpc_slave_state": "homogenize then forward scatter",
        "seed_sha256_local": local_sha,
    }


def build_positive_material_coefficients(
    side_system: Any,
) -> tuple[fem.Function, fem.Function, dict[str, object]]:
    """Build positive DG0 coefficients by explicit owned-cell DoF mapping."""

    cfg = side_system.cfg
    local_mesh = side_system.local_mesh
    mesh = local_mesh.mesh
    if bool(cfg.use_pml):
        raise NotImplementedError("BAL_H side coefficients require the no-PML side path")
    if side_system.V.mesh is not mesh:
        raise ValueError("BAL_H p6 space and side mesh must be identical")

    coefficient_space = fem.functionspace(mesh, ("DG", 0))
    mu = fem.Function(coefficient_space, name="bal_h_abs_inv_mu")
    mass = fem.Function(coefficient_space, name="bal_h_k0_squared_abs_eps")
    mu_value = abs(1.0 / complex(cfg.mu_r))
    epsilon_by_tag = {
        int(cfg.tags.air): complex(cfg.eps_air),
        int(cfg.tags.substrate): complex(cfg.eps_substrate),
        int(cfg.tags.grating): complex(cfg.eps_grating),
    }
    if not np.isfinite(mu_value) or mu_value <= 0.0:
        raise ValueError("BAL_H curl coefficient is not positive finite")
    cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    tags = np.full(cell_count, -1, dtype=np.int32)
    tag_indices = np.asarray(local_mesh.mesh_data.cell_tags.indices, dtype=np.int32)
    tag_values = np.asarray(local_mesh.mesh_data.cell_tags.values, dtype=np.int32)
    if tag_indices.size != cell_count or np.unique(tag_indices).size != cell_count:
        raise ValueError("BAL_H cell tags do not cover owned cells exactly once")
    tags[tag_indices] = tag_values
    material_counts: dict[int, int] = {}
    for cell in range(cell_count):
        tag = int(tags[cell])
        try:
            epsilon = epsilon_by_tag[tag]
        except KeyError as exc:
            raise NotImplementedError(
                f"BAL_H has no positive DG0 contract for cell tag {tag}"
            ) from exc
        mass_value = float(cfg.k0**2 * abs(epsilon))
        if not np.isfinite(mass_value) or mass_value <= 0.0:
            raise ValueError("BAL_H mass coefficient is not positive finite")
        mu_dof = int(coefficient_space.dofmap.cell_dofs(cell)[0])
        mass_dof = int(coefficient_space.dofmap.cell_dofs(cell)[0])
        if max(mu_dof, mass_dof) >= mu.x.array.size:
            raise RuntimeError("BAL_H DG0 cell DoF exceeds local coefficient storage")
        mu.x.array[mu_dof] = mu_value
        mass.x.array[mass_dof] = mass_value
        material_counts[tag] = material_counts.get(tag, 0) + 1
    mu.x.scatter_forward()
    mass.x.scatter_forward()
    return mu, mass, {
        "curl_coefficient": float(mu_value),
        "mass_coefficient_by_tag": {
            str(tag): float(cfg.k0**2 * abs(epsilon_by_tag[tag]))
            for tag in sorted(material_counts)
        },
        "owned_cell_count": cell_count,
        "owned_cell_counts_by_tag": {
            str(tag): int(count) for tag, count in sorted(material_counts.items())
        },
        "dg0_assignment": "owned cell -> coefficient_space.dofmap.cell_dofs(cell)[0]",
        "ghost_scatter": "forward",
    }


class FixedH6:
    """Frozen degree-three Jacobi-scaled Chebyshev action."""

    def __init__(
        self,
        window_action: FullspaceMpcFormAction,
        diagonal: PETSc.Vec,
        seed: PETSc.Vec,
        material_audit: dict[str, object],
        seed_audit: dict[str, object],
    ) -> None:
        matrix = window_action.matrix
        rows, columns = (int(value) for value in matrix.getSize())
        if rows != columns or rows <= 0:
            raise ValueError("BAL_H action must be nonempty and square")
        if diagonal.getSize() != rows or seed.getSize() != rows:
            raise ValueError("BAL_H diagonal and seed layouts must match action")
        self.action = window_action
        self.diagonal = diagonal
        self._matrix = matrix
        self._destroyed = False
        self._runtime_installed = False
        self.matrix_mult_count = 0
        self._inv_sqrt = matrix.createVecRight()
        diagonal_values = np.asarray(diagonal.getArray(readonly=True), dtype=np.complex128)
        if (
            not np.all(np.isfinite(diagonal_values))
            or np.any(np.abs(diagonal_values.imag) > _MPC_TOLERANCE)
            or np.any(diagonal_values.real <= 0.0)
        ):
            self.destroy()
            raise ValueError("BAL_H Jacobi diagonal is not positive")
        self._inv_sqrt.array[:] = 1.0 / np.sqrt(diagonal_values.real)
        self._scaled_input = matrix.createVecRight()
        self._scaled_action = matrix.createVecLeft()
        power_vector = matrix.createVecRight()
        power_action = matrix.createVecLeft()
        try:
            if seed.getLocalSize() != power_vector.getLocalSize():
                raise ValueError("BAL_H fixed seed local layout does not match action")
            seed.copy(power_vector)
            seed_values = np.asarray(power_vector.getArray(readonly=True))
            if not np.all(np.isfinite(seed_values)):
                raise FloatingPointError("BAL_H fixed seed is non-finite")
            norm = float(power_vector.norm())
            if not np.isfinite(norm) or norm == 0.0:
                raise FloatingPointError("BAL_H fixed seed is invalid")
            power_vector.scale(1.0 / norm)
            history: list[float] = []
            for _ in range(POWER_STEPS):
                self._apply_scaled_into(power_vector, power_action)
                norm = float(power_action.norm())
                if not np.isfinite(norm) or norm == 0.0:
                    raise FloatingPointError("BAL_H power estimate is invalid")
                power_action.copy(power_vector)
                power_vector.scale(1.0 / norm)
                self._apply_scaled_into(power_vector, power_action)
                rayleigh = power_vector.dot(power_action)
                value = float(np.real(rayleigh))
                if (
                    not np.isfinite(value)
                    or value <= 0.0
                    or abs(float(np.imag(rayleigh)))
                    > 1.0e-10 * max(value, 1.0)
                ):
                    raise FloatingPointError("BAL_H power estimate is invalid")
                history.append(value)
            self.power_history = tuple(history)
        except BaseException:
            power_vector.destroy()
            power_action.destroy()
            self.destroy()
            raise
        power_vector.destroy()
        power_action.destroy()
        self.power_matrix_mult_count = int(self.matrix_mult_count)
        self.window_original_apply_count = int(window_action.audit["apply_count"])
        self.lambda_power10 = float(self.power_history[-1])
        self.lambda_hi = LAMBDA_HI_FACTOR * self.lambda_power10
        self.lambda_lo = LAMBDA_LO_FACTOR * self.lambda_hi
        if not np.isfinite(self.lambda_hi) or not 0.0 < self.lambda_lo < self.lambda_hi:
            self.destroy()
            raise FloatingPointError("BAL_H frozen spectral window is invalid")
        self._rhs_scaled = matrix.createVecRight()
        self._residual = matrix.createVecLeft()
        self._direction = matrix.createVecRight()
        self._solution = matrix.createVecRight()
        self._action = matrix.createVecLeft()
        self.apply_count = 0
        self._material_audit = dict(material_audit)
        self._seed_audit = dict(seed_audit)
        self._audit = {
            "schema": "task041.bal_h.v5.fixed.v1",
            "h6_degree": H6_DEGREE,
            "power_steps": POWER_STEPS,
            "power_matrix_mult_count": self.power_matrix_mult_count,
            "matrix_mult_count": self.matrix_mult_count,
            "window_original_apply_count": self.window_original_apply_count,
            "runtime_apply_count_at_install": None,
            "power_history": tuple(self.power_history),
            "lambda_power10": self.lambda_power10,
            "lambda_hi": self.lambda_hi,
            "lambda_lo": self.lambda_lo,
            "lambda_hi_factor": LAMBDA_HI_FACTOR,
            "lambda_lo_factor": LAMBDA_LO_FACTOR,
            "window_action": "original FFCx form action",
            "runtime_action": "IsotropicPartialAssembly positive_sum",
            "contiguous_work": True,
            "factor_count": 0,
            "numeric_allgather": False,
            "material": dict(self._material_audit),
            "seed": dict(self._seed_audit),
            "apply_count": 0,
        }

    @property
    def matrix(self) -> PETSc.Mat:
        if self._destroyed:
            raise RuntimeError("BAL_H has been destroyed")
        return self._matrix

    @property
    def audit(self) -> MappingProxyType:
        self._audit["apply_count"] = int(self.apply_count)
        self._audit["matrix_mult_count"] = int(self.matrix_mult_count)
        return MappingProxyType(self._audit)

    def _apply_scaled_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._scaled_input.pointwiseMult(self._inv_sqrt, source)
        self._matrix.mult(self._scaled_input, self._scaled_action)
        target.pointwiseMult(self._inv_sqrt, self._scaled_action)
        self.matrix_mult_count += 1

    def _install_runtime_action(
        self,
        runtime_action: FullspaceMpcFormAction,
    ) -> None:
        """Install the packed action once, after the frozen power window."""

        if self._runtime_installed:
            raise RuntimeError("BAL_H runtime action is already installed")
        runtime_apply_count = int(runtime_action.audit["apply_count"])
        window_action = self.action
        self.action = runtime_action
        self._matrix = runtime_action.matrix
        self._runtime_installed = True
        self._audit["runtime_apply_count_at_install"] = runtime_apply_count
        window_action.destroy()

    def apply_into(self, rhs: PETSc.Vec, target: PETSc.Vec) -> dict[str, object]:
        if self._destroyed:
            raise RuntimeError("BAL_H has been destroyed")
        if rhs.getSize() != self._matrix.getSize()[0] or target.getSize() != self._matrix.getSize()[0]:
            raise ValueError("BAL_H vector layout does not match action")
        before = self.matrix_mult_count
        self._rhs_scaled.pointwiseMult(self._inv_sqrt, rhs)
        center = 0.5 * (self.lambda_hi + self.lambda_lo)
        half_width = 0.5 * (self.lambda_hi - self.lambda_lo)
        sigma = center / half_width
        rho = 1.0 / sigma
        self._rhs_scaled.copy(self._direction)
        self._direction.scale(1.0 / center)
        self._direction.copy(self._solution)
        for _ in range(1, H6_DEGREE):
            self._apply_scaled_into(self._solution, self._action)
            self._rhs_scaled.copy(self._residual)
            self._residual.axpy(-1.0, self._action)
            rho_new = 1.0 / (2.0 * sigma - rho)
            self._direction.scale(rho_new * rho)
            self._direction.axpy(2.0 * rho_new / half_width, self._residual)
            self._solution.axpy(1.0, self._direction)
            rho = rho_new
        target.pointwiseMult(self._inv_sqrt, self._solution)
        self.apply_count += 1
        facts = {
            "matrix_mult_count": self.matrix_mult_count - before,
            "apply_count": int(self.apply_count),
        }
        return facts

    def apply(self, rhs: PETSc.Vec) -> PETSc.Vec:
        target = self._matrix.createVecRight()
        try:
            self.apply_into(rhs, target)
        except BaseException:
            target.destroy()
            raise
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        action = getattr(self, "action", None)
        self.action = None
        if action is not None:
            action.destroy()
        for name in (
            "_inv_sqrt",
            "_scaled_input",
            "_scaled_action",
            "_rhs_scaled",
            "_residual",
            "_direction",
            "_solution",
            "_action",
            "diagonal",
        ):
            vector = getattr(self, name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        self._matrix = None


def _h6_window_inventory(
    h6: FixedH6,
    seed: PETSc.Vec,
) -> dict[str, Any]:
    owned = [
        _payload_vector_inventory(
            h6.diagonal,
            label="h6.diagonal",
            ownership="FixedH6 until destroy",
        )
    ]
    for name in (
        "_inv_sqrt",
        "_scaled_input",
        "_scaled_action",
        "_rhs_scaled",
        "_residual",
        "_direction",
        "_solution",
        "_action",
    ):
        owned.append(
            _payload_vector_inventory(
                getattr(h6, name),
                label=f"h6.{name[1:]}",
                ownership="FixedH6 until destroy",
            )
        )
    matrix = h6.matrix
    return {
        "stage_scope": "rank_local",
        "owned_objects": owned,
        "borrowed_objects": [
            {
                **_payload_vector_inventory(
                    seed,
                    label="h6.seed_input",
                    ownership="caller pending destroy after H6 runtime setup",
                ),
            }
        ],
        "matrix": {
            "label": "h6.window_matrix",
            "local_shape": [int(value) for value in matrix.getLocalSize()],
            "global_shape": [int(value) for value in matrix.getSize()],
            "payload_bytes_local": "unknown",
        },
        "native_workspace_bytes": "unknown",
    }


def _h6_runtime_inventory(h6: FixedH6) -> dict[str, Any]:
    action = h6.action
    kernel = getattr(action, "_local_kernel", None)
    kernel_objects = []
    if kernel is not None:
        for name in ("permutations", "dofs", "material_indices", "metrics"):
            kernel_objects.append(
                _payload_array_inventory(
                    getattr(kernel, name, None),
                    label=f"h6.runtime.kernel.{name}",
                    ownership="IsotropicPartialAssembly until H6 destroy",
                )
            )
        basis = getattr(kernel, "basis", None)
        for name in ("values", "curls", "weights", "geometry_derivatives"):
            kernel_objects.append(
                _payload_array_inventory(
                    getattr(basis, name, None),
                    label=f"h6.runtime.kernel.basis.{name}",
                    ownership="PositiveCellBasis via IsotropicPartialAssembly",
                )
            )
    return {
        "stage_scope": "rank_local",
        "owned_objects": [
            _payload_vector_inventory(
                action._output_vector,
                label="h6.runtime.output_vector",
                ownership="FullspaceMpcFormAction until H6 destroy",
            ),
            _payload_array_inventory(
                action._coefficient.x.array,
                label="h6.runtime.coefficient_array",
                ownership="FullspaceMpcFormAction until H6 destroy",
            ),
            _payload_array_inventory(
                action._constraint_work,
                label="h6.runtime.constraint_work",
                ownership="FullspaceMpcFormAction until H6 destroy",
            ),
            _payload_array_inventory(
                action._owned_slave_work,
                label="h6.runtime.owned_slave_work",
                ownership="FullspaceMpcFormAction until H6 destroy",
            ),
            _payload_array_inventory(
                action._constants,
                label="h6.runtime.packed_constants",
                ownership="FullspaceMpcFormAction until H6 destroy",
            ),
            *kernel_objects,
        ],
        "borrowed_objects": [
            {
                "label": "h6.runtime.mpc_space",
                "ownership": "borrowed from side system; not destroyed here",
                "payload_bytes_local": "unknown",
            }
        ],
        "native_workspace_bytes": "unknown",
    }


def build_balanced_h6(
    side_system: Any,
    *,
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> FixedH6:
    """Build BAL_H from an existing side mesh, p6 space and finalized MPC."""

    cfg = side_system.cfg
    space = side_system.V
    floquet_data = side_system.floquet_data
    mpc = floquet_data.mpc
    if int(cfg.nedelec_degree) != 6:
        raise ValueError("BAL_H requires the p6 side space")
    if mpc.function_space.mesh is not side_system.local_mesh.mesh:
        raise ValueError("BAL_H MPC and side mesh must match")
    if int(space.element.basix_element.degree) != 6:
        raise ValueError("BAL_H requires a degree-six p6 space")

    mu = mass = None
    diagonal = seed = None
    original = runtime = None
    h6 = None

    def emit(event: str, detail: Mapping[str, Any] | None = None) -> None:
        if lifecycle_callback is not None:
            lifecycle_callback(
                event,
                {
                    "scope": "side_local",
                    **({} if detail is None else dict(detail)),
                },
            )

    try:
        mu, mass, material_audit = build_positive_material_coefficients(side_system)
        form = same_mesh_positive_form(
            space,
            curl_coefficient=mu,
            mass_coefficient=mass,
        )
        original = FullspaceMpcFormAction(form, space, mpc=mpc)
        emit("h6_diagonal_begin", {"source": "quadrature_positive_diagonal"})
        diagonal = build_quadrature_positive_diagonal(space, mu, mass, mpc)
        if lifecycle_callback is None:
            emit("h6_diagonal_ready", {"source": "quadrature_positive_diagonal"})
        else:
            emit(
                "h6_diagonal_ready",
                {
                    "source": "quadrature_positive_diagonal",
                    "object_inventory": {
                        "owned_objects": [
                            _payload_vector_inventory(
                                diagonal,
                                label="h6.diagonal_build_output",
                                ownership=(
                                    "build_balanced_h6 until FixedH6 construction"
                                ),
                            )
                        ],
                        "native_workspace_bytes": "unknown",
                    },
                },
            )
        seed, seed_audit = build_fixed_random_seed(space, floquet_data, cfg)
        emit("h6_window_begin", {"source": "FixedH6"})
        h6 = FixedH6(
            original,
            diagonal,
            seed,
            material_audit,
            seed_audit,
        )
        diagonal = None
        original = None
        if lifecycle_callback is None:
            emit("h6_window_ready", {"source": "FixedH6"})
        else:
            emit(
                "h6_window_ready",
                {
                    "source": "FixedH6",
                    "object_inventory": _h6_window_inventory(h6, seed),
                },
            )
        emit("h6_runtime_begin", {"source": "FullspaceMpcFormAction"})
        runtime = FullspaceMpcFormAction(
            form,
            space,
            mpc=mpc,
            local_kernel=IsotropicPartialAssembly(
                mpc.function_space,
                mu,
                mass,
                contiguous_work=True,
            ),
        )
        h6._install_runtime_action(runtime)
        runtime = None
        if lifecycle_callback is None:
            emit("h6_runtime_ready", {"source": "IsotropicPartialAssembly"})
        else:
            emit(
                "h6_runtime_ready",
                {
                    "source": "IsotropicPartialAssembly",
                    "object_inventory": _h6_runtime_inventory(h6),
                },
            )
        seed.destroy()
        seed = None
        h6._audit["side"] = str(getattr(side_system, "side", "unknown"))
        return h6
    except BaseException:
        if h6 is not None:
            h6.destroy()
        if original is not None:
            original.destroy()
        if runtime is not None:
            runtime.destroy()
        if diagonal is not None:
            diagonal.destroy()
        if seed is not None:
            seed.destroy()
        raise


__all__ = (
    "H6_DEGREE",
    "LAMBDA_HI_FACTOR",
    "LAMBDA_LO_FACTOR",
    "POWER_STEPS",
    "FixedH6",
    "build_balanced_h6",
    "build_fixed_random_seed",
    "build_positive_material_coefficients",
)
