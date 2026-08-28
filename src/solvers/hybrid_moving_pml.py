"""Research-only moving-PML full-state PC for the Task040 fallback route.

The physical bare ``F`` is borrowed and remains the outer residual carrier.
Each auxiliary group uses a temporary material-by-side PML tagging and an
action-only assembly-time condensation.  Only the selected overlap-cell
contributions are assembled on one owner; no auxiliary global matrix or
extended factor is created.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np
import ufl
from dolfinx import fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.common.pml_3d import z_pml_diagonal_tensors
from src.geometry.tetra_mesh_audit import owned_cell_geometry
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from src.solvers.hybrid_side_impedance import _petsc_matrix_hash
from src.solvers.physical_slab_two_level import (
    assemble_owner_local_slab_matrix,
    build_owner_local_slab_plan,
)


__all__ = (
    "MovingPMLBuildDiagnostics",
    "MovingPMLFullStateAction",
    "build_moving_pml_full_state_action",
)


_SWEEP = (0, 1, 2, 2, 1, 0)
_GROUP_LAYERS = ((0, 1, 2, 3), (0, 1, 2, 3, 4, 5), (2, 3, 4, 5))
_MATERIAL_NAMES = ("air", "substrate", "grating")


@dataclass(frozen=True)
class MovingPMLBuildDiagnostics:
    """JSON-safe build identity shared by all three local PML groups."""

    bare_f_hash_before: str
    bare_f_hash_after: str
    global_auxiliary_matrix: bool = False
    numeric_allgather: bool = False
    sweep: tuple[int, ...] = _SWEEP
    pml_profile: str = "quadratic"
    integrated_attenuation: float = 6.0
    inner_gmres_max_it: int = 2
    cleanup: str = "action_owns_groups_and_work_vectors_borrows_bare_f"

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sweep"] = list(self.sweep)
        return value


def _material_eps(cfg: Any) -> dict[int, tuple[str, complex]]:
    tags = cfg.tags
    return {
        int(tags.air): ("air", complex(cfg.eps_air)),
        int(tags.substrate): ("substrate", complex(cfg.eps_substrate)),
        int(tags.grating): ("grating", complex(cfg.eps_grating)),
    }


def _pml_tag_map(cfg: Any) -> dict[tuple[str, int], int]:
    tag_values = [int(value) for value in vars(cfg.tags).values()]
    next_tag = max(tag_values, default=0) + 100
    result: dict[tuple[str, int], int] = {}
    for side_index, side in enumerate(("bottom", "top")):
        for material_index, material in enumerate(_MATERIAL_NAMES):
            result[(side, material_index)] = next_tag + 10 * side_index + material_index
    return result


def _temporary_pml_cell_tags(
    mesh_data: Any,
    cfg: Any,
    pml_cells_by_side: Mapping[str, Sequence[int]],
) -> tuple[mesh.MeshTags, dict[tuple[str, int], int], dict[str, Any]]:
    """Copy material tags and replace only selected collar cells."""

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    original = {
        int(cell): int(tag)
        for cell, tag in zip(
            mesh_data.cell_tags.indices,
            mesh_data.cell_tags.values,
            strict=True,
        )
    }
    material_eps = _material_eps(cfg)
    tag_map = _pml_tag_map(cfg)
    side_by_cell: dict[int, str] = {}
    for side in ("bottom", "top"):
        for raw_cell in pml_cells_by_side.get(side, ()):
            cell = int(raw_cell)
            if cell < 0 or cell >= owned_cells:
                raise ValueError(f"moving-PML collar cell {cell} is not owned")
            if cell in side_by_cell:
                raise ValueError(f"moving-PML collar cell {cell} has two sides")
            side_by_cell[cell] = side
    values = np.empty(owned_cells, dtype=np.int32)
    physical_counts = {material: 0 for material in _MATERIAL_NAMES}
    counts: dict[str, int] = {}
    for cell in range(owned_cells):
        if cell not in original:
            raise RuntimeError(f"owned cell {cell} has no physical material tag")
        material_tag = int(original[cell])
        side = side_by_cell.get(cell)
        if side is None:
            values[cell] = material_tag
            material = material_eps.get(material_tag)
            if material is not None:
                physical_counts[material[0]] += 1
            continue
        material = material_eps.get(material_tag)
        if material is None:
            raise ValueError(
                f"moving-PML collar cell {cell} has non-material tag {material_tag}"
            )
        material_name = material[0]
        material_index = _MATERIAL_NAMES.index(material_name)
        values[cell] = tag_map[(side, material_index)]
        key = f"{side}:{material_name}"
        counts[key] = counts.get(key, 0) + 1
    tags = mesh.meshtags(
        msh,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        values,
    )
    comm = msh.comm
    global_counts = {
        f"{side}:{material}": int(
            comm.allreduce(counts.get(f"{side}:{material}", 0), op=MPI.SUM)
        )
        for side in ("bottom", "top")
        for material in _MATERIAL_NAMES
    }
    global_physical_counts = {
        material: int(comm.allreduce(physical_counts[material], op=MPI.SUM))
        for material in _MATERIAL_NAMES
    }
    return tags, tag_map, {
        "material_side_tags": {
            f"{side}:{material}": int(tag_map[(side, index)])
            for side in ("bottom", "top")
            for index, material in enumerate(_MATERIAL_NAMES)
        },
        "collar_cell_counts_local": counts,
        "collar_cell_counts_global": global_counts,
        "physical_material_counts_local": physical_counts,
        "physical_material_counts_global": global_physical_counts,
    }


def _build_auxiliary_pml_form(
    msh: mesh.Mesh,
    function_space: Any,
    cell_tags: mesh.MeshTags,
    cfg: Any,
    pml_tags: Mapping[tuple[str, int], int],
    physical_counts: Mapping[str, int],
    pml_counts: Mapping[str, int],
):
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    a = PETSc.ScalarType(0.0) * ufl.inner(u, v) * dx
    material_eps = _material_eps(cfg)
    physical_tags = []
    for material_tag, (name, epsilon) in material_eps.items():
        if int(physical_counts.get(name, 0)) <= 0:
            continue
        physical_tags.append(material_tag)
        a += (
            PETSc.ScalarType(1.0 / cfg.mu_r) * ufl.inner(curl_u, curl_v) * dx(material_tag)
            - cfg.k0**2 * PETSc.ScalarType(epsilon) * ufl.inner(u, v) * dx(material_tag)
        )
    if float(cfg.divergence_penalty) > 0.0:
        a += PETSc.ScalarType(cfg.divergence_penalty) * ufl.inner(
            ufl.div(u), ufl.div(v)
        ) * dx(tuple(physical_tags))
    x = ufl.SpatialCoordinate(msh)
    for side in ("bottom", "top"):
        thickness = float(
            cfg.pml_bottom_thickness if side == "bottom" else cfg.pml_top_thickness
        )
        if thickness <= 0.0:
            continue
        for material_index, material_name in enumerate(_MATERIAL_NAMES):
            side_material = f"{side}:{material_name}"
            if int(pml_counts.get(side_material, 0)) <= 0:
                continue
            epsilon = next(
                epsilon
                for _tag, (name, epsilon) in material_eps.items()
                if name == material_name
            )
            eps_pml, mu_inverse_pml = z_pml_diagonal_tensors(
                x, cfg, side, epsilon
            )
            a += (
                ufl.inner(mu_inverse_pml * curl_u, curl_v)
                - cfg.k0**2 * ufl.inner(eps_pml * u, v)
            ) * dx(pml_tags[(side, material_index)])
    return a


def _group_cfg(cfg: Any, z_values: np.ndarray, group: int) -> Any:
    low = float(z_values[2 * group])
    high = float(z_values[2 * group + 2])
    bottom = (
        float(z_values[2 * group] - z_values[2 * group - 2]) if group > 0 else 0.0
    )
    top = (
        float(z_values[2 * group + 4] - z_values[2 * group + 2])
        if group < 2
        else 0.0
    )
    return replace(
        cfg,
        z_min=low,
        z_max=high,
        use_pml=True,
        pml_bottom_thickness=bottom,
        pml_top_thickness=top,
        pml_alpha=6.0,
    )


def _cell_layer(record: Any, z_values: np.ndarray) -> int:
    centroid = float(np.mean(record.coordinates[:, 2]))
    layer = int(np.searchsorted(z_values, centroid, side="right") - 1)
    if layer < 0 or layer >= 6:
        raise ValueError(f"moving-PML cell centroid has invalid z layer {layer}")
    return layer


def _group_cells(
    plan: Any,
    records: Sequence[Any],
    z_values: np.ndarray,
    group: int,
) -> tuple[dict[str, tuple[int, ...]], dict[str, Any]]:
    selected = plan.local_cell_indices_by_slab[group]
    if len(set(selected)) != len(selected):
        raise RuntimeError(f"moving-PML group {group} selected duplicate cells")
    pml: dict[str, list[int]] = {"bottom": [], "top": []}
    layer_counts: dict[str, int] = {}
    allowed = set(_GROUP_LAYERS[group])
    for cell in selected:
        layer = _cell_layer(records[cell], z_values)
        if layer not in allowed:
            raise RuntimeError(
                f"moving-PML group {group} selected cell {cell} in layer {layer}; "
                f"expected layers {sorted(allowed)}"
            )
        layer_counts[str(layer)] = layer_counts.get(str(layer), 0) + 1
        if group == 0 and layer in (2, 3):
            pml["top"].append(cell)
        elif group == 1 and layer in (0, 1):
            pml["bottom"].append(cell)
        elif group == 1 and layer in (4, 5):
            pml["top"].append(cell)
        elif group == 2 and layer in (2, 3):
            pml["bottom"].append(cell)
    comm = plan.comm
    return {side: tuple(cells) for side, cells in pml.items()}, {
        "selected_cells_local": len(selected),
        "selected_cells_global": int(comm.allreduce(len(selected), op=MPI.SUM)),
        "collar_cells_local": sum(len(cells) for cells in pml.values()),
        "collar_cells_global": int(
            comm.allreduce(sum(len(cells) for cells in pml.values()), op=MPI.SUM)
        ),
        "selected_layer_counts_local": layer_counts,
    }


def _route_core_rows(
    plan: Any,
    core_group_rows: Sequence[np.ndarray],
) -> tuple[tuple[np.ndarray, ...], tuple[dict[int, int], ...]]:
    if len(core_group_rows) != 3:
        raise ValueError("moving-PML needs three core row closures")
    comm = plan.comm
    local_membership: dict[int, int] = {}
    normalized: list[np.ndarray] = []
    for raw_rows in core_group_rows:
        rows = np.unique(np.asarray(raw_rows, dtype=PETSc.IntType))
        if rows.size and (int(rows[0]) < 0 or int(rows[-1]) >= int(plan.active_rows)):
            raise ValueError("moving-PML core row closure is outside bare-F")
        normalized.append(rows)
    for rows in normalized:
        for row in rows:
            local_membership[int(row)] = local_membership.get(int(row), 0) + 1
    packets: list[list[tuple[int, int, int]]] = [[] for _ in range(comm.size)]
    for group, rows in enumerate(normalized):
        owner = int(plan.slab_owners[group])
        packets[owner].extend(
            (group, int(row), int(local_membership[int(row)])) for row in rows
        )
    incoming = comm.alltoall(packets)
    owner_rows: list[dict[int, int]] = [dict() for _ in range(3)]
    for packet in incoming:
        for group, row, membership in packet:
            if row in owner_rows[group]:
                raise RuntimeError(f"moving-PML core row {row} arrived twice")
            owner_rows[group][row] = int(membership)
    result_rows: list[np.ndarray] = []
    for group, owner in enumerate(plan.slab_owners):
        rows = np.asarray(sorted(owner_rows[group]), dtype=PETSc.IntType)
        if comm.rank != owner:
            rows = np.empty(0, dtype=PETSc.IntType)
        extended = np.asarray(plan.owner_rows[group], dtype=PETSc.IntType)
        if rows.size and not np.all(np.isin(rows, extended, assume_unique=True)):
            raise RuntimeError(f"moving-PML core rows escape extended group {group}")
        result_rows.append(rows)
    return tuple(result_rows), tuple(owner_rows)


def _make_scatter(template: PETSc.Vec, rows: np.ndarray):
    rows = np.asarray(rows, dtype=PETSc.IntType)
    sequential = PETSc.Vec().createSeq(int(rows.size), comm=PETSc.COMM_SELF)
    global_is = PETSc.IS().createGeneral(rows, comm=PETSc.COMM_SELF)
    local_is = PETSc.IS().createStride(
        int(rows.size), first=0, step=1, comm=PETSc.COMM_SELF
    )
    try:
        scatter = PETSc.Scatter().create(template, global_is, sequential, local_is)
    finally:
        local_is.destroy()
        global_is.destroy()
    return scatter, sequential


def _owner_submatrix(
    matrix: PETSc.Mat,
    owner: int,
    rows: np.ndarray,
    comm: MPI.Intracomm,
) -> PETSc.Mat | None:
    local_rows = rows if comm.rank == owner else np.empty(0, dtype=PETSc.IntType)
    index_set = PETSc.IS().createGeneral(local_rows, comm=PETSc.COMM_SELF)
    try:
        submatrices = matrix.createSubMatrices([index_set])
    finally:
        index_set.destroy()
    submatrix = submatrices[0]
    if comm.rank != owner:
        if submatrix is not None:
            submatrix.destroy()
        return None
    if submatrix is None or submatrix.getSize() != (rows.size, rows.size):
        if submatrix is not None:
            submatrix.destroy()
        raise RuntimeError("moving-PML core factor extraction returned wrong size")
    return submatrix


class _CoreCollarPC:
    def __init__(
        self,
        core_factor: ResearchExactFactorInverse,
        core_rhs: PETSc.Vec,
        core_solution: PETSc.Vec,
        core_positions: np.ndarray,
        collar_positions: np.ndarray,
        collar_diagonal_inverse: np.ndarray,
    ) -> None:
        self.core_factor = core_factor
        self.core_rhs = core_rhs
        self.core_solution = core_solution
        self.core_positions = core_positions
        self.collar_positions = collar_positions
        self.collar_diagonal_inverse = collar_diagonal_inverse

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.set(0.0)
        source_values = source.getArray(readonly=True)
        target_values = target.getArray()
        if self.core_positions.size:
            self.core_rhs.getArray()[:] = source_values[self.core_positions]
            self.core_solution.set(0.0)
            self.core_factor.solve(self.core_rhs, self.core_solution)
            target_values[self.core_positions] = self.core_solution.getArray(
                readonly=True
            )
        if self.collar_positions.size:
            target_values[self.collar_positions] = (
                self.collar_diagonal_inverse * source_values[self.collar_positions]
            )


class _MovingPMLGroup:
    def __init__(
        self,
        *,
        group: int,
        owner: int,
        owner_rows: np.ndarray,
        core_rows: np.ndarray,
        membership: Mapping[int, int],
        bare_f: PETSc.Mat,
        auxiliary_matrix: PETSc.Mat | None,
        group_audit: Mapping[str, Any],
    ) -> None:
        self.group = int(group)
        self.owner = int(owner)
        self.comm = bare_f.getComm().tompi4py()
        self.owner_rows = np.asarray(owner_rows, dtype=PETSc.IntType).copy()
        self.core_rows = np.asarray(core_rows, dtype=PETSc.IntType).copy()
        self._destroyed = False
        self._scatter = None
        self._rhs = None
        self._solution = None
        self._weighted_solution = None
        self._local_residual = None
        self._auxiliary_matrix = auxiliary_matrix
        self._core_matrix = None
        self._core_factor = None
        self._core_rhs = None
        self._core_solution = None
        self._local_ksp = None
        self._pc_context = None
        self._group_audit = dict(group_audit)
        self._last_inner = {
            "initial_true_residual": 0.0,
            "final_true_residual": 0.0,
            "ratio": 0.0,
            "iterations": 0,
        }
        try:
            template = bare_f.createVecRight()
            try:
                self._scatter, self._rhs = _make_scatter(template, self.owner_rows)
            finally:
                template.destroy()
            self._solution = self._rhs.duplicate()
            self._weighted_solution = self._rhs.duplicate()
            self._local_residual = self._rhs.duplicate()
            if self.comm.rank == self.owner:
                if self._auxiliary_matrix is None:
                    raise RuntimeError(f"moving-PML group {group} has no owner matrix")
                owner_positions = np.searchsorted(self.owner_rows, self.core_rows)
                if self.core_rows.size and (
                    np.any(owner_positions >= self.owner_rows.size)
                    or not np.all(self.owner_rows[owner_positions] == self.core_rows)
                ):
                    raise RuntimeError(f"moving-PML group {group} core rows are not owner aligned")
                self._core_positions = np.asarray(owner_positions, dtype=PETSc.IntType)
                self._collar_positions = np.setdiff1d(
                    np.arange(self.owner_rows.size, dtype=PETSc.IntType),
                    self._core_positions,
                    assume_unique=True,
                )
                weights = np.asarray(
                    [1.0 / int(membership[int(row)]) for row in self.core_rows],
                    dtype=PETSc.ScalarType,
                )
                self._core_weights = weights
            self._core_matrix = _owner_submatrix(
                bare_f,
                self.owner,
                self.core_rows,
                self.comm,
            )
            if self.comm.rank == self.owner:
                assert self._core_matrix is not None
                core_matrix_nnz = int(
                    self._core_matrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"]
                )
                self._core_rhs = self._core_matrix.createVecRight()
                self._core_solution = self._core_matrix.createVecLeft()
                self._core_factor = ResearchExactFactorInverse(
                    self._core_matrix,
                    factor_solver_type="mumps",
                    factor_only_storage=True,
                )
                self._core_factor.release_borrowed_matrix()
                self._core_matrix.destroy()
                self._core_matrix = None
                diagonal = self._auxiliary_matrix.createVecLeft()
                try:
                    self._auxiliary_matrix.getDiagonal(diagonal)
                    diagonal_values = np.asarray(
                        diagonal.getArray(readonly=True), dtype=PETSc.ScalarType
                    ).copy()
                finally:
                    diagonal.destroy()
                collar_diagonal_values = diagonal_values[self._collar_positions]
                if np.any(collar_diagonal_values == 0.0):
                    raise RuntimeError(
                        f"moving-PML group {group} auxiliary collar diagonal contains zero"
                    )
                if not np.all(np.isfinite(collar_diagonal_values)):
                    raise RuntimeError(
                        f"moving-PML group {group} auxiliary collar diagonal is non-finite"
                    )
                diagonal_inverse = np.asarray(
                    1.0 / collar_diagonal_values,
                    dtype=PETSc.ScalarType,
                )
                self._pc_context = _CoreCollarPC(
                    self._core_factor,
                    self._core_rhs,
                    self._core_solution,
                    self._core_positions,
                    self._collar_positions,
                    diagonal_inverse,
                )
                self._local_ksp = PETSc.KSP().create(PETSc.COMM_SELF)
                self._local_ksp.setOperators(self._auxiliary_matrix)
                self._local_ksp.setType("gmres")
                self._local_ksp.setGMRESRestart(2)
                self._local_ksp.setNormType(PETSc.KSP.NormType.NONE)
                self._local_ksp.setInitialGuessNonzero(False)
                self._local_ksp.setTolerances(rtol=0.0, atol=0.0, max_it=2)
                local_pc = self._local_ksp.getPC()
                local_pc.setType("python")
                local_pc.setPythonContext(self._pc_context)
                self._local_ksp.setUp()
                self._group_audit.update(
                    {
                        "owner_local_rows": int(self.owner_rows.size),
                        "core_rows": int(self.core_rows.size),
                        "collar_rows": int(self._collar_positions.size),
                        "auxiliary_nnz": int(
                            self._auxiliary_matrix.getInfo(PETSc.Mat.InfoType.LOCAL)[
                                "nz_used"
                            ]
                        ),
                        "core_factor_nnz": core_matrix_nnz,
                        "core_factor_diagnostics": dict(self._core_factor.diagnostics),
                        "core_factor_count": 1,
                        "extended_factor_count": 0,
                        "extended_matrix_factorized": False,
                        "core_only_weight_sum_error": float(
                            np.max(
                                np.abs(
                                    self._core_weights
                                    * np.asarray(
                                        [membership[int(row)] for row in self.core_rows],
                                        dtype=PETSc.ScalarType,
                                    )
                                    - 1.0
                                ),
                                initial=0.0,
                            )
                        ),
                    }
                )
            else:
                self._core_positions = np.empty(0, dtype=PETSc.IntType)
                self._collar_positions = np.empty(0, dtype=PETSc.IntType)
                self._core_weights = np.empty(0, dtype=PETSc.ScalarType)
            local_factor_count = int(self._core_factor is not None)
            self._group_audit["global_core_factor_count"] = int(
                self.comm.allreduce(local_factor_count, op=MPI.SUM)
            )
        except Exception:
            self.destroy()
            raise

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("moving-PML group has been destroyed")
        target.set(0.0)
        self._scatter.scatter(
            source,
            self._rhs,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        if self.comm.rank == self.owner:
            self._solution.set(0.0)
            self._local_ksp.solve(self._rhs, self._solution)
            rhs_norm = float(self._rhs.norm())
            self._auxiliary_matrix.mult(self._solution, self._local_residual)
            self._local_residual.axpy(PETSc.ScalarType(-1.0), self._rhs)
            final_norm = float(self._local_residual.norm())
            self._last_inner = {
                "initial_true_residual": rhs_norm,
                "final_true_residual": final_norm,
                "ratio": final_norm / max(rhs_norm, np.finfo(float).tiny),
                "iterations": int(self._local_ksp.getIterationNumber()),
            }
            if self._last_inner["iterations"] != 2:
                raise RuntimeError(
                    f"moving-PML group {self.group} fixed GMRES used "
                    f"{self._last_inner['iterations']} iterations, expected 2"
                )
            self._weighted_solution.set(0.0)
            self._weighted_solution.getArray()[self._core_positions] = (
                self._core_weights
                * self._solution.getArray(readonly=True)[self._core_positions]
            )
        else:
            self._solution.set(0.0)
            self._weighted_solution.set(0.0)
        self._scatter.scatter(
            self._weighted_solution,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        target.assemble()

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self.comm.rank == self.owner:
            local_inner = self._last_inner
        else:
            local_inner = {
                "initial_true_residual": 0.0,
                "final_true_residual": 0.0,
                "ratio": 0.0,
                "iterations": 0,
            }
        diagnostics = dict(self._group_audit)
        diagnostics["group"] = self.group
        diagnostics["owner_rank"] = self.owner
        diagnostics["inner"] = dict(local_inner)
        diagnostics["destroyed"] = self._destroyed
        diagnostics["collar_prolongation_weight"] = 0.0
        return diagnostics

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._local_ksp is not None:
            self._local_ksp.destroy()
        if self._core_factor is not None:
            self._core_factor.destroy()
            self._core_factor = None
        for vector_name in (
            "_local_residual",
            "_weighted_solution",
            "_solution",
            "_rhs",
            "_core_solution",
            "_core_rhs",
        ):
            vector = getattr(self, vector_name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, vector_name, None)
        for matrix_name in ("_auxiliary_matrix", "_core_matrix"):
            matrix = getattr(self, matrix_name, None)
            if matrix is not None:
                matrix.destroy()
                setattr(self, matrix_name, None)
        if self._scatter is not None:
            self._scatter.destroy()
            self._scatter = None
        self._pc_context = None
        self._local_ksp = None
        self._destroyed = True


class MovingPMLFullStateAction:
    """Borrowed bare-F multiplicative moving-PML pilot action."""

    def __init__(
        self,
        bare_f: PETSc.Mat,
        groups: Sequence[_MovingPMLGroup],
        build_diagnostics: MovingPMLBuildDiagnostics,
    ) -> None:
        if len(groups) != 3:
            raise ValueError("moving-PML action needs exactly three groups")
        self._bare_f = bare_f
        self._groups = tuple(groups)
        self._build_diagnostics = build_diagnostics
        self._current = None
        self._residual = None
        self._correction = None
        self._apply_count = 0
        self._destroyed = False
        try:
            self._current = bare_f.createVecRight()
            self._residual = bare_f.createVecLeft()
            self._correction = bare_f.createVecLeft()
        except Exception:
            for group in reversed(self._groups):
                group.destroy()
            self._groups = ()
            raise

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("moving-PML action has been destroyed")
        expected = self._bare_f.getSize()[0]
        if source.getSize() != expected or target.getSize() != expected:
            raise ValueError("moving-PML vectors do not match bare-F size")
        self._current.set(0.0)
        for group in _SWEEP:
            self._bare_f.mult(self._current, self._residual)
            self._residual.scale(PETSc.ScalarType(-1.0))
            self._residual.axpy(PETSc.ScalarType(1.0), source)
            self._groups[group].apply(self._residual, self._correction)
            self._current.axpy(PETSc.ScalarType(1.0), self._correction)
        self._current.copy(target)
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        after_hash = (
            self._build_diagnostics.bare_f_hash_after
            if self._destroyed
            else _petsc_matrix_hash(self._bare_f)
        )
        return {
            **self._build_diagnostics.as_dict(),
            "bare_f_hash_after_observed": after_hash,
            "bare_f_unchanged": (
                self._build_diagnostics.bare_f_hash_before == after_hash
            ),
            "groups": [group.diagnostics for group in self._groups],
            "apply_count": self._apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        for group in reversed(self._groups):
            group.destroy()
        for vector in (self._correction, self._residual, self._current):
            if vector is not None:
                vector.destroy()
        self._groups = ()
        self._bare_f = None
        self._destroyed = True


def build_moving_pml_full_state_action(
    system: Any,
    bare_f: PETSc.Mat,
    core_group_rows: Sequence[np.ndarray],
) -> MovingPMLFullStateAction:
    """Build the fixed three-group moving-PML mechanism pilot.

    ``system`` supplies the already-created mesh, H(curl) space, and Floquet
    MPC.  The auxiliary forms are temporary and use the same space/MPC; the
    caller retains ownership of ``system`` and ``bare_f``.
    """

    if not isinstance(bare_f, PETSc.Mat):
        raise TypeError("moving-PML bare_f must be a PETSc matrix")
    local_mesh = system.local_mesh
    z_values = np.asarray(local_mesh.z_values, dtype=np.float64)
    if z_values.shape != (7,) or np.any(np.diff(z_values) <= 0.0):
        raise ValueError("moving-PML requires six ordered z layers")
    condensed = system.static_condensation.condensed
    if bare_f.getSize() != (condensed.active_rows, condensed.active_rows):
        raise ValueError("moving-PML bare_f and condensation sizes disagree")
    comm = bare_f.getComm().tompi4py()
    f_hash_before = _petsc_matrix_hash(bare_f)
    plan = build_owner_local_slab_plan(
        condensed,
        local_mesh.mesh,
        domain_z=(float(z_values[0]), float(z_values[-1])),
        num_slabs=3,
        overlap_fraction=0.0,
    )
    core_rows_by_owner, core_membership = _route_core_rows(plan, core_group_rows)
    records = owned_cell_geometry(local_mesh.mesh)
    groups: list[_MovingPMLGroup] = []
    try:
        for group in range(3):
            pml_cells, cell_audit = _group_cells(
                plan, records, z_values, group
            )
            group_cfg = _group_cfg(system.cfg, z_values, group)
            temporary_tags, pml_tags, tag_audit = _temporary_pml_cell_tags(
                local_mesh.mesh_data,
                group_cfg,
                pml_cells,
            )
            form = _build_auxiliary_pml_form(
                local_mesh.mesh,
                system.V,
                temporary_tags,
                group_cfg,
                pml_tags,
                tag_audit["physical_material_counts_global"],
                tag_audit["collar_cell_counts_global"],
            )
            auxiliary = None
            auxiliary_matrix = None
            try:
                auxiliary = build_unconstrained_assembly_time_condensation(
                    fem.form(form),
                    system.V,
                    temporary_tags,
                    mpc=getattr(system.floquet_data, "mpc", None),
                    materialize_global_matrix=False,
                    retain_local_schur_for_matrix_free=True,
                )
                if auxiliary.matrix is not None:
                    raise RuntimeError("moving-PML auxiliary global matrix was materialized")
                auxiliary_matrix, matrix_audit = assemble_owner_local_slab_matrix(
                    auxiliary,
                    plan,
                    group,
                )
            finally:
                if auxiliary is not None:
                    auxiliary.destroy()
            group_audit = {
                **cell_audit,
                **tag_audit,
                "pml_profile": "quadratic",
                "integrated_attenuation": 6.0,
                "pml_alpha": 6.0,
                "core_bounds": [
                    float(z_values[2 * group]),
                    float(z_values[2 * group + 2]),
                ],
                "pml_bottom_thickness": float(group_cfg.pml_bottom_thickness),
                "pml_top_thickness": float(group_cfg.pml_top_thickness),
                "global_auxiliary_matrix": False,
                "numeric_allgather": False,
                "compiled_physical_materials": [
                    material
                    for material in _MATERIAL_NAMES
                    if tag_audit["physical_material_counts_global"][material] > 0
                ],
                "compiled_pml_material_sides": [
                    key
                    for key in tag_audit["collar_cell_counts_global"]
                    if tag_audit["collar_cell_counts_global"][key] > 0
                ],
                "owners": list(plan.slab_owners),
                "matrix_audit": dict(matrix_audit),
            }
            groups.append(
                _MovingPMLGroup(
                    group=group,
                    owner=int(plan.slab_owners[group]),
                    owner_rows=plan.owner_rows[group],
                    core_rows=core_rows_by_owner[group],
                    membership=core_membership[group],
                    bare_f=bare_f,
                    auxiliary_matrix=auxiliary_matrix,
                    group_audit=group_audit,
                )
            )
        f_hash_after = _petsc_matrix_hash(bare_f)
        if f_hash_before != f_hash_after:
            raise RuntimeError("moving-PML setup changed the borrowed bare-F matrix")
        build_audit = MovingPMLBuildDiagnostics(
            bare_f_hash_before=f_hash_before,
            bare_f_hash_after=f_hash_after,
        )
        return MovingPMLFullStateAction(bare_f, groups, build_audit)
    except Exception:
        for group in reversed(groups):
            group.destroy()
        raise
