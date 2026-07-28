"""Global numerical p7 shadow saturation for Task035e.

The p7 basis in this module is *shadow only*.  It supplies a global
complement correction and 59 Hermitian-adjoint solves for current production
spaces whose degrees remain in ``{4, 5, 6}``.  It never constructs a
production degree-7 plan and never counts shadow rows as production rows.

The module deliberately separates three kinds of evidence:

* the structural bridge enumerates every p6 target and constraint orbit;
* the compiled operator receipt binds real p7 tensors, local Schur blocks,
  hanging/Floquet constraints, and the DtN action;
* the physical endpoint receipt binds an independently postprocessed field.

Dense or synthetic PETSc systems exercise the algebra, but cannot produce a
formal ``measured_pass`` or ``measured_fail``.  Missing any live prerequisite
leaves the result ``unknown``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from petsc4py import PETSc

from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
    blind_tolerance,
)


P7_GLOBAL_CATALOG_SCHEMA = "task035e.p7-global-shadow-catalog.v1"
P7_COMPILED_ASSEMBLY_AUDIT_SCHEMA = (
    "task035e.p7-compiled-complement-assembly.v1"
)
P7_CONSTRAINT_AUDIT_SCHEMA = "task035e.p7-global-constraint-action.v1"
P7_OPERATOR_RECEIPT_SCHEMA = "task035e.p7-global-operator-receipt.v1"
P7_LIVE_ENDPOINT_AUDIT_SCHEMA = "task035e.p7-live-physical-endpoint.v1"
P7_ENDPOINT_RECEIPT_SCHEMA = "task035e.p7-physical-endpoint-receipt.v1"
P7_GLOBAL_EVIDENCE_SCHEMA = "task035e.p7-global-numerical-evidence.v1"
P7_GLOBAL_COVERAGE_SCHEMA = "task035e.p7-global-saturation-coverage.v1"
P7_GLOBAL_CAPABILITY_SCHEMA = "task035e.p7-global-shadow-capability.v1"

_BRIDGE_SCHEMA = "task035e.p7-saturation-structural-bridge.v1"
_PORT_SCHEMA = "task035d.variable-p-trace-only-port-operator.v1"
_FORMAL_MPI_SIZE = 8
_TRUE_RESIDUAL_LIMIT = 1.0e-9
_ADJOINT_RESIDUAL_LIMIT = 1.0e-9
_DWR_CLOSURE_LIMIT = 5.0e-10
_SATURATION_NORMALIZED_LIMIT = 0.5
_DWR_VERIFIED_GOAL_MINIMUM = 54
_SHA256_LENGTH = 64


class P7GlobalShadowError(ValueError):
    """Raised when p7 numerical evidence is malformed or cross-bound."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _array_sha256(values: Any, *, namespace: str) -> str:
    array = np.asarray(values)
    if np.iscomplexobj(array):
        canonical = np.ascontiguousarray(array, dtype=np.dtype("<c16"))
    elif np.issubdtype(array.dtype, np.integer):
        canonical = np.ascontiguousarray(array, dtype=np.dtype("<i8"))
    else:
        canonical = np.ascontiguousarray(array, dtype=np.dtype("<f8"))
    return hashlib.sha256(
        namespace.encode("ascii")
        + b"\0"
        + json.dumps(
            list(canonical.shape),
            separators=(",", ":"),
        ).encode("ascii")
        + b"\0"
        + canonical.tobytes()
    ).hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    if (
        len(normalized) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise P7GlobalShadowError(f"{label} must be a lowercase SHA-256")
    return normalized


def _closed_payload(
    payload: Mapping[str, Any],
    *,
    digest_key: str,
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    digest = payload.get(digest_key)
    if not isinstance(digest, str):
        return False
    unsigned = dict(payload)
    unsigned.pop(digest_key, None)
    return digest == _json_sha256(unsigned)


def _canonical_ids(values: Sequence[Any], *, label: str) -> tuple[str, ...]:
    result = tuple(str(value) for value in values)
    if any(not value for value in result):
        raise P7GlobalShadowError(f"{label} contains an empty identity")
    if result != tuple(sorted(set(result))):
        raise P7GlobalShadowError(
            f"{label} must be unique and canonically sorted"
        )
    return result


def _duplicate_ids(groups: Sequence[Sequence[str]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for group in groups:
        for value in group:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
    return sorted(duplicates)


def _port_operator_complete(port: Mapping[str, Any] | None) -> bool:
    if not isinstance(port, Mapping):
        return False
    checks = port.get("checks")
    return bool(
        port.get("schema_version") == _PORT_SCHEMA
        and port.get("pass") is True
        and isinstance(checks, Mapping)
        and checks
        and all(value is True for value in checks.values())
        and port.get("auxiliary_interior_columns_allocated") is False
    )


def p7_global_shadow_vector_sha256(values: Any) -> str:
    """Return a partition-bound identity for a dense or PETSc vector."""

    if isinstance(values, PETSc.Vec):
        comm = values.getComm().tompi4py()
        local = np.asarray(
            values.getArray(readonly=True),
            dtype=np.dtype("<c16"),
        ).copy()
        start, end = map(int, values.getOwnershipRange())
        local_digest = _array_sha256(
            local,
            namespace=(
                "task035e.p7-global-vector."
                f"rank{comm.rank}.rows{start}-{end}.v1"
            ),
        )
        return _json_sha256(
            {
                "global_size": int(values.getSize()),
                "ownership_ranges": comm.allgather([start, end]),
                "rank_local_sha256": comm.allgather(local_digest),
            }
        )
    vector = np.asarray(values, dtype=np.complex128)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        raise P7GlobalShadowError(
            "dense p7 global shadow vector must be finite and one-dimensional"
        )
    return _array_sha256(
        vector,
        namespace="task035e.p7-global-vector.dense.v1",
    )


def _petsc_matrix_sha256(matrix: PETSc.Mat) -> str:
    comm = matrix.getComm().tompi4py()
    row_start, row_end = map(int, matrix.getOwnershipRange())
    try:
        indptr, indices, values = matrix.getValuesCSR()
    except PETSc.Error as exc:
        raise P7GlobalShadowError(
            "formal p7 complement operator must expose distributed CSR"
        ) from exc
    local = {
        "rank": int(comm.rank),
        "row_range": [row_start, row_end],
        "indptr_sha256": _array_sha256(
            indptr,
            namespace=(
                f"task035e.p7-global-matrix.indptr.rank{comm.rank}.v1"
            ),
        ),
        "indices_sha256": _array_sha256(
            indices,
            namespace=(
                f"task035e.p7-global-matrix.indices.rank{comm.rank}.v1"
            ),
        ),
        "values_sha256": _array_sha256(
            values,
            namespace=(
                f"task035e.p7-global-matrix.values.rank{comm.rank}.v1"
            ),
        ),
    }
    return _json_sha256(
        {
            "size": list(map(int, matrix.getSize())),
            "rank_local": comm.allgather(local),
        }
    )


def _matrix_sha256(matrix: np.ndarray | PETSc.Mat) -> str:
    if isinstance(matrix, PETSc.Mat):
        return _petsc_matrix_sha256(matrix)
    operator = np.asarray(matrix, dtype=np.complex128)
    if (
        operator.ndim != 2
        or operator.shape[0] != operator.shape[1]
        or not np.all(np.isfinite(operator))
    ):
        raise P7GlobalShadowError(
            "dense p7 complement operator must be finite and square"
        )
    return _array_sha256(
        operator,
        namespace="task035e.p7-global-matrix.dense.v1",
    )


@dataclass(frozen=True, slots=True)
class P7GlobalCoverageCatalog:
    """Exact p6-target and p7 constraint-orbit inventory."""

    p6_target_ids: tuple[str, ...]
    periodic_orbit_ids: tuple[str, ...]
    hanging_orbit_ids: tuple[str, ...]
    audit: Mapping[str, Any]


def build_p7_global_coverage_catalog(
    structural_evidence: Mapping[str, Any],
) -> P7GlobalCoverageCatalog:
    """Derive the numerical coverage inventory from the structural bridge."""

    if not isinstance(structural_evidence, Mapping):
        raise P7GlobalShadowError("p7 structural evidence must be a mapping")
    if structural_evidence.get("schema_version") != _BRIDGE_SCHEMA:
        raise P7GlobalShadowError("p7 structural bridge schema differs")
    if not _closed_payload(
        structural_evidence,
        digest_key="evidence_sha256",
    ):
        raise P7GlobalShadowError("p7 structural bridge identity drifted")
    enumeration = structural_evidence.get("enumeration")
    component = structural_evidence.get("p7_component_binding")
    numbering = structural_evidence.get("production_numbering")
    mpi = structural_evidence.get("mpi")
    if not all(
        isinstance(row, Mapping)
        for row in (enumeration, component, numbering, mpi)
    ):
        raise P7GlobalShadowError(
            "p7 structural bridge lacks one required evidence section"
        )
    assert isinstance(enumeration, Mapping)
    assert isinstance(component, Mapping)
    assert isinstance(numbering, Mapping)
    assert isinstance(mpi, Mapping)
    p6_target_ids = _canonical_ids(
        enumeration.get("p6_target_ids", ()),
        label="p6 target inventory",
    )
    cell_orbits = enumeration.get("cell_orbits")
    periodic_orbits = enumeration.get("periodic_trace_orbits")
    hanging_audits = component.get("hanging_component_audits")
    if (
        not isinstance(cell_orbits, Sequence)
        or isinstance(cell_orbits, (str, bytes))
        or not isinstance(periodic_orbits, Sequence)
        or isinstance(periodic_orbits, (str, bytes))
        or not isinstance(hanging_audits, Sequence)
        or isinstance(hanging_audits, (str, bytes))
    ):
        raise P7GlobalShadowError(
            "p7 structural bridge orbit catalogs are malformed"
        )
    cell_targets = {
        str(row.get("target_id"))
        for row in cell_orbits
        if isinstance(row, Mapping)
    }
    if not set(p6_target_ids).issubset(cell_targets):
        raise P7GlobalShadowError(
            "p7 structural bridge omits one p6 cell complement orbit"
        )
    periodic_orbit_ids = tuple(
        sorted(
            "periodic:" + _json_sha256(row)
            for row in periodic_orbits
            if isinstance(row, Mapping)
        )
    )
    if len(periodic_orbit_ids) != len(periodic_orbits):
        raise P7GlobalShadowError(
            "p7 structural bridge has a malformed periodic orbit"
        )
    hanging_orbit_ids = tuple(
        sorted(
            f"hanging:{int(row['patch_index'])}"
            for row in hanging_audits
            if isinstance(row, Mapping) and "patch_index" in row
        )
    )
    if len(hanging_orbit_ids) != len(hanging_audits):
        raise P7GlobalShadowError(
            "p7 structural bridge has a malformed hanging orbit"
        )
    if len(set(periodic_orbit_ids)) != len(periodic_orbit_ids):
        raise P7GlobalShadowError("p7 periodic orbit identities collide")
    if len(set(hanging_orbit_ids)) != len(hanging_orbit_ids):
        raise P7GlobalShadowError("p7 hanging orbit identities collide")
    structural_formal = bool(
        structural_evidence.get("structural_coverage_pass") is True
        and structural_evidence.get(
            "mathematical_structural_coverage_pass"
        )
        is True
        and mpi.get("observed_size") == _FORMAL_MPI_SIZE
        and mpi.get("formal_partition_identity_status") == "pass"
        and mpi.get("all_rank_digest_pass") is True
        and numbering.get("p7_rows_added") == 0
        and numbering.get("inactive_p7_numbering_pass") is True
    )
    payload: dict[str, Any] = {
        "schema_version": P7_GLOBAL_CATALOG_SCHEMA,
        "status": (
            "p7_global_coverage_catalog_formal"
            if structural_formal
            else "p7_global_coverage_catalog_diagnostic"
        ),
        "structural_bridge_sha256": structural_evidence[
            "evidence_sha256"
        ],
        "structural_bridge_formal_mpi8": structural_formal,
        "p6_target_count": len(p6_target_ids),
        "p6_target_ids": list(p6_target_ids),
        "p6_target_ids_sha256": _json_sha256(
            {"p6_target_ids": list(p6_target_ids)}
        ),
        "periodic_orbit_count": len(periodic_orbit_ids),
        "periodic_orbit_ids": list(periodic_orbit_ids),
        "hanging_orbit_count": len(hanging_orbit_ids),
        "hanging_orbit_ids": list(hanging_orbit_ids),
        "production_degree_set": list(
            numbering.get("production_degrees", [])
        ),
        "production_p7_rows": int(numbering.get("p7_rows_added", -1)),
        "shadow_only": True,
        "selectable_as_production": False,
        "next_production_plan": None,
    }
    payload["catalog_sha256"] = _json_sha256(payload)
    return P7GlobalCoverageCatalog(
        p6_target_ids=p6_target_ids,
        periodic_orbit_ids=periodic_orbit_ids,
        hanging_orbit_ids=hanging_orbit_ids,
        audit=MappingProxyType(payload),
    )


@dataclass(frozen=True, slots=True)
class P7ComplementOperatorReceipt:
    """Hash-bound compiled or diagnostic p7 complement operator receipt."""

    covered_p6_target_ids: tuple[str, ...]
    covered_periodic_orbit_ids: tuple[str, ...]
    covered_hanging_orbit_ids: tuple[str, ...]
    audit: Mapping[str, Any]


def _coverage_subset(
    values: Sequence[Any],
    expected: tuple[str, ...],
    *,
    label: str,
) -> tuple[str, ...]:
    normalized = _canonical_ids(values, label=label)
    extras = sorted(set(normalized) - set(expected))
    if extras:
        raise P7GlobalShadowError(
            f"{label} contains identities absent from the catalog: {extras}"
        )
    return normalized


def build_p7_component_operator_receipt(
    matrix: np.ndarray | PETSc.Mat,
    catalog: P7GlobalCoverageCatalog,
    *,
    covered_p6_target_ids: Sequence[str] | None = None,
    covered_periodic_orbit_ids: Sequence[str] | None = None,
    covered_hanging_orbit_ids: Sequence[str] | None = None,
) -> P7ComplementOperatorReceipt:
    """Build an algebra-only receipt that can never receive formal credit."""

    return _build_operator_receipt(
        matrix,
        catalog,
        covered_p6_target_ids=(
            catalog.p6_target_ids
            if covered_p6_target_ids is None
            else covered_p6_target_ids
        ),
        covered_periodic_orbit_ids=(
            catalog.periodic_orbit_ids
            if covered_periodic_orbit_ids is None
            else covered_periodic_orbit_ids
        ),
        covered_hanging_orbit_ids=(
            catalog.hanging_orbit_ids
            if covered_hanging_orbit_ids is None
            else covered_hanging_orbit_ids
        ),
        assembly_audit=None,
        constraint_audit=None,
        port_operator_audit=None,
    )


def build_p7_compiled_operator_receipt(
    matrix: PETSc.Mat,
    catalog: P7GlobalCoverageCatalog,
    *,
    assembly_audit: Mapping[str, Any],
    constraint_audit: Mapping[str, Any],
    port_operator_audit: Mapping[str, Any],
) -> P7ComplementOperatorReceipt:
    """Validate caller-supplied component audits without granting credit.

    The actual compiled p7 live-view type does not exist yet.  Accepting
    arbitrary mappings as proof would make the formal Gate forgeable, so this
    constructor records their consistency but remains component-only.
    """

    if not isinstance(matrix, PETSc.Mat):
        raise P7GlobalShadowError(
            "formal p7 complement operator must be a PETSc matrix"
        )
    return _build_operator_receipt(
        matrix,
        catalog,
        covered_p6_target_ids=assembly_audit.get(
            "covered_p6_target_ids",
            (),
        ),
        covered_periodic_orbit_ids=assembly_audit.get(
            "covered_periodic_orbit_ids",
            (),
        ),
        covered_hanging_orbit_ids=assembly_audit.get(
            "covered_hanging_orbit_ids",
            (),
        ),
        assembly_audit=assembly_audit,
        constraint_audit=constraint_audit,
        port_operator_audit=port_operator_audit,
    )


def _build_operator_receipt(
    matrix: np.ndarray | PETSc.Mat,
    catalog: P7GlobalCoverageCatalog,
    *,
    covered_p6_target_ids: Sequence[Any],
    covered_periodic_orbit_ids: Sequence[Any],
    covered_hanging_orbit_ids: Sequence[Any],
    assembly_audit: Mapping[str, Any] | None,
    constraint_audit: Mapping[str, Any] | None,
    port_operator_audit: Mapping[str, Any] | None,
) -> P7ComplementOperatorReceipt:
    if not isinstance(catalog, P7GlobalCoverageCatalog) or not _closed_payload(
        catalog.audit,
        digest_key="catalog_sha256",
    ):
        raise P7GlobalShadowError("p7 global coverage catalog drifted")
    targets = _coverage_subset(
        covered_p6_target_ids,
        catalog.p6_target_ids,
        label="covered p6 targets",
    )
    periodic = _coverage_subset(
        covered_periodic_orbit_ids,
        catalog.periodic_orbit_ids,
        label="covered p7 periodic orbits",
    )
    hanging = _coverage_subset(
        covered_hanging_orbit_ids,
        catalog.hanging_orbit_ids,
        label="covered p7 hanging orbits",
    )
    matrix_sha = _matrix_sha256(matrix)
    if isinstance(matrix, PETSc.Mat):
        matrix_size = tuple(map(int, matrix.getSize()))
        comm_size = int(matrix.getComm().getSize())
        matrix_handle: int | None = int(matrix.handle)
        backend = "petsc_distributed_selected_p7_complement"
    else:
        operator = np.asarray(matrix)
        matrix_size = tuple(map(int, operator.shape))
        comm_size = 1
        matrix_handle = None
        backend = "dense_synthetic_selected_p7_complement"
    blockers: list[str] = []
    if not isinstance(assembly_audit, Mapping):
        blockers.append("compiled_p7_tensor_schur_receipt_missing")
        tensor_sha = None
        schur_sha = None
    else:
        tensor_sha = assembly_audit.get("compiled_p7_tensor_sha256")
        schur_sha = assembly_audit.get("compiled_schur_sha256")
        assembly_checks = {
            "compiled_assembly_schema": (
                assembly_audit.get("schema_version")
                == P7_COMPILED_ASSEMBLY_AUDIT_SCHEMA
            ),
            "compiled_p7_tensor_builder": (
                assembly_audit.get("compiled_p7_tensor_builder") is True
            ),
            "compiled_local_schur": (
                assembly_audit.get("compiled_local_schur") is True
            ),
            "matrix_identity": (
                assembly_audit.get("matrix_sha256") == matrix_sha
            ),
            "row_count": (
                assembly_audit.get("selected_shadow_rows")
                == matrix_size[0]
            ),
            "tensor_count": (
                isinstance(
                    assembly_audit.get("compiled_p7_tensor_count"),
                    int,
                )
                and assembly_audit["compiled_p7_tensor_count"] > 0
            ),
            "schur_count": (
                isinstance(
                    assembly_audit.get("compiled_schur_count"),
                    int,
                )
                and assembly_audit["compiled_schur_count"] > 0
            ),
            "tensor_sha256": (
                isinstance(tensor_sha, str)
                and len(tensor_sha) == _SHA256_LENGTH
            ),
            "schur_sha256": (
                isinstance(schur_sha, str)
                and len(schur_sha) == _SHA256_LENGTH
            ),
            "inactive_p7_not_numbered": (
                assembly_audit.get(
                    "inactive_p7_modes_globally_numbered"
                )
                is False
            ),
            "production_p7_rows_zero": (
                assembly_audit.get("production_p7_rows_numbered") is False
                and assembly_audit.get("production_p7_row_count") == 0
            ),
            "production_degrees_unchanged": (
                assembly_audit.get("production_degree_set") == [4, 5, 6]
            ),
        }
        blockers.extend(
            f"assembly_{name}_failed"
            for name, passed in assembly_checks.items()
            if not passed
        )
    if not isinstance(constraint_audit, Mapping):
        blockers.append("hanging_floquet_constraint_action_missing")
    else:
        constraint_checks = {
            "constraint_schema": (
                constraint_audit.get("schema_version")
                == P7_CONSTRAINT_AUDIT_SCHEMA
            ),
            "catalog_identity": (
                constraint_audit.get("catalog_sha256")
                == catalog.audit["catalog_sha256"]
            ),
            "hanging": (
                constraint_audit.get("hanging_constraint_pass") is True
            ),
            "floquet": (
                constraint_audit.get("floquet_constraint_pass") is True
            ),
            "periodic_orbit_closure": (
                constraint_audit.get("periodic_orbit_closure_pass") is True
            ),
            "no_production_p7_rows": (
                constraint_audit.get("production_p7_rows_numbered") is False
            ),
        }
        blockers.extend(
            f"constraint_{name}_failed"
            for name, passed in constraint_checks.items()
            if not passed
        )
    if not _port_operator_complete(port_operator_audit):
        blockers.append("full_floquet_dtn_port_action_missing")
    if not isinstance(matrix, PETSc.Mat):
        blockers.append("dense_synthetic_backend_has_no_formal_credit")
    if comm_size != _FORMAL_MPI_SIZE:
        blockers.append("selected_p7_complement_operator_is_not_mpi8")
    if catalog.audit.get("structural_bridge_formal_mpi8") is not True:
        blockers.append("structural_bridge_formal_mpi8_missing")
    if assembly_audit is not None:
        blockers.append("typed_live_compiled_operator_view_missing")
    payload: dict[str, Any] = {
        "schema_version": P7_OPERATOR_RECEIPT_SCHEMA,
        "status": (
            "compiled_p7_complement_operator_bound"
            if not blockers
            else "p7_complement_operator_component_only"
        ),
        "backend": backend,
        "formal_backend_qualified": not blockers,
        "formal_blockers": blockers,
        "catalog_sha256": catalog.audit["catalog_sha256"],
        "matrix_sha256": matrix_sha,
        "matrix_handle": matrix_handle,
        "matrix_size": list(matrix_size),
        "mpi_size": comm_size,
        "selected_shadow_rows": matrix_size[0],
        "compiled_p7_tensor_sha256": tensor_sha,
        "compiled_schur_sha256": schur_sha,
        "assembly_audit_sha256": (
            None if assembly_audit is None else _json_sha256(assembly_audit)
        ),
        "constraint_audit_sha256": (
            None
            if constraint_audit is None
            else _json_sha256(constraint_audit)
        ),
        "port_operator_audit_sha256": (
            None
            if port_operator_audit is None
            else _json_sha256(port_operator_audit)
        ),
        "covered_p6_target_ids": list(targets),
        "covered_periodic_orbit_ids": list(periodic),
        "covered_hanging_orbit_ids": list(hanging),
        "production_degree_set": [4, 5, 6],
        "production_p7_rows": 0,
        "inactive_p7_modes_in_production": 0,
        "shadow_only": True,
        "selectable_as_production": False,
        "next_production_plan": None,
    }
    payload["operator_receipt_sha256"] = _json_sha256(payload)
    return P7ComplementOperatorReceipt(
        covered_p6_target_ids=targets,
        covered_periodic_orbit_ids=periodic,
        covered_hanging_orbit_ids=hanging,
        audit=MappingProxyType(payload),
    )


@dataclass(frozen=True, slots=True)
class P7PhysicalEndpointReceipt:
    """Independent current-vs-p7-shadow physical goal observation."""

    current_goals: GoalVector
    shadow_goals: GoalVector
    audit: Mapping[str, Any]


def build_p7_physical_endpoint_receipt(
    operator_receipt: P7ComplementOperatorReceipt,
    *,
    current_goals: GoalVector,
    shadow_goals: GoalVector,
    correction_sha256: str,
    candidate_output_payload_sha256: str,
    watchdog_record_sha256: str,
    live_endpoint_audit: Mapping[str, Any] | None = None,
) -> P7PhysicalEndpointReceipt:
    """Bind a diagnostic endpoint which can never receive formal credit.

    A mapping is not a live numerical object.  Until the p7 runner exposes a
    typed view containing its PETSc matrix, solution vector, port action,
    residual, and postprocess payload, the formal endpoint is deliberately
    unreachable.
    """

    if not isinstance(
        operator_receipt,
        P7ComplementOperatorReceipt,
    ) or not _closed_payload(
        operator_receipt.audit,
        digest_key="operator_receipt_sha256",
    ):
        raise P7GlobalShadowError("p7 operator receipt identity drifted")
    if not isinstance(current_goals, GoalVector) or not isinstance(
        shadow_goals,
        GoalVector,
    ):
        raise P7GlobalShadowError(
            "p7 endpoint receipt requires two complete GoalVector objects"
        )
    if live_endpoint_audit is not None:
        raise P7GlobalShadowError(
            "caller Mapping cannot qualify a live p7 physical endpoint; "
            "a typed runner live view is not implemented"
        )
    blockers = [
        "typed_live_physical_endpoint_view_missing",
        "independent_live_physical_endpoint_missing",
    ]
    true_relative_residual: float | None = None
    payload: dict[str, Any] = {
        "schema_version": P7_ENDPOINT_RECEIPT_SCHEMA,
        "status": "p7_shadow_endpoint_component_only",
        "qualified_live_endpoint": False,
        "formal_blockers": blockers,
        "operator_receipt_sha256": operator_receipt.audit[
            "operator_receipt_sha256"
        ],
        "operator_matrix_sha256": operator_receipt.audit["matrix_sha256"],
        "correction_sha256": _sha256(
            correction_sha256,
            label="correction_sha256",
        ),
        "candidate_output_payload_sha256": _sha256(
            candidate_output_payload_sha256,
            label="candidate_output_payload_sha256",
        ),
        "watchdog_record_sha256": _sha256(
            watchdog_record_sha256,
            label="watchdog_record_sha256",
        ),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "current_goal_vector_sha256": current_goals.sha256,
        "shadow_goal_vector_sha256": shadow_goals.sha256,
        "full_explicit_true_relative_residual": true_relative_residual,
        "true_residual_limit": _TRUE_RESIDUAL_LIMIT,
        "live_endpoint_audit_sha256": None,
        "endpoint_values_caller_written": True,
        "production_degree_set": [4, 5, 6],
        "production_p7_rows": 0,
        "shadow_only": True,
        "selectable_as_production": False,
        "next_production_plan": None,
    }
    payload["endpoint_receipt_sha256"] = _json_sha256(payload)
    return P7PhysicalEndpointReceipt(
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        audit=MappingProxyType(payload),
    )


@dataclass(frozen=True, slots=True)
class P7GlobalGoalEvidence:
    """One signed DWR value and independent physical endpoint delta."""

    goal_id: str
    signed_dwr_delta: float
    direct_linear_delta: float
    actual_endpoint_delta: float
    blind_tolerance: float
    normalized_actual_delta: float
    dwr_direct_error: float
    effectivity: float | None
    safe_near_zero: bool
    sign_consistent: bool
    within_factor_two: bool
    dwr_verified: bool
    inside_saturation_budget: bool


@dataclass(frozen=True, slots=True)
class P7GlobalNumericalEvidence:
    """Global correction and all 59 p7-shadow adjoints."""

    goals: tuple[P7GlobalGoalEvidence, ...]
    audit: Mapping[str, Any]


def _dense_global_algebra(
    matrix: np.ndarray,
    residual: np.ndarray,
    expected_correction: np.ndarray,
    gradients: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    operator = np.asarray(matrix, dtype=np.complex128)
    right = np.asarray(residual, dtype=np.complex128)
    expected = np.asarray(expected_correction, dtype=np.complex128)
    if (
        operator.ndim != 2
        or operator.shape[0] != operator.shape[1]
        or right.shape != (operator.shape[0],)
        or expected.shape != right.shape
        or not np.all(np.isfinite(operator))
        or not np.all(np.isfinite(right))
        or not np.all(np.isfinite(expected))
    ):
        raise P7GlobalShadowError(
            "dense p7 global complement layout is inconsistent"
        )
    correction = np.linalg.solve(operator, right)
    correction_residual = operator @ correction - right
    correction_relative = float(
        np.linalg.norm(correction_residual)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )
    expected_error = float(
        np.linalg.norm(correction - expected)
        / max(np.linalg.norm(expected), np.finfo(float).tiny)
    )
    signed: dict[str, float] = {}
    direct: dict[str, float] = {}
    adjoint_relative: dict[str, float] = {}
    for goal_id in FORMAL_GOAL_IDS:
        gradient = np.asarray(gradients[goal_id], dtype=np.complex128)
        if gradient.shape != right.shape or not np.all(np.isfinite(gradient)):
            raise P7GlobalShadowError(
                "dense p7 goal gradients are inconsistent"
            )
        adjoint = np.linalg.solve(operator.conj().T, gradient)
        adjoint_residual = operator.conj().T @ adjoint - gradient
        adjoint_relative[goal_id] = float(
            np.linalg.norm(adjoint_residual)
            / max(np.linalg.norm(gradient), np.finfo(float).tiny)
        )
        signed[goal_id] = float(np.real(np.vdot(adjoint, right)))
        direct[goal_id] = float(np.real(np.vdot(gradient, correction)))
    return {
        "backend": "dense_synthetic_selected_p7_complement",
        "mpi_size": 1,
        "matrix_sha256": _matrix_sha256(operator),
        "residual_sha256": p7_global_shadow_vector_sha256(right),
        "expected_correction_sha256": (
            p7_global_shadow_vector_sha256(expected)
        ),
        "computed_correction_sha256": (
            p7_global_shadow_vector_sha256(correction)
        ),
        "correction_relative_residual": correction_relative,
        "expected_correction_relative_error": expected_error,
        "maximum_adjoint_relative_residual": max(
            adjoint_relative.values(),
            default=math.inf,
        ),
        "converged_adjoint_count": len(FORMAL_GOAL_IDS),
        "all_solves_converged": True,
        "signed": signed,
        "direct": direct,
    }


def _petsc_global_algebra(
    matrix: PETSc.Mat,
    residual: PETSc.Vec,
    expected_correction: PETSc.Vec,
    gradients: Mapping[str, PETSc.Vec],
    *,
    ksp: PETSc.KSP,
) -> dict[str, Any]:
    comm = matrix.getComm().tompi4py()
    size = tuple(map(int, matrix.getSize()))
    vectors = (residual, expected_correction, *gradients.values())
    if size[0] != size[1] or any(
        int(vector.getSize()) != size[0] for vector in vectors
    ):
        raise P7GlobalShadowError(
            "PETSc p7 global complement layout is inconsistent"
        )
    operator, preconditioner = ksp.getOperators()
    if int(operator.handle) != int(matrix.handle) or int(
        preconditioner.handle
    ) != int(matrix.handle):
        raise P7GlobalShadowError(
            "p7 global KSP does not use the supplied complement operator"
        )
    expected_range = tuple(map(int, residual.getOwnershipRange()))
    if any(
        tuple(map(int, vector.getOwnershipRange())) != expected_range
        for vector in vectors
    ):
        raise P7GlobalShadowError(
            "PETSc p7 global vector ownership differs"
        )
    correction = residual.duplicate()
    action = residual.duplicate()
    difference = residual.duplicate()
    try:
        ksp.solve(residual, correction)
        correction_reason = int(ksp.getConvergedReason())
        matrix.mult(correction, action)
        action.axpy(PETSc.ScalarType(-1.0), residual)
        correction_relative = float(
            action.norm(PETSc.NormType.NORM_2)
            / max(
                residual.norm(PETSc.NormType.NORM_2),
                np.finfo(float).tiny,
            )
        )
        expected_correction.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), correction)
        expected_error = float(
            difference.norm(PETSc.NormType.NORM_2)
            / max(
                expected_correction.norm(PETSc.NormType.NORM_2),
                np.finfo(float).tiny,
            )
        )
        signed: dict[str, float] = {}
        direct: dict[str, float] = {}
        maximum_adjoint_relative = 0.0
        converged_adjoint_count = 0
        all_converged = correction_reason > 0
        for goal_id in FORMAL_GOAL_IDS:
            gradient = gradients[goal_id]
            conjugated = gradient.copy()
            adjoint = gradient.duplicate()
            adjoint_action = gradient.duplicate()
            try:
                conjugated.conjugate()
                ksp.solveTranspose(conjugated, adjoint)
                reason = int(ksp.getConvergedReason())
                if reason > 0:
                    converged_adjoint_count += 1
                all_converged = all_converged and reason > 0
                adjoint.conjugate()
                matrix.multHermitian(adjoint, adjoint_action)
                adjoint_action.axpy(PETSc.ScalarType(-1.0), gradient)
                relative = float(
                    adjoint_action.norm(PETSc.NormType.NORM_2)
                    / max(
                        gradient.norm(PETSc.NormType.NORM_2),
                        np.finfo(float).tiny,
                    )
                )
                maximum_adjoint_relative = max(
                    maximum_adjoint_relative,
                    relative,
                )
                signed[goal_id] = float(adjoint.dot(residual).real)
                direct[goal_id] = float(gradient.dot(correction).real)
            finally:
                adjoint_action.destroy()
                adjoint.destroy()
                conjugated.destroy()
        return {
            "backend": "petsc_distributed_selected_p7_complement",
            "mpi_size": int(comm.size),
            "matrix_sha256": _petsc_matrix_sha256(matrix),
            "residual_sha256": p7_global_shadow_vector_sha256(residual),
            "expected_correction_sha256": (
                p7_global_shadow_vector_sha256(expected_correction)
            ),
            "computed_correction_sha256": (
                p7_global_shadow_vector_sha256(correction)
            ),
            "correction_relative_residual": correction_relative,
            "expected_correction_relative_error": expected_error,
            "maximum_adjoint_relative_residual": (
                maximum_adjoint_relative
            ),
            "converged_adjoint_count": converged_adjoint_count,
            "all_solves_converged": all_converged,
            "signed": signed,
            "direct": direct,
        }
    finally:
        difference.destroy()
        action.destroy()
        correction.destroy()


def evaluate_p7_global_shadow(
    catalog: P7GlobalCoverageCatalog,
    operator_receipt: P7ComplementOperatorReceipt,
    endpoint_receipt: P7PhysicalEndpointReceipt,
    *,
    matrix: np.ndarray | PETSc.Mat,
    projected_residual: np.ndarray | PETSc.Vec,
    expected_correction: np.ndarray | PETSc.Vec,
    goal_gradients: Mapping[str, np.ndarray | PETSc.Vec],
    ksp: PETSc.KSP | None = None,
) -> P7GlobalNumericalEvidence:
    """Solve the global correction and 59 actual ``A^H`` adjoints."""

    if tuple(goal_gradients) != FORMAL_GOAL_IDS:
        raise P7GlobalShadowError(
            "p7 global gradients must use the exact formal goal order"
        )
    if not isinstance(catalog, P7GlobalCoverageCatalog) or not _closed_payload(
        catalog.audit,
        digest_key="catalog_sha256",
    ):
        raise P7GlobalShadowError("p7 coverage catalog identity drifted")
    if not isinstance(
        operator_receipt,
        P7ComplementOperatorReceipt,
    ) or not _closed_payload(
        operator_receipt.audit,
        digest_key="operator_receipt_sha256",
    ):
        raise P7GlobalShadowError("p7 operator receipt identity drifted")
    if not isinstance(
        endpoint_receipt,
        P7PhysicalEndpointReceipt,
    ) or not _closed_payload(
        endpoint_receipt.audit,
        digest_key="endpoint_receipt_sha256",
    ):
        raise P7GlobalShadowError("p7 endpoint receipt identity drifted")
    matrix_sha = _matrix_sha256(matrix)
    if (
        operator_receipt.audit.get("catalog_sha256")
        != catalog.audit["catalog_sha256"]
        or operator_receipt.audit.get("matrix_sha256") != matrix_sha
        or endpoint_receipt.audit.get("operator_receipt_sha256")
        != operator_receipt.audit["operator_receipt_sha256"]
        or endpoint_receipt.audit.get("operator_matrix_sha256")
        != matrix_sha
    ):
        raise P7GlobalShadowError(
            "p7 catalog, operator, or endpoint identities differ"
        )
    petsc_backend = isinstance(matrix, PETSc.Mat)
    if petsc_backend:
        if (
            not isinstance(projected_residual, PETSc.Vec)
            or not isinstance(expected_correction, PETSc.Vec)
            or ksp is None
            or any(
                not isinstance(value, PETSc.Vec)
                for value in goal_gradients.values()
            )
        ):
            raise P7GlobalShadowError(
                "PETSc p7 global shadow inputs are incomplete"
            )
        algebra = _petsc_global_algebra(
            matrix,
            projected_residual,
            expected_correction,
            goal_gradients,
            ksp=ksp,
        )
    else:
        if (
            isinstance(projected_residual, PETSc.Vec)
            or isinstance(expected_correction, PETSc.Vec)
            or any(
                isinstance(value, PETSc.Vec)
                for value in goal_gradients.values()
            )
        ):
            raise P7GlobalShadowError(
                "dense and PETSc p7 global inputs are mixed"
            )
        algebra = _dense_global_algebra(
            np.asarray(matrix),
            np.asarray(projected_residual),
            np.asarray(expected_correction),
            goal_gradients,
        )
    if (
        endpoint_receipt.audit.get("correction_sha256")
        != algebra["expected_correction_sha256"]
    ):
        raise P7GlobalShadowError(
            "p7 physical endpoint binds another correction"
        )
    current_values = endpoint_receipt.current_goals.by_id
    shadow_values = endpoint_receipt.shadow_goals.by_id
    goals: list[P7GlobalGoalEvidence] = []
    dwr_closure_max = 0.0
    dwr_verified_count = 0
    active_effectivity_count = 0
    opposite_sign_goal_ids: list[str] = []
    for goal_id in FORMAL_GOAL_IDS:
        signed = float(algebra["signed"][goal_id])
        direct = float(algebra["direct"][goal_id])
        actual = float(shadow_values[goal_id] - current_values[goal_id])
        tolerance = blind_tolerance(
            goal_id,
            current_values,
            shadow_values,
        )
        normalized = abs(actual) / tolerance
        closure_error = abs(signed - direct)
        dwr_closure_max = max(dwr_closure_max, closure_error)
        safe_near_zero = (
            abs(signed) <= tolerance and abs(actual) <= tolerance
        )
        effectivity = (
            None
            if abs(actual) <= np.finfo(float).tiny
            else signed / actual
        )
        sign_consistent = safe_near_zero or signed * actual > 0.0
        within_factor_two = safe_near_zero or bool(
            effectivity is not None
            and 0.5 <= abs(effectivity) <= 2.0
        )
        dwr_verified = sign_consistent and within_factor_two
        dwr_verified_count += dwr_verified
        if not safe_near_zero:
            active_effectivity_count += 1
            if not sign_consistent:
                opposite_sign_goal_ids.append(goal_id)
        goals.append(
            P7GlobalGoalEvidence(
                goal_id=goal_id,
                signed_dwr_delta=signed,
                direct_linear_delta=direct,
                actual_endpoint_delta=actual,
                blind_tolerance=tolerance,
                normalized_actual_delta=normalized,
                dwr_direct_error=closure_error,
                effectivity=effectivity,
                safe_near_zero=safe_near_zero,
                sign_consistent=sign_consistent,
                within_factor_two=within_factor_two,
                dwr_verified=dwr_verified,
                inside_saturation_budget=(
                    normalized <= _SATURATION_NORMALIZED_LIMIT
                ),
            )
        )
    dwr_scale = max(
        (
            abs(row.signed_dwr_delta)
            for row in goals
        ),
        default=1.0,
    )
    dwr_scale = max(
        dwr_scale,
        max(
            (abs(row.direct_linear_delta) for row in goals),
            default=1.0,
        ),
        1.0,
    )
    blockers = list(operator_receipt.audit["formal_blockers"])
    blockers.extend(endpoint_receipt.audit["formal_blockers"])
    if algebra["backend"] != (
        "petsc_distributed_selected_p7_complement"
    ):
        blockers.append("dense_synthetic_backend_has_no_formal_credit")
    if int(algebra["mpi_size"]) != _FORMAL_MPI_SIZE:
        blockers.append("p7_global_shadow_is_not_mpi8")
    if catalog.audit.get("structural_bridge_formal_mpi8") is not True:
        blockers.append("p7_structural_bridge_formal_mpi8_missing")
    if operator_receipt.audit.get("formal_backend_qualified") is not True:
        blockers.append("compiled_p7_operator_not_qualified")
    if endpoint_receipt.audit.get("qualified_live_endpoint") is not True:
        blockers.append("independent_physical_endpoint_not_qualified")
    if not algebra["all_solves_converged"]:
        blockers.append("one_or_more_p7_global_solves_did_not_converge")
    if algebra["converged_adjoint_count"] != len(FORMAL_GOAL_IDS):
        blockers.append("not_all_59_p7_adjoint_solves_converged")
    if algebra["correction_relative_residual"] > _TRUE_RESIDUAL_LIMIT:
        blockers.append("p7_global_correction_residual_gate_failed")
    if (
        algebra["maximum_adjoint_relative_residual"]
        > _ADJOINT_RESIDUAL_LIMIT
    ):
        blockers.append("p7_global_adjoint_residual_gate_failed")
    if (
        algebra["expected_correction_relative_error"]
        > _TRUE_RESIDUAL_LIMIT
    ):
        blockers.append("p7_expected_correction_identity_failed")
    if dwr_closure_max > _DWR_CLOSURE_LIMIT * dwr_scale:
        blockers.append("p7_signed_dwr_direct_identity_failed")
    if dwr_verified_count < _DWR_VERIFIED_GOAL_MINIMUM:
        blockers.append("p7_actual_endpoint_effectivity_below_54_of_59")
    systematic_opposite_limit = math.floor(
        0.1 * active_effectivity_count
    )
    if len(opposite_sign_goal_ids) > systematic_opposite_limit:
        blockers.append("p7_high_priority_goals_systematically_opposite")
    blockers = sorted(set(blockers))
    formal_complete = not blockers
    payload: dict[str, Any] = {
        "schema_version": P7_GLOBAL_EVIDENCE_SCHEMA,
        "status": (
            "p7_global_numerical_component_complete"
            if formal_complete
            else "p7_global_numerical_component_formal_unknown"
        ),
        "p6_saturation_status": "unknown",
        "measured_pass": False,
        "measured_fail": False,
        "formal_component_complete": formal_complete,
        "formal_blockers": blockers,
        "catalog_sha256": catalog.audit["catalog_sha256"],
        "operator_receipt_sha256": operator_receipt.audit[
            "operator_receipt_sha256"
        ],
        "endpoint_receipt_sha256": endpoint_receipt.audit[
            "endpoint_receipt_sha256"
        ],
        "backend": algebra["backend"],
        "mpi_size": int(algebra["mpi_size"]),
        "matrix_sha256": algebra["matrix_sha256"],
        "projected_residual_sha256": algebra["residual_sha256"],
        "expected_correction_sha256": algebra[
            "expected_correction_sha256"
        ],
        "computed_correction_sha256": algebra[
            "computed_correction_sha256"
        ],
        "correction_relative_residual": algebra[
            "correction_relative_residual"
        ],
        "correction_residual_limit": _TRUE_RESIDUAL_LIMIT,
        "expected_correction_relative_error": algebra[
            "expected_correction_relative_error"
        ],
        "maximum_adjoint_relative_residual": algebra[
            "maximum_adjoint_relative_residual"
        ],
        "adjoint_residual_limit": _ADJOINT_RESIDUAL_LIMIT,
        "converged_adjoint_count": algebra["converged_adjoint_count"],
        "formal_goal_count": len(goals),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "signed_dwr_direct_closure_error_max": dwr_closure_max,
        "signed_dwr_direct_closure_limit": (
            _DWR_CLOSURE_LIMIT * dwr_scale
        ),
        "dwr_verified_goal_count": dwr_verified_count,
        "dwr_verified_goal_minimum": _DWR_VERIFIED_GOAL_MINIMUM,
        "active_effectivity_goal_count": active_effectivity_count,
        "opposite_sign_goal_count": len(opposite_sign_goal_ids),
        "opposite_sign_goal_ids": opposite_sign_goal_ids,
        "systematic_opposite_sign_limit": systematic_opposite_limit,
        "high_priority_goal_semantics": (
            "all 59 formal Task035e goals; near-zero pairs are safe only "
            "when both DWR and actual endpoint delta fit one blind tolerance"
        ),
        "normalized_max": max(
            (row.normalized_actual_delta for row in goals),
            default=0.0,
        ),
        "inside_saturation_budget_goal_count": sum(
            row.inside_saturation_budget for row in goals
        ),
        "saturation_normalized_limit": _SATURATION_NORMALIZED_LIMIT,
        "goal_rows": [
            {
                "goal_id": row.goal_id,
                "signed_dwr_delta": row.signed_dwr_delta,
                "direct_linear_delta": row.direct_linear_delta,
                "actual_endpoint_delta": row.actual_endpoint_delta,
                "blind_tolerance": row.blind_tolerance,
                "normalized_actual_delta": row.normalized_actual_delta,
                "dwr_direct_error": row.dwr_direct_error,
                "effectivity": row.effectivity,
                "safe_near_zero": row.safe_near_zero,
                "sign_consistent": row.sign_consistent,
                "within_factor_two": row.within_factor_two,
                "dwr_verified": row.dwr_verified,
                "inside_saturation_budget": (
                    row.inside_saturation_budget
                ),
            }
            for row in goals
        ],
        "covered_p6_target_ids": list(
            operator_receipt.covered_p6_target_ids
        ),
        "covered_periodic_orbit_ids": list(
            operator_receipt.covered_periodic_orbit_ids
        ),
        "covered_hanging_orbit_ids": list(
            operator_receipt.covered_hanging_orbit_ids
        ),
        "actual_global_correction_complete": True,
        "actual_59_goal_adjoint_complete": (
            algebra["converged_adjoint_count"] == len(FORMAL_GOAL_IDS)
        ),
        "actual_signed_dwr_complete": len(goals) == len(FORMAL_GOAL_IDS),
        "independent_physical_endpoint_consumed": True,
        "production_degree_set": [4, 5, 6],
        "production_p7_rows": 0,
        "shadow_only": True,
        "selectable_as_production": False,
        "next_production_plan": None,
    }
    payload["numerical_evidence_sha256"] = _json_sha256(payload)
    return P7GlobalNumericalEvidence(
        goals=tuple(goals),
        audit=MappingProxyType(payload),
    )


@dataclass(frozen=True, slots=True)
class P7GlobalSaturationCoverage:
    """Exact all-target/orbit p6-saturation classification."""

    audit: Mapping[str, Any]


def close_p7_global_saturation_coverage(
    catalog: P7GlobalCoverageCatalog,
    evidence: Sequence[P7GlobalNumericalEvidence],
) -> P7GlobalSaturationCoverage:
    """Return measured pass/fail only after every prerequisite is complete."""

    if not isinstance(catalog, P7GlobalCoverageCatalog) or not _closed_payload(
        catalog.audit,
        digest_key="catalog_sha256",
    ):
        raise P7GlobalShadowError("p7 coverage catalog identity drifted")
    rows = tuple(evidence)
    for row in rows:
        if not isinstance(
            row,
            P7GlobalNumericalEvidence,
        ) or not _closed_payload(
            row.audit,
            digest_key="numerical_evidence_sha256",
        ):
            raise P7GlobalShadowError(
                "p7 numerical coverage contains drifted evidence"
            )
        if row.audit.get("catalog_sha256") != catalog.audit[
            "catalog_sha256"
        ]:
            raise P7GlobalShadowError(
                "p7 numerical evidence binds another coverage catalog"
            )
    target_groups = [
        tuple(map(str, row.audit["covered_p6_target_ids"]))
        for row in rows
    ]
    periodic_groups = [
        tuple(map(str, row.audit["covered_periodic_orbit_ids"]))
        for row in rows
    ]
    hanging_groups = [
        tuple(map(str, row.audit["covered_hanging_orbit_ids"]))
        for row in rows
    ]
    observed_targets = set().union(*map(set, target_groups)) if rows else set()
    observed_periodic = (
        set().union(*map(set, periodic_groups)) if rows else set()
    )
    observed_hanging = (
        set().union(*map(set, hanging_groups)) if rows else set()
    )
    expected_targets = set(catalog.p6_target_ids)
    expected_periodic = set(catalog.periodic_orbit_ids)
    expected_hanging = set(catalog.hanging_orbit_ids)
    duplicate_targets = _duplicate_ids(target_groups)
    duplicate_periodic = _duplicate_ids(periodic_groups)
    duplicate_hanging = _duplicate_ids(hanging_groups)
    missing_targets = sorted(expected_targets - observed_targets)
    missing_periodic = sorted(expected_periodic - observed_periodic)
    missing_hanging = sorted(expected_hanging - observed_hanging)
    extra_targets = sorted(observed_targets - expected_targets)
    extra_periodic = sorted(observed_periodic - expected_periodic)
    extra_hanging = sorted(observed_hanging - expected_hanging)
    complete_coverage = not any(
        (
            duplicate_targets,
            duplicate_periodic,
            duplicate_hanging,
            missing_targets,
            missing_periodic,
            missing_hanging,
            extra_targets,
            extra_periodic,
            extra_hanging,
        )
    )
    fully_qualified = bool(
        rows
        and complete_coverage
        and all(
            row.audit.get("formal_component_complete") is True
            for row in rows
        )
    )
    failing_rows = [
        {
            "evidence_sha256": row.audit[
                "numerical_evidence_sha256"
            ],
            "goal_id": goal.goal_id,
            "actual_endpoint_delta": goal.actual_endpoint_delta,
            "blind_tolerance": goal.blind_tolerance,
            "normalized_actual_delta": goal.normalized_actual_delta,
        }
        for row in rows
        for goal in row.goals
        if not goal.inside_saturation_budget
    ]
    measured_pass = fully_qualified and not failing_rows
    measured_fail = fully_qualified and bool(failing_rows)
    status = (
        "measured_pass"
        if measured_pass
        else "measured_fail"
        if measured_fail
        else "unknown"
    )
    payload: dict[str, Any] = {
        "schema_version": P7_GLOBAL_COVERAGE_SCHEMA,
        "status": (
            "p7_global_saturation_measured_pass"
            if measured_pass
            else "p7_global_saturation_measured_fail"
            if measured_fail
            else "p7_global_saturation_formal_unknown"
        ),
        "p6_saturation_status": status,
        "measured_pass": measured_pass,
        "measured_fail": measured_fail,
        "controller_consumption_eligible": fully_qualified,
        "catalog_sha256": catalog.audit["catalog_sha256"],
        "expected_p6_target_count": len(expected_targets),
        "observed_p6_target_count": len(observed_targets),
        "missing_p6_target_ids": missing_targets,
        "extra_p6_target_ids": extra_targets,
        "duplicate_p6_target_ids": duplicate_targets,
        "expected_periodic_orbit_count": len(expected_periodic),
        "observed_periodic_orbit_count": len(observed_periodic),
        "missing_periodic_orbit_ids": missing_periodic,
        "extra_periodic_orbit_ids": extra_periodic,
        "duplicate_periodic_orbit_ids": duplicate_periodic,
        "expected_hanging_orbit_count": len(expected_hanging),
        "observed_hanging_orbit_count": len(observed_hanging),
        "missing_hanging_orbit_ids": missing_hanging,
        "extra_hanging_orbit_ids": extra_hanging,
        "duplicate_hanging_orbit_ids": duplicate_hanging,
        "all_p6_targets_and_orbits_covered": complete_coverage,
        "all_numerical_components_formally_complete": (
            fully_qualified and complete_coverage
        ),
        "numerical_evidence_sha256s": [
            row.audit["numerical_evidence_sha256"] for row in rows
        ],
        "saturation_normalized_limit": _SATURATION_NORMALIZED_LIMIT,
        "normalized_max": max(
            (
                goal.normalized_actual_delta
                for row in rows
                for goal in row.goals
            ),
            default=0.0,
        ),
        "failing_goal_count": len(failing_rows),
        "failing_goal_rows": failing_rows,
        "classification_note": (
            "measured pass/fail requires MPI8, compiled p7 tensors and "
            "Schur blocks, hanging/Floquet/DtN actions, a true-residual "
            "qualified physical endpoint, 59 A^H adjoints, and exact "
            "all-target/orbit coverage"
        ),
        "production_degree_set": [4, 5, 6],
        "production_p7_rows": 0,
        "production_plan_mutated": False,
        "selectable_as_production": False,
        "next_production_plan": None,
    }
    payload["coverage_sha256"] = _json_sha256(payload)
    return P7GlobalSaturationCoverage(
        audit=MappingProxyType(payload)
    )


def p7_global_shadow_backend_capability_report() -> Mapping[str, Any]:
    """Describe the ready algebra and the exact missing live runner adapters."""

    payload: dict[str, Any] = {
        "schema_version": P7_GLOBAL_CAPABILITY_SCHEMA,
        "status": (
            "global_algebra_ready_formal_live_receipts_unreachable"
        ),
        "p6_saturation_status": "unknown",
        "measured_pass": False,
        "formal_compiled_operator_receipt_reachable": False,
        "formal_physical_endpoint_receipt_reachable": False,
        "mapping_audits_can_grant_formal_credit": False,
        "completed_components": [
            "distributed selected-complement correction",
            "59 PETSc Hermitian-adjoint solves",
            "signed DWR/direct algebra identity",
            "independent physical endpoint receipt contract",
            "all-p6-target and constraint-orbit coverage aggregator",
            "fail-closed measured pass/fail classification",
        ],
        "live_runner_integration_gaps": [
            (
                "assemble one global selected p7-complement CSR from the "
                "compiled p7 cell tensors and local Schur blocks"
            ),
            (
                "scatter the enriched residual and all 59 physical goal "
                "gradients onto the selected complement ownership"
            ),
            (
                "apply the existing hanging, Floquet, and DtN operators to "
                "the same complement row identity"
            ),
            (
                "recover the p7-shadow field without numbering p7 rows in "
                "the production p4/p5/p6 system"
            ),
            (
                "postprocess a live independent 59-goal physical endpoint "
                "and bind its watchdog and full explicit residual"
            ),
            (
                "emit the compiled assembly and live endpoint schemas "
                "consumed by this module"
            ),
        ],
        "formal_mpi_size": _FORMAL_MPI_SIZE,
        "true_residual_limit": _TRUE_RESIDUAL_LIMIT,
        "adjoint_residual_limit": _ADJOINT_RESIDUAL_LIMIT,
        "dwr_verified_goal_minimum": _DWR_VERIFIED_GOAL_MINIMUM,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "production_degree_set": [4, 5, 6],
        "production_p7_rows": 0,
        "shadow_only": True,
        "selectable_as_production": False,
        "next_production_plan": None,
        "ordinary_default_changed": False,
    }
    payload["capability_sha256"] = _json_sha256(payload)
    return MappingProxyType(payload)


__all__ = [
    "P7_COMPILED_ASSEMBLY_AUDIT_SCHEMA",
    "P7_CONSTRAINT_AUDIT_SCHEMA",
    "P7_ENDPOINT_RECEIPT_SCHEMA",
    "P7_GLOBAL_CAPABILITY_SCHEMA",
    "P7_GLOBAL_CATALOG_SCHEMA",
    "P7_GLOBAL_COVERAGE_SCHEMA",
    "P7_GLOBAL_EVIDENCE_SCHEMA",
    "P7_LIVE_ENDPOINT_AUDIT_SCHEMA",
    "P7_OPERATOR_RECEIPT_SCHEMA",
    "P7ComplementOperatorReceipt",
    "P7GlobalCoverageCatalog",
    "P7GlobalGoalEvidence",
    "P7GlobalNumericalEvidence",
    "P7GlobalSaturationCoverage",
    "P7GlobalShadowError",
    "P7PhysicalEndpointReceipt",
    "build_p7_compiled_operator_receipt",
    "build_p7_component_operator_receipt",
    "build_p7_global_coverage_catalog",
    "build_p7_physical_endpoint_receipt",
    "close_p7_global_saturation_coverage",
    "evaluate_p7_global_shadow",
    "p7_global_shadow_backend_capability_report",
    "p7_global_shadow_vector_sha256",
]
