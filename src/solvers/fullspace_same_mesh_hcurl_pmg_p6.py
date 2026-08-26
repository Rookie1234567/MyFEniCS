"""Exact owner-local constrained diagonal for the same-mesh H(curl) form.

The helper is intentionally smaller than an assembler.  It evaluates the
compiled cell kernel once per owned cell, applies the DOLFINx row-standard
and transpose-right Basix transformations, and accumulates only diagonal
contributions of ``C^H A C``.  No global high-order matrix or per-cell tensor
cache is retained.  A finalized MPC contributes identity rows for its owned
slave storage locations.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

__all__ = (
    "accumulate_constrained_local_diagonal",
    "build_constrained_jacobi_diagonal",
    "SameMeshP6MatrixFreeShell",
    "SameMeshP6NestedVcycle",
)


def accumulate_constrained_local_diagonal(
    tensor: np.ndarray,
    target_indices: np.ndarray,
    expansion_coefficients: np.ndarray,
    output: np.ndarray,
) -> None:
    """Add ``diag(C^H tensor C)`` to an indexed output without forming ``C``.

    ``target_indices[row, link]`` and ``expansion_coefficients[row, link]``
    describe the local expansion of a raw row into independent target rows.
    A target may occur in several raw rows and may have several links in one
    row; the row-pair sum therefore retains all multi-master cross terms.
    """

    tensor = np.asarray(tensor, dtype=np.complex128)
    targets = np.asarray(target_indices, dtype=np.int64)
    coefficients = np.asarray(expansion_coefficients, dtype=np.complex128)
    output = np.asarray(output, dtype=np.complex128)
    if tensor.ndim != 2 or tensor.shape[0] != tensor.shape[1]:
        raise ValueError("local tensor must be square")
    if (
        targets.ndim != 2
        or coefficients.shape != targets.shape
        or targets.shape[0] != tensor.shape[0]
        or output.ndim != 1
    ):
        raise ValueError("local MPC expansion has an incompatible shape")
    if targets.shape[1] == 0:
        raise ValueError("local MPC expansion has no links")

    flat_targets = targets.reshape(-1)
    flat_coefficients = coefficients.reshape(-1)
    for target in np.unique(flat_targets[flat_targets >= 0]):
        target = int(target)
        if target >= output.size:
            raise ValueError("local MPC target is outside the diagonal storage")
        positions = np.flatnonzero(flat_targets == target)
        rows = positions // targets.shape[1]
        values = flat_coefficients[positions]
        contribution = 0.0 + 0.0j
        for row, coefficient in zip(rows, values, strict=True):
            contribution += np.conjugate(coefficient) * np.dot(
                tensor[int(row), rows], values
            )
        output[target] += contribution


def _apply_standard_row_transform(
    element: Any,
    tensor: np.ndarray,
    cell_info: int,
    transform_workspace: np.ndarray,
) -> None:
    """Apply DOLFINx ``P0`` to a complex tensor via real Basix transforms."""

    if not bool(element.needs_dof_transformations):
        return
    info = np.asarray([int(cell_info)], dtype=np.uint32)
    for part in (tensor.real, tensor.imag):
        np.copyto(transform_workspace, part.reshape(-1))
        element.T_apply(
            transform_workspace, info, int(tensor.shape[1])
        )
        part[:] = transform_workspace.reshape(tensor.shape)


def _apply_transpose_right_transform(
    element: Any,
    tensor: np.ndarray,
    cell_info: int,
    transform_workspace: np.ndarray,
) -> None:
    """Apply DOLFINx ``P1T`` using Basix ``Tt_apply_right`` exactly."""

    if not bool(element.needs_dof_transformations):
        return
    basix_element = element.basix_element
    for part in (tensor.real, tensor.imag):
        np.copyto(transform_workspace, part.reshape(-1))
        basix_element.Tt_apply_right(
            transform_workspace, int(tensor.shape[0]), int(cell_info)
        )
        part[:] = transform_workspace.reshape(tensor.shape)


def _cell_kernel(compiled_form: Any, owned_cells: int) -> Any:
    ufcx_form = compiled_form.ufcx_form
    module = compiled_form.module
    if isinstance(module, list) or isinstance(ufcx_form, list):
        raise NotImplementedError("mixed-topology diagonal kernels are unsupported")
    if int(
        compiled_form._cpp_object.num_integrals(fem.IntegralType.cell, 0)
    ) != 1:
        raise ValueError("constrained diagonal requires exactly one cell integral")
    for integral_type in (
        fem.IntegralType.exterior_facet,
        fem.IntegralType.interior_facet,
    ):
        if int(compiled_form._cpp_object.num_integrals(integral_type, 0)) != 0:
            raise ValueError("constrained diagonal supports cell integrals only")
    start = int(ufcx_form.form_integral_offsets[0])
    kernel = ufcx_form.form_integrals[start].tabulate_tensor_complex128
    if kernel == module.ffi.NULL:
        raise TypeError("compiled form has no complex128 cell kernel")
    domains = np.asarray(
        compiled_form._cpp_object.domains(fem.IntegralType.cell, 0),
        dtype=np.int32,
    )
    expected = np.arange(int(owned_cells), dtype=np.int32)
    if domains.shape != expected.shape or not np.array_equal(domains, expected):
        raise ValueError("cell integral domain must cover owned cells in order")
    return kernel


def _packed_cell_coefficients(
    packed: Any, cell: int, cell_count: int
) -> np.ndarray:
    try:
        values = packed[(fem.IntegralType.cell, 0)]
    except KeyError:
        return np.empty(0, dtype=np.complex128)
    values = np.asarray(values, dtype=np.complex128)
    if values.size == 0:
        return np.empty(0, dtype=np.complex128)
    if values.ndim != 2 or values.shape[0] != int(cell_count):
        raise ValueError("packed cell coefficients must be full-owned rows")
    return np.ascontiguousarray(values[int(cell)], dtype=np.complex128)


def _kernel_cell_tensor(
    compiled_form: Any,
    kernel: Any,
    coordinates: np.ndarray,
    coefficients: np.ndarray,
    constants: np.ndarray,
    tensor: np.ndarray,
) -> None:
    tensor.fill(0.0 + 0.0j)
    ffi = compiled_form.module.ffi
    coefficient_pointer = (
        ffi.NULL
        if coefficients.size == 0
        else ffi.cast(
            "double _Complex *", ffi.from_buffer(coefficients)
        )
    )
    constant_pointer = (
        ffi.NULL
        if constants.size == 0
        else ffi.cast("double _Complex *", ffi.from_buffer(constants))
    )
    kernel(
        ffi.cast("double _Complex *", ffi.from_buffer(tensor)),
        coefficient_pointer,
        constant_pointer,
        ffi.cast("double *", ffi.from_buffer(coordinates)),
        ffi.NULL,
        ffi.NULL,
        ffi.NULL,
    )


def _cell_expansion_workspace(
    mpc: Any | None,
    storage: int,
    dimension: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    storage = int(storage)
    if mpc is None:
        slaves = np.empty(0, dtype=np.int64)
        max_links = 1
    else:
        slaves = np.asarray(mpc.slaves, dtype=np.int64)
        if slaves.size and (
            np.any(slaves < 0) or np.any(slaves >= storage)
        ):
            raise ValueError("MPC slave rows exceed local storage")
        _, offsets = mpc.coefficients()
        offsets = np.asarray(offsets, dtype=np.int64)
        max_links = 1
        for slave in slaves:
            row = int(slave)
            if row + 1 >= offsets.size:
                raise ValueError("MPC offsets do not cover slave rows")
            max_links = max(max_links, int(offsets[row + 1] - offsets[row]))
    slave_mask = np.zeros(storage, dtype=bool)
    slave_mask[slaves.astype(np.int64, copy=False)] = True
    target_indices = np.full((int(dimension), max_links), -1, dtype=np.int64)
    expansion_coefficients = np.zeros(
        (int(dimension), max_links), dtype=np.complex128
    )
    return (
        slaves,
        slave_mask,
        target_indices,
        expansion_coefficients,
    )


def _fill_cell_expansion(
    local_dofs: np.ndarray,
    mpc: Any | None,
    storage: int,
    slave_mask: np.ndarray,
    target_indices: np.ndarray,
    expansion_coefficients: np.ndarray,
) -> None:
    target_indices.fill(-1)
    expansion_coefficients.fill(0.0 + 0.0j)
    if target_indices.shape[0] != local_dofs.size:
        raise ValueError("MPC expansion and cell tensor dimensions differ")
    if mpc is None:
        target_indices[:, 0] = local_dofs
        expansion_coefficients[:, 0] = 1.0 + 0.0j
        return
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
            master = int(master)
            if master < 0 or master >= int(storage):
                raise ValueError("MPC master row exceeds local storage")
            target_indices[position, link] = master
            expansion_coefficients[position, link] = complex(value)


def build_constrained_jacobi_diagonal(
    compiled_form: Any,
    mpc: Any | None = None,
) -> PETSc.Vec:
    """Build the exact diagonal of a positive full-space MPC operator.

    ``compiled_form`` must be the complex128 bilinear form used for the
    positive curl-plus-mass action.  Only owned cells are evaluated.  The
    returned vector has the MPC function-space layout when ``mpc`` is given;
    owned slave entries are set to one after the local ``C^H A C`` additions.
    """

    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise TypeError("constrained diagonal requires complex128 PETSc")
    form_spaces = compiled_form.function_spaces
    if len(form_spaces) != 2:
        raise ValueError("constrained diagonal requires a rank-two form")
    if mpc is None:
        work_space = form_spaces[0]
    else:
        work_space = mpc.function_space
        if int(work_space.dofmap.index_map.size_global) != int(
            form_spaces[0].dofmap.index_map.size_global
        ):
            raise ValueError("MPC and compiled form layouts differ")
    if int(work_space.dofmap.index_map_bs) != 1:
        raise NotImplementedError("constrained diagonal requires scalar DoFs")
    if int(form_spaces[0].dofmap.index_map.size_global) != int(
        form_spaces[1].dofmap.index_map.size_global
    ):
        raise ValueError("compiled diagonal form is not square")

    mesh = work_space.mesh
    index_map = work_space.dofmap.index_map
    owned = int(index_map.size_local)
    storage = owned + int(index_map.num_ghosts)
    element0 = form_spaces[0].element
    element1 = form_spaces[1].element
    dimension = int(element0.space_dimension)
    if dimension != int(element1.space_dimension):
        raise ValueError("compiled diagonal form has different test/trial sizes")
    slaves, slave_mask, target_indices, expansion_coefficients = _cell_expansion_workspace(
        mpc, storage, dimension
    )
    mesh.topology.create_entity_permutations()
    cell_info = np.asarray(
        mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )
    owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    if cell_info.size < owned_cells:
        raise RuntimeError("cell permutation inventory is incomplete")

    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    geometry_coordinates = np.asarray(mesh.geometry.x)
    if geometry_dofmap.shape[0] < owned_cells:
        raise RuntimeError("geometry cell inventory is incomplete")
    kernel = _cell_kernel(compiled_form, owned_cells)
    packed_coefficients = fem.pack_coefficients(compiled_form)
    constants = np.ascontiguousarray(
        np.asarray(fem.pack_constants(compiled_form), dtype=np.complex128)
    ).reshape(-1)
    tensor = np.zeros((dimension, dimension), dtype=np.complex128)
    transform_workspace = np.empty(tensor.size, dtype=np.float64)
    coordinates = np.empty(
        int(geometry_dofmap.shape[1]) * 3, dtype=np.float64
    )
    local_diagonal = np.zeros(storage, dtype=np.complex128)
    for cell in range(owned_cells):
        local_dofs = np.asarray(
            work_space.dofmap.cell_dofs(cell), dtype=np.int32
        )
        if local_dofs.size != dimension:
            raise ValueError("cell DoF count does not match the compiled form")
        geometry_dofs = np.asarray(geometry_dofmap[cell], dtype=np.int32)
        cell_coordinates = np.asarray(
            geometry_coordinates[geometry_dofs], dtype=np.float64
        )
        if cell_coordinates.size != coordinates.size:
            raise ValueError("cell geometry shape changed across cells")
        coordinates[:] = cell_coordinates.reshape(-1)
        coefficients = _packed_cell_coefficients(
            packed_coefficients, cell, owned_cells
        )
        _kernel_cell_tensor(
            compiled_form,
            kernel,
            coordinates,
            coefficients,
            constants,
            tensor,
        )
        _apply_standard_row_transform(
            element0,
            tensor,
            int(cell_info[cell]),
            transform_workspace,
        )
        _apply_transpose_right_transform(
            element1,
            tensor,
            int(cell_info[cell]),
            transform_workspace,
        )
        _fill_cell_expansion(
            local_dofs,
            mpc,
            storage,
            slave_mask,
            target_indices,
            expansion_coefficients,
        )
        accumulate_constrained_local_diagonal(
            tensor,
            target_indices,
            expansion_coefficients,
            local_diagonal,
        )

    diagonal = create_vector(
        [(index_map, int(work_space.dofmap.index_map_bs))]
    )
    with diagonal.localForm() as local:
        local.array_w[:] = local_diagonal
    diagonal.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    owned_values = np.asarray(diagonal.array[:owned], dtype=np.complex128).copy()
    if not np.all(np.isfinite(owned_values)):
        diagonal.destroy()
        raise RuntimeError("constrained diagonal contains non-finite entries")
    owned_slaves = (
        slaves[(slaves >= 0) & (slaves < owned)]
        if mpc is not None
        else np.empty(0, dtype=np.int64)
    )
    non_slave_mask = np.ones(owned, dtype=bool)
    non_slave_mask[owned_slaves] = False
    if np.any(owned_values.real[non_slave_mask] <= 0.0):
        diagonal.destroy()
        raise ValueError("constrained diagonal is not strictly positive")
    if mpc is not None:
        with diagonal.localForm() as local:
            local.array_w[owned_slaves] = 1.0 + 0.0j
    diagonal.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return diagonal


P6_NESTED_SCHEMA = "task038.same_mesh_hcurl_pmg.p6-nested.v1"
P6_NESTED_LEVELS = (6, 3, 1)
P6_NESTED_PAIRS = ((6, 3), (3, 1))


class SameMeshP6MatrixFreeShell:
    """PETSc shell owning one full-space p6 action and exact diagonal.

    The shell owns and destroys ``action`` and ``diagonal`` exactly once.
    Only the Vec returned by ``action.apply`` is borrowed and reusable.
    """

    def __init__(self, action: Any, diagonal: PETSc.Vec) -> None:
        source_matrix = action.matrix
        global_rows, global_columns = (int(value) for value in source_matrix.getSize())
        local_rows, local_columns = (
            int(value) for value in source_matrix.getLocalSize()
        )
        if global_rows != global_columns or local_rows != local_columns:
            raise ValueError("p6 matrix-free shell requires a square action")
        if (
            int(diagonal.getSize()) != global_rows
            or int(diagonal.getLocalSize()) != local_rows
        ):
            raise ValueError("p6 diagonal and action layouts differ")
        action_audit = getattr(action, "audit", {})
        if action_audit.get("slave_row_identity") is not True:
            raise ValueError("p6 shell requires the full-space slave identity action")
        self.action = action
        self.diagonal = diagonal
        self._global_rows = global_rows
        self._local_rows = local_rows
        self._matrix: PETSc.Mat | None = PETSc.Mat().createPython(
            ((local_rows, global_rows), (local_columns, global_columns)),
            context=self,
            comm=source_matrix.getComm(),
        )
        self._matrix.setUp()
        self._destroyed = False
        self.audit = MappingProxyType(
            {
                "schema": P6_NESTED_SCHEMA,
                "p6_matrix_free": True,
                "p6_global_aij": False,
                "global_dense_transfer": False,
                "numeric_allgather": False,
                "owns_action": True,
                "owns_exact_diagonal": True,
                "apply_output_ownership": "borrowed_reusable_copied_to_target",
                "action_borrowed_output_copied": True,
                "diagonal": "exact_constrained_jacobi",
                "slave_row_identity": True,
            }
        )

    @property
    def matrix(self) -> PETSc.Mat:
        if self._matrix is None:
            raise RuntimeError("p6 matrix-free shell has been destroyed")
        return self._matrix

    def mult(
        self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self._destroyed:
            raise RuntimeError("p6 matrix-free shell has been destroyed")
        # FullspaceMpcFormAction.apply returns its reusable borrowed Vec.
        # The shell copies it and deliberately does not destroy it.
        borrowed = self.action.apply(source)
        borrowed.copy(target)

    def getDiagonal(self, _matrix: PETSc.Mat, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("p6 matrix-free shell has been destroyed")
        self.diagonal.copy(target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        matrix = self._matrix
        self._matrix = None
        self._destroyed = True
        if matrix is not None and _matrix is None:
            matrix.destroy()
        diagonal = self.diagonal
        action = self.action
        self.diagonal = None
        self.action = None
        diagonal.destroy()
        action.destroy()


class SameMeshP6NestedVcycle:
    """Fixed p6 -> p3 -> p1 composition with reusable PETSc work vectors."""

    def __init__(
        self,
        p6_shell: SameMeshP6MatrixFreeShell,
        lower_cycle: Any,
        p63_transfer: Any,
        p3_matrix: PETSc.Mat,
        *,
        smoother: Any | None = None,
        owned_slave_indices: np.ndarray | None = None,
        owns_lower_cycle: bool = False,
        owns_p63_transfer: bool = False,
        owns_p6_shell: bool = True,
    ) -> None:
        p6_matrix = p6_shell.matrix
        p6_global = p6_matrix.getSize()
        p6_local = p6_matrix.getLocalSize()
        p3_global = p3_matrix.getSize()
        p3_local = p3_matrix.getLocalSize()
        if p6_global[0] != p6_global[1] or p3_global[0] != p3_global[1]:
            raise ValueError("nested p6 cycle requires square level matrices")
        for name in ("apply_primal_into", "apply_adjoint_into"):
            if not callable(getattr(p63_transfer, name, None)):
                raise TypeError(f"p6 cycle transfer lacks {name}")
        if not callable(getattr(lower_cycle, "apply_into", None)):
            raise TypeError("p6 cycle requires an existing lower V-cycle")
        slaves = (
            np.empty(0, dtype=np.int32)
            if owned_slave_indices is None
            else np.asarray(owned_slave_indices, dtype=np.int32)
        )
        if (
            slaves.ndim != 1
            or np.any(slaves < 0)
            or np.any(slaves >= int(p6_local[1]))
        ):
            raise ValueError("p6 owned slave indices are outside target storage")
        if np.unique(slaves).size != slaves.size:
            raise ValueError("p6 owned slave indices are duplicated")
        self.p6_shell = p6_shell
        self.lower_cycle = lower_cycle
        self.p63_transfer = p63_transfer
        self.p3_matrix = p3_matrix
        self._owns_lower_cycle = bool(owns_lower_cycle)
        self._owns_p63_transfer = bool(owns_p63_transfer)
        self._owns_p6_shell = bool(owns_p6_shell)
        self._owned_slave_indices = np.ascontiguousarray(slaves).copy()
        self._owned_slave_indices.flags.writeable = False
        self._p6_rhs_layout = (int(p6_global[0]), int(p6_local[0]))
        self._p6_target_layout = (int(p6_global[1]), int(p6_local[1]))
        self._p3_rhs_layout = (int(p3_global[0]), int(p3_local[0]))
        self._p3_target_layout = (int(p3_global[1]), int(p3_local[1]))
        self._work: list[PETSc.Vec] = []
        self.smoother = None
        self._owns_smoother = smoother is None
        self._destroyed = False
        self.apply_count = 0
        self._p63_primal_total = 0
        self._p63_adjoint_total = 0
        self._lower_cycle_total = 0
        self._smoother_apply_total = 0
        try:
            if smoother is None:
                from .fullspace_lor_edge_geometric_mg_global import (
                    FixedChebyshevJacobiPETSc,
                )

                self.smoother = FixedChebyshevJacobiPETSc(p6_matrix)
            else:
                self.smoother = smoother
            self._allocate_work()
            self.audit = MappingProxyType(
                {
                    "schema": P6_NESTED_SCHEMA,
                    "levels": list(P6_NESTED_LEVELS),
                    "pairs": [list(pair) for pair in P6_NESTED_PAIRS],
                    "p6_matrix_free": True,
                    "p6_global_aij": False,
                    "p3_sparse_allowed": True,
                    "global_dense_transfer": False,
                    "numeric_allgather": False,
                    "smoother": "fixed_degree_3_chebyshev_jacobi",
                    "smoother_instances": 1,
                    "power_steps": 10,
                    "pre_smoother_count": 1,
                    "post_smoother_count": 1,
                    "p63_primal_count": 1,
                    "p63_adjoint_count": 1,
                    "lower_cycle_count": 1,
                    "p1_exact_factor": True,
                    "retains_per_apply_history": False,
                    "owned_slave_zeroing": True,
                    "work_vector_count": len(self._work),
                    "destroy_order": [
                        "p6_smoother",
                        "p6_cycle_work_vectors",
                        "lower_cycle_if_owned",
                        "p63_transfer_if_owned",
                        "p6_shell_if_owned",
                    ],
                }
            )
            self.last_apply_facts: dict[str, object] = {}
        except Exception:
            self.destroy()
            raise

    def _allocate_work(self) -> None:
        matrix = self.p6_shell.matrix

        def add(vector: PETSc.Vec) -> PETSc.Vec:
            self._work.append(vector)
            return vector

        self._p6_pre = add(matrix.createVecRight())
        self._p6_action = add(matrix.createVecLeft())
        self._p6_residual = add(matrix.createVecLeft())
        self._p6_correction = add(matrix.createVecRight())
        self._p6_solution = add(matrix.createVecRight())
        self._p6_post_action = add(matrix.createVecLeft())
        self._p6_post_residual = add(matrix.createVecLeft())
        self._p6_post_correction = add(matrix.createVecRight())
        self._p3_rhs = add(self.p3_matrix.createVecLeft())
        self._p3_correction = add(self.p3_matrix.createVecRight())

    @property
    def matrix(self) -> PETSc.Mat:
        return self.p6_shell.matrix

    @property
    def work_vectors(self) -> tuple[PETSc.Vec, ...]:
        return tuple(self._work)

    def _require_vector(
        self, vector: PETSc.Vec, layout: tuple[int, int], name: str
    ) -> None:
        if (int(vector.getSize()), int(vector.getLocalSize())) != layout:
            raise ValueError(f"{name} vector layout does not match the fixed cycle")

    def _zero_owned_slaves(self, vector: PETSc.Vec) -> None:
        if self._owned_slave_indices.size:
            vector.array[self._owned_slave_indices] = 0.0 + 0.0j

    def _owned_slave_max(self, vector: PETSc.Vec) -> float:
        local = (
            float(np.max(np.abs(vector.array[self._owned_slave_indices])))
            if self._owned_slave_indices.size
            else 0.0
        )
        comm = self.matrix.getComm().tompi4py()
        return float(comm.allreduce(local, op=MPI.MAX))

    def apply_into(self, rhs: PETSc.Vec, target: PETSc.Vec) -> dict[str, object]:
        if self._destroyed:
            raise RuntimeError("p6 nested V-cycle has been destroyed")
        self._require_vector(rhs, self._p6_rhs_layout, "p6 dual residual")
        self._require_vector(target, self._p6_target_layout, "p6 primal target")
        order = ["p6_pre"]
        self.smoother.apply_into(rhs, self._p6_pre)
        self._smoother_apply_total += 1
        self.matrix.mult(self._p6_pre, self._p6_action)
        rhs.copy(self._p6_residual)
        self._p6_residual.axpy(-1.0, self._p6_action)
        order.append("p6_residual")
        self.p63_transfer.apply_adjoint_into(
            self._p6_residual, self._p3_rhs
        )
        self._p63_adjoint_total += 1
        order.append("p6_to_p3_adjoint")
        lower_facts = self.lower_cycle.apply_into(
            self._p3_rhs, self._p3_correction
        )
        self._lower_cycle_total += 1
        p1_solve_count = int(lower_facts["p1_solve_count"])
        if p1_solve_count != 1:
            raise RuntimeError("lower p3-to-p1 cycle did not perform one p1 solve")
        order.append("p3_to_p1_cycle")
        self.p63_transfer.apply_primal_into(
            self._p3_correction, self._p6_correction
        )
        self._p63_primal_total += 1
        self._zero_owned_slaves(self._p6_correction)
        self._p6_pre.copy(self._p6_solution)
        self._p6_solution.axpy(1.0, self._p6_correction)
        order.append("p3_to_p6_primal")
        self.matrix.mult(self._p6_solution, self._p6_post_action)
        rhs.copy(self._p6_post_residual)
        self._p6_post_residual.axpy(-1.0, self._p6_post_action)
        self.smoother.apply_into(
            self._p6_post_residual, self._p6_post_correction
        )
        self._smoother_apply_total += 1
        self._p6_solution.axpy(1.0, self._p6_post_correction)
        self._zero_owned_slaves(self._p6_solution)
        self._p6_solution.copy(target)
        order.append("p6_post")
        output_norm = float(target.norm())
        owned_slave_max = self._owned_slave_max(target)
        if not np.isfinite(output_norm) or not np.isfinite(owned_slave_max):
            raise RuntimeError("p6 nested V-cycle output is non-finite")
        if owned_slave_max != 0.0:
            raise RuntimeError("p6 nested V-cycle output is not slave-zero")
        self.apply_count += 1
        facts: dict[str, object] = {
            "order": tuple(order),
            "p6_pre_smoother_count": 1,
            "p6_post_smoother_count": 1,
            "p6_smoother_apply_count": 2,
            "p6_smoother_apply_total": int(self._smoother_apply_total),
            "p63_adjoint_count": 1,
            "p63_primal_count": 1,
            "p63_adjoint_total": int(self._p63_adjoint_total),
            "p63_primal_total": int(self._p63_primal_total),
            "lower_cycle_count": 1,
            "lower_cycle_total": int(self._lower_cycle_total),
            "p1_solve_count": p1_solve_count,
            "output_finite": True,
            "owned_slave_max": owned_slave_max,
            "apply_count": int(self.apply_count),
            "lower_cycle_facts": dict(lower_facts),
        }
        self.last_apply_facts = facts
        return facts

    def apply(self, rhs: PETSc.Vec) -> PETSc.Vec:
        target = self.matrix.createVecRight()
        try:
            self.apply_into(rhs, target)
        except Exception:
            target.destroy()
            raise
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        smoother = self.smoother
        self.smoother = None
        if self._owns_smoother and smoother is not None:
            smoother.destroy()
        for vector in self._work:
            vector.destroy()
        self._work = []
        if self._owns_lower_cycle:
            self.lower_cycle.destroy()
        if self._owns_p63_transfer:
            self.p63_transfer.destroy()
        if self._owns_p6_shell:
            self.p6_shell.destroy()
        self.lower_cycle = None
        self.p63_transfer = None
        self.p3_matrix = None
