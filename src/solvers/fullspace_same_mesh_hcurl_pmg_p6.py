"""Exact owner-local constrained diagonal for the same-mesh H(curl) form.

The helper is intentionally smaller than an assembler.  It evaluates the
compiled cell kernel once per owned cell, applies the DOLFINx row-standard
and transpose-right Basix transformations, and accumulates only diagonal
contributions of ``C^H A C``.  No global high-order matrix or per-cell tensor
cache is retained.  A finalized MPC contributes identity rows for its owned
slave storage locations.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from dolfinx import fem
from dolfinx.la.petsc import create_vector
from petsc4py import PETSc

__all__ = (
    "accumulate_constrained_local_diagonal",
    "build_constrained_jacobi_diagonal",
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
