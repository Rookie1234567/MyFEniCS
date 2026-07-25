"""Typed physical z-slab partitions for assembly-time-condensed trace rows.

The assembly-time-condensed operator uses active coordinates rather than the
original H(curl) DoF numbers.  A physical Schwarz smoother must therefore not
guess slab membership from contiguous PETSc row ranges.  This module converts
owned-cell support into active trace rows through the exact trace expansion and
adds each DtN auxiliary row only to its physical top or bottom boundary slab.

The builder is collective and fail closed.  It refuses incomplete active-row
coverage, invalid auxiliary-side metadata, empty physical slabs, or rows
outside the assembled reduced operator.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .physical_slab_two_level import gather_global_subdomain_indices


def _canonical_partition_sha256(
    subdomains: Sequence[np.ndarray],
    *,
    trace_rows: int,
    dtn_auxiliary_rows: int,
    dtn_side_by_aux: Sequence[str],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        np.asarray(
            [trace_rows, dtn_auxiliary_rows, len(subdomains)],
            dtype=np.int64,
        ).tobytes()
    )
    for side in dtn_side_by_aux:
        encoded = side.encode("ascii")
        digest.update(np.asarray([len(encoded)], dtype=np.int64).tobytes())
        digest.update(encoded)
    for slab, rows in enumerate(subdomains):
        normalized = np.asarray(rows, dtype=np.int64)
        digest.update(np.asarray([slab, normalized.size], dtype=np.int64).tobytes())
        digest.update(normalized.tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class CondensedPhysicalSlabPartition:
    """Validated active-row partition for a physical z-slab smoother."""

    subdomains: tuple[np.ndarray, ...]
    trace_rows: int
    dtn_auxiliary_rows: int
    dtn_side_by_aux: tuple[str, ...]
    domain_z_min: float
    domain_z_max: float
    overlap_layers: float
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        trace_rows = int(self.trace_rows)
        auxiliary_rows = int(self.dtn_auxiliary_rows)
        sides = tuple(str(side) for side in self.dtn_side_by_aux)
        if trace_rows <= 0 or auxiliary_rows <= 0:
            raise ValueError(
                "condensed physical-slab partition requires positive trace "
                "and DtN auxiliary row counts"
            )
        if len(sides) != auxiliary_rows:
            raise ValueError(
                "one physical top/bottom side is required per DtN auxiliary row"
            )
        if any(side not in {"top", "bottom"} for side in sides):
            raise ValueError("DtN auxiliary sides must be 'top' or 'bottom'")
        if not self.subdomains:
            raise ValueError(
                "condensed physical-slab partition requires at least one slab"
            )
        if not np.isfinite(self.domain_z_min) or not np.isfinite(
            self.domain_z_max
        ):
            raise ValueError("physical z bounds must be finite")
        if self.domain_z_max <= self.domain_z_min:
            raise ValueError("physical z bounds must have positive extent")
        if not np.isfinite(self.overlap_layers) or self.overlap_layers < 0.0:
            raise ValueError("physical-slab overlap must be finite and nonnegative")

        matrix_rows = trace_rows + auxiliary_rows
        normalized: list[np.ndarray] = []
        coverage = np.zeros(matrix_rows, dtype=np.int32)
        for slab, raw_rows in enumerate(self.subdomains):
            rows = np.unique(np.asarray(raw_rows, dtype=PETSc.IntType))
            if rows.size == 0:
                raise ValueError(f"physical z-slab {slab} is empty")
            if int(rows[0]) < 0 or int(rows[-1]) >= matrix_rows:
                raise ValueError(
                    f"physical z-slab {slab} contains an out-of-range row"
                )
            rows.setflags(write=False)
            normalized.append(rows)
            coverage[rows] += 1
        if np.any(coverage == 0):
            missing = np.flatnonzero(coverage == 0)
            raise ValueError(
                "physical z-slab partition does not cover every reduced row; "
                f"missing rows {missing[:8].tolist()}"
            )

        auxiliary_membership = {
            row: [
                slab
                for slab, rows in enumerate(normalized)
                if np.any(rows == trace_rows + row)
            ]
            for row in range(auxiliary_rows)
        }
        final_slab = len(normalized) - 1
        for row, side in enumerate(sides):
            expected = 0 if side == "bottom" else final_slab
            if auxiliary_membership[row] != [expected]:
                raise ValueError(
                    "DtN auxiliary row is not confined to its physical "
                    f"boundary slab: row={row}, side={side}, "
                    f"memberships={auxiliary_membership[row]}"
                )

        audit = dict(self.audit)
        if audit.get("capability_pass") is not True:
            raise ValueError(
                "physical z-slab partition requires an affirmative capability "
                "audit"
            )
        expected_sha = _canonical_partition_sha256(
            normalized,
            trace_rows=trace_rows,
            dtn_auxiliary_rows=auxiliary_rows,
            dtn_side_by_aux=sides,
        )
        if audit.get("partition_sha256") != expected_sha:
            raise ValueError(
                "physical z-slab partition audit hash does not match its rows"
            )
        object.__setattr__(self, "subdomains", tuple(normalized))
        object.__setattr__(self, "trace_rows", trace_rows)
        object.__setattr__(self, "dtn_auxiliary_rows", auxiliary_rows)
        object.__setattr__(self, "dtn_side_by_aux", sides)
        object.__setattr__(self, "audit", MappingProxyType(audit))

    @property
    def matrix_rows(self) -> int:
        return self.trace_rows + self.dtn_auxiliary_rows


def build_condensed_physical_z_slab_partition(
    *,
    comm: MPI.Comm,
    owned_cell_midpoint_z: np.ndarray,
    owned_cell_original_dofs: Sequence[np.ndarray],
    expansion_by_original: Mapping[
        int,
        tuple[np.ndarray, np.ndarray],
    ],
    trace_rows: int,
    dtn_side_by_aux: Sequence[str],
    domain_z_min: float,
    domain_z_max: float,
    num_slabs: int,
    overlap_layers: float,
) -> CondensedPhysicalSlabPartition:
    """Map physical owned-cell support to active condensed trace rows.

    ``expansion_by_original`` is the exact map
    ``u_original_trace = C_t q_active`` from
    :class:`~src.solvers.hcurl_assembly_time_condensation.TraceConstraintMap`.
    Original cell-interior DoFs are absent from that map and are intentionally
    ignored.  Active rows reached through periodic slave pullbacks are included
    in the same physical slabs as their supporting original trace entities.
    """

    trace_rows = int(trace_rows)
    num_slabs = int(num_slabs)
    midpoint_z = np.asarray(owned_cell_midpoint_z, dtype=np.float64)
    if midpoint_z.ndim != 1:
        raise ValueError("owned cell midpoint z coordinates must be one-dimensional")
    if len(owned_cell_original_dofs) != midpoint_z.size:
        raise ValueError(
            "owned cell midpoint and original-DoF arrays must have equal length"
        )
    if not np.all(np.isfinite(midpoint_z)):
        raise ValueError("owned cell midpoint z coordinates must be finite")
    if trace_rows <= 0:
        raise ValueError("active condensed trace row count must be positive")
    if num_slabs <= 0:
        raise ValueError("physical z-slab count must be positive")
    if not np.isfinite(domain_z_min) or not np.isfinite(domain_z_max):
        raise ValueError("physical z bounds must be finite")
    if domain_z_max <= domain_z_min:
        raise ValueError("physical z bounds must have positive extent")
    if not np.isfinite(overlap_layers) or overlap_layers < 0.0:
        raise ValueError("physical-slab overlap must be finite and nonnegative")

    sides = tuple(str(side) for side in dtn_side_by_aux)
    if not sides:
        raise ValueError(
            "physical z-slab partition requires positive DtN auxiliary rows"
        )
    if any(side not in {"top", "bottom"} for side in sides):
        raise ValueError("DtN auxiliary sides must be 'top' or 'bottom'")

    edges = np.linspace(
        float(domain_z_min),
        float(domain_z_max),
        num_slabs + 1,
    )
    width = float(domain_z_max - domain_z_min) / num_slabs
    local_trace_pieces: list[np.ndarray] = []
    for slab in range(num_slabs):
        low = float(edges[slab] - overlap_layers * width)
        high = float(edges[slab + 1] + overlap_layers * width)
        selected_cells = np.flatnonzero(
            (midpoint_z >= low) & (midpoint_z <= high)
        )
        active_rows: list[np.ndarray] = []
        for cell in selected_cells:
            original_dofs = np.asarray(
                owned_cell_original_dofs[int(cell)],
                dtype=PETSc.IntType,
            )
            if original_dofs.ndim != 1:
                raise ValueError("owned cell original DoFs must be 1D arrays")
            for original in original_dofs:
                expansion = expansion_by_original.get(int(original))
                if expansion is None:
                    continue
                rows, values = expansion
                rows = np.asarray(rows, dtype=PETSc.IntType)
                values = np.asarray(values, dtype=PETSc.ScalarType)
                if rows.ndim != 1 or values.ndim != 1 or rows.size != values.size:
                    raise ValueError(
                        "trace expansion rows and values must be matching 1D "
                        "arrays"
                    )
                if rows.size and (
                    int(rows.min()) < 0 or int(rows.max()) >= trace_rows
                ):
                    raise ValueError(
                        "trace expansion contains an out-of-range active row"
                    )
                nonzero = np.flatnonzero(np.abs(values) > 0.0)
                if nonzero.size:
                    active_rows.append(rows[nonzero])
        local_trace_pieces.append(
            np.unique(np.concatenate(active_rows)).astype(
                PETSc.IntType,
                copy=False,
            )
            if active_rows
            else np.empty(0, dtype=PETSc.IntType)
        )

    global_trace_slabs = gather_global_subdomain_indices(
        local_trace_pieces,
        comm=comm,
    )
    trace_coverage = np.zeros(trace_rows, dtype=np.int32)
    for rows in global_trace_slabs:
        trace_coverage[rows] += 1
    if np.any(trace_coverage == 0):
        missing = np.flatnonzero(trace_coverage == 0)
        raise ValueError(
            "owned-cell physical map does not cover every active trace row; "
            f"missing rows {missing[:8].tolist()}"
        )

    augmented_slabs = [rows.copy() for rows in global_trace_slabs]
    bottom_auxiliary = np.asarray(
        [
            trace_rows + row
            for row, side in enumerate(sides)
            if side == "bottom"
        ],
        dtype=PETSc.IntType,
    )
    top_auxiliary = np.asarray(
        [
            trace_rows + row
            for row, side in enumerate(sides)
            if side == "top"
        ],
        dtype=PETSc.IntType,
    )
    if bottom_auxiliary.size:
        augmented_slabs[0] = np.unique(
            np.concatenate((augmented_slabs[0], bottom_auxiliary))
        ).astype(PETSc.IntType, copy=False)
    if top_auxiliary.size:
        augmented_slabs[-1] = np.unique(
            np.concatenate((augmented_slabs[-1], top_auxiliary))
        ).astype(PETSc.IntType, copy=False)

    partition_sha256 = _canonical_partition_sha256(
        augmented_slabs,
        trace_rows=trace_rows,
        dtn_auxiliary_rows=len(sides),
        dtn_side_by_aux=sides,
    )
    trace_membership_total = int(
        sum(np.count_nonzero(rows < trace_rows) for rows in augmented_slabs)
    )
    audit = {
        "schema_version": "task035b.condensed-physical-z-slab-partition.v1",
        "status": "physical_active_trace_partition_qualified",
        "capability_pass": True,
        "row_space": "active_condensed_trace_plus_physical_dtn_auxiliary",
        "mapping_source": (
            "owned cell support through exact original-trace-to-active-row "
            "expansion"
        ),
        "periodic_slave_pullback_applied": True,
        "inactive_trace_rows_added": False,
        "trace_rows": trace_rows,
        "dtn_auxiliary_rows": len(sides),
        "matrix_rows": trace_rows + len(sides),
        "num_physical_z_slabs": num_slabs,
        "overlap_layers": float(overlap_layers),
        "domain_z_min": float(domain_z_min),
        "domain_z_max": float(domain_z_max),
        "slab_row_counts": [int(rows.size) for rows in augmented_slabs],
        "trace_row_membership_total": trace_membership_total,
        "trace_row_maximum_multiplicity": int(trace_coverage.max(initial=0)),
        "bottom_auxiliary_rows": int(bottom_auxiliary.size),
        "top_auxiliary_rows": int(top_auxiliary.size),
        "all_active_trace_rows_covered": True,
        "all_auxiliary_rows_covered_once_on_physical_side": True,
        "partition_sha256": partition_sha256,
        "ordinary_default_changed": False,
    }
    return CondensedPhysicalSlabPartition(
        subdomains=tuple(augmented_slabs),
        trace_rows=trace_rows,
        dtn_auxiliary_rows=len(sides),
        dtn_side_by_aux=sides,
        domain_z_min=float(domain_z_min),
        domain_z_max=float(domain_z_max),
        overlap_layers=float(overlap_layers),
        audit=audit,
    )


def build_condensed_physical_z_slab_partition_from_space(
    function_space,
    condensed_system,
    *,
    dtn_side_by_aux: Sequence[str],
    domain_z_min: float,
    domain_z_max: float,
    num_slabs: int,
    overlap_layers: float,
) -> CondensedPhysicalSlabPartition:
    """Adapt an actual DOLFINx space and condensed system to the typed map.

    Only owned cells are enumerated.  Their full-space local DoFs are converted
    to original global DoF numbers before the exact trace expansion is applied;
    cell-interior DoFs are absent from that expansion and therefore never enter
    the slab row sets.
    """

    from dolfinx import mesh as dolfinx_mesh

    msh = function_space.mesh
    communicator_relation = MPI.Comm.Compare(
        condensed_system.matrix.getComm().tompi4py(),
        msh.comm,
    )
    if communicator_relation not in (MPI.IDENT, MPI.CONGRUENT):
        raise ValueError(
            "condensed operator and function-space mesh communicators differ"
        )
    tdim = int(msh.topology.dim)
    owned_cells = np.arange(
        msh.topology.index_map(tdim).size_local,
        dtype=np.int32,
    )
    midpoint_z = np.asarray(
        dolfinx_mesh.compute_midpoints(msh, tdim, owned_cells)[:, 2],
        dtype=np.float64,
    )
    dofmap = function_space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "condensed physical z-slabs require scalar-blocked H(curl)"
        )
    owned_cell_original_dofs = tuple(
        np.asarray(
            dofmap.index_map.local_to_global(
                np.asarray(dofmap.cell_dofs(int(cell)), dtype=np.int32)
            ),
            dtype=PETSc.IntType,
        )
        for cell in owned_cells
    )
    trace_constraints = condensed_system.trace_constraints
    if int(trace_constraints.active_rows) != int(
        condensed_system.active_rows
    ):
        raise ValueError(
            "condensed trace-constraint and active-row counts disagree"
        )
    return build_condensed_physical_z_slab_partition(
        comm=msh.comm,
        owned_cell_midpoint_z=midpoint_z,
        owned_cell_original_dofs=owned_cell_original_dofs,
        expansion_by_original=trace_constraints.expansion_by_original,
        trace_rows=int(condensed_system.active_rows),
        dtn_side_by_aux=dtn_side_by_aux,
        domain_z_min=domain_z_min,
        domain_z_max=domain_z_max,
        num_slabs=num_slabs,
        overlap_layers=overlap_layers,
    )


__all__ = [
    "CondensedPhysicalSlabPartition",
    "build_condensed_physical_z_slab_partition",
    "build_condensed_physical_z_slab_partition_from_space",
]
