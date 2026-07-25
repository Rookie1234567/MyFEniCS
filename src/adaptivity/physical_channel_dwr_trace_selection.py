"""Physical actual-channel DWR to selective-p6 trace row-plan bridge.

The Task035b selective-trace path has three deliberately separate layers:

* the algebraic complement-Schur/channel-DWR kernel;
* the actual-mesh p5/p6 Riesz/Floquet orbit catalog; and
* the inactive-row-free owner-aware assembly expansion.

This module binds those layers without constructing a full-p6 trace matrix.
Its complement coordinates are the actual DOLFINx-oriented periodic-orbit
coordinates returned by
``build_physical_p6_trace_orbit_pullbacks(..., basis_kind="missing")``.
Physical entity residuals therefore enter an orbit block only through
``P_entity^H r_entity``.  The inverse expansion is
``u_entity = P_entity u_representative``.

The bridge remains fail closed about PDE provenance.  An analytic fixture can
exercise every algebraic and MPI-numbering invariant, but only an
``actual_pde`` provenance with physical enriched residuals, action-only
complement Schur solves, actual DtN/port gradients, and qualified retained
adjoints can become a formal selection input.  Even then, the returned row
plan is not a successful candidate: it still requires an MPI8 PDE re-solve
and the unchanged 12/12 power plus 12/12 complex-amplitude audit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import pairwise
import json
from numbers import Integral
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from scipy.linalg import qr

from src.adaptivity.complement_schur_channel_dwr import (
    ChannelGoal,
    ComplementDWRAnalysis,
    ComplementSchurOperator,
    GoalComponent,
    WholeOrbitBlock,
    evaluate_complement_channel_dwr,
)
from src.adaptivity.p6_trace_complement_qualification import (
    P5P6TraceComplementQualification,
)
from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
    ExactSequenceClosedP6TraceNumbering,
    build_exact_sequence_closed_p6_trace_numbering,
)
from src.constraints.selective_p6_trace_3d import (
    SelectiveP6TraceMPIRowPlan,
    build_selective_p6_trace_mpi_row_plan,
    canonical_selective_p6_trace_selection_sha256,
)
from src.constraints.selective_p6_trace_expansion import (
    PhysicalP6TraceOrbitPullback,
    build_physical_p6_trace_orbit_pullbacks,
)
from src.constraints.selective_p6_trace_mesh_catalog import (
    SelectiveP6TraceMeshCatalog,
    build_selected_p6_trace_orbit_owner_inputs,
)


EvidenceClass = Literal["actual_pde", "analytic_fixture"]
ComplementStorageKind = Literal["action_only", "analytic_fixture_dense"]
LogicalComplementMode = tuple[int, int]

_RETAINED_TRACE_DIMENSION = {"edge": 5, "face": 40}
_FOCUS_GOAL_COMPONENTS: Mapping[str, GoalComponent] = MappingProxyType(
    {
        "T_m-4_n0_s_power": "real_power",
        "T_m-4_n0_s_amplitude_real": "complex_amplitude_real",
        "T_m-4_n0_s_amplitude_imag": "complex_amplitude_imag",
        "R_m-4_n0_s_power": "real_power",
        "R_m-4_n0_s_amplitude_real": "complex_amplitude_real",
        "R_m-4_n0_s_amplitude_imag": "complex_amplitude_imag",
        "R_m-5_n0_s_power": "real_power",
        "R_m-5_n0_s_amplitude_real": "complex_amplitude_real",
        "R_m-5_n0_s_amplitude_imag": "complex_amplitude_imag",
    }
)
FORMAL_H14_MINIMUM_WIRING: Mapping[str, Any] = MappingProxyType(
    {
        "storage_space": (
            "standard full-p6 trace plus p6-interior on the actual h14 mesh"
        ),
        "all_missing_orbit_expansion": (
            "build an all-missing-orbit CallerTraceExpansion only as the "
            "diagnostic low/high coordinate authority before global "
            "insertion; expose local/action blocks without materializing a "
            "full-p6 candidate trace matrix, and give inactive candidate "
            "orbits no PETSc rows after selection"
        ),
        "operator_blocks": (
            "assemble/action A_LL, A_LH, A_HL, A_HH in the physical layout "
            "and form r_H=b_H-A_HL*u_L plus action-only complement Schur "
            "S_H=A_HH-A_HL*A_LL^{-1}*A_LH"
        ),
        "channel_goals": (
            "reuse dtn_goal_adjoint actual auxiliary channel gradients and "
            "qualified retained Hermitian adjoints for independent power, "
            "amplitude-real, and amplitude-imag goals"
        ),
        "complement_solves": (
            "supply residual-checked S_H^{-1} and S_H^{-H} actions; the "
            "unpreconditioned q_H^H r_H proxy is not a DWR indicator"
        ),
        "exact_sequence": (
            "build actual same-mesh scalar p5-to-p6 discrete-gradient orbit "
            "rules bound to the ordered scalar basis, ordered Hcurl trace "
            "basis, physical geometry, Basix orientation, and Floquet "
            "pullbacks before owner-aware row numbering"
        ),
        "existing_h14_offline_reconstruction": "not_authorized",
        "existing_h14_offline_reconstruction_reason": (
            "old h14 artifacts were written with "
            "stage4_retain_dual_recovery_context=False and retain neither "
            "the full channel dual context nor the reduced operator blocks"
        ),
        "layout_validation_reuse": (
            "MissingTraceResidualDiagnostic may be reused for PETSc global/"
            "local size and ownership-range validation of retained/missing "
            "vectors, but its paired residual remains proxy-only and cannot "
            "authorize orbit selection"
        ),
    }
)


def _validated_sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


def _validated_source_commit(value: str) -> str:
    normalized = str(value).lower()
    try:
        valid = (
            len(normalized) in {40, 64}
            and len(bytes.fromhex(normalized)) * 2 == len(normalized)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("source commit must be a 40- or 64-digit hex value")
    return normalized


def _readonly_vector(
    values: np.ndarray,
    *,
    dimension: int,
    label: str,
) -> np.ndarray:
    vector = np.asarray(values, dtype=np.complex128)
    if vector.shape != (int(dimension),):
        raise ValueError(
            f"{label} has shape {vector.shape}, expected {(dimension,)}"
        )
    if not np.all(np.isfinite(vector)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    result = np.array(vector, dtype=np.complex128, copy=True)
    result.setflags(write=False)
    return result


def _matrix_sha256(values: np.ndarray) -> str:
    matrix = np.ascontiguousarray(values, dtype=np.dtype("<c16"))
    digest = hashlib.sha256()
    digest.update(np.asarray(matrix.shape, dtype="<i8").tobytes())
    digest.update(matrix.tobytes())
    return digest.hexdigest()


def _layout_sha256(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    orbits: Sequence[PhysicalP6TraceOrbitPullback],
) -> str:
    payload = {
        "schema": "task035b.physical-missing-p6-dwr-layout.v1",
        "catalog_sha256": catalog.catalog_sha256,
        "trace_geometry_sha256": catalog.trace_geometry_sha256,
        "ordered_trace_basis_sha256": catalog.ordered_trace_basis_sha256,
        "qualification_sha256": qualification.qualification_sha256,
        "orbits": [
            {
                "representative_entity_id": orbit.representative_entity_id,
                "member_entity_ids": list(orbit.member_entity_ids),
                "entity_kind": orbit.entity_kind,
                "dimension": orbit.dimension,
                "pullback_sha256": {
                    str(member): _matrix_sha256(
                        orbit.representative_to_member[member]
                    )
                    for member in orbit.member_entity_ids
                },
            }
            for orbit in orbits
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class PhysicalMissingTraceDWROrbit:
    """One actual periodic orbit in the complement-DWR coordinate layout."""

    representative_entity_id: int
    entity_kind: str
    member_entity_ids: tuple[int, ...]
    complement_indices: tuple[int, ...]
    representative_to_member_pullbacks: Mapping[int, np.ndarray]
    orbit_id: str

    def __post_init__(self) -> None:
        representative = int(self.representative_entity_id)
        members = tuple(map(int, self.member_entity_ids))
        indices = tuple(map(int, self.complement_indices))
        if representative < 0 or representative not in members:
            raise ValueError("DWR orbit representative must be a member")
        if self.entity_kind not in _RETAINED_TRACE_DIMENSION:
            raise ValueError("DWR orbit must be an edge or face")
        expected_dimension = 1 if self.entity_kind == "edge" else 20
        if len(indices) != expected_dimension:
            raise ValueError("DWR orbit has the wrong missing-shell dimension")
        if not indices or len(set(indices)) != len(indices) or min(indices) < 0:
            raise ValueError("DWR orbit complement indices are invalid")
        if not members or len(set(members)) != len(members):
            raise ValueError("DWR orbit physical members are invalid")
        if set(map(int, self.representative_to_member_pullbacks)) != set(
            members
        ):
            raise ValueError("DWR orbit pullbacks do not cover every member")
        frozen: dict[int, np.ndarray] = {}
        for member, values in self.representative_to_member_pullbacks.items():
            matrix = np.asarray(values, dtype=np.complex128)
            if (
                matrix.shape != (expected_dimension, expected_dimension)
                or not np.all(np.isfinite(matrix))
            ):
                raise ValueError("DWR orbit pullback has the wrong shape")
            matrix = np.array(matrix, dtype=np.complex128, copy=True)
            matrix.setflags(write=False)
            frozen[int(member)] = matrix
        orbit_id = str(self.orbit_id)
        if not orbit_id:
            raise ValueError("DWR orbit id must be nonempty")
        object.__setattr__(
            self,
            "representative_entity_id",
            representative,
        )
        object.__setattr__(self, "member_entity_ids", members)
        object.__setattr__(self, "complement_indices", indices)
        object.__setattr__(
            self,
            "representative_to_member_pullbacks",
            MappingProxyType(frozen),
        )
        object.__setattr__(self, "orbit_id", orbit_id)

    @property
    def whole_orbit_block(self) -> WholeOrbitBlock:
        return WholeOrbitBlock(
            orbit_id=self.orbit_id,
            complement_indices=self.complement_indices,
            member_entity_ids=self.member_entity_ids,
            periodic_orbit_closed=True,
        )


@dataclass(frozen=True)
class PhysicalMissingTraceDWRLayout:
    """Hash-bound physical complement coordinate authority."""

    orbits: tuple[PhysicalMissingTraceDWROrbit, ...]
    canonical_logical_modes: tuple[LogicalComplementMode, ...]
    logical_mode_to_index: Mapping[LogicalComplementMode, int]
    entity_to_representative: Mapping[int, int]
    high_dimension: int
    catalog_sha256: str
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    qualification_sha256: str
    layout_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("physical missing-trace DWR layout is unqualified")
        object.__setattr__(
            self,
            "logical_mode_to_index",
            MappingProxyType(
                {
                    (int(key[0]), int(key[1])): int(index)
                    for key, index in self.logical_mode_to_index.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "entity_to_representative",
            MappingProxyType(
                {
                    int(entity): int(representative)
                    for entity, representative in (
                        self.entity_to_representative.items()
                    )
                }
            ),
        )
        for field_name in (
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "qualification_sha256",
            "layout_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _validated_sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )


def build_physical_missing_trace_dwr_layout(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    algebra_tolerance: float = 2.0e-10,
) -> PhysicalMissingTraceDWRLayout:
    """Bind the actual Piola/Riesz/Floquet orbit layout used by DWR."""

    if catalog.audit.get("pass") is not True:
        raise RuntimeError("actual mesh trace catalog is unqualified")
    if qualification.audit.get("pass") is not True:
        raise RuntimeError("p5/p6 trace complement basis is unqualified")
    if catalog.qualification_sha256 != qualification.qualification_sha256:
        raise RuntimeError("catalog and trace Riesz basis hashes differ")
    for entity_kind in ("edge", "face"):
        shell = getattr(qualification, entity_kind)
        required = (
            "missing_basis_is_riesz_orthonormal",
            "retained_missing_riesz_leakage_absent",
            "covariant_piola_push_forward_matches",
            "covariant_piola_roundtrip_passes",
            "tangential_covectors_pull_back_exactly",
            "entity_transformations_are_qualified",
        )
        if any(shell.audit["checks"].get(name) is not True for name in required):
            raise RuntimeError(
                f"{entity_kind} Piola/Riesz trace authority is incomplete"
            )

    pullbacks = build_physical_p6_trace_orbit_pullbacks(
        catalog=catalog,
        basis_kind="missing",
        tolerance=algebra_tolerance,
    )
    canonical_orbits = {
        orbit.representative_entity_id: orbit
        for orbit in catalog.all_inactive_orbit_numbering.orbits
    }
    result: list[PhysicalMissingTraceDWROrbit] = []
    logical_modes: list[LogicalComplementMode] = []
    logical_to_index: dict[LogicalComplementMode, int] = {}
    entity_to_representative: dict[int, int] = {}
    cursor = 0
    for pullback in pullbacks:
        canonical = canonical_orbits.get(pullback.representative_entity_id)
        if canonical is None:
            raise RuntimeError(
                "actual missing pullback has no canonical periodic orbit"
            )
        if (
            canonical.member_entity_ids != pullback.member_entity_ids
            or canonical.entity_kind != pullback.entity_kind
            or canonical.missing_mode_count != pullback.dimension
        ):
            raise RuntimeError(
                "actual missing pullback differs from physical orbit catalog"
            )
        indices = tuple(range(cursor, cursor + pullback.dimension))
        orbit_id = (
            f"{pullback.entity_kind}:"
            f"{pullback.representative_entity_id}"
        )
        result.append(
            PhysicalMissingTraceDWROrbit(
                representative_entity_id=(
                    pullback.representative_entity_id
                ),
                entity_kind=pullback.entity_kind,
                member_entity_ids=pullback.member_entity_ids,
                complement_indices=indices,
                representative_to_member_pullbacks=(
                    pullback.representative_to_member
                ),
                orbit_id=orbit_id,
            )
        )
        for mode, index in enumerate(indices):
            logical = (pullback.representative_entity_id, mode)
            logical_modes.append(logical)
            logical_to_index[logical] = index
        for member in pullback.member_entity_ids:
            if member in entity_to_representative:
                raise RuntimeError(
                    "physical entity belongs to multiple DWR orbits"
                )
            entity_to_representative[member] = (
                pullback.representative_entity_id
            )
        cursor += pullback.dimension

    expected_dimension = int(
        catalog.audit["quotient_missing_shell_dofs"]
    )
    expected_entities = {entity.entity_id for entity in catalog.entities}
    flattened_indices = {
        index for orbit in result for index in orbit.complement_indices
    }
    checks = MappingProxyType(
        {
            "actual_dolfinx_mesh_catalog_bound": True,
            "physical_covariant_piola_basis_qualified": True,
            "physical_tangential_riesz_complement_qualified": True,
            "actual_basix_entity_orientation_used": True,
            "actual_floquet_phase_pullback_used": True,
            "periodic_pullback_cycles_closed": True,
            "whole_orbits_cover_every_physical_entity": (
                set(entity_to_representative) == expected_entities
            ),
            "canonical_complement_indices_are_bijective": (
                flattened_indices == set(range(cursor))
                and len(logical_to_index) == cursor
            ),
            "quotient_dimension_matches_catalog": (
                cursor == expected_dimension
            ),
            "matrix_not_constructed": True,
            "active_rows_not_allocated": True,
            "inactive_rows_not_allocated": True,
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "physical missing-trace DWR layout failed: "
            + ", ".join(failed)
        )
    layout_hash = _layout_sha256(
        catalog=catalog,
        qualification=qualification,
        orbits=pullbacks,
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.physical-missing-p6-trace-dwr-layout.v1"
            ),
            "status": "physical_missing_p6_trace_dwr_layout_pass",
            "pass": True,
            "orbit_count": len(result),
            "physical_entity_count": len(entity_to_representative),
            "high_dimension": cursor,
            "coordinate_semantics": (
                "actual_DOLFINx_oriented_periodic_orbit_representative_"
                "missing_Riesz_coefficients"
            ),
            "entity_residual_projection": "r_rep += P_entity^H r_entity",
            "entity_state_expansion": "u_entity = P_entity u_rep",
            "catalog_sha256": catalog.catalog_sha256,
            "trace_geometry_sha256": catalog.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                catalog.ordered_trace_basis_sha256
            ),
            "qualification_sha256": qualification.qualification_sha256,
            "layout_sha256": layout_hash,
            "layout_hash_includes_actual_dolfinx_orientation": True,
            "layout_hash_is_not_claimed_mpi_partition_independent": True,
            "full_p6_trace_matrix_constructed": False,
            "inactive_p6_rows_allocated": 0,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return PhysicalMissingTraceDWRLayout(
        orbits=tuple(result),
        canonical_logical_modes=tuple(logical_modes),
        logical_mode_to_index=logical_to_index,
        entity_to_representative=entity_to_representative,
        high_dimension=cursor,
        catalog_sha256=catalog.catalog_sha256,
        trace_geometry_sha256=catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=catalog.ordered_trace_basis_sha256,
        qualification_sha256=qualification.qualification_sha256,
        layout_sha256=layout_hash,
        audit=audit,
    )


def project_physical_missing_trace_entity_vectors(
    layout: PhysicalMissingTraceDWRLayout,
    *,
    entity_vectors: Mapping[int, np.ndarray],
) -> np.ndarray:
    """Accumulate missing-Riesz entity duals into quotient coordinates.

    Each input has already been restricted from the full p6 entity storage
    basis to the missing Riesz shell.  Use
    :func:`project_full_p6_storage_entity_duals_to_complement` when the caller
    starts from the six edge or sixty face p6 storage residual entries.
    """

    expected_entities = set(layout.entity_to_representative)
    supplied_entities = set(map(int, entity_vectors))
    if supplied_entities != expected_entities:
        raise ValueError(
            "physical entity-vector map must cover the complete trace catalog: "
            f"missing={sorted(expected_entities - supplied_entities)}, "
            f"extra={sorted(supplied_entities - expected_entities)}"
        )
    result = np.zeros(layout.high_dimension, dtype=np.complex128)
    for orbit in layout.orbits:
        accumulator = np.zeros(
            len(orbit.complement_indices),
            dtype=np.complex128,
        )
        for member in orbit.member_entity_ids:
            vector = _readonly_vector(
                entity_vectors[member],
                dimension=len(orbit.complement_indices),
                label=f"physical missing-trace entity {member} vector",
            )
            pullback = orbit.representative_to_member_pullbacks[member]
            accumulator += pullback.conj().T @ vector
        result[np.asarray(orbit.complement_indices, dtype=np.int64)] = (
            accumulator
        )
    result.setflags(write=False)
    return result


def project_full_p6_storage_entity_duals_to_complement(
    layout: PhysicalMissingTraceDWRLayout,
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    storage_entity_duals: Mapping[int, np.ndarray],
) -> np.ndarray:
    """Apply ``P_entity^H B_missing^H`` to full-p6 entity dual vectors."""

    if layout.catalog_sha256 != catalog.catalog_sha256:
        raise RuntimeError("layout and physical entity catalog hashes differ")
    if layout.qualification_sha256 != qualification.qualification_sha256:
        raise RuntimeError("layout and missing Riesz basis hashes differ")
    expected_entities = {entity.entity_id for entity in catalog.entities}
    supplied_entities = set(map(int, storage_entity_duals))
    if supplied_entities != expected_entities:
        raise ValueError(
            "full-p6 storage entity duals must cover the complete catalog: "
            f"missing={sorted(expected_entities - supplied_entities)}, "
            f"extra={sorted(supplied_entities - expected_entities)}"
        )
    missing_entity_duals: dict[int, np.ndarray] = {}
    for entity in catalog.entities:
        shell = getattr(qualification, entity.entity_kind)
        storage_dimension = shell.enriched_dimension
        storage_dual = _readonly_vector(
            storage_entity_duals[entity.entity_id],
            dimension=storage_dimension,
            label=f"full-p6 entity {entity.entity_id} storage dual",
        )
        missing_entity_duals[entity.entity_id] = (
            shell.missing_basis.conj().T @ storage_dual
        )
    return project_physical_missing_trace_entity_vectors(
        layout,
        entity_vectors=missing_entity_duals,
    )


def expand_missing_trace_complement_vector_to_entities(
    layout: PhysicalMissingTraceDWRLayout,
    *,
    complement_vector: np.ndarray,
) -> Mapping[int, np.ndarray]:
    """Expand representative complement coordinates to physical entities."""

    vector = _readonly_vector(
        complement_vector,
        dimension=layout.high_dimension,
        label="physical missing-trace complement vector",
    )
    result: dict[int, np.ndarray] = {}
    for orbit in layout.orbits:
        representative_values = vector[
            np.asarray(orbit.complement_indices, dtype=np.int64)
        ]
        for member in orbit.member_entity_ids:
            values = (
                orbit.representative_to_member_pullbacks[member]
                @ representative_values
            )
            values = np.asarray(values, dtype=np.complex128)
            values.setflags(write=False)
            result[member] = values
    return MappingProxyType(result)


def expand_missing_trace_complement_vector_to_full_p6_storage_entities(
    layout: PhysicalMissingTraceDWRLayout,
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    qualification: P5P6TraceComplementQualification,
    complement_vector: np.ndarray,
) -> Mapping[int, np.ndarray]:
    """Apply ``B_missing P_entity`` into full-p6 physical entity storage."""

    if layout.catalog_sha256 != catalog.catalog_sha256:
        raise RuntimeError("layout and physical entity catalog hashes differ")
    if layout.qualification_sha256 != qualification.qualification_sha256:
        raise RuntimeError("layout and missing Riesz basis hashes differ")
    missing_entities = expand_missing_trace_complement_vector_to_entities(
        layout,
        complement_vector=complement_vector,
    )
    result: dict[int, np.ndarray] = {}
    for entity in catalog.entities:
        shell = getattr(qualification, entity.entity_kind)
        values = (
            shell.missing_basis @ missing_entities[entity.entity_id]
        )
        values = np.asarray(values, dtype=np.complex128)
        values.setflags(write=False)
        result[entity.entity_id] = values
    return MappingProxyType(result)


@dataclass(frozen=True)
class PhysicalComplementDWRProvenance:
    """Fail-closed caller evidence for a layout-bound complement system."""

    evidence_class: EvidenceClass
    source_commit: str
    retained_candidate_record_sha256: str
    significant_channel_reference_sha256: str
    complement_layout_sha256: str
    complement_storage_kind: ComplementStorageKind
    physical_missing_basis_tabulated: bool
    physical_entity_residual_projection_used: bool
    actual_enriched_residual_assembled: bool
    actual_complement_schur_actions: bool
    actual_complement_schur_inverse: bool
    actual_dtn_port_channel_gradients: bool
    retained_adjoints_qualified: bool
    full_p6_trace_matrix_materialized: bool
    inactive_p6_rows_allocated: int

    def __post_init__(self) -> None:
        if self.evidence_class not in {"actual_pde", "analytic_fixture"}:
            raise ValueError("unsupported complement-DWR evidence class")
        object.__setattr__(
            self,
            "source_commit",
            _validated_source_commit(self.source_commit),
        )
        for field_name in (
            "retained_candidate_record_sha256",
            "significant_channel_reference_sha256",
            "complement_layout_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _validated_sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        if self.complement_storage_kind not in {
            "action_only",
            "analytic_fixture_dense",
        }:
            raise ValueError("unsupported complement Schur storage kind")
        if self.full_p6_trace_matrix_materialized is not False:
            raise RuntimeError(
                "physical complement DWR cannot use a full-p6 trace matrix"
            )
        if (
            isinstance(self.inactive_p6_rows_allocated, bool)
            or not isinstance(self.inactive_p6_rows_allocated, Integral)
        ):
            raise TypeError("inactive p6 row count must be an integer")
        if int(self.inactive_p6_rows_allocated) != 0:
            raise RuntimeError(
                "inactive missing-p6 modes must not receive matrix rows"
            )
        object.__setattr__(
            self,
            "inactive_p6_rows_allocated",
            int(self.inactive_p6_rows_allocated),
        )
        if self.evidence_class == "actual_pde":
            required = {
                "physical_missing_basis_tabulated": (
                    self.physical_missing_basis_tabulated
                ),
                "physical_entity_residual_projection_used": (
                    self.physical_entity_residual_projection_used
                ),
                "actual_enriched_residual_assembled": (
                    self.actual_enriched_residual_assembled
                ),
                "actual_complement_schur_actions": (
                    self.actual_complement_schur_actions
                ),
                "actual_complement_schur_inverse": (
                    self.actual_complement_schur_inverse
                ),
                "actual_dtn_port_channel_gradients": (
                    self.actual_dtn_port_channel_gradients
                ),
                "retained_adjoints_qualified": (
                    self.retained_adjoints_qualified
                ),
                "action_only_complement_storage": (
                    self.complement_storage_kind == "action_only"
                ),
            }
            if not all(required.values()):
                failed = [
                    name for name, passed in required.items() if not passed
                ]
                raise RuntimeError(
                    "actual PDE complement provenance is incomplete: "
                    + ", ".join(failed)
                )

    @property
    def formal_actual_pde(self) -> bool:
        return self.evidence_class == "actual_pde"


@dataclass(frozen=True)
class PhysicalChannelDWRAnalysis:
    """Algebraic DWR result bound to one physical trace layout."""

    layout: PhysicalMissingTraceDWRLayout
    provenance: PhysicalComplementDWRProvenance
    algebraic: ComplementDWRAnalysis
    focus_goal_labels: tuple[str, ...]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("physical channel DWR analysis is unqualified")


def _validate_focus_goals(
    goals: Sequence[ChannelGoal],
) -> tuple[str, ...]:
    by_label = {goal.label: goal for goal in goals}
    if len(by_label) != len(tuple(goals)):
        raise ValueError("physical channel DWR goal labels are duplicated")
    missing = set(_FOCUS_GOAL_COMPONENTS) - set(by_label)
    if missing:
        raise RuntimeError(
            "physical channel DWR lacks independent focus components: "
            + ", ".join(sorted(missing))
        )
    for label, component in _FOCUS_GOAL_COMPONENTS.items():
        goal = by_label[label]
        if goal.component != component:
            raise RuntimeError(
                f"{label} has component {goal.component}, expected {component}"
            )
        if goal.selection_target is not True or goal.protected:
            raise RuntimeError(
                f"{label} must be a selection target and not protected"
            )
    return tuple(_FOCUS_GOAL_COMPONENTS)


def evaluate_physical_channel_dwr(
    *,
    layout: PhysicalMissingTraceDWRLayout,
    provenance: PhysicalComplementDWRProvenance,
    schur: ComplementSchurOperator,
    missing_right_hand_side: np.ndarray,
    retained_state: np.ndarray,
    goals: Sequence[ChannelGoal],
    identity_tolerance: float = 5.0e-11,
) -> PhysicalChannelDWRAnalysis:
    """Evaluate actual/fixture DWR in the hash-bound physical orbit layout."""

    if provenance.complement_layout_sha256 != layout.layout_sha256:
        raise RuntimeError(
            "complement system and physical DWR layout hashes differ"
        )
    if schur.high_dimension != layout.high_dimension:
        raise RuntimeError(
            "complement Schur dimension differs from physical orbit layout"
        )
    focus_labels = _validate_focus_goals(goals)
    algebraic = evaluate_complement_channel_dwr(
        schur,
        missing_right_hand_side=missing_right_hand_side,
        retained_state=retained_state,
        goals=goals,
        orbits=tuple(
            orbit.whole_orbit_block for orbit in layout.orbits
        ),
        identity_tolerance=identity_tolerance,
    )
    expected_orbit_ids = tuple(orbit.orbit_id for orbit in layout.orbits)
    diagnostic_orbit_ids = tuple(
        algebraic.svd_rrqr_diagnostics["orbit_ids"]
    )
    if diagnostic_orbit_ids != expected_orbit_ids:
        raise RuntimeError("DWR orbit ordering differs from physical layout")
    actual = provenance.formal_actual_pde
    checks = MappingProxyType(
        {
            "physical_layout_hash_matches_complement_system": True,
            "complement_dimension_matches_physical_quotient": True,
            "physical_piola_riesz_orbit_layout_qualified": True,
            "actual_dolfinx_orientation_and_floquet_pullback_used": True,
            "focus_channels_have_independent_power_real_imag_goals": True,
            "algebraic_complement_dwr_identity_pass": (
                algebraic.audit.get("pass") is True
            ),
            "whole_orbit_partition_closes": (
                algebraic.audit["whole_orbit_partition_closes"] is True
            ),
            "full_p6_trace_matrix_not_materialized": (
                provenance.full_p6_trace_matrix_materialized is False
            ),
            "inactive_p6_rows_allocated_is_zero": (
                provenance.inactive_p6_rows_allocated == 0
            ),
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "physical channel DWR integration failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.physical-channel-dwr-analysis.v1"
            ),
            "status": (
                "actual_physical_channel_dwr_pass"
                if actual
                else "analytic_fixture_physical_layout_dwr_pass"
            ),
            "pass": True,
            "evidence_class": provenance.evidence_class,
            "formal_actual_pde": actual,
            "physical_candidate_selection_input_authorized": actual,
            "layout_sha256": layout.layout_sha256,
            "catalog_sha256": layout.catalog_sha256,
            "trace_geometry_sha256": layout.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                layout.ordered_trace_basis_sha256
            ),
            "retained_candidate_record_sha256": (
                provenance.retained_candidate_record_sha256
            ),
            "significant_channel_reference_sha256": (
                provenance.significant_channel_reference_sha256
            ),
            "focus_goal_labels": list(focus_labels),
            "focus_channel_semantics": (
                "T(-4,0), R(-4,0), R(-5,0), each with independent "
                "power/amplitude-real/amplitude-imag goals"
            ),
            "full_12_channel_postsolve_reaudit_required": True,
            "formal_candidate_passed": False,
            "inactive_p6_rows_allocated": 0,
            "full_p6_trace_matrix_materialized": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return PhysicalChannelDWRAnalysis(
        layout=layout,
        provenance=provenance,
        algebraic=algebraic,
        focus_goal_labels=focus_labels,
        audit=audit,
    )


@dataclass(frozen=True)
class RankRevealingDWRSeedSelection:
    """Bounded whole-orbit seeds chosen from positive actual-channel DWR."""

    seed_representative_entity_ids: tuple[int, ...]
    seed_orbit_ids: tuple[str, ...]
    eligible_orbit_ids: tuple[str, ...]
    target_goal_labels: tuple[str, ...]
    target_matrix_rank: int
    rank_tolerance: float
    rrqr_pivot_orbit_ids: tuple[str, ...]
    maximum_seed_orbits: int
    rank_span_complete: bool
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("DWR seed selection is unqualified")


def select_rank_revealing_dwr_seed_orbits(
    analysis: PhysicalChannelDWRAnalysis,
    *,
    maximum_seed_orbits: int,
) -> RankRevealingDWRSeedSelection:
    """Choose a bounded, non-regressing RRQR set of whole physical orbits."""

    if (
        isinstance(maximum_seed_orbits, bool)
        or not isinstance(maximum_seed_orbits, Integral)
        or int(maximum_seed_orbits) <= 0
    ):
        raise ValueError("maximum seed orbit count must be a positive integer")
    maximum = int(maximum_seed_orbits)
    orbit_by_id = {
        orbit.orbit_id: orbit for orbit in analysis.layout.orbits
    }
    eligible = tuple(
        orbit
        for orbit in analysis.algebraic.ranked_orbits
        if (
            orbit.selection_score > 0.0
            and orbit.target_net_absolute_error_improvement > 0.0
            and orbit.target_regression_count == 0
            and orbit.target_gate_crossing_count == 0
            and orbit.protected_regression_count == 0
            and orbit.protected_gate_crossing_count == 0
        )
    )
    if not eligible:
        raise RuntimeError(
            "actual-channel DWR has no positive non-regressing whole orbit"
        )
    unknown = {orbit.orbit_id for orbit in eligible} - set(orbit_by_id)
    if unknown:
        raise RuntimeError(
            "DWR ranking contains orbits outside the physical layout"
        )
    target_labels = tuple(analysis.focus_goal_labels)
    target_matrix = np.asarray(
        [
            [
                float(
                    orbit.goals[label][
                        "normalized_signed_correction"
                    ]
                )
                for orbit in eligible
            ]
            for label in target_labels
        ],
        dtype=np.float64,
    )
    singular_values = np.linalg.svd(target_matrix, compute_uv=False)
    if singular_values.size and singular_values[0] > 0.0:
        rank_tolerance = float(
            max(target_matrix.shape)
            * np.finfo(np.float64).eps
            * singular_values[0]
        )
        numerical_rank = int(
            np.count_nonzero(singular_values > rank_tolerance)
        )
    else:
        rank_tolerance = 0.0
        numerical_rank = 0
    if numerical_rank <= 0:
        raise RuntimeError(
            "positive DWR orbit matrix has zero numerical target rank"
        )
    _q, _r, pivots = qr(
        target_matrix,
        mode="economic",
        pivoting=True,
        check_finite=True,
    )
    pivot_orbits = tuple(eligible[int(index)] for index in pivots)
    selected_count = min(numerical_rank, maximum)
    selected = pivot_orbits[:selected_count]
    seed_ids = tuple(
        orbit_by_id[item.orbit_id].representative_entity_id
        for item in selected
    )
    checks = MappingProxyType(
        {
            "eligible_orbits_are_whole_physical_orbits": True,
            "eligible_orbits_have_positive_target_improvement": all(
                orbit.target_net_absolute_error_improvement > 0.0
                for orbit in eligible
            ),
            "eligible_orbits_have_no_target_regression": all(
                orbit.target_regression_count == 0
                and orbit.target_gate_crossing_count == 0
                for orbit in eligible
            ),
            "eligible_orbits_have_no_protected_regression": all(
                orbit.protected_regression_count == 0
                and orbit.protected_gate_crossing_count == 0
                for orbit in eligible
            ),
            "rrqr_operates_on_focus_goal_by_whole_orbit_matrix": True,
            "seed_count_respects_bound": len(selected) <= maximum,
            "coordinate_mode_selection_not_performed": True,
            "matrix_rows_not_allocated": True,
        }
    )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.rank-revealing-physical-channel-dwr-seeds.v1"
            ),
            "status": "bounded_rank_revealing_whole_orbit_seeds_pass",
            "pass": True,
            "evidence_class": analysis.provenance.evidence_class,
            "target_matrix_shape": list(target_matrix.shape),
            "target_matrix_rank": numerical_rank,
            "rank_tolerance": rank_tolerance,
            "maximum_seed_orbits": maximum,
            "selected_seed_count": len(selected),
            "rank_span_complete": selected_count == numerical_rank,
            "selection_policy": (
                "positive normalized absolute-error improvement, no target "
                "or protected regression/gate crossing, then RRQR whole-orbit "
                "columns"
            ),
            "formal_candidate_passed": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return RankRevealingDWRSeedSelection(
        seed_representative_entity_ids=seed_ids,
        seed_orbit_ids=tuple(item.orbit_id for item in selected),
        eligible_orbit_ids=tuple(item.orbit_id for item in eligible),
        target_goal_labels=target_labels,
        target_matrix_rank=numerical_rank,
        rank_tolerance=rank_tolerance,
        rrqr_pivot_orbit_ids=tuple(
            item.orbit_id for item in pivot_orbits
        ),
        maximum_seed_orbits=maximum,
        rank_span_complete=selected_count == numerical_rank,
        audit=audit,
    )


@dataclass(frozen=True)
class PhysicalDiscreteGradientAuthority:
    """Hash-bound exact-sequence rules on the same physical orbit catalog."""

    rules: tuple[DiscreteGradientOrbitRule, ...]
    evidence_class: EvidenceClass
    catalog_sha256: str
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    ordered_scalar_basis_sha256: str
    actual_scalar_space_on_same_mesh: bool
    actual_discrete_gradient_coefficients: bool
    actual_periodic_floquet_pullback: bool

    def __post_init__(self) -> None:
        if self.evidence_class not in {"actual_pde", "analytic_fixture"}:
            raise ValueError("unsupported discrete-gradient evidence class")
        for field_name in (
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "ordered_scalar_basis_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _validated_sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )
        rules = tuple(self.rules)
        if not rules:
            raise ValueError("physical discrete-gradient rules are empty")
        if any(
            rule.ordered_trace_basis_sha256
            != self.ordered_trace_basis_sha256
            for rule in rules
        ):
            raise RuntimeError(
                "discrete-gradient rules do not bind the physical trace basis"
            )
        if any(
            rule.ordered_scalar_basis_sha256
            != self.ordered_scalar_basis_sha256
            for rule in rules
        ):
            raise RuntimeError(
                "discrete-gradient rules do not bind one scalar basis identity"
            )
        if self.evidence_class == "actual_pde":
            required = {
                "actual_scalar_space_on_same_mesh": (
                    self.actual_scalar_space_on_same_mesh
                ),
                "actual_discrete_gradient_coefficients": (
                    self.actual_discrete_gradient_coefficients
                ),
                "actual_periodic_floquet_pullback": (
                    self.actual_periodic_floquet_pullback
                ),
            }
            if not all(required.values()):
                failed = [
                    name for name, passed in required.items() if not passed
                ]
                raise RuntimeError(
                    "actual physical discrete-gradient authority is "
                    "incomplete: " + ", ".join(failed)
                )
        object.__setattr__(self, "rules", rules)

    @property
    def formal_actual_pde(self) -> bool:
        return self.evidence_class == "actual_pde"


@dataclass(frozen=True)
class PhysicalChannelDWRTraceRowPlan:
    """DWR seeds, exact-sequence closure, and inactive-row-free MPI plan."""

    dwr_analysis: PhysicalChannelDWRAnalysis
    seed_selection: RankRevealingDWRSeedSelection
    discrete_gradient_authority: PhysicalDiscreteGradientAuthority
    exact_sequence_numbering: ExactSequenceClosedP6TraceNumbering
    row_plan: SelectiveP6TraceMPIRowPlan
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("physical channel-DWR trace row plan is unqualified")


def build_physical_channel_dwr_trace_row_plan(
    *,
    catalog: SelectiveP6TraceMeshCatalog,
    dwr_analysis: PhysicalChannelDWRAnalysis,
    seed_selection: RankRevealingDWRSeedSelection,
    discrete_gradient: PhysicalDiscreteGradientAuthority,
    full3d_base_dofs: int,
    full3d_dof_limit: int,
) -> PhysicalChannelDWRTraceRowPlan:
    """Close DWR seeds under exact sequence and allocate only active rows."""

    if dwr_analysis.layout.catalog_sha256 != catalog.catalog_sha256:
        raise RuntimeError("DWR layout and physical mesh catalog hashes differ")
    if discrete_gradient.catalog_sha256 != catalog.catalog_sha256:
        raise RuntimeError(
            "discrete gradient and physical mesh catalog hashes differ"
        )
    if (
        discrete_gradient.trace_geometry_sha256
        != catalog.trace_geometry_sha256
    ):
        raise RuntimeError(
            "discrete gradient and trace geometry hashes differ"
        )
    if (
        discrete_gradient.ordered_trace_basis_sha256
        != catalog.ordered_trace_basis_sha256
    ):
        raise RuntimeError(
            "discrete gradient and ordered trace basis hashes differ"
        )
    layout_representatives = {
        orbit.representative_entity_id for orbit in dwr_analysis.layout.orbits
    }
    if not set(
        seed_selection.seed_representative_entity_ids
    ).issubset(layout_representatives):
        raise RuntimeError("DWR seed selection contains an unknown orbit")
    if not seed_selection.seed_representative_entity_ids:
        raise RuntimeError("DWR seed selection is empty")

    base_counts = [0] * catalog.mpi_size
    for orbit in catalog.all_inactive_orbit_numbering.orbits:
        owner = catalog.representative_owner_ranks[
            orbit.representative_entity_id
        ]
        base_counts[owner] += _RETAINED_TRACE_DIMENSION[orbit.entity_kind]
    active_base_rows = sum(base_counts)
    closed = build_exact_sequence_closed_p6_trace_numbering(
        entities=catalog.missing_trace_entities,
        periodic_relations=catalog.periodic_relations,
        gradient_rules=discrete_gradient.rules,
        seed_trace_representative_ids=(
            seed_selection.seed_representative_entity_ids
        ),
        full3d_base_dofs=full3d_base_dofs,
        active_base_rows=active_base_rows,
        full3d_dof_limit=full3d_dof_limit,
    )
    owner_inputs = build_selected_p6_trace_orbit_owner_inputs(
        catalog,
        selected_physical_entity_ids=(
            closed.closure.selected_physical_entity_ids
        ),
    )
    selection_sha256 = canonical_selective_p6_trace_selection_sha256(
        closed_numbering=closed,
        geometry_key_sha256=catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=catalog.ordered_trace_basis_sha256,
    )
    row_plan = build_selective_p6_trace_mpi_row_plan(
        closed_numbering=closed,
        selected_orbit_owner_ranks=(
            owner_inputs.selected_orbit_owner_ranks
        ),
        owned_base_row_counts_by_rank=tuple(base_counts),
        owned_selected_trace_row_counts_by_rank=(
            owner_inputs.owned_selected_trace_row_counts_by_rank
        ),
        geometry_key_sha256=catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=catalog.ordered_trace_basis_sha256,
        selection_sha256=selection_sha256,
        expected_full3d_dof_limit=full3d_dof_limit,
        caller_qualified_geometry_key=True,
        caller_qualified_ordered_basis_identity=True,
        caller_qualified_representative_owners=True,
    )
    formal = bool(
        dwr_analysis.provenance.formal_actual_pde
        and discrete_gradient.formal_actual_pde
    )
    checks = MappingProxyType(
        {
            "DWR_and_catalog_hashes_match": True,
            "DWR_seeds_are_whole_physical_orbits": True,
            "exact_sequence_closure_pass": (
                closed.audit.get("pass") is True
            ),
            "full3d_budget_pass": (
                closed.closure.full3d_equivalent_dofs
                <= full3d_dof_limit
            ),
            "actual_owner_aware_row_plan_pass": (
                row_plan.audit.get("pass") is True
                and row_plan.actual_mesh is True
            ),
            "active_rows_cover_only_closed_orbits": (
                row_plan.quotient_active_increment
                == closed.closure.active_row_increment
            ),
            "inactive_modes_have_no_petsc_rows": (
                row_plan.audit["checks"][
                    "inactive_modes_have_no_row_descriptors"
                ]
                is True
            ),
            "full_p6_trace_matrix_not_constructed": (
                row_plan.audit["checks"][
                    "full_p6_matrix_not_constructed"
                ]
                is True
            ),
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "physical channel-DWR row-plan integration failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.physical-channel-dwr-trace-row-plan.v1"
            ),
            "status": (
                "actual_channel_dwr_exact_sequence_row_plan_pass"
                if formal
                else "analytic_fixture_exact_sequence_row_plan_pass"
            ),
            "pass": True,
            "formal_actual_pde_selection_input": formal,
            "formal_candidate_passed": False,
            "candidate_PDE_resolve_required": True,
            "full_12_power_and_amplitude_reaudit_required": True,
            "seed_orbit_ids": list(seed_selection.seed_orbit_ids),
            "seed_representative_entity_ids": list(
                seed_selection.seed_representative_entity_ids
            ),
            "exact_sequence_closure_added_representative_entity_ids": list(
                closed.closure.closure_added_trace_representative_ids
            ),
            "selected_representative_entity_ids": list(
                closed.closure.selected_trace_representative_ids
            ),
            "full3d_base_dofs": closed.closure.full3d_base_dofs,
            "full3d_equivalent_increment": (
                closed.closure.full3d_equivalent_increment
            ),
            "full3d_equivalent_dofs": (
                closed.closure.full3d_equivalent_dofs
            ),
            "full3d_dof_limit": full3d_dof_limit,
            "full3d_headroom": closed.closure.full3d_headroom,
            "active_base_rows": active_base_rows,
            "selected_missing_rows": row_plan.quotient_active_increment,
            "active_rows": row_plan.active_rows,
            "inactive_missing_petsc_rows": 0,
            "selection_sha256": row_plan.selection_sha256,
            "catalog_sha256": catalog.catalog_sha256,
            "trace_geometry_sha256": catalog.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                catalog.ordered_trace_basis_sha256
            ),
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return PhysicalChannelDWRTraceRowPlan(
        dwr_analysis=dwr_analysis,
        seed_selection=seed_selection,
        discrete_gradient_authority=discrete_gradient,
        exact_sequence_numbering=closed,
        row_plan=row_plan,
        audit=audit,
    )


def physical_channel_dwr_trace_row_plan_record(
    result: PhysicalChannelDWRTraceRowPlan,
) -> dict[str, Any]:
    """Return a compact JSON/checker input without solution vectors."""

    dwr = result.dwr_analysis
    physical_orbit_by_id = {
        orbit.orbit_id: orbit for orbit in dwr.layout.orbits
    }
    return {
        "schema_version": (
            "task035b.physical-channel-dwr-trace-selection-record.v1"
        ),
        "status": result.audit["status"],
        "pass": True,
        "formal_actual_pde_selection_input": result.audit[
            "formal_actual_pde_selection_input"
        ],
        "formal_candidate_passed": False,
        "source_commit": dwr.provenance.source_commit,
        "authorities": {
            "retained_candidate_record_sha256": (
                dwr.provenance.retained_candidate_record_sha256
            ),
            "significant_channel_reference_sha256": (
                dwr.provenance.significant_channel_reference_sha256
            ),
            "catalog_sha256": dwr.layout.catalog_sha256,
            "trace_geometry_sha256": dwr.layout.trace_geometry_sha256,
            "ordered_trace_basis_sha256": (
                dwr.layout.ordered_trace_basis_sha256
            ),
            "qualification_sha256": dwr.layout.qualification_sha256,
            "complement_layout_sha256": dwr.layout.layout_sha256,
            "selection_sha256": result.row_plan.selection_sha256,
        },
        "complement": {
            "evidence_class": dwr.provenance.evidence_class,
            "storage_kind": dwr.provenance.complement_storage_kind,
            "high_dimension": dwr.layout.high_dimension,
            "orbit_count": len(dwr.layout.orbits),
            "full_p6_trace_matrix_materialized": False,
            "inactive_p6_rows_allocated": 0,
        },
        "goals": {
            label: {
                "component": goal.component,
                "tolerance": goal.tolerance,
                "signed_component_correction": (
                    goal.signed_component_correction
                ),
                "normalized_signed_correction": (
                    goal.normalized_signed_correction
                ),
                "identity_relative_error": goal.identity_relative_error,
            }
            for label, goal in dwr.algebraic.goals.items()
        },
        "ranked_orbits": [
            {
                "rank": orbit.rank,
                "orbit_id": orbit.orbit_id,
                "representative_entity_id": (
                    physical_orbit_by_id[
                        orbit.orbit_id
                    ].representative_entity_id
                ),
                "entity_kind": physical_orbit_by_id[
                    orbit.orbit_id
                ].entity_kind,
                "missing_mode_count": len(orbit.complement_indices),
                "member_entity_ids": list(orbit.member_entity_ids),
                "complement_indices": list(orbit.complement_indices),
                "selection_score": orbit.selection_score,
                "target_net_absolute_error_improvement": (
                    orbit.target_net_absolute_error_improvement
                ),
                "target_regression_count": orbit.target_regression_count,
                "target_gate_crossing_count": (
                    orbit.target_gate_crossing_count
                ),
                "protected_regression_count": (
                    orbit.protected_regression_count
                ),
                "protected_gate_crossing_count": (
                    orbit.protected_gate_crossing_count
                ),
            }
            for orbit in dwr.algebraic.ranked_orbits
        ],
        "seed_selection": {
            "maximum_seed_orbits": (
                result.seed_selection.maximum_seed_orbits
            ),
            "target_matrix_rank": (
                result.seed_selection.target_matrix_rank
            ),
            "rank_span_complete": (
                result.seed_selection.rank_span_complete
            ),
            "rrqr_pivot_orbit_ids": list(
                result.seed_selection.rrqr_pivot_orbit_ids
            ),
            "seed_orbit_ids": list(result.seed_selection.seed_orbit_ids),
            "seed_representative_entity_ids": list(
                result.seed_selection.seed_representative_entity_ids
            ),
        },
        "exact_sequence": {
            "gradient_evidence_class": (
                result.discrete_gradient_authority.evidence_class
            ),
            "full3d_base_dofs": result.row_plan.full3d_base_dofs,
            "closure_added_representative_entity_ids": list(
                result.exact_sequence_numbering.closure
                .closure_added_trace_representative_ids
            ),
            "selected_representative_entity_ids": list(
                result.exact_sequence_numbering.closure
                .selected_trace_representative_ids
            ),
            "full3d_equivalent_increment": (
                result.row_plan.full3d_equivalent_increment
            ),
            "full3d_equivalent_dofs": (
                result.row_plan.full3d_equivalent_dofs
            ),
            "full3d_dof_limit": result.row_plan.full3d_dof_limit,
        },
        "row_plan": {
            "mpi_size": result.row_plan.mpi_size,
            "active_base_rows": result.row_plan.active_base_rows,
            "selected_missing_rows": (
                result.row_plan.quotient_active_increment
            ),
            "active_rows": result.row_plan.active_rows,
            "petsc_ownership_ranges": [
                list(value)
                for value in result.row_plan.petsc_ownership_ranges
            ],
            "inactive_missing_petsc_rows": 0,
            "full_p6_trace_matrix_constructed": False,
        },
        "remaining_gates": {
            "selected_space_PDE_resolve": "not_run",
            "MPI8": "not_run",
            "full_explicit_true_residual": "not_run",
            "R00_R_T_Aclosure_fields": "not_run",
            "significant_power_12_of_12": "not_run",
            "significant_complex_amplitude_12_of_12": "not_run",
        },
        "formal_h14_minimum_wiring": dict(FORMAL_H14_MINIMUM_WIRING),
        "ordinary_default_changed": False,
    }


def check_physical_channel_dwr_trace_row_plan_record(
    record: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Independently recompute compact selection and inactive-row gates."""

    checks: dict[str, bool] = {}
    failures: list[str] = []

    def check(name: str, passed: bool) -> None:
        value = bool(passed)
        checks[name] = value
        if not value:
            failures.append(name)

    try:
        check(
            "schema_is_supported",
            record.get("schema_version")
            == (
                "task035b.physical-channel-dwr-trace-selection-"
                "record.v1"
            ),
        )
        authorities = record["authorities"]
        for name in (
            "retained_candidate_record_sha256",
            "significant_channel_reference_sha256",
            "catalog_sha256",
            "trace_geometry_sha256",
            "ordered_trace_basis_sha256",
            "qualification_sha256",
            "complement_layout_sha256",
            "selection_sha256",
        ):
            try:
                _validated_sha256(authorities[name], label=name)
                valid = True
            except (KeyError, TypeError, ValueError):
                valid = False
            check(f"{name}_is_sha256", valid)

        complement = record["complement"]
        check(
            "full_p6_trace_matrix_not_materialized",
            complement.get("full_p6_trace_matrix_materialized") is False,
        )
        check(
            "inactive_complement_rows_are_zero",
            complement.get("inactive_p6_rows_allocated") == 0,
        )
        check(
            "complement_dimension_is_positive",
            int(complement.get("high_dimension", 0)) > 0,
        )

        goals = record["goals"]
        focus_components_match = all(
            label in goals and goals[label].get("component") == component
            for label, component in _FOCUS_GOAL_COMPONENTS.items()
        )
        check(
            "focus_power_real_imag_goals_are_complete",
            focus_components_match,
        )
        check(
            "goal_dwr_identities_pass",
            bool(goals)
            and all(
                np.isfinite(float(goal["identity_relative_error"]))
                and float(goal["identity_relative_error"]) <= 5.0e-11
                for goal in goals.values()
            ),
        )

        ranked = tuple(record["ranked_orbits"])
        orbit_by_representative: dict[int, Mapping[str, Any]] = {}
        orbit_ids: set[str] = set()
        complement_indices: set[int] = set()
        ranked_valid = True
        for orbit in ranked:
            representative = int(orbit["representative_entity_id"])
            members = tuple(map(int, orbit["member_entity_ids"]))
            indices = tuple(map(int, orbit["complement_indices"]))
            missing_modes = int(orbit["missing_mode_count"])
            orbit_id = str(orbit["orbit_id"])
            ranked_valid = bool(
                ranked_valid
                and representative >= 0
                and representative in members
                and len(members) == len(set(members))
                and len(indices) == missing_modes
                and len(indices) == len(set(indices))
                and not complement_indices.intersection(indices)
                and orbit_id not in orbit_ids
                and representative not in orbit_by_representative
                and orbit["entity_kind"] in {"edge", "face"}
            )
            orbit_ids.add(orbit_id)
            complement_indices.update(indices)
            orbit_by_representative[representative] = orbit
        check(
            "ranked_whole_orbits_are_unique_and_nonoverlapping",
            ranked_valid,
        )
        check(
            "ranked_orbits_partition_complement_dimension",
            complement_indices
            == set(range(int(complement["high_dimension"]))),
        )

        seeds = record["seed_selection"]
        seed_representatives = tuple(
            map(int, seeds["seed_representative_entity_ids"])
        )
        seed_orbit_ids = tuple(map(str, seeds["seed_orbit_ids"]))
        check(
            "seed_orbits_are_ranked_whole_orbits",
            len(seed_representatives) == len(seed_orbit_ids)
            and len(seed_representatives) > 0
            and len(set(seed_representatives)) == len(seed_representatives)
            and all(
                representative in orbit_by_representative
                for representative in seed_representatives
            )
            and all(orbit_id in orbit_ids for orbit_id in seed_orbit_ids),
        )
        check(
            "seed_count_respects_bound",
            len(seed_representatives)
            <= int(seeds["maximum_seed_orbits"]),
        )

        exact = record["exact_sequence"]
        selected_representatives = tuple(
            map(int, exact["selected_representative_entity_ids"])
        )
        check(
            "exact_sequence_selection_contains_all_seeds",
            set(seed_representatives).issubset(selected_representatives),
        )
        check(
            "selected_orbits_are_known_and_unique",
            len(selected_representatives)
            == len(set(selected_representatives))
            and all(
                representative in orbit_by_representative
                for representative in selected_representatives
            ),
        )
        selected_orbits = [
            orbit_by_representative[representative]
            for representative in sorted(selected_representatives)
        ]
        recomputed_full3d_increment = sum(
            int(orbit["missing_mode_count"])
            * len(orbit["member_entity_ids"])
            for orbit in selected_orbits
        )
        recomputed_quotient_increment = sum(
            int(orbit["missing_mode_count"])
            for orbit in selected_orbits
        )
        row_plan = record["row_plan"]
        check(
            "full3d_increment_recomputed_from_physical_orbits",
            recomputed_full3d_increment
            == int(exact["full3d_equivalent_increment"]),
        )
        check(
            "quotient_increment_recomputed_from_selected_orbits",
            recomputed_quotient_increment
            == int(row_plan["selected_missing_rows"]),
        )
        check(
            "full3d_total_and_budget_recompute",
            int(exact["full3d_equivalent_dofs"])
            == int(exact["full3d_base_dofs"])
            + recomputed_full3d_increment
            and int(exact["full3d_equivalent_dofs"])
            <= int(exact["full3d_dof_limit"]),
        )
        check(
            "active_rows_recompute",
            int(row_plan["active_rows"])
            == int(row_plan["active_base_rows"])
            + recomputed_quotient_increment,
        )
        check(
            "row_plan_has_no_inactive_rows_or_full_matrix",
            row_plan.get("inactive_missing_petsc_rows") == 0
            and row_plan.get("full_p6_trace_matrix_constructed") is False,
        )
        ownership_ranges = tuple(
            tuple(map(int, row_range))
            for row_range in row_plan["petsc_ownership_ranges"]
        )
        check(
            "petsc_ownership_ranges_are_contiguous",
            bool(ownership_ranges)
            and ownership_ranges[0][0] == 0
            and all(
                left[1] == right[0]
                for left, right in pairwise(ownership_ranges)
            )
            and ownership_ranges[-1][1] == int(row_plan["active_rows"]),
        )

        selection_payload = {
            "schema": "task035b.selective-p6-trace-selection.v1",
            "geometry_key_sha256": authorities[
                "trace_geometry_sha256"
            ],
            "ordered_trace_basis_sha256": authorities[
                "ordered_trace_basis_sha256"
            ],
            "selected_orbits": [
                {
                    "representative_entity_id": int(
                        orbit["representative_entity_id"]
                    ),
                    "member_entity_ids": list(
                        map(int, orbit["member_entity_ids"])
                    ),
                    "entity_kind": orbit["entity_kind"],
                    "missing_mode_count": int(
                        orbit["missing_mode_count"]
                    ),
                }
                for orbit in selected_orbits
            ],
            "full3d_base_dofs": int(exact["full3d_base_dofs"]),
            "full3d_equivalent_increment": (
                recomputed_full3d_increment
            ),
            "quotient_active_increment": recomputed_quotient_increment,
        }
        recomputed_selection_hash = hashlib.sha256(
            json.dumps(
                selection_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        check(
            "selection_sha256_recomputed",
            recomputed_selection_hash == authorities["selection_sha256"],
        )

        formal_input = record.get(
            "formal_actual_pde_selection_input"
        ) is True
        if formal_input:
            check(
                "formal_input_uses_actual_action_only_authorities",
                complement.get("evidence_class") == "actual_pde"
                and complement.get("storage_kind") == "action_only"
                and exact.get("gradient_evidence_class") == "actual_pde",
            )
        else:
            check(
                "fixture_or_incomplete_input_not_promoted",
                record.get("formal_candidate_passed") is False,
            )
        remaining = record["remaining_gates"]
        check(
            "postselection_PDE_gates_remain_not_run",
            bool(remaining)
            and set(remaining.values()) == {"not_run"}
            and record.get("formal_candidate_passed") is False,
        )
        wiring = record["formal_h14_minimum_wiring"]
        check(
            "old_h14_offline_reconstruction_is_forbidden",
            wiring.get("existing_h14_offline_reconstruction")
            == "not_authorized"
            and "stage4_retain_dual_recovery_context=False"
            in wiring.get(
                "existing_h14_offline_reconstruction_reason",
                "",
            ),
        )
        check(
            "ordinary_default_unchanged",
            record.get("ordinary_default_changed") is False,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        FloatingPointError,
    ) as exc:
        failures.append(
            f"record_parse_error:{type(exc).__name__}:{exc}"
        )

    passed = not failures and all(checks.values())
    return MappingProxyType(
        {
            "schema_version": (
                "task035b.physical-channel-dwr-trace-selection-"
                "checker.v1"
            ),
            "status": (
                "physical_channel_dwr_trace_selection_record_pass"
                if passed
                else "physical_channel_dwr_trace_selection_record_fail"
            ),
            "pass": passed,
            "checks": MappingProxyType(checks),
            "failures": tuple(failures),
            "trusts_record_status_field": False,
            "recomputes_selection_sha256": True,
            "ordinary_default_changed": False,
        }
    )


__all__ = [
    "EvidenceClass",
    "FORMAL_H14_MINIMUM_WIRING",
    "PhysicalChannelDWRAnalysis",
    "PhysicalChannelDWRTraceRowPlan",
    "PhysicalComplementDWRProvenance",
    "PhysicalDiscreteGradientAuthority",
    "PhysicalMissingTraceDWRLayout",
    "PhysicalMissingTraceDWROrbit",
    "RankRevealingDWRSeedSelection",
    "build_physical_channel_dwr_trace_row_plan",
    "build_physical_missing_trace_dwr_layout",
    "check_physical_channel_dwr_trace_row_plan_record",
    "evaluate_physical_channel_dwr",
    "expand_missing_trace_complement_vector_to_entities",
    "expand_missing_trace_complement_vector_to_full_p6_storage_entities",
    "physical_channel_dwr_trace_row_plan_record",
    "project_full_p6_storage_entity_duals_to_complement",
    "project_physical_missing_trace_entity_vectors",
    "select_rank_revealing_dwr_seed_orbits",
]
