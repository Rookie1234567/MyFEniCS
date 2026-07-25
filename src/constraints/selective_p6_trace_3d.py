"""Pure MPI row plan for an exact-sequence-closed selective p6 trace shell.

This module does not inspect a mesh, communicate with MPI, or construct a
PETSc matrix.  It consumes an already qualified
``ExactSequenceClosedP6TraceNumbering`` plus caller-supplied ownership and
allgather-like row counts.  Every rank owns its base rows first and then all
missing-p6 modes for the selected periodic orbits whose canonical
representative entity it owns.

Inactive missing-p6 modes never receive row descriptors.  The complete-p6
matrix is therefore not a hidden intermediate of this numbering layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import pairwise
import json
from numbers import Integral
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from src.adaptivity.selective_p6_trace_exact_sequence import (
    ExactSequenceClosedP6TraceNumbering,
)
from src.adaptivity.selective_p6_trace_orbits import PeriodicP6TraceOrbit


LogicalOrbitMode = tuple[int, int]
RowRange = tuple[int, int]


def _validated_sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


def _validated_count_vector(
    values: Sequence[int],
    *,
    label: str,
) -> tuple[int, ...]:
    result: list[int] = []
    for rank, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError(f"{label}[{rank}] must be an integer")
        count = int(value)
        if count < 0:
            raise ValueError(f"{label}[{rank}] must be nonnegative")
        result.append(count)
    if not result:
        raise ValueError(f"{label} must contain at least one rank")
    return tuple(result)


def _selected_orbits_and_validate_serial_numbering(
    closed_numbering: ExactSequenceClosedP6TraceNumbering,
) -> tuple[PeriodicP6TraceOrbit, ...]:
    if closed_numbering.audit.get("pass") is not True:
        raise ValueError("exact-sequence closed numbering is not qualified")
    closure = closed_numbering.closure
    numbering = closed_numbering.numbering
    if closure.audit.get("pass") is not True:
        raise ValueError("exact-sequence closure is not qualified")
    if numbering.audit.get("pass") is not True:
        raise ValueError("selective trace numbering is not qualified")

    selected_orbits = tuple(
        sorted(
            (orbit for orbit in numbering.orbits if orbit.selected),
            key=lambda orbit: orbit.representative_entity_id,
        )
    )
    inactive_orbits = tuple(
        orbit for orbit in numbering.orbits if not orbit.selected
    )
    selected_representatives = tuple(
        orbit.representative_entity_id for orbit in selected_orbits
    )
    if selected_representatives != (
        closure.selected_trace_representative_ids
    ):
        raise RuntimeError(
            "selected periodic orbits disagree with exact-sequence closure"
        )
    selected_physical_entities = tuple(
        sorted(
            member
            for orbit in selected_orbits
            for member in orbit.member_entity_ids
        )
    )
    if selected_physical_entities != closure.selected_physical_entity_ids:
        raise RuntimeError(
            "selected physical entities are not complete periodic orbits"
        )
    if numbering.selected_entity_ids != closure.selected_physical_entity_ids:
        raise RuntimeError(
            "numbered physical selection disagrees with exact-sequence closure"
        )
    if set(numbering.entity_active_row_ranges) != set(
        selected_physical_entities
    ):
        raise RuntimeError(
            "serial row ranges do not cover exactly the selected entities"
        )
    if any(
        orbit.active_row_start is not None
        or orbit.active_row_stop is not None
        for orbit in inactive_orbits
    ):
        raise RuntimeError("inactive periodic orbit has a serial row range")

    cursor = int(numbering.active_base_rows)
    observed_ranges: set[RowRange] = set()
    for orbit in selected_orbits:
        start = orbit.active_row_start
        stop = orbit.active_row_stop
        if start is None or stop is None:
            raise RuntimeError("selected periodic orbit has no serial rows")
        row_range = (int(start), int(stop))
        if row_range[0] != cursor:
            relation = "overlap" if row_range[0] < cursor else "gap"
            raise RuntimeError(
                f"selected periodic orbit serial row ranges contain a "
                f"{relation}"
            )
        if row_range[1] - row_range[0] != orbit.missing_mode_count:
            raise RuntimeError(
                "selected periodic orbit row range has the wrong mode count"
            )
        if row_range in observed_ranges:
            raise RuntimeError("selected periodic orbit row ranges overlap")
        if any(
            numbering.entity_active_row_ranges.get(member) != row_range
            for member in orbit.member_entity_ids
        ):
            raise RuntimeError(
                "periodic orbit members do not share the representative rows"
            )
        observed_ranges.add(row_range)
        cursor = row_range[1]
    if cursor != numbering.active_rows:
        raise RuntimeError(
            "selected periodic orbit serial row ranges do not close active rows"
        )

    full3d_increment = sum(
        orbit.full3d_equivalent_dof_cost for orbit in selected_orbits
    )
    quotient_increment = sum(
        orbit.missing_mode_count for orbit in selected_orbits
    )
    if full3d_increment != closure.full3d_equivalent_increment:
        raise RuntimeError("selected physical Full3D increment is inconsistent")
    if quotient_increment != closure.active_row_increment:
        raise RuntimeError("selected quotient active increment is inconsistent")
    if numbering.full3d_equivalent_increment != full3d_increment:
        raise RuntimeError("numbering Full3D increment is inconsistent")
    if numbering.active_row_increment != quotient_increment:
        raise RuntimeError("numbering active-row increment is inconsistent")
    if numbering.active_rows != (
        numbering.active_base_rows + quotient_increment
    ):
        raise RuntimeError("numbering active-row total is inconsistent")
    return selected_orbits


def canonical_selective_p6_trace_selection_sha256(
    *,
    closed_numbering: ExactSequenceClosedP6TraceNumbering,
    geometry_key_sha256: str,
    ordered_trace_basis_sha256: str,
) -> str:
    """Hash the physical selection independently of its MPI repartition."""

    geometry_hash = _validated_sha256(
        geometry_key_sha256,
        label="geometry key SHA256",
    )
    basis_hash = _validated_sha256(
        ordered_trace_basis_sha256,
        label="ordered trace basis SHA256",
    )
    selected_orbits = _selected_orbits_and_validate_serial_numbering(
        closed_numbering
    )
    payload = {
        "schema": "task035b.selective-p6-trace-selection.v1",
        "geometry_key_sha256": geometry_hash,
        "ordered_trace_basis_sha256": basis_hash,
        "selected_orbits": [
            {
                "representative_entity_id": orbit.representative_entity_id,
                "member_entity_ids": list(orbit.member_entity_ids),
                "entity_kind": orbit.entity_kind,
                "missing_mode_count": orbit.missing_mode_count,
            }
            for orbit in selected_orbits
        ],
        "full3d_base_dofs": closed_numbering.numbering.full3d_base_dofs,
        "full3d_equivalent_increment": (
            closed_numbering.closure.full3d_equivalent_increment
        ),
        "quotient_active_increment": (
            closed_numbering.closure.active_row_increment
        ),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SelectedP6TraceOwnedRow:
    """One active missing-p6 quotient row."""

    representative_entity_id: int
    mode_index: int
    entity_kind: str
    physical_member_entity_ids: tuple[int, ...]
    owner_rank: int
    petsc_row: int

    @property
    def logical_orbit_mode(self) -> LogicalOrbitMode:
        return (self.representative_entity_id, self.mode_index)


@dataclass(frozen=True)
class SelectiveP6TraceMPIRowPlan:
    """Contiguous PETSc ownership plus canonical logical-row permutation."""

    mpi_size: int
    petsc_ownership_ranges: tuple[RowRange, ...]
    rank_base_row_ranges: tuple[RowRange, ...]
    rank_selected_trace_row_ranges: tuple[RowRange, ...]
    owned_base_row_counts_by_rank: tuple[int, ...]
    owned_selected_trace_row_counts_by_rank: tuple[int, ...]
    owned_selected_orbit_representatives_by_rank: tuple[tuple[int, ...], ...]
    selected_orbit_owner_ranks: Mapping[int, int]
    selected_row_descriptors: tuple[SelectedP6TraceOwnedRow, ...]
    canonical_logical_orbit_modes: tuple[LogicalOrbitMode, ...]
    petsc_rows_in_canonical_logical_order: tuple[int, ...]
    logical_orbit_mode_to_petsc_row: Mapping[LogicalOrbitMode, int]
    petsc_row_to_logical_orbit_mode: Mapping[int, LogicalOrbitMode]
    full3d_base_dofs: int
    full3d_equivalent_increment: int
    full3d_equivalent_dofs: int
    full3d_dof_limit: int | None
    active_base_rows: int
    quotient_active_increment: int
    active_rows: int
    geometry_key_sha256: str
    ordered_trace_basis_sha256: str
    selection_sha256: str
    actual_mesh: bool
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("selective p6 trace MPI row plan is not qualified")
        object.__setattr__(
            self,
            "selected_orbit_owner_ranks",
            MappingProxyType(
                {
                    int(representative): int(owner)
                    for representative, owner in (
                        self.selected_orbit_owner_ranks.items()
                    )
                }
            ),
        )
        object.__setattr__(
            self,
            "logical_orbit_mode_to_petsc_row",
            MappingProxyType(
                {
                    (int(key[0]), int(key[1])): int(row)
                    for key, row in (
                        self.logical_orbit_mode_to_petsc_row.items()
                    )
                }
            ),
        )
        object.__setattr__(
            self,
            "petsc_row_to_logical_orbit_mode",
            MappingProxyType(
                {
                    int(row): (int(key[0]), int(key[1]))
                    for row, key in (
                        self.petsc_row_to_logical_orbit_mode.items()
                    )
                }
            ),
        )


def _validated_owner_map(
    owner_ranks: Mapping[int, int],
    *,
    selected_orbits: Sequence[PeriodicP6TraceOrbit],
    mpi_size: int,
) -> dict[int, int]:
    selected_representatives = {
        orbit.representative_entity_id for orbit in selected_orbits
    }
    raw_keys = set(owner_ranks)
    if raw_keys != selected_representatives:
        missing = sorted(selected_representatives - raw_keys)
        extra = sorted(raw_keys - selected_representatives)
        raise RuntimeError(
            "representative owner map must cover exactly whole selected "
            f"orbits: missing={missing}, extra={extra}"
        )
    result: dict[int, int] = {}
    for representative, value in owner_ranks.items():
        if (
            isinstance(representative, bool)
            or not isinstance(representative, Integral)
        ):
            raise TypeError("selected orbit representative must be an integer")
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError("selected orbit owner rank must be an integer")
        normalized_representative = int(representative)
        owner = int(value)
        if owner < 0 or owner >= mpi_size:
            raise ValueError(
                "selected orbit owner rank is outside the MPI communicator"
            )
        result[normalized_representative] = owner
    return result


def _prefix_ranges(counts: Sequence[int]) -> tuple[RowRange, ...]:
    ranges: list[RowRange] = []
    cursor = 0
    for count in counts:
        start = cursor
        cursor += int(count)
        ranges.append((start, cursor))
    return tuple(ranges)


def build_selective_p6_trace_mpi_row_plan(
    *,
    closed_numbering: ExactSequenceClosedP6TraceNumbering,
    selected_orbit_owner_ranks: Mapping[int, int],
    owned_base_row_counts_by_rank: Sequence[int],
    owned_selected_trace_row_counts_by_rank: Sequence[int],
    geometry_key_sha256: str,
    ordered_trace_basis_sha256: str,
    selection_sha256: str,
    expected_full3d_dof_limit: int | None,
    caller_qualified_geometry_key: bool = False,
    caller_qualified_ordered_basis_identity: bool = False,
    caller_qualified_representative_owners: bool = False,
) -> SelectiveP6TraceMPIRowPlan:
    """Build an MPI-owner-aware row plan without allocating inactive modes."""

    selected_orbits = _selected_orbits_and_validate_serial_numbering(
        closed_numbering
    )
    numbering = closed_numbering.numbering
    closure = closed_numbering.closure
    base_counts = _validated_count_vector(
        owned_base_row_counts_by_rank,
        label="owned base row counts",
    )
    selected_counts = _validated_count_vector(
        owned_selected_trace_row_counts_by_rank,
        label="owned selected trace row counts",
    )
    mpi_size = len(base_counts)
    if len(selected_counts) != mpi_size:
        raise ValueError(
            "base and selected allgather-like counts have different MPI sizes"
        )
    owners = _validated_owner_map(
        selected_orbit_owner_ranks,
        selected_orbits=selected_orbits,
        mpi_size=mpi_size,
    )
    if sum(base_counts) != numbering.active_base_rows:
        raise RuntimeError(
            "allgather-like base row counts disagree with active base rows"
        )

    owned_orbits: list[list[PeriodicP6TraceOrbit]] = [
        [] for _rank in range(mpi_size)
    ]
    recomputed_selected_counts = [0] * mpi_size
    for orbit in selected_orbits:
        owner = owners[orbit.representative_entity_id]
        owned_orbits[owner].append(orbit)
        recomputed_selected_counts[owner] += orbit.missing_mode_count
    recomputed_selected_tuple = tuple(recomputed_selected_counts)
    if selected_counts != recomputed_selected_tuple:
        raise RuntimeError(
            "allgather-like selected trace row counts disagree with whole "
            "orbit ownership"
        )
    if sum(selected_counts) != closure.active_row_increment:
        raise RuntimeError(
            "selected trace row counts disagree with quotient active increment"
        )

    if expected_full3d_dof_limit is not None:
        if (
            isinstance(expected_full3d_dof_limit, bool)
            or not isinstance(expected_full3d_dof_limit, Integral)
        ):
            raise TypeError("expected Full3D DoF limit must be an integer")
        expected_full3d_dof_limit = int(expected_full3d_dof_limit)
        if expected_full3d_dof_limit < 0:
            raise ValueError("expected Full3D DoF limit must be nonnegative")
    if closure.full3d_dof_limit != expected_full3d_dof_limit:
        raise RuntimeError(
            "caller Full3D budget disagrees with exact-sequence closure"
        )
    if numbering.full3d_dof_limit != expected_full3d_dof_limit:
        raise RuntimeError(
            "caller Full3D budget disagrees with selective numbering"
        )
    if (
        expected_full3d_dof_limit is not None
        and closure.full3d_equivalent_dofs > expected_full3d_dof_limit
    ):
        raise RuntimeError("selective trace plan exceeds the Full3D budget")

    geometry_hash = _validated_sha256(
        geometry_key_sha256,
        label="geometry key SHA256",
    )
    basis_hash = _validated_sha256(
        ordered_trace_basis_sha256,
        label="ordered trace basis SHA256",
    )
    supplied_selection_hash = _validated_sha256(
        selection_sha256,
        label="selection SHA256",
    )
    recomputed_selection_hash = (
        canonical_selective_p6_trace_selection_sha256(
            closed_numbering=closed_numbering,
            geometry_key_sha256=geometry_hash,
            ordered_trace_basis_sha256=basis_hash,
        )
    )
    if supplied_selection_hash != recomputed_selection_hash:
        raise RuntimeError(
            "selection SHA256 does not bind the canonical selected orbits"
        )

    for label, value in (
        ("caller-qualified geometry key", caller_qualified_geometry_key),
        (
            "caller-qualified ordered basis identity",
            caller_qualified_ordered_basis_identity,
        ),
        (
            "caller-qualified representative owners",
            caller_qualified_representative_owners,
        ),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{label} flag must be bool")
    actual_mesh = bool(
        caller_qualified_geometry_key
        and caller_qualified_ordered_basis_identity
        and caller_qualified_representative_owners
    )

    total_counts = tuple(
        base + selected
        for base, selected in zip(base_counts, selected_counts, strict=True)
    )
    ownership_ranges = _prefix_ranges(total_counts)
    base_ranges = tuple(
        (start, start + base)
        for (start, _stop), base in zip(
            ownership_ranges,
            base_counts,
            strict=True,
        )
    )
    selected_ranges = tuple(
        (base_stop, ownership_stop)
        for (_base_start, base_stop), (_owner_start, ownership_stop) in zip(
            base_ranges,
            ownership_ranges,
            strict=True,
        )
    )

    descriptors: list[SelectedP6TraceOwnedRow] = []
    for rank, rank_orbits in enumerate(owned_orbits):
        cursor = selected_ranges[rank][0]
        for orbit in sorted(
            rank_orbits,
            key=lambda item: item.representative_entity_id,
        ):
            for mode_index in range(orbit.missing_mode_count):
                descriptors.append(
                    SelectedP6TraceOwnedRow(
                        representative_entity_id=(
                            orbit.representative_entity_id
                        ),
                        mode_index=mode_index,
                        entity_kind=orbit.entity_kind,
                        physical_member_entity_ids=orbit.member_entity_ids,
                        owner_rank=rank,
                        petsc_row=cursor,
                    )
                )
                cursor += 1
        if cursor != selected_ranges[rank][1]:
            raise RuntimeError(
                "rank-local selected trace rows do not close ownership range"
            )

    logical_to_petsc = {
        descriptor.logical_orbit_mode: descriptor.petsc_row
        for descriptor in descriptors
    }
    petsc_to_logical = {
        descriptor.petsc_row: descriptor.logical_orbit_mode
        for descriptor in descriptors
    }
    canonical_logical = tuple(
        (orbit.representative_entity_id, mode_index)
        for orbit in selected_orbits
        for mode_index in range(orbit.missing_mode_count)
    )
    if set(logical_to_petsc) != set(canonical_logical):
        raise RuntimeError("logical orbit-mode row permutation has gaps")
    if len(logical_to_petsc) != len(descriptors):
        raise RuntimeError("logical orbit-mode row permutation overlaps")
    if len(petsc_to_logical) != len(descriptors):
        raise RuntimeError("PETSc selected trace rows overlap")
    petsc_rows_in_canonical_order = tuple(
        logical_to_petsc[key] for key in canonical_logical
    )
    expected_selected_rows = {
        row
        for start, stop in selected_ranges
        for row in range(start, stop)
    }
    if set(petsc_to_logical) != expected_selected_rows:
        raise RuntimeError(
            "selected trace descriptors have gaps in PETSc ownership ranges"
        )
    base_rows = {
        row for start, stop in base_ranges for row in range(start, stop)
    }
    if base_rows.intersection(expected_selected_rows):
        raise RuntimeError("base and selected trace PETSc rows overlap")
    if ownership_ranges:
        for left, right in pairwise(ownership_ranges):
            if left[1] != right[0]:
                raise RuntimeError("PETSc ownership ranges contain a gap")

    inactive_representatives = {
        orbit.representative_entity_id
        for orbit in numbering.orbits
        if not orbit.selected
    }
    descriptor_representatives = {
        descriptor.representative_entity_id
        for descriptor in descriptors
    }
    checks = MappingProxyType(
        {
            "serial_selection_is_complete_periodic_orbits": True,
            "serial_selected_ranges_have_no_gaps_or_overlap": True,
            "owner_map_covers_exactly_selected_orbits": (
                set(owners)
                == {
                    orbit.representative_entity_id
                    for orbit in selected_orbits
                }
            ),
            "each_selected_orbit_has_one_owner": (
                len(owners) == len(selected_orbits)
            ),
            "allgather_base_counts_match": (
                sum(base_counts) == numbering.active_base_rows
            ),
            "allgather_selected_counts_match": (
                selected_counts == recomputed_selected_tuple
            ),
            "rank_layout_is_base_then_selected_trace": all(
                base_range[1] == selected_range[0]
                for base_range, selected_range in zip(
                    base_ranges,
                    selected_ranges,
                    strict=True,
                )
            ),
            "petsc_ownership_ranges_are_contiguous": all(
                left[1] == right[0]
                for left, right in pairwise(ownership_ranges)
            ),
            "logical_orbit_mode_permutation_is_bijective": (
                len(logical_to_petsc)
                == len(petsc_to_logical)
                == closure.active_row_increment
            ),
            "inactive_modes_have_no_row_descriptors": (
                not descriptor_representatives.intersection(
                    inactive_representatives
                )
            ),
            "full3d_budget_matches_closed_numbering": (
                closure.full3d_dof_limit == expected_full3d_dof_limit
                and numbering.full3d_dof_limit == expected_full3d_dof_limit
            ),
            "selection_hash_recomputed": (
                supplied_selection_hash == recomputed_selection_hash
            ),
            "full_p6_matrix_not_constructed": True,
            "matrix_not_constructed": True,
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "selective p6 trace MPI row plan audit failed: "
            + ", ".join(failed)
        )

    owned_representatives = tuple(
        tuple(
            orbit.representative_entity_id
            for orbit in sorted(
                rank_orbits,
                key=lambda item: item.representative_entity_id,
            )
        )
        for rank_orbits in owned_orbits
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.selective-p6-trace-mpi-row-plan.v1"
            ),
            "status": (
                "owner_aware_inactive_row_free_mpi_numbering_pass"
            ),
            "pass": True,
            "mpi_size": mpi_size,
            "owner_policy": (
                "caller_supplied_canonical_representative_entity_owner"
            ),
            "allgather_policy": (
                "caller_supplied_counts_verified_against_closed_orbits"
            ),
            "rank_local_layout": "owned_base_then_owned_selected_p6_trace",
            "physical_full3d_equivalent_increment": (
                closure.full3d_equivalent_increment
            ),
            "quotient_active_increment": closure.active_row_increment,
            "geometry_key_sha256": geometry_hash,
            "ordered_trace_basis_sha256": basis_hash,
            "selection_sha256": supplied_selection_hash,
            "selection_hash_is_mpi_partition_independent": True,
            "actual_mesh": actual_mesh,
            "actual_mesh_claim_authority": (
                "caller_qualified_hashes_and_representative_owners"
                if actual_mesh
                else "not_caller_qualified"
            ),
            "actual_mesh_verified_by_this_pure_layer": False,
            "actual_dwr_used_by_this_layer": False,
            "matrix_constructed": False,
            "inactive_p6_rows_numbered": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return SelectiveP6TraceMPIRowPlan(
        mpi_size=mpi_size,
        petsc_ownership_ranges=ownership_ranges,
        rank_base_row_ranges=base_ranges,
        rank_selected_trace_row_ranges=selected_ranges,
        owned_base_row_counts_by_rank=base_counts,
        owned_selected_trace_row_counts_by_rank=selected_counts,
        owned_selected_orbit_representatives_by_rank=owned_representatives,
        selected_orbit_owner_ranks=owners,
        selected_row_descriptors=tuple(descriptors),
        canonical_logical_orbit_modes=canonical_logical,
        petsc_rows_in_canonical_logical_order=(
            petsc_rows_in_canonical_order
        ),
        logical_orbit_mode_to_petsc_row=logical_to_petsc,
        petsc_row_to_logical_orbit_mode=petsc_to_logical,
        full3d_base_dofs=numbering.full3d_base_dofs,
        full3d_equivalent_increment=closure.full3d_equivalent_increment,
        full3d_equivalent_dofs=closure.full3d_equivalent_dofs,
        full3d_dof_limit=closure.full3d_dof_limit,
        active_base_rows=numbering.active_base_rows,
        quotient_active_increment=closure.active_row_increment,
        active_rows=numbering.active_rows,
        geometry_key_sha256=geometry_hash,
        ordered_trace_basis_sha256=basis_hash,
        selection_sha256=supplied_selection_hash,
        actual_mesh=actual_mesh,
        audit=audit,
    )


__all__ = [
    "LogicalOrbitMode",
    "SelectedP6TraceOwnedRow",
    "SelectiveP6TraceMPIRowPlan",
    "build_selective_p6_trace_mpi_row_plan",
    "canonical_selective_p6_trace_selection_sha256",
]
