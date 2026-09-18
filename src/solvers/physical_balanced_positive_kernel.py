"""Small positive H(curl) cell kernel for the BAL_H smoother.

The kernel keeps the donor V5 order: orient the reference basis, expand each
cell row through the finalized MPC, combine equal targets, and only then form
the positive curl-plus-mass energy.  It retains no dense cell matrix.
"""

from __future__ import annotations

import hashlib
from typing import Any

import basix
import numpy as np
import ufl
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from petsc4py import PETSc


def same_mesh_positive_form(
    space: Any,
    *,
    curl_coefficient: Any,
    mass_coefficient: Any,
) -> Any:
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    return (
        curl_coefficient * ufl.inner(ufl.curl(trial), ufl.curl(test))
        + mass_coefficient * ufl.inner(trial, test)
    ) * ufl.dx


def _cell_expansion_workspace(
    mpc: Any,
    storage: int,
    dimension: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    slaves = np.asarray(mpc.slaves, dtype=np.int64)
    if slaves.size and (
        np.any(slaves < 0) or np.any(slaves >= int(storage))
    ):
        raise ValueError("MPC slave rows exceed local cell storage")
    _, offsets = mpc.coefficients()
    offsets = np.asarray(offsets, dtype=np.int64)
    max_links = 1
    for slave in slaves.tolist():
        if int(slave) + 1 >= offsets.size:
            raise ValueError("MPC offsets do not cover slave rows")
        max_links = max(
            max_links,
            int(offsets[int(slave) + 1] - offsets[int(slave)]),
        )
    slave_mask = np.zeros(int(storage), dtype=bool)
    slave_mask[slaves] = True
    target_indices = np.full(
        (int(dimension), max_links), -1, dtype=np.int64
    )
    expansion_coefficients = np.zeros(
        (int(dimension), max_links), dtype=np.complex128
    )
    return slaves, slave_mask, target_indices, expansion_coefficients


def _fill_cell_expansion(
    local_dofs: np.ndarray,
    mpc: Any,
    storage: int,
    slave_mask: np.ndarray,
    target_indices: np.ndarray,
    expansion_coefficients: np.ndarray,
) -> None:
    target_indices.fill(-1)
    expansion_coefficients.fill(0.0 + 0.0j)
    if target_indices.shape[0] != local_dofs.size:
        raise ValueError("MPC expansion and cell basis dimensions differ")
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    for position, local_row in enumerate(local_dofs.tolist()):
        row = int(local_row)
        if not slave_mask[row]:
            target_indices[position, 0] = row
            expansion_coefficients[position, 0] = 1.0 + 0.0j
            continue
        start = int(offsets[row])
        stop = int(offsets[row + 1])
        masters = np.asarray(mpc.masters.links(row), dtype=np.int64)
        row_coefficients = coefficients[start:stop]
        if masters.size != row_coefficients.size:
            raise ValueError("MPC master/coefficient metadata do not close")
        if masters.size > target_indices.shape[1]:
            raise ValueError("MPC expansion workspace is too small")
        for link, (master, value) in enumerate(
            zip(masters.tolist(), row_coefficients.tolist(), strict=True)
        ):
            if master < 0 or int(master) >= int(storage):
                raise ValueError("MPC master row exceeds local cell storage")
            target_indices[position, link] = int(master)
            expansion_coefficients[position, link] = complex(value)


def accumulate_basis_energy(
    values: np.ndarray,
    curls: np.ndarray,
    weights: np.ndarray,
    targets: np.ndarray,
    coefficients: np.ndarray,
    output: np.ndarray,
    *,
    curl_coefficient: float,
    mass_coefficient: float,
) -> None:
    """Accumulate ``diag(C^H A C)`` after target-wise basis combination."""

    if (
        values.shape != curls.shape
        or values.ndim != 3
        or weights.shape != (values.shape[1],)
        or targets.ndim != 2
        or targets.shape != coefficients.shape
        or targets.shape[0] != values.shape[0]
    ):
        raise ValueError("incompatible positive-basis expansion dimensions")
    for target in np.unique(targets[targets >= 0]):
        target = int(target)
        if target >= output.size:
            raise ValueError("positive-basis target is outside local storage")
        rows, links = np.nonzero(targets == target)
        factors = coefficients[rows, links]
        value = np.einsum("i,iqk->qk", factors, values[rows])
        curl = np.einsum("i,iqk->qk", factors, curls[rows])
        output[target] += np.dot(
            weights,
            float(mass_coefficient) * np.sum(np.abs(value) ** 2, axis=1)
            + float(curl_coefficient) * np.sum(np.abs(curl) ** 2, axis=1),
        )


def _cell_jacobians(
    geometry_derivatives: np.ndarray,
    coordinates: np.ndarray,
) -> np.ndarray:
    """Compute geometry Jacobians after removing translation-only coordinates."""

    coordinates = np.asarray(coordinates, dtype=np.float64)
    local_coordinates = coordinates - coordinates[0]
    return np.einsum("aqi,ib->qba", geometry_derivatives, local_coordinates)


def _validate_affine_cell_jacobians(
    jacobians: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Validate affine, positively oriented cell Jacobians."""

    jacobian = jacobians[0]
    scale = max(float(np.max(np.abs(jacobian))), np.finfo(float).tiny)
    if np.max(np.abs(jacobians - jacobian)) > 128 * np.finfo(float).eps * scale:
        raise NotImplementedError("BAL_H requires affine geometry")
    determinant = float(np.linalg.det(jacobian))
    if not np.isfinite(determinant) or determinant <= 0.0:
        raise ValueError("BAL_H requires positive finite cell Jacobians")
    return jacobian, determinant


class ReferenceCellBasis:
    """Reference quadrature and oriented N1curl basis tables."""

    def __init__(self, space: Any, form: Any) -> None:
        from ffcx.analysis import analyze_ufl_objects
        from ffcx.element_interface import create_quadrature

        mesh = space.mesh
        element = space.element.basix_element
        if (
            mesh.basix_cell() != basix.CellType.hexahedron
            or element.map_type != basix.MapType.covariantPiola
            or element.family != basix.ElementFamily.N1E
            or mesh.geometry.cmap.degree != 1
            or mesh.geometry.dim != 3
            or int(space.dofmap.index_map_bs) != 1
        ):
            raise NotImplementedError(
                "BAL_H requires scalar-blocked N1curl on affine Q1 hexes"
            )
        self.space = space
        analysis = analyze_ufl_objects([form], np.dtype(np.complex128))
        data = analysis.form_data[0]
        integrals = [
            integral
            for group in data.integral_data
            for integral in group.integrals
        ]
        if len(integrals) != 1 or integrals[0].integral_type() != "cell":
            raise NotImplementedError("BAL_H requires one cell integral")
        metadata = integrals[0].metadata()
        rule = metadata["quadrature_rule"]
        if rule in ("custom", "vertex"):
            raise NotImplementedError("BAL_H does not use custom quadrature")
        points, weights = create_quadrature(
            "hexahedron",
            metadata["quadrature_degree"],
            rule,
            data.argument_elements,
        )
        table = element.tabulate(1, points)
        self.values = np.ascontiguousarray(table[0].transpose(1, 0, 2))
        self.curls = np.ascontiguousarray(
            np.stack(
                (
                    table[2, :, :, 2] - table[3, :, :, 1],
                    table[3, :, :, 0] - table[1, :, :, 2],
                    table[1, :, :, 1] - table[2, :, :, 0],
                ),
                axis=2,
            ).transpose(1, 0, 2)
        )
        geometry_element = basix.create_element(
            basix.ElementFamily.P,
            basix.CellType.hexahedron,
            1,
            basix.LagrangeVariant.equispaced,
        )
        self.geometry_derivatives = geometry_element.tabulate(1, points)[
            1:, :, :, 0
        ]
        self.weights = np.asarray(weights, dtype=np.float64)
        self.audit = {
            "quadrature_degree": int(metadata["quadrature_degree"]),
            "quadrature_rule": rule,
            "quadrature_points": len(points),
            "points_sha256": hashlib.sha256(points.tobytes()).hexdigest(),
            "weights_sha256": hashlib.sha256(self.weights.tobytes()).hexdigest(),
            "reference_initialization_array_upper_bound_bytes": int(
                4 * table.nbytes
                + self.geometry_derivatives.nbytes
                + points.nbytes
                + self.weights.nbytes
            ),
            "dense_cell_tensor": False,
        }


class PositiveCellBasis(ReferenceCellBasis):
    """Reference basis with positive DG0 curl and mass coefficients."""

    def __init__(self, space: Any, mu: Any, mass: Any, *, action_rule: bool) -> None:
        for coefficient in (mu, mass):
            element = coefficient.function_space.element.basix_element
            if (
                coefficient.function_space.mesh is not space.mesh
                or element.degree != 0
                or not element.discontinuous
                or element.dim != 1
            ):
                raise NotImplementedError("BAL_H coefficients must be same-mesh DG0")
            array = np.asarray(coefficient.x.array)
            if (
                not np.all(np.isfinite(array))
                or np.any(array.imag != 0.0)
                or np.any(array.real <= 0.0)
            ):
                raise ValueError("BAL_H coefficients must be finite and positive")
        self.mu = mu
        self.mass = mass
        form = same_mesh_positive_form(
            space,
            curl_coefficient=mu,
            mass_coefficient=mass,
        )
        if action_rule:
            form = ufl.action(form, fem.Function(space))
        super().__init__(space, form)

    def cell(
        self,
        cell: int,
        permutation: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[float, float]]:
        mesh = self.space.mesh
        coordinates = mesh.geometry.x[mesh.geometry.dofmap[cell]]
        jacobians = _cell_jacobians(self.geometry_derivatives, coordinates)
        jacobian, determinant = _validate_affine_cell_jacobians(jacobians)
        values = np.ascontiguousarray(self.values @ np.linalg.inv(jacobian))
        curls = np.ascontiguousarray(self.curls @ jacobian.T / determinant)
        if self.space.element.needs_dof_transformations:
            info = np.asarray([permutation], dtype=np.uint32)
            for array in (values, curls):
                self.space.element.T_apply(array.reshape(-1), info, array.shape[1] * 3)
        mu_dof = int(self.mu.function_space.dofmap.cell_dofs(cell)[0])
        mass_dof = int(self.mass.function_space.dofmap.cell_dofs(cell)[0])
        return (
            values,
            curls,
            self.weights * determinant,
            (
                float(np.real(self.mu.x.array[mu_dof])),
                float(np.real(self.mass.x.array[mass_dof])),
            ),
        )


def build_quadrature_positive_diagonal(
    space: Any,
    mu: Any,
    mass: Any,
    mpc: Any,
) -> PETSc.Vec:
    """Build the owned-cell diagonal of the constrained positive operator."""

    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise TypeError("BAL_H requires complex128 PETSc")
    if mpc is None or mpc.function_space.mesh is not space.mesh:
        raise ValueError("BAL_H diagonal requires a matching finalized MPC")
    work_space = mpc.function_space
    index_map = work_space.dofmap.index_map
    owned = int(index_map.size_local)
    storage = owned + int(index_map.num_ghosts)
    dimension = int(work_space.element.space_dimension)
    slaves, mask, targets, coefficients = _cell_expansion_workspace(
        mpc, storage, dimension
    )
    basis = PositiveCellBasis(space, mu, mass, action_rule=False)
    work_space.mesh.topology.create_entity_permutations()
    permutations = work_space.mesh.topology.get_cell_permutation_info()
    cell_count = int(work_space.mesh.topology.index_map(work_space.mesh.topology.dim).size_local)
    local = np.zeros(storage, dtype=np.complex128)
    for cell in range(cell_count):
        dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
        _fill_cell_expansion(dofs, mpc, storage, mask, targets, coefficients)
        values, curls, weights, (mu_cell, mass_cell) = basis.cell(
            cell, int(permutations[cell])
        )
        accumulate_basis_energy(
            values,
            curls,
            weights,
            targets,
            coefficients,
            local,
            curl_coefficient=mu_cell,
            mass_coefficient=mass_cell,
        )
        del values, curls, weights

    diagonal = create_vector(
        [(index_map, int(work_space.dofmap.index_map_bs))]
    )
    try:
        with diagonal.localForm() as local_form:
            local_form.array_w[:] = local
        diagonal.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        owned_values = np.asarray(diagonal.array[:owned], dtype=np.complex128)
        owned_slaves = slaves[slaves < owned]
        non_slave = np.ones(owned, dtype=bool)
        non_slave[owned_slaves] = False
        if (
            not np.all(np.isfinite(owned_values))
            or np.any(owned_values.real[non_slave] <= 0.0)
        ):
            raise ValueError("BAL_H constrained diagonal is not positive")
        with diagonal.localForm() as local_form:
            local_form.array_w[owned_slaves] = 1.0 + 0.0j
        diagonal.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        return diagonal
    except BaseException:
        diagonal.destroy()
        raise


class IsotropicPartialAssembly:
    """Qualified positive-sum packed cell action with bounded work storage."""

    batch_size = 8

    def __init__(
        self,
        space: Any,
        mu: Any,
        mass: Any,
        *,
        contiguous_work: bool,
    ) -> None:
        self.space = space
        self.contiguous_work = bool(contiguous_work)
        self.basis = PositiveCellBasis(space, mu, mass, action_rule=True)
        mesh = space.mesh
        mesh.topology.create_entity_permutations()
        self.permutations = np.asarray(
            mesh.topology.get_cell_permutation_info(), dtype=np.uint32
        )
        self.cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
        dimension, points, _components = self.basis.values.shape
        self.dofs = np.asarray(
            [space.dofmap.cell_dofs(cell) for cell in range(self.cell_count)],
            dtype=np.int32,
        ).reshape(self.cell_count, dimension)
        self.material_indices = np.asarray(
            [
                [
                    int(mass.function_space.dofmap.cell_dofs(cell)[0]),
                    int(mu.function_space.dofmap.cell_dofs(cell)[0]),
                ]
                for cell in range(self.cell_count)
            ],
            dtype=np.int32,
        ).reshape(self.cell_count, 2)
        self.metrics = np.empty((self.cell_count, 2, 3, 3), dtype=np.float64)
        for cell in range(self.cell_count):
            coordinates = mesh.geometry.x[mesh.geometry.dofmap[cell]]
            jacobians = _cell_jacobians(
                self.basis.geometry_derivatives, coordinates
            )
            jacobian, determinant = _validate_affine_cell_jacobians(jacobians)
            inverse = np.linalg.inv(jacobian)
            self.metrics[cell, 0] = inverse @ inverse.T * determinant
            self.metrics[cell, 1] = jacobian.T @ jacobian / determinant
        for array in (self.permutations, self.dofs, self.material_indices, self.metrics):
            array.flags.writeable = False
        self.audit = {
            **self.basis.audit,
            "backend": "IsotropicPartialAssembly",
            "component": "positive_sum",
            "contiguous_work": self.contiguous_work,
            "cell_count_owned": self.cell_count,
            "packing_workspace_upper_bound_bytes": int(
                self.batch_size * (16 * dimension + 48 * points)
            ),
            "temporary_budget_bytes": int(
                self.batch_size * (64 * dimension + 256 * points + 512)
                + self.batch_size * (16 * dimension + 48 * points)
            ),
            "reference_table_bytes": int(
                sum(
                    array.nbytes
                    for array in (
                        self.basis.values,
                        self.basis.curls,
                        self.basis.weights,
                        self.basis.geometry_derivatives,
        )
                )
            ),
            "cell_metadata_bytes": int(
                sum(
                    array.nbytes
                    for array in (
                        self.permutations,
                        self.dofs,
                        self.material_indices,
                        self.metrics,
                    )
                )
            ),
            "dense_cell_tensor": False,
        }

    def apply(self, input_values: np.ndarray, output: np.ndarray) -> None:
        basis = self.basis
        element = self.space.element
        values = basis.values.reshape(basis.values.shape[0], -1)
        curls = basis.curls.reshape(basis.curls.shape[0], -1)
        for start in range(0, self.cell_count, self.batch_size):
            stop = min(start + self.batch_size, self.cell_count)
            cells = range(start, stop)
            dofs = self.dofs[start:stop]
            local = np.ascontiguousarray(input_values[dofs])
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.Tt_apply(
                        local[row].view(np.float64),
                        self.permutations[cell : cell + 1],
                        2,
                    )
            result = np.zeros_like(local)
            real = np.ascontiguousarray(local.real) if self.contiguous_work else local.real
            imag = np.ascontiguousarray(local.imag) if self.contiguous_work else local.imag
            for column, (table, kind) in enumerate(((values, "mass"), (curls, "curl"))):
                flux = (real @ table + 1j * (imag @ table)).reshape(len(dofs), -1, 3)
                for row, cell in enumerate(cells):
                    coefficient = (
                        basis.mass.x.array[self.material_indices[cell, 0]]
                        if kind == "mass"
                        else basis.mu.x.array[self.material_indices[cell, 1]]
                    )
                    flux[row] = (
                        flux[row] @ self.metrics[cell, column]
                    ) * (float(np.real(coefficient)) * basis.weights[:, None])
                flat = flux.reshape(len(dofs), -1)
                flat_real = np.ascontiguousarray(flat.real) if self.contiguous_work else flat.real
                flat_imag = np.ascontiguousarray(flat.imag) if self.contiguous_work else flat.imag
                result += flat_real @ table.T + 1j * (flat_imag @ table.T)
            for row, cell in enumerate(cells):
                if element.needs_dof_transformations:
                    element.T_apply(
                        result[row].view(np.float64),
                        self.permutations[cell : cell + 1],
                        2,
                    )
            np.add.at(output, dofs.ravel(), result.ravel())


__all__ = (
    "IsotropicPartialAssembly",
    "PositiveCellBasis",
    "ReferenceCellBasis",
    "accumulate_basis_energy",
    "build_quadrature_positive_diagonal",
    "same_mesh_positive_form",
)
