"""Global level-three h-saturation shadows for Task035e.

Production Task035e plans stop at dyadic level two.  This module owns a
strictly separate level-three *shadow* path.  It can reuse the qualified
variable-p assembly-time condensation backend on a level-three carrier, and
it can evaluate a complete augmented global operator through one primal
correction, 59 conjugate-transpose adjoints, and independently observed goal
endpoints.

The module never emits a production plan and never numbers a level-three row
in the production system.  A single orbit, a dense synthetic operator, a
cell-only operator without DtN, a non-MPI8 execution, or incomplete endpoint
provenance always leaves the formal saturation status ``unknown``.  Only a
complete set of independently qualified MPI8 orbit endpoints can be closed as
``measured_pass`` or ``measured_fail`` by the coverage authority.
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

from .blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    GoalVector,
    blind_tolerance,
)
from .stage4_local_h import (
    Stage4LocalHContext,
    build_stage4_local_h_reduction_authority,
)
from .task035e_h_saturation import (
    HLevel3ConstraintEvidence,
    HLevel3SaturationCatalog,
    HLevel3ShadowPatch,
    build_level3_h_saturation_catalog,
)
from .task035e_hp_transition import HPTransitionState
from .task035e_hp_transition import canonical_hp_cell_target_id


GLOBAL_CELL_SYSTEM_SCHEMA = "task035e.level3-shadow-cell-system.v1"
ENDPOINT_RECEIPT_SCHEMA = "task035e.level3-shadow-endpoint-receipt.v1"
GLOBAL_ORBIT_EVIDENCE_SCHEMA = "task035e.level3-global-orbit-evidence.v1"
GLOBAL_COVERAGE_SCHEMA = "task035e.level3-h-saturation-coverage.v1"
GLOBAL_CAPABILITY_SCHEMA = "task035e.level3-shadow-backend-capability.v1"
_TRUE_RESIDUAL_LIMIT = 1.0e-9
_ADJOINT_RESIDUAL_LIMIT = 1.0e-9
_DWR_VERIFIED_GOAL_MINIMUM = 54
_FREEZE_NORMALIZED_LIMIT = 0.5


def _jsonable(value: Any) -> Any:
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
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("global shadow evidence contains a non-finite float")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(
        "global shadow evidence contains a non-canonical object: "
        f"{type(value).__name__}"
    )


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _jsonable(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _array_sha256(values: Any, *, namespace: str) -> str:
    array = np.asarray(values)
    if np.issubdtype(array.dtype, np.complexfloating):
        canonical = np.asarray(array, dtype="<c16")
    elif np.issubdtype(array.dtype, np.floating):
        canonical = np.asarray(array, dtype="<f8")
    elif np.issubdtype(array.dtype, np.integer):
        canonical = np.asarray(array, dtype="<i8")
    else:
        raise TypeError(f"unsupported global shadow array dtype: {array.dtype}")
    contiguous = np.ascontiguousarray(canonical)
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(
        np.asarray(contiguous.shape, dtype="<i8").tobytes(order="C")
    )
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    result = str(value)
    if (
        len(result) != 64
        or any(character not in "0123456789abcdef" for character in result)
    ):
        raise ValueError(f"{label} must be one lowercase SHA-256")
    return result


def _closed_payload(
    payload: Mapping[str, Any],
    *,
    digest_key: str,
) -> bool:
    closed = dict(payload)
    digest = closed.pop(digest_key, None)
    return digest == _json_sha256(closed)


def _patch_gate(patch: HLevel3ShadowPatch) -> None:
    if not isinstance(patch, HLevel3ShadowPatch):
        raise ValueError("global shadow requires an HLevel3ShadowPatch")
    if not _closed_payload(patch.audit, digest_key="patch_sha256"):
        raise ValueError("global shadow patch identity drifted")
    if (
        patch.audit.get("structural_geometry_pass") is not True
        or patch.audit.get("shadow_only") is not True
        or patch.audit.get("production_plan_mutated") is not False
        or patch.audit.get("production_level_three_selectable") is not False
        or patch.audit.get("production_level_three_rows_numbered") is not False
        or not patch.level_three_leaf_keys
    ):
        raise ValueError("global shadow patch is not a closed shadow-only mesh")


def _constraint_gate(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
) -> None:
    _patch_gate(patch)
    if not isinstance(constraints, HLevel3ConstraintEvidence):
        raise ValueError("global shadow requires level3 constraint evidence")
    if not _closed_payload(
        constraints.audit,
        digest_key="constraint_evidence_sha256",
    ):
        raise ValueError("global shadow constraint identity drifted")
    if (
        constraints.audit.get("patch_sha256")
        != patch.audit.get("patch_sha256")
        or constraints.audit.get("structural_constraint_pass") is not True
        or constraints.audit.get("hanging_constraints_complete") is not True
        or constraints.audit.get("periodic_cycle_closure") is not True
        or constraints.audit.get("production_rows_numbered") is not False
    ):
        raise ValueError("global shadow constraints are incomplete")


def level3_shadow_backend_capability_report() -> Mapping[str, Any]:
    """Publish the exact reusable route and current public-API blockers."""

    payload: dict[str, Any] = {
        "schema_version": GLOBAL_CAPABILITY_SCHEMA,
        "status": "equivalent_full_shadow_route_available_incremental_blocked",
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "freezing_credit": False,
        "reusable_public_components": [
            {
                "function": (
                    "src.adaptivity.dyadic_hexa_refinement."
                    "refine_balanced_dyadic_hexa_forest"
                ),
                "role": "real balanced level3 geometry",
            },
            {
                "function": (
                    "src.adaptivity.stage4_local_h."
                    "build_stage4_local_h_reduction_authority"
                ),
                "role": "variable exact-sequence hanging/Floquet rows",
            },
            {
                "function": (
                    "src.solvers.hcurl_variable_p_assembly."
                    "build_variable_p_condensed_trace_system_from_compiled_form"
                ),
                "role": "p6 tensor evaluation and variable-p cell Schur assembly",
            },
        ],
        "compiled_tensor_shape": [882, 882],
        "compiled_tensor_requirement": (
            "one full p6 hexa tensor per locally owned shadow cell; "
            "persistent tensor classes may be reused"
        ),
        "equivalent_complete_shadow_system_available": True,
        "child_only_incremental_shadow_system_available": False,
        "missing_public_interfaces": [
            {
                "name": "append_level3_child_schur_delta",
                "missing_contract": (
                    "no public builder accepts only removed parents plus "
                    "new level3 child tensors and updates CSR/preallocation"
                ),
            },
            {
                "name": "standalone_variable_p_dtn_augmentation",
                "missing_contract": (
                    "Floquet/DtN auxiliary row insertion and RHS construction "
                    "remain internal to solve_stage4_3d_dtn"
                ),
            },
            {
                "name": "standalone_level3_live_view_factory",
                "missing_contract": (
                    "Stage4VariablePLiveView is published only inside the "
                    "qualified solve callback lifecycle"
                ),
            },
        ],
        "production_plan_maximum_level": 2,
        "shadow_maximum_level": 3,
        "production_plan_parser_accepts_level3": False,
        "production_plan_mutated": False,
        "production_level_three_rows_numbered": False,
        "recommended_current_route": (
            "build a complete shadow-only level3 carrier; reuse cached p6 "
            "tensor classes; assemble an equivalent complete condensed cell "
            "system; augment and solve through a dedicated shadow callback"
        ),
    }
    payload["capability_sha256"] = _json_sha256(payload)
    return MappingProxyType(payload)


@dataclass
class HLevel3ShadowCellSystem:
    """Cell Schur plus exact hanging/Floquet rows on the shadow carrier."""

    patch: HLevel3ShadowPatch
    constraints: HLevel3ConstraintEvidence
    reduction_authority: Any
    system: Any
    audit: Mapping[str, Any]
    _destroyed: bool = False

    def destroy(self) -> None:
        """Release the shadow-only PETSc matrix exactly once."""

        if self._destroyed:
            return
        self._destroyed = True
        self.system.destroy()

    def __enter__(self) -> HLevel3ShadowCellSystem:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.destroy()


def _shadow_context(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
) -> Stage4LocalHContext:
    degree_by_box = {
        cell.box: int(patch.cell_degree_by_key[cell.key])
        for cell in patch.forest.leaves
    }
    mesh_audit = MappingProxyType(
        {
            "schema_version": "task035e.stage4-multilevel-local-h-mesh.v1",
            "status": "level3_shadow_only_mesh_component",
            "pass": True,
            "shadow_only": True,
            "production_maximum_level": 2,
            "shadow_maximum_level": 3,
            "production_plan_mutated": False,
            "production_level_three_selectable": False,
            "production_level_three_rows_numbered": False,
            "patch_sha256": patch.audit["patch_sha256"],
            "leaf_catalog_sha256": patch.audit[
                "shadow_leaf_catalog_sha256"
            ],
            "hanging_face_catalog_sha256": patch.audit[
                "shadow_hanging_face_catalog_sha256"
            ],
            "constraint_evidence_sha256": constraints.audit[
                "constraint_evidence_sha256"
            ],
            "ordinary_default_changed": False,
        }
    )
    return Stage4LocalHContext(
        forest=patch.forest,
        carrier=constraints.carrier,
        plan_path="shadow-only-level3-no-production-plan",
        plan_file_sha256=patch.audit["patch_sha256"],
        trace_degree=min(degree_by_box.values()),
        cell_interior_degree=6,
        cell_interior_degree_by_box=MappingProxyType(degree_by_box),
        variable_trace_from_cell_degrees=True,
        selected_p6_face_geometry_keys=(),
        audit=mesh_audit,
    )


def build_level3_shadow_cell_system_from_compiled_form(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
    *,
    compiled_p6_form: Any,
    p6_space: Any,
    cell_tags: Any,
    phase_x: complex,
    phase_y: complex,
    persistent_raw_tensor_cache_directory: str | None = None,
    persistent_raw_tensor_cache_namespace: str | None = None,
) -> HLevel3ShadowCellSystem:
    """Reuse the qualified variable-p condensed builder on the shadow mesh.

    The existing builder requires one tensor for every shadow cell.  Its
    persistent class cache can reuse unchanged tensor classes, but there is no
    public child-only delta-assembly API.  This adapter therefore constructs
    the equivalent complete shadow cell system and records that limitation.
    DtN rows are still absent at this stage.
    """

    from src.solvers.hcurl_variable_p_assembly import (
        build_variable_p_condensed_trace_system_from_compiled_form,
    )

    _constraint_gate(patch, constraints)
    context = _shadow_context(patch, constraints)
    if p6_space.mesh is not context.carrier.mesh:
        raise ValueError("compiled p6 space does not use the level3 carrier")
    reduction = build_stage4_local_h_reduction_authority(
        context,
        phase_x=complex(phase_x),
        phase_y=complex(phase_y),
    )
    if (
        reduction.audit["physical_trace"]["physical_authority_sha256"]
        != constraints.audit["physical_authority_sha256"]
    ):
        raise RuntimeError("replayed level3 trace authority identity drifted")
    system = build_variable_p_condensed_trace_system_from_compiled_form(
        compiled_p6_form,
        p6_space,
        cell_tags,
        reduction.degree_plan.entity_map,
        trace_constraints=reduction.trace_constraints,
        persistent_raw_tensor_cache_directory=(
            persistent_raw_tensor_cache_directory
        ),
        persistent_raw_tensor_cache_namespace=(
            persistent_raw_tensor_cache_namespace
        ),
    )
    audit_payload: dict[str, Any] = {
        "schema_version": GLOBAL_CELL_SYSTEM_SCHEMA,
        "status": "level3_shadow_cell_schur_hanging_floquet_complete",
        "component_pass": True,
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "freezing_credit": False,
        "patch_sha256": patch.audit["patch_sha256"],
        "constraint_evidence_sha256": constraints.audit[
            "constraint_evidence_sha256"
        ],
        "physical_authority_sha256": constraints.audit[
            "physical_authority_sha256"
        ],
        "compiled_p6_tensor_builder": system.build_audit.get(
            "compiled_p6_tensor_builder"
        )
        is True,
        "compiled_trace_constraint_binding_complete": system.build_audit.get(
            "compiled_trace_constraint_binding_complete"
        )
        is True,
        "active_trace_rows": int(system.active_trace_rows),
        "matrix_rows": int(system.matrix.getSize()[0]),
        "inactive_shadow_rows_in_production": 0,
        "production_plan_mutated": False,
        "production_level_three_rows_numbered": False,
        "shadow_only_matrix": True,
        "cell_schur_complete": True,
        "hanging_floquet_complete": True,
        "dtn_operator_complete": False,
        "rhs_complete": False,
        "global_shadow_solve_complete": False,
        "child_only_incremental_assembly_api_available": False,
        "equivalent_complete_shadow_cell_assembly_used": True,
        "unchanged_tensor_classes_cache_reusable": True,
        "structural_blockers": [
            "public_variable_p_builder_requires_all_shadow_cell_tensors",
            "dtn_augmentation_is_internal_to_stage4_dtn_solve_flow",
            "global_shadow_rhs_not_built_by_cell_system_adapter",
            "global_shadow_endpoint_not_observed",
        ],
    }
    audit_payload["cell_system_sha256"] = _json_sha256(audit_payload)
    return HLevel3ShadowCellSystem(
        patch=patch,
        constraints=constraints,
        reduction_authority=reduction,
        system=system,
        audit=MappingProxyType(audit_payload),
    )


def global_shadow_vector_sha256(values: Any) -> str:
    """Return a partition-bound identity for one dense or PETSc vector."""

    if isinstance(values, PETSc.Vec):
        comm = values.getComm().tompi4py()
        local = np.asarray(
            values.getArray(readonly=True),
            dtype="<c16",
        ).copy()
        local_digest = _array_sha256(
            local,
            namespace=f"task035e.level3-shadow-vector.rank{comm.rank}.v1",
        )
        ranges = tuple(
            tuple(map(int, row))
            for row in comm.allgather(values.getOwnershipRange())
        )
        rank_digests = tuple(comm.allgather(local_digest))
        return _json_sha256(
            {
                "global_size": int(values.getSize()),
                "ownership_ranges": ranges,
                "rank_local_sha256": rank_digests,
            }
        )
    vector = np.asarray(values, dtype=np.complex128)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        raise ValueError("dense global shadow vector must be finite and 1D")
    return _array_sha256(
        vector,
        namespace="task035e.level3-shadow-vector.dense.v1",
    )


@dataclass(frozen=True, slots=True)
class HLevel3EndpointReceipt:
    """Hash-bound independent physical-goal observation at one endpoint."""

    current_goals: GoalVector
    shadow_goals: GoalVector
    audit: Mapping[str, Any]


def build_level3_endpoint_receipt(
    patch: HLevel3ShadowPatch,
    *,
    current_goals: GoalVector,
    shadow_goals: GoalVector,
    shadow_solution_sha256: str,
    candidate_output_payload_sha256: str,
    watchdog_record_sha256: str,
    actual_field_postprocess: bool,
) -> HLevel3EndpointReceipt:
    """Build a component receipt which deliberately has no formal credit.

    A formally qualified physical endpoint must use
    :func:`build_level3_endpoint_receipt_from_live_view`; accepting a caller
    boolean here would make the numerical Gate forgeable.
    """

    _patch_gate(patch)
    if not isinstance(current_goals, GoalVector) or not isinstance(
        shadow_goals,
        GoalVector,
    ):
        raise ValueError("endpoint receipt requires two GoalVector objects")
    if type(actual_field_postprocess) is not bool:
        raise ValueError("actual_field_postprocess must be boolean")
    if actual_field_postprocess:
        raise ValueError(
            "formal endpoint receipts require a qualified live view"
        )
    audit_payload: dict[str, Any] = {
        "schema_version": ENDPOINT_RECEIPT_SCHEMA,
        "status": "synthetic_level3_shadow_endpoint_component",
        "patch_sha256": patch.audit["patch_sha256"],
        "shadow_solution_sha256": _sha256(
            shadow_solution_sha256,
            label="shadow_solution_sha256",
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
        "actual_field_postprocess": actual_field_postprocess,
        "qualified_live_view": False,
        "live_view_matrix_handle": None,
        "live_view_port_operator_sha256": None,
        "endpoint_values_caller_written": not actual_field_postprocess,
        "production_plan_mutated": False,
        "production_level_three_rows_numbered": False,
    }
    audit_payload["endpoint_receipt_sha256"] = _json_sha256(audit_payload)
    return HLevel3EndpointReceipt(
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        audit=MappingProxyType(audit_payload),
    )


def build_level3_endpoint_receipt_from_live_view(
    patch: HLevel3ShadowPatch,
    *,
    live_view: Any,
    current_goals: GoalVector,
    shadow_goals: GoalVector,
    candidate_output_payload_sha256: str,
    watchdog_record_sha256: str,
) -> HLevel3EndpointReceipt:
    """Bind one actual MPI8 Stage4 field endpoint to its borrowed live view."""

    from src.solvers.dtn_port_3d import Stage4VariablePLiveView

    _patch_gate(patch)
    if not isinstance(live_view, Stage4VariablePLiveView):
        raise ValueError("formal endpoint requires Stage4VariablePLiveView")
    if not isinstance(current_goals, GoalVector) or not isinstance(
        shadow_goals,
        GoalVector,
    ):
        raise ValueError("endpoint receipt requires two GoalVector objects")
    comm = live_view.A.getComm().tompi4py()
    local_h = live_view.reduction.build_audit.get("local_h")
    mesh_audit = (
        local_h.get("mesh") if isinstance(local_h, Mapping) else None
    )
    residual = live_view.full_active_residual
    relative = (
        residual.get("linear_system_relative_residual")
        if isinstance(residual, Mapping)
        else None
    )
    if (
        comm.size != 8
        or not isinstance(mesh_audit, Mapping)
        or mesh_audit.get("leaf_catalog_sha256")
        != patch.audit["shadow_leaf_catalog_sha256"]
        or live_view.reduction.system.build_audit.get(
            "compiled_p6_tensor_builder"
        )
        is not True
        or not _port_operator_complete(live_view.port_operator_audit)
        or not isinstance(relative, (float, int))
        or not math.isfinite(float(relative))
        or float(relative) > _TRUE_RESIDUAL_LIMIT
    ):
        raise ValueError("level3 live view lacks a formal numerical Gate")
    port_sha = _json_sha256(live_view.port_operator_audit)
    audit_payload: dict[str, Any] = {
        "schema_version": ENDPOINT_RECEIPT_SCHEMA,
        "status": "actual_level3_shadow_field_endpoint_observed",
        "patch_sha256": patch.audit["patch_sha256"],
        "shadow_solution_sha256": global_shadow_vector_sha256(live_view.x),
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
        "actual_field_postprocess": True,
        "qualified_live_view": True,
        "live_view_matrix_handle": int(live_view.A.handle),
        "live_view_port_operator_sha256": port_sha,
        "live_view_true_relative_residual": float(relative),
        "endpoint_values_caller_written": False,
        "production_plan_mutated": False,
        "production_level_three_rows_numbered": False,
    }
    audit_payload["endpoint_receipt_sha256"] = _json_sha256(audit_payload)
    return HLevel3EndpointReceipt(
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        audit=MappingProxyType(audit_payload),
    )


def _endpoint_gate(
    patch: HLevel3ShadowPatch,
    receipt: HLevel3EndpointReceipt,
    *,
    shadow_solution_sha256: str,
) -> None:
    if not isinstance(receipt, HLevel3EndpointReceipt):
        raise ValueError("global shadow requires an endpoint receipt")
    if not _closed_payload(
        receipt.audit,
        digest_key="endpoint_receipt_sha256",
    ):
        raise ValueError("endpoint receipt identity drifted")
    if (
        receipt.audit.get("patch_sha256") != patch.audit.get("patch_sha256")
        or receipt.audit.get("shadow_solution_sha256")
        != shadow_solution_sha256
        or receipt.audit.get("current_goal_vector_sha256")
        != receipt.current_goals.sha256
        or receipt.audit.get("shadow_goal_vector_sha256")
        != receipt.shadow_goals.sha256
    ):
        raise ValueError("endpoint receipt content binding drifted")


@dataclass(frozen=True, slots=True)
class HLevel3GlobalGoalEvidence:
    """One signed DWR prediction and independently observed endpoint."""

    goal_id: str
    signed_dwr_delta: float
    linearized_endpoint_delta: float
    actual_endpoint_delta: float
    blind_tolerance: float
    normalized_actual_delta: float
    sign_consistent: bool
    within_factor_two: bool
    verified: bool
    inside_saturation_budget: bool


@dataclass(frozen=True, slots=True)
class HLevel3GlobalOrbitEvidence:
    """Complete global algebra for one selected level-two periodic orbit."""

    goals: tuple[HLevel3GlobalGoalEvidence, ...]
    audit: Mapping[str, Any]


def _dense_global_algebra(
    matrix: np.ndarray,
    rhs: np.ndarray,
    current: np.ndarray,
    expected_shadow: np.ndarray,
    gradients: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    operator = np.asarray(matrix, dtype=np.complex128)
    right = np.asarray(rhs, dtype=np.complex128)
    injected = np.asarray(current, dtype=np.complex128)
    expected = np.asarray(expected_shadow, dtype=np.complex128)
    if (
        operator.ndim != 2
        or operator.shape[0] != operator.shape[1]
        or right.shape != (operator.shape[0],)
        or injected.shape != right.shape
        or expected.shape != right.shape
        or not np.all(np.isfinite(operator))
        or not np.all(np.isfinite(right))
        or not np.all(np.isfinite(injected))
        or not np.all(np.isfinite(expected))
    ):
        raise ValueError("dense global shadow operator layout is inconsistent")
    ordered = {
        goal_id: np.asarray(gradients[goal_id], dtype=np.complex128)
        for goal_id in FORMAL_GOAL_IDS
    }
    if any(
        value.shape != right.shape or not np.all(np.isfinite(value))
        for value in ordered.values()
    ):
        raise ValueError("dense global shadow gradients are inconsistent")
    residual = right - operator @ injected
    correction = np.linalg.solve(operator, residual)
    shadow = injected + correction
    expected_error = float(
        np.linalg.norm(shadow - expected)
        / max(np.linalg.norm(expected), np.finfo(float).tiny)
    )
    true_residual = operator @ shadow - right
    true_relative = float(
        np.linalg.norm(true_residual)
        / max(np.linalg.norm(right), np.finfo(float).tiny)
    )
    signed: dict[str, float] = {}
    linear: dict[str, float] = {}
    adjoint_relative: dict[str, float] = {}
    for goal_id, gradient in ordered.items():
        adjoint = np.linalg.solve(operator.conj().T, gradient)
        adjoint_residual = operator.conj().T @ adjoint - gradient
        relative = float(
            np.linalg.norm(adjoint_residual)
            / max(np.linalg.norm(gradient), np.finfo(float).tiny)
        )
        adjoint_relative[goal_id] = relative
        signed[goal_id] = float(np.real(np.vdot(adjoint, residual)))
        linear[goal_id] = float(np.real(np.vdot(gradient, correction)))
    return {
        "backend": "dense_synthetic_component",
        "mpi_size": 1,
        "matrix_sha256": _array_sha256(
            operator,
            namespace="task035e.level3-global-matrix.dense.v1",
        ),
        "rhs_sha256": global_shadow_vector_sha256(right),
        "current_sha256": global_shadow_vector_sha256(injected),
        "shadow_sha256": global_shadow_vector_sha256(expected),
        "computed_shadow_sha256": global_shadow_vector_sha256(shadow),
        "signed": signed,
        "linear": linear,
        "true_relative_residual": true_relative,
        "expected_shadow_relative_error": expected_error,
        "maximum_adjoint_relative_residual": max(
            adjoint_relative.values(),
            default=math.inf,
        ),
        "all_adjoint_solves_converged": True,
    }


def _petsc_matrix_sha256(matrix: PETSc.Mat) -> str:
    comm = matrix.getComm().tompi4py()
    row_start, row_end = map(int, matrix.getOwnershipRange())
    indptr, indices, values = matrix.getValuesCSR()
    local = {
        "rank": comm.rank,
        "row_range": [row_start, row_end],
        "indptr_sha256": _array_sha256(
            indptr,
            namespace=f"task035e.level3-matrix.indptr.rank{comm.rank}.v1",
        ),
        "indices_sha256": _array_sha256(
            indices,
            namespace=f"task035e.level3-matrix.indices.rank{comm.rank}.v1",
        ),
        "values_sha256": _array_sha256(
            values,
            namespace=f"task035e.level3-matrix.values.rank{comm.rank}.v1",
        ),
    }
    return _json_sha256(
        {
            "size": list(map(int, matrix.getSize())),
            "rank_local": comm.allgather(local),
        }
    )


def _petsc_global_algebra(
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    current: PETSc.Vec,
    expected_shadow: PETSc.Vec,
    gradients: Mapping[str, PETSc.Vec],
    *,
    ksp: PETSc.KSP,
) -> dict[str, Any]:
    comm = matrix.getComm().tompi4py()
    size = tuple(map(int, matrix.getSize()))
    if size[0] != size[1] or any(
        int(vector.getSize()) != size[0]
        for vector in (rhs, current, expected_shadow, *gradients.values())
    ):
        raise ValueError("PETSc global shadow operator layout is inconsistent")
    operator, preconditioner = ksp.getOperators()
    if int(operator.handle) != int(matrix.handle) or int(
        preconditioner.handle
    ) != int(matrix.handle):
        raise ValueError("global shadow KSP does not factor the supplied matrix")
    expected_range = tuple(map(int, rhs.getOwnershipRange()))
    if any(
        tuple(map(int, vector.getOwnershipRange())) != expected_range
        for vector in (current, expected_shadow, *gradients.values())
    ):
        raise ValueError("PETSc global shadow vector ownership differs")

    action = rhs.duplicate()
    residual = rhs.copy()
    correction = rhs.duplicate()
    shadow = current.copy()
    true_residual = rhs.duplicate()
    difference = rhs.duplicate()
    try:
        matrix.mult(current, action)
        residual.axpy(PETSc.ScalarType(-1.0), action)
        ksp.solve(residual, correction)
        correction_reason = int(ksp.getConvergedReason())
        shadow.axpy(PETSc.ScalarType(1.0), correction)
        matrix.mult(shadow, true_residual)
        true_residual.axpy(PETSc.ScalarType(-1.0), rhs)
        true_relative = float(
            true_residual.norm(PETSc.NormType.NORM_2)
            / max(rhs.norm(PETSc.NormType.NORM_2), np.finfo(float).tiny)
        )
        expected_shadow.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), shadow)
        expected_error = float(
            difference.norm(PETSc.NormType.NORM_2)
            / max(
                expected_shadow.norm(PETSc.NormType.NORM_2),
                np.finfo(float).tiny,
            )
        )
        computed_shadow_sha = global_shadow_vector_sha256(shadow)
        expected_shadow_sha = global_shadow_vector_sha256(expected_shadow)
        signed: dict[str, float] = {}
        linear: dict[str, float] = {}
        maximum_adjoint_relative = 0.0
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
                linear[goal_id] = float(gradient.dot(correction).real)
            finally:
                adjoint_action.destroy()
                adjoint.destroy()
                conjugated.destroy()
        return {
            "backend": "petsc_distributed_global_shadow",
            "mpi_size": comm.size,
            "matrix_sha256": _petsc_matrix_sha256(matrix),
            "rhs_sha256": global_shadow_vector_sha256(rhs),
            "current_sha256": global_shadow_vector_sha256(current),
            "shadow_sha256": expected_shadow_sha,
            "computed_shadow_sha256": computed_shadow_sha,
            "signed": signed,
            "linear": linear,
            "true_relative_residual": true_relative,
            "expected_shadow_relative_error": expected_error,
            "maximum_adjoint_relative_residual": (
                maximum_adjoint_relative
            ),
            "all_adjoint_solves_converged": all_converged,
        }
    finally:
        difference.destroy()
        true_residual.destroy()
        shadow.destroy()
        correction.destroy()
        residual.destroy()
        action.destroy()


def _port_operator_complete(port: Mapping[str, Any] | None) -> bool:
    if not isinstance(port, Mapping):
        return False
    checks = port.get("checks")
    return bool(
        port.get("schema_version")
        == "task035d.variable-p-trace-only-port-operator.v1"
        and port.get("pass") is True
        and isinstance(checks, Mapping)
        and checks
        and all(value is True for value in checks.values())
        and port.get("auxiliary_interior_columns_allocated") is False
    )


def _cell_system_gate(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
    cell_system: HLevel3ShadowCellSystem,
) -> None:
    if not isinstance(cell_system, HLevel3ShadowCellSystem):
        raise ValueError("global shadow cell system has the wrong type")
    if cell_system._destroyed:
        raise ValueError("global shadow cell system was already destroyed")
    if not _closed_payload(
        cell_system.audit,
        digest_key="cell_system_sha256",
    ):
        raise ValueError("global shadow cell-system identity drifted")
    if (
        cell_system.patch.audit["patch_sha256"]
        != patch.audit["patch_sha256"]
        or cell_system.constraints.audit["constraint_evidence_sha256"]
        != constraints.audit["constraint_evidence_sha256"]
        or cell_system.reduction_authority.audit.get("pass") is not True
        or cell_system.system.build_audit.get(
            "compiled_p6_tensor_builder"
        )
        is not True
        or cell_system.system.build_audit.get(
            "compiled_trace_constraint_binding_complete"
        )
        is not True
    ):
        raise ValueError("global shadow cell-system structure drifted")


def evaluate_level3_global_shadow_orbit(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
    *,
    shadow_matrix: np.ndarray | PETSc.Mat,
    shadow_rhs: np.ndarray | PETSc.Vec,
    current_in_shadow: np.ndarray | PETSc.Vec,
    expected_shadow_solution: np.ndarray | PETSc.Vec,
    goal_gradients: Mapping[str, np.ndarray | PETSc.Vec],
    endpoint_receipt: HLevel3EndpointReceipt,
    ksp: PETSc.KSP | None = None,
    cell_system: HLevel3ShadowCellSystem | None = None,
    port_operator_audit: Mapping[str, Any] | None = None,
) -> HLevel3GlobalOrbitEvidence:
    """Solve the global correction and all 59 adjoints for one orbit."""

    _constraint_gate(patch, constraints)
    if tuple(goal_gradients) != FORMAL_GOAL_IDS:
        raise ValueError("global shadow gradients must use formal goal order")
    petsc_backend = isinstance(shadow_matrix, PETSc.Mat)
    if petsc_backend:
        if (
            not isinstance(shadow_rhs, PETSc.Vec)
            or not isinstance(current_in_shadow, PETSc.Vec)
            or not isinstance(expected_shadow_solution, PETSc.Vec)
            or ksp is None
            or any(
                not isinstance(value, PETSc.Vec)
                for value in goal_gradients.values()
            )
        ):
            raise ValueError("PETSc global shadow inputs are incomplete")
        algebra = _petsc_global_algebra(
            shadow_matrix,
            shadow_rhs,
            current_in_shadow,
            expected_shadow_solution,
            goal_gradients,
            ksp=ksp,
        )
    else:
        if (
            isinstance(shadow_rhs, PETSc.Vec)
            or isinstance(current_in_shadow, PETSc.Vec)
            or isinstance(expected_shadow_solution, PETSc.Vec)
            or any(
                isinstance(value, PETSc.Vec)
                for value in goal_gradients.values()
            )
        ):
            raise ValueError("dense and PETSc global shadow inputs are mixed")
        algebra = _dense_global_algebra(
            np.asarray(shadow_matrix),
            np.asarray(shadow_rhs),
            np.asarray(current_in_shadow),
            np.asarray(expected_shadow_solution),
            goal_gradients,
        )
    _endpoint_gate(
        patch,
        endpoint_receipt,
        shadow_solution_sha256=algebra["shadow_sha256"],
    )

    current_values = endpoint_receipt.current_goals.by_id
    shadow_values = endpoint_receipt.shadow_goals.by_id
    goal_rows: list[HLevel3GlobalGoalEvidence] = []
    verified_count = 0
    inside_count = 0
    for goal_id in FORMAL_GOAL_IDS:
        predicted = float(algebra["signed"][goal_id])
        linear = float(algebra["linear"][goal_id])
        actual = float(shadow_values[goal_id] - current_values[goal_id])
        tolerance = blind_tolerance(
            goal_id,
            current_values,
            shadow_values,
        )
        safe_zero = (
            abs(predicted) <= tolerance
            and abs(actual) <= tolerance
        )
        sign_consistent = safe_zero or predicted * actual > 0.0
        ratio = (
            None
            if abs(actual) <= np.finfo(float).tiny
            else abs(predicted / actual)
        )
        within_factor_two = safe_zero or bool(
            ratio is not None and 0.5 <= ratio <= 2.0
        )
        verified = sign_consistent and within_factor_two
        normalized_actual = abs(actual) / tolerance
        inside = normalized_actual <= _FREEZE_NORMALIZED_LIMIT
        verified_count += verified
        inside_count += inside
        goal_rows.append(
            HLevel3GlobalGoalEvidence(
                goal_id=goal_id,
                signed_dwr_delta=predicted,
                linearized_endpoint_delta=linear,
                actual_endpoint_delta=actual,
                blind_tolerance=tolerance,
                normalized_actual_delta=normalized_actual,
                sign_consistent=sign_consistent,
                within_factor_two=within_factor_two,
                verified=verified,
                inside_saturation_budget=inside,
            )
        )

    blockers: list[str] = []
    if algebra["backend"] != "petsc_distributed_global_shadow":
        blockers.append("dense_synthetic_backend_has_no_formal_credit")
    if int(algebra["mpi_size"]) != 8:
        blockers.append("global_shadow_is_not_mpi8")
    if cell_system is None:
        blockers.append("compiled_level3_shadow_cell_system_missing")
    else:
        _cell_system_gate(patch, constraints, cell_system)
        if cell_system.audit.get("compiled_p6_tensor_builder") is not True:
            blockers.append("compiled_level3_tensor_builder_not_proven")
        if petsc_backend and int(cell_system.system.matrix.handle) != int(
            shadow_matrix.handle
        ):
            blockers.append("augmented_operator_is_not_cell_system_matrix")
    if not _port_operator_complete(port_operator_audit):
        blockers.append("full_floquet_dtn_port_operator_not_proven")
    if (
        endpoint_receipt.audit.get("actual_field_postprocess") is not True
        or endpoint_receipt.audit.get("qualified_live_view") is not True
    ):
        blockers.append("independent_actual_field_endpoint_missing")
    elif petsc_backend:
        if endpoint_receipt.audit.get("live_view_matrix_handle") != int(
            shadow_matrix.handle
        ):
            blockers.append("endpoint_live_view_operator_identity_differs")
        if endpoint_receipt.audit.get(
            "live_view_port_operator_sha256"
        ) != _json_sha256(port_operator_audit):
            blockers.append("endpoint_live_view_port_identity_differs")
    if not algebra["all_adjoint_solves_converged"]:
        blockers.append("one_or_more_global_solves_did_not_converge")
    if algebra["true_relative_residual"] > _TRUE_RESIDUAL_LIMIT:
        blockers.append("global_shadow_true_residual_gate_failed")
    if (
        algebra["maximum_adjoint_relative_residual"]
        > _ADJOINT_RESIDUAL_LIMIT
    ):
        blockers.append("global_shadow_adjoint_residual_gate_failed")
    if algebra["expected_shadow_relative_error"] > _TRUE_RESIDUAL_LIMIT:
        blockers.append("observed_shadow_solution_differs_from_global_solve")
    if verified_count < _DWR_VERIFIED_GOAL_MINIMUM:
        blockers.append("global_shadow_dwr_effectivity_below_54_of_59")
    formally_complete = not blockers
    audit_payload: dict[str, Any] = {
        "schema_version": GLOBAL_ORBIT_EVIDENCE_SCHEMA,
        "status": (
            "level3_global_orbit_measured_component_complete"
            if formally_complete
            else "level3_global_orbit_component_formal_unknown"
        ),
        "component_algebra_pass": (
            algebra["all_adjoint_solves_converged"]
            and algebra["true_relative_residual"]
            <= _TRUE_RESIDUAL_LIMIT
            and algebra["maximum_adjoint_relative_residual"]
            <= _ADJOINT_RESIDUAL_LIMIT
            and algebra["expected_shadow_relative_error"]
            <= _TRUE_RESIDUAL_LIMIT
        ),
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "measured_fail": False,
        "freezing_credit": False,
        "controller_consumption_eligible": formally_complete,
        "formal_orbit_evidence_complete": formally_complete,
        "state_sha256": patch.audit["state_sha256"],
        "catalog_sha256": patch.audit["catalog_sha256"],
        "patch_sha256": patch.audit["patch_sha256"],
        "orbit_id": patch.orbit.orbit_id,
        "orbit_sha256": patch.orbit.orbit_sha256,
        "constraint_evidence_sha256": constraints.audit[
            "constraint_evidence_sha256"
        ],
        "cell_system_sha256": (
            None
            if cell_system is None
            else cell_system.audit["cell_system_sha256"]
        ),
        "endpoint_receipt_sha256": endpoint_receipt.audit[
            "endpoint_receipt_sha256"
        ],
        "backend": algebra["backend"],
        "mpi_size": int(algebra["mpi_size"]),
        "matrix_sha256": algebra["matrix_sha256"],
        "rhs_sha256": algebra["rhs_sha256"],
        "current_in_shadow_sha256": algebra["current_sha256"],
        "shadow_solution_sha256": algebra["shadow_sha256"],
        "computed_shadow_solution_sha256": algebra[
            "computed_shadow_sha256"
        ],
        "true_relative_residual": algebra["true_relative_residual"],
        "true_residual_limit": _TRUE_RESIDUAL_LIMIT,
        "expected_shadow_relative_error": algebra[
            "expected_shadow_relative_error"
        ],
        "maximum_adjoint_relative_residual": algebra[
            "maximum_adjoint_relative_residual"
        ],
        "adjoint_residual_limit": _ADJOINT_RESIDUAL_LIMIT,
        "formal_goal_count": len(goal_rows),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "dwr_verified_goal_count": verified_count,
        "dwr_verified_goal_minimum": _DWR_VERIFIED_GOAL_MINIMUM,
        "inside_saturation_budget_goal_count": inside_count,
        "saturation_normalized_limit": _FREEZE_NORMALIZED_LIMIT,
        "normalized_max": max(
            (row.normalized_actual_delta for row in goal_rows),
            default=0.0,
        ),
        "all_goals_inside_saturation_budget": (
            inside_count == len(FORMAL_GOAL_IDS)
        ),
        "goal_rows": [
            {
                "goal_id": row.goal_id,
                "signed_dwr_delta": row.signed_dwr_delta,
                "linearized_endpoint_delta": row.linearized_endpoint_delta,
                "actual_endpoint_delta": row.actual_endpoint_delta,
                "blind_tolerance": row.blind_tolerance,
                "normalized_actual_delta": row.normalized_actual_delta,
                "sign_consistent": row.sign_consistent,
                "within_factor_two": row.within_factor_two,
                "verified": row.verified,
                "inside_saturation_budget": (
                    row.inside_saturation_budget
                ),
            }
            for row in goal_rows
        ],
        "formal_blockers": blockers,
        "global_correction_complete": True,
        "actual_59_goal_adjoint_complete": True,
        "actual_endpoint_consumed": True,
        "hanging_floquet_constraint_identity_bound": True,
        "inactive_shadow_rows_in_production": 0,
        "production_plan_mutated": False,
        "production_level_three_selectable": False,
        "production_level_three_rows_numbered": False,
    }
    audit_payload["orbit_evidence_sha256"] = _json_sha256(audit_payload)
    return HLevel3GlobalOrbitEvidence(
        goals=tuple(goal_rows),
        audit=MappingProxyType(audit_payload),
    )


@dataclass(frozen=True, slots=True)
class HLevel3SaturationCoverage:
    """All-orbit measured h-saturation closure."""

    audit: Mapping[str, Any]


def close_level3_h_saturation_coverage(
    state: HPTransitionState,
    catalog: HLevel3SaturationCatalog,
    orbit_evidence: Sequence[HLevel3GlobalOrbitEvidence],
) -> HLevel3SaturationCoverage:
    """Classify h saturation only after exact coverage of every orbit."""

    expected = build_level3_h_saturation_catalog(state)
    if (
        catalog.periodic_orbits != expected.periodic_orbits
        or dict(catalog.audit) != dict(expected.audit)
    ):
        raise ValueError("h-saturation coverage received a drifted catalog")
    evidence_by_id: dict[str, HLevel3GlobalOrbitEvidence] = {}
    for evidence in orbit_evidence:
        if not isinstance(evidence, HLevel3GlobalOrbitEvidence):
            raise ValueError("h-saturation coverage contains wrong evidence")
        if not _closed_payload(
            evidence.audit,
            digest_key="orbit_evidence_sha256",
        ):
            raise ValueError("one global orbit evidence identity drifted")
        orbit_id = str(evidence.audit["orbit_id"])
        if orbit_id in evidence_by_id:
            raise ValueError("h-saturation coverage duplicates one orbit")
        evidence_by_id[orbit_id] = evidence
    expected_by_id = {
        orbit.orbit_id: orbit for orbit in catalog.periodic_orbits
    }
    extras = sorted(set(evidence_by_id) - set(expected_by_id))
    if extras:
        raise ValueError(f"h-saturation coverage has unknown orbits: {extras}")
    for orbit_id, evidence in evidence_by_id.items():
        orbit = expected_by_id[orbit_id]
        if (
            evidence.audit.get("state_sha256") != state.state_sha256
            or evidence.audit.get("catalog_sha256")
            != catalog.audit["catalog_sha256"]
            or evidence.audit.get("orbit_sha256") != orbit.orbit_sha256
        ):
            raise ValueError("one global orbit evidence binds another state")

    missing = sorted(set(expected_by_id) - set(evidence_by_id))
    level_two_target_ids = tuple(
        sorted(
            canonical_hp_cell_target_id(key)
            for key in catalog.level_two_leaf_keys
        )
    )
    expected_orbit_ids = tuple(sorted(expected_by_id))
    qualified_orbit_ids = tuple(
        sorted(
            orbit_id
            for orbit_id, evidence in evidence_by_id.items()
            if evidence.audit.get("formal_orbit_evidence_complete") is True
        )
    )
    covered_target_ids = tuple(
        sorted(
            {
                canonical_hp_cell_target_id(key)
                for orbit_id in qualified_orbit_ids
                for key in expected_by_id[orbit_id].leaf_keys
            }
        )
    )
    fully_qualified = bool(
        not missing
        and all(
            evidence.audit.get("formal_orbit_evidence_complete") is True
            for evidence in evidence_by_id.values()
        )
    )
    normalized_max = max(
        (
            row.normalized_actual_delta
            for evidence in evidence_by_id.values()
            for row in evidence.goals
        ),
        default=0.0,
    )
    failing_rows = [
        {
            "orbit_id": orbit_id,
            "goal_id": row.goal_id,
            "actual_endpoint_delta": row.actual_endpoint_delta,
            "blind_tolerance": row.blind_tolerance,
            "normalized_actual_delta": row.normalized_actual_delta,
        }
        for orbit_id, evidence in sorted(evidence_by_id.items())
        for row in evidence.goals
        if not row.inside_saturation_budget
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
    audit_payload: dict[str, Any] = {
        "schema_version": GLOBAL_COVERAGE_SCHEMA,
        "status": (
            "level3_h_saturation_measured_pass"
            if measured_pass
            else "level3_h_saturation_measured_fail"
            if measured_fail
            else "level3_h_saturation_formal_unknown"
        ),
        "formal_h_saturation_status": status,
        "measured_pass": measured_pass,
        "measured_fail": measured_fail,
        "freezing_credit": False,
        "controller_consumption_eligible": fully_qualified,
        "state_sha256": state.state_sha256,
        "catalog_sha256": catalog.audit["catalog_sha256"],
        "orbit_catalog_sha256": catalog.audit["orbit_catalog_sha256"],
        "level_two_target_ids": list(level_two_target_ids),
        "level_two_target_ids_sha256": _json_sha256(
            {"canonical_target_ids": list(level_two_target_ids)}
        ),
        "expected_orbit_ids": list(expected_orbit_ids),
        "expected_orbit_ids_sha256": _json_sha256(
            {"canonical_orbit_ids": list(expected_orbit_ids)}
        ),
        "covered_target_ids": list(covered_target_ids),
        "covered_target_ids_sha256": _json_sha256(
            {"canonical_target_ids": list(covered_target_ids)}
        ),
        "covered_orbit_ids": list(qualified_orbit_ids),
        "covered_orbit_ids_sha256": _json_sha256(
            {"canonical_orbit_ids": list(qualified_orbit_ids)}
        ),
        "expected_orbit_count": len(expected_by_id),
        "observed_orbit_count": len(evidence_by_id),
        "missing_orbit_ids": missing,
        "all_level_two_orbits_covered": not missing,
        "all_orbit_evidence_formally_complete": (
            fully_qualified and not missing
        ),
        "saturation_normalized_limit": _FREEZE_NORMALIZED_LIMIT,
        "normalized_max": normalized_max,
        "orbit_evidence_sha256s": {
            orbit_id: evidence.audit["orbit_evidence_sha256"]
            for orbit_id, evidence in sorted(evidence_by_id.items())
        },
        "failing_goal_count": len(failing_rows),
        "failing_rows": failing_rows,
        "production_plan_mutated": False,
        "production_level_three_selectable": False,
        "production_level_three_rows_numbered": False,
        "classification_note": (
            "measured pass/fail is reachable only with MPI8 compiled tensor, "
            "hanging/Floquet/DtN, 59-adjoint, independent endpoint evidence "
            "for every level-two periodic orbit"
        ),
    }
    audit_payload["coverage_sha256"] = _json_sha256(audit_payload)
    return HLevel3SaturationCoverage(
        audit=MappingProxyType(audit_payload)
    )


__all__ = [
    "ENDPOINT_RECEIPT_SCHEMA",
    "GLOBAL_CELL_SYSTEM_SCHEMA",
    "GLOBAL_CAPABILITY_SCHEMA",
    "GLOBAL_COVERAGE_SCHEMA",
    "GLOBAL_ORBIT_EVIDENCE_SCHEMA",
    "HLevel3EndpointReceipt",
    "HLevel3GlobalGoalEvidence",
    "HLevel3GlobalOrbitEvidence",
    "HLevel3SaturationCoverage",
    "HLevel3ShadowCellSystem",
    "build_level3_endpoint_receipt",
    "build_level3_endpoint_receipt_from_live_view",
    "build_level3_shadow_cell_system_from_compiled_form",
    "close_level3_h_saturation_coverage",
    "evaluate_level3_global_shadow_orbit",
    "global_shadow_vector_sha256",
    "level3_shadow_backend_capability_report",
]
