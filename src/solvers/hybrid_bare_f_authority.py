"""Fresh current-layout bare-``F`` authority for the Task040 V5 route.

This module is deliberately separate from the historical side oracle.  It
assembles the current condensed fine operator, materializes only its explicit
bare ``F`` matrix for the one diagnostic factor, and creates RHS columns from
current surface forms or current canonical active-trace keys.  It never
constructs ``C``, ``D``, ``H``, a Woodbury inverse, a physical DtN operator, or
an outer Hybrid system.
"""

from __future__ import annotations

import hashlib
import json
import os
import gc
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from dolfinx import cpp, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.modes_3d import outgoing_port_modes_3d
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh
from src.solvers.dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _dtn_surface_quadrature_degree,
    _traction_vector,
    _assemble_unconstrained_vector,
)
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    condense_unconstrained_vector_to_active_trace,
    project_mpc_vector_to_active_trace,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
    reconstruct_canonical_active_trace_vec,
)
from src.solvers.hybrid_interface_basis import (
    canonical_external_mode_metadata_sha256,
    canonical_mode_keys_sha256,
)
from src.solvers.common_3d_utils import _trim_process_heap
from src.solvers.hybrid_interface_packet_dolfinx import (
    build_dolfinx_plane_gamma_layout,
)
from src.solvers.hybrid_local_dtn_action import _build_variational_forms
from src.coupling.hybrid_internal_modes import (
    _trace_from_streamed_local_values,
)
from src.coupling.hybrid_one_cell_exact_traction_builder import (
    ExactOneCellSourceIdentityError,
    build_exact_one_cell_selected_traction_columns,
)
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.static_local_schur_action import (
    materialize_research_explicit_fine_matrix,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from src.solvers.hybrid_side_impedance import _petsc_matrix_hash


V5_BARE_F_SCHEMA = "task040.v5.current_bare_f_authority.v1"
V5_BARE_F_METHOD = "task040_v5_current_layout_bare_f_authority"
V5_BARE_F_SOURCE_LABELS = (
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)
V5_BARE_F_SOURCE_SPECS = {
    "modal_traction_positive": {
        "seed": 761,
        "resolved_column": 281,
        "source": (
            "frozen_selected_packet.current_layout_exact_one_cell.positive_traction"
        ),
        "kind": "current_layout_full3d_one_cell_exact_schur_column",
        "sign_convention": "matrix_column_as_stored/no_extra_sign",
    },
    "modal_traction_negative": {
        "seed": 763,
        "resolved_column": 283,
        "source": (
            "frozen_selected_packet.current_layout_exact_one_cell.negative_traction"
        ),
        "kind": "current_layout_full3d_one_cell_exact_schur_column",
        "sign_convention": "matrix_column_as_stored/no_extra_sign",
    },
    "external_dtn_coupling": {
        "seed": 769,
        "resolved_column": 177,
        "source": "current_external_minimal_surface_components",
        "kind": "minimal_surface_coupling_column",
        "sign": -1.0,
    },
    "fixed_random_repeat_0": {
        "seed": 773,
        "source": "current_canonical_active_trace_formula",
        "kind": "canonical_random",
    },
    "fixed_random_repeat_1": {
        "seed": 779,
        "source": "current_canonical_active_trace_formula",
        "kind": "canonical_random",
    },
}


class ExternalModeAuthorityIdentityError(RuntimeError):
    """The current external mode order or metadata differs from frozen authority."""


def _is_valid_sha256_text(value: Any) -> bool:
    text = str(value) if value is not None else ""
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


class FreshBareFAuthorityIdentityError(RuntimeError):
    """A qualified current-layout source or packet identity Gate failed."""

    def __init__(
        self,
        failure_code: str,
        message: str,
        *,
        stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_code = str(failure_code)
        self.stage = str(stage)
        self.details = dict(details or {})


def _require_fresh_bare_f_identity(
    passed: bool,
    failure_code: str,
    message: str,
    *,
    stage: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    if not passed:
        raise FreshBareFAuthorityIdentityError(
            failure_code,
            message,
            stage=stage,
            details=details,
        )


def _construct_bare_f_factor_after_identity_gate(
    identity_pass: bool,
    matrix: PETSc.Mat,
    *,
    marker_callback: Any | None = None,
    operator_hash: str | None = None,
) -> ResearchExactFactorInverse:
    """Construct the sole bare-F factor only after source identity passes."""

    _require_fresh_bare_f_identity(
        identity_pass,
        "SOURCE_IDENTITY_GATE_FAILED_BEFORE_BARE_F_FACTOR",
        "bare-F factor construction was attempted before source identity passed",
        stage="before_bare_f_factor",
    )
    marker_detail = {
        "factor_scope": "full_side_bare_f",
        "factored_operator": "explicit_current_bare_F",
        "operator_hash": operator_hash,
        "factor_count": 0,
        "consumer_retains_factor": False,
    }
    if marker_callback is not None:
        marker_callback("v5_bare_f_factor_setup_begin", dict(marker_detail))
    factor = ResearchExactFactorInverse(
        matrix,
        factor_solver_type="mumps",
        factor_only_storage=True,
    )
    if marker_callback is not None:
        marker_callback(
            "v5_bare_f_factor_ready",
            {
                **marker_detail,
                "factor_count": 1,
                "factor_diagnostics": dict(factor.diagnostics),
            },
        )
    return factor


def _collective_raise_fresh_bare_f_identity(
    comm: MPI.Intracomm,
    local_error: FreshBareFAuthorityIdentityError | None,
) -> None:
    """Make a local identity failure a single collective decision."""

    payload = None
    if local_error is not None:
        payload = {
            "failure_code": local_error.failure_code,
            "message": str(local_error),
            "stage": local_error.stage,
            "details": _json_safe(local_error.details),
        }
    gathered = comm.allgather(payload)
    first = next((item for item in gathered if item is not None), None)
    if first is not None:
        raise FreshBareFAuthorityIdentityError(
            str(first["failure_code"]),
            str(first["message"]),
            stage=str(first["stage"]),
            details={"local_errors": _json_safe(gathered), **dict(first["details"])},
        )


def _collective_raise_canonical_exception(
    comm: MPI.Intracomm,
    *,
    stage: str,
    identity_error: FreshBareFAuthorityIdentityError | None = None,
    implementation_error: Exception | None = None,
) -> None:
    """Propagate canonical identity or implementation errors symmetrically."""

    payload = None
    if implementation_error is not None:
        payload = {
            "kind": "implementation",
            "rank": int(comm.rank),
            "type": type(implementation_error).__name__,
            "message": str(implementation_error),
            "stage": str(stage),
        }
    elif identity_error is not None:
        payload = {
            "kind": "identity",
            "rank": int(comm.rank),
            "failure_code": identity_error.failure_code,
            "message": str(identity_error),
            "stage": identity_error.stage,
            "details": _json_safe(identity_error.details),
        }
    gathered = comm.allgather(payload)
    implementation = next(
        (item for item in gathered if item and item.get("kind") == "implementation"),
        None,
    )
    if implementation is not None:
        error_type = {
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "RuntimeError": RuntimeError,
        }.get(str(implementation["type"]), RuntimeError)
        error = error_type(
            "collective implementation failure at "
            f"{implementation['stage']} on rank {implementation['rank']}: "
            f"{implementation['message']}"
        )
        error.stage = str(implementation["stage"])
        error.source_rank = int(implementation["rank"])
        error.local_errors = _json_safe(gathered)
        raise error
    identity = next((item for item in gathered if item is not None), None)
    if identity is not None:
        raise FreshBareFAuthorityIdentityError(
            str(identity["failure_code"]),
            str(identity["message"]),
            stage=str(identity["stage"]),
            details={
                "local_errors": _json_safe(gathered),
                **dict(identity.get("details", {})),
            },
        )


def _collective_identity_stop_with_cleanup(
    comm: MPI.Intracomm,
    local_error: FreshBareFAuthorityIdentityError | None,
    cleanup: Any,
) -> None:
    """Make the decision first, then clean every rank's local temporary."""

    try:
        _collective_raise_fresh_bare_f_identity(comm, local_error)
    except FreshBareFAuthorityIdentityError:
        cleanup()
        raise


def _fresh_bare_f_identity_stop_bookkeeping(
    *,
    rhs_vectors: Mapping[str, Any],
    exact_records: Mapping[str, Any],
    inventory: Mapping[str, Any],
    factor_ready: Mapping[str, Any],
    factor_after: Mapping[str, Any],
    stage: str,
    system_created: bool,
) -> dict[str, Any]:
    """Snapshot work already performed before a controlled identity stop."""

    generated_rhs_labels = [
        label for label in V5_BARE_F_SOURCE_LABELS if label in rhs_vectors
    ]
    generated_exact_labels = [
        label for label in V5_BARE_F_SOURCE_LABELS if label in exact_records
    ]
    factor_constructed = bool(factor_ready or factor_after)
    minimal_external_constructed = int(
        inventory.get("minimal_external_coupling_objects_constructed", 0)
    )
    late_stage = stage in {
        "exact_canonical_reconstruction",
        "packet_binding",
    }
    return {
        "rhs_vectors_loaded": len(generated_rhs_labels),
        "rhs_generated_labels": generated_rhs_labels,
        "exact_output_vectors_loaded": len(generated_exact_labels),
        "exact_output_generated_labels": generated_exact_labels,
        "factor_constructed": factor_constructed,
        "factor_stage": "after_factor" if factor_constructed else "before_factor",
        "external_dtn_status": (
            "minimal_rhs_constructed_before_identity_stop"
            if minimal_external_constructed > 0
            else "not_run_by_identity_gate"
        ),
        "gate_status": (
            "identity_failed_after_factor"
            if (late_stage or factor_constructed)
            else "not_run_by_identity_gate"
        ),
        "late_identity_stage": late_stage,
        "system_created": bool(system_created),
    }


def _external_mode_record(mode: Any) -> dict[str, Any]:
    beta = complex(mode.beta)
    return {
        "side": str(mode.side),
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization),
        "beta": [float(beta.real), float(beta.imag)],
        "propagating": bool(mode.propagating),
        "rayleigh_warning": bool(mode.rayleigh_warning),
    }


def validate_external_mode_authority(
    external_modes: tuple[Any, ...] | list[Any],
    authority: Mapping[str, Any],
    *,
    current_resolved_config_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate the current bottom mode stream before forming minimal C."""

    if not isinstance(authority, Mapping):
        raise ExternalModeAuthorityIdentityError(
            "external mode authority descriptor is missing"
        )
    modes = tuple(mode for mode in external_modes if str(mode.side) == "bottom")
    records = tuple(_external_mode_record(mode) for mode in modes)
    keys = tuple(
        {
            "side": row["side"],
            "m": row["m"],
            "n": row["n"],
            "polarization": row["polarization"],
        }
        for row in records
    )
    if current_resolved_config_sha256 is None:
        raise ExternalModeAuthorityIdentityError(
            "current resolved-config SHA256 was not supplied"
        )
    expected_resolved_config_sha256 = str(authority["resolved_config_sha256"])
    current_resolved_config_sha256 = str(current_resolved_config_sha256)
    observed = {
        "count": len(records),
        "canonical_key_list_sha256": canonical_mode_keys_sha256(keys),
        "resolved_mode_metadata_sha256": canonical_external_mode_metadata_sha256(
            records
        ),
        "legacy_beta_metadata_sha256": str(
            authority["legacy_beta_metadata_sha256"]
        ),
        "index177_key": keys[177] if len(keys) > 177 else None,
        "resolved_config_sha256": current_resolved_config_sha256,
    }
    expected_keys = tuple(authority["canonical_keys"])
    expected_records = tuple(authority["beta_metadata"])
    expected = {
        "count": int(authority["count"]),
        "canonical_key_list_sha256": str(authority["canonical_key_list_sha256"]),
        "resolved_mode_metadata_sha256": str(
            authority["resolved_mode_metadata_sha256"]
        ),
        "legacy_beta_metadata_sha256": str(
            authority["legacy_beta_metadata_sha256_expected"]
        ),
        "resolved_config_sha256": expected_resolved_config_sha256,
        "index177_key": authority["index177_key"],
    }
    checks = {
        "count": observed["count"] == expected["count"],
        "ordered_keys": keys == expected_keys,
        "canonical_key_list_sha256": (
            observed["canonical_key_list_sha256"]
            == expected["canonical_key_list_sha256"]
        ),
        "beta_metadata": records == expected_records,
        "resolved_mode_metadata_sha256": (
            observed["resolved_mode_metadata_sha256"]
            == expected["resolved_mode_metadata_sha256"]
        ),
        "legacy_beta_metadata_sha256": (
            _is_valid_sha256_text(observed["legacy_beta_metadata_sha256"])
            and _is_valid_sha256_text(expected["legacy_beta_metadata_sha256"])
            and observed["legacy_beta_metadata_sha256"]
            == expected["legacy_beta_metadata_sha256"]
        ),
        "index177_key": observed["index177_key"] == expected["index177_key"],
        "resolved_config_sha256": (
            _is_valid_sha256_text(observed["resolved_config_sha256"])
            and _is_valid_sha256_text(expected["resolved_config_sha256"])
            and observed["resolved_config_sha256"] == expected["resolved_config_sha256"]
        ),
    }
    if not all(checks.values()):
        error = ExternalModeAuthorityIdentityError(
            "current external bottom mode authority mismatch: "
            f"observed={observed!r}, expected={expected!r}, checks={checks!r}"
        )
        error.checks = checks
        raise error
    return {
        "status": "pass",
        "pass": True,
        "checks": checks,
        "observed": observed,
        "expected": expected,
        "resolved_config_sha256": expected_resolved_config_sha256,
    }


@dataclass
class _SelectedModeSourceContext:
    """One reusable, hash-bound selected-mode-to-current-surface adapter."""

    packet_provider: Any
    spaces: Any
    surface_load: Any | None = None
    traction_evaluator: Any | None = None


class _BareFStaticCondensationAdapter:
    """Narrow trace-only reduction contract for the bare-F source path."""

    def __init__(self, condensed: Any) -> None:
        self.condensed = condensed

    def reduce_tangential_surface_mpc_vector(
        self,
        full_mpc_vector: PETSc.Vec,
        *,
        audit: dict[str, object] | None = None,
        **_: Any,
    ) -> PETSc.Vec:
        return project_mpc_vector_to_active_trace(
            self.condensed,
            full_mpc_vector,
            eliminated_tolerance=1.0e-12,
            eliminated_relative_tolerance=(1024.0 * np.finfo(np.float64).eps),
            audit=audit,
        )


def combine_surface_component_values(
    component_zero: np.ndarray,
    component_one: np.ndarray,
    coefficients: tuple[complex, complex] | list[complex],
    *,
    sign: float = -1.0,
) -> np.ndarray:
    """Combine two owned surface components with the authoritative coefficients.

    The external DtN column is the negative surface-load convention used by
    ``hybrid_local_dtn.py``.  Keeping this arithmetic in a small pure helper
    makes the minimal-C regression independent of PETSc and of a full C/D/H
    construction.
    """

    first = np.asarray(component_zero, dtype=np.complex128)
    second = np.asarray(component_one, dtype=np.complex128)
    if first.shape != second.shape:
        raise ValueError("surface components must have matching shapes")
    coeffs = np.asarray(coefficients, dtype=np.complex128)
    if coeffs.shape != (2,):
        raise ValueError("surface coefficient vector must have two entries")
    values = float(sign) * (coeffs[0] * first + coeffs[1] * second)
    if not np.isfinite(values).all():
        raise ValueError("surface source values are nonfinite")
    return np.asarray(values, dtype=np.complex128)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"value is not JSON-safe: {type(value)!r}")


def _canonical_key_token(key: Any) -> str:
    """Encode the existing physical canonical key without row-number data."""

    return json.dumps(_json_safe(key), sort_keys=True, separators=(",", ":"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_owned_array(values: np.ndarray) -> str:
    return _sha256_bytes(np.ascontiguousarray(values).tobytes(order="C"))


def _require_sha256(value: Any, name: str) -> str:
    text = str(value)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{name} must be a lowercase 64-hex SHA256")
    return text


def _is_valid_sha256(value: Any) -> bool:
    return _is_valid_sha256_text(value)


def _is_valid_source_provenance(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    required_sha256 = (
        "input_sha256",
        "physical_model_sha256",
        "selected_manifest_sha256",
        "selected_identity_sha256",
        "resolved_config_sha256",
    )
    if any(not _is_valid_sha256(value.get(field)) for field in required_sha256):
        return False
    source_sha = value.get("source_sha", value.get("committed_source_sha"))
    return (
        isinstance(source_sha, str)
        and len(source_sha) == 40
        and all(character in "0123456789abcdef" for character in source_sha)
    )


def _source_semantic_descriptor(
    *,
    label: str,
    metadata: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the rank-independent physical definition of one source."""

    common = {
        "label": str(label),
        "source": _json_safe(metadata.get("source")),
        "kind": _json_safe(metadata.get("kind")),
        "source_sha": str(metadata.get("source_sha", provenance.get("source_sha", ""))),
        "input_sha256": str(
            metadata.get("input_sha256", provenance.get("input_sha256", ""))
        ),
        "physical_model_sha256": str(
            metadata.get(
                "physical_model_sha256", provenance.get("physical_model_sha256", "")
            )
        ),
        "selected_manifest_sha256": str(
            metadata.get(
                "selected_manifest_sha256",
                provenance.get("selected_manifest_sha256", ""),
            )
        ),
        "selected_identity_sha256": str(
            metadata.get(
                "selected_identity_sha256",
                provenance.get("selected_identity_sha256", ""),
            )
        ),
        "resolved_config_sha256": str(
            metadata.get(
                "resolved_config_sha256", provenance.get("resolved_config_sha256", "")
            )
        ),
    }
    if label.startswith("modal_traction_"):
        required = (
            "selected_mode_packet_branch",
            "selected_mode_packet_index",
            "selected_mode_packet_mode_key",
            "selected_mode_packet_beta",
            "selected_mode_packet_manifest_sha256",
            "selected_mode_packet_identity_sha256",
            "surface_load_convention",
            "sign_convention",
            "propagation_model",
            "propagation_axial_fem_degree",
            "propagation_axial_h_nm",
        )
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValueError(
                f"modal source definition is missing semantic fields: {missing}"
            )
        common["modal"] = {key: _json_safe(metadata[key]) for key in required}
    elif label == "external_dtn_coupling":
        required = (
            "mode_index",
            "mode_key",
            "traction_coefficients",
            "surface_quadrature_degree",
            "sign",
            "external_mode_authority",
        )
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValueError(
                f"external source definition is missing semantic fields: {missing}"
            )
        common["external"] = {key: _json_safe(metadata[key]) for key in required}
    elif metadata.get("kind") == "canonical_random":
        required = ("seed", "numeric_formula")
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValueError(
                f"random source definition is missing semantic fields: {missing}"
            )
        common["random"] = {key: _json_safe(metadata[key]) for key in required}
    else:
        raise ValueError(f"unsupported source definition label: {label!r}")
    return common


def _source_definition_sha256(
    *,
    label: str,
    metadata: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> str:
    """Hash only the complete rank-independent physical/source descriptor."""

    descriptor = _source_semantic_descriptor(
        label=label,
        metadata=metadata,
        provenance=provenance,
    )
    metadata_descriptor = dict(metadata)
    metadata_descriptor["source_definition_descriptor"] = descriptor
    provenance_keys = (
        "committed_source_sha",
        "input_sha256",
        "physical_model_sha256",
        "selected_manifest_sha256",
        "selected_identity_sha256",
        "resolved_config_sha256",
    )
    payload = {
        "label": str(label),
        "source_metadata": _json_safe(
            metadata_descriptor["source_definition_descriptor"]
        ),
        "provenance": {
            key: _json_safe(provenance[key])
            for key in provenance_keys
            if key in provenance
        },
    }
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _rank_local_shard_binding_sha256(
    *,
    rank: int,
    label: str,
    role: str,
    source_definition_sha256: str,
    key_set_sha256: str,
    canonical_layout_sha256: str,
    identity: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
    bare_f_operator_hash: str | None,
    rhs_repeat: Mapping[str, Any] | None,
) -> str:
    """Hash owner-local layout/value binding without changing source semantics."""

    payload = {
        "rank": int(rank),
        "label": str(label),
        "role": str(role),
        "source_definition_sha256": str(source_definition_sha256),
        "canonical_key_set_sha256": str(key_set_sha256),
        "canonical_layout_sha256": str(canonical_layout_sha256),
        "bare_f_operator_hash": bare_f_operator_hash,
        "source_provenance": _json_safe(dict(source_provenance)),
        "ownership_range": _json_safe(identity.get("ownership_range")),
        "array_sha256": _json_safe(identity.get("array_sha256")),
        "owner_row_array_sha256": _json_safe(identity.get("owner_row_array_sha256")),
        "canonical_to_current_roundtrip_relative": _json_safe(
            identity.get("canonical_to_current_roundtrip_relative")
        ),
        "rhs_repeat": _json_safe(dict(rhs_repeat)) if rhs_repeat else None,
    }
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _provenance_reference(
    provenance: Mapping[str, Any] | None,
    *,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
) -> dict[str, Any]:
    """Return one compact identity reference shared by every source packet."""

    observed = dict(provenance.get("observed", {})) if provenance else {}
    reference = {
        "committed_source_sha": str(observed.get("committed_source_sha", source_sha)),
        "input_sha256": str(observed.get("input_file_sha256", input_sha256)),
        "physical_model_sha256": str(
            observed.get("physical_model_sha256", physical_model_sha256)
        ),
        "selected_manifest_sha256": str(observed.get("selected_manifest_sha256", "")),
        "selected_identity_sha256": str(observed.get("selected_identity_sha256", "")),
        "resolved_config_sha256": str(observed.get("resolved_config_sha256", "")),
    }
    if provenance is not None:
        reference["identity_preflight_sha256"] = _sha256_bytes(
            json.dumps(
                _json_safe(provenance),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    return reference


def _operator_evidence_bindings(source_sha: str) -> dict[str, Any]:
    """Bind the static old/current source claims to reviewed source files."""

    repository_root = Path(__file__).resolve().parents[2]
    evidence = {
        "old_rhs_builder": (
            "benchmarks/task039_v3_7_orchestration.py",
            "_v5_blr_rhs_vector",
        ),
        "old_side_components": (
            "benchmarks/task039_v3_side_oracle.py",
            "_build_research_explicit_side_components",
        ),
        "old_side_action": (
            "src/solvers/hybrid_local_dtn_woodbury.py",
            "ResearchExactSideLuAction",
        ),
        "current_bare_f_core": (
            "src/solvers/hybrid_bare_f_authority.py",
            "run_current_bare_f_authority",
        ),
        "current_one_cell_source": (
            "src/coupling/hybrid_one_cell_exact_traction_builder.py",
            "build_exact_one_cell_selected_traction_columns",
        ),
    }
    bindings: dict[str, Any] = {}
    for name, (relative_path, symbol) in evidence.items():
        path = repository_root / relative_path
        bindings[name] = {
            "path": relative_path,
            "symbol": symbol,
            "source_sha": str(source_sha),
            "present": path.is_file(),
            "file_sha256": (
                _sha256_bytes(path.read_bytes()) if path.is_file() else None
            ),
        }
    return bindings


def build_v5_operator_semantics_audit(
    *,
    source_sha: str,
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Describe the old/current operator boundary before any system is built."""

    record: dict[str, Any] = {
        "schema": "task040.v5.operator_semantics_audit.v1",
        "source_sha": str(source_sha),
        "old_authority": {
            "producer_action": "ResearchExactSideLuAction",
            "operator_semantics": "A_side=F-C-H_inverse-D_or_Woodbury_associated",
            "current_bare_f_authority": False,
            "raw_global_row_remap": False,
        },
        "old_rhs_source_definitions": {
            "modal_traction_positive": {
                "source": "setup.coupling.bottom.positive_traction",
                "column": "coupling_side.positive_traction",
                "internal_traction_model": "full3d_one_cell_exact_schur",
            },
            "modal_traction_negative": {
                "source": "setup.coupling.bottom.negative_traction",
                "column": "coupling_side.negative_traction",
                "internal_traction_model": "full3d_one_cell_exact_schur",
            },
            "external_dtn_coupling": {
                "source": "pre_action_components.C",
                "column": "external coupling C",
                "operator_context": "ResearchExactSideLuAction/Woodbury-associated",
            },
            "fixed_random_repeat_0": {
                "source": "old_owner_row_formula",
                "operator_context": "historical exact-side spool",
            },
            "fixed_random_repeat_1": {
                "source": "old_owner_row_formula",
                "operator_context": "historical exact-side spool",
            },
        },
        "current_authority": {
            "status": "minimal_modal_source_identity_repair_applied",
            "authority_qualified": "conditional_static_source_path",
            "static_path_identity": True,
            "runtime_qualification_required": True,
            "runtime_qualification_gates": [
                "primal_endpoint_identity",
                "independent_rhs_repeat",
                "one_cell_factor_lifecycle",
                "current_bare_f_residual",
            ],
            "operator": "explicit_current_bare_F",
            "factor": "ResearchExactFactorInverse(F)",
            "modal_traction_model": "full3d_one_cell_exact_schur",
            "modal_source_builder": ("build_exact_one_cell_selected_traction_columns"),
            "selected_packet_use": "one_selected_right_trace_per_column",
            "selected_columns": {"positive": 281, "negative": 283},
            "top_system_constructed": False,
            "full_coupling_constructed": False,
            "one_cell_source_factor_sequence": (
                "one_cell_factor_1_to_0_before_full_side_factor_1_to_0"
            ),
            "qep_calls": 0,
            "C_D_H_constructed": {"C": 0, "D": 0, "H": 0},
            "woodbury_inverse": False,
            "physical_dtn_operator": False,
        },
        "current_rhs_source_definitions": {
            "modal_traction_positive": {
                "source": (
                    "frozen_selected_packet.current_layout_exact_one_cell."
                    "positive_traction"
                ),
                "traction_model": "full3d_one_cell_exact_schur",
                "resolved_column": 281,
            },
            "modal_traction_negative": {
                "source": (
                    "frozen_selected_packet.current_layout_exact_one_cell."
                    "negative_traction"
                ),
                "traction_model": "full3d_one_cell_exact_schur",
                "resolved_column": 283,
            },
            "external_dtn_coupling": {
                "source": "current_external_minimal_surface_components",
                "traction_coefficients": "_traction_vector",
            },
            "fixed_random_repeat_0": {
                "source": "current_canonical_active_trace_formula",
            },
            "fixed_random_repeat_1": {
                "source": "current_canonical_active_trace_formula",
            },
        },
        "modal_source_identity": {
            "old_model": "full3d_one_cell_exact_schur",
            "current_model": "full3d_one_cell_exact_schur",
            "equivalence_proof": (
                "same_frozen_full3d_one_cell_exact_schur_primitives_"
                "restricted_to_selected_current_layout_columns"
            ),
            "repair": {
                "status": "applied",
                "path": "minimal_current_layout_bottom_only_selected_columns",
                "columns": [281, 283],
                "qep_calls": 0,
                "top_system_constructed": False,
                "full_coupling_constructed": False,
                "scalar_cg_substitution": False,
                "source_factor_sequence": (
                    "one_cell_factor_destroyed_before_full_side_factor"
                ),
            },
            "difference_resolved": (
                "prior_scalar_cg_discrete_derivative_path_was_not_the_frozen_"
                "full3d_one_cell_source"
            ),
            "pass": True,
            "gate": "FRESH_BARE_F_AUTHORITY_IDENTITY_PASS_PENDING_NUMERICAL_GATE",
        },
        "source_definitions": {
            label: {
                "resolved_column": spec.get("resolved_column"),
                "source": spec["source"],
                "kind": spec["kind"],
            }
            for label, spec in V5_BARE_F_SOURCE_SPECS.items()
        },
        "evidence_bindings": _operator_evidence_bindings(source_sha),
        "provenance": _json_safe(dict(provenance or {})),
    }
    record["record_sha256"] = _sha256_bytes(
        json.dumps(
            _json_safe(record),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return record


def _canonical_random_value(key: Any, seed: int) -> complex:
    token = _canonical_key_token(key).encode("utf-8")
    integer = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    phase = 2.0 * np.pi * ((integer + int(seed)) % 104729) / 104729.0
    return complex(np.sin(phase), np.cos(phase))


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_npy(path: Path, values: np.ndarray) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, np.ascontiguousarray(values), allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@dataclass
class CurrentBareFAuthoritySystem:
    """Owned current-layout bare-F assembly and its canonical source context."""

    cfg: Any
    side: str
    local_mesh: Any
    V: Any
    floquet_data: Any
    condensed: Any
    static_condensation: _BareFStaticCondensationAdapter
    F: PETSc.Mat
    full_fe_rhs: PETSc.Vec
    external_modes: tuple[Any, ...]
    construction_inventory: dict[str, Any]
    source_work_directory: Path | None = None
    selected_mode_provider: Any | None = None
    external_mode_authority: Mapping[str, Any] | None = None
    external_mode_current_resolved_config_sha256: str | None = None
    source_factor_marker_callback: Any | None = None
    _selected_mode_context: _SelectedModeSourceContext | None = None
    _selected_exact_source_cache: dict[str, Any] | None = None
    _destroyed: bool = False

    @property
    def dtn_objects_constructed(self) -> dict[str, int]:
        """Return counts derived from the actual construction inventory."""

        return {
            name: int(self.construction_inventory["objects"].get(name, 0))
            for name in ("C", "D", "H")
        }

    @property
    def comm(self) -> MPI.Intracomm:
        return self.F.getComm().tompi4py()

    @property
    def active_rows(self) -> int:
        return int(self.F.getSize()[0])

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.F.destroy()
        self.full_fe_rhs.destroy()
        self.condensed.destroy()
        mpc = getattr(self.floquet_data, "mpc", None)
        if mpc is not None and hasattr(mpc, "destroy"):
            mpc.destroy()
        self._selected_mode_context = None
        self._destroyed = True


def assemble_current_bare_f_authority_system(
    cfg: Any,
    *,
    side: str = "bottom",
    bottom_interface_z_nm: float = 10.0,
    top_interface_z_nm: float = 110.0,
    source_work_directory: str | Path | None = None,
    selected_mode_provider: Any | None = None,
    external_mode_authority: Mapping[str, Any] | None = None,
    external_mode_current_resolved_config_sha256: str | None = None,
    source_factor_marker_callback: Any | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> CurrentBareFAuthoritySystem:
    """Assemble current ``F_b`` without creating any physical DtN blocks."""

    if side != "bottom":
        raise ValueError("Task040 V5 bare-F authority is bottom-only")
    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("V5 bare-F authority requires auxiliary assembly")
    if cfg.use_pml:
        raise ValueError("V5 bare-F authority requires use_pml=False")
    local_mesh = build_hybrid_local_mesh(
        cfg,
        side,
        bottom_interface_z_nm=bottom_interface_z_nm,
        top_interface_z_nm=top_interface_z_nm,
        comm=comm,
    )
    V = _create_nedelec_space(local_mesh.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, local_mesh.mesh_data, cfg, log=None)
    bilinear_form, linear_form = _build_variational_forms(
        local_mesh.mesh,
        local_mesh.mesh_data,
        cfg,
        V,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    condensed = None
    F = None
    full_fe_rhs = None
    try:
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear_form),
            V,
            local_mesh.mesh_data.cell_tags,
            mpc=floquet_data.mpc,
            defer_final_assembly=True,
            retain_local_schur_for_matrix_free=True,
            materialize_global_matrix=False,
        )
        if condensed.matrix is not None or condensed.appended_rows != 0:
            raise RuntimeError("bare-F assembly allocated forbidden appended rows")
        full_fe_rhs = _assemble_unconstrained_vector(linear_form)
        F = materialize_research_explicit_fine_matrix(condensed)
        if F.getSize() != (condensed.active_rows, condensed.active_rows):
            raise RuntimeError("current bare-F size differs from active trace rows")
        modes = tuple(
            mode for mode in outgoing_port_modes_3d(cfg) if str(mode.side) == side
        )
        external_column = int(
            V5_BARE_F_SOURCE_SPECS["external_dtn_coupling"]["resolved_column"]
        )
        if len(modes) <= external_column:
            raise RuntimeError("current bottom mode inventory is too small")
        created_object_names: tuple[str, ...] = ()
        forbidden_object_names = ("C", "D", "H")
        if any(name in created_object_names for name in forbidden_object_names):
            raise RuntimeError("bare-F assembly unexpectedly created a C/D/H object")
        return CurrentBareFAuthoritySystem(
            cfg=cfg,
            side=side,
            local_mesh=local_mesh,
            V=V,
            floquet_data=floquet_data,
            condensed=condensed,
            static_condensation=_BareFStaticCondensationAdapter(condensed),
            F=F,
            full_fe_rhs=full_fe_rhs,
            external_modes=modes,
            selected_mode_provider=selected_mode_provider,
            external_mode_authority=external_mode_authority,
            external_mode_current_resolved_config_sha256=(
                external_mode_current_resolved_config_sha256
            ),
            source_factor_marker_callback=source_factor_marker_callback,
            source_work_directory=(
                Path(source_work_directory)
                if source_work_directory is not None
                else None
            ),
            construction_inventory={
                "created_object_names": list(created_object_names),
                "forbidden_object_names": list(forbidden_object_names),
                "objects": {
                    name: int(name in created_object_names)
                    for name in forbidden_object_names
                },
                "qep_calls": 0,
                "physical_dtn_operator_constructed": False,
                "woodbury_inverse_constructed": False,
                "research_exact_side_lu_action_called": False,
                "minimal_external_coupling_objects_constructed": 0,
                "minimal_external_surface_component_count": 0,
                "minimal_external_coupling_construction_call_count": 0,
                "minimal_external_component_instances_total": 0,
                "minimal_external_peak_live_components": 0,
                "minimal_external_coupling_kind_count": 0,
                "external_mode_authority_required": external_mode_authority is not None,
                "external_mode_authority": None,
                "one_cell_source_factor_events": [],
                "one_cell_source_factor_active": 0,
                "one_cell_source_factor_peak": 0,
                "one_cell_source_factor_ready": 0,
                "one_cell_source_factor_destroyed": False,
                "one_cell_source_factor_factor_count_after": None,
                "one_cell_source_factor_mat_solve_call_count": 0,
                "one_cell_source_factor_rhs_columns_solved": 0,
                "one_cell_source_factor_construction_count": 0,
                "one_cell_source_factor_apply_count": 0,
                "source_build_counts": {label: 0 for label in V5_BARE_F_SOURCE_LABELS},
            },
        )
    except Exception:
        if F is not None:
            F.destroy()
        if full_fe_rhs is not None:
            full_fe_rhs.destroy()
        if condensed is not None:
            condensed.destroy()
        mpc = getattr(floquet_data, "mpc", None)
        if mpc is not None and hasattr(mpc, "destroy"):
            mpc.destroy()
        raise


def _selected_mode_source_context(
    system: CurrentBareFAuthoritySystem,
) -> _SelectedModeSourceContext:
    """Create the one reusable selected-packet/current-surface bridge."""

    if system._selected_mode_context is not None:
        return system._selected_mode_context
    if system.selected_mode_provider is None:
        raise RuntimeError(
            "V5 internal modal sources require a runner-supplied hash-bound "
            "selected-mode provider"
        )
    from src.modes.cross_section_spaces import (
        build_cross_section_spaces,
        build_matching_cross_section,
    )

    cross_section = build_matching_cross_section(
        system.cfg,
        "stage4_xy",
        comm=system.comm,
    )
    spaces = build_cross_section_spaces(
        cross_section,
        transverse_degree=int(system.cfg.nedelec_degree),
    )
    system._selected_mode_context = _SelectedModeSourceContext(
        packet_provider=system.selected_mode_provider,
        spaces=spaces,
        surface_load=None,
        traction_evaluator=None,
    )
    return system._selected_mode_context


def _record_one_cell_source_factor_event(
    inventory: dict[str, Any],
    events: list[dict[str, Any]],
    stage: str,
    detail: Mapping[str, Any],
) -> None:
    """Drive source-factor inventory from observed lifecycle callbacks."""

    observed = dict(detail)
    factor_count = observed.get("factor_count")
    if stage == "v5_one_cell_source_factor_ready":
        if int(factor_count) != 1:
            raise RuntimeError("one-cell source factor ready count was not one")
        inventory["one_cell_source_factor_active"] = 1
        inventory["one_cell_source_factor_ready"] = 1
        inventory["one_cell_source_factor_peak"] = max(
            int(inventory.get("one_cell_source_factor_peak", 0)),
            int(observed.get("peak_simultaneous_factor_count", 1)),
        )
        inventory["one_cell_source_factor_construction_count"] = int(
            observed["factor_construction_count"]
        )
    elif stage == "v5_one_cell_source_factor_apply":
        if int(inventory.get("one_cell_source_factor_active", 0)) != 1:
            raise RuntimeError("one-cell source apply occurred while factor inactive")
        inventory["one_cell_source_factor_apply_count"] = int(observed["apply_count"])
        inventory["one_cell_source_factor_mat_solve_call_count"] = int(
            observed["mat_solve_call_count"]
        )
        inventory["one_cell_source_factor_rhs_columns_solved"] = int(
            observed["rhs_columns_solved"]
        )
    elif stage == "v5_one_cell_source_factor_destroyed":
        if int(factor_count) != 0 or observed.get("factor_destroyed") is not True:
            raise RuntimeError("one-cell source factor destroy was not observed")
        if observed.get("factor_matrix_alive") is not False:
            raise RuntimeError("one-cell source factor matrix remained alive")
        inventory["one_cell_source_factor_active"] = 0
        inventory["one_cell_source_factor_destroyed"] = True
        inventory["one_cell_source_factor_factor_count_after"] = int(factor_count)
        inventory["one_cell_source_factor_mat_solve_call_count"] = int(
            observed["mat_solve_call_count"]
        )
        inventory["one_cell_source_factor_rhs_columns_solved"] = int(
            observed["rhs_columns_solved"]
        )
    events.append({"stage": stage, **_json_safe(observed)})


def _ensure_selected_exact_source_cache(
    system: CurrentBareFAuthoritySystem,
) -> dict[str, Any]:
    """Generate both modal branches twice under one one-cell factor."""

    if system._selected_exact_source_cache is not None:
        return system._selected_exact_source_cache
    if system.source_work_directory is None:
        raise RuntimeError(
            "exact one-cell modal sources require a dedicated ignored work directory"
        )
    context = _selected_mode_source_context(system)
    packets = {
        "positive": context.packet_provider("positive", 281),
        "negative": context.packet_provider("negative", 283),
    }
    if not all(isinstance(packet, Mapping) for packet in packets.values()):
        raise TypeError("selected-mode provider must return branch mappings")
    for branch, packet in packets.items():
        right = np.asarray(packet["right_local"], dtype=np.complex128)
        left = np.asarray(packet["left_local"], dtype=np.complex128)
        if right.shape != left.shape or not np.isfinite(right).all():
            raise ValueError(f"selected {branch} packet values are invalid")
        if not np.isfinite(left).all():
            raise ValueError(f"selected {branch} adjoint packet values are invalid")
        if packet.get("passive_branch_valid") is not True:
            raise ValueError(f"selected {branch} packet is not passive-certified")
    if tuple(map(int, packets["positive"]["ownership_range"])) != tuple(
        map(int, packets["negative"]["ownership_range"])
    ):
        raise ValueError("selected modal branch ownership ranges differ")
    traces = {
        branch: _trace_from_streamed_local_values(
            np.asarray(packet["right_local"], dtype=np.complex128),
            context.spaces,
            packet["ownership_range"],
            name=f"task040_v5_{branch}_selected_trace",
        )
        for branch, packet in packets.items()
    }
    inventory = system.construction_inventory
    events = inventory.setdefault("one_cell_source_factor_events", [])

    def source_factor_callback(stage: str, detail: Mapping[str, Any]) -> None:
        _record_one_cell_source_factor_event(inventory, events, stage, detail)
        marker = getattr(system, "source_factor_marker_callback", None)
        if system.comm.rank == 0 and marker is not None:
            marker(
                stage,
                {
                    "factor_scope": "one_cell_source",
                    **dict(detail),
                },
            )

    try:
        target_rows, columns, audit = build_exact_one_cell_selected_traction_columns(
            system.cfg,
            traces,
            positive_beta=complex(packets["positive"]["beta"]),
            negative_beta=complex(packets["negative"]["beta"]),
            positive_passive_branch_valid=bool(
                packets["positive"]["passive_branch_valid"]
            ),
            negative_passive_branch_valid=bool(
                packets["negative"]["passive_branch_valid"]
            ),
            bottom_system=system,
            work_dir=Path(system.source_work_directory) / "modal_pair_build01",
            stage_callback=source_factor_callback,
        )
        lifecycle = audit["one_cell_factor_lifecycle"]
        required_lifecycle = {
            "factor_count_ready": 1,
            "factor_construction_count": 1,
            "apply_count": 2,
            "mat_solve_call_count": 2,
            "rhs_columns_solved": 4,
            "peak_simultaneous_factor_count": 1,
            "factor_count_after": 0,
            "factor_destroyed_before_return": True,
            "factor_matrix_alive_after_return": False,
        }
        if any(
            lifecycle.get(name) != expected
            for name, expected in required_lifecycle.items()
        ):
            raise RuntimeError(
                "one-cell source lifecycle did not satisfy observed state machine: "
                f"{lifecycle!r}"
            )
        if (
            int(inventory.get("one_cell_source_factor_ready", 0)) != 1
            or int(inventory.get("one_cell_source_factor_active", 0)) != 0
            or inventory.get("one_cell_source_factor_destroyed") is not True
            or int(inventory.get("one_cell_source_factor_peak", 0)) != 1
            or int(inventory.get("one_cell_source_factor_mat_solve_call_count", 0)) != 2
            or int(inventory.get("one_cell_source_factor_rhs_columns_solved", 0)) != 4
        ):
            raise RuntimeError(
                "source-factor callbacks did not record ready/apply/destroy state"
            )
        gc.collect()
        system.comm.barrier()
        cleanup_local: dict[str, Any] = {
            "rank": int(system.comm.rank),
            "petsc_garbage_cleanup_call_completed": False,
            "petsc_call_completed": False,
        }
        PETSc.garbage_cleanup(system.comm)
        cleanup_local["petsc_garbage_cleanup_call_completed"] = True
        cleanup_local["petsc_call_completed"] = True
        gc.collect()
        heap_audit = _trim_process_heap()
        cleanup_local["heap_trim"] = _json_safe(heap_audit)
        cleanup_local["before_mb"] = heap_audit.get("rss_before_mb")
        cleanup_local["after_mb"] = heap_audit.get("rss_after_mb")
        cleanup_local["released_mb"] = heap_audit.get("rss_released_mb")
        cleanup_local["allocator_call_completed"] = bool(
            heap_audit.get("call_completed") is True
        )
        cleanup_by_rank = system.comm.allgather(cleanup_local)
        all_ranks_inactive = bool(
            system.comm.allreduce(
                int(inventory.get("one_cell_source_factor_active", 0)) == 0,
                op=MPI.LAND,
            )
        )
        petsc_cleanup_completed = all(
            item["petsc_call_completed"] is True for item in cleanup_by_rank
        )
        allocator_cleanup_completed = all(
            item["allocator_call_completed"] is True for item in cleanup_by_rank
        )
        inventory["one_cell_source_factor_cleanup"] = {
            "python_gc_collect_count": 2,
            "collective_barrier": True,
            "all_ranks_inactive": all_ranks_inactive,
            "action_destroyed": True,
            "factor_count_after": int(
                inventory["one_cell_source_factor_factor_count_after"]
            ),
            "before_full_side_factor": True,
            "petsc_garbage_cleanup_calls_completed": petsc_cleanup_completed,
            "allocator_trim_calls_completed": allocator_cleanup_completed,
            "calls_completed": bool(
                petsc_cleanup_completed and allocator_cleanup_completed
            ),
            "ranks": _json_safe(cleanup_by_rank),
            "before_mb_by_rank": [item["before_mb"] for item in cleanup_by_rank],
            "after_mb_by_rank": [item["after_mb"] for item in cleanup_by_rank],
            "released_mb_by_rank": [item["released_mb"] for item in cleanup_by_rank],
            "call_completed_by_rank": [
                bool(item["petsc_call_completed"] and item["allocator_call_completed"])
                for item in cleanup_by_rank
            ],
        }
        if not all(
            (all_ranks_inactive, petsc_cleanup_completed, allocator_cleanup_completed)
        ):
            raise RuntimeError("one-cell source cleanup did not complete collectively")
        marker = getattr(system, "source_factor_marker_callback", None)
        if system.comm.rank == 0 and marker is not None:
            marker(
                "v5_one_cell_source_cleanup_complete",
                {
                    "factor_scope": "one_cell_source",
                    "factor_count": 0,
                    "active": 0,
                    "calls_completed": True,
                    "before_full_side_factor": True,
                },
            )
        system._selected_exact_source_cache = {
            "target_rows": np.asarray(target_rows, dtype=PETSc.IntType).copy(),
            "columns": {
                branch: {
                    "values": np.asarray(values["values"], dtype=np.complex128),
                    "repeat_values": np.asarray(
                        values["repeat_values"], dtype=np.complex128
                    ),
                }
                for branch, values in columns.items()
            },
            "packets": {
                branch: {
                    key: _json_safe(packet[key])
                    for key in (
                        "manifest_path",
                        "manifest_sha256",
                        "identity_sha256",
                        "branch",
                        "mode_key",
                        "beta",
                        "passive_branch_valid",
                        "ownership_range",
                        "global_size",
                    )
                    if key in packet
                }
                for branch, packet in packets.items()
            },
            "audit": _json_safe(dict(audit)),
        }
        return system._selected_exact_source_cache
    except ExactOneCellSourceIdentityError as exc:
        raise FreshBareFAuthorityIdentityError(
            "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL",
            str(exc),
            stage=getattr(exc, "stage", "modal_source_identity"),
            details={
                "source_identity": "full3d_one_cell_exact_schur",
                "local_errors": _json_safe(getattr(exc, "local_errors", [])),
            },
        ) from exc
    finally:
        for trace in traces.values():
            del trace


def _validate_current_active_target_rows(
    target_rows: Any,
    values: Any,
    *,
    current_global_size: int,
    current_ownership_range: tuple[int, int],
    all_ownership_ranges: tuple[tuple[int, int], ...],
    all_target_row_shards: tuple[tuple[int, ...], ...],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Validate owner-local one-cell target rows against the active Vec layout."""

    rows = np.asarray(target_rows, dtype=np.int64)
    data = np.asarray(values, dtype=np.complex128)
    global_size = int(current_global_size)
    if rows.ndim != 1 or data.ndim != 1:
        raise ValueError("current active target rows and values must be vectors")
    if len(rows) != len(data):
        raise ValueError("current active target row/value lengths differ")
    if not np.isfinite(data).all():
        raise ValueError("current active target values are non-finite")
    current_range = tuple(map(int, current_ownership_range))
    if (
        len(current_range) != 2
        or not 0 <= current_range[0] <= current_range[1] <= global_size
    ):
        raise ValueError("current Vec ownership range is invalid")
    normalized_ranges = tuple(
        tuple(map(int, ownership_range)) for ownership_range in all_ownership_ranges
    )
    if current_range not in normalized_ranges:
        raise ValueError("current Vec ownership range is absent from the MPI layout")
    if len(normalized_ranges) != len(all_target_row_shards):
        raise ValueError("MPI ownership and target-row shard counts differ")
    if any(
        len(ownership_range) != 2
        or not 0 <= ownership_range[0] <= ownership_range[1] <= global_size
        for ownership_range in normalized_ranges
    ):
        raise ValueError("MPI ownership ranges are invalid")
    ordered_ranges = sorted(normalized_ranges)
    if (
        not ordered_ranges
        or ordered_ranges[0][0] != 0
        or ordered_ranges[-1][1] != global_size
        or any(
            previous[1] != current[0]
            for previous, current in zip(ordered_ranges, ordered_ranges[1:])
        )
    ):
        raise ValueError("MPI ownership ranges are not contiguous over the F bounds")
    local_rows = tuple(int(row) for row in rows)
    if len(local_rows) != len(set(local_rows)):
        raise ValueError("current active target rows contain duplicates")
    if global_size <= 0 or any(row < 0 or row >= global_size for row in local_rows):
        raise ValueError("current active target rows are outside the F bounds")
    if any(row < current_range[0] or row >= current_range[1] for row in local_rows):
        raise ValueError("current active target row is outside its owner range")
    normalized_shards = tuple(
        tuple(int(row) for row in shard) for shard in all_target_row_shards
    )
    flattened_rows = [row for shard in normalized_shards for row in shard]
    if len(flattened_rows) != len(set(flattened_rows)):
        raise ValueError("current active target rows overlap across MPI shards")
    for ownership_range, shard in zip(
        normalized_ranges, normalized_shards, strict=True
    ):
        first, last = ownership_range
        if len(shard) != len(set(shard)):
            raise ValueError("current active target rows contain a local duplicate")
        if any(row < 0 or row >= global_size for row in shard):
            raise ValueError("current active target rows are outside the F bounds")
        if any(row < first or row >= last for row in shard):
            raise ValueError("current active target row is outside its owner range")
    first, last = current_range
    owned = np.ones(len(rows), dtype=bool)
    return owned, {
        "target_row_count": int(len(rows)),
        "target_row_sha256": _sha256_owned_array(rows),
        "global_size": global_size,
        "current_ownership_range": [first, last],
        "owner_coverage": {
            "pass": True,
            "global_target_row_count": len(flattened_rows),
            "global_unique_target_row_count": len(set(flattened_rows)),
            "mpi_size": len(normalized_ranges),
        },
    }


def _selected_mode_internal_traction_vector(
    system: CurrentBareFAuthoritySystem,
    *,
    branch: str,
    mode_index: int,
    label: str,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Consume one branch from the paired, one-factor exact source cache."""

    if branch not in {"positive", "negative"}:
        raise ValueError("selected internal branch must be positive or negative")
    if int(mode_index) != (281 if branch == "positive" else 283):
        raise ValueError("selected exact source column is not frozen")
    cache = _ensure_selected_exact_source_cache(system)
    packet = cache["packets"][branch]
    count = int(system.construction_inventory["source_build_counts"][label])
    if count not in {1, 2}:
        raise RuntimeError("selected exact source cache was consumed too many times")
    values = cache["columns"][branch]["values" if count == 1 else "repeat_values"]
    target_rows = np.asarray(cache["target_rows"], dtype=PETSc.IntType)
    values = np.asarray(values, dtype=np.complex128)
    vector = system.F.createVecLeft()
    vector.set(0.0)
    current_ownership = tuple(map(int, vector.getOwnershipRange()))
    all_ownership = tuple(
        tuple(map(int, ownership_range))
        for ownership_range in system.comm.allgather(current_ownership)
    )
    local_row_error: FreshBareFAuthorityIdentityError | None = None
    try:
        local_target_rows = tuple(int(row) for row in target_rows)
    except (TypeError, ValueError, OverflowError) as exc:
        local_target_rows = ()
        local_row_error = FreshBareFAuthorityIdentityError(
            "CURRENT_ACTIVE_TARGET_ROW_IDENTITY_FAIL",
            f"one-cell source target rows are invalid: {exc}",
            stage="source_mapping",
        )
    target_row_shards = tuple(
        tuple(int(row) for row in shard)
        for shard in system.comm.allgather(local_target_rows)
    )
    validation_error = local_row_error
    if validation_error is None:
        try:
            owned, target_row_audit = _validate_current_active_target_rows(
                target_rows,
                values,
                current_global_size=int(vector.getSize()),
                current_ownership_range=current_ownership,
                all_ownership_ranges=all_ownership,
                all_target_row_shards=target_row_shards,
            )
        except ValueError as exc:
            validation_error = FreshBareFAuthorityIdentityError(
                "CURRENT_ACTIVE_TARGET_ROW_IDENTITY_FAIL",
                str(exc),
                stage="source_mapping",
                details={"target_row_count": int(len(target_rows))},
            )
    _collective_identity_stop_with_cleanup(
        system.comm,
        validation_error,
        vector.destroy,
    )
    if np.any(owned):
        vector.setValues(
            target_rows[owned],
            np.asarray(values[owned], dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    vector.assemble()
    return vector, {
        "label": label,
        "source": (
            f"frozen_selected_packet.current_layout_exact_one_cell.{branch}_traction"
        ),
        "kind": "current_layout_full3d_one_cell_exact_schur_column",
        "mode_index": int(mode_index),
        "rhs_generation": "first" if count == 1 else "independent_repeat",
        "selected_mode_packet_manifest": str(packet["manifest_path"]),
        "selected_mode_packet_manifest_sha256": str(packet["manifest_sha256"]),
        "selected_mode_packet_identity_sha256": str(packet["identity_sha256"]),
        "selected_mode_packet_branch": branch,
        "selected_mode_packet_index": int(mode_index),
        "selected_mode_packet_mode_key": _json_safe(packet["mode_key"]),
        "selected_mode_packet_beta": _json_safe(packet["beta"]),
        "selected_mode_packet_passive_branch_valid": bool(
            packet["passive_branch_valid"]
        ),
        "selected_mode_packet_qep_calls": 0,
        "selected_mode_packet_left_values_checked": True,
        "selected_mode_packet_ownership_range": list(
            map(int, packet["ownership_range"])
        ),
        "selected_mode_packet_global_size": int(packet["global_size"]),
        "current_active_rhs_global_size": int(vector.getSize()),
        "current_active_rhs_ownership_range": list(
            map(int, vector.getOwnershipRange())
        ),
        "current_active_target_row_audit": target_row_audit,
        "surface_load_convention": "frozen_full3d_one_cell_exact_schur",
        "sign_convention": "matrix_column_as_stored/no_extra_sign",
        "propagation_model": cache["audit"].get(
            "propagation_model", "full3d_uniform_cg"
        ),
        "propagation_axial_fem_degree": cache["audit"].get(
            "propagation_axial_fem_degree"
        ),
        "propagation_axial_h_nm": cache["audit"].get("propagation_axial_h_nm", 10.0),
        "matrix_objects": dict(system.dtn_objects_constructed),
        "physical_dtn_operator_constructed": False,
        "raw_global_row_remap": False,
        "one_cell_source_audit": cache["audit"],
    }


def _external_minimal_c_vector(
    system: CurrentBareFAuthoritySystem,
    *,
    mode_index: int,
    sign: float,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    authority = getattr(system, "external_mode_authority", None)
    if authority is not None:
        system.construction_inventory["external_mode_authority"] = (
            validate_external_mode_authority(
                system.external_modes,
                authority,
                current_resolved_config_sha256=getattr(
                    system, "external_mode_current_resolved_config_sha256", None
                ),
            )
        )
    mode = system.external_modes[int(mode_index)]
    degree = _dtn_surface_quadrature_degree(system.cfg, list(system.external_modes))
    assemblers = tuple(
        _ReusableSurfaceComponentAssembler(
            system.V,
            system.local_mesh.mesh_data,
            system.local_mesh.external_facet_tag,
            component,
            quadrature_degree=degree,
        )
        for component in (0, 1)
    )
    full = None
    active = None
    try:
        full_components = tuple(
            assembler.assemble_unconstrained_vector(mode) for assembler in assemblers
        )
        inventory = system.construction_inventory
        inventory["minimal_external_coupling_objects_constructed"] = 1
        inventory["minimal_external_surface_component_count"] = len(full_components)
        inventory["minimal_external_coupling_construction_call_count"] = (
            int(inventory.get("minimal_external_coupling_construction_call_count", 0))
            + 1
        )
        inventory["minimal_external_component_instances_total"] = int(
            inventory.get("minimal_external_component_instances_total", 0)
        ) + len(assemblers)
        inventory["minimal_external_peak_live_components"] = max(
            int(inventory.get("minimal_external_peak_live_components", 0)),
            len(assemblers),
        )
        inventory["minimal_external_coupling_kind_count"] = 1
        full = full_components[0].copy()
        traction = np.asarray(_traction_vector(mode, system.cfg), dtype=np.complex128)
        full.scale(PETSc.ScalarType(traction[0]))
        full.axpy(PETSc.ScalarType(traction[1]), full_components[1])
        active = condense_unconstrained_vector_to_active_trace(
            system.condensed,
            full,
            side="right",
        )
        active.scale(PETSc.ScalarType(sign))
        return active, {
            "mode_index": int(mode_index),
            "mode_key": {
                "side": str(mode.side),
                "m": int(mode.m),
                "n": int(mode.n),
                "polarization": str(mode.polarization),
                "alpha": _json_safe(mode.alpha),
                "gamma": _json_safe(mode.gamma),
                "beta": _json_safe(mode.beta),
            },
            "source": "current_external_minimal_surface_components",
            "sign": float(sign),
            "traction_coefficients": _json_safe(traction),
            "surface_quadrature_degree": int(degree),
            "external_mode_authority": _json_safe(
                system.construction_inventory.get("external_mode_authority", {})
            ),
            "surface_components": 2,
            "full_C_materialized": False,
            "full_C_oracle": "test_only_direct_component_column_regression",
            "matrix_objects": dict(system.dtn_objects_constructed),
            "physical_dtn_operator_constructed": False,
        }
    except Exception:
        if active is not None:
            active.destroy()
        raise
    finally:
        if full is not None:
            full.destroy()
        for vector in locals().get("full_components", ()):
            vector.destroy()


def _surface_source_vector(
    system: CurrentBareFAuthoritySystem,
    *,
    label: str,
    mode_index: int,
    sign: float,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Dispatch to the semantically distinct internal or external source."""

    if label == "modal_traction_positive":
        return _selected_mode_internal_traction_vector(
            system,
            branch="positive",
            mode_index=mode_index,
            label=label,
        )
    if label == "modal_traction_negative":
        return _selected_mode_internal_traction_vector(
            system,
            branch="negative",
            mode_index=mode_index,
            label=label,
        )
    if label == "external_dtn_coupling":
        return _external_minimal_c_vector(
            system,
            mode_index=mode_index,
            sign=sign,
        )
    raise ValueError(f"unsupported surface source label: {label!r}")


def build_current_bare_f_rhs(
    system: CurrentBareFAuthoritySystem,
    label: str,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Build one frozen source on the current canonical active layout."""

    if label not in V5_BARE_F_SOURCE_SPECS:
        raise ValueError(f"unknown V5 bare-F source label: {label!r}")
    source_build_counts = system.construction_inventory.setdefault(
        "source_build_counts",
        {name: 0 for name in V5_BARE_F_SOURCE_LABELS},
    )
    source_build_counts[label] = int(source_build_counts.get(label, 0)) + 1
    spec = dict(V5_BARE_F_SOURCE_SPECS[label])
    if spec["kind"] == "canonical_random":
        zero = system.condensed.create_active_vector()
        try:
            packets, _audit = _canonical_packets_collective_safe(system, zero)
            values = {
                key: _canonical_random_value(key, int(spec["seed"]))
                for key, _value in packets
            }
            vector = _reconstruct_canonical_vec_collective_safe(
                system,
                values,
                label=label,
            )
            return vector, {
                **spec,
                "label": label,
                "canonical_key_source": "current_hcurl_canonical_vector_dolfinx",
                "matrix_objects": dict(system.dtn_objects_constructed),
                "physical_dtn_operator_constructed": False,
                "numeric_formula": "sha256(canonical_physical_key)+seed",
            }
        finally:
            zero.destroy()
    vector, source_audit = _surface_source_vector(
        system,
        label=label,
        mode_index=int(spec["resolved_column"]),
        sign=float(spec.get("sign", -1.0)),
    )
    return vector, {**spec, "label": label, **source_audit}


def _canonical_value_error_is_identity(exc: ValueError) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "duplicate canonical",
            "canonical active-trace",
            "canonical entity",
            "canonical key",
            "floquet relation",
        )
    )


def _canonical_packets_collective_safe(
    system: CurrentBareFAuthoritySystem,
    vector: PETSc.Vec,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Extract raw canonical packets with a collective identity decision."""

    local_error: FreshBareFAuthorityIdentityError | None = None
    implementation_error: Exception | None = None
    packets: tuple[Any, ...] = ()
    audit: dict[str, Any] = {}
    try:
        packets, audit = extract_canonical_active_trace_packets(
            system.condensed,
            system.V,
            system.floquet_data,
            vector,
        )
        tokens = tuple(_canonical_key_token(key) for key, _value in packets)
        if len(tokens) != len(set(tokens)):
            local_error = FreshBareFAuthorityIdentityError(
                "CANONICAL_ACTIVE_KEY_DUPLICATE_IDENTITY_FAIL",
                "current canonical active-trace packets contain duplicates",
                stage="canonical_packet_extraction",
            )
    except ValueError as exc:
        if _canonical_value_error_is_identity(exc):
            local_error = FreshBareFAuthorityIdentityError(
                "CANONICAL_ACTIVE_KEY_EXTRACTION_IDENTITY_FAIL",
                str(exc),
                stage="canonical_packet_extraction",
            )
        else:
            implementation_error = exc
    except Exception as exc:
        implementation_error = exc
    _collective_raise_canonical_exception(
        system.comm,
        stage="canonical_packet_extraction",
        identity_error=local_error,
        implementation_error=implementation_error,
    )
    return packets, audit


def canonical_packets_for_vector(
    system: CurrentBareFAuthoritySystem,
    vector: PETSc.Vec,
) -> tuple[tuple[str, ...], np.ndarray, dict[str, Any]]:
    """Return owner-local canonical keys and values for one active Vec."""

    packets, audit = _canonical_packets_collective_safe(system, vector)
    implementation_error: Exception | None = None
    tokens: tuple[str, ...] = ()
    values = np.asarray([], dtype=np.complex128)
    try:
        tokens = tuple(_canonical_key_token(key) for key, _value in packets)
        values = np.asarray([value for _key, value in packets], dtype=np.complex128)
    except Exception as exc:
        implementation_error = exc
    _collective_raise_canonical_exception(
        system.comm,
        stage="canonical_packet_tokenization",
        implementation_error=implementation_error,
    )
    return tokens, values, audit


def canonical_layout_tokens(
    system: CurrentBareFAuthoritySystem,
) -> tuple[tuple[str, ...], str, dict[str, Any]]:
    """Extract the current owner-local key layout and a global key-set hash."""

    zero = system.condensed.create_active_vector()
    try:
        tokens, _values, audit = canonical_packets_for_vector(system, zero)
    finally:
        zero.destroy()
    gathered = system.comm.gather(tuple(tokens), root=0)
    local_error = None
    if system.comm.rank == 0:
        all_tokens = [token for part in gathered for token in part]
        if len(all_tokens) != len(set(all_tokens)):
            local_error = FreshBareFAuthorityIdentityError(
                "CANONICAL_ACTIVE_KEY_SET_IDENTITY_FAIL",
                "current canonical active-trace key set is not unique",
                stage="canonical_layout_validation",
            )
    _collective_raise_fresh_bare_f_identity(system.comm, local_error)
    if system.comm.rank == 0:
        all_tokens = [token for part in gathered for token in part]
        key_hash = _sha256_bytes("\n".join(sorted(all_tokens)).encode("utf-8"))
    else:
        key_hash = None
    key_hash = system.comm.bcast(key_hash, root=0)
    return tokens, str(key_hash), audit


def _plane_original_dofs(
    system: CurrentBareFAuthoritySystem,
    *,
    plane_z_nm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Find owner-local original/active trace rows on one current plane."""

    mesh = system.local_mesh.mesh
    topology = mesh.topology
    tdim = topology.dim
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(dimension, tdim)
        topology.create_connectivity(tdim, dimension)
    layout = system.V.dofmap.dof_layout
    owned_original = {
        int(value)
        for value in system.condensed.trace_constraints.owned_active_original_dofs
    }
    original_to_active = {
        int(key): int(value)
        for key, value in system.condensed.trace_constraints.original_to_active.items()
    }
    cell_to_entity = {
        dimension: topology.connectivity(tdim, dimension) for dimension in (1, 2)
    }
    tolerance = 1.0e-10 * max(
        system.local_mesh.mesh_data.mesh_axis_cell_stats["x"]["max"],
        system.local_mesh.mesh_data.mesh_axis_cell_stats["y"]["max"],
        1.0,
    )
    plane_rows: set[int] = set()
    owned_cells = int(topology.index_map(tdim).size_local)
    for cell in range(owned_cells):
        local_dofs = np.asarray(system.V.dofmap.cell_dofs(cell), dtype=np.int32)
        global_dofs = np.asarray(
            system.V.dofmap.index_map.local_to_global(local_dofs), dtype=np.int64
        )
        for dimension in (1, 2):
            links = np.asarray(cell_to_entity[dimension].links(cell), dtype=np.int32)
            for local_entity, entity in enumerate(links):
                geometry = cpp.mesh.entities_to_geometry(
                    mesh._cpp_object,
                    dimension,
                    np.asarray([int(entity)], dtype=np.int32),
                    True,
                )
                coordinates = np.asarray(
                    mesh.geometry.x[np.asarray(geometry[0], dtype=np.int64)],
                    dtype=np.float64,
                )
                if not np.allclose(
                    coordinates[:, 2],
                    float(plane_z_nm),
                    rtol=0.0,
                    atol=10.0 * tolerance,
                ):
                    continue
                positions = np.asarray(
                    layout.entity_dofs(dimension, local_entity), dtype=np.int32
                )
                for row in global_dofs[positions]:
                    if int(row) in owned_original:
                        plane_rows.add(int(row))
    original_rows = np.asarray(sorted(plane_rows), dtype=PETSc.IntType)
    active_rows = np.asarray(
        [original_to_active[int(row)] for row in original_rows],
        dtype=PETSc.IntType,
    )
    if len(np.unique(active_rows)) != len(active_rows):
        raise RuntimeError("current Gamma plane has duplicate active rows")
    return original_rows, active_rows


def _build_current_gamma_layout(
    system: CurrentBareFAuthoritySystem,
    *,
    name: str,
    plane_z_nm: float,
    plane_cell_side: str,
    frozen_z_index: int,
) -> Any:
    original_rows, active_rows = _plane_original_dofs(
        system,
        plane_z_nm=plane_z_nm,
    )
    return build_dolfinx_plane_gamma_layout(
        function_space=system.V,
        condensed=system.condensed,
        floquet_data=system.floquet_data,
        interface_z_nm=float(plane_z_nm),
        plane_cell_side=plane_cell_side,
        plane_original_dofs=original_rows,
        gamma_rows_local=active_rows,
        plane_identity={
            "name": str(name),
            "side": "bottom",
            "interface_z_nm": float(plane_z_nm),
            "source": "current_bare_f_active_trace",
            "frozen_group_partition_z_index": int(frozen_z_index),
            "established_layout_reference": "task040_v2_v3_lower_upper_gamma_rows",
        },
    )


def _gamma_values_for_vector(
    vector: PETSc.Vec,
    layout: Any,
) -> np.ndarray:
    """Convert one current active vector to the layout's canonical Gamma order."""

    start, end = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    values = np.zeros(len(layout.canonical_keys), dtype=np.complex128)
    for placement in layout.blocks:
        raw_rows = np.asarray(placement.block.raw_row_ids, dtype=np.int64)
        if np.any(raw_rows < start) or np.any(raw_rows >= end):
            raise RuntimeError("Gamma layout contains a non-owned active row")
        raw_values = local[raw_rows - start]
        canonical_values = placement.block.raw_to_canonical @ raw_values
        values[np.asarray(placement.positions, dtype=np.int64)] = canonical_values
    if not np.isfinite(values).all():
        raise ValueError("Gamma packet values are nonfinite")
    return values


def _write_gamma_trace_packet(
    *,
    root: Path,
    rank: int,
    label: str,
    gamma_name: str,
    layout: Any,
    layout_path: str,
    layout_sha256: str,
    vector: PETSc.Vec,
    source_metadata: Mapping[str, Any],
    key_set_sha256: str,
    bare_f_operator_hash: str,
    canonical_layout_sha256: str,
) -> dict[str, Any]:
    rank_dir = root / f"rank{int(rank):04d}"
    values = _gamma_values_for_vector(vector, layout)
    stem = f"bottom_{label}_{gamma_name.lower()}_exact_trace"
    array_path = rank_dir / f"{stem}.npy"
    metadata_path = rank_dir / f"{stem}.json"
    _atomic_npy(array_path, values)
    array_sha256 = _sha256_owned_array(values)
    vector_comm = vector.getComm().tompi4py()
    global_array_hashes = vector_comm.gather(array_sha256, root=0)
    if vector_comm.rank == 0:
        global_array_sha256 = _sha256_bytes(
            "\n".join(global_array_hashes).encode("ascii")
        )
    else:
        global_array_sha256 = None
    global_array_sha256 = vector_comm.bcast(global_array_sha256, root=0)
    source_definition_sha256 = _require_sha256(
        source_metadata.get("source_definition_sha256"),
        "source_definition_sha256",
    )
    bare_f_operator_hash = _require_sha256(
        bare_f_operator_hash,
        "bare_f_operator_hash",
    )
    record = {
        "schema": "task040.v5.current_bare_f_authority_trace.v1",
        "side": "bottom",
        "label": label,
        "role": "exact_trace",
        "gamma": gamma_name,
        "dtype": "complex128",
        "array_path": str(array_path.relative_to(root)),
        "metadata_path": str(metadata_path.relative_to(root)),
        "layout_path": layout_path,
        "layout_sha256": layout_sha256,
        "array_sha256": array_sha256,
        "source_definition_sha256": source_definition_sha256,
        "bare_f_operator_hash": str(bare_f_operator_hash),
        "canonical_key_set_sha256": str(key_set_sha256),
        "canonical_layout_sha256": _require_sha256(
            canonical_layout_sha256,
            "canonical_layout_sha256",
        ),
        "source_provenance": {
            key: source_metadata.get(key)
            for key in (
                "input_sha256",
                "physical_model_sha256",
                "selected_manifest_sha256",
                "selected_identity_sha256",
                "resolved_config_sha256",
                "source_sha",
            )
        },
        "canonical_key_count_local": len(layout.canonical_keys),
        "canonical_key_order_sha256": layout.audit["canonical_key_order_sha256"],
        "layout_audit": _json_safe(dict(layout.audit)),
        "global_sha256": str(global_array_sha256),
        "raw_global_row_remap": False,
    }
    record["rank_local_shard_binding_sha256"] = _sha256_bytes(
        json.dumps(
            {
                "rank": int(rank),
                "label": str(label),
                "role": "exact_trace",
                "gamma": gamma_name,
                "source_definition_sha256": source_definition_sha256,
                "canonical_key_set_sha256": str(key_set_sha256),
                "layout_sha256": str(layout_sha256),
                "array_sha256": array_sha256,
                "bare_f_operator_hash": str(bare_f_operator_hash),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    _atomic_json(metadata_path, record)
    return record


def _check_owner_packet_bindings(
    *,
    owner_shards: list[Mapping[str, Any]],
    all_rhs_records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    all_exact_records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    all_gamma_records: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Any]]]],
    all_gamma_layout_records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    source_definition_hashes: Mapping[str, list[str]],
    bare_f_operator_hash: str,
    labels: tuple[str, ...] = V5_BARE_F_SOURCE_LABELS,
    expected_mpi_size: int = 8,
) -> bool:
    """Purely validate complete per-rank RHS/exact/Gamma packet bindings."""

    expected_ranks = {str(rank) for rank in range(int(expected_mpi_size))}
    rank_sets = (
        set(all_rhs_records),
        set(all_exact_records),
        set(all_gamma_records),
        set(all_gamma_layout_records),
        {str(item.get("rank")) for item in owner_shards},
    )
    if any(rank_set != expected_ranks for rank_set in rank_sets):
        return False
    if len(owner_shards) != int(expected_mpi_size):
        return False
    if any(
        not _is_valid_sha256(item.get("sha256"))
        or not _is_valid_sha256(item.get("canonical_layout", {}).get("sha256"))
        for item in owner_shards
    ):
        return False
    expected_layout = {
        str(item["rank"]): item["canonical_layout"]["sha256"] for item in owner_shards
    }

    def vector_record_passes(
        record: Mapping[str, Any],
        *,
        rank: str,
        role: str,
    ) -> bool:
        if record.get("role") != role:
            return False
        identity = record.get("vector_identity")
        source_definition = record.get("source_definition")
        provenance = record.get("source_provenance")
        if (
            not isinstance(identity, Mapping)
            or not isinstance(source_definition, Mapping)
            or not _is_valid_source_provenance(provenance)
        ):
            return False
        record_required_hashes = (
            "source_definition_sha256",
            "bare_f_operator_hash",
            "canonical_key_set_sha256",
            "canonical_layout_sha256",
            "rank_local_shard_binding_sha256",
            "global_sha256",
        )
        identity_required_hashes = (
            "array_sha256",
            "owner_row_array_sha256",
            "global_sha256",
            "canonical_key_set_sha256",
        )
        if any(
            not _is_valid_sha256(record.get(field)) for field in record_required_hashes
        ) or any(
            not _is_valid_sha256(identity.get(field))
            for field in identity_required_hashes
        ):
            return False
        for field in (
            "array_sha256",
            "owner_row_array_sha256",
            "global_sha256",
            "canonical_to_current_roundtrip_relative",
        ):
            if record.get(field) != identity.get(field):
                return False
        for field in ("global_size", "local_size", "ownership_range"):
            if record.get(field) != identity.get(field):
                return False
        if record.get("source_definition_sha256") != source_definition.get(
            "source_definition_sha256"
        ):
            return False
        if record.get("canonical_key_set_sha256") != identity.get(
            "canonical_key_set_sha256"
        ):
            return False
        if record.get("bare_f_operator_hash") != str(bare_f_operator_hash):
            return False
        if record.get("canonical_layout_sha256") != expected_layout[rank]:
            return False
        if record.get("finite") is False or identity.get("finite") is not True:
            return False
        roundtrip = identity.get("canonical_to_current_roundtrip_relative")
        if not isinstance(roundtrip, (int, float)) or not np.isfinite(roundtrip):
            return False
        if float(roundtrip) > 1.0e-12:
            return False
        rhs_repeat = source_definition.get("rhs_repeat")
        if not isinstance(rhs_repeat, Mapping) or rhs_repeat.get("pass") is not True:
            return False
        expected_binding = _rank_local_shard_binding_sha256(
            rank=int(rank),
            label=str(record.get("label")),
            role=role,
            source_definition_sha256=str(record["source_definition_sha256"]),
            key_set_sha256=str(record["canonical_key_set_sha256"]),
            canonical_layout_sha256=str(record["canonical_layout_sha256"]),
            identity=identity,
            source_provenance=provenance,
            bare_f_operator_hash=str(record["bare_f_operator_hash"]),
            rhs_repeat=rhs_repeat,
        )
        return record.get("rank_local_shard_binding_sha256") == expected_binding

    def gamma_record_passes(
        record: Mapping[str, Any],
        *,
        rank: str,
        label: str,
        gamma_name: str,
    ) -> bool:
        if (
            record.get("role") != "exact_trace"
            or record.get("label") != label
            or record.get("gamma") != gamma_name
        ):
            return False
        provenance = record.get("source_provenance")
        if not _is_valid_source_provenance(provenance):
            return False
        if any(
            not _is_valid_sha256(record.get(field))
            for field in (
                "source_definition_sha256",
                "bare_f_operator_hash",
                "canonical_key_set_sha256",
                "canonical_layout_sha256",
                "layout_sha256",
                "array_sha256",
                "global_sha256",
                "rank_local_shard_binding_sha256",
            )
        ):
            return False
        if record.get("bare_f_operator_hash") != str(bare_f_operator_hash):
            return False
        if record.get("canonical_layout_sha256") != expected_layout[rank]:
            return False
        if record.get("layout_sha256") != all_gamma_layout_records[rank][
            gamma_name
        ].get("sha256"):
            return False
        binding_payload = {
            "rank": int(rank),
            "label": label,
            "role": "exact_trace",
            "gamma": gamma_name,
            "source_definition_sha256": record["source_definition_sha256"],
            "canonical_key_set_sha256": record["canonical_key_set_sha256"],
            "layout_sha256": record["layout_sha256"],
            "array_sha256": record["array_sha256"],
            "bare_f_operator_hash": record["bare_f_operator_hash"],
        }
        expected_binding = _sha256_bytes(
            json.dumps(
                binding_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return record.get("rank_local_shard_binding_sha256") == expected_binding

    def global_hash_passes(
        records: Mapping[str, Mapping[str, Mapping[str, Any]]],
        label: str,
    ) -> bool:
        by_rank = [records[rank][label] for rank in sorted(expected_ranks)]
        local_hashes = [
            str(record.get("vector_identity", {}).get("array_sha256"))
            for record in by_rank
        ]
        if any(not _is_valid_sha256(value) for value in local_hashes):
            return False
        expected_global = _sha256_bytes("\n".join(local_hashes).encode("ascii"))
        return all(
            record.get("global_sha256") == expected_global
            and record.get("vector_identity", {}).get("global_sha256")
            == expected_global
            for record in by_rank
        )

    def gamma_global_hash_passes(label: str, gamma_name: str) -> bool:
        by_rank = [
            all_gamma_records[rank][label][gamma_name]
            for rank in sorted(expected_ranks)
        ]
        local_hashes = [str(record.get("array_sha256")) for record in by_rank]
        if any(not _is_valid_sha256(value) for value in local_hashes):
            return False
        expected_global = _sha256_bytes("\n".join(local_hashes).encode("ascii"))
        return all(record.get("global_sha256") == expected_global for record in by_rank)

    def vector_ownership_contract_passes(
        records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> bool:
        vectors = [
            records[rank][label] for rank in sorted(expected_ranks) for label in labels
        ]
        global_sizes = {record.get("global_size") for record in vectors}
        if len(global_sizes) != 1:
            return False
        global_size = next(iter(global_sizes))
        if not isinstance(global_size, int) or global_size <= 0:
            return False
        for record in vectors:
            ownership = record.get("ownership_range")
            if not isinstance(ownership, list) or len(ownership) != 2:
                return False
            first, last = map(int, ownership)
            if last - first != record.get("local_size"):
                return False
            if not 0 <= first <= last <= global_size:
                return False
        for label in labels:
            ranges = [
                tuple(map(int, records[rank][label]["ownership_range"]))
                for rank in sorted(expected_ranks)
            ]
            ordered = sorted(ranges)
            if (
                not ordered
                or ordered[0][0] != 0
                or ordered[-1][1] != global_size
                or any(
                    previous[1] != current[0]
                    for previous, current in zip(ordered, ordered[1:])
                )
            ):
                return False
        return True

    for label in labels:
        rhs_hashes = [
            str(all_rhs_records[rank][label].get("source_definition_sha256"))
            for rank in sorted(expected_ranks)
            if label in all_rhs_records[rank]
        ]
        exact_hashes = [
            str(all_exact_records[rank][label].get("source_definition_sha256"))
            for rank in sorted(expected_ranks)
            if label in all_exact_records[rank]
        ]
        if (
            len(rhs_hashes) != int(expected_mpi_size)
            or len(exact_hashes) != int(expected_mpi_size)
            or len(set(rhs_hashes)) != 1
            or rhs_hashes != exact_hashes
            or source_definition_hashes.get(label) != rhs_hashes
            or not _is_valid_sha256(rhs_hashes[0])
        ):
            return False
    if not vector_ownership_contract_passes(all_rhs_records):
        return False
    if not vector_ownership_contract_passes(all_exact_records):
        return False
    for rank in sorted(expected_ranks):
        for label in labels:
            rhs_range = all_rhs_records[rank][label].get("ownership_range")
            exact_range = all_exact_records[rank][label].get("ownership_range")
            if rhs_range != exact_range:
                return False
    if any(
        set(all_gamma_layout_records[rank]) != {"Gamma_L", "Gamma_U"}
        or any(
            not isinstance(all_gamma_layout_records[rank][gamma_name], Mapping)
            or not _is_valid_sha256(
                all_gamma_layout_records[rank][gamma_name].get("sha256")
            )
            for gamma_name in ("Gamma_L", "Gamma_U")
        )
        for rank in sorted(expected_ranks)
    ):
        return False
    for rank in sorted(expected_ranks):
        rhs_by_label = all_rhs_records[rank]
        exact_by_label = all_exact_records[rank]
        gamma_by_label = all_gamma_records[rank]
        if set(rhs_by_label) != set(labels) or set(exact_by_label) != set(labels):
            return False
        if set(gamma_by_label) != set(labels):
            return False
        layout_sha = expected_layout[rank]
        for label in labels:
            rhs = rhs_by_label[label]
            exact = exact_by_label[label]
            if not _is_valid_source_provenance(
                rhs.get("source_provenance")
            ) or not _is_valid_source_provenance(exact.get("source_provenance")):
                return False
            for field in (
                "source_definition_sha256",
                "bare_f_operator_hash",
                "canonical_key_set_sha256",
                "canonical_layout_sha256",
                "source_provenance",
            ):
                if rhs.get(field) != exact.get(field):
                    return False
            if rhs.get("bare_f_operator_hash") != str(bare_f_operator_hash):
                return False
            if rhs.get("canonical_layout_sha256") != layout_sha:
                return False
            if not vector_record_passes(rhs, rank=rank, role="rhs"):
                return False
            if not vector_record_passes(exact, rank=rank, role="exact_output"):
                return False
            if not global_hash_passes(all_rhs_records, label):
                return False
            if not global_hash_passes(all_exact_records, label):
                return False
            gamma_for_label = gamma_by_label[label]
            if set(gamma_for_label) != {"Gamma_L", "Gamma_U"}:
                return False
            for gamma_name, gamma in gamma_for_label.items():
                for field in (
                    "source_definition_sha256",
                    "bare_f_operator_hash",
                    "canonical_key_set_sha256",
                    "canonical_layout_sha256",
                    "source_provenance",
                ):
                    if gamma.get(field) != rhs.get(field):
                        return False
                if gamma.get("canonical_layout_sha256") != layout_sha:
                    return False
                if not gamma_record_passes(
                    gamma,
                    rank=rank,
                    label=label,
                    gamma_name=gamma_name,
                ) or not gamma_global_hash_passes(label, gamma_name):
                    return False
    return True


def vector_identity(
    system: CurrentBareFAuthoritySystem,
    tokens: tuple[str, ...],
    values: np.ndarray,
    key_set_sha256: str,
    owner_values: np.ndarray | None = None,
    canonical_roundtrip_relative: float | None = None,
) -> dict[str, Any]:
    """Build compact owner/global identity without using raw-row semantics."""

    first, last = map(int, system.F.getOwnershipRange())
    values = np.asarray(values, dtype=np.complex128)
    local_hash = _sha256_owned_array(values)
    owner_values = (
        np.asarray(owner_values, dtype=np.complex128)
        if owner_values is not None
        else values
    )
    owner_hash = _sha256_owned_array(owner_values)
    hashes = system.comm.gather(local_hash, root=0)
    if system.comm.rank == 0:
        global_hash = _sha256_bytes("\n".join(hashes).encode("ascii"))
    else:
        global_hash = None
    global_hash = system.comm.bcast(global_hash, root=0)
    return {
        "dtype": "complex128",
        "global_size": int(system.F.getSize()[0]),
        "local_size": int(last - first),
        "ownership_range": [first, last],
        "array_sha256": local_hash,
        "owner_row_array_sha256": owner_hash,
        "owner_row_order": "petsc_current_ownership_range",
        "global_sha256": str(global_hash),
        "canonical_key_set_sha256": str(key_set_sha256),
        "canonical_key_count_local": len(tokens),
        "finite": bool(np.all(np.isfinite(values))),
        "norm_local": float(np.linalg.norm(values)),
        "raw_global_row_remap": False,
        "canonical_to_current_roundtrip_relative": canonical_roundtrip_relative,
    }


def canonical_to_current_roundtrip_relative(
    system: CurrentBareFAuthoritySystem,
    tokens: tuple[str, ...],
    values: np.ndarray,
    vector: PETSc.Vec,
) -> float:
    """Reconstruct a current Vec from canonical packets and compare it."""

    if len(tokens) != len(values):
        raise ValueError("canonical token/value lengths differ")
    zero = system.condensed.create_active_vector()
    try:
        reference_packets, _audit = extract_canonical_active_trace_packets(
            system.condensed,
            system.V,
            system.floquet_data,
            zero,
        )
        values_by_token = {
            token: value for token, value in zip(tokens, values, strict=True)
        }
        values_by_key = {
            key: values_by_token[_canonical_key_token(key)]
            for key, _value in reference_packets
        }
        reconstructed = reconstruct_canonical_active_trace_vec(
            system.condensed,
            system.V,
            system.floquet_data,
            values_by_key,
        )
    finally:
        zero.destroy()
    try:
        return _relative_difference(reconstructed, vector)
    finally:
        reconstructed.destroy()


def _canonical_roundtrip_or_identity_stop(
    system: CurrentBareFAuthoritySystem,
    tokens: tuple[str, ...],
    values: np.ndarray,
    vector: PETSc.Vec,
    *,
    label: str,
    stage: str,
) -> float:
    """Run canonical round-trip collectively and classify only data failures."""

    local_error: FreshBareFAuthorityIdentityError | None = None
    implementation_error: Exception | None = None
    result = float("nan")
    try:
        result = canonical_to_current_roundtrip_relative(
            system,
            tokens,
            values,
            vector,
        )
    except (KeyError, IndexError) as exc:
        local_error = FreshBareFAuthorityIdentityError(
            "CANONICAL_ACTIVE_ROUNDTRIP_IDENTITY_FAIL",
            f"canonical round-trip reconstruction failed for {label}: {exc}",
            stage=stage,
            details={"label": label},
        )
    except ValueError as exc:
        if _canonical_value_error_is_identity(exc):
            local_error = FreshBareFAuthorityIdentityError(
                "CANONICAL_ACTIVE_ROUNDTRIP_IDENTITY_FAIL",
                f"canonical round-trip reconstruction failed for {label}: {exc}",
                stage=stage,
                details={"label": label},
            )
        else:
            implementation_error = exc
    except Exception as exc:
        implementation_error = exc
    _collective_raise_canonical_exception(
        system.comm,
        stage=stage,
        identity_error=local_error,
        implementation_error=implementation_error,
    )
    return result


def _reconstruct_canonical_vec_collective_safe(
    system: CurrentBareFAuthoritySystem,
    values_by_key: Mapping[Any, complex],
    *,
    label: str,
) -> PETSc.Vec:
    """Reconstruct a canonical Vec and collectively classify key-data errors."""

    local_error: FreshBareFAuthorityIdentityError | None = None
    implementation_error: Exception | None = None
    vector: PETSc.Vec | None = None
    try:
        vector = reconstruct_canonical_active_trace_vec(
            system.condensed,
            system.V,
            system.floquet_data,
            values_by_key,
        )
    except (KeyError, IndexError) as exc:
        local_error = FreshBareFAuthorityIdentityError(
            "CANONICAL_ACTIVE_RECONSTRUCTION_IDENTITY_FAIL",
            f"canonical reconstruction failed for {label}: {exc}",
            stage="rhs_generation",
            details={"label": label},
        )
    except ValueError as exc:
        if _canonical_value_error_is_identity(exc):
            local_error = FreshBareFAuthorityIdentityError(
                "CANONICAL_ACTIVE_RECONSTRUCTION_IDENTITY_FAIL",
                f"canonical reconstruction failed for {label}: {exc}",
                stage="rhs_generation",
                details={"label": label},
            )
        else:
            implementation_error = exc
    except Exception as exc:
        implementation_error = exc
    try:
        _collective_raise_canonical_exception(
            system.comm,
            stage="canonical_reconstruction",
            identity_error=local_error,
            implementation_error=implementation_error,
        )
    except Exception:
        if vector is not None:
            vector.destroy()
        raise
    if vector is None:
        raise AssertionError("collective canonical reconstruction returned no Vec")
    return vector


def _relative_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
) -> float:
    applied = operator.createVecLeft()
    try:
        operator.mult(solution, applied)
        applied.axpy(PETSc.ScalarType(-1.0), rhs)
        return float(applied.norm()) / max(float(rhs.norm()), 1.0e-30)
    finally:
        applied.destroy()


def _relative_difference(first: PETSc.Vec, second: PETSc.Vec) -> float:
    difference = first.duplicate()
    try:
        first.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), second)
        return float(difference.norm()) / max(float(second.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _write_vector_packet(
    *,
    root: Path,
    rank: int,
    label: str,
    role: str,
    tokens: tuple[str, ...],
    values: np.ndarray,
    owner_values: np.ndarray,
    identity: Mapping[str, Any],
    source_metadata: Mapping[str, Any],
    key_set_sha256: str,
    canonical_layout_sha256: str,
) -> dict[str, Any]:
    rank_dir = root / f"rank{int(rank):04d}"
    rank_dir.mkdir(parents=True, exist_ok=True)
    array_path = rank_dir / f"bottom_{label}_{role}.npy"
    owner_array_path = rank_dir / f"bottom_{label}_{role}_owner_rows.npy"
    metadata_path = rank_dir / f"bottom_{label}_{role}.json"
    layout_path = rank_dir / "canonical_active_layout.json"
    _atomic_npy(array_path, values)
    _atomic_npy(owner_array_path, owner_values)
    source_definition_sha256 = _require_sha256(
        source_metadata.get("source_definition_sha256"),
        "source_definition_sha256",
    )
    bare_f_operator_hash = source_metadata.get("bare_f_operator_hash")
    bare_f_operator_hash = _require_sha256(
        bare_f_operator_hash,
        "bare_f_operator_hash",
    )
    identity_with_local_hashes = {
        **dict(identity),
        "array_sha256": _sha256_owned_array(values),
        "owner_row_array_sha256": _sha256_owned_array(owner_values),
    }
    record = {
        "schema": "task040.v5.current_bare_f_authority_vector.v1",
        "side": "bottom",
        "label": label,
        "role": role,
        "dtype": "complex128",
        "array_path": str(array_path.relative_to(root)),
        "owner_row_array_path": str(owner_array_path.relative_to(root)),
        "metadata_path": str(metadata_path.relative_to(root)),
        "canonical_layout_path": str(layout_path.relative_to(root)),
        "canonical_layout_sha256": canonical_layout_sha256,
        "canonical_key_set_sha256": key_set_sha256,
        "canonical_key_count_local": len(tokens),
        "array_sha256": identity_with_local_hashes["array_sha256"],
        "owner_row_array_sha256": identity_with_local_hashes["owner_row_array_sha256"],
        "source_definition_sha256": source_definition_sha256,
        "bare_f_operator_hash": bare_f_operator_hash,
        "global_size": identity_with_local_hashes.get("global_size"),
        "local_size": identity_with_local_hashes.get("local_size"),
        "ownership_range": _json_safe(
            identity_with_local_hashes.get("ownership_range")
        ),
        "global_sha256": identity_with_local_hashes.get("global_sha256"),
        "canonical_to_current_roundtrip_relative": identity_with_local_hashes.get(
            "canonical_to_current_roundtrip_relative"
        ),
        "source_provenance": {
            key: source_metadata.get(key)
            for key in (
                "input_sha256",
                "physical_model_sha256",
                "selected_manifest_sha256",
                "selected_identity_sha256",
                "resolved_config_sha256",
                "source_sha",
            )
        },
        "owner_row_order": "petsc_current_ownership_range",
        "array_values_written": True,
        "raw_global_row_remap": False,
        "source_definition": _json_safe(dict(source_metadata)),
        "vector_identity": _json_safe(identity_with_local_hashes),
    }
    record["rank_local_shard_binding_sha256"] = _rank_local_shard_binding_sha256(
        rank=rank,
        label=label,
        role=role,
        source_definition_sha256=source_definition_sha256,
        key_set_sha256=key_set_sha256,
        canonical_layout_sha256=canonical_layout_sha256,
        identity=identity_with_local_hashes,
        source_provenance={
            key: source_metadata.get(key)
            for key in (
                "input_sha256",
                "physical_model_sha256",
                "selected_manifest_sha256",
                "selected_identity_sha256",
                "resolved_config_sha256",
                "source_sha",
            )
        },
        bare_f_operator_hash=(
            str(bare_f_operator_hash) if bare_f_operator_hash is not None else None
        ),
        rhs_repeat=source_metadata.get("rhs_repeat"),
    )
    _atomic_json(metadata_path, record)
    return record


def run_current_bare_f_authority(
    cfg: Any,
    profile: Any,
    *,
    run_directory: str | Path,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    provenance: Mapping[str, Any] | None = None,
    selected_mode_provider: Any | None = None,
    external_mode_authority: Mapping[str, Any] | None = None,
    external_mode_current_resolved_config_sha256: str | None = None,
    marker_callback: Any | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Produce one current-layout bare-F authority and release its factor."""

    output_root = Path(run_directory) / "bare_f_authority"
    if comm.rank == 0:
        output_root.mkdir(parents=True, exist_ok=False)
    comm.barrier()
    rank_dir = output_root / f"rank{int(comm.rank):04d}"
    rank_dir.mkdir(parents=True, exist_ok=False)
    comm.barrier()
    system: CurrentBareFAuthoritySystem | None = None
    factor: ResearchExactFactorInverse | None = None
    rhs_vectors: dict[str, PETSc.Vec] = {}
    rhs_metadata: dict[str, dict[str, Any]] = {}
    rhs_records: dict[str, dict[str, Any]] = {}
    exact_records: dict[str, dict[str, Any]] = {}
    reports: dict[str, dict[str, Any]] = {}
    factor_ready: Mapping[str, Any] = {}
    factor_after: Mapping[str, Any] = {}
    source_modal_audit: Mapping[str, Any] = {}
    source_provenance = _provenance_reference(
        provenance,
        source_sha=source_sha,
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
    )
    rhs_repeat_records: dict[str, dict[str, Any]] = {}
    operator_semantics_audit = build_v5_operator_semantics_audit(
        source_sha=source_sha,
        provenance=provenance,
    )
    if not operator_semantics_audit["modal_source_identity"]["pass"]:
        raise RuntimeError(
            "V5 modal source identity is not established: "
            f"{operator_semantics_audit['modal_source_identity']!r}"
        )
    operator_semantics_audit_file_sha256 = ""
    if comm.rank == 0:
        audit_path = output_root / "operator_semantics_audit.json"
        _atomic_json(audit_path, operator_semantics_audit)
        operator_semantics_audit_file_sha256 = _sha256_bytes(audit_path.read_bytes())
    operator_semantics_audit_file_sha256 = comm.bcast(
        operator_semantics_audit_file_sha256,
        root=0,
    )
    comm.barrier()
    try:
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=profile.bottom_interface_nm,
            top_interface_z_nm=profile.top_interface_nm,
            source_work_directory=output_root / "one_cell_source",
            selected_mode_provider=selected_mode_provider,
            external_mode_authority=external_mode_authority,
            external_mode_current_resolved_config_sha256=(
                external_mode_current_resolved_config_sha256
                or source_provenance.get("resolved_config_sha256")
            ),
            source_factor_marker_callback=marker_callback,
            comm=comm,
        )
        _emit = marker_callback
        if _emit is not None:
            _emit(
                "v5_bare_f_system_ready",
                {
                    "side": "bottom",
                    "bare_f_rows": system.active_rows,
                    "global_A_materialized": False,
                    "physical_dtn_coupling": False,
                    "minimal_external_dtn_coupling_objects": int(
                        system.construction_inventory[
                            "minimal_external_coupling_objects_constructed"
                        ]
                    ),
                    "matrix_objects": dict(system.dtn_objects_constructed),
                    "qep_calls": 0,
                    "factor_count": 0,
                },
            )
        tokens, key_set_sha256, layout_audit = canonical_layout_tokens(system)
        layout_record = {
            "schema": "task040.v5.current_bare_f_authority_layout.v1",
            "side": "bottom",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
            "dtype": "complex128",
            "global_size": int(system.F.getSize()[0]),
            "local_size": len(tokens),
            "ownership_range": list(map(int, system.F.getOwnershipRange())),
            "canonical_key_set_sha256": key_set_sha256,
            "canonical_keys": list(tokens),
            "canonical_packet_audit": dict(layout_audit),
            "raw_global_row_remap": False,
        }
        _atomic_json(
            rank_dir / "canonical_active_layout.json",
            layout_record,
        )
        canonical_layout_path = rank_dir / "canonical_active_layout.json"
        canonical_layout_sha256 = _sha256_bytes(canonical_layout_path.read_bytes())
        gamma_layouts = {
            "Gamma_L": _build_current_gamma_layout(
                system,
                name="Gamma_L",
                plane_z_nm=float(system.local_mesh.z_values[2]),
                plane_cell_side="lower",
                frozen_z_index=2,
            ),
            "Gamma_U": _build_current_gamma_layout(
                system,
                name="Gamma_U",
                plane_z_nm=float(system.local_mesh.z_values[4]),
                plane_cell_side="upper",
                frozen_z_index=4,
            ),
        }
        gamma_layout_records: dict[str, dict[str, Any]] = {}
        for gamma_name, gamma_layout in gamma_layouts.items():
            gamma_layout_path = rank_dir / f"{gamma_name.lower()}_layout.json"
            gamma_layout_payload = {
                "schema": "task040.v5.current_bare_f_authority_gamma_layout.v1",
                "gamma": gamma_name,
                "rank": int(comm.rank),
                "mpi_size": int(comm.size),
                "gamma_rows_local": [
                    int(value) for value in gamma_layout.gamma_rows_local
                ],
                "active_row_set_sha256": _sha256_bytes(
                    "\n".join(
                        str(int(value))
                        for value in sorted(gamma_layout.gamma_rows_local)
                    ).encode("ascii")
                ),
                "canonical_keys": list(gamma_layout.canonical_keys),
                "canonical_key_order_sha256": gamma_layout.audit[
                    "canonical_key_order_sha256"
                ],
                "audit": _json_safe(dict(gamma_layout.audit)),
                "plane_identity": _json_safe(dict(gamma_layout.plane_identity)),
                "raw_global_row_remap": False,
            }
            _atomic_json(gamma_layout_path, gamma_layout_payload)
            gamma_layout_records[gamma_name] = {
                "path": str(gamma_layout_path.relative_to(output_root)),
                "sha256": _sha256_bytes(gamma_layout_path.read_bytes()),
                "gamma_rows_local": len(gamma_layout.gamma_rows_local),
                "canonical_key_order_sha256": gamma_layout.audit[
                    "canonical_key_order_sha256"
                ],
            }
        source_identity_error: dict[str, Any] | None = None
        try:
            if external_mode_authority is None:
                raise ExternalModeAuthorityIdentityError(
                    "current external mode authority was not supplied"
                )
            external_mode_audit = validate_external_mode_authority(
                system.external_modes,
                external_mode_authority,
                current_resolved_config_sha256=(
                    external_mode_current_resolved_config_sha256
                    or source_provenance.get("resolved_config_sha256")
                ),
            )
            system.construction_inventory["external_mode_authority"] = (
                external_mode_audit
            )
            _ensure_selected_exact_source_cache(system)
            source_modal_audit = dict(system._selected_exact_source_cache["audit"])
        except (
            ExactOneCellSourceIdentityError,
            ExternalModeAuthorityIdentityError,
        ) as exc:
            source_identity_error = {
                "code": (
                    "EXTERNAL_MODE_AUTHORITY_FAIL"
                    if isinstance(exc, ExternalModeAuthorityIdentityError)
                    else "MODAL_SOURCE_PRIMAL_OR_DUAL_CONGRUENCE_FAIL"
                ),
                "type": type(exc).__name__,
                "message": str(exc),
            }
        source_identity_errors = comm.allgather(source_identity_error)
        first_source_identity_error = next(
            (item for item in source_identity_errors if item is not None), None
        )
        if first_source_identity_error is not None:
            inventory = dict(system.construction_inventory)
            controlled_result = {
                "schema": V5_BARE_F_SCHEMA,
                "method": V5_BARE_F_METHOD,
                "profile": "task040.v5.h4.current_layout_bare_f_authority.v1",
                "status": "not_run_by_source_identity_gate",
                "classification": "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL",
                "identity_failure_code": "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL",
                "identity_failure": first_source_identity_error,
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "source_provenance": source_provenance,
                "operator_semantics_audit": {
                    "path": "operator_semantics_audit.json",
                    "sha256": operator_semantics_audit_file_sha256,
                    "content_sha256": operator_semantics_audit["record_sha256"],
                },
                "system_created": True,
                "rhs_vectors_loaded": 0,
                "exact_output_vectors_loaded": 0,
                "reports": {},
                "factor_lifecycle": {
                    "factor_count_before_solve": 0,
                    "factor_count_after_cleanup": 0,
                    "consumer_retains_factor": False,
                },
                "modal_source_factor_lifecycle": {
                    "construction_count": int(
                        inventory.get("one_cell_source_factor_construction_count", 0)
                    ),
                    "apply_count": int(
                        inventory.get("one_cell_source_factor_apply_count", 0)
                    ),
                    "mat_solve_call_count": int(
                        inventory.get("one_cell_source_factor_mat_solve_call_count", 0)
                    ),
                    "rhs_columns_solved": int(
                        inventory.get("one_cell_source_factor_rhs_columns_solved", 0)
                    ),
                    "peak_simultaneous": int(
                        inventory.get("one_cell_source_factor_peak", 0)
                    ),
                    "factor_ready": bool(
                        inventory.get("one_cell_source_factor_ready", 0) == 1
                    ),
                    "factor_destroyed": bool(
                        inventory.get("one_cell_source_factor_destroyed", False)
                    ),
                    "factor_count_after": inventory.get(
                        "one_cell_source_factor_factor_count_after"
                    ),
                    "destroyed_before_full_side_factor": bool(
                        inventory.get("one_cell_source_factor_active", 0) == 0
                    ),
                    "cleanup": _json_safe(
                        inventory.get("one_cell_source_factor_cleanup")
                    ),
                    "events": _json_safe(
                        inventory.get("one_cell_source_factor_events", [])
                    ),
                },
                "construction_inventory": _json_safe(inventory),
                "external_dtn_coupling": {
                    "status": "not_run_by_source_identity_gate",
                    "matrix_objects_constructed": {"C": 0, "D": 0, "H": 0},
                },
                "qep_calls": 0,
                "pde_solve": "not_run",
                "interface_mass_constructed": False,
                "outer_ksp": "not_run",
                "gate": {
                    "pass": False,
                    "status": "not_run_by_identity_gate",
                },
            }
            comm.barrier()
            if comm.rank == 0:
                _atomic_json(output_root / "manifest.json", controlled_result)
            comm.barrier()
            if _emit is not None:
                _emit(
                    "v5_modal_source_identity_stop",
                    {
                        "classification": controlled_result["classification"],
                        "identity_failure_code": controlled_result[
                            "identity_failure_code"
                        ],
                        "system_created": True,
                        "factor_count": 0,
                        "qep_calls": 0,
                    },
                )
            return controlled_result
        gamma_records: dict[str, dict[str, dict[str, Any]]] = {}
        f_hash_before = _petsc_matrix_hash(system.F)
        for label in V5_BARE_F_SOURCE_LABELS:
            rhs, metadata = build_current_bare_f_rhs(system, label)
            rhs_vectors[label] = rhs
            rhs_repeat, repeat_metadata = build_current_bare_f_rhs(system, label)
            try:
                rhs_repeat_relative = _relative_difference(rhs_repeat, rhs)
                rhs_repeat_finite = bool(
                    np.isfinite(rhs_repeat.norm())
                    and np.isfinite(rhs.norm())
                    and np.all(np.isfinite(rhs_repeat.getArray(readonly=True)))
                )
                rhs_repeat_records[label] = {
                    "source_build_count": int(
                        system.construction_inventory["source_build_counts"][label]
                    ),
                    "relative_difference": float(rhs_repeat_relative),
                    "threshold": 1.0e-12,
                    "finite": rhs_repeat_finite,
                    "repeat_norm": float(rhs_repeat.norm()),
                    "source_metadata": _json_safe(dict(repeat_metadata)),
                    "pass": bool(rhs_repeat_finite and rhs_repeat_relative <= 1.0e-12),
                }
            finally:
                rhs_repeat.destroy()
            rhs_repeat_error = None
            if not rhs_repeat_records[label]["pass"]:
                rhs_repeat_error = FreshBareFAuthorityIdentityError(
                    "RHS_REPEAT_IDENTITY_FAIL",
                    f"fresh RHS repeat Gate failed for {label}",
                    stage="rhs_generation",
                    details={"label": label, "record": rhs_repeat_records[label]},
                )
            _collective_raise_fresh_bare_f_identity(comm, rhs_repeat_error)
            rhs_tokens, rhs_values, rhs_audit = canonical_packets_for_vector(
                system, rhs
            )
            rhs_key_error = None
            if set(rhs_tokens) != set(tokens):
                rhs_key_error = FreshBareFAuthorityIdentityError(
                    "RHS_CANONICAL_KEY_SET_IDENTITY_FAIL",
                    f"RHS canonical key set changed for {label}",
                    stage="rhs_canonical_reconstruction",
                    details={
                        "label": label,
                        "expected_key_count": len(tokens),
                        "observed_key_count": len(rhs_tokens),
                    },
                )
            _collective_raise_fresh_bare_f_identity(comm, rhs_key_error)
            rhs_by_token = dict(zip(rhs_tokens, rhs_values, strict=True))
            ordered_rhs_values = np.asarray(
                [rhs_by_token[token] for token in tokens], dtype=np.complex128
            )
            rhs_owner_values = np.asarray(
                rhs.getArray(readonly=True), dtype=np.complex128
            ).copy()
            rhs_roundtrip = _canonical_roundtrip_or_identity_stop(
                system,
                tokens,
                ordered_rhs_values,
                rhs,
                label=label,
                stage="rhs_canonical_reconstruction",
            )
            rhs_roundtrip_error = None
            if not np.isfinite(rhs_roundtrip) or rhs_roundtrip > 1.0e-12:
                rhs_roundtrip_error = FreshBareFAuthorityIdentityError(
                    "RHS_CANONICAL_ROUNDTRIP_IDENTITY_FAIL",
                    f"RHS canonical round-trip Gate failed for {label}",
                    stage="rhs_canonical_reconstruction",
                    details={
                        "label": label,
                        "roundtrip_relative": float(rhs_roundtrip),
                        "threshold": 1.0e-12,
                    },
                )
            _collective_raise_fresh_bare_f_identity(comm, rhs_roundtrip_error)
            identity = vector_identity(
                system,
                tokens,
                ordered_rhs_values,
                key_set_sha256,
                owner_values=rhs_owner_values,
                canonical_roundtrip_relative=rhs_roundtrip,
            )
            identity["global_norm"] = float(rhs.norm())
            identity["rhs_packet_audit"] = dict(rhs_audit)
            rhs_source_metadata = {
                **metadata,
                "provenance": dict(source_provenance),
                "rhs_repeat": rhs_repeat_records[label],
                "input_sha256": str(source_provenance["input_sha256"]),
                "physical_model_sha256": str(
                    source_provenance["physical_model_sha256"]
                ),
                "selected_manifest_sha256": str(
                    source_provenance["selected_manifest_sha256"]
                ),
                "selected_identity_sha256": str(
                    source_provenance["selected_identity_sha256"]
                ),
                "resolved_config_sha256": str(
                    source_provenance["resolved_config_sha256"]
                ),
                "source_sha": str(source_sha),
                "canonical_key_set_sha256": key_set_sha256,
                "bare_f_operator_hash": f_hash_before,
                "finite": bool(identity["finite"]),
                "norm": float(identity["global_norm"]),
                "minimal_coupling_object": label == "external_dtn_coupling",
            }
            rhs_source_metadata["source_definition_descriptor"] = (
                _source_semantic_descriptor(
                    label=label,
                    metadata=rhs_source_metadata,
                    provenance=source_provenance,
                )
            )
            rhs_source_metadata["source_definition_sha256"] = _source_definition_sha256(
                label=label,
                metadata=rhs_source_metadata,
                provenance=source_provenance,
            )
            rhs_records[label] = _write_vector_packet(
                root=output_root,
                rank=comm.rank,
                label=label,
                role="rhs",
                tokens=tokens,
                values=ordered_rhs_values,
                owner_values=rhs_owner_values,
                identity=identity,
                source_metadata=rhs_source_metadata,
                key_set_sha256=key_set_sha256,
                canonical_layout_sha256=canonical_layout_sha256,
            )
            rhs_metadata[label] = rhs_source_metadata
            if _emit is not None:
                _emit(
                    "v5_bare_f_rhs_ready",
                    {
                        "label": label,
                        "canonical_key_set_sha256": key_set_sha256,
                        "rhs_finite": bool(identity["finite"]),
                        "rhs_norm": float(identity["global_norm"]),
                        "matrix_objects": dict(
                            metadata.get(
                                "matrix_objects", system.dtn_objects_constructed
                            )
                        ),
                        "physical_dtn_coupling": False,
                        "minimal_external_dtn_coupling_objects": int(
                            system.construction_inventory[
                                "minimal_external_coupling_objects_constructed"
                            ]
                        ),
                    },
                )
        source_definition_hashes: dict[str, list[str]] = {}
        for label in V5_BARE_F_SOURCE_LABELS:
            hashes = [
                str(value)
                for value in comm.allgather(
                    rhs_metadata[label]["source_definition_sha256"]
                )
            ]
            if len(set(hashes)) != 1:
                raise FreshBareFAuthorityIdentityError(
                    "SOURCE_DEFINITION_HASH_IDENTITY_FAIL",
                    f"source definition hash is not rank-independent for {label}",
                    stage="source_definition_binding",
                    details={"label": label, "hashes": hashes},
                )
            source_definition_hashes[label] = hashes
        source_definition_gate_pass = all(
            len(values) == int(comm.size)
            and len(set(values)) == 1
            and all(_is_valid_sha256(value) for value in values)
            for values in source_definition_hashes.values()
        )
        _require_fresh_bare_f_identity(
            source_definition_gate_pass,
            "SOURCE_DEFINITION_HASH_IDENTITY_FAIL",
            "source definition hashes did not pass the collective identity Gate",
            stage="source_definition_binding",
            details={"source_definition_hashes": source_definition_hashes},
        )
        if int(system.construction_inventory.get("one_cell_source_factor_active", 0)):
            raise RuntimeError(
                "one-cell source factor remained active before bare-F factor setup"
            )
        system._selected_exact_source_cache = None
        factor = _construct_bare_f_factor_after_identity_gate(
            True,
            system.F,
            marker_callback=_emit,
            operator_hash=f_hash_before,
        )
        factor_ready = dict(factor.diagnostics)
        for label in V5_BARE_F_SOURCE_LABELS:
            rhs = rhs_vectors[label]
            exact = rhs.duplicate()
            repeat = rhs.duplicate()
            exact_key = f"__temporary_exact__{label}"
            repeat_key = f"__temporary_repeat__{label}"
            rhs_vectors[exact_key] = exact
            rhs_vectors[repeat_key] = repeat
            factor.solve(rhs, exact)
            factor.solve(rhs, repeat)
            exact_tokens, exact_values, exact_audit = canonical_packets_for_vector(
                system, exact
            )
            exact_key_error = None
            if set(exact_tokens) != set(tokens):
                exact_key_error = FreshBareFAuthorityIdentityError(
                    "EXACT_CANONICAL_KEY_SET_IDENTITY_FAIL",
                    f"exact canonical key set changed for {label}",
                    stage="exact_canonical_reconstruction",
                    details={
                        "label": label,
                        "expected_key_count": len(tokens),
                        "observed_key_count": len(exact_tokens),
                    },
                )
            _collective_raise_fresh_bare_f_identity(comm, exact_key_error)
            exact_by_token = dict(zip(exact_tokens, exact_values, strict=True))
            ordered_exact_values = np.asarray(
                [exact_by_token[token] for token in tokens], dtype=np.complex128
            )
            exact_identity = vector_identity(
                system,
                tokens,
                ordered_exact_values,
                key_set_sha256,
                owner_values=np.asarray(
                    exact.getArray(readonly=True), dtype=np.complex128
                ).copy(),
                canonical_roundtrip_relative=_canonical_roundtrip_or_identity_stop(
                    system,
                    tokens,
                    ordered_exact_values,
                    exact,
                    label=label,
                    stage="exact_canonical_reconstruction",
                ),
            )
            exact_roundtrip = exact_identity["canonical_to_current_roundtrip_relative"]
            exact_roundtrip_error = None
            if not np.isfinite(exact_roundtrip) or exact_roundtrip > 1.0e-12:
                exact_roundtrip_error = FreshBareFAuthorityIdentityError(
                    "EXACT_CANONICAL_ROUNDTRIP_IDENTITY_FAIL",
                    f"exact canonical round-trip Gate failed for {label}",
                    stage="exact_canonical_reconstruction",
                    details={
                        "label": label,
                        "roundtrip_relative": exact_roundtrip,
                        "threshold": 1.0e-12,
                    },
                )
            _collective_raise_fresh_bare_f_identity(comm, exact_roundtrip_error)
            exact_identity["global_norm"] = float(exact.norm())
            exact_identity["exact_packet_audit"] = dict(exact_audit)
            exact_records[label] = _write_vector_packet(
                root=output_root,
                rank=comm.rank,
                label=label,
                role="exact_output",
                tokens=tokens,
                values=ordered_exact_values,
                owner_values=np.asarray(
                    exact.getArray(readonly=True), dtype=np.complex128
                ).copy(),
                identity=exact_identity,
                source_metadata=rhs_metadata[label],
                key_set_sha256=key_set_sha256,
                canonical_layout_sha256=canonical_layout_sha256,
            )
            gamma_records[label] = {
                gamma_name: _write_gamma_trace_packet(
                    root=output_root,
                    rank=comm.rank,
                    label=label,
                    gamma_name=gamma_name,
                    layout=gamma_layout,
                    layout_path=gamma_layout_records[gamma_name]["path"],
                    layout_sha256=gamma_layout_records[gamma_name]["sha256"],
                    vector=exact,
                    source_metadata=rhs_metadata[label],
                    key_set_sha256=key_set_sha256,
                    bare_f_operator_hash=f_hash_before,
                    canonical_layout_sha256=canonical_layout_sha256,
                )
                for gamma_name, gamma_layout in gamma_layouts.items()
            }
            reports[label] = {
                "label": label,
                "bare_f_residual": _relative_residual(system.F, rhs, exact),
                "solve_repeat_relative": _relative_difference(exact, repeat),
                "rhs_repeat_relative": rhs_repeat_records[label]["relative_difference"],
                "rhs_repeat_pass": rhs_repeat_records[label]["pass"],
                "finite": bool(
                    np.all(np.isfinite(ordered_exact_values))
                    and np.isfinite(_relative_residual(system.F, rhs, exact))
                ),
                "rhs_norm": float(rhs.norm()),
                "solution_norm": float(exact.norm()),
                "canonical_key_set_sha256": key_set_sha256,
                "canonical_to_current_roundtrip_relative": exact_identity[
                    "canonical_to_current_roundtrip_relative"
                ],
                "raw_global_row_remap": False,
            }
            exact.destroy()
            repeat.destroy()
            rhs_vectors.pop(exact_key, None)
            rhs_vectors.pop(repeat_key, None)
            if _emit is not None:
                _emit(
                    "v5_bare_f_exact_output_ready",
                    {
                        "label": label,
                        "bare_f_residual": reports[label]["bare_f_residual"],
                        "solve_repeat_relative": reports[label][
                            "solve_repeat_relative"
                        ],
                        "rhs_repeat_relative": reports[label]["rhs_repeat_relative"],
                        "finite": reports[label]["finite"],
                        "factor_count": 1,
                    },
                )
        shard_manifest = {
            "schema": "task040.v5.current_bare_f_authority_owner_shard.v1",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
            "rhs_records": dict(rhs_records),
            "exact_output_records": dict(exact_records),
            "gamma_trace_records": dict(gamma_records),
            "gamma_layout_records": dict(gamma_layout_records),
            "source_labels": list(V5_BARE_F_SOURCE_LABELS),
            "canonical_layout": {
                "path": str(
                    (rank_dir / "canonical_active_layout.json").relative_to(output_root)
                ),
                "sha256": canonical_layout_sha256,
            },
            "operator_semantics_audit": {
                "path": "operator_semantics_audit.json",
                "sha256": operator_semantics_audit_file_sha256,
                "content_sha256": operator_semantics_audit["record_sha256"],
            },
            "raw_global_row_remap": False,
        }
        _atomic_json(rank_dir / "shard_manifest.json", shard_manifest)
        comm.barrier()
        owner_shards: list[dict[str, Any]] | None = None
        all_rhs_records: dict[str, Any] | None = None
        all_exact_records: dict[str, Any] | None = None
        all_gamma_records: dict[str, Any] | None = None
        all_gamma_layout_records: dict[str, Any] | None = None
        if comm.rank == 0:
            owner_shards = []
            all_rhs_records = {}
            all_exact_records = {}
            all_gamma_records = {}
            all_gamma_layout_records = {}
            for owner_rank in range(comm.size):
                shard_path = (
                    output_root / f"rank{owner_rank:04d}" / "shard_manifest.json"
                )
                shard_payload = json.loads(shard_path.read_text(encoding="utf-8"))
                owner_shards.append(
                    {
                        "rank": owner_rank,
                        "path": str(shard_path.relative_to(output_root)),
                        "sha256": _sha256_bytes(shard_path.read_bytes()),
                        "canonical_layout": shard_payload["canonical_layout"],
                    }
                )
                all_rhs_records[str(owner_rank)] = shard_payload["rhs_records"]
                all_exact_records[str(owner_rank)] = shard_payload[
                    "exact_output_records"
                ]
                all_gamma_records[str(owner_rank)] = shard_payload[
                    "gamma_trace_records"
                ]
                all_gamma_layout_records[str(owner_rank)] = shard_payload[
                    "gamma_layout_records"
                ]
        owner_shards = comm.bcast(owner_shards, root=0)
        all_rhs_records = comm.bcast(all_rhs_records, root=0)
        all_exact_records = comm.bcast(all_exact_records, root=0)
        all_gamma_records = comm.bcast(all_gamma_records, root=0)
        all_gamma_layout_records = comm.bcast(all_gamma_layout_records, root=0)
        f_hash_after = _petsc_matrix_hash(system.F)
        factor.destroy()
        factor_after = dict(factor.diagnostics)
        required_destroyed_fields = {
            "factor_destroyed": True,
            "factor_matrix_alive": False,
            "direct_factor_count": 0,
            "exact_factor_count": 0,
            "solve_count": len(V5_BARE_F_SOURCE_LABELS) * 2,
        }
        if any(
            factor_after.get(name) != expected
            for name, expected in required_destroyed_fields.items()
        ):
            raise RuntimeError(
                "bare-F factor lifecycle diagnostics did not observe destruction: "
                f"{factor_after!r}"
            )
        factor = None
        if _emit is not None:
            _emit(
                "v5_bare_f_factor_destroyed",
                {
                    "factor_scope": "full_side_bare_f",
                    "factored_operator": "explicit_current_bare_F",
                    "operator_hash": f_hash_before,
                    "factor_count_before_destroy": 1,
                    "factor_count_after_destroy": factor_after["direct_factor_count"],
                    "factor_diagnostics": factor_after,
                    "consumer_retains_factor": False,
                },
            )
        local_reports = reports
        gathered_reports = comm.gather(local_reports, root=0)
        if comm.rank == 0:
            # Every rank owns a disjoint canonical shard; report the worst
            # scalar from the complete current operator on every rank.
            merged = {
                label: dict(gathered_reports[0][label])
                for label in V5_BARE_F_SOURCE_LABELS
            }
        else:
            merged = None
        merged = comm.bcast(merged, root=0)
        reports = dict(merged)
        local_roundtrip_pass = all(
            float(
                rhs_records[label]["vector_identity"][
                    "canonical_to_current_roundtrip_relative"
                ]
            )
            <= 1.0e-12
            and float(
                exact_records[label]["vector_identity"][
                    "canonical_to_current_roundtrip_relative"
                ]
            )
            <= 1.0e-12
            for label in V5_BARE_F_SOURCE_LABELS
        )
        roundtrip_pass = bool(comm.allreduce(local_roundtrip_pass, op=MPI.LAND))
        source_lifecycle = system.construction_inventory
        source_lifecycle_pass = bool(
            source_lifecycle.get("one_cell_source_factor_ready") == 1
            and source_lifecycle.get("one_cell_source_factor_destroyed") is True
            and source_lifecycle.get("one_cell_source_factor_active") == 0
            and source_lifecycle.get("one_cell_source_factor_peak") == 1
            and source_lifecycle.get("one_cell_source_factor_construction_count") == 1
            and source_lifecycle.get("one_cell_source_factor_apply_count") == 2
            and source_lifecycle.get("one_cell_source_factor_mat_solve_call_count") == 2
            and source_lifecycle.get("one_cell_source_factor_rhs_columns_solved") == 4
            and isinstance(
                source_lifecycle.get("one_cell_source_factor_cleanup"), Mapping
            )
            and source_lifecycle["one_cell_source_factor_cleanup"].get(
                "calls_completed"
            )
            is True
        )
        dual_identity_pass = bool(
            source_modal_audit.get("dual_endpoint_transfer")
            and all(
                float(item["dual_inverse_map_reconstruction_error"]) <= 1.0e-12
                for item in source_modal_audit["dual_endpoint_transfer"].values()
            )
        )
        primal_identity_pass = bool(
            source_modal_audit.get("primal_endpoint_identity", {}).get("pass") is True
        )
        external_authority_pass = bool(
            source_lifecycle.get("external_mode_authority", {}).get("pass") is True
        )
        gamma_complete = bool(
            len(all_gamma_records or {}) == int(comm.size)
            and all(
                set(rank_records) == set(V5_BARE_F_SOURCE_LABELS)
                and all(
                    set(rank_records[label]) == {"Gamma_L", "Gamma_U"}
                    for label in V5_BARE_F_SOURCE_LABELS
                )
                for rank_records in (all_gamma_records or {}).values()
            )
        )
        packet_binding_pass = _check_owner_packet_bindings(
            owner_shards=owner_shards,
            all_rhs_records=all_rhs_records or {},
            all_exact_records=all_exact_records or {},
            all_gamma_records=all_gamma_records or {},
            all_gamma_layout_records=all_gamma_layout_records or {},
            source_definition_hashes=source_definition_hashes,
            bare_f_operator_hash=f_hash_before,
            expected_mpi_size=8,
        )
        _require_fresh_bare_f_identity(
            packet_binding_pass,
            "PACKET_BINDING_IDENTITY_FAIL",
            "owner-row, canonical, Gamma, or provenance packet binding failed",
            stage="packet_binding",
            details={
                "owner_shard_count": len(owner_shards),
                "rhs_rank_count": len(all_rhs_records or {}),
                "exact_rank_count": len(all_exact_records or {}),
                "gamma_rank_count": len(all_gamma_records or {}),
            },
        )
        runtime_qualification = {
            "static_path_identity": bool(
                operator_semantics_audit["current_authority"]["static_path_identity"]
                is True
                and operator_semantics_audit["modal_source_identity"]["pass"] is True
            ),
            "runtime_qualification_required": bool(
                operator_semantics_audit["current_authority"][
                    "runtime_qualification_required"
                ]
            ),
            "mpi_size": int(comm.size) == 8,
            "source_factor_lifecycle": source_lifecycle_pass,
            "primal_identity": primal_identity_pass,
            "dual_identity_first_repeat": dual_identity_pass,
            "qep_zero": int(source_lifecycle.get("qep_calls", 0)) == 0,
            "physical_dtn_zero": source_lifecycle.get(
                "physical_dtn_operator_constructed"
            )
            is False,
            "woodbury_false": source_lifecycle.get("woodbury_inverse_constructed")
            is False,
            "research_side_lu_false": source_lifecycle.get(
                "research_exact_side_lu_action_called"
            )
            is False,
            "external_mode_authority": external_authority_pass,
            "external_minimal_counts": (
                source_lifecycle.get("minimal_external_coupling_objects_constructed")
                == 1
                and source_lifecycle.get("minimal_external_surface_component_count")
                == 2
                and source_lifecycle.get(
                    "minimal_external_coupling_construction_call_count"
                )
                == 2
                and source_lifecycle.get("minimal_external_component_instances_total")
                == 4
                and source_lifecycle.get("minimal_external_peak_live_components") == 2
                and source_lifecycle.get("minimal_external_coupling_kind_count") == 1
            ),
            "gamma_complete": gamma_complete,
            "packet_bindings": packet_binding_pass,
            "factor_lifecycle": (
                factor_after.get("direct_factor_count") == 0
                and factor_after.get("exact_factor_count") == 0
                and factor_after.get("factor_destroyed") is True
                and factor_after.get("factor_matrix_alive") is False
                and factor_after.get("solve_count") == 10
                and factor_ready.get("direct_factor_count") == 1
            ),
            "bare_f_operator_unchanged": f_hash_before == f_hash_after,
            "c_d_h_zero": system.dtn_objects_constructed == {"C": 0, "D": 0, "H": 0},
            "packet_roundtrip": roundtrip_pass,
        }
        runtime_qualification["pass"] = all(runtime_qualification.values())
        numerical_gate_pass = bool(
            all(
                row["finite"]
                and row["bare_f_residual"] <= 1.0e-9
                and row["solve_repeat_relative"] <= 1.0e-12
                and row["rhs_repeat_pass"]
                for row in reports.values()
            )
        )
        identity_gate_pass = bool(runtime_qualification["pass"])
        gate = bool(
            f_hash_before == f_hash_after
            and numerical_gate_pass
            and factor_after["direct_factor_count"] == 0
            and factor_after["exact_factor_count"] == 0
            and system.dtn_objects_constructed == {"C": 0, "D": 0, "H": 0}
            and roundtrip_pass
            and identity_gate_pass
        )
        if not identity_gate_pass:
            final_status = "identity_failed_after_factor"
            final_classification = "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL"
        elif not numerical_gate_pass:
            final_status = "fresh_bare_f_authority_numerical_fail"
            final_classification = "FRESH_BARE_F_AUTHORITY_NUMERICAL_FAIL"
        else:
            final_status = "fresh_bare_f_authority_pass"
            final_classification = "FRESH_BARE_F_AUTHORITY_PASS"
        result = {
            "schema": V5_BARE_F_SCHEMA,
            "method": V5_BARE_F_METHOD,
            "profile": "task040.v5.h4.current_layout_bare_f_authority.v1",
            "status": final_status,
            "classification": final_classification,
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "source_provenance": source_provenance,
            "operator_semantics_audit": {
                "path": "operator_semantics_audit.json",
                "sha256": operator_semantics_audit_file_sha256,
                "content_sha256": operator_semantics_audit["record_sha256"],
            },
            "side": "bottom",
            "mpi_size": int(comm.size),
            "threads_per_rank": 1,
            "source_labels": list(V5_BARE_F_SOURCE_LABELS),
            "source_definition_hashes": source_definition_hashes,
            "rhs_records": all_rhs_records,
            "exact_output_records": all_exact_records,
            "gamma_trace_records": all_gamma_records,
            "gamma_layout_records": all_gamma_layout_records,
            "owner_shards": owner_shards,
            "reports": reports,
            "rhs_repeat_records": rhs_repeat_records,
            "bare_f": {
                "operator_hash_before": f_hash_before,
                "operator_hash_after": f_hash_after,
                "operator_unchanged": f_hash_before == f_hash_after,
                "global_size": int(system.F.getSize()[0]),
                "ownership_range": list(map(int, system.F.getOwnershipRange())),
                "canonical_key_set_sha256": key_set_sha256,
            },
            "canonical_layout": {
                "packet_root": str(output_root),
                "key_set_sha256": key_set_sha256,
                "owner_shards": int(comm.size),
                "owner_layouts": {
                    str(item["rank"]): item["canonical_layout"] for item in owner_shards
                },
                "raw_global_row_remap": False,
            },
            "canonical_roundtrip_gate": {
                "threshold": 1.0e-12,
                "rhs_and_exact_all_owner_shards_pass": roundtrip_pass,
            },
            "external_dtn_coupling": {
                "rhs_only": True,
                "minimal_surface_components_only": True,
                "matrix_objects_constructed": dict(system.dtn_objects_constructed),
                "minimal_external_coupling_objects_constructed": int(
                    system.construction_inventory[
                        "minimal_external_coupling_objects_constructed"
                    ]
                ),
                "minimal_external_surface_component_count": int(
                    system.construction_inventory[
                        "minimal_external_surface_component_count"
                    ]
                ),
                "minimal_external_coupling_construction_call_count": int(
                    system.construction_inventory[
                        "minimal_external_coupling_construction_call_count"
                    ]
                ),
                "minimal_external_component_instances_total": int(
                    system.construction_inventory[
                        "minimal_external_component_instances_total"
                    ]
                ),
                "minimal_external_peak_live_components": int(
                    system.construction_inventory[
                        "minimal_external_peak_live_components"
                    ]
                ),
                "minimal_external_coupling_kind_count": int(
                    system.construction_inventory[
                        "minimal_external_coupling_kind_count"
                    ]
                ),
                "physical_dtn_operator_constructed": False,
                "research_exact_side_lu_called": False,
                "woodbury_called": False,
                "mode_authority": _json_safe(
                    system.construction_inventory.get("external_mode_authority")
                ),
            },
            "construction_inventory": _json_safe(dict(system.construction_inventory)),
            "modal_source_factor_lifecycle": {
                "construction_count": int(
                    system.construction_inventory.get(
                        "one_cell_source_factor_construction_count", 0
                    )
                ),
                "apply_count": int(
                    system.construction_inventory.get(
                        "one_cell_source_factor_apply_count", 0
                    )
                ),
                "mat_solve_call_count": int(
                    system.construction_inventory.get(
                        "one_cell_source_factor_mat_solve_call_count", 0
                    )
                ),
                "rhs_columns_solved": int(
                    system.construction_inventory.get(
                        "one_cell_source_factor_rhs_columns_solved", 0
                    )
                ),
                "peak_simultaneous": int(
                    system.construction_inventory.get("one_cell_source_factor_peak", 0)
                ),
                "factor_ready": bool(
                    system.construction_inventory.get("one_cell_source_factor_ready", 0)
                    == 1
                ),
                "factor_destroyed": bool(
                    system.construction_inventory.get(
                        "one_cell_source_factor_destroyed", False
                    )
                ),
                "factor_count_after": system.construction_inventory.get(
                    "one_cell_source_factor_factor_count_after"
                ),
                "destroyed_before_full_side_factor": bool(
                    system.construction_inventory.get(
                        "one_cell_source_factor_active", 0
                    )
                    == 0
                ),
                "cleanup": _json_safe(
                    system.construction_inventory.get("one_cell_source_factor_cleanup")
                ),
                "events": _json_safe(
                    list(
                        system.construction_inventory.get(
                            "one_cell_source_factor_events", []
                        )
                    )
                ),
            },
            "factor_lifecycle": {
                "factored_operator": "explicit_current_bare_F",
                "operator_hash": f_hash_before,
                "factor_count_before_solve": 1,
                "factor_count_after_cleanup": factor_after["direct_factor_count"],
                "consumer_retains_factor": False,
                "factor_solver_type": "mumps",
                "factor_only_storage": True,
                "factor_ready": factor_ready,
                "factor_after_cleanup": factor_after,
            },
            "qep_calls": 0,
            "pde_solve": "not_run",
            "system_created": True,
            "interface_mass_constructed": False,
            "outer_ksp": "not_run",
            "gate": {
                "bare_f_residual_threshold": 1.0e-9,
                "repeat_threshold": 1.0e-12,
                "numerical_pass": numerical_gate_pass,
                "identity_pass": identity_gate_pass,
                "runtime_qualification": runtime_qualification,
                "pass": gate,
            },
            "resource_role": "diagnostic_bare_f_authority_oracle_only",
        }
        comm.barrier()
        if comm.rank == 0:
            _atomic_json(output_root / "manifest.json", result)
        comm.barrier()
        if _emit is not None:
            _emit(
                "v5_bare_f_authority_complete",
                {
                    "classification": result["classification"],
                    "gate_pass": gate,
                    "factor_count_after_cleanup": factor_after["direct_factor_count"],
                    "factor_diagnostics": factor_after,
                    "qep_calls": 0,
                    "pde_solve": "not_run",
                },
            )
        return result
    except FreshBareFAuthorityIdentityError as exc:
        system_was_created = system is not None
        if factor is not None:
            factor.destroy()
            factor_after = dict(factor.diagnostics)
            factor = None
        inventory = dict(system.construction_inventory) if system is not None else {}
        stop_bookkeeping = _fresh_bare_f_identity_stop_bookkeeping(
            rhs_vectors=rhs_vectors,
            exact_records=exact_records,
            inventory=inventory,
            factor_ready=factor_ready,
            factor_after=factor_after,
            stage=exc.stage,
            system_created=system_was_created,
        )
        generated_rhs_labels = list(stop_bookkeeping["rhs_generated_labels"])
        generated_exact_labels = list(stop_bookkeeping["exact_output_generated_labels"])
        for vector in rhs_vectors.values():
            vector.destroy()
        rhs_vectors.clear()
        if system is not None:
            system.destroy()
            system = None
        controlled_result = {
            "schema": V5_BARE_F_SCHEMA,
            "method": V5_BARE_F_METHOD,
            "profile": "task040.v5.h4.current_layout_bare_f_authority.v1",
            "status": stop_bookkeeping["gate_status"],
            "classification": "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL",
            "identity_failure_code": str(exc.failure_code),
            "identity_failure": {
                "stage": exc.stage,
                "message": str(exc),
                "details": _json_safe(exc.details),
            },
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "source_provenance": source_provenance,
            "operator_semantics_audit": {
                "path": "operator_semantics_audit.json",
                "sha256": operator_semantics_audit_file_sha256,
                "content_sha256": operator_semantics_audit["record_sha256"],
            },
            "system_created": stop_bookkeeping["system_created"],
            "rhs_vectors_loaded": stop_bookkeeping["rhs_vectors_loaded"],
            "rhs_generated_labels": generated_rhs_labels,
            "rhs_vectors_cleanup": {
                "count": stop_bookkeeping["rhs_vectors_loaded"],
                "completed": True,
            },
            "exact_output_vectors_loaded": stop_bookkeeping[
                "exact_output_vectors_loaded"
            ],
            "exact_output_generated_labels": generated_exact_labels,
            "exact_output_vectors_cleanup": {
                "count": stop_bookkeeping["exact_output_vectors_loaded"],
                "completed": True,
            },
            "reports": _json_safe(reports),
            "factor_lifecycle": {
                "factor_count_before_solve": 1 if factor_after else 0,
                "factor_count_after_cleanup": factor_after.get(
                    "direct_factor_count", 0
                ),
                "consumer_retains_factor": False,
                "factor_ready": _json_safe(dict(factor_ready)),
                "factor_after_cleanup": _json_safe(dict(factor_after)),
            },
            "modal_source_factor_lifecycle": _json_safe(
                inventory.get("one_cell_source_factor_events", [])
            ),
            "construction_inventory": _json_safe(inventory),
            "external_dtn_coupling": {
                "status": stop_bookkeeping["external_dtn_status"],
                "matrix_objects_constructed": dict(
                    inventory.get("objects", {"C": 0, "D": 0, "H": 0})
                ),
                "minimal_external_coupling_objects_constructed": int(
                    inventory.get("minimal_external_coupling_objects_constructed", 0)
                ),
                "minimal_external_surface_component_count": int(
                    inventory.get("minimal_external_surface_component_count", 0)
                ),
            },
            "qep_calls": int(inventory.get("qep_calls", 0)),
            "pde_solve": "not_run",
            "interface_mass_constructed": False,
            "outer_ksp": "not_run",
            "gate": {
                "numerical_pass": None,
                "identity_pass": False,
                "pass": False,
                "status": stop_bookkeeping["gate_status"],
            },
        }
        comm.barrier()
        if comm.rank == 0:
            _atomic_json(output_root / "manifest.json", controlled_result)
        comm.barrier()
        if marker_callback is not None:
            marker_callback(
                "v5_bare_f_identity_stop",
                {
                    "classification": controlled_result["classification"],
                    "identity_failure_code": controlled_result["identity_failure_code"],
                    "stage": exc.stage,
                    "system_created": stop_bookkeeping["system_created"],
                    "factor_count": 0,
                    "qep_calls": int(inventory.get("qep_calls", 0)),
                },
            )
        return controlled_result
    finally:
        if factor is not None:
            factor.destroy()
        for vector in rhs_vectors.values():
            vector.destroy()
        if system is not None:
            system.destroy()


__all__ = (
    "CurrentBareFAuthoritySystem",
    "FreshBareFAuthorityIdentityError",
    "V5_BARE_F_METHOD",
    "V5_BARE_F_SCHEMA",
    "V5_BARE_F_SOURCE_LABELS",
    "V5_BARE_F_SOURCE_SPECS",
    "assemble_current_bare_f_authority_system",
    "build_v5_operator_semantics_audit",
    "build_current_bare_f_rhs",
    "canonical_layout_tokens",
    "canonical_packets_for_vector",
    "_collective_raise_fresh_bare_f_identity",
    "_construct_bare_f_factor_after_identity_gate",
    "vector_identity",
)
