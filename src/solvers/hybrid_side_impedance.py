"""Small side-impedance transmission algebra for Task040.

The carrier is deliberately independent of the Hybrid global operator.  It
orchestrates restriction/prolongation and the frozen forward/backward sweep;
the caller supplies the local solve for
``R_j F_s R_j^T + T_j^- + T_j^+``.  Thus the impedance is a PC ingredient and
the bare ``F_s`` action is never modified by this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from typing import Any

import numpy as np
import ufl
from dolfinx import fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from ..constraints.cross_section_floquet import reduce_matrix_hermitian
from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse

__all__ = (
    "TASK040_FORWARD_ORDER",
    "TASK040_LEVEL_A_SUBDOMAINS",
    "TASK040_BACKWARD_ORDER",
    "TASK040_LEVEL_A_SOURCE_LABELS",
    "SideImpedanceTransmissionAction",
    "PetscSideImpedanceTransmissionAction",
    "build_first_order_interface_impedance",
    "build_first_order_tangential_impedance",
    "ArtificialZTraceMass",
    "audit_artificial_z_interface_support",
    "build_level_a_cell_recovery_group_rows",
    "assemble_reduced_artificial_interface_tangential_mass",
    "build_artificial_z_tangential_trace_mass",
    "build_first_order_petsc_interface_impedance",
    "build_side_impedance_transmission_action",
    "build_petsc_side_impedance_transmission_action",
    "build_level_a_oracle",
    "audit_petsc_level_a_one_apply",
)


TASK040_LEVEL_A_SUBDOMAINS = ((0, 1), (2, 3), (4, 5))
TASK040_FORWARD_ORDER = (0, 1, 2)
TASK040_BACKWARD_ORDER = (2, 1, 0)
TASK040_LEVEL_A_SOURCE_LABELS = (
    "physical_side_rhs",
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)


def build_level_a_cell_recovery_group_rows(
    system: Any,
    matrix: PETSc.Mat,
    interface_supports: Sequence[Mapping[str, Any]],
) -> tuple[tuple[np.ndarray, ...], dict[str, Any]]:
    """Build owned Level-A rows from six-layer cell recovery maps.

    The cell union is the group definition.  Interface supports are used only
    for a collective identity audit; they are never appended to a group.
    """

    z_values = np.asarray(system.local_mesh.z_values, dtype=np.float64)
    comm = matrix.getComm().tompi4py()
    condensed = system.static_condensation.condensed
    expansion = condensed.trace_constraints.expansion_by_original
    first, last = map(int, matrix.getOwnershipRange())
    global_size = int(matrix.getSize()[0])
    local_mask = np.zeros(
        (len(TASK040_LEVEL_A_SUBDOMAINS), global_size), dtype=np.bool_
    )
    local_error: str | None = None
    try:
        if z_values.shape != (7,) or np.any(np.diff(z_values) <= 0.0):
            raise ValueError("Task040 cell recovery requires six ordered z layers")
        geometry = system.local_mesh.mesh.geometry
        for cell, recovery in enumerate(condensed.cell_recovery_maps):
            geometry_indices = np.asarray(geometry.dofmap[cell], dtype=np.int64)
            centroid_z = float(np.mean(geometry.x[geometry_indices, 2]))
            layer = int(np.searchsorted(z_values, centroid_z, side="right") - 1)
            if layer < 0 or layer >= 6:
                raise ValueError(
                    f"Task040 cell recovery layer {layer} is outside z partition"
                )
            group = layer // 2
            for original in recovery.trace_original_dofs:
                active_ids, coefficients = expansion[int(original)]
                for active, coefficient in zip(active_ids, coefficients, strict=True):
                    if coefficient != 0:
                        active = int(active)
                        if active < 0 or active >= global_size:
                            raise ValueError(
                                f"active expansion row {active} is outside matrix"
                            )
                        local_mask[group, active] = True
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise ValueError(
            "Task040 cell-recovery group construction failed: "
            + next(error for error in errors if error is not None)
        )

    global_mask = np.zeros_like(local_mask)
    comm.Allreduce(local_mask, global_mask, op=MPI.LOR)
    group_rows = tuple(
        np.flatnonzero(global_mask[group, first:last]).astype(PETSc.IntType) + first
        for group in range(len(TASK040_LEVEL_A_SUBDOMAINS))
    )
    global_rows = tuple(
        int(comm.allreduce(len(rows), op=MPI.SUM)) for rows in group_rows
    )
    if any(rows == 0 for rows in global_rows):
        raise ValueError("Task040 cell-recovery group has no global rows")

    coverage: list[dict[str, Any]] = []
    for interface, support in enumerate(interface_supports):
        active_support = {int(value) for value in support["active_support"]}
        counts = []
        for group in (interface, interface + 1):
            if active_support and (
                min(active_support) < 0 or max(active_support) >= global_size
            ):
                raise ValueError("Artificial-interface support row is outside matrix")
            counts.append(
                int(np.count_nonzero(global_mask[group, list(active_support)]))
            )
        expected = len(active_support)
        coverage.append(
            {
                "interface": interface,
                "active_support_count": expected,
                "lower_group_count": counts[0],
                "upper_group_count": counts[1],
                "lower_complete": counts[0] == expected,
                "upper_complete": counts[1] == expected,
            }
        )
    if not all(item["lower_complete"] and item["upper_complete"] for item in coverage):
        raise ValueError("Task040 artificial-interface support is absent from a group")

    group_mask_hashes = [
        hashlib.sha256(np.ascontiguousarray(global_mask[group]).tobytes()).hexdigest()
        for group in range(len(TASK040_LEVEL_A_SUBDOMAINS))
    ]
    direct_cell_union_hash = hashlib.sha256(
        repr(tuple(group_mask_hashes)).encode()
    ).hexdigest()
    return group_rows, {
        "group_global_rows": list(global_rows),
        "group_local_rows": [len(rows) for rows in group_rows],
        "group_mask_sha256": group_mask_hashes,
        "direct_cell_union_sha256": direct_cell_union_hash,
        "interface_support_coverage": coverage,
        "support_source": "cell_recovery_maps_and_trace_constraints",
        "mapping_source": "cell_recovery_union_mpi_or",
        "oracle_only_global_boolean_metadata_collective": True,
        "oracle_only": True,
    }


def build_first_order_tangential_impedance(
    tangential_mass: np.ndarray,
    beta: complex,
    outward_normal_sign: int,
) -> np.ndarray:
    """Return the fixed first-order tangential impedance ``-i beta M``.

    The outward normal is carried by the traction/integration-by-parts term;
    it is deliberately not folded into this Robin mass coefficient.
    """

    mass = np.asarray(tangential_mass, dtype=np.complex128)
    if mass.ndim != 2 or mass.shape[0] != mass.shape[1]:
        raise ValueError("Tangential impedance mass must be square.")
    if not np.all(np.isfinite(mass)) or not np.isfinite(complex(beta)):
        raise ValueError("Tangential impedance data must be finite.")
    if int(outward_normal_sign) not in {-1, 1}:
        raise ValueError("Artificial-interface outward normal must be +/-1.")
    return np.asarray(
        -1j * complex(beta) * mass,
        dtype=np.complex128,
    )


def build_first_order_interface_impedance(
    tangential_mass: np.ndarray,
    beta: complex,
    outward_normal_signs: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Build same-sign Robin masses for opposite traction normals."""

    if len(outward_normal_signs) != 2:
        raise ValueError("An interface needs two outward normal signs.")
    left, right = (int(value) for value in outward_normal_signs)
    if left != -right:
        raise ValueError("Artificial-interface normals must be opposite.")
    return (
        build_first_order_tangential_impedance(tangential_mass, beta, left),
        build_first_order_tangential_impedance(tangential_mass, beta, right),
    )


@dataclass
class ArtificialZTraceMass:
    """One reduced sparse tangential mass on an artificial z interface.

    The mass is assembled once on the interior facet with the ``+`` trace and
    reduced through the existing trace-constraint expansion.  Both adjacent
    PC blocks use this same matrix; their traction normals remain opposite.
    """

    matrix: PETSc.Mat
    audit: dict[str, Any]
    _destroyed: bool = False

    def build_impedance_pair(
        self,
        beta: complex,
        outward_normal_signs: tuple[int, int],
    ) -> tuple[PETSc.Mat, PETSc.Mat]:
        if self._destroyed:
            raise RuntimeError("Artificial z trace mass is destroyed.")
        left, right = (int(value) for value in outward_normal_signs)
        if left != -right or left not in {-1, 1}:
            raise ValueError("Artificial-interface normals must be opposite +/-1.")
        if not np.isfinite(complex(beta)):
            raise ValueError("Artificial-interface beta must be finite.")
        result = []
        try:
            for _normal in outward_normal_signs:
                matrix = self.matrix.copy()
                matrix.scale(PETSc.ScalarType(-1j * complex(beta)))
                result.append(matrix)
            return result[0], result[1]
        except Exception:
            for matrix in result:
                matrix.destroy()
            raise

    def destroy(self) -> None:
        if not self._destroyed:
            self.matrix.destroy()
            self._destroyed = True


def audit_artificial_z_interface_support(
    V: Any,
    condensed: Any,
    interface_z: float,
    *,
    tolerance: float = 1.0e-10,
) -> dict[str, Any]:
    """Audit two-sided cell/facet and condensed active support for one z plane."""

    msh = V.mesh
    comm = msh.comm
    tdim = msh.topology.dim
    fdim = tdim - 1
    if tdim != 3 or str(msh.basix_cell()).split(".")[-1] != "hexahedron":
        raise ValueError("Artificial z interfaces require a 3D hexahedron mesh.")
    if int(V.dofmap.index_map_bs) != 1:
        raise ValueError("Artificial z support requires scalar-blocked H(curl) DoFs.")
    msh.topology.create_entities(fdim)
    msh.topology.create_connectivity(fdim, tdim)
    msh.topology.create_connectivity(tdim, fdim)
    facet_to_cell = msh.topology.connectivity(fdim, tdim)
    cell_to_facet = msh.topology.connectivity(tdim, fdim)
    layout = V.dofmap.dof_layout
    dofmap = V.dofmap
    geometry = msh.geometry
    owned_facet_count = int(msh.topology.index_map(fdim).size_local)
    located_facets = np.asarray(
        mesh.locate_entities(
            msh,
            fdim,
            lambda x: np.isclose(x[2], float(interface_z), atol=tolerance, rtol=0.0),
        ),
        dtype=np.int32,
    )
    located_facets = located_facets[located_facets < owned_facet_count]
    midpoints = mesh.compute_midpoints(msh, fdim, located_facets)
    constraints = condensed.trace_constraints
    local_records: list[dict[str, Any]] = []
    local_error: str | None = None

    def active_support(raw: tuple[int, ...]) -> tuple[int, ...]:
        active: set[int] = set()
        for original in raw:
            if int(original) not in constraints.expansion_by_original:
                raise ValueError(f"missing trace constraint expansion for {original}")
            ids, coefficients = constraints.expansion_by_original[int(original)]
            active.update(
                int(value)
                for value, coefficient in zip(ids, coefficients, strict=True)
                if coefficient != 0
            )
        return tuple(sorted(active))

    try:
        for facet, midpoint in zip(located_facets, midpoints, strict=True):
            facet = int(facet)
            coordinates = np.asarray(midpoint, dtype=np.float64)
            cells = np.asarray(facet_to_cell.links(facet), dtype=np.int32)
            if len(cells) != 2:
                raise ValueError(
                    f"z={interface_z:g} facet {facet} has {len(cells)} adjacent cells"
                )
            centers = np.asarray(
                [
                    np.asarray(
                        geometry.x[np.asarray(geometry.dofmap[int(cell)])],
                        dtype=np.float64,
                    )[:, 2].mean()
                    for cell in cells
                ]
            )
            lower = np.flatnonzero(centers < float(interface_z) - tolerance)
            upper = np.flatnonzero(centers > float(interface_z) + tolerance)
            if len(lower) != 1 or len(upper) != 1:
                raise ValueError(
                    f"z={interface_z:g} facet {facet} lacks one lower and one upper cell"
                )
            side_raw: list[tuple[int, ...]] = []
            for position in (int(lower[0]), int(upper[0])):
                cell = int(cells[position])
                cell_facets = np.asarray(cell_to_facet.links(cell), dtype=np.int32)
                local_facet = np.flatnonzero(cell_facets == int(facet))
                if len(local_facet) != 1:
                    raise ValueError(f"facet {facet} is not unique in cell {cell}")
                local_dofs = np.asarray(
                    layout.entity_closure_dofs(fdim, int(local_facet[0])),
                    dtype=np.int32,
                )
                cell_dofs = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
                original = np.asarray(
                    dofmap.index_map.local_to_global(cell_dofs[local_dofs]),
                    dtype=np.int64,
                )
                side_raw.append(tuple(sorted(set(int(value) for value in original))))
            if side_raw[0] != side_raw[1]:
                raise ValueError(f"facet {facet} lower/upper raw support differs")
            lower_active = active_support(side_raw[0])
            upper_active = active_support(side_raw[1])
            if lower_active != upper_active:
                raise ValueError(f"facet {facet} lower/upper active support differs")
            key = tuple(round(float(value), 12) for value in coordinates)
            local_records.append(
                {
                    "facet": facet,
                    "key": key,
                    "raw": side_raw[0],
                    "active": lower_active,
                }
            )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"

    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        first = next(error for error in errors if error is not None)
        raise ValueError(f"Artificial z interface support audit failed: {first}")
    local_keys = tuple(record["key"] for record in local_records)
    all_keys = [key for packet in comm.allgather(local_keys) for key in packet]
    keys = tuple(all_keys)
    if not keys:
        raise ValueError(f"Artificial z interface z={interface_z:g} has no facets")
    if len(keys) != len(set(keys)):
        raise ValueError("Artificial z interface facet ownership is duplicated")
    selected_records = tuple(local_records)
    local_facets = sorted(int(record["facet"]) for record in selected_records)
    local_raw_support = tuple(
        sorted({value for record in selected_records for value in record["raw"]})
    )
    local_active_support = tuple(
        sorted({value for record in selected_records for value in record["active"]})
    )
    raw_support = tuple(
        sorted(
            {value for packet in comm.allgather(local_raw_support) for value in packet}
        )
    )
    active_support = tuple(
        sorted(
            {
                value
                for packet in comm.allgather(local_active_support)
                for value in packet
            }
        )
    )
    support_hash = hashlib.sha256(
        repr((tuple(sorted(keys)), raw_support, active_support)).encode()
    ).hexdigest()
    tags = mesh.meshtags(
        msh,
        fdim,
        np.asarray(local_facets, dtype=np.int32),
        np.ones(len(local_facets), dtype=np.int32),
    )
    return {
        "facet_tags": tags,
        "facet_tag": 1,
        "interface_z": float(interface_z),
        "facet_count_global": int(comm.allreduce(len(selected_records), op=MPI.SUM)),
        "raw_support": raw_support,
        "active_support": active_support,
        "lower_support": {
            "raw_trace_dof_count": len(raw_support),
            "active_trace_dof_count": len(active_support),
            "raw_support_nnz": len(raw_support),
            "active_support_nnz": len(active_support),
            "support_sha256": support_hash,
        },
        "upper_support": {
            "raw_trace_dof_count": len(raw_support),
            "active_trace_dof_count": len(active_support),
            "raw_support_nnz": len(raw_support),
            "active_support_nnz": len(active_support),
            "support_sha256": support_hash,
        },
        "support_sets_exact_match": True,
        "outward_normal_signs": [1, -1],
    }


def _distributed_sparse_support(
    matrix: PETSc.Mat, *, tolerance: float = 1.0e-14
) -> tuple[set[int], set[int]]:
    first, last = map(int, matrix.getOwnershipRange())
    rows: set[int] = set()
    columns: set[int] = set()
    for row in range(first, last):
        cols, values = matrix.getRow(row)
        nonzero = [
            int(column) for column, value in zip(cols, values) if abs(value) > tolerance
        ]
        if nonzero:
            rows.add(row)
            columns.update(nonzero)
    comm = matrix.getComm().tompi4py()
    packets = comm.allgather((rows, columns))
    return (
        set().union(*(packet[0] for packet in packets)),
        set().union(*(packet[1] for packet in packets)),
    )


def _petsc_matrix_hash(matrix: PETSc.Mat) -> str:
    local = hashlib.sha256()
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        columns, values = matrix.getRow(row)
        local.update(np.asarray([row], dtype=np.int64).tobytes())
        local.update(np.asarray(columns, dtype=np.int64).tobytes())
        local.update(np.asarray(values, dtype=np.complex128).tobytes())
    comm = matrix.getComm().tompi4py()
    result = hashlib.sha256()
    for digest in comm.allgather(local.digest()):
        result.update(digest)
    return result.hexdigest()


def _petsc_matrix_finite(matrix: PETSc.Mat) -> bool:
    first, last = map(int, matrix.getOwnershipRange())
    local = True
    for row in range(first, last):
        _columns, values = matrix.getRow(row)
        local = local and bool(np.all(np.isfinite(values)))
    return bool(matrix.getComm().tompi4py().allreduce(local, op=MPI.LAND))


def _petsc_matrix_effective_nnz(
    matrix: PETSc.Mat, *, tolerance: float = 1.0e-14
) -> int:
    first, last = map(int, matrix.getOwnershipRange())
    local = 0
    for row in range(first, last):
        _columns, values = matrix.getRow(row)
        local += int(np.count_nonzero(np.abs(values) > tolerance))
    comm = matrix.getComm().tompi4py()
    return int(comm.allreduce(local, op=MPI.SUM))


def _rayleigh_probe_audit(matrix: PETSc.Mat) -> dict[str, Any]:
    comm = matrix.getComm().tompi4py()
    first, last = map(int, matrix.getOwnershipRange())
    real_values: list[float] = []
    relative_imaginary_values: list[float] = []
    for probe_index in range(3):
        vector = matrix.createVecRight()
        image = matrix.createVecLeft()
        try:
            indices = np.arange(first, last, dtype=np.float64)
            vector.array[:] = np.asarray(
                (probe_index + 1.0) * (1.0 + 0.13 * indices)
                + 1j * (0.07 * indices - 0.11 * probe_index),
                dtype=PETSc.ScalarType,
            )
            vector.assemble()
            vector.scale(PETSc.ScalarType(1.0 / vector.norm()))
            matrix.mult(vector, image)
            rayleigh = complex(vector.dot(image))
            real_values.append(float(rayleigh.real))
            relative_imaginary_values.append(
                float(abs(rayleigh.imag) / max(abs(rayleigh), np.finfo(float).tiny))
            )
        finally:
            image.destroy()
            vector.destroy()
    minimum_real = float(comm.allreduce(min(real_values), op=MPI.MIN))
    maximum_relative_imag = float(
        comm.allreduce(max(relative_imaginary_values), op=MPI.MAX)
    )
    return {
        "rayleigh_probe_min_real": minimum_real,
        "rayleigh_probe_max_relative_imag": maximum_relative_imag,
        "rayleigh_probe_nonnegative": bool(
            np.isfinite(minimum_real)
            and np.isfinite(maximum_relative_imag)
            and minimum_real >= -1.0e-10
            and maximum_relative_imag <= 1.0e-10
        ),
    }


def _reduce_artificial_z_mass(
    full: PETSc.Mat,
    condensed: Any,
    raw_support: tuple[int, ...],
) -> PETSc.Mat:
    comm = full.getComm().tompi4py()
    support_index = {int(original): index for index, original in enumerate(raw_support)}
    support_size = len(raw_support)
    local_start = (support_size * comm.rank) // comm.size
    local_stop = (support_size * (comm.rank + 1)) // comm.size
    local_size = local_stop - local_start
    support_matrix = PETSc.Mat().createAIJ(
        size=((local_size, support_size), (local_size, support_size)), comm=comm
    )
    support_matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    first, last = map(int, full.getOwnershipRange())
    for row in range(first, last):
        support_row = support_index.get(row)
        if support_row is None:
            continue
        columns, values = full.getRow(row)
        selected = [
            (support_index[int(column)], value)
            for column, value in zip(columns, values, strict=True)
            if abs(value) > 1.0e-14
        ]
        if selected:
            support_matrix.setValues(
                np.asarray([support_row], dtype=PETSc.IntType),
                np.asarray(
                    [column for column, _value in selected], dtype=PETSc.IntType
                ),
                np.asarray(
                    [value for _column, value in selected], dtype=PETSc.ScalarType
                ),
            )
    support_matrix.assemble()
    local_missing = []
    for row in range(local_start, local_stop):
        columns, values = support_matrix.getRow(row)
        if not any(value != 0 for value in values):
            local_missing.append(row)
    if not comm.allreduce(not local_missing, op=MPI.LAND):
        support_matrix.destroy()
        raise ValueError("Artificial z mass lost a raw trace support row")

    transform = PETSc.Mat().createAIJ(
        size=(
            (local_size, support_size),
            (int(condensed.owned_active_rows), int(condensed.active_rows)),
        ),
        comm=comm,
    )
    transform.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    expansion = condensed.trace_constraints.expansion_by_original
    for local_row, original in enumerate(raw_support[local_start:local_stop]):
        active, coefficients = expansion[int(original)]
        transform.setValues(
            np.asarray([local_start + local_row], dtype=PETSc.IntType),
            np.asarray(active, dtype=PETSc.IntType),
            np.asarray(coefficients, dtype=PETSc.ScalarType),
        )
    transform.assemble()
    try:
        reduced = reduce_matrix_hermitian(support_matrix, transform)
    finally:
        transform.destroy()
        support_matrix.destroy()
    return reduced


def assemble_reduced_artificial_interface_tangential_mass(
    V: Any,
    condensed: Any,
    support: Mapping[str, Any],
    *,
    quadrature_degree: int | None = None,
    bare_operator: PETSc.Mat,
) -> ArtificialZTraceMass:
    """Assemble one ``dS`` tangential mass and reduce it as ``C^H M C``."""

    comm = V.mesh.comm
    raw_support = tuple(int(value) for value in support["raw_support"])
    expected_active = set(int(value) for value in support["active_support"])
    if not raw_support or not expected_active:
        raise ValueError("Artificial z support is empty")
    if bare_operator is None:
        raise ValueError("Artificial z mass requires a bare-operator identity audit")
    if int(condensed.full_rows) != int(V.dofmap.index_map.size_global):
        raise ValueError("Condensed full-row layout does not match H(curl) space")
    before_hash = _petsc_matrix_hash(bare_operator)
    dS = ufl.Measure("dS", domain=V.mesh, subdomain_data=support["facet_tags"])
    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    normal = ufl.FacetNormal(V.mesh)
    tangential_trial = ufl.cross(normal("+"), trial("+"))
    tangential_test = ufl.cross(normal("+"), test("+"))
    compiler_options = (
        {}
        if quadrature_degree is None
        else {"quadrature_degree": int(quadrature_degree)}
    )
    full = fem_petsc.assemble_matrix(
        fem.form(
            ufl.inner(tangential_trial, tangential_test)
            * dS(int(support["facet_tag"])),
            form_compiler_options=compiler_options,
        ),
        bcs=[],
    )
    full.assemble()
    try:
        full_rows, full_columns = _distributed_sparse_support(full)
        if full_rows != set(raw_support) or full_columns != set(raw_support):
            raise ValueError(
                "Artificial z mass support differs from cell/facet trace support"
            )
        full_structural_nz_used = int(
            comm.allreduce(int(full.getInfo()["nz_used"]), op=MPI.SUM)
        )
        full_effective_nnz = _petsc_matrix_effective_nnz(full)
        reduced = _reduce_artificial_z_mass(full, condensed, raw_support)
    finally:
        full.destroy()
    rows, columns = _distributed_sparse_support(reduced)
    if rows != expected_active or columns != expected_active:
        reduced.destroy()
        raise ValueError(
            "Reduced artificial z mass support differs from constraint expansion"
        )
    hermitian = PETSc.Mat()
    reduced.hermitianTranspose(hermitian)
    difference = reduced.copy()
    difference.axpy(
        PETSc.ScalarType(-1.0),
        hermitian,
        structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
    )
    hermitian_error = float(difference.norm()) / max(float(reduced.norm()), 1.0e-30)
    difference.destroy()
    hermitian.destroy()
    diagonal = reduced.createVecLeft()
    reduced.getDiagonal(diagonal)
    values = np.asarray(diagonal.array, dtype=np.complex128)
    finite = bool(comm.allreduce(bool(np.all(np.isfinite(values))), op=MPI.LAND))
    minimum_real = float(
        comm.allreduce(float(np.min(values.real, initial=np.inf)), op=MPI.MIN)
    )
    maximum_imag = float(
        comm.allreduce(float(np.max(np.abs(values.imag), initial=0.0)), op=MPI.MAX)
    )
    diagonal.destroy()
    after_hash = _petsc_matrix_hash(bare_operator)
    reduced_structural_nz_used = int(
        comm.allreduce(int(reduced.getInfo()["nz_used"]), op=MPI.SUM)
    )
    reduced_effective_nnz = _petsc_matrix_effective_nnz(reduced)
    reduced_value_hash = _petsc_matrix_hash(reduced)
    finite = bool(finite and _petsc_matrix_finite(reduced))
    rayleigh = _rayleigh_probe_audit(reduced)
    if (
        not finite
        or not np.isfinite(hermitian_error)
        or hermitian_error > 1.0e-10
        or minimum_real < -1.0e-12
        or not rayleigh["rayleigh_probe_nonnegative"]
    ):
        reduced.destroy()
        raise ValueError("Artificial z mass failed finite/Hermitian/Rayleigh audit")
    audit = {
        "facet_tag": int(support["facet_tag"]),
        "interface_z": float(support["interface_z"]),
        "facet_count_global": int(support["facet_count_global"]),
        "lower_support": support["lower_support"],
        "upper_support": support["upper_support"],
        "support_sets_exact_match": bool(support["support_sets_exact_match"]),
        "outward_normal_signs": list(support["outward_normal_signs"]),
        "mass_integral_count": 1,
        "trace_side_integrated": "+",
        "trace_mass_form": "inner(cross(n(+),u(+)),cross(n(+),v(+))) dS",
        "full_structural_nz_used": full_structural_nz_used,
        "full_thresholded_effective_nnz": full_effective_nnz,
        "reduced_structural_nz_used": reduced_structural_nz_used,
        "reduced_thresholded_effective_nnz": reduced_effective_nnz,
        "reduced_matrix_value_sha256": reduced_value_hash,
        "reduced_matrix_frobenius_norm": float(reduced.norm()),
        "raw_support_rows": len(raw_support),
        "reduced_support_rows": len(rows),
        "reduced_support_columns": len(columns),
        "reduced_support_sha256": hashlib.sha256(
            repr((tuple(sorted(rows)), tuple(sorted(columns)))).encode()
        ).hexdigest(),
        "hermitian_relative_defect": hermitian_error,
        "diagonal_real_min": minimum_real,
        "diagonal_imag_max": maximum_imag,
        "finite": finite,
        "real_diagonal_nonnegative": bool(minimum_real >= -1.0e-12),
        **rayleigh,
        "bare_operator_hash_before": before_hash,
        "bare_operator_hash_after": after_hash,
        "bare_operator_unchanged": before_hash == after_hash,
    }
    if not audit["bare_operator_unchanged"]:
        reduced.destroy()
        raise ValueError("Artificial z mass changed the bare operator")
    return ArtificialZTraceMass(matrix=reduced, audit=audit)


def build_artificial_z_tangential_trace_mass(
    system: Any,
    interface_z: float,
    *,
    tolerance: float = 1.0e-10,
    quadrature_degree: int | None = None,
    bare_operator: PETSc.Mat,
) -> ArtificialZTraceMass:
    """Audit and assemble a real two-sided artificial-z trace mass."""

    condensed = system.static_condensation.condensed
    support = audit_artificial_z_interface_support(
        system.V,
        condensed,
        interface_z,
        tolerance=tolerance,
    )
    return assemble_reduced_artificial_interface_tangential_mass(
        system.V,
        condensed,
        support,
        quadrature_degree=quadrature_degree,
        bare_operator=bare_operator,
    )


def build_first_order_petsc_interface_impedance(
    mass: ArtificialZTraceMass,
    beta: complex,
    outward_normal_signs: tuple[int, int],
) -> tuple[PETSc.Mat, PETSc.Mat]:
    """Scale one audited sparse mass with the same ``q=-i beta`` on both sides."""

    return mass.build_impedance_pair(beta, outward_normal_signs)


class SideImpedanceTransmissionAction:
    """Apply a fixed three-subdomain impedance transmission preconditioner.

    ``local_solve`` owns the local PC solve and must be source-independent.
    The action performs one forward sweep followed by one backward sweep, in
    the fixed order ``0 -> 1 -> 2 -> 1 -> 0``.  Coupling blocks are the bare
    block-tridiagonal coupling; only the local solve callback sees the
    impedance-modified blocks.
    """

    operator_identity = "task040.first_order_tangential_impedance_transmission"

    def __init__(
        self,
        *,
        global_size: int,
        local_sizes: Sequence[int],
        restriction: Sequence[Callable[[np.ndarray], np.ndarray]],
        prolongation: Sequence[Callable[[np.ndarray], np.ndarray]],
        local_solve: Sequence[Callable[[np.ndarray], np.ndarray]],
        coupling_left: Sequence[np.ndarray],
        coupling_right: Sequence[np.ndarray],
        interface_normals: Sequence[tuple[int, int]],
        restriction_prolongation_audit: Callable[[], float],
        bare_operator_identity_audit: Callable[[], bool],
        local_bare_matrices: Sequence[np.ndarray] | None = None,
        local_pc_matrices: Sequence[np.ndarray] | None = None,
        local_left_impedance: Sequence[np.ndarray] | None = None,
        local_right_impedance: Sequence[np.ndarray] | None = None,
        comm: MPI.Intracomm = MPI.COMM_WORLD,
        subdomains: Sequence[Sequence[int]] = TASK040_LEVEL_A_SUBDOMAINS,
    ) -> None:
        if tuple(tuple(int(v) for v in group) for group in subdomains) != (
            TASK040_LEVEL_A_SUBDOMAINS
        ):
            raise ValueError("Task040 transmission uses the frozen three subdomains.")
        if len(restriction) != 3 or len(prolongation) != 3 or len(local_solve) != 3:
            raise ValueError("Transmission action requires three local blocks.")
        if len(coupling_left) != 2 or len(coupling_right) != 2:
            raise ValueError("Transmission action requires two interface couplings.")
        if len(interface_normals) != 2:
            raise ValueError("Transmission action requires two interface normals.")
        if len(local_sizes) != 3 or any(int(value) <= 0 for value in local_sizes):
            raise ValueError("Transmission action requires three positive local sizes.")
        if not callable(restriction_prolongation_audit):
            raise ValueError(
                "Restriction/prolongation needs an observed audit callback."
            )
        if not callable(bare_operator_identity_audit):
            raise ValueError("Bare-F identity needs an observed audit callback.")
        self.comm = comm
        self._restriction = tuple(restriction)
        self._prolongation = tuple(prolongation)
        self._local_solve = tuple(local_solve)
        self._coupling_left = tuple(self._matrix(value) for value in coupling_left)
        self._coupling_right = tuple(self._matrix(value) for value in coupling_right)
        self._interface_normals = tuple(
            (int(pair[0]), int(pair[1])) for pair in interface_normals
        )
        if any(
            sign not in {-1, 1} for pair in self._interface_normals for sign in pair
        ) or any(left != -right for left, right in self._interface_normals):
            raise ValueError("Interface normals must be explicit opposite +/- pairs.")
        if not all(
            callable(restrict) and callable(prolong)
            for restrict, prolong in zip(self._restriction, self._prolongation)
        ):
            raise ValueError("Restriction/prolongation must be callbacks.")
        self._global_size = int(global_size)
        self._local_sizes = tuple(int(value) for value in local_sizes)
        if self._global_size <= 0:
            raise ValueError("Transmission global size must be positive.")
        self.restriction_prolongation_error = float(restriction_prolongation_audit())
        if not np.isfinite(self.restriction_prolongation_error):
            raise ValueError("Restriction/prolongation audit is non-finite.")
        if self.restriction_prolongation_error > 1.0e-12:
            raise ValueError("Restriction/prolongation does not form a partition.")
        self._bare_operator_identity_pass = bool(bare_operator_identity_audit())
        if not self._bare_operator_identity_pass:
            raise ValueError("Bare-F operator identity audit failed.")
        self._validate_couplings()
        self._validate_pc_local_identity(
            local_bare_matrices,
            local_pc_matrices,
            local_left_impedance,
            local_right_impedance,
        )
        self._apply_count = 0
        self._destroyed = False

    @staticmethod
    def _matrix(value: np.ndarray) -> np.ndarray:
        array = np.asarray(value, dtype=np.complex128)
        if array.ndim != 2 or not np.all(np.isfinite(array)):
            raise ValueError("Transmission matrix must be finite and two-dimensional.")
        return array.copy()

    def _validate_couplings(self) -> None:
        for index in range(2):
            left = self._coupling_left[index]
            right = self._coupling_right[index]
            expected = (self._local_sizes[index + 1], self._local_sizes[index])
            if left.shape != expected:
                raise ValueError("Forward coupling has the wrong local shape.")
            expected = (self._local_sizes[index], self._local_sizes[index + 1])
            if right.shape != expected:
                raise ValueError("Backward coupling has the wrong local shape.")

    def _validate_pc_local_identity(
        self,
        bare: Sequence[np.ndarray] | None,
        pc: Sequence[np.ndarray] | None,
        left: Sequence[np.ndarray] | None,
        right: Sequence[np.ndarray] | None,
    ) -> None:
        supplied = (bare, pc, left, right)
        if all(value is None for value in supplied):
            return
        if any(value is None for value in supplied) or any(
            len(value) != 3 for value in supplied if value is not None
        ):
            raise ValueError("PC identity audit requires all three local block sets.")
        for index in range(3):
            expected = (
                self._matrix(bare[index])
                + self._matrix(left[index])
                + self._matrix(right[index])
            )
            actual = self._matrix(pc[index])
            if actual.shape != expected.shape or not np.allclose(
                actual, expected, atol=1e-12, rtol=1e-12
            ):
                raise ValueError("Impedance changed the local PC identity.")
        self._pc_identity_bound = True

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        """Apply one fixed forward/backward transmission sweep."""

        if self._destroyed:
            raise RuntimeError("Side impedance transmission action is destroyed.")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self._global_size,) or not np.all(np.isfinite(source)):
            raise ValueError("Transmission RHS has the wrong shape or is non-finite.")
        values: list[np.ndarray | None] = [None, None, None]
        for index in TASK040_FORWARD_ORDER:
            local_rhs = self._checked_restriction(index, source)
            if index:
                local_rhs = (
                    local_rhs - self._coupling_left[index - 1] @ values[index - 1]
                )
            values[index] = self._checked_local_solve(index, local_rhs)
        for index in TASK040_BACKWARD_ORDER:
            local_rhs = self._checked_restriction(index, source)
            if index:
                local_rhs = (
                    local_rhs - self._coupling_left[index - 1] @ values[index - 1]
                )
            if index < 2:
                local_rhs = local_rhs - self._coupling_right[index] @ values[index + 1]
            values[index] = self._checked_local_solve(index, local_rhs)
        result = sum(
            (self._checked_prolongation(index, values[index]) for index in range(3)),
            start=np.zeros(self._global_size, dtype=np.complex128),
        )
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("Transmission action produced non-finite values.")
        self._apply_count += 1
        return result

    def _checked_restriction(self, index: int, source: np.ndarray) -> np.ndarray:
        value = np.asarray(self._restriction[index](source), dtype=np.complex128)
        if value.shape != (self._local_sizes[index],) or not np.all(np.isfinite(value)):
            raise ValueError("Restriction callback returned invalid values.")
        return value

    def _checked_prolongation(self, index: int, value: np.ndarray) -> np.ndarray:
        result = np.asarray(self._prolongation[index](value), dtype=np.complex128)
        if result.shape != (self._global_size,) or not np.all(np.isfinite(result)):
            raise ValueError("Prolongation callback returned invalid values.")
        return result

    def _checked_local_solve(self, index: int, rhs: np.ndarray) -> np.ndarray:
        value = np.asarray(self._local_solve[index](rhs), dtype=np.complex128)
        if value.shape != (self._local_sizes[index],) or not np.all(np.isfinite(value)):
            raise ValueError("Local impedance solve returned invalid values.")
        return value

    def audit(
        self,
        sources: Sequence[np.ndarray],
        *,
        bare_apply: Callable[[np.ndarray], np.ndarray] | None = None,
    ) -> dict[str, Any]:
        """Measure zero, repeat, linearity and optional bare-F contraction."""

        if not sources:
            raise ValueError("Transmission audit needs at least one source.")
        vectors = [np.asarray(source, dtype=np.complex128) for source in sources]
        zero = np.zeros(self._global_size, dtype=np.complex128)
        zero_error = float(np.linalg.norm(self.apply(zero), ord=np.inf))
        repeat_error = 0.0
        linearity_error = 0.0
        rho_values: list[float] = []
        for source in vectors:
            first = self.apply(source)
            second = self.apply(source)
            repeat_error = max(
                repeat_error,
                float(np.linalg.norm(first - second))
                / max(float(np.linalg.norm(first)), 1.0e-30),
            )
            if bare_apply is not None:
                residual = np.asarray(bare_apply(first), dtype=np.complex128) - source
                rho_values.append(
                    float(np.linalg.norm(residual))
                    / max(float(np.linalg.norm(source)), 1.0e-30)
                )
        if len(vectors) >= 2:
            a, b = vectors[:2]
            linearity = self.apply(a + b) - self.apply(a) - self.apply(b)
            linearity_error = float(np.linalg.norm(linearity)) / max(
                float(np.linalg.norm(self.apply(a + b))), 1.0e-30
            )
        local = {
            "finite": True,
            "zero_output_norm": zero_error,
            "repeat_relative_error": repeat_error,
            "linearity_relative_error": linearity_error,
            "rho": rho_values,
        }
        return {
            **local,
            "zero_map_pass": zero_error <= 1.0e-13,
            "repeat_pass": repeat_error <= 1.0e-10,
            "linearity_pass": linearity_error <= 1.0e-10,
            "rho": [
                float(self.comm.allreduce(value, op=MPI.MAX)) for value in rho_values
            ],
            "restriction_prolongation_error": self.restriction_prolongation_error,
            "restriction_prolongation_pass": self.restriction_prolongation_error
            <= 1.0e-12,
            "forward_order": list(TASK040_FORWARD_ORDER),
            "backward_order": list(TASK040_BACKWARD_ORDER),
            "interface_normals": [list(pair) for pair in self._interface_normals],
            "impedance_applied_to_pc_only": True,
            "bare_operator_unchanged": self._bare_operator_identity_pass,
            "bare_operator_identity_audited": True,
            "apply_count": int(self._apply_count),
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "operator_identity": self.operator_identity,
            "subdomains": [list(group) for group in TASK040_LEVEL_A_SUBDOMAINS],
            "forward_order": list(TASK040_FORWARD_ORDER),
            "backward_order": list(TASK040_BACKWARD_ORDER),
            "interface_normals": [list(pair) for pair in self._interface_normals],
            "global_size": self._global_size,
            "local_sizes": list(self._local_sizes),
            "restriction_prolongation_error": self.restriction_prolongation_error,
            "impedance_applied_to_pc_only": True,
            "bare_operator_unchanged": self._bare_operator_identity_pass,
            "bare_operator_identity_audited": True,
            "pc_identity_bound": bool(getattr(self, "_pc_identity_bound", False)),
            "apply_count": self._apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._local_solve = ()
        self._restriction = ()
        self._prolongation = ()
        self._coupling_left = ()
        self._coupling_right = ()
        self._destroyed = True


class _PetscTransmissionWorkspace:
    def __init__(
        self,
        scatter: PETSc.Scatter,
        template: PETSc.Vec,
        prolongation_weight: PETSc.Vec | None = None,
    ) -> None:
        self.scatter = scatter
        self.rhs = template.duplicate()
        self.y = template.duplicate()
        self.temp = template.duplicate()
        self.prolongation_weight = prolongation_weight
        self.weighted_y = (
            template.duplicate() if prolongation_weight is not None else None
        )

    def destroy(self) -> None:
        self.scatter.destroy()
        if self.weighted_y is not None:
            self.weighted_y.destroy()
        if self.prolongation_weight is not None:
            self.prolongation_weight.destroy()
        self.temp.destroy()
        self.y.destroy()
        self.rhs.destroy()


class PetscSideImpedanceTransmissionAction:
    """PETSc VecScatter carrier for the formal Level A/B route.

    This is the production carrier: all global/subdomain data stays in PETSc
    Vec/Mat ownership layouts.  Its sweep deliberately follows the existing
    ``LayerSweepAction`` cumulative-RHS semantics; the NumPy class above is
    only a tiny dense algebra oracle.
    """

    operator_identity = SideImpedanceTransmissionAction.operator_identity

    def __init__(
        self,
        *,
        parent_size: int,
        workspaces: Sequence[_PetscTransmissionWorkspace],
        local_solve: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
        coupling_left: Sequence[PETSc.Mat],
        coupling_right: Sequence[PETSc.Mat],
        interface_normals: Sequence[tuple[int, int]],
        restriction_prolongation_audit: Callable[[], float],
        bare_operator_identity_audit: Callable[[], bool],
        bare_operator: PETSc.Mat | None = None,
        multiplicative_sequence: Sequence[int] | None = None,
    ) -> None:
        if len(workspaces) != 3 or len(local_solve) != 3:
            raise ValueError("PETSc transmission requires three local workspaces.")
        if bare_operator is None and (
            len(coupling_left) != 2 or len(coupling_right) != 2
        ):
            raise ValueError("PETSc transmission requires two interface couplings.")
        if len(interface_normals) != 2 or any(
            int(left) != -int(right) or int(left) not in {-1, 1}
            for left, right in interface_normals
        ):
            raise ValueError("PETSc interface normals must be opposite +/- pairs.")
        if not callable(restriction_prolongation_audit):
            raise ValueError("PETSc R/P needs an observed audit callback.")
        if not callable(bare_operator_identity_audit):
            raise ValueError("PETSc bare-F identity needs an observed audit callback.")
        self._parent_size = int(parent_size)
        self._workspaces = tuple(workspaces)
        self._local_solve = tuple(local_solve)
        self._coupling_left = tuple(coupling_left)
        self._coupling_right = tuple(coupling_right)
        self._bare_operator = bare_operator
        if self._bare_operator is not None and any(
            workspace.prolongation_weight is None for workspace in self._workspaces
        ):
            raise ValueError("PETSc overlap action requires PoU prolongation weights.")
        self._multiplicative_sequence = (
            tuple(int(index) for index in multiplicative_sequence)
            if multiplicative_sequence is not None
            else None
        )
        if self._bare_operator is not None:
            if self._bare_operator.getSize() != (
                self._parent_size,
                self._parent_size,
            ):
                raise ValueError("PETSc overlap action bare F has the wrong size.")
            if self._multiplicative_sequence != (0, 1, 2, 2, 1, 0):
                raise ValueError(
                    "PETSc overlap action needs the frozen six-step order."
                )
            self._current = self._bare_operator.createVecRight()
            self._residual = self._bare_operator.createVecLeft()
            self._correction = self._bare_operator.createVecLeft()
        else:
            self._current = None
            self._residual = None
            self._correction = None
        self._interface_normals = tuple(
            (int(left), int(right)) for left, right in interface_normals
        )
        self.restriction_prolongation_error = float(restriction_prolongation_audit())
        if not np.isfinite(self.restriction_prolongation_error):
            raise ValueError("PETSc R/P audit is non-finite.")
        if self.restriction_prolongation_error > 1.0e-12:
            raise ValueError("PETSc R/P audit exceeds the frozen tolerance.")
        self._bare_operator_identity_pass = bool(bare_operator_identity_audit())
        if not self._bare_operator_identity_pass:
            raise ValueError("PETSc bare-F operator identity audit failed.")
        self._apply_count = 0
        self._destroyed = False

    def _gather(self, source: PETSc.Vec) -> None:
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.rhs,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )

    def _solve(self, index: int) -> None:
        self._local_solve[index](
            self._workspaces[index].rhs,
            self._workspaces[index].y,
        )

    def _forward(self) -> None:
        for index in TASK040_FORWARD_ORDER:
            workspace = self._workspaces[index]
            if index:
                self._coupling_left[index - 1].mult(
                    self._workspaces[index - 1].y,
                    workspace.temp,
                )
                workspace.rhs.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve(index)

    def _backward(self) -> None:
        for index in TASK040_BACKWARD_ORDER:
            workspace = self._workspaces[index]
            if index < 2:
                self._coupling_right[index].mult(
                    self._workspaces[index + 1].y,
                    workspace.temp,
                )
                # workspace.rhs already contains the forward lower coupling.
                workspace.rhs.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve(index)

    def _scatter_solution(self, target: PETSc.Vec) -> None:
        target.set(0.0)
        for index in range(len(self._workspaces)):
            self._scatter_one(index, target, reset=False)
        target.assemble()

    def _scatter_one(
        self,
        index: int,
        target: PETSc.Vec,
        *,
        reset: bool = True,
    ) -> None:
        if reset:
            target.set(0.0)
        workspace = self._workspaces[index]
        solution = workspace.y
        if workspace.prolongation_weight is not None:
            workspace.weighted_y.pointwiseMult(
                workspace.y, workspace.prolongation_weight
            )
            solution = workspace.weighted_y
        workspace.scatter.scatter(
            solution,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("PETSc side impedance transmission is destroyed.")
        if (
            source.getSize() != self._parent_size
            or target.getSize() != self._parent_size
        ):
            raise ValueError("PETSc transmission vector has the wrong global size.")
        if self._bare_operator is None:
            self._gather(source)
            self._forward()
            self._backward()
            self._scatter_solution(target)
        else:
            if any(
                workspace.prolongation_weight is None for workspace in self._workspaces
            ):
                raise RuntimeError("Overlap action requires PoU prolongation weights.")
            self._current.set(0.0)
            for index in self._multiplicative_sequence:
                self._bare_operator.mult(self._current, self._residual)
                self._residual.scale(PETSc.ScalarType(-1.0))
                self._residual.axpy(PETSc.ScalarType(1.0), source)
                self._gather(self._residual)
                self._solve(index)
                self._scatter_one(index, self._correction)
                self._correction.assemble()
                self._current.axpy(PETSc.ScalarType(1.0), self._correction)
            self._current.copy(target)
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "operator_identity": self.operator_identity,
            "carrier": "petsc_vecscatter",
            "global_numpy_copy": False,
            "subdomain_vectors_global_numpy_copy": False,
            "subdomains": [list(group) for group in TASK040_LEVEL_A_SUBDOMAINS],
            "forward_order": list(TASK040_FORWARD_ORDER),
            "backward_order": list(TASK040_BACKWARD_ORDER),
            "interface_normals": [list(pair) for pair in self._interface_normals],
            "restriction_prolongation_error": self.restriction_prolongation_error,
            "restriction_prolongation_pass": self.restriction_prolongation_error
            <= 1.0e-12,
            "impedance_applied_to_pc_only": True,
            "sweep_mode": (
                "multiplicative_schwarz"
                if self._bare_operator is not None
                else "cumulative_rhs"
            ),
            "multiplicative_sequence": (
                None
                if self._multiplicative_sequence is None
                else list(self._multiplicative_sequence)
            ),
            "partition_of_unity_weighted_prolongation": any(
                workspace.prolongation_weight is not None
                for workspace in self._workspaces
            ),
            "bare_operator_unchanged": self._bare_operator_identity_pass,
            "bare_operator_identity_audited": True,
            "apply_count": self._apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        for workspace in reversed(self._workspaces):
            workspace.destroy()
        self._workspaces = ()
        self._local_solve = ()
        self._coupling_left = ()
        self._coupling_right = ()
        if self._correction is not None:
            self._correction.destroy()
        if self._residual is not None:
            self._residual.destroy()
        if self._current is not None:
            self._current.destroy()
        self._correction = None
        self._residual = None
        self._current = None
        self._bare_operator = None
        self._destroyed = True


def build_side_impedance_transmission_action(
    **kwargs: Any,
) -> SideImpedanceTransmissionAction:
    """Explicit opt-in constructor for the frozen Task040 transmission route."""

    return SideImpedanceTransmissionAction(**kwargs)


def build_petsc_side_impedance_transmission_action(
    *,
    parent_template: PETSc.Vec,
    local_templates: Sequence[PETSc.Vec],
    scatters: Sequence[PETSc.Scatter],
    local_solve: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
    coupling_left: Sequence[PETSc.Mat],
    coupling_right: Sequence[PETSc.Mat],
    interface_normals: Sequence[tuple[int, int]],
    restriction_prolongation_audit: Callable[[], float],
    bare_operator_identity_audit: Callable[[], bool],
    prolongation_weights: Sequence[PETSc.Vec] | None = None,
    bare_operator: PETSc.Mat | None = None,
    multiplicative_sequence: Sequence[int] | None = None,
) -> PetscSideImpedanceTransmissionAction:
    """Build the PETSc-owned carrier without copying global arrays."""

    if len(local_templates) != 3 or len(scatters) != 3:
        raise ValueError("PETSc transmission needs three templates and scatters.")
    if prolongation_weights is not None and len(prolongation_weights) != 3:
        raise ValueError("PETSc transmission needs three PoU weight vectors.")
    workspaces = []
    try:
        workspaces = [
            _PetscTransmissionWorkspace(
                scatter,
                template,
                None if prolongation_weights is None else prolongation_weights[index],
            )
            for index, (scatter, template) in enumerate(zip(scatters, local_templates))
        ]
        return PetscSideImpedanceTransmissionAction(
            parent_size=int(parent_template.getSize()),
            workspaces=workspaces,
            local_solve=local_solve,
            coupling_left=coupling_left,
            coupling_right=coupling_right,
            interface_normals=interface_normals,
            restriction_prolongation_audit=restriction_prolongation_audit,
            bare_operator_identity_audit=bare_operator_identity_audit,
            bare_operator=bare_operator,
            multiplicative_sequence=multiplicative_sequence,
        )
    except Exception:
        for workspace in reversed(workspaces):
            workspace.destroy()
        raise


class _LevelAOracleOwner:
    """Own the Level-A factor-only objects without owning the bare operator."""

    def __init__(
        self,
        action: PetscSideImpedanceTransmissionAction,
        factors: Sequence[Any],
        parent: PETSc.Vec,
    ) -> None:
        self._action = action
        self._factors = list(factors)
        self._parent = parent
        self._destroyed = False

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "factor_count_ready": len(self._factors) if not self._destroyed else 0,
            "factor_count_after_cleanup": 0 if self._destroyed else None,
            "action_destroyed": self._action is None,
            "parent_released": bool(self._destroyed),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._action is not None:
            self._action.destroy()
            self._action = None
        for factor in reversed(self._factors):
            factor.destroy()
        self._factors.clear()
        self._parent.destroy()
        self._destroyed = True


def _make_level_a_pou_weights(
    group_rows: Sequence[np.ndarray],
    templates: Sequence[PETSc.Vec],
) -> list[PETSc.Vec]:
    membership: dict[int, int] = {}
    for rows in group_rows:
        for row in rows:
            membership[int(row)] = membership.get(int(row), 0) + 1
    weights: list[PETSc.Vec] = []
    try:
        for rows, template in zip(group_rows, templates, strict=True):
            if int(template.getLocalSize()) != len(rows):
                raise ValueError("Task040 factor ownership differs from group rows")
            weight = template.duplicate()
            weight.array[:] = np.asarray(
                [1.0 / membership[int(row)] for row in rows],
                dtype=PETSc.ScalarType,
            )
            weights.append(weight)
        return weights
    except Exception:
        for weight in weights:
            weight.destroy()
        raise


def _make_level_a_group_scatter(
    parent: PETSc.Vec,
    group_is: PETSc.IS,
    template: PETSc.Vec,
) -> PETSc.Scatter:
    first, last = map(int, template.getOwnershipRange())
    positions = PETSc.IS().createStride(
        last - first,
        first=first,
        step=1,
        comm=parent.getComm(),
    )
    try:
        return PETSc.Scatter().create(parent, group_is, template, positions)
    finally:
        positions.destroy()


def build_level_a_oracle(
    *,
    bare_f: PETSc.Mat,
    group_rows: Sequence[np.ndarray],
    interface_masses: Sequence[ArtificialZTraceMass],
    beta: complex,
    group_audit: Mapping[str, Any],
) -> tuple[PetscSideImpedanceTransmissionAction, Any, dict[str, Any]]:
    """Build the opt-in Level-A PC and its factor-only cleanup owner."""

    if len(group_rows) != 3 or len(interface_masses) != 2:
        raise ValueError("Task040 Level-A needs three groups and two interfaces")
    if not isinstance(bare_f, PETSc.Mat) or str(bare_f.getType()).lower() == "python":
        raise ValueError("Task040 Level-A requires an explicit bare F matrix")
    comm = bare_f.getComm().tompi4py()
    group_is: list[PETSc.IS] = []
    blocks: list[PETSc.Mat] = []
    factors: list[Any] = []
    pair_matrices: list[tuple[PETSc.Mat, PETSc.Mat]] = []
    templates: list[PETSc.Vec] = []
    weights: list[PETSc.Vec] = []
    scatters: list[PETSc.Scatter] = []
    parent = bare_f.createVecRight()
    action = None
    owner = None
    builder_entered = False
    try:
        for rows in group_rows:
            group_is.append(
                PETSc.IS().createGeneral(
                    np.asarray(rows, dtype=PETSc.IntType), comm=comm
                )
            )
        for mass in interface_masses:
            pair_matrices.append(
                build_first_order_petsc_interface_impedance(mass, beta, (1, -1))
            )
        for group_index, index_pairs in enumerate(((0,), (0, 1), (1,))):
            block = bare_f.createSubMatrix(group_is[group_index], group_is[group_index])
            blocks.append(block)
            try:
                for interface_index in index_pairs:
                    side_index = 0 if group_index <= interface_index else 1
                    restricted = pair_matrices[interface_index][
                        side_index
                    ].createSubMatrix(group_is[group_index], group_is[group_index])
                    try:
                        block.axpy(
                            PETSc.ScalarType(1.0),
                            restricted,
                            structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
                        )
                    finally:
                        restricted.destroy()
                block.assemble()
                factor = ResearchExactFactorInverse(
                    block,
                    factor_solver_type="mumps",
                    factor_only_storage=True,
                )
                factors.append(factor)
                factor.release_borrowed_matrix()
                templates.append(factor.operator.createVecRight())
            finally:
                block.destroy()
                blocks.pop()

        weights = _make_level_a_pou_weights(group_rows, templates)
        scatters = [
            _make_level_a_group_scatter(parent, group_is[index], templates[index])
            for index in range(3)
        ]
        bare_hash = _petsc_matrix_hash(bare_f)

        def restriction_audit() -> float:
            probe = parent.duplicate()
            restored = parent.duplicate()
            local_vectors = [template.duplicate() for template in templates]
            try:
                first, last = map(int, probe.getOwnershipRange())
                probe.array[:] = np.asarray(
                    1.0 + 0.003 * np.arange(first, last),
                    dtype=PETSc.ScalarType,
                )
                probe.assemble()
                restored.set(0.0)
                for index, scatter in enumerate(scatters):
                    scatter.scatter(
                        probe,
                        local_vectors[index],
                        addv=PETSc.InsertMode.INSERT_VALUES,
                        mode=PETSc.ScatterMode.FORWARD,
                    )
                    local_vectors[index].pointwiseMult(
                        local_vectors[index], weights[index]
                    )
                    scatter.scatter(
                        local_vectors[index],
                        restored,
                        addv=PETSc.InsertMode.ADD_VALUES,
                        mode=PETSc.ScatterMode.REVERSE,
                    )
                restored.assemble()
                difference = restored.copy()
                try:
                    difference.axpy(PETSc.ScalarType(-1.0), probe)
                    return float(difference.norm()) / max(float(probe.norm()), 1.0e-30)
                finally:
                    difference.destroy()
            finally:
                for vector in local_vectors:
                    vector.destroy()
                restored.destroy()
                probe.destroy()

        def bare_identity_audit() -> bool:
            return _petsc_matrix_hash(bare_f) == bare_hash

        builder_entered = True
        action = build_petsc_side_impedance_transmission_action(
            parent_template=parent,
            local_templates=templates,
            scatters=scatters,
            local_solve=tuple(factor.solve for factor in factors),
            coupling_left=(),
            coupling_right=(),
            interface_normals=((1, -1), (1, -1)),
            restriction_prolongation_audit=restriction_audit,
            bare_operator_identity_audit=bare_identity_audit,
            prolongation_weights=weights,
            bare_operator=bare_f,
            multiplicative_sequence=TASK040_FORWARD_ORDER + TASK040_BACKWARD_ORDER,
        )
        weights = []
        scatters = []
        for template in templates:
            template.destroy()
        templates.clear()
        for group in group_is:
            group.destroy()
        group_is.clear()
        for pair in pair_matrices:
            for matrix in pair:
                matrix.destroy()
        pair_matrices.clear()
        factor_records = [
            {
                "factor_solver_type": factor.factor_solver_type,
                "factor_only_storage": bool(factor.factor_only_storage),
                "direct_factor_count": int(factor.diagnostics["direct_factor_count"]),
                "ksp_created": bool(factor.diagnostics["ksp_created"]),
                "ksp_destroyed": bool(factor.diagnostics["ksp_destroyed"]),
            }
            for factor in factors
        ]
        factor_count_ready = sum(
            record["direct_factor_count"] for record in factor_records
        )
        if factor_count_ready != 3:
            raise RuntimeError(
                f"Task040 expected three ready cross-section factors, got {factor_count_ready}"
            )
        diagnostics = {
            "factor_records": factor_records,
            "factor_count_ready": factor_count_ready,
            "group_audit": dict(group_audit),
            "bare_operator_hash": bare_hash,
            "restriction_prolongation_error": float(
                action.restriction_prolongation_error
            ),
            "factor_owner": "level_a_oracle_owner",
            "oracle_only": True,
            "scalable_candidate": False,
            "cross_section_factor_count_ready": factor_count_ready,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        }
        action_result = action
        owner = _LevelAOracleOwner(action_result, factors, parent)
        action = None
        factors = []
        parent = None
        return action_result, owner, diagnostics
    except Exception:
        if owner is not None:
            owner.destroy()
        elif action is not None:
            action.destroy()
        if not builder_entered:
            for scatter in scatters:
                scatter.destroy()
            for weight in weights:
                weight.destroy()
        for template in templates:
            template.destroy()
        for group in group_is:
            group.destroy()
        for pair in pair_matrices:
            for matrix in pair:
                matrix.destroy()
        for block in blocks:
            block.destroy()
        for factor in factors:
            factor.destroy()
        if parent is not None:
            parent.destroy()
        raise


def audit_petsc_level_a_one_apply(
    action: PetscSideImpedanceTransmissionAction,
    bare_operator: PETSc.Mat,
    sources: Mapping[str, PETSc.Vec] | Sequence[PETSc.Vec],
    factor_inventory: Mapping[str, Any],
    *,
    labels: Sequence[str] = TASK040_LEVEL_A_SOURCE_LABELS,
    preferred_labels: Sequence[str] = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    ),
    collect_scalar_contractions: bool = False,
) -> dict[str, Any]:
    """Audit one PETSc Level-A action on the frozen six-source family.

    The action and factor inventory are observed by the caller; this helper
    only computes true bare-F residuals and the zero/repeat/linearity gates.
    It never assembles or factorizes an operator.
    """

    labels = tuple(labels)
    preferred_labels = tuple(preferred_labels)
    comm = bare_operator.getComm().tompi4py()
    local_ok = len(labels) == 6 and len(set(labels)) == 6
    try:
        if isinstance(sources, Mapping):
            local_ok = local_ok and tuple(sources) == labels
            source_list = tuple(sources[label] for label in labels)
        else:
            source_list = tuple(sources)
            local_ok = local_ok and len(source_list) == len(labels)
        matrix_rows, matrix_cols = bare_operator.getSize()
        local_ok = local_ok and matrix_rows == matrix_cols
        local_ok = local_ok and all(
            isinstance(source, PETSc.Vec) and source.getSize() == matrix_rows
            for source in source_list
        )
    except (KeyError, TypeError, ValueError):
        source_list = ()
        local_ok = False
    if not bool(comm.allreduce(local_ok, op=MPI.LAND)):
        raise ValueError("Level-A source/operator contract failed collectively.")

    action_diagnostics = action.diagnostics
    action_identity = {
        "carrier": action_diagnostics.get("carrier"),
        "global_numpy_copy": action_diagnostics.get("global_numpy_copy"),
        "subdomain_vectors_global_numpy_copy": action_diagnostics.get(
            "subdomain_vectors_global_numpy_copy"
        ),
        "restriction_prolongation_pass": action_diagnostics.get(
            "restriction_prolongation_pass"
        ),
        "bare_operator_unchanged": action_diagnostics.get("bare_operator_unchanged"),
    }
    action_identity_local = (
        action_identity["carrier"] == "petsc_vecscatter"
        and action_identity["global_numpy_copy"] is False
        and action_identity["subdomain_vectors_global_numpy_copy"] is False
        and action_identity["restriction_prolongation_pass"] is True
        and action_identity["bare_operator_unchanged"] is True
    )
    action_identity_pass = bool(comm.allreduce(action_identity_local, op=MPI.LAND))

    inventory = dict(factor_inventory)
    inventory_pass = all(
        (
            inventory.get("observed") is True,
            inventory.get("factor_count_ready") == 3,
            inventory.get("oracle_only") is True,
            inventory.get("scalable_candidate") is False,
            inventory.get("full_side_exact_factor_count") == 0,
            inventory.get("global_direct_factor_count") == 0,
            inventory.get("nested_ksp_count") == 0,
        )
    )
    inventory_pass = bool(comm.allreduce(inventory_pass, op=MPI.LAND))
    outputs: dict[str, PETSc.Vec] = {}
    scalar_y_vectors: dict[str, PETSc.Vec] = {}
    scalar_records: dict[str, dict[str, Any]] = {}
    reports: list[dict[str, Any]] = []
    finite_pass = True
    try:
        for label, source in zip(labels, source_list):
            target = source.duplicate()
            residual = source.duplicate()
            repeated = source.duplicate()
            difference = source.duplicate()
            try:
                source_finite = bool(np.all(np.isfinite(source.array_r)))
                source_finite = bool(comm.allreduce(source_finite, op=MPI.LAND))
                action.apply(source, target)
                output_finite = bool(np.all(np.isfinite(target.array_r)))
                output_finite = bool(comm.allreduce(output_finite, op=MPI.LAND))
                finite_pass = finite_pass and source_finite and output_finite
                source_norm = float(source.norm())
                output_norm = float(target.norm())
                bare_operator.mult(target, residual)
                if collect_scalar_contractions and label != labels[0]:
                    scalar_y = residual.duplicate()
                    residual.copy(scalar_y)
                    scalar_y_vectors[label] = scalar_y
                    y_finite = bool(np.all(np.isfinite(scalar_y.array_r)))
                    y_finite = bool(comm.allreduce(y_finite, op=MPI.LAND))
                    scalar_records[label] = {
                        "source_norm": source_norm,
                        "source_norm_squared": float(
                            np.real(complex(source.dot(source)))
                        ),
                        "x_norm_squared": float(np.real(complex(target.dot(target)))),
                        "y_norm": float(scalar_y.norm()),
                        "y_norm_squared": float(
                            np.real(complex(scalar_y.dot(scalar_y)))
                        ),
                    }
                residual.axpy(PETSc.ScalarType(-1.0), source)
                residual_norm = float(residual.norm())
                rho = residual_norm / source_norm if source_norm > 1.0e-30 else None
                if collect_scalar_contractions and label != labels[0]:
                    scalar_records[label].update(
                        {
                            "true_residual_norm": residual_norm,
                            "original_rho": rho,
                            "finite": source_finite and output_finite and y_finite,
                        }
                    )
                action.apply(source, repeated)
                target.copy(difference)
                difference.axpy(PETSc.ScalarType(-1.0), repeated)
                repeat_error = float(difference.norm()) / max(output_norm, 1.0e-30)
                outputs[label] = target.duplicate()
                target.copy(outputs[label])
                reports.append(
                    {
                        "label": label,
                        "source_norm": source_norm,
                        "output_norm": output_norm,
                        "true_residual_norm": residual_norm,
                        "true_residual_relative": rho,
                        "repeat_error": repeat_error,
                        "finite": source_finite and output_finite,
                        "physical_zero": label == labels[0] and source_norm <= 1.0e-13,
                    }
                )
            finally:
                difference.destroy()
                repeated.destroy()
                residual.destroy()
                target.destroy()

        mandatory = [report for report in reports if not report["physical_zero"]]
        preferred = [
            report for report in mandatory if report["label"] in preferred_labels
        ]
        linear_source = source_list[1].duplicate()
        linear_source.axpy(PETSc.ScalarType(1.0), source_list[2])
        linear_target = linear_source.duplicate()
        expected_linear = outputs[labels[1]].duplicate()
        try:
            expected_linear.axpy(PETSc.ScalarType(1.0), outputs[labels[2]])
            action.apply(linear_source, linear_target)
            linear_target.axpy(PETSc.ScalarType(-1.0), expected_linear)
            linearity_error = float(linear_target.norm()) / max(
                float(expected_linear.norm()), 1.0e-30
            )
        finally:
            expected_linear.destroy()
            linear_target.destroy()
            linear_source.destroy()

        physical = reports[0]
        physical_zero = bool(physical["physical_zero"])
        zero_map_pass: bool | str = (
            physical["output_norm"] <= 1.0e-13 if physical_zero else "not_applicable"
        )
        worst_rho = max(float(report["true_residual_relative"]) for report in mandatory)
        all_repeat_pass = all(report["repeat_error"] <= 1.0e-10 for report in reports)
        mandatory_rho_pass = all(
            float(report["true_residual_relative"]) < 1.0 for report in mandatory
        )
        preferred_rho_pass = all(
            float(report["true_residual_relative"]) <= 0.90 for report in preferred
        )
        gate = {
            "finite_pass": bool(finite_pass),
            "zero_map_pass": zero_map_pass,
            "action_identity_pass": action_identity_pass,
            "repeat_pass": all_repeat_pass,
            "linearity_relative_error": linearity_error,
            "linearity_pass": linearity_error <= 1.0e-10,
            "mandatory_rho_pass": mandatory_rho_pass,
            "worst_mandatory_rho": worst_rho,
            "worst_rho_pass": worst_rho <= 0.95,
            "preferred_rho_pass": preferred_rho_pass,
            "factor_inventory_pass": inventory_pass,
        }
        gate["pass"] = bool(
            gate["finite_pass"]
            and gate["zero_map_pass"] is not False
            and gate["action_identity_pass"]
            and gate["repeat_pass"]
            and gate["linearity_pass"]
            and gate["mandatory_rho_pass"]
            and gate["worst_rho_pass"]
            and gate["preferred_rho_pass"]
            and gate["factor_inventory_pass"]
        )
        result = {
            "source_labels": list(labels),
            "reports": reports,
            "factor_inventory": inventory,
            "action_identity": action_identity,
            "gate": gate,
            "action_apply_count_delta": action.diagnostics["apply_count"]
            - action_diagnostics["apply_count"],
            "formal_source_apply_count": len(reports),
            "repeat_audit_apply_count": len(reports),
            "linearity_audit_apply_count": 1,
        }
        if collect_scalar_contractions:
            nonzero_labels = tuple(labels[1:])

            def pairs(values: np.ndarray) -> list[list[list[float]]]:
                return [
                    [[float(np.real(value)), float(np.imag(value))] for value in row]
                    for row in values
                ]

            b_vectors = tuple(source_list[1:])
            y_vectors = tuple(scalar_y_vectors[label] for label in nonzero_labels)
            bhb = np.empty(
                (len(nonzero_labels), len(nonzero_labels)), dtype=np.complex128
            )
            bhy = np.empty_like(bhb)
            yhy = np.empty_like(bhb)
            for row, (b_vector, y_vector) in enumerate(
                zip(b_vectors, y_vectors, strict=True)
            ):
                for column, (other_b, other_y) in enumerate(
                    zip(b_vectors, y_vectors, strict=True)
                ):
                    bhb[row, column] = complex(other_b.dot(b_vector))
                    bhy[row, column] = complex(other_y.dot(b_vector))
                    yhy[row, column] = complex(other_y.dot(y_vector))
            result["scalar_contractions"] = {
                "labels": list(nonzero_labels),
                "BHB": pairs(bhb),
                "BHY": pairs(bhy),
                "YHY": pairs(yhy),
                "per_source": scalar_records,
            }
        return result
    finally:
        for output in outputs.values():
            output.destroy()
        for vector in scalar_y_vectors.values():
            vector.destroy()
