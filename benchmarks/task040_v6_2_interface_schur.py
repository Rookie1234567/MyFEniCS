"""Thin V6-2 full-interface Schur and exact-qualification runners.

The identity entry point records only scalar and owner-local metadata evidence;
it does not write numerical packets or construct a full-side factor.  The
separate exact-qualification entry point below is a later, explicit opt-in
consumer that receives an already constructed current system and writes only
the four owner-local packet roles after the independent full-residual Gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_schur import (
    build_canonical_interface_layout,
    build_petsc_d1_reference_interface_schur_mat,
    build_petsc_full_interface_schur_action,
    build_petsc_interface_schur_oracle,
    build_v6_cell_recovery_owner_group_rows,
)
from src.solvers.hybrid_exact_qualification import (
    V5_VECTOR_SCHEMA,
    V5_VECTOR_SIDE,
    aggregate_exact_packet_manifests,
    gamma_layout_packet_identity,
    hash_file_sha256,
    make_current_exact_packet_identity_provider,
    make_current_exact_packet_writer,
    make_current_exact_solution_packet_consumer,
    rank_local_shard_binding_sha256,
    run_exact_qualification_family,
    validate_owner_vector_descriptor,
)
from src.solvers.hybrid_bare_f_authority import (
    _source_definition_sha256 as _v5_source_definition_sha256,
    _source_semantic_descriptor as _v5_source_semantic_descriptor,
)


V6_2_INTERFACE_SCHUR_FLAG = "--v6-2-interface-schur"
V6_2_INTERFACE_SCHUR_METHOD = "task040_v6_2_full_interface_schur"
V6_2_INTERFACE_SCHUR_SCHEMA = "task040.v6_2.full_interface_schur.v1"
V6_2_INTERFACE_SCHUR_PROFILE_ID = "task040.v6_2.h4.full_interface.v1"
V6_2_FORMAL_SEQUENCE_START_SCOPE = (
    "run_v6_2_interface_schur_entry_before_preflight_and_artifact_setup"
)
V6_2_INTERFACE_LOWER_COUNT = 7560
V6_2_INTERFACE_UPPER_COUNT = 7560
V6_2_INTERFACE_JOINT_COUNT = (
    V6_2_INTERFACE_LOWER_COUNT + V6_2_INTERFACE_UPPER_COUNT
)
V6_2_ZERO_TOLERANCE = 1.0e-13
V6_2_ROUNDTRIP_TOLERANCE = 1.0e-11
V6_2_ACTION_TOLERANCE = 1.0e-10
V6_2_RESOURCE_HEADROOM_BYTES = 4 * 2**30
V6_2_MIN_DISK_FREE_BYTES = 20 * 2**30
V6_2_EXACT_QUALIFICATION_SOURCES = (
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "modal_traction_positive",
    "modal_traction_negative",
    "fixed_random_repeat_1",
)
V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA = (
    "fd7bea41d7d7b7869dd3ade4407129b00900ef7d"
)
V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH = (
    "a672183780b34a0f39739458a68f952a631316248955926fed697fb8d619ac5e"
)
V7_SCALE_NORMALIZED_IDENTITY_SCHEMA = (
    "task040.v7.scale_normalized_identity.v1"
)
V7_SCALE_NORMALIZED_IDENTITY_FLAG = "--v7-scale-normalized-identity"
V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA = (
    "task040.v7.scale_normalized_identity.formal.v1"
)
V7_SCALE_NORMALIZED_IDENTITY_METHOD = "task040_v7_scale_normalized_identity"
V7_SCALE_NORMALIZED_IDENTITY_PROFILE_ID = "task040.v7.h4.identity.v1"
V7_IDENTITY_TARGET_SECONDS = 1800
V7_IDENTITY_HARD_SECONDS = 3600
V7_PREFERRED_MEMORY_BYTES = 35 * 2**30
V7_SAFE_DENOMINATOR = 1.0e-300
V7_IDENTITY_VECTOR_INDICES = (0, 1, 2)
V7_LINEARITY_VECTOR_INDICES = (10, 11)
V7_SCALE_EXPONENTS = (-10, 0, 10)
V7_LINEARITY_ALPHA = 0.37 - 0.21j
V7_D1_CONTRIBUTION_ORDER = (
    "middle_boundary",
    "middle_correction",
    "lower_correction",
    "upper_correction",
)
V7_MOVING_PML_FULL_STATE_FLAG = "--v7-moving-pml-full-state"
V7_MOVING_PML_FULL_STATE_METHOD = "task040_v6_5_moving_pml_full_state"
V7_MOVING_PML_FULL_STATE_SCHEMA = "task040.v6_5.moving_pml_full_state.v1"
V7_MOVING_PML_FULL_STATE_PROFILE_ID = "task040.v6_5.moving_pml.full_state.v1"
V8_FULL_SPECTRUM_ONLY_FLAG = "--v8-full-spectrum-only"
V8_FULL_SPECTRUM_ONLY_METHOD = "task040_v8_full_spectrum_two_source"
V8_FULL_SPECTRUM_ONLY_SCHEMA = "task040.v8.full_spectrum_two_source.v1"
V8_FULL_SPECTRUM_ONLY_PROFILE_ID = "task040.v8.full_spectrum.two_source.v1"
V8_FULL_SPECTRUM_TIMEOUT_SECONDS = 10800
V8_FULL_SPECTRUM_MIN_AVAILABLE_BYTES = 96 * 2**30
V8_FULL_SPECTRUM_PREFERRED_MEMORY_BYTES = 40 * 2**30
V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS = 1800
V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS = 900
V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS = 1200
V8_FULL_SPECTRUM_SOURCES = (
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "modal_traction_positive",
    "modal_traction_negative",
    "fixed_random_repeat_1",
)
V8_FULL_SPECTRUM_CHECKPOINTS = (8, 16, 32, 64)
V8_ADAPTIVE_SCHWARZ_ONLY_FLAG = "--v8-adaptive-schwarz-only"
V8_ADAPTIVE_SCHWARZ_ONLY_METHOD = "task040_v8_adaptive_impedance_schwarz_stage_a"
V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA = (
    "task040.v8.adaptive_impedance_schwarz.stage_a.v1"
)
V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID = (
    "task040.v8.adaptive_impedance_schwarz.stage_a.v1"
)
V8_ADAPTIVE_PREFERRED_MEMORY_BYTES = 35 * 2**30
V8_ADAPTIVE_HARD_STOP_BYTES = 45 * 2**30
V8_ADAPTIVE_SETUP_TARGET_SECONDS = 3600
V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS = 1200
V8_ADAPTIVE_TIMEOUT_SECONDS = 10800

__all__ = (
    "V6_2_EXACT_QUALIFICATION_SOURCES",
    "V6_2_FORMAL_SEQUENCE_START_SCOPE",
    "V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH",
    "V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA",
    "V6_2_INTERFACE_JOINT_COUNT",
    "V6_2_INTERFACE_LOWER_COUNT",
    "V6_2_INTERFACE_SCHUR_FLAG",
    "V6_2_INTERFACE_SCHUR_METHOD",
    "V6_2_INTERFACE_SCHUR_PROFILE_ID",
    "V6_2_INTERFACE_SCHUR_SCHEMA",
    "V6_2_INTERFACE_UPPER_COUNT",
    "V6_2_MIN_DISK_FREE_BYTES",
    "V6_2_RESOURCE_HEADROOM_BYTES",
    "V7_D1_CONTRIBUTION_ORDER",
    "V7_IDENTITY_HARD_SECONDS",
    "V7_IDENTITY_TARGET_SECONDS",
    "V7_IDENTITY_VECTOR_INDICES",
    "V7_LINEARITY_ALPHA",
    "V7_LINEARITY_VECTOR_INDICES",
    "V7_MOVING_PML_FULL_STATE_FLAG",
    "V7_MOVING_PML_FULL_STATE_METHOD",
    "V7_MOVING_PML_FULL_STATE_PROFILE_ID",
    "V7_MOVING_PML_FULL_STATE_SCHEMA",
    "V7_PREFERRED_MEMORY_BYTES",
    "V7_SAFE_DENOMINATOR",
    "V7_SCALE_EXPONENTS",
    "V7_SCALE_NORMALIZED_IDENTITY_FLAG",
    "V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA",
    "V7_SCALE_NORMALIZED_IDENTITY_METHOD",
    "V7_SCALE_NORMALIZED_IDENTITY_PROFILE_ID",
    "V7_SCALE_NORMALIZED_IDENTITY_SCHEMA",
    "V8_ADAPTIVE_HARD_STOP_BYTES",
    "V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS",
    "V8_ADAPTIVE_PREFERRED_MEMORY_BYTES",
    "V8_ADAPTIVE_SCHWARZ_ONLY_FLAG",
    "V8_ADAPTIVE_SCHWARZ_ONLY_METHOD",
    "V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID",
    "V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA",
    "V8_ADAPTIVE_SETUP_TARGET_SECONDS",
    "V8_ADAPTIVE_TIMEOUT_SECONDS",
    "V8_FULL_SPECTRUM_CHECKPOINTS",
    "V8_FULL_SPECTRUM_MIN_AVAILABLE_BYTES",
    "V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS",
    "V8_FULL_SPECTRUM_ONLY_FLAG",
    "V8_FULL_SPECTRUM_ONLY_METHOD",
    "V8_FULL_SPECTRUM_ONLY_PROFILE_ID",
    "V8_FULL_SPECTRUM_ONLY_SCHEMA",
    "V8_FULL_SPECTRUM_PREFERRED_MEMORY_BYTES",
    "V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS",
    "V8_FULL_SPECTRUM_SOURCES",
    "V8_FULL_SPECTRUM_TIMEOUT_SECONDS",
    "V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS",
    "build_v6_2_exact_qualification_plan",
    "collect_v7_scale_normalized_identity_metrics",
    "run_v6_2_exact_qualification_packets",
    "run_v6_2_interface_schur",
)


def build_v6_2_exact_qualification_plan() -> dict[str, Any]:
    """Describe the same-process exact qualification path.

    The plan is configuration/provenance, not a numerical result.  The actual
    run keeps the three group factors alive across identity, exact
    qualification, and any later continuation before the one final cleanup.
    """

    return {
        "status": "configured_same_process_exact",
        "execution_mode": "same_process_exact_then_v6_3_continuation",
        "identity_only": False,
        "source_order": list(V6_2_EXACT_QUALIFICATION_SOURCES),
        "rhs_layout": "current_canonical_active_keys_owner_local",
        "interface_rhs": "g=b_Gamma-A_GammaI*A_II^-1*b_I",
        "checkpoints": [16, 32, 64, 128],
        "conditional_checkpoints": [256, 512],
        "conditional_authority": {
            "256": "r128<=0.8 or log10(r64/r128)>=0.10",
            "512": (
                "r256<=1e-2 and full_residual_history_monotone and "
                "current_rss<45GiB and swap=0 and elapsed<21600s; "
                "final watchdog peak_rss<45GiB"
            ),
        },
        "solution_recovery": (
            "x_I=A_II^-1*(b_I-A_I,Gamma*x_Gamma)"
        ),
        "full_residual": "independent_current_bare_F_mult",
        "first_two_gate": "each relative true residual <= 1e-9",
        "remaining_sources": "run only after first_two_gate",
        "packetization": {
            "required": True,
            "roles": [
                "exact_output_canonical",
                "exact_output_owner_rows",
                "gamma_l_canonical",
                "gamma_u_canonical",
            ],
            "writer": "current_live_full_state_and_gamma_layout_values",
            "aggregate": "all_rank_role_manifests_rehashed_and_reopened",
        },
        "one_cell_source_factor": "not_reexecuted",
        "full_side_exact_factor": "not_constructed; bare-F is used only for explicit residual",
        "frozen_owner_row_arrays": (
            "loaded per source only after fixed metadata/shard/canonical/live-roundtrip "
            "validation; complex PETSc owner-order values, never row ids"
        ),
    }


def _assert_disjoint_roots(first: str | Path, second: str | Path) -> tuple[Path, Path]:
    """Resolve two artifact roots and reject either root nesting the other."""

    first_root = Path(first).resolve()
    second_root = Path(second).resolve()
    if first_root == second_root:
        raise ValueError("V6-2 packet output and frozen input roots must be disjoint")
    for child, parent in ((first_root, second_root), (second_root, first_root)):
        try:
            child.relative_to(parent)
        except ValueError:
            continue
        raise ValueError(
            "V6-2 packet output and frozen input roots must not be nested"
        )
    return first_root, second_root


def _collective_driver_error(
    comm: MPI.Intracomm,
    stage: str,
    local_error: str | None,
) -> None:
    """Make a post-family local extraction error collective-safe."""

    errors = comm.allgather(local_error)
    first = next(
        ((rank, error) for rank, error in enumerate(errors) if error is not None),
        None,
    )
    if first is not None:
        rank, error = first
        raise RuntimeError(f"V6-2 {stage} failed on rank {rank}: {error}")


def _require_fresh_packet_root(root: Path) -> None:
    """Reject an existing non-empty packet root before any artifact write."""

    if root.exists():
        if not root.is_dir():
            raise ValueError("V6-2 packet output root is not a directory")
        if any(root.iterdir()):
            raise ValueError(
                "V6-2 packet output root must be fresh or an empty directory"
            )


_V6_2_EXACT_PROVENANCE_FIELDS = (
    "input_sha256",
    "physical_model_sha256",
    "selected_manifest_sha256",
    "selected_identity_sha256",
    "resolved_config_sha256",
    "source_sha",
)


def _v6_2_is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _v6_2_resolve_under(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"V6-2 {field} must be a path")
    candidate = Path(value)
    resolved = (
        candidate if candidate.is_absolute() else root / candidate
    ).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"V6-2 {field} escapes the frozen exact-authority root"
        ) from exc
    return resolved


def _v6_2_require_v5_rhs_authority_root(root: Path) -> Path:
    """Require the V6 formal input root to be the frozen V5 RHS authority."""

    resolved = Path(root).resolve()
    if resolved.name != "bare_f_authority" or resolved.parent.name != "worker":
        raise ValueError(
            "V6-2 exact_spool_root must point to the frozen V5 "
            "worker/bare_f_authority root, not a historical Task039 spool"
        )
    if not resolved.is_dir():
        raise ValueError(f"V6-2 frozen V5 RHS authority root is missing: {resolved}")
    return resolved


def _v6_2_recompute_source_definition(
    descriptor: Mapping[str, Any],
) -> str:
    """Recompute the frozen producer's semantic source-definition digest.

    The V5 metadata stores both the semantic descriptor and its digest.  A
    caller-supplied copy is not authority merely because those two fields
    agree with each other: the semantic descriptor is reconstructed through
    the same producer routine and its provenance is checked as well.
    """

    label = descriptor.get("label")
    source_definition = descriptor.get("source_definition")
    if not isinstance(label, str) or not isinstance(source_definition, Mapping):
        raise ValueError("V6-2 frozen descriptor lacks source_definition")
    definition_provenance = source_definition.get("provenance")
    if not isinstance(definition_provenance, Mapping):
        raise ValueError(
            f"V6-2 frozen descriptor {label} lacks source-definition provenance"
        )
    semantic = _v5_source_semantic_descriptor(
        label=label,
        metadata=source_definition,
        provenance=definition_provenance,
    )
    if source_definition.get("source_definition_descriptor") != semantic:
        raise ValueError(
            f"V6-2 frozen descriptor {label} source semantic descriptor mismatch"
        )
    observed_digest = descriptor.get("source_definition_sha256")
    source_definition_digest = source_definition.get("source_definition_sha256")
    recomputed = _v5_source_definition_sha256(
        label=label,
        metadata=source_definition,
        provenance=definition_provenance,
    )
    if (
        observed_digest != source_definition_digest
        or observed_digest != recomputed
    ):
        raise ValueError(
            f"V6-2 frozen descriptor {label} source_definition_sha256 mismatch"
        )
    return str(recomputed)


def _v6_2_load_frozen_rhs_descriptors(
    frozen_root: Path,
    *,
    comm: MPI.Intracomm,
    frozen_rhs_provenance: Mapping[str, Any],
    bare_operator_hash: str,
    expected_global_size: int,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, str],
    dict[str, dict[str, Any]],
]:
    """Read the one fixed V5 descriptor per source for this MPI rank.

    Formal callers may carry a descriptor mapping for convenience, but the
    authority is always the immutable ``rank%04d/bottom_<label>_rhs.json``
    file selected from the frozen V5 root.  Paths, metadata bytes, source
    semantics, and all six provenance fields are checked before the mapping
    is returned to the exact consumer.
    """

    descriptors: dict[str, dict[str, Any]] = {}
    raw_descriptors: dict[str, dict[str, Any]] = {}
    metadata_hashes: dict[str, str] = {}
    rank_dir = frozen_root / f"rank{int(comm.rank):04d}"
    try:
        rank_dir.relative_to(frozen_root)
    except ValueError as exc:
        raise ValueError("V6-2 frozen rank descriptor directory escapes root") from exc
    for label in V6_2_EXACT_QUALIFICATION_SOURCES:
        relative_metadata = Path(
            f"rank{int(comm.rank):04d}/bottom_{label}_rhs.json"
        )
        metadata_path = (frozen_root / relative_metadata).resolve()
        try:
            metadata_path.relative_to(frozen_root)
        except ValueError as exc:
            raise ValueError(
                f"V6-2 frozen descriptor path escapes root for {label}"
            ) from exc
        if not metadata_path.is_file():
            raise FileNotFoundError(
                f"V6-2 frozen descriptor is missing: {metadata_path}"
            )
        raw = metadata_path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"V6-2 frozen descriptor is not valid JSON: {metadata_path}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise TypeError(f"V6-2 frozen descriptor {label} is not a mapping")
        raw_descriptor = dict(payload)
        expected_metadata_path = relative_metadata.as_posix()
        if raw_descriptor.get("metadata_path") != expected_metadata_path:
            raise ValueError(
                f"V6-2 frozen descriptor {label} metadata_path is not authority-bound"
            )
        if raw_descriptor.get("label") != label:
            raise ValueError(
                f"V6-2 frozen descriptor label mismatch for {label}"
            )
        descriptor_provenance = raw_descriptor.get("source_provenance")
        if not isinstance(descriptor_provenance, Mapping):
            raise ValueError(f"V6-2 frozen descriptor {label} lacks source_provenance")
        for field in _V6_2_EXACT_PROVENANCE_FIELDS:
            if descriptor_provenance.get(field) != frozen_rhs_provenance.get(field):
                raise ValueError(
                    f"V6-2 frozen descriptor {label} provenance mismatch for {field}"
                )
        _v6_2_recompute_source_definition(raw_descriptor)
        validate_owner_vector_descriptor(
            raw_descriptor,
            expected_label=label,
            expected_schema=V5_VECTOR_SCHEMA,
            expected_side=V5_VECTOR_SIDE,
            expected_source_sha256=frozen_rhs_provenance["source_sha"],
            expected_input_sha256=frozen_rhs_provenance["input_sha256"],
            expected_physical_model_sha256=frozen_rhs_provenance[
                "physical_model_sha256"
            ],
            expected_selected_manifest_sha256=frozen_rhs_provenance[
                "selected_manifest_sha256"
            ],
            expected_resolved_config_sha256=frozen_rhs_provenance[
                "resolved_config_sha256"
            ],
            expected_operator_hash=V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH,
            expected_global_size=expected_global_size,
        )
        for field in (
            "array_path",
            "owner_row_array_path",
            "canonical_layout_path",
        ):
            _v6_2_resolve_under(frozen_root, raw_descriptor[field], field)
        raw_descriptors[label] = deepcopy(raw_descriptor)
        descriptor = deepcopy(raw_descriptor)
        descriptor["bare_f_operator_hash"] = bare_operator_hash
        runtime_source_definition = descriptor["source_definition"]
        runtime_source_definition["bare_f_operator_hash"] = bare_operator_hash
        descriptor["rank_local_shard_binding_sha256"] = (
            rank_local_shard_binding_sha256(
                rank=int(comm.rank),
                label=str(descriptor["label"]),
                role=str(descriptor["role"]),
                source_definition_sha256=str(
                    descriptor["source_definition_sha256"]
                ),
                key_set_sha256=str(descriptor["canonical_key_set_sha256"]),
                canonical_layout_sha256=str(
                    descriptor["canonical_layout_sha256"]
                ),
                identity=descriptor["vector_identity"],
                source_provenance=descriptor["source_provenance"],
                bare_f_operator_hash=bare_operator_hash,
                rhs_repeat=runtime_source_definition["rhs_repeat"],
            )
        )
        validate_owner_vector_descriptor(
            descriptor,
            expected_label=label,
            expected_schema=V5_VECTOR_SCHEMA,
            expected_side=V5_VECTOR_SIDE,
            expected_source_sha256=frozen_rhs_provenance["source_sha"],
            expected_input_sha256=frozen_rhs_provenance["input_sha256"],
            expected_physical_model_sha256=frozen_rhs_provenance[
                "physical_model_sha256"
            ],
            expected_selected_manifest_sha256=frozen_rhs_provenance[
                "selected_manifest_sha256"
            ],
            expected_resolved_config_sha256=frozen_rhs_provenance[
                "resolved_config_sha256"
            ],
            expected_operator_hash=bare_operator_hash,
            expected_global_size=expected_global_size,
        )
        descriptors[label] = descriptor
        metadata_hashes[label] = hashlib.sha256(raw).hexdigest()
    return descriptors, metadata_hashes, raw_descriptors


def _v6_2_formal_authority_provenance(
    identity_preflight: Mapping[str, Any],
    source_sha: str,
    *,
    frozen_rhs_source_sha: str = V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA,
) -> dict[str, dict[str, str]]:
    """Separate current qualification identity from frozen RHS provenance."""

    if identity_preflight.get("pass") is not True:
        raise ValueError("V6-2 formal binding requires a passing identity preflight")
    observed = identity_preflight.get("observed")
    if not isinstance(observed, Mapping):
        raise ValueError("V6-2 identity preflight lacks observed authority fields")
    values = {
        "input_sha256": observed.get("input_sha256"),
        "physical_model_sha256": observed.get("physical_model_sha256"),
        "selected_manifest_sha256": observed.get("selected_manifest_sha256"),
        "selected_identity_sha256": observed.get("selected_identity_sha256"),
        "resolved_config_sha256": observed.get("resolved_config_sha256"),
    }
    for field, value in values.items():
        expected_length = 64
        if not _v6_2_is_hex(value, expected_length):
            raise ValueError(
                f"V6-2 authority provenance {field} is not a valid identity"
            )
    if not _v6_2_is_hex(source_sha, 40):
        raise ValueError("V6-2 qualification source SHA is not a valid commit SHA")
    if not _v6_2_is_hex(frozen_rhs_source_sha, 40):
        raise ValueError("V5 RHS producer source SHA is not a valid commit SHA")
    current = {
        **{field: str(value) for field, value in values.items()},
        "source_sha": str(source_sha),
    }
    frozen_rhs = {
        **{field: str(value) for field, value in values.items()},
        "source_sha": str(frozen_rhs_source_sha),
    }
    return {
        "current_qualification": current,
        "frozen_rhs": frozen_rhs,
    }


def _v6_2_validate_provenance(
    value: Mapping[str, Any],
    *,
    name: str,
) -> dict[str, str]:
    """Normalize one explicit six-field authority identity for evidence."""

    if not isinstance(value, Mapping):
        raise TypeError(f"V6-2 {name} must be a mapping")
    normalized: dict[str, str] = {}
    for field in _V6_2_EXACT_PROVENANCE_FIELDS:
        observed = value.get(field)
        expected_length = 40 if field == "source_sha" else 64
        if not _v6_2_is_hex(observed, expected_length):
            raise ValueError(
                f"V6-2 {name}.{field} is not a valid authority identity"
            )
        normalized[field] = str(observed)
    return normalized


def _v6_2_validate_descriptor_metadata_hashes(
    value: Mapping[str, Any],
    *,
    name: str = "frozen_rhs_descriptor_metadata_sha256",
) -> dict[str, str]:
    """Require the per-rank fixed five-descriptor byte hashes."""

    if not isinstance(value, Mapping):
        raise TypeError(f"V6-2 {name} must be a mapping")
    labels = tuple(str(label) for label in value)
    if labels != V6_2_EXACT_QUALIFICATION_SOURCES:
        raise ValueError(
            f"V6-2 {name} must contain the five sources in authority order"
        )
    normalized: dict[str, str] = {}
    for label in V6_2_EXACT_QUALIFICATION_SOURCES:
        digest = value.get(label)
        if not _v6_2_is_hex(digest, 64):
            raise ValueError(
                f"V6-2 {name}[{label!r}] is not a SHA256 digest"
            )
        normalized[label] = str(digest)
    return normalized


def _bind_v6_2_formal_exact_configuration(
    exact_configuration: Mapping[str, Any],
    *,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    identity_preflight: Mapping[str, Any],
    bare_operator: PETSc.Mat,
    bare_operator_hash: str,
    source_sha: str,
) -> dict[str, Any]:
    """Bind caller configuration to the live V6-2 authority identities.

    The formal path may accept callbacks and numerical knobs from its caller,
    but it cannot accept a second source of truth for descriptors, roots,
    provenance, or validation.  This function is metadata-only and is called
    after the current bare-F operator exists, so the expected operator hash and
    global size are derived from the live object.
    """

    if not isinstance(exact_configuration, Mapping):
        raise TypeError("V6-2 formal exact configuration must be a mapping")
    if not isinstance(bare_operator, PETSc.Mat):
        raise TypeError("V6-2 formal exact binding requires a PETSc bare operator")
    if not _v6_2_is_hex(bare_operator_hash, 64):
        raise ValueError("V6-2 live bare-F operator hash is not a SHA256 digest")
    frozen_root = Path(exact_spool_root).resolve()
    output_root = Path(run_directory).resolve()
    derived_packet_root = output_root / "exact_packets"
    _assert_disjoint_roots(output_root, frozen_root)
    if "frozen_root" in exact_configuration:
        supplied_frozen = exact_configuration["frozen_root"]
        if supplied_frozen is None or Path(supplied_frozen).resolve() != frozen_root:
            raise ValueError(
                "V6-2 formal exact frozen_root is not the actual exact spool"
            )
    if "packet_root" in exact_configuration:
        supplied_packet = exact_configuration["packet_root"]
        if (
            supplied_packet is None
            or Path(supplied_packet).resolve() != derived_packet_root
        ):
            raise ValueError(
                "V6-2 formal exact packet_root must be derived from run_directory"
            )
    provenance_sets = _v6_2_formal_authority_provenance(
        identity_preflight,
        source_sha,
    )
    current_provenance = provenance_sets["current_qualification"]
    frozen_rhs_provenance = provenance_sets["frozen_rhs"]
    if "base_directory" in exact_configuration:
        supplied_base = exact_configuration["base_directory"]
        if supplied_base is None:
            raise ValueError("V6-2 formal exact base_directory is missing")
        base_directory = _v6_2_resolve_under(
            frozen_root, supplied_base, "base_directory"
        )
        if base_directory != frozen_root:
            raise ValueError(
                "V6-2 formal exact base_directory must be the frozen V5 "
                "authority root"
            )
    else:
        base_directory = frozen_root

    comm = bare_operator.getComm().tompi4py()
    (
        descriptors,
        descriptor_metadata_hashes,
        raw_descriptors,
    ) = _v6_2_load_frozen_rhs_descriptors(
        frozen_root,
        comm=comm,
        frozen_rhs_provenance=frozen_rhs_provenance,
        bare_operator_hash=bare_operator_hash,
        expected_global_size=int(bare_operator.getSize()[0]),
    )
    supplied_descriptors = exact_configuration.get("descriptors")
    if supplied_descriptors is not None:
        _validate_exact_descriptor_order(supplied_descriptors)
        try:
            supplied_encoded = json.dumps(
                supplied_descriptors,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            derived_encoded = json.dumps(
                raw_descriptors,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "V6-2 supplied descriptors are not JSON-comparable authority metadata"
            ) from exc
        if supplied_encoded != derived_encoded:
            raise ValueError(
                "V6-2 supplied descriptors differ from fixed V5 authority files"
            )
    labels = _validate_exact_descriptor_order(descriptors)
    supplied_provenance = exact_configuration.get("source_provenance")
    if "source_provenance" in exact_configuration:
        if not isinstance(supplied_provenance, Mapping):
            raise TypeError("V6-2 formal source_provenance must be a mapping")
        for field in _V6_2_EXACT_PROVENANCE_FIELDS:
            if supplied_provenance.get(field) != frozen_rhs_provenance[field]:
                raise ValueError(
                    "V6-2 formal source_provenance must use frozen V5 RHS "
                    f"authority for {field}"
                )
    supplied_validation = exact_configuration.get("validation")
    if "validation" in exact_configuration and supplied_validation is None:
        raise ValueError("V6-2 formal validation cannot be None")
    for operator_field in ("bare_f_operator_hash", "operator_hash"):
        if operator_field in exact_configuration:
            if exact_configuration[operator_field] != bare_operator_hash:
                raise ValueError(
                    f"V6-2 formal {operator_field} is not the live bare-F hash"
                )

    generated_validation = {
        "expected_schema": V5_VECTOR_SCHEMA,
        "expected_side": V5_VECTOR_SIDE,
        "expected_source_sha256": frozen_rhs_provenance["source_sha"],
        "expected_input_sha256": frozen_rhs_provenance["input_sha256"],
        "expected_physical_model_sha256": frozen_rhs_provenance[
            "physical_model_sha256"
        ],
        "expected_selected_manifest_sha256": frozen_rhs_provenance[
            "selected_manifest_sha256"
        ],
        "expected_resolved_config_sha256": frozen_rhs_provenance[
            "resolved_config_sha256"
        ],
        "expected_operator_hash": bare_operator_hash,
        "expected_global_size": int(bare_operator.getSize()[0]),
    }
    if "validation" in exact_configuration:
        if not isinstance(supplied_validation, Mapping):
            raise TypeError("V6-2 formal validation must be a mapping")
        for field, expected in generated_validation.items():
            if field in supplied_validation and supplied_validation[field] != expected:
                raise ValueError(
                    f"V6-2 formal validation.{field} is not authority-bound"
                )

    for label in labels:
        descriptor = descriptors[label]
        descriptor_provenance = descriptor.get("source_provenance")
        if not isinstance(descriptor_provenance, Mapping):
            raise ValueError(
                f"V6-2 descriptor {label} lacks frozen source_provenance"
            )
        for field in _V6_2_EXACT_PROVENANCE_FIELDS:
            if descriptor_provenance.get(field) != frozen_rhs_provenance[field]:
                raise ValueError(
                    f"V6-2 descriptor {label} {field} is not frozen RHS authority"
                )
        for field in (
            "array_path",
            "owner_row_array_path",
            "canonical_layout_path",
        ):
            _v6_2_resolve_under(frozen_root, descriptor.get(field), field)
        validate_owner_vector_descriptor(
            descriptor,
            expected_label=label,
            expected_schema=V5_VECTOR_SCHEMA,
            expected_side=V5_VECTOR_SIDE,
            expected_source_sha256=frozen_rhs_provenance["source_sha"],
            expected_input_sha256=frozen_rhs_provenance["input_sha256"],
            expected_physical_model_sha256=frozen_rhs_provenance[
                "physical_model_sha256"
            ],
            expected_selected_manifest_sha256=frozen_rhs_provenance[
                "selected_manifest_sha256"
            ],
            expected_resolved_config_sha256=frozen_rhs_provenance[
                "resolved_config_sha256"
            ],
            expected_operator_hash=bare_operator_hash,
            expected_global_size=int(bare_operator.getSize()[0]),
        )

    canonical_roundtrip = exact_configuration.get("canonical_roundtrip")
    if isinstance(canonical_roundtrip, Mapping):
        missing_callbacks = [
            label
            for label in labels
            if not callable(canonical_roundtrip.get(label))
        ]
        if missing_callbacks:
            raise TypeError(
                "V6-2 canonical_roundtrip is missing callable labels: "
                f"{missing_callbacks}"
            )
    elif not callable(canonical_roundtrip):
        raise TypeError("V6-2 canonical_roundtrip must be callable or label-indexed")

    operator_identity_bridge = {
        "schema": "task040.v6_2.operator_identity_bridge.v1",
        "status": "frozen_rhs_rebound_to_live_bare_f",
        "frozen_bare_f_operator_hash": V6_2_FROZEN_V5_BARE_F_OPERATOR_HASH,
        "qualification_live_bare_f_operator_hash": bare_operator_hash,
        "raw_descriptor_metadata_unchanged": True,
        "numeric_rhs_arrays_unchanged": True,
        "runtime_binding_recomputed": True,
        "shared_input_model_authority": True,
    }
    bound = dict(exact_configuration)
    bound["descriptors"] = descriptors
    bound["base_directory"] = str(base_directory)
    bound["frozen_root"] = str(frozen_root)
    bound["packet_root"] = str(derived_packet_root)
    bound["source_provenance"] = dict(frozen_rhs_provenance)
    bound["qualification_source_provenance"] = dict(current_provenance)
    bound["frozen_rhs_descriptor_metadata_sha256"] = dict(
        descriptor_metadata_hashes
    )
    bound["validation"] = generated_validation
    bound["operator_identity_bridge"] = operator_identity_bridge
    bound.pop("bare_f_operator_hash", None)
    bound.pop("operator_hash", None)
    # Keep current-source identity in the outer V6 manifest, never in the
    # frozen V5 descriptor provenance consumed by the exact family.
    bound.pop("current_source_sha", None)
    return bound


def _validate_exact_descriptor_order(
    descriptors: Mapping[str, Mapping[str, Any]],
) -> tuple[str, ...]:
    """Validate the ordered five-source contract before any source collective."""

    if not isinstance(descriptors, Mapping):
        raise TypeError("V6-2 exact qualification descriptors must be a mapping")
    labels = tuple(descriptors)
    if any(not isinstance(label, str) for label in labels):
        raise TypeError("V6-2 exact qualification descriptor keys must be strings")
    if labels != V6_2_EXACT_QUALIFICATION_SOURCES:
        raise ValueError(
            "V6-2 exact qualification descriptors must use the five sources in order"
        )
    for label in labels:
        descriptor = descriptors[label]
        if not isinstance(descriptor, Mapping):
            raise TypeError(f"V6-2 descriptor for {label} is not a mapping")
        if descriptor.get("label") != label:
            raise ValueError(
                f"V6-2 descriptor label does not match ordered key {label!r}"
            )
    return labels


def _observed_shared_factor_lifecycle(
    action: Any,
    *,
    expected_factor_count: int,
    stage: str,
) -> dict[str, Any]:
    """Read, validate, and copy the live group-factor lifecycle at one stage."""

    diagnostics = getattr(action, "diagnostics", {})
    if not isinstance(diagnostics, Mapping):
        raise RuntimeError(f"V6-2 {stage} action diagnostics are not a mapping")
    lifecycle = diagnostics.get("factor_lifecycle", diagnostics)
    if not isinstance(lifecycle, Mapping):
        raise RuntimeError(f"V6-2 {stage} action lifecycle is not a mapping")
    ready = lifecycle.get("ready")
    destroyed = lifecycle.get("destroyed", False)
    if int(ready) != int(expected_factor_count) or bool(destroyed):
        raise RuntimeError(
            f"V6-2 group factors were not retained at {stage} continuation boundary"
        )
    return dict(lifecycle)


def _run_v6_2_shared_current_lifecycle(
    *,
    action: Any,
    system: Any,
    interface_operator: PETSc.Mat,
    bare_operator: PETSc.Mat,
    exact_configuration: Mapping[str, Any],
    exact_runner: Callable[..., Mapping[str, Any]],
    expected_factor_count: int,
    gamma_layouts: Mapping[str, Any],
    canonical_layout: Any,
    continuation: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    checkpoint_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Keep identity, exact packets, and later services on one live action.

    The identity runner owns construction and final destruction.  This helper
    is the explicit hand-off between phases: it injects the already-created
    objects into the exact runner, checks that the group-factor service remains
    ready, and only then invokes an optional later-stage continuation.
    """

    if not isinstance(exact_configuration, Mapping):
        raise TypeError("V6-2 shared lifecycle configuration must be a mapping")
    if not callable(exact_runner):
        raise TypeError("V6-2 shared lifecycle exact runner must be callable")
    if not isinstance(interface_operator, PETSc.Mat) or not isinstance(
        bare_operator, PETSc.Mat
    ):
        raise TypeError("V6-2 shared lifecycle requires PETSc operators")
    if not isinstance(gamma_layouts, Mapping):
        raise TypeError("V6-2 shared lifecycle Gamma layouts must be a mapping")
    if "lower" not in gamma_layouts or "upper" not in gamma_layouts:
        raise ValueError("V6-2 shared lifecycle needs lower and upper Gamma layouts")
    if canonical_layout is None:
        raise ValueError("V6-2 shared lifecycle needs the joint canonical layout")
    lower_layout_identity = gamma_layout_packet_identity(gamma_layouts["lower"])
    upper_layout_identity = gamma_layout_packet_identity(gamma_layouts["upper"])
    canonical_audit = getattr(canonical_layout, "audit", {})
    if not isinstance(canonical_audit, Mapping):
        raise TypeError("V6-2 shared lifecycle canonical layout audit is not a mapping")
    layout_summary = {
        "lower": lower_layout_identity,
        "upper": upper_layout_identity,
        "joint": {
            "global_size": int(
                getattr(canonical_layout, "lower_global_count")
            )
            + int(getattr(canonical_layout, "upper_global_count")),
            "lower_global_count": int(
                getattr(canonical_layout, "lower_global_count")
            ),
            "upper_global_count": int(
                getattr(canonical_layout, "upper_global_count")
            ),
            "canonical_order": canonical_audit.get("canonical_order"),
            "canonical_key_order_sha256": canonical_audit.get(
                "canonical_key_order_sha256"
            ),
            "coverage_exact": canonical_audit.get("coverage_exact"),
            "canonical_position_bijection": canonical_audit.get(
                "canonical_position_bijection"
            ),
            "owner_local_mapping": canonical_audit.get("owner_local_mapping"),
        },
    }
    configuration = {
        key: value
        for key, value in exact_configuration.items()
        if key
        not in {
            "system",
            "schur_action",
            "interface_operator",
            "bare_operator",
            "comm",
            "lower_gamma_layout",
            "upper_gamma_layout",
            "canonical_layout",
            "gamma_layouts",
        }
    }
    configuration.update(
        {
            "system": system,
            "schur_action": action,
            "interface_operator": interface_operator,
            "bare_operator": bare_operator,
            "lower_gamma_layout": gamma_layouts["lower"],
            "upper_gamma_layout": gamma_layouts["upper"],
            "canonical_layout": canonical_layout,
            "checkpoint_callback": checkpoint_callback,
        }
    )
    exact_result = exact_runner(**configuration)
    lifecycle_after_exact = _observed_shared_factor_lifecycle(
        action,
        expected_factor_count=expected_factor_count,
        stage="exact qualification",
    )
    continuation_result: Mapping[str, Any] | None = None
    lifecycle_after_continuation: dict[str, Any] | None = None
    if continuation is not None:
        continuation_result = continuation(
            {
                "system": system,
                "interface_operator": interface_operator,
                "bare_operator": bare_operator,
                "schur_action": action,
                "exact_qualification": exact_result,
                "lower_gamma_layout": gamma_layouts["lower"],
                "upper_gamma_layout": gamma_layouts["upper"],
                "canonical_layout": canonical_layout,
                "factor_lifecycle_after_exact": dict(lifecycle_after_exact),
            }
        )
        if not isinstance(continuation_result, Mapping):
            raise TypeError("V6-2 continuation must return a mapping")
        lifecycle_after_continuation = _observed_shared_factor_lifecycle(
            action,
            expected_factor_count=expected_factor_count,
            stage="V6-3 continuation",
        )
    return {
        "exact_qualification": exact_result,
        "continuation": continuation_result,
        "same_live_action": True,
        "layout_summary": layout_summary,
        "same_layout_objects_injected": True,
        "factor_lifecycle_after_exact": lifecycle_after_exact,
        "factor_lifecycle_after_continuation": lifecycle_after_continuation,
    }


def run_v6_2_exact_qualification_packets(
    *,
    descriptors: Mapping[str, Mapping[str, Any]],
    base_directory: str | Path,
    interface_operator: PETSc.Mat,
    bare_operator: PETSc.Mat,
    schur_action: Any,
    system: Any,
    canonical_layout: Any,
    lower_gamma_layout: Any,
    upper_gamma_layout: Any,
    canonical_roundtrip: Callable[..., float]
    | Mapping[str, Callable[..., float]],
    canonical_packets_for_vector: Callable[..., Any],
    gamma_canonical_values_for_vector: Callable[..., Any],
    exact_output_canonical_roundtrip: Callable[..., float],
    packet_root: str | Path,
    frozen_root: str | Path,
    source_provenance: Mapping[str, Any],
    qualification_source_provenance: Mapping[str, Any],
    frozen_rhs_descriptor_metadata_sha256: Mapping[str, str],
    comm: MPI.Intracomm | None = None,
    right_preconditioner: Any | None = None,
    restart: int = 32,
    mandatory_checkpoints: Sequence[int] = (16, 32, 64, 128),
    conditional_checkpoints: Sequence[int] = (256, 512),
    authorize_conditional: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    max_iterations: int | None = None,
    checkpoint_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    full_residual_tolerance: float = 1.0e-9,
    validation: Mapping[str, Any] | None = None,
    operator_identity_bridge: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the one-process V6-2 exact family and aggregate four packet roles.

    This is intentionally a thin orchestration boundary.  The benchmark owns
    source ordering and artifact-root policy; the reusable ``src`` module owns
    loading, condensed RHS construction, restarted FGMRES, full-state recovery,
    live canonical extraction, packet rehashing, and all-rank aggregation.  A
    caller must provide the live current-system APIs explicitly, which keeps
    the numerical core independent of task-numbered benchmark paths.
    """

    if not isinstance(interface_operator, PETSc.Mat) or not isinstance(
        bare_operator, PETSc.Mat
    ):
        raise TypeError("V6-2 exact qualification requires PETSc operators")
    operator_comm = interface_operator.getComm().tompi4py()
    bare_comm = bare_operator.getComm().tompi4py()
    if comm is None:
        comm = operator_comm
    preflight_error: str | None = None
    packet_output_root: Path | None = None
    frozen_input_root: Path | None = None
    try:
        if (int(comm.rank), int(comm.size)) != (
            int(operator_comm.rank),
            int(operator_comm.size),
        ) or (int(comm.rank), int(comm.size)) != (
            int(bare_comm.rank),
            int(bare_comm.size),
        ):
            raise ValueError(
                "V6-2 exact qualification communicator does not match operator"
            )
        _validate_exact_descriptor_order(descriptors)
        if not isinstance(source_provenance, Mapping):
            raise TypeError(
                "V6-2 exact qualification source provenance must be a mapping"
            )
        if operator_identity_bridge is not None and not isinstance(
            operator_identity_bridge, Mapping
        ):
            raise TypeError("V6-2 operator identity bridge must be a mapping")
        frozen_provenance = _v6_2_validate_provenance(
            source_provenance,
            name="frozen RHS source provenance",
        )
        current_provenance = _v6_2_validate_provenance(
            qualification_source_provenance,
            name="qualification source provenance",
        )
        if any(
            current_provenance[field] != frozen_provenance[field]
            for field in _V6_2_EXACT_PROVENANCE_FIELDS
            if field != "source_sha"
        ):
            raise ValueError(
                "V6-2 qualification and frozen RHS provenance disagree on "
                "the shared input/model authority"
            )
        descriptor_metadata_hashes = _v6_2_validate_descriptor_metadata_hashes(
            frozen_rhs_descriptor_metadata_sha256
        )
        if canonical_layout is None:
            raise ValueError("V6-2 exact qualification needs the joint canonical layout")
        packet_output_root, frozen_input_root = _assert_disjoint_roots(
            packet_root, frozen_root
        )
        _require_fresh_packet_root(packet_output_root)
        aggregate_root = packet_output_root / "aggregate"
        _assert_disjoint_roots(aggregate_root, frozen_input_root)
        if not callable(canonical_roundtrip) and not isinstance(
            canonical_roundtrip, Mapping
        ):
            raise TypeError("V6-2 exact qualification requires canonical roundtrip")
        if isinstance(canonical_roundtrip, Mapping):
            missing_roundtrips = [
                label
                for label in V6_2_EXACT_QUALIFICATION_SOURCES
                if not callable(canonical_roundtrip.get(label))
            ]
            if missing_roundtrips:
                raise TypeError(
                    "V6-2 exact qualification canonical roundtrip mapping is "
                    f"missing callable labels: {missing_roundtrips}"
                )
        if not callable(canonical_packets_for_vector):
            raise TypeError("V6-2 exact qualification requires live canonical packets")
        if not callable(gamma_canonical_values_for_vector):
            raise TypeError("V6-2 exact qualification requires live Gamma values")
        if not callable(exact_output_canonical_roundtrip):
            raise TypeError("V6-2 exact qualification requires exact-output roundtrip")
        for label in V6_2_EXACT_QUALIFICATION_SOURCES:
            descriptor = descriptors[label]
            if not isinstance(descriptor, Mapping):
                raise TypeError(
                    f"V6-2 exact descriptor {label} is not a mapping"
                )
            if descriptor.get("source_provenance") != frozen_provenance:
                raise ValueError(
                    f"V6-2 exact descriptor {label} is not bound to frozen RHS provenance"
                )
            _v6_2_recompute_source_definition(descriptor)
            relative_metadata = Path(
                f"rank{int(comm.rank):04d}/bottom_{label}_rhs.json"
            )
            metadata_path = _v6_2_resolve_under(
                Path(frozen_root).resolve(), relative_metadata, "metadata_path"
            )
            observed_metadata_hash = hashlib.sha256(
                metadata_path.read_bytes()
            ).hexdigest()
            if descriptor_metadata_hashes[label] != observed_metadata_hash:
                raise ValueError(
                    f"V6-2 descriptor metadata hash differs for {label}"
                )
    except Exception as exc:
        preflight_error = f"{type(exc).__name__}: {exc}"
    _collective_driver_error(operator_comm, "exact qualification preflight", preflight_error)
    assert packet_output_root is not None
    assert frozen_input_root is not None

    identity_error: str | None = None
    lower_identity: Mapping[str, Any] | None = None
    upper_identity: Mapping[str, Any] | None = None
    try:
        lower_identity = gamma_layout_packet_identity(lower_gamma_layout)
        upper_identity = gamma_layout_packet_identity(upper_gamma_layout)
    except Exception as exc:
        identity_error = f"{type(exc).__name__}: {exc}"
    _collective_driver_error(operator_comm, "Gamma layout identity", identity_error)
    assert lower_identity is not None
    assert upper_identity is not None
    expected_gamma_global_sizes = {
        "gamma_l_canonical": int(lower_identity["canonical_global_size"]),
        "gamma_u_canonical": int(upper_identity["canonical_global_size"]),
    }
    construction_error: str | None = None
    identity_provider = None
    packet_writer = None
    packet_consumer = None
    try:
        identity_provider = make_current_exact_packet_identity_provider(
            lower_gamma_layout=lower_gamma_layout,
            upper_gamma_layout=upper_gamma_layout,
        )
        packet_writer = make_current_exact_packet_writer(
            root=packet_output_root,
            rank=int(comm.rank),
            forbidden_root=frozen_input_root,
        )
        packet_consumer = make_current_exact_solution_packet_consumer(
            system=system,
            schur_action=schur_action,
            bare_operator=bare_operator,
            packet_callback=packet_writer,
            canonical_packets_for_vector=canonical_packets_for_vector,
            expected_packet_identity_provider=identity_provider,
            lower_gamma_layout=lower_gamma_layout,
            upper_gamma_layout=upper_gamma_layout,
            gamma_canonical_values_for_vector=gamma_canonical_values_for_vector,
            exact_output_canonical_roundtrip=exact_output_canonical_roundtrip,
            full_residual_tolerance=full_residual_tolerance,
        )
    except Exception as exc:
        construction_error = f"{type(exc).__name__}: {exc}"
    _collective_driver_error(
        operator_comm, "exact qualification packet construction", construction_error
    )
    assert identity_provider is not None
    assert packet_writer is not None
    assert packet_consumer is not None
    family = run_exact_qualification_family(
        descriptors,
        base_directory=base_directory,
        interface_operator=interface_operator,
        bare_operator=bare_operator,
        schur_action=schur_action,
        canonical_roundtrip=canonical_roundtrip,
        right_preconditioner=right_preconditioner,
        initial_labels=V6_2_EXACT_QUALIFICATION_SOURCES[:2],
        restart=restart,
        mandatory_checkpoints=mandatory_checkpoints,
        conditional_checkpoints=conditional_checkpoints,
        authorize_conditional=authorize_conditional,
        resource_callback=resource_callback,
        max_iterations=max_iterations,
        checkpoint_callback=checkpoint_callback,
        accepted_solution_consumer=packet_consumer,
        packetization_required=True,
        validation=validation,
        full_residual_tolerance=full_residual_tolerance,
    )

    initial_pair_gate_pass = bool(family.get("initial_pair_gate_pass"))
    publication_error: str | None = None
    if not initial_pair_gate_pass and int(comm.rank) == 0:
        try:
            if packet_output_root.exists():
                shutil.rmtree(packet_output_root)
        except Exception as exc:
            publication_error = f"{type(exc).__name__}: {exc}"
    _collective_driver_error(
        comm, "initial-pair packet publication", publication_error
    )
    initial_pair_packet_root_exists = packet_output_root.exists()

    packet_records: dict[str, Mapping[str, Any]] = {}
    local_error: str | None = None
    try:
        for record in family.get("source_records", ()):
            if not isinstance(record, Mapping):
                raise TypeError("exact family returned a non-mapping source record")
            label = str(record["label"])
            fgmres = record.get("fgmres")
            if not isinstance(fgmres, Mapping):
                raise TypeError(f"exact family record {label} lacks FGMRES audit")
            full_residual_gate_pass = bool(record.get("full_residual_gate_pass"))
            packetization_gate_error = fgmres.get("packetization_gate_error")
            if packetization_gate_error:
                raise ValueError(
                    f"exact family record {label} has packetization contract error: "
                    f"{packetization_gate_error}"
                )
            accepted_audit = fgmres.get("accepted_solution_packet_audit")
            if not isinstance(accepted_audit, Mapping):
                if not full_residual_gate_pass and not packetization_gate_error:
                    # A source whose independent full-F residual did not meet
                    # the qualification tolerance has no accepted Vec and no
                    # packet by contract.  This is a numerical negative, not
                    # a malformed packet, and the shared continuation may
                    # still inspect the live three-factor service.
                    continue
                raise ValueError(
                    f"exact family record {label} lacks packet audit after "
                    "the full-residual Gate"
                )
            packet_write = accepted_audit.get("packet_write")
            if not isinstance(packet_write, Mapping):
                raise ValueError(
                    f"exact family record {label} lacks packet manifest after "
                    "the full-residual Gate"
                )
            packet_records[label] = packet_write
        if bool(family.get("all_sources_gate_pass")) and set(packet_records) != set(
            V6_2_EXACT_QUALIFICATION_SOURCES
        ):
            raise ValueError("exact family passed without all five packet records")
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_driver_error(comm, "packet record extraction", local_error)

    aggregate_records: dict[str, Any] = {}
    if bool(family.get("all_sources_gate_pass")):
        for label in V6_2_EXACT_QUALIFICATION_SOURCES:
            aggregate_records[label] = aggregate_exact_packet_manifests(
                packet_records[label],
                root=aggregate_root,
                label=label,
                comm=comm,
                source_provenance=source_provenance,
                expected_gamma_global_sizes=expected_gamma_global_sizes,
                qualification_source_provenance=qualification_source_provenance,
                frozen_rhs_descriptor_metadata_sha256=(
                    descriptor_metadata_hashes
                ),
                forbidden_root=frozen_input_root,
            )
    return {
        "schema": "task040.v6_2.exact_qualification_packets.v1",
        "status": (
            "completed_all_sources_and_packet_aggregate"
            if aggregate_records
            else str(
                family.get(
                    "status",
                    "completed_exact_numerical_gate_negative_continuation_allowed",
                )
            )
        ),
        "classification": (
            "V6_EXACT_QUALIFICATION_READY_WITH_PACKETS"
            if aggregate_records
            else "V6_EXACT_QUALIFICATION_GATE_FAIL"
        ),
        "source_order": list(V6_2_EXACT_QUALIFICATION_SOURCES),
        "family": family,
        "packet_root": str(packet_output_root),
        "initial_pair_publication": {
            "initial_pair_gate_pass": initial_pair_gate_pass,
            "status": (
                "passed_then_published"
                if initial_pair_gate_pass
                else "failed_then_discarded"
            ),
            "packet_root_exists_after_gate": initial_pair_packet_root_exists,
        },
        "aggregate_root": str(aggregate_root),
        "frozen_input_root": str(frozen_input_root),
        "frozen_rhs_source_provenance": _json_safe(source_provenance),
        "qualification_source_provenance": _json_safe(current_provenance),
        "frozen_rhs_descriptor_metadata_sha256": _json_safe(
            descriptor_metadata_hashes
        ),
        "operator_identity_bridge": _json_safe(operator_identity_bridge),
        "authority_identity_chain": {
            "frozen_rhs_source_provenance": _json_safe(frozen_provenance),
            "qualification_source_provenance": _json_safe(current_provenance),
            "frozen_rhs_descriptor_metadata_sha256": _json_safe(
                descriptor_metadata_hashes
            ),
            "operator_identity_bridge": _json_safe(operator_identity_bridge),
        },
        "expected_gamma_global_sizes": expected_gamma_global_sizes,
        "packet_aggregate": aggregate_records,
        "packet_aggregate_gate_pass": bool(
            aggregate_records
            and len(aggregate_records) == len(V6_2_EXACT_QUALIFICATION_SOURCES)
        ),
        "numeric_allgather": False,
        "full_numeric_replica": False,
    }


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
    raise TypeError(f"V6-2 value is not JSON-safe: {type(value)!r}")


def _compact_exact_stage_summary(value: Any) -> dict[str, Any]:
    """Keep public source traces while omitting rank-local packet payloads."""

    if not isinstance(value, Mapping):
        return {
            "executed": False,
            "status": "not_run",
            "classification": None,
            "all_sources_gate_pass": False,
            "packet_aggregate_gate_pass": False,
        }
    family = value.get("family")
    source_residual_ledger: list[dict[str, Any]] = []
    if isinstance(family, Mapping):
        for record in family.get("source_records", ()):
            if not isinstance(record, Mapping):
                continue
            fgmres = record.get("fgmres")
            if not isinstance(fgmres, Mapping):
                fgmres = {}
            checkpoints: list[dict[str, Any]] = []
            for checkpoint in fgmres.get("checkpoint_history", ()):
                if not isinstance(checkpoint, Mapping):
                    continue
                compact_checkpoint = {
                    field: checkpoint[field]
                    for field in (
                        "iteration",
                        "checkpoint_kind",
                        "interface_true_residual_norm",
                        "interface_true_residual_relative",
                        "full_true_residual_norm",
                        "full_true_residual_relative",
                        "full_residual_tolerance",
                        "finite",
                        "accepted_full_solution",
                    )
                    if field in checkpoint
                }
                checkpoints.append(compact_checkpoint)
            source_residual_ledger.append(
                {
                    "label": str(record.get("label")),
                    "full_residual_gate_pass": bool(
                        record.get("full_residual_gate_pass", False)
                    ),
                    "best_full_true_residual_relative": record.get(
                        "best_full_true_residual_relative"
                    ),
                    "packetization_gate_pass": bool(
                        record.get("packetization_gate_pass", False)
                    ),
                    "packetization_gate_error": fgmres.get(
                        "packetization_gate_error"
                    ),
                    "accepted_solution_present": bool(
                        fgmres.get("accepted_solution_present", False)
                    ),
                    "accepted_solution_consumed": bool(
                        fgmres.get("accepted_solution_consumed", False)
                    ),
                    "checkpoints": checkpoints,
                }
            )
    packet_aggregate_refs: dict[str, dict[str, Any]] = {}
    packet_aggregate = value.get("packet_aggregate")
    if isinstance(packet_aggregate, Mapping):
        for label, aggregate in packet_aggregate.items():
            if not isinstance(aggregate, Mapping):
                continue
            packet_aggregate_refs[str(label)] = {
                field: aggregate[field]
                for field in (
                    "path",
                    "sha256",
                    "mpi_size",
                    "rank_count",
                    "role_count_per_rank",
                    "frozen_rhs_descriptor_metadata_binding_sha256",
                )
                if field in aggregate
            }
    identity_chain = value.get("authority_identity_chain")
    public_identity_chain: dict[str, Any] = {}
    if isinstance(identity_chain, Mapping):
        for field in (
            "frozen_rhs_source_provenance",
            "qualification_source_provenance",
            "operator_identity_bridge",
        ):
            if field in identity_chain:
                public_identity_chain[field] = identity_chain[field]
    return {
        "executed": True,
        "status": value.get("status"),
        "classification": value.get("classification"),
        "family_status": (
            family.get("status") if isinstance(family, Mapping) else None
        ),
        "family_classification": (
            family.get("classification") if isinstance(family, Mapping) else None
        ),
        "initial_pair_gate_pass": bool(
            family.get("initial_pair_gate_pass")
            if isinstance(family, Mapping)
            else False
        ),
        "all_sources_gate_pass": bool(
            family.get("all_sources_gate_pass")
            if isinstance(family, Mapping)
            else False
        ),
        "initial_pair_publication": _json_safe(
            value.get("initial_pair_publication")
        ),
        "operator_identity_bridge": _json_safe(
            value.get("operator_identity_bridge")
        ),
        "packet_aggregate_gate_pass": bool(
            value.get("packet_aggregate_gate_pass", False)
        ),
        "source_residual_ledger": source_residual_ledger,
        "packet_aggregate_refs": packet_aggregate_refs,
        "authority_identity_chain": public_identity_chain,
    }


def _build_exact_qualification_artifact_reference(
    *,
    rank: int,
    mpi_size: int,
    exact_rank_path: Path,
    output_root: Path,
    source_sha: str,
    exact_result: Mapping[str, Any],
    formal_sequence_start_scope: str,
) -> dict[str, Any]:
    """Build the hash-bound outer reference for one exact rank detail."""

    frozen_provenance = exact_result.get("frozen_rhs_source_provenance", {})
    frozen_descriptor_hashes = exact_result.get(
        "frozen_rhs_descriptor_metadata_sha256", {}
    )
    if not isinstance(frozen_provenance, Mapping):
        raise TypeError("exact result frozen provenance is not a mapping")
    return {
        "rank": int(rank),
        "mpi_size": int(mpi_size),
        "path": str(exact_rank_path.relative_to(output_root)),
        "sha256": "",
        "qualification_source_sha": str(source_sha),
        "frozen_rhs_source_sha": str(frozen_provenance.get("source_sha", "")),
        "frozen_rhs_descriptor_metadata_sha256": _json_safe(
            frozen_descriptor_hashes
        ),
        "formal_sequence_start_scope": str(formal_sequence_start_scope),
    }


def _exact_pde_status(exact_stage_summary: Mapping[str, Any]) -> str:
    """Name the observed exact PDE stage without inferring a Gate result."""

    return (
        "exact_interface_fgmres_with_full_bare_f_residual_run"
        if bool(exact_stage_summary.get("executed"))
        else "not_run_by_v6_2_identity_gate"
    )


def _combined_v6_2_status(
    *,
    identity_gate_pass: bool,
    exact_consensus: bool,
    exact_executed: bool,
    continuation_consensus: bool,
    continuation_executed: bool,
) -> str:
    """Summarize which same-process stages actually ran."""

    if not exact_consensus or not continuation_consensus:
        return "completed_v6_2_rank_consensus_failure"
    if continuation_executed:
        return "completed_v6_2_identity_exact_qualification_and_v6_3_continuation"
    if exact_executed:
        return "completed_v6_2_identity_and_exact_qualification"
    return (
        "completed_v6_2_identity"
        if identity_gate_pass
        else "completed_v6_2_identity_gate_negative"
    )


_V6_2_FORMAL_NUMERIC_OPTIONS = frozenset({"restart"})
_V6_2_FIXED_EXACT_OPTIONS: dict[str, Any] = {
    "mandatory_checkpoints": (16, 32, 64, 128),
    "conditional_checkpoints": (256, 512),
    "max_iterations": 512,
    "full_residual_tolerance": 1.0e-9,
    "right_preconditioner": None,
}


def _v6_2_formal_numeric_options(
    configuration: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Accept only numerical knobs from a formal caller.

    Descriptors, roots, provenance, validation, and physical callbacks are
    authority data.  They are deliberately not caller-configurable on the
    combined benchmark path; they are derived below from the live system and
    the fixed V5 descriptor root.
    """

    if configuration is None:
        return {}
    if not isinstance(configuration, Mapping):
        raise TypeError("V6-2 formal exact configuration must be a mapping")
    unsupported = sorted(
        set(configuration)
        - _V6_2_FORMAL_NUMERIC_OPTIONS
        - set(_V6_2_FIXED_EXACT_OPTIONS)
    )
    if unsupported:
        raise ValueError(
            "V6-2 formal exact configuration contains non-knob authority fields: "
            f"{unsupported}"
        )
    options = {
        key: configuration[key]
        for key in configuration
        if key in _V6_2_FORMAL_NUMERIC_OPTIONS
    }
    if "restart" in options:
        restart = options["restart"]
        if (
            isinstance(restart, bool)
            or not isinstance(restart, (int, np.integer))
            or int(restart) <= 0
        ):
            raise ValueError(
                "V6-2 formal exact restart must be a positive integer"
            )
        options["restart"] = int(restart)
    for key, expected in _V6_2_FIXED_EXACT_OPTIONS.items():
        if key in configuration:
            observed = configuration[key]
            if key in {"mandatory_checkpoints", "conditional_checkpoints"}:
                observed = tuple(observed)
            if observed != expected:
                raise ValueError(
                    f"V6-2 formal fixed option {key} must equal {expected!r}"
                )
        options[key] = expected
    return options


def _v6_2_conditional_authorizer(
    gate_input: Mapping[str, Any],
    *,
    hard_stop_bytes: int,
    budget_seconds: float,
) -> dict[str, Any]:
    """Apply the Review V6 256/512 rules to observed checkpoint data.

    Missing or non-finite observations are a conservative denial.  The
    surrounding FGMRES driver supplies the collective decision protocol, so
    this function performs no MPI operation and never creates a rank-local
    branch by itself.
    """

    history = gate_input.get("checkpoint_history")
    checkpoint = gate_input.get("checkpoint")
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
        history = ()
    try:
        checkpoint_value = int(checkpoint)
    except (TypeError, ValueError):
        checkpoint_value = -1
    by_iteration: dict[int, float] = {}
    for item in history:
        if not isinstance(item, Mapping):
            continue
        try:
            iteration = int(item["iteration"])
            residual = float(item["full_true_residual_relative"])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(residual) and residual >= 0.0:
            by_iteration[iteration] = residual
    resource = gate_input.get("resource_snapshot")
    if not isinstance(resource, Mapping):
        resource = {}
    try:
        rss_bytes = int(resource["rss_bytes"])
        swap_bytes = float(resource["swap_bytes"])
    except (KeyError, TypeError, ValueError):
        rss_bytes = -1
        swap_bytes = float("nan")
    resource_pass = bool(
        resource.get("pass") is True
        and rss_bytes >= 0
        and rss_bytes < int(hard_stop_bytes)
        and np.isfinite(swap_bytes)
        and swap_bytes == 0.0
        and resource.get("all_status_readable") is True
    )
    wall = resource.get("wall_observation")
    if not isinstance(wall, Mapping):
        wall = {}
    try:
        elapsed = float(wall["elapsed_seconds"])
        observed_budget = float(wall["budget_seconds"])
    except (KeyError, TypeError, ValueError):
        elapsed = float("nan")
        observed_budget = float("nan")
    wall_pass = bool(
        np.isfinite(elapsed)
        and elapsed >= 0.0
        and np.isfinite(observed_budget)
        and observed_budget == float(budget_seconds)
        and elapsed < float(budget_seconds)
    )

    residual_gate = False
    residual_observation: dict[str, Any] = {
        "checkpoint": checkpoint_value,
        "r64": by_iteration.get(64),
        "r128": by_iteration.get(128),
        "r256": by_iteration.get(256),
        "drop_64_to_128_decade": None,
        "monotone_history": False,
        "required_checkpoint_iterations": [16, 32, 64, 128, 256],
        "observed_checkpoint_sequence": [
            iteration for iteration, _value in sorted(by_iteration.items())
        ],
    }
    if checkpoint_value == 128:
        r64 = by_iteration.get(64)
        r128 = by_iteration.get(128)
        direct_threshold = r128 is not None and r128 <= 0.8
        drop_gate = False
        if r64 is not None and r128 is not None and r64 > 0.0 and r128 > 0.0:
            drop = float(np.log10(r64 / r128))
            residual_observation["drop_64_to_128_decade"] = drop
            drop_gate = drop >= 0.10
        residual_observation["r128_threshold_gate"] = bool(direct_threshold)
        residual_observation["drop_64_to_128_gate"] = bool(drop_gate)
        residual_gate = bool(direct_threshold or drop_gate)
        target = 256
    elif checkpoint_value == 256:
        r256 = by_iteration.get(256)
        ordered = sorted(by_iteration.items())
        required = (16, 32, 64, 128, 256)
        required_present = all(iteration in by_iteration for iteration in required)
        monotone = required_present and all(
            value <= previous + 1.0e-14
            for (_, previous), (_, value) in zip(ordered, ordered[1:], strict=False)
        )
        residual_observation["monotone_history"] = monotone
        residual_observation["required_checkpoint_set_complete"] = required_present
        residual_gate = r256 is not None and r256 <= 1.0e-2 and monotone
        target = 512
    else:
        target = None
    if target == 256:
        # Review V6 makes 256 a residual-only conditional checkpoint.  The
        # current resource sample is retained as evidence, but an external
        # watchdog remains the authority for hard-stop enforcement and the
        # sample must not become an additional solver Gate here.
        authorized = residual_gate
    elif target == 512:
        authorized = residual_gate and resource_pass and wall_pass
    else:
        authorized = False
    return {
        "authorized": bool(authorized),
        "target_checkpoint": target,
        "residual_gate": bool(residual_gate),
        "resource_gate": bool(resource_pass),
        "wall_gate": bool(wall_pass) if target == 512 else None,
        "resource_observation": {
            "current_rss_bytes": rss_bytes,
            "current_swap_bytes": swap_bytes,
            "current_sample_only": True,
            "external_watchdog_hard_stop_crossed": resource.get(
                "hard_stop_crossed"
            ),
            "dedicated_cgroup_memory_peak_bytes": resource.get(
                "dedicated_cgroup_memory_peak_bytes"
            ),
            "dedicated_cgroup_swap_peak_bytes": resource.get(
                "dedicated_cgroup_swap_peak_bytes"
            ),
            "all_status_readable": resource.get("all_status_readable"),
            "pass": resource.get("pass"),
        },
        "wall_observation": {
            "elapsed_seconds": elapsed,
            "budget_seconds": observed_budget,
        },
        "residual_observation": residual_observation,
        "rule": (
            "256: r128<=0.8 or log10(r64/r128)>=0.10; "
            "512: r256<=1e-2 and monotone history and resource/wall gates"
        ),
    }


def _v6_2_live_resource_callback(
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    *,
    comm: MPI.Intracomm,
    formal_sequence_started: float,
    hard_stop_bytes: int,
    budget_seconds: float,
) -> Callable[[], Mapping[str, Any]]:
    """Bind a collective resource sampler to one monotonic formal start."""

    def observe() -> Mapping[str, Any]:
        if resource_callback is None:
            return {
                "status": "not_provided",
                "pass": False,
                "rss_bytes": None,
                "swap_bytes": None,
                "all_status_readable": False,
                "hard_limit_bytes": int(hard_stop_bytes),
                "wall_observation": {
                    "budget_seconds": float(budget_seconds),
                    "elapsed_seconds": None,
                    "pass": False,
                },
            }
        observed = resource_callback()
        if not isinstance(observed, Mapping):
            raise TypeError("V6-2 exact resource callback must return a mapping")
        local_elapsed = max(
            0.0, float(time.perf_counter() - formal_sequence_started)
        )
        elapsed = float(comm.allreduce(local_elapsed, op=MPI.MAX))
        result = dict(observed)
        result["hard_limit_bytes"] = int(hard_stop_bytes)
        result["formal_sequence_elapsed_seconds"] = elapsed
        result["wall_observation"] = {
            "budget_seconds": float(budget_seconds),
            "elapsed_seconds": elapsed,
            "pass": bool(elapsed < float(budget_seconds)),
            "formula": "elapsed=MAX_rank(monotonic_now-formal_sequence_start)",
        }
        return result

    return observe


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v7_canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_v7_identity_bundle(
    *,
    rank_root: Path,
    output_root: Path,
    raw_metrics: Mapping[str, Any],
    checker_result: Mapping[str, Any],
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    elapsed_seconds: float,
    selected_operator: Mapping[str, Any],
) -> dict[str, Any]:
    raw = _json_safe(raw_metrics)
    checked = _json_safe(checker_result)
    payload = {
        "schema": "task040.v7.scale_normalized_identity.bundle.v1",
        "raw": raw,
        "raw_sha256": _v7_canonical_json_sha256(raw),
        "checker": checked,
        "checker_sha256": _v7_canonical_json_sha256(checked),
        "provenance": {
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "rank": int(rank_root.name.removeprefix("rank")),
        },
        "timing": {
            "identity_elapsed_seconds": float(elapsed_seconds),
            "identity_target_seconds": V7_IDENTITY_TARGET_SECONDS,
            "identity_hard_seconds": V7_IDENTITY_HARD_SECONDS,
        },
        "selected_operator": _json_safe(selected_operator),
    }
    bundle_path = rank_root / "v7_scale_normalized_identity_bundle.json"
    bundle_sha = _write_json(bundle_path, payload)
    readback_sha = hash_file_sha256(bundle_path)
    if readback_sha != bundle_sha:
        raise RuntimeError("V7 identity bundle hash reread failed")
    reopened = json.loads(bundle_path.read_text(encoding="utf-8"))
    if (
        _v7_canonical_json_sha256(reopened["raw"]) != payload["raw_sha256"]
        or _v7_canonical_json_sha256(reopened["checker"])
        != payload["checker_sha256"]
    ):
        raise RuntimeError("V7 identity bundle logical hash reread failed")
    return {
        "rank": int(rank_root.name.removeprefix("rank")),
        "path": str(bundle_path.relative_to(output_root)),
        "sha256": bundle_sha,
        "readback_sha256": readback_sha,
        "readback_valid": True,
        "bundle_readback_valid": True,
        "raw_sha256": payload["raw_sha256"],
        "checker_sha256": payload["checker_sha256"],
        "formal_adjudication": False,
        "d0_pass_candidate": bool(
            checker_result.get("gate_candidates", {}).get("d0_pass_candidate")
        ),
        "d1_pass_candidate": bool(
            checker_result.get("gate_candidates", {}).get("d1_pass_candidate")
        ),
        "evidence_valid": bool(checker_result.get("evidence_valid")),
        "checker_pass": bool(checker_result.get("checker_pass")),
        "selected_candidate": checker_result.get("selected_candidate"),
        "next_required_stage": checker_result.get("next_required_stage"),
        "expected_next_required_stage": (
            "formal_integration_requires_full_spectrum_continuation"
        ),
    }


def _v7_compact_decision_consensus(
    comm: MPI.Intracomm, local: Mapping[str, Any]
) -> dict[str, Any]:
    decisions = comm.allgather(_json_safe(local))

    def same(name: str) -> bool:
        values = [
            json.dumps(item.get(name), sort_keys=True, separators=(",", ":"))
            for item in decisions
        ]
        return bool(values) and len(set(values)) == 1

    elapsed = [item.get("identity_elapsed_seconds") for item in decisions]
    elapsed_valid = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in elapsed
    )
    common = {
        name: local.get(name) if same(name) else None
        for name in (
            "evidence_valid",
            "checker_pass",
            "d0_pass_candidate",
            "d1_pass_candidate",
            "formal_adjudication",
            "selected_candidate",
            "next_required_stage",
            "expected_next_required_stage",
        )
    }
    common.update(
        {
            "mpi_size_8": all(item.get("mpi_size") == 8 for item in decisions),
            "evidence_valid_consensus": same("evidence_valid"),
            "checker_pass_consensus": same("checker_pass"),
            "d0_pass_candidate_consensus": same("d0_pass_candidate"),
            "d1_pass_candidate_consensus": same("d1_pass_candidate"),
            "formal_adjudication_consensus": same("formal_adjudication"),
            "selected_candidate_consensus": same("selected_candidate"),
            "next_required_stage_consensus": same("next_required_stage"),
            "expected_next_required_stage_consensus": same(
                "expected_next_required_stage"
            ),
            "identity_elapsed_seconds_max": (
                max(float(value) for value in elapsed) if elapsed_valid else None
            ),
            "identity_elapsed_target_seconds": V7_IDENTITY_TARGET_SECONDS,
            "identity_elapsed_hard_seconds": V7_IDENTITY_HARD_SECONDS,
            "identity_elapsed_target_exceeded": elapsed_valid
            and any(float(value) > V7_IDENTITY_TARGET_SECONDS for value in elapsed),
            "identity_elapsed_hard_gate": elapsed_valid
            and all(float(value) <= V7_IDENTITY_HARD_SECONDS for value in elapsed),
            "bundle_readback_valid": all(
                item.get("bundle_readback_valid") is True for item in decisions
            ),
            "metadata_only": True,
            "raw_metrics_allgathered": False,
            "numeric_vectors_allgathered": False,
        }
    )
    common["pass"] = bool(
        common["mpi_size_8"]
        and common["evidence_valid_consensus"]
        and common["evidence_valid"] is True
        and common["checker_pass_consensus"]
        and common["checker_pass"] is True
        and common["d0_pass_candidate_consensus"]
        and common["d1_pass_candidate_consensus"]
        and common["formal_adjudication_consensus"]
        and common["formal_adjudication"] is False
        and common["selected_candidate_consensus"]
        and common["selected_candidate"] is not None
        and common["next_required_stage_consensus"]
        and common["expected_next_required_stage_consensus"]
        and common["next_required_stage"]
        == "formal_integration_requires_full_spectrum_continuation"
        and common["identity_elapsed_hard_gate"]
        and common["bundle_readback_valid"]
    )
    return common


def _emit(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(stage, detail)


def _v8_factor_ready_marker(group: int) -> str:
    group = int(group)
    if group not in (0, 1, 2):
        raise ValueError("V8 factor marker requires group0, group1, or group2")
    return f"v8_full_spectrum_group{group}_factor_ready"


def _collective_error(
    comm: MPI.Intracomm,
    stage: str,
    local_error: str | None,
) -> None:
    errors = comm.allgather(local_error)
    first = next(
        ((rank, error) for rank, error in enumerate(errors) if error is not None),
        None,
    )
    if first is not None:
        rank, error = first
        raise RuntimeError(f"V6-2 {stage} failed on rank {rank}: {error}")


def _global_max(comm: MPI.Intracomm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


def _local_mapping_sha256(mapping: Mapping[int, int]) -> str:
    encoded = json.dumps(
        [[int(row), int(position)] for row, position in sorted(mapping.items())],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _support_summary(
    comm: MPI.Intracomm,
    support: np.ndarray,
    *,
    global_count: int,
    global_hash: str,
) -> dict[str, Any]:
    local_hash = hashlib.sha256(
        np.ascontiguousarray(np.asarray(support, dtype=np.int64)).tobytes()
    ).hexdigest()
    return {
        "local_count": int(support.size),
        "local_sha256": local_hash,
        "global_count": int(global_count),
        "global_sha256": str(global_hash),
        "owner_local": True,
        "replicated": False,
        "numeric_allgather": False,
        "support_metadata_replicated": True,
        "rank_local_hashes": comm.allgather(local_hash),
    }


def _resource_preflight(
    comm: MPI.Intracomm,
    run_directory: Path,
    *,
    hard_stop_bytes: int,
    watchdog_hard_stop_bytes: int | None = None,
    minimum_mem_available_bytes: int | None = None,
) -> dict[str, Any]:
    """Record actual V6-2 environment facts before any system construction."""

    from benchmarks.task034_wsl_resources import wsl_memory_snapshot
    from benchmarks.task040_level_a import _worker_current_resource

    worker_hard_stop_bytes = int(hard_stop_bytes)
    observed_watchdog_hard_stop = (
        None if watchdog_hard_stop_bytes is None else int(watchdog_hard_stop_bytes)
    )
    memory = wsl_memory_snapshot()
    disk = shutil.disk_usage(run_directory.parent)
    current = _worker_current_resource(comm, hard_limit_bytes=worker_hard_stop_bytes)
    scalar = np.dtype(PETSc.ScalarType)
    minimum_mem_available_bytes = (
        worker_hard_stop_bytes + V6_2_RESOURCE_HEADROOM_BYTES
        if minimum_mem_available_bytes is None
        else int(minimum_mem_available_bytes)
    )
    thread_environment = {
        name: os.environ.get(name)
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "BLIS_NUM_THREADS",
        )
    }
    mem_available = memory.get("mem_available_bytes")
    local = {
        "comm_size": int(comm.size),
        "petsc_scalar_type": str(scalar),
        "petsc_int_type": str(PETSc.IntType),
        "qualified_activation": os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV")
        == "1",
        "python": sys.executable,
        "mem_available_bytes": mem_available,
        "minimum_mem_available_bytes": minimum_mem_available_bytes,
        "disk_free_bytes": int(disk.free),
        "swap_bytes": int(current.get("swap_bytes", -1)),
        "all_status_readable": bool(current.get("all_status_readable", False)),
        "hard_stop_bytes": worker_hard_stop_bytes,
        "watchdog_hard_stop_bytes": observed_watchdog_hard_stop,
        "thread_environment": thread_environment,
    }
    local["checks"] = {
        "mpi_size_8": local["comm_size"] == 8,
        "petsc_complex128": scalar == np.dtype(np.complex128),
        "qualified_activation": local["qualified_activation"],
        "mem_available_at_least_minimum": (
            isinstance(mem_available, (int, float))
            and not isinstance(mem_available, bool)
            and int(mem_available) >= minimum_mem_available_bytes
        ),
        "disk_at_least_20_gib": local["disk_free_bytes"] >= V6_2_MIN_DISK_FREE_BYTES,
        "swap_zero": local["swap_bytes"] == 0,
        "process_tree_readable": local["all_status_readable"],
        "below_watchdog_hard_stop": bool(current.get("pass", False)),
        "watchdog_hard_stop_matches_worker": (
            observed_watchdog_hard_stop is not None
            and worker_hard_stop_bytes == observed_watchdog_hard_stop
        ),
        "thread_environment_one": all(
            value == "1" for value in thread_environment.values()
        ),
    }
    local["pass"] = all(bool(value) for value in local["checks"].values())
    states = comm.allgather(local)
    checks = {
        name: all(bool(state.get("checks", {}).get(name)) for state in states)
        for name in local["checks"]
    }
    return {
        "schema": "task040.v6_2.resource_preflight.v1",
        "status": "pass" if all(checks.values()) else "not_run_by_resource_preflight",
        "pass": all(checks.values()),
        "checks": checks,
        "ranks": states,
        "hard_stop_bytes": worker_hard_stop_bytes,
        "watchdog_hard_stop_bytes": observed_watchdog_hard_stop,
        "minimum_mem_available_bytes": minimum_mem_available_bytes,
        "minimum_disk_free_bytes": V6_2_MIN_DISK_FREE_BYTES,
        "swap_limit_bytes": 0,
        "numeric_allgather": False,
        "thread_environment_required": {
            name: "1"
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        },
    }


def _stop_result(
    *,
    status: str,
    classification: str,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    identity_preflight: Mapping[str, Any],
    resource_preflight: Mapping[str, Any] | None,
    formal_sequence_start_scope: str = V6_2_FORMAL_SEQUENCE_START_SCOPE,
) -> dict[str, Any]:
    return {
        "schema": V6_2_INTERFACE_SCHUR_SCHEMA,
        "method": V6_2_INTERFACE_SCHUR_METHOD,
        "profile": V6_2_INTERFACE_SCHUR_PROFILE_ID,
        "status": status,
        "classification": classification,
        "source_sha": str(source_sha),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "formal_sequence_start_scope": formal_sequence_start_scope,
        "identity_preflight": _json_safe(identity_preflight),
        "resource_preflight": (
            None if resource_preflight is None else _json_safe(resource_preflight)
        ),
        "system_created": False,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "downstream": {
            "full_spectrum": "not_run_by_v6_2_preflight",
            "moving_pml": "not_run_by_v6_2_preflight",
            "adaptive_schwarz": "not_run_by_v6_2_preflight",
            "factor_free_local_service": "not_run_by_v6_2_preflight",
        },
    }


def _v7_stop_result(
    *,
    status: str,
    classification: str,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    continuation_callable: bool,
    mpi_size_8: bool,
) -> dict[str, Any]:
    identity_preflight = {
        "status": status,
        "pass": False,
        "checks": {
            "continuation_callable": continuation_callable,
            "mpi_size_8": mpi_size_8,
        },
    }
    result = _stop_result(
        status=status,
        classification=classification,
        source_sha=source_sha,
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
        identity_preflight=identity_preflight,
        resource_preflight=None,
    )
    result.update(
        {
            "schema": V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA,
            "method": V7_SCALE_NORMALIZED_IDENTITY_METHOD,
            "profile": V7_SCALE_NORMALIZED_IDENTITY_PROFILE_ID,
            "v7_scale_normalized_identity": True,
            "formal_adjudication": False,
            "v7_classification": classification,
            "v7_progress_gate": {
                "pass": False,
                "continuation_callable": continuation_callable,
                "mpi_size_8": mpi_size_8,
                "system_created": False,
                "exact_not_run": True,
            },
        }
    )
    return result


def _fill_deterministic_interface_vector(vector: PETSc.Vec, vector_index: int) -> None:
    first, last = map(int, vector.getOwnershipRange())
    positions = np.arange(first, last, dtype=np.float64)
    scale = float(vector_index + 1)
    vector.array[:] = PETSc.ScalarType(
        scale * (0.125 + 0.00001 * positions)
        + 1j * (0.03125 * scale + 0.000003 * positions)
    )
    vector.assemble()


def _interior_residual_norm(
    comm: MPI.Intracomm,
    residual: PETSc.Vec,
    interior_rows: np.ndarray,
) -> float:
    first, last = map(int, residual.getOwnershipRange())
    rows = np.asarray(interior_rows, dtype=np.int64)
    if np.any(rows < first) or np.any(rows >= last):
        raise ValueError("V6-2 interior residual rows are not owner-local")
    values = np.asarray(residual.array[rows - first], dtype=np.complex128)
    local_squared = float(np.vdot(values, values).real)
    return float(np.sqrt(max(comm.allreduce(local_squared, op=MPI.SUM), 0.0)))


def _one_identity_probe(
    comm: MPI.Intracomm,
    bare: PETSc.Mat,
    matrix: PETSc.Mat,
    action: Any,
    vector_index: int,
) -> dict[str, Any]:
    source = action.create_interface_vector()
    target = matrix.createVecLeft()
    repeat_target = matrix.createVecLeft()
    residual = bare.createVecLeft()
    full_state: PETSc.Vec | None = None
    extracted: PETSc.Vec | None = None
    repeat_difference: PETSc.Vec | None = None
    roundtrip_difference: PETSc.Vec | None = None
    lower: PETSc.Vec | None = None
    upper: PETSc.Vec | None = None
    roundtrip: PETSc.Vec | None = None
    try:
        _fill_deterministic_interface_vector(source, vector_index)
        matrix.mult(source, target)
        matrix.mult(source, repeat_target)
        repeat_difference = target.duplicate()
        target.copy(repeat_difference)
        repeat_difference.axpy(PETSc.ScalarType(-1.0), repeat_target)

        full_state, state_audit = action.build_full_eliminated_state(source)
        bare.mult(full_state, residual)
        extracted = action.extract_interface_from_active_vector(residual)
        gamma_difference = target.duplicate()
        try:
            target.copy(gamma_difference)
            gamma_difference.axpy(PETSc.ScalarType(-1.0), extracted)
            gamma_error = float(gamma_difference.norm())
        finally:
            gamma_difference.destroy()

        lower, upper = action.restrict_interface(source)
        roundtrip = action.create_interface_vector()
        action.prolong_interface(lower, upper, roundtrip)
        roundtrip_difference = source.duplicate()
        source.copy(roundtrip_difference)
        roundtrip_difference.axpy(PETSc.ScalarType(-1.0), roundtrip)

        interior_error = _interior_residual_norm(
            comm,
            residual,
            np.asarray(state_audit["interior_rows_local"], dtype=np.int64),
        )
        return {
            "vector_index": int(vector_index),
            "gamma_action_error": _global_max(comm, gamma_error),
            "full_interior_residual_error": float(interior_error),
            "solve_count": int(state_audit["group_interior_solve_count"]),
            "roundtrip_error": _global_max(comm, float(roundtrip_difference.norm())),
            "repeat_error": _global_max(comm, float(repeat_difference.norm())),
        }
    finally:
        for vector in (
            roundtrip,
            upper,
            lower,
            roundtrip_difference,
            repeat_difference,
            extracted,
            full_state,
            residual,
            repeat_target,
            target,
            source,
        ):
            if vector is not None:
                vector.destroy()


def _linearity_probe(
    comm: MPI.Intracomm,
    matrix: PETSc.Mat,
    action: Any,
) -> float:
    left = action.create_interface_vector()
    right = action.create_interface_vector()
    combined = action.create_interface_vector()
    left_result = matrix.createVecLeft()
    right_result = matrix.createVecLeft()
    combined_result = matrix.createVecLeft()
    expected = matrix.createVecLeft()
    difference = matrix.createVecLeft()
    try:
        _fill_deterministic_interface_vector(left, 10)
        _fill_deterministic_interface_vector(right, 11)
        left.copy(combined)
        combined.axpy(PETSc.ScalarType(0.37 - 0.21j), right)
        matrix.mult(left, left_result)
        matrix.mult(right, right_result)
        matrix.mult(combined, combined_result)
        left_result.copy(expected)
        expected.scale(PETSc.ScalarType(1.0))
        expected.axpy(PETSc.ScalarType(0.37 - 0.21j), right_result)
        combined_result.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        return _global_max(comm, float(difference.norm()))
    finally:
        for vector in (
            difference,
            expected,
            combined_result,
            right_result,
            left_result,
            combined,
            right,
            left,
        ):
            vector.destroy()


def _v7_fill_scaled_interface_vector(
    vector: PETSc.Vec, index: int, scale: float
) -> None:
    _fill_deterministic_interface_vector(vector, index)
    vector.scale(PETSc.ScalarType(scale))


def _v7_diff(first: PETSc.Vec, second: PETSc.Vec) -> float:
    value = first.duplicate()
    try:
        first.copy(value)
        value.axpy(PETSc.ScalarType(-1.0), second)
        return float(value.norm())
    finally:
        value.destroy()


def _v7_ratio(diff: float, *norms: float) -> float:
    return float(diff) / max(float(sum(norms)), V7_SAFE_DENOMINATOR)


def _v7_repeat(first: PETSc.Vec, second: PETSc.Vec) -> dict[str, Any]:
    n1, n2 = float(first.norm()), float(second.norm())
    diff = _v7_diff(first, second)
    return {
        "terms": {"diff": diff, "n1": n1, "n2": n2},
        "relative": _v7_ratio(diff, n1, n2),
    }


def _v7_identity(diff: float, naction: float, nfull: float) -> dict[str, Any]:
    terms = {"diff": diff, "naction": naction, "nfull": nfull}
    return {"terms": terms, "relative": _v7_ratio(diff, naction, nfull)}


def _v7_linearity(
    diff: float, ncombined: float, nleft: float, nright: float
) -> dict[str, Any]:
    terms = {
        "diff": diff,
        "ncombined": ncombined,
        "nleft": nleft,
        "alpha_abs": float(abs(V7_LINEARITY_ALPHA)),
        "nright": nright,
    }
    return {
        "terms": terms,
        "relative": _v7_ratio(
            diff, ncombined, nleft, float(abs(V7_LINEARITY_ALPHA)) * nright
        ),
    }


def _v7_linear_diff(
    combined: PETSc.Vec, left: PETSc.Vec, right: PETSc.Vec
) -> float:
    value = combined.duplicate()
    try:
        left.copy(value)
        value.scale(PETSc.ScalarType(-1.0))
        value.axpy(PETSc.ScalarType(1.0), combined)
        value.axpy(PETSc.ScalarType(-V7_LINEARITY_ALPHA), right)
        return float(value.norm())
    finally:
        value.destroy()


def _v7_finite(comm: MPI.Intracomm, vectors: Sequence[PETSc.Vec]) -> bool:
    local = all(bool(np.isfinite(np.asarray(vector.array)).all()) for vector in vectors)
    return bool(comm.allreduce(local, op=MPI.LAND))


def _v7_rows(residual: PETSc.Vec, rows: np.ndarray) -> np.ndarray:
    first, last = map(int, residual.getOwnershipRange())
    rows = np.asarray(rows, dtype=np.int64)
    if rows.size and not bool(np.all((rows >= first) & (rows < last))):
        raise ValueError("V7 residual rows are not owner-local")
    return np.asarray(residual.array[rows - first], dtype=np.complex128)


def _v7_norm(comm: MPI.Intracomm, values: np.ndarray) -> float:
    local = float(np.vdot(np.asarray(values, dtype=np.complex128),
                          np.asarray(values, dtype=np.complex128)).real)
    return float(np.sqrt(max(float(comm.allreduce(local, op=MPI.SUM)), 0.0)))


def _v7_full(
    comm: MPI.Intracomm, bare: PETSc.Mat, action: Any, source: PETSc.Vec
) -> tuple[PETSc.Vec, PETSc.Vec, PETSc.Vec, dict[str, Any], float]:
    state, audit = action.build_full_eliminated_state(source)
    residual = bare.createVecLeft()
    try:
        bare.mult(state, residual)
        reference = action.extract_interface_from_active_vector(residual)
        interior = _v7_rows(
            residual, np.asarray(audit["interior_rows_local"], dtype=np.int64)
        )
        return state, residual, reference, audit, _v7_norm(comm, interior)
    except Exception:
        residual.destroy()
        state.destroy()
        raise


def _v7_group_apply(
    action: Any, oracle: Any, group: int, kind: str, source: PETSc.Vec,
    target: PETSc.Vec,
) -> None:
    local = action.restrict_group_interface(group, source)
    try:
        if kind == "middle_boundary":
            oracle.apply_group_gamma_gamma(1, local, target)
        else:
            oracle.apply_group_interior_correction(group, local, target)
    finally:
        local.destroy()


def _v7_layer_b(
    comm: MPI.Intracomm, action: Any, oracle: Any, left: PETSc.Vec,
    right: PETSc.Vec, combined: PETSc.Vec,
) -> dict[str, Any]:
    specs = (
        ("middle_boundary", 1, "middle_boundary"),
        ("middle_correction", 1, "middle_correction"),
        ("lower_correction", 0, "lower_correction"),
        ("upper_correction", 2, "upper_correction"),
    )
    result = {}
    for name, group, kind in specs:
        outputs = {
            label: oracle.create_group_gamma_vector(group)
            for label in ("left", "right", "combined")
        }
        first = oracle.create_group_gamma_vector(group)
        second = oracle.create_group_gamma_vector(group)
        try:
            for label, source in (
                ("left", left), ("right", right), ("combined", combined)
            ):
                _v7_group_apply(action, oracle, group, kind, source, outputs[label])
            _v7_group_apply(action, oracle, group, kind, left, first)
            _v7_group_apply(action, oracle, group, kind, left, second)
            norms = {label: float(value.norm()) for label, value in outputs.items()}
            result[name] = {
                "group": group,
                "output_norms": norms,
                "repeat": _v7_repeat(first, second),
                "linearity": _v7_linearity(
                    _v7_linear_diff(outputs["combined"], outputs["left"], outputs["right"]),
                    norms["combined"], norms["left"], norms["right"],
                ),
                "finite": _v7_finite(
                    comm, [*outputs.values(), first, second]
                ),
            }
        finally:
            second.destroy()
            first.destroy()
            for value in outputs.values():
                value.destroy()
    return result


def _v7_layer_a(
    comm: MPI.Intracomm, action: Any, oracle: Any, source: PETSc.Vec,
    residual: PETSc.Vec,
) -> list[dict[str, Any]]:
    result = []
    for group in range(3):
        rhs = action.create_group_interior_vector(group)
        solution1 = action.create_group_interior_vector(group)
        solution2 = action.create_group_interior_vector(group)
        try:
            before = dict(action.group_factor_diagnostics(group))
            action.build_group_interior_rhs(group, source, rhs)
            action.solve_group_interior_rhs(group, rhs, solution1)
            action.solve_group_interior_rhs(group, rhs, solution2)
            after = dict(action.group_factor_diagnostics(group))
            q = np.asarray(rhs.array, dtype=np.complex128)
            r = _v7_rows(residual, oracle.group_interior_rows_local(group))
            repeat = _v7_repeat(solution1, solution2)
            before_count = int(before.get("solve_count", -1))
            after_count = int(after.get("solve_count", -1))
            residual_norm = _v7_norm(comm, r)
            rhs_norm = float(rhs.norm())
            n_aii_x = _v7_norm(comm, r - q)
            result.append(
                {
                    "group": group,
                    "rhs_norm": rhs_norm,
                    "solution1_norm": float(solution1.norm()),
                    "solution2_norm": float(solution2.norm()),
                    "solve_count_before": before_count,
                    "solve_count_after": after_count,
                    "solve_count_delta": after_count - before_count,
                    "factor_identity_before": before.get("factor_identity"),
                    "factor_identity_after": after.get("factor_identity"),
                    "factor_diagnostics_before": _json_safe(before),
                    "factor_diagnostics_after": _json_safe(after),
                    "backward": {
                        "terms": {
                            "residual": residual_norm,
                            "n_aii_x": n_aii_x,
                            "n_rhs": rhs_norm,
                        },
                        "relative": _v7_ratio(residual_norm, n_aii_x, rhs_norm),
                    },
                    "repeat": repeat,
                    "finite": _v7_finite(comm, [rhs, solution1, solution2]),
                }
            )
        finally:
            solution2.destroy()
            solution1.destroy()
            rhs.destroy()
    return result


def _v7_variant(
    comm: MPI.Intracomm, first: PETSc.Vec, second: PETSc.Vec,
    reference: PETSc.Vec,
) -> dict[str, Any]:
    naction, nfull = float(first.norm()), float(reference.norm())
    return {
        "output_norm": naction,
        "finite": _v7_finite(comm, [first]),
        "identity": _v7_identity(_v7_diff(first, reference), naction, nfull),
        "repeat": _v7_repeat(first, second),
    }


def _v7_apply_d1(
    action: Any, source: PETSc.Vec, target: PETSc.Vec,
    contributions: Mapping[str, PETSc.Vec],
) -> None:
    action.apply_d1_reference(
        source, target, *(contributions[name] for name in V7_D1_CONTRIBUTION_ORDER)
    )


def _v7_identity_record(
    comm: MPI.Intracomm, bare: PETSc.Mat, matrix: PETSc.Mat, action: Any,
    oracle: Any, source_index: int, exponent: int, scale: float,
) -> dict[str, Any]:
    source = action.create_interface_vector()
    d0_first, d0_second = (matrix.createVecLeft() for _ in range(2))
    d1_first, d1_second = (action.create_interface_vector() for _ in range(2))
    contributions = {
        name: action.create_interface_vector()
        for name in V7_D1_CONTRIBUTION_ORDER
    }
    first_contributions = {
        name: action.create_interface_vector()
        for name in V7_D1_CONTRIBUTION_ORDER
    }
    state = residual = reference = None
    try:
        _v7_fill_scaled_interface_vector(source, source_index, scale)
        matrix.mult(source, d0_first)
        matrix.mult(source, d0_second)
        _v7_apply_d1(action, source, d1_first, contributions)
        for name, contribution in contributions.items():
            contribution.copy(first_contributions[name])
        _v7_apply_d1(action, source, d1_second, contributions)
        state, residual, reference, audit, interior_norm = _v7_full(
            comm, bare, action, source
        )
        lower, upper = action.restrict_interface(source)
        roundtrip = action.create_interface_vector()
        try:
            action.prolong_interface(lower, upper, roundtrip)
            roundtrip_error = _v7_diff(source, roundtrip)
        finally:
            roundtrip.destroy()
            upper.destroy()
            lower.destroy()
        d0_record = _v7_variant(comm, d0_first, d0_second, reference)
        d1_record = _v7_variant(comm, d1_first, d1_second, reference)
        d0_d1_diff = _v7_diff(d0_first, d1_first)
        d0_norm, d1_norm = float(d0_first.norm()), float(d1_first.norm())
        return {
            "source_index": source_index,
            "scale_exponent": exponent,
            "scale": scale,
            "source_norm": float(source.norm()),
            "layer_a": {"groups": _v7_layer_a(
                comm, action, oracle, source, residual
            )},
            "layer_c": {
                "full": {
                    "output_norm": float(reference.norm()),
                    "interior_residual_norm": interior_norm,
                    "finite": _v7_finite(comm, [reference]),
                },
                "d0": d0_record,
                "d1": d1_record,
                "d0_d1": {
                    "terms": {"diff": d0_d1_diff, "nd0": d0_norm, "nd1": d1_norm},
                    "eta": _v7_ratio(d0_d1_diff, d0_norm, d1_norm),
                },
                "contribution_output_norms": {
                    name: {
                        "output_norm": float(value.norm()),
                        "finite": _v7_finite(comm, [value]),
                    }
                    for name, value in first_contributions.items()
                },
                "roundtrip_error": roundtrip_error,
                "full_state_audit": _json_safe(audit),
            },
        }
    finally:
        for value in first_contributions.values():
            value.destroy()
        for value in contributions.values():
            value.destroy()
        for value in (d1_second, d1_first, d0_second, d0_first, source):
            value.destroy()
        if reference is not None:
            reference.destroy()
        if residual is not None:
            residual.destroy()
        if state is not None:
            state.destroy()


def _v7_linearity_record(
    comm: MPI.Intracomm, matrix: PETSc.Mat, action: Any, oracle: Any,
    exponent: int, scale: float,
) -> dict[str, Any]:
    left, right, combined = (
        action.create_interface_vector() for _ in range(3)
    )
    d0 = {name: matrix.createVecLeft() for name in ("left", "right", "combined")}
    d1 = {name: action.create_interface_vector() for name in d0}
    contributions = {
        name: action.create_interface_vector()
        for name in V7_D1_CONTRIBUTION_ORDER
    }
    try:
        _v7_fill_scaled_interface_vector(left, V7_LINEARITY_VECTOR_INDICES[0], scale)
        _v7_fill_scaled_interface_vector(right, V7_LINEARITY_VECTOR_INDICES[1], scale)
        left.copy(combined)
        combined.axpy(PETSc.ScalarType(V7_LINEARITY_ALPHA), right)
        input_norms = {
            name: float(value.norm())
            for name, value in (("left", left), ("right", right), ("combined", combined))
        }
        for name, source in (
            ("left", left), ("right", right), ("combined", combined)
        ):
            matrix.mult(source, d0[name])
            _v7_apply_d1(action, source, d1[name], contributions)

        def variant(values: Mapping[str, PETSc.Vec]) -> dict[str, Any]:
            norms = {name: float(value.norm()) for name, value in values.items()}
            return {
                "output_norms": norms,
                **_v7_linearity(
                    _v7_linear_diff(values["combined"], values["left"], values["right"]),
                    norms["combined"], norms["left"], norms["right"],
                ),
                "finite": _v7_finite(comm, list(values.values())),
            }

        return {
            "scale_exponent": exponent,
            "scale": scale,
            "left_source_index": V7_LINEARITY_VECTOR_INDICES[0],
            "right_source_index": V7_LINEARITY_VECTOR_INDICES[1],
            "alpha": {
                "real": float(V7_LINEARITY_ALPHA.real),
                "imag": float(V7_LINEARITY_ALPHA.imag),
                "abs": float(abs(V7_LINEARITY_ALPHA)),
            },
            "input_norms": input_norms,
            "layer_b": _v7_layer_b(comm, action, oracle, left, right, combined),
            "layer_c": {"d0": variant(d0), "d1": variant(d1)},
        }
    finally:
        for value in contributions.values():
            value.destroy()
        for value in d1.values():
            value.destroy()
        for value in d0.values():
            value.destroy()
        combined.destroy()
        right.destroy()
        left.destroy()


def _v7_legacy_absolute_diagnostic(
    matrix: PETSc.Mat, action: Any, identity_records: Sequence[Mapping[str, Any]],
    linearity_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source, target = action.create_interface_vector(), matrix.createVecLeft()
    try:
        source.set(0.0)
        source.assemble()
        matrix.mult(source, target)
        zero_error = float(target.norm())
    finally:
        target.destroy()
        source.destroy()
    records = sorted(
        (item for item in identity_records if int(item["scale_exponent"]) == 0),
        key=lambda item: int(item["source_index"]),
    )
    linearity = next(
        item for item in linearity_records if int(item["scale_exponent"]) == 0
    )
    deterministic = [
        {
            "vector_index": int(item["source_index"]),
            "gamma_action_error": float(item["layer_c"]["d0"]["identity"]["terms"]["diff"]),
            "full_interior_residual_error": float(
                item["layer_c"]["full"]["interior_residual_norm"]
            ),
            "roundtrip_error": float(item["layer_c"]["roundtrip_error"]),
            "repeat_error": float(item["layer_c"]["d0"]["repeat"]["terms"]["diff"]),
        }
        for item in records
    ]
    thresholds = {
        "zero_map": float(V6_2_ZERO_TOLERANCE),
        "repeat": float(V6_2_ROUNDTRIP_TOLERANCE),
        "linearity": float(V6_2_ROUNDTRIP_TOLERANCE),
        "restriction_prolongation": float(V6_2_ROUNDTRIP_TOLERANCE),
        "full_elimination_gamma": float(V6_2_ACTION_TOLERANCE),
        "full_elimination_interior": float(V6_2_ACTION_TOLERANCE),
    }
    values = {
        "zero_map": zero_error,
        "repeat": max(item["repeat_error"] for item in deterministic),
        "linearity": float(linearity["layer_c"]["d0"]["terms"]["diff"]),
        "restriction_prolongation": max(item["roundtrip_error"] for item in deterministic),
        "full_elimination_gamma": max(item["gamma_action_error"] for item in deterministic),
        "full_elimination_interior": max(item["full_interior_residual_error"] for item in deterministic),
    }
    gate = {name: values[name] <= limit for name, limit in thresholds.items()}
    gate["three_deterministic_vectors"] = len(deterministic) == 3
    return {
        "scale_exponent": 0,
        "scale": 1.0,
        "deterministic": deterministic,
        "zero_error": zero_error,
        "linearity_error": values["linearity"],
        "thresholds": thresholds,
        "gate": gate,
        "gate_pass": bool(all(gate.values())),
        "relative_metrics_not_used": True,
    }


def _v7_structural_diagnostics(action: Any) -> dict[str, Any]:
    diagnostics = action.diagnostics
    layout = diagnostics["interface_layout"]
    return {
        "layout": {
            "global_size": int(layout["global_size"]),
            "lower_global_rows": int(layout["lower_global_rows"]),
            "upper_global_rows": int(layout["upper_global_rows"]),
            "owner_local_mapping_count": int(layout["owner_local_mapping_count"]),
            "canonical_position_bijection": bool(
                layout["canonical_position_bijection"]
            ),
            "coverage_exact": bool(layout["coverage_exact"]),
            "owner_distributed": bool(layout["owner_distributed"]),
        },
        "factor_count_ready": int(diagnostics["factor_count_ready"]),
        "factor_count_ready_observed": int(
            diagnostics["factor_count_ready_observed"]
        ),
        "numeric_allgather": bool(diagnostics["numeric_allgather"]),
        "fe_numeric_allgather": bool(diagnostics["fe_numeric_allgather"]),
        "full_interface_numeric_replica": bool(
            diagnostics["full_interface_numeric_replica"]
        ),
        "scratch_vectors_allocated_per_apply": int(
            diagnostics["scratch_vectors_allocated_per_apply"]
        ),
    }


def collect_v7_scale_normalized_identity_metrics(
    comm: MPI.Intracomm, bare: PETSc.Mat, matrix: PETSc.Mat, action: Any, oracle: Any
) -> dict[str, Any]:
    """Collect norms and raw terms only; this is not formal adjudication."""
    structure_before = _v7_structural_diagnostics(action)
    identities = [
        _v7_identity_record(
            comm, bare, matrix, action, oracle, source, exponent, float(2.0**exponent)
        )
        for exponent in V7_SCALE_EXPONENTS
        for source in V7_IDENTITY_VECTOR_INDICES
    ]
    linearities = [
        _v7_linearity_record(
            comm, matrix, action, oracle, exponent, float(2.0**exponent)
        )
        for exponent in V7_SCALE_EXPONENTS
    ]
    structure_after = _v7_structural_diagnostics(action)
    groups = identities[0]["layer_a"]["groups"]
    return {
        "schema": V7_SCALE_NORMALIZED_IDENTITY_SCHEMA,
        "status": "diagnostics_only",
        "classification": "not_formal_adjudication",
        "formal_adjudication": False,
        "next_required_stage": "independent_raw_checker_then_formal_integration",
        "safe_denominator": float(V7_SAFE_DENOMINATOR),
        "identity_source_indices": list(V7_IDENTITY_VECTOR_INDICES),
        "linearity_source_indices": list(V7_LINEARITY_VECTOR_INDICES),
        "scales": [
            {"exponent": exponent, "scale": float(2.0**exponent)}
            for exponent in V7_SCALE_EXPONENTS
        ],
        "linearity_alpha": {
            "real": float(V7_LINEARITY_ALPHA.real),
            "imag": float(V7_LINEARITY_ALPHA.imag),
            "abs": float(abs(V7_LINEARITY_ALPHA)),
        },
        "d1_contribution_order": list(V7_D1_CONTRIBUTION_ORDER),
        "structure": {"before": structure_before, "after": structure_after},
        "factor_setup": {
            "same_action": True,
            "same_factor_setup": True,
            "factor_identity_by_group": {
                str(item["group"]): item["factor_identity_before"] for item in groups
            },
            "factor_readback_by_group": {
                str(item["group"]): item["factor_diagnostics_before"] for item in groups
            },
        },
        "identity_records": identities,
        "linearity_records": linearities,
        "legacy_v6_2_absolute_diagnostic": _v7_legacy_absolute_diagnostic(
            matrix, action, identities, linearities
        ),
        "runner_claims": {
            "gate_pass": None,
            "classification": "not_formal_adjudication",
        },
    }


def _run_v8_adaptive_stage_a_route(
    *,
    system: Any,
    beta: complex,
    quadrature_degree: int,
    event_callback: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Run the one-source Stage-A pilot on one current bare-F system."""

    from src.solvers.hybrid_adaptive_impedance_screen import (
        run_adaptive_impedance_stage_a_one_apply,
    )
    from src.solvers.hybrid_bare_f_authority import build_current_bare_f_rhs

    source = None
    source_audit: Mapping[str, Any] | None = None
    result: dict[str, Any] | None = None
    source_destroyed = False
    try:
        source, source_audit = build_current_bare_f_rhs(
            system, "external_dtn_coupling"
        )
        evidence = run_adaptive_impedance_stage_a_one_apply(
            function_space=system.V,
            condensed=system.static_condensation.condensed,
            bare_f=system.F,
            source=source,
            source_label="external_dtn_coupling",
            beta=beta,
            quadrature_degree=quadrature_degree,
            event_callback=event_callback,
        )
        checks = dict(evidence.get("gate_checks", {}))
        result = {
            "schema": V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA,
            "method": V8_ADAPTIVE_SCHWARZ_ONLY_METHOD,
            "profile": V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID,
            "status": "completed_adaptive_stage_a",
            "classification": (
                "V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS"
                if all(bool(value) for value in checks.values())
                else "V8_ADAPTIVE_STAGE_A_LOCAL_GATE_FAIL"
            ),
            "pass": None,
            "local_gate_pass": all(bool(value) for value in checks.values()),
            "resource_gate": "pending_watchdog",
            "formal_adjudication": False,
            "executed": True,
            "source_order": ["external_dtn_coupling"],
            "source_build_audit": _json_safe(source_audit),
            "beta": [float(complex(beta).real), float(complex(beta).imag)],
            "quadrature_degree": int(quadrature_degree),
            "stage_a_gate": checks,
            "evidence": _json_safe(evidence),
            "system_created": True,
            "gamma_canonical_interface_built": False,
            "group_factors_built": False,
            "fgmres": "not_run",
        }
    finally:
        if source is not None:
            source.destroy()
            source_destroyed = True
        if result is not None:
            result["source_destroyed"] = source_destroyed
    if result is None:
        raise RuntimeError("adaptive Stage-A route produced no result")
    return _json_safe(result)


def run_v6_2_interface_schur(
    cfg: Any,
    profile: Any,
    *,
    comm: MPI.Intracomm,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    input_path: str | Path,
    input_sha256: str,
    physical_model_sha256: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    watchdog_enabled: bool = False,
    bottom_route_only: bool = False,
    hard_stop_bytes: int = 45 * 2**30,
    watchdog_hard_stop_bytes: int | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    exact_qualification: Mapping[str, Any] | None = None,
    v7_scale_normalized_identity: bool = False,
    v7_moving_pml_full_state: bool = False,
    v8_full_spectrum_only: bool = False,
    v8_adaptive_schwarz_only: bool = False,
    v6_3_continuation: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    v7_continuation: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run identity and exact qualification on one live current system."""

    # This is the single clock origin for the whole worker sequence.  It must
    # include authority/root, ABI/resource preflight, directory setup, system
    # assembly, identity probes, exact qualification, and any continuation.
    # Do not move it below a preflight or artifact-write boundary.
    formal_sequence_started = time.perf_counter()
    formal_sequence_start_scope = V6_2_FORMAL_SEQUENCE_START_SCOPE

    from benchmarks.task040_level_a import (
        TASK040_LEVEL_A_TIMEOUT_SECONDS,
        _petsc_matrix_hash,
        _v5_authority_identity_preflight,
        _v5_selected_mode_provider,
        _v5_write_operator_semantics_audit,
        assemble_current_bare_f_authority_system,
        audit_artificial_z_interface_support,
        build_current_gamma_layout,
        level_a_bottom_beta,
    )

    output_argument = Path(run_directory)
    if not output_argument.is_absolute():
        raise ValueError("V6-2 output root must be absolute")
    output_root, frozen_root = _assert_disjoint_roots(
        output_argument, exact_spool_root
    )
    if v7_scale_normalized_identity and not callable(v7_continuation):
        return _v7_stop_result(
            status="not_run_by_v7_continuation_gate",
            classification="V7_SCALE_NORMALIZED_IDENTITY_NOT_RUN",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            continuation_callable=False,
            mpi_size_8=int(comm.size) == 8,
        )
    if v7_scale_normalized_identity and int(comm.size) != 8:
        return _v7_stop_result(
            status="not_run_by_v7_mpi_size_gate",
            classification="V7_SCALE_NORMALIZED_IDENTITY_NOT_RUN",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            continuation_callable=True,
            mpi_size_8=False,
        )
    if v8_full_spectrum_only and int(comm.size) != 8:
        return _stop_result(
            status="not_run_by_v8_mpi_size_gate",
            classification="V8_FULL_SPECTRUM_NOT_RUN",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            identity_preflight={
                "status": "mpi_size_gate",
                "pass": False,
                "checks": {"mpi_size_8": False},
            },
            resource_preflight=None,
        ) | {
            "schema": V8_FULL_SPECTRUM_ONLY_SCHEMA,
            "method": V8_FULL_SPECTRUM_ONLY_METHOD,
            "profile": V8_FULL_SPECTRUM_ONLY_PROFILE_ID,
            "formal_adjudication": False,
        }
    if v8_adaptive_schwarz_only and int(comm.size) != 8:
        return _stop_result(
            status="not_run_by_v8_adaptive_mpi_size_gate",
            classification="V8_ADAPTIVE_STAGE_A_NOT_RUN",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            identity_preflight={
                "status": "mpi_size_gate",
                "pass": False,
                "checks": {"mpi_size_8": False},
            },
            resource_preflight=None,
        ) | {
            "schema": V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA,
            "method": V8_ADAPTIVE_SCHWARZ_ONLY_METHOD,
            "profile": V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID,
            "formal_adjudication": False,
        }
    if v7_moving_pml_full_state and int(comm.size) != 8:
        moving_stop = _stop_result(
            status="not_run_by_v7_moving_pml_mpi_size_gate",
            classification="V7_MOVING_PML_FULL_STATE_NOT_RUN",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            identity_preflight={
                "status": "mpi_size_gate",
                "pass": False,
                "checks": {"mpi_size_8": False},
            },
            resource_preflight=None,
        )
        moving_stop.update(
            {
                "schema": V7_MOVING_PML_FULL_STATE_SCHEMA,
                "method": V7_MOVING_PML_FULL_STATE_METHOD,
                "profile": V7_MOVING_PML_FULL_STATE_PROFILE_ID,
                "formal_adjudication": False,
            }
        )
        return moving_stop
    authority_root_error: str | None = None
    try:
        frozen_root = _v6_2_require_v5_rhs_authority_root(frozen_root)
    except Exception as exc:
        authority_root_error = f"{type(exc).__name__}: {exc}"
    _collective_driver_error(
        comm, "V5 RHS authority-root preflight", authority_root_error
    )

    identity_preflight = _v5_authority_identity_preflight(
        comm=comm,
        input_path=input_path,
        input_sha256=str(input_sha256),
        physical_model_sha256=str(physical_model_sha256),
        source_sha=str(source_sha),
        watchdog_enabled=watchdog_enabled,
        bottom_route_only=bottom_route_only,
    )
    audit_file = _v5_write_operator_semantics_audit(
        comm,
        output_root,
        identity_preflight.get("operator_semantics_audit"),
    )
    identity_preflight = {**identity_preflight, "operator_semantics_audit_file": audit_file}
    _emit(
        marker_callback,
        "v6_2_identity_preflight",
        status=identity_preflight["status"],
        **{"pass": bool(identity_preflight["pass"])},
    )
    if not identity_preflight["pass"]:
        return _stop_result(
            status="not_run_by_identity_preflight",
            classification="V6_2_INTERFACE_IDENTITY_FAIL",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            identity_preflight=identity_preflight,
            resource_preflight=None,
            formal_sequence_start_scope=formal_sequence_start_scope,
        )

    resource_preflight = _resource_preflight(
        comm,
        output_root,
        hard_stop_bytes=int(hard_stop_bytes),
        watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
        minimum_mem_available_bytes=(
            V8_FULL_SPECTRUM_MIN_AVAILABLE_BYTES if v8_full_spectrum_only else None
        ),
    )
    _emit(
        marker_callback,
        "v6_2_resource_preflight",
        status=resource_preflight["status"],
        **{"pass": bool(resource_preflight["pass"])},
        checks=resource_preflight["checks"],
    )
    if not resource_preflight["pass"]:
        return _stop_result(
            status="not_run_by_resource_preflight",
            classification="V6_2_INTERFACE_RESOURCE_BLOCKED",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            identity_preflight=identity_preflight,
            resource_preflight=resource_preflight,
            formal_sequence_start_scope=formal_sequence_start_scope,
        )

    adaptive_marker_state: dict[str, Any] = {
        "last_wall": formal_sequence_started,
        "factor_lifecycle": {"ready": 0},
        "screen_cleanup": {},
    }
    adaptive_event_callback = None
    adaptive_marker_resource_callback = None
    if v8_adaptive_schwarz_only:
        adaptive_marker_resource_callback = _v6_2_live_resource_callback(
            resource_callback,
            comm=comm,
            formal_sequence_started=formal_sequence_started,
            hard_stop_bytes=int(hard_stop_bytes),
            budget_seconds=float(V8_ADAPTIVE_TIMEOUT_SECONDS),
        )

        def adaptive_mark(stage: str, **detail: Any) -> None:
            now = time.perf_counter()
            stage_start = adaptive_marker_state["last_wall"]
            if stage.endswith("_one_apply_begin"):
                adaptive_marker_state["one_apply_wall"] = now
            elif stage.endswith("_one_apply_end"):
                stage_start = adaptive_marker_state.get("one_apply_wall", stage_start)
            resource = adaptive_marker_resource_callback()
            factor_lifecycle = detail.get(
                "factor_lifecycle", adaptive_marker_state["factor_lifecycle"]
            )
            adaptive_marker_state["factor_lifecycle"] = dict(factor_lifecycle)
            _emit(
                marker_callback,
                stage,
                status="running" if stage.endswith("_begin") else "complete",
                formal_wall_seconds=float(now - formal_sequence_started),
                stage_wall_seconds=float(now - stage_start),
                rss_bytes=resource.get("rss_bytes"),
                swap_bytes=resource.get("swap_bytes"),
                resource=_json_safe(resource),
                pc_apply_count=detail.get("pc_apply_count"),
                action_apply_count=detail.get("action_apply_count"),
                factor_lifecycle=_json_safe(factor_lifecycle),
                source=detail.get("source"),
                checkpoint=detail.get("checkpoint"),
                **{
                    key: _json_safe(value)
                    for key, value in detail.items()
                    if key
                    not in {
                        "pc_apply_count",
                        "action_apply_count",
                        "factor_lifecycle",
                        "source",
                        "checkpoint",
                    }
                },
            )
            adaptive_marker_state["last_wall"] = now

        def adaptive_event(event: str, detail: Mapping[str, Any]) -> None:
            stages = {
                "factor_ready": "v8_adaptive_factor_ready",
                "one_apply_begin": "v8_adaptive_external_one_apply_begin",
                "one_apply_end": "v8_adaptive_external_one_apply_end",
                "checkpoint": "v8_adaptive_checkpoint",
            }
            if event == "cleanup":
                adaptive_marker_state["screen_cleanup"] = dict(detail)
                return
            adaptive_mark(stages[event], **dict(detail))

        adaptive_mark(
            "v8_adaptive_preflight",
            system_created=False,
            factor_lifecycle={"ready": 0},
            pc_apply_count=0,
            action_apply_count=0,
            source=None,
            checkpoint=None,
            resource_limits={
                "preferred_memory_bytes": V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
                "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "setup_target_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                "one_apply_target_seconds": V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
                "total_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                "swap_limit_bytes": 0,
            },
        )

    v8_marker_payload: dict[str, Any] | None = None
    v8_marker_resource_callback = (
        resource_callback if callable(resource_callback) else dict
    )
    if v8_full_spectrum_only:
        from src.solvers.hybrid_full_spectrum_screen import _v8_mark

        v8_marker_payload = {"marker_callback": marker_callback}
        _v8_mark(
            v8_marker_payload,
            "v8_full_spectrum_preflight",
            formal_sequence_started,
            v8_marker_resource_callback,
            None,
            resource_preflight=_json_safe(resource_preflight),
            system_created=False,
            factor_lifecycle={"ready": 0, "after_cleanup": None},
            pc_apply_count=0,
            action_apply_count=0,
        )

    if comm.rank == 0:
        output_root.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    rank_root = output_root / f"rank{int(comm.rank):04d}"
    rank_root.mkdir(parents=True, exist_ok=False)
    comm.barrier()

    system = None
    matrix = None
    action = None
    v7_d1_matrix: PETSc.Mat | None = None
    v7_raw_metrics: Mapping[str, Any] | None = None
    v7_checker_result: Mapping[str, Any] | None = None
    v7_bundle_descriptor: dict[str, Any] | None = None
    v7_progress_gate: dict[str, Any] | None = None
    v7_compact_consensus: dict[str, Any] | None = None
    v7_rank_bundle_descriptors: list[dict[str, Any]] = []
    v7_classification: str | None = None
    v7_continuation_result: Mapping[str, Any] | None = None
    v7_factor_lifecycle_after_continuation: Mapping[str, Any] | None = None
    shared_lifecycle: Mapping[str, Any] | None = None
    result: dict[str, Any] | None = None
    exact_budget_seconds = (
        V8_FULL_SPECTRUM_TIMEOUT_SECONDS
        if v8_full_spectrum_only
        else TASK040_LEVEL_A_TIMEOUT_SECONDS
    )
    try:
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=float(profile.bottom_interface_nm),
            top_interface_z_nm=float(profile.top_interface_nm),
            source_work_directory=output_root / "source",
            selected_mode_provider=(
                _v5_selected_mode_provider(comm)
                if v7_moving_pml_full_state or v8_full_spectrum_only
                else None
            ),
            external_mode_authority=identity_preflight["external_mode_authority"],
            external_mode_current_resolved_config_sha256=str(
                identity_preflight["observed"]["resolved_config_sha256"]
            ),
            source_factor_marker_callback=(
                marker_callback
                if v7_moving_pml_full_state or v8_full_spectrum_only
                else None
            ),
            comm=comm,
        )
        inventory = dict(system.construction_inventory)
        matrix_objects = dict(system.dtn_objects_constructed)
        if any(int(matrix_objects.get(name, -1)) != 0 for name in ("C", "D", "H")):
            raise RuntimeError("V6-2 bare-F assembly constructed C/D/H")
        if int(inventory.get("qep_calls", -1)) != 0:
            raise RuntimeError("V6-2 bare-F assembly observed qep_calls != 0")
        if any(
            bool(inventory.get(name))
            for name in (
                "physical_dtn_operator_constructed",
                "woodbury_inverse_constructed",
                "research_exact_side_lu_action_called",
            )
        ):
            raise RuntimeError("V6-2 assembly entered a forbidden side-operator path")
        _emit(
            marker_callback,
            "v6_2_system_ready",
            side="bottom",
            bare_f_rows=int(system.active_rows),
            factored_operator="none",
            matrix_objects=matrix_objects,
            qep_calls=0,
            full_side_exact_factor_count=0,
        )
        if v8_full_spectrum_only:
            _v8_mark(
                v8_marker_payload,
                "v8_full_spectrum_system_ready",
                formal_sequence_started,
                v8_marker_resource_callback,
                action,
                system_created=True,
                matrix_objects=matrix_objects,
                qep_calls=0,
                factor_lifecycle={"ready": 0, "after_cleanup": None},
                pc_apply_count=0,
                action_apply_count=0,
            )
        if v8_adaptive_schwarz_only:
            adaptive_mark(
                "v8_adaptive_system_ready",
                system_created=True,
                factor_lifecycle={"ready": 0},
                pc_apply_count=0,
                action_apply_count=0,
                source=None,
                checkpoint=None,
                bare_f_rows=int(system.active_rows),
                matrix_objects=matrix_objects,
                qep_calls=0,
                gamma_canonical_interface_built=False,
                group_factors_built=False,
            )
            result = _run_v8_adaptive_stage_a_route(
                system=system,
                beta=level_a_bottom_beta(cfg),
                quadrature_degree=2 * int(cfg.nedelec_degree),
                event_callback=adaptive_event_callback,
            )
            evidence = result.get("evidence", {})
            result.update(
                {
                    "source_sha": str(source_sha),
                    "input_sha256": str(input_sha256),
                    "physical_model_sha256": str(physical_model_sha256),
                    "identity_preflight": _json_safe(identity_preflight),
                    "resource_preflight": _json_safe(resource_preflight),
                    "system_inventory": {
                        "rank": int(comm.rank),
                        "mpi_size": int(comm.size),
                        "active_rows": int(
                            system.static_condensation.condensed.active_rows
                        ),
                        "full_rows": int(
                            system.static_condensation.condensed.full_rows
                        ),
                        "bare_f_shape": [int(value) for value in system.F.getSize()],
                    },
                    "matrix_objects": {
                        "bare_f": "borrowed",
                        "source": "caller_owned_until_route_finally",
                        "gamma_canonical_interface": 0,
                        "group_factors": 0,
                        "qep": 0,
                        "full_side_factor": 0,
                        "global_factor": 0,
                    },
                    "qep_calls": 0,
                    "full_side_factor_count": 0,
                    "global_factor_count": 0,
                    "global_summary": {
                        "mpi_size": int(comm.size),
                        "source_order": list(result["source_order"]),
                        "stage_a_gate": dict(result["stage_a_gate"]),
                        "patch_residual_summary": _json_safe(
                            evidence.get("patch_residual_summary", {})
                        ),
                        "true_residual_relative": evidence.get(
                            "true_residual_relative"
                        ),
                    },
                }
            )
            return result

        z_values = np.asarray(system.local_mesh.z_values, dtype=np.float64)
        gamma_layouts = {
            "lower": build_current_gamma_layout(
                system,
                name="Gamma_L",
                plane_z_nm=float(z_values[2]),
                plane_cell_side="lower",
                frozen_z_index=2,
            ),
            "upper": build_current_gamma_layout(
                system,
                name="Gamma_U",
                plane_z_nm=float(z_values[4]),
                plane_cell_side="upper",
                frozen_z_index=4,
            ),
        }
        canonical_layout = build_canonical_interface_layout(
            gamma_layouts["lower"],
            gamma_layouts["upper"],
            comm=comm,
            expected_lower_count=V6_2_INTERFACE_LOWER_COUNT,
            expected_upper_count=V6_2_INTERFACE_UPPER_COUNT,
        )
        group_rows, group_audit = build_v6_cell_recovery_owner_group_rows(
            system, system.F, comm=comm
        )
        first, last = map(int, system.F.getOwnershipRange())
        support_audits: dict[str, dict[str, Any]] = {}
        supports: list[np.ndarray] = []
        interface_supports: dict[str, Mapping[str, Any]] = {}
        for name, z_value in (("lower", z_values[2]), ("upper", z_values[4])):
            support = audit_artificial_z_interface_support(
                system.V,
                system.static_condensation.condensed,
                float(z_value),
            )
            interface_supports[name] = support
            global_support = np.asarray(support["active_support"], dtype=np.int64)
            local_support = global_support[
                (global_support >= first) & (global_support < last)
            ].astype(PETSc.IntType, copy=False)
            supports.append(local_support)
            global_hash = hashlib.sha256(global_support.tobytes()).hexdigest()
            support_audits[name] = _support_summary(
                comm,
                local_support,
                global_count=int(global_support.size),
                global_hash=global_hash,
            )
        support_metadata_replicated = any(
            bool(audit.get("support_metadata_replicated"))
            for audit in support_audits.values()
        )
        if v7_moving_pml_full_state:
            oracle = None
            matrix = None
            action = None
            action_before = {}
        else:
            live_resource_callback: Callable[[], Mapping[str, Any]] | None = None
            factor_ready_callback = None
            if v8_full_spectrum_only:
                factor_setup_started = time.perf_counter()
                live_resource_callback = _v6_2_live_resource_callback(
                    resource_callback,
                    comm=comm,
                    formal_sequence_started=formal_sequence_started,
                    hard_stop_bytes=int(hard_stop_bytes),
                    budget_seconds=float(exact_budget_seconds),
                )

                def factor_ready_callback(
                    group: int, factor: Mapping[str, Any]
                ) -> None:
                    nonlocal factor_setup_started
                    _v8_mark(
                        v8_marker_payload,
                        _v8_factor_ready_marker(group),
                        formal_sequence_started,
                        live_resource_callback,
                        action,
                        stage_clock_start=factor_setup_started,
                        factor_lifecycle={
                            "ready": int(group) + 1,
                            "after_cleanup": None,
                        },
                        pc_apply_count=0,
                        action_apply_count=0,
                        source=None,
                        checkpoint=None,
                        factor=_json_safe(factor),
                    )
                    factor_setup_started = time.perf_counter()

            oracle = build_petsc_interface_schur_oracle(
                system.F,
                group_rows,
                supports,
                factor_ready_callback=factor_ready_callback,
            )
            matrix, action = build_petsc_full_interface_schur_action(
                oracle,
                canonical_layout=canonical_layout,
                own_oracle=True,
            )
            action_before = action.diagnostics
        bare_operator_hash = _petsc_matrix_hash(system.F)
        binding_error: str | None = None
        bound_exact_configuration: dict[str, Any] | None = None
        moving_resource_callback: Callable[[], Mapping[str, Any]] | None = None
        if v7_moving_pml_full_state:
            moving_resource_callback = _v6_2_live_resource_callback(
                resource_callback,
                comm=comm,
                formal_sequence_started=formal_sequence_started,
                hard_stop_bytes=int(hard_stop_bytes),
                budget_seconds=float(exact_budget_seconds),
            )
        else:
            try:
                from src.solvers.hybrid_bare_f_authority import (
                    canonical_packets_for_vector,
                    canonical_to_current_roundtrip_relative,
                    gamma_values_for_vector,
                )
                from src.solvers.hybrid_exact_qualification import (
                    make_live_persisted_canonical_roundtrip_callback,
                )

                live_persisted_roundtrip = (
                    make_live_persisted_canonical_roundtrip_callback(
                        system,
                        canonical_packets_for_vector=canonical_packets_for_vector,
                        canonical_to_current_roundtrip_relative=(
                            canonical_to_current_roundtrip_relative
                        ),
                    )
                )
                if live_resource_callback is None:
                    live_resource_callback = _v6_2_live_resource_callback(
                        resource_callback,
                        comm=comm,
                        formal_sequence_started=formal_sequence_started,
                        hard_stop_bytes=int(hard_stop_bytes),
                        budget_seconds=float(exact_budget_seconds),
                    )
                numeric_options = _v6_2_formal_numeric_options(exact_qualification)
                numeric_options.update(
                    {
                        "canonical_roundtrip": {
                            label: live_persisted_roundtrip
                            for label in V6_2_EXACT_QUALIFICATION_SOURCES
                        },
                        "canonical_packets_for_vector": canonical_packets_for_vector,
                        "gamma_canonical_values_for_vector": gamma_values_for_vector,
                        "exact_output_canonical_roundtrip": (
                            canonical_to_current_roundtrip_relative
                        ),
                        "resource_callback": live_resource_callback,
                        "authorize_conditional": (
                            lambda gate_input: _v6_2_conditional_authorizer(
                                gate_input,
                                hard_stop_bytes=int(hard_stop_bytes),
                                budget_seconds=float(exact_budget_seconds),
                            )
                        ),
                    }
                )
                bound_exact_configuration = _bind_v6_2_formal_exact_configuration(
                    numeric_options,
                    exact_spool_root=frozen_root,
                    run_directory=output_root,
                    identity_preflight=identity_preflight,
                    bare_operator=system.F,
                    bare_operator_hash=bare_operator_hash,
                    source_sha=str(source_sha),
                )
            except Exception as exc:
                binding_error = f"{type(exc).__name__}: {exc}"
            _collective_driver_error(
                comm, "formal exact authority binding", binding_error
            )
            if bound_exact_configuration is None:
                raise RuntimeError("formal exact authority binding produced no config")
        if v7_moving_pml_full_state and int(comm.size) != 8:
            raise RuntimeError("moving-PML formal screen requires MPI size 8")
        if v7_moving_pml_full_state:
            from benchmarks.check_task040_v7_moving_pml import (
                check_moving_pml_screen,
            )
            from src.solvers.hybrid_bare_f_authority import (
                V5_BARE_F_SOURCE_LABELS,
                build_current_bare_f_rhs,
            )
            from src.solvers.hybrid_moving_pml import (
                build_moving_pml_full_state_action,
            )
            from src.solvers.hybrid_moving_pml_screen import (
                run_v7_moving_pml_full_state,
            )

            rhs_by_label: dict[str, PETSc.Vec] = {}
            source_build_audits: dict[str, Mapping[str, Any]] = {}
            moving_action = None
            try:
                for label in V5_BARE_F_SOURCE_LABELS:
                    rhs, source_audit = build_current_bare_f_rhs(system, label)
                    rhs_by_label[label] = rhs
                    source_build_audits[label] = source_audit
                moving_action = build_moving_pml_full_state_action(
                    system, system.F, group_rows
                )
                _emit(
                    marker_callback,
                    "v7_moving_pml_setup",
                    status="complete",
                    factor_ready=3,
                    rhs_source="build_current_bare_f_rhs",
                )
                _emit(
                    marker_callback,
                    "v7_moving_pml_sources",
                    status="started",
                    source_count=5,
                )
                screen_raw = run_v7_moving_pml_full_state(
                    {
                        "bare_operator": system.F,
                        "rhs_by_label": rhs_by_label,
                        "moving_action": moving_action,
                        "resource_callback": moving_resource_callback,
                        "source_build_audits": source_build_audits,
                    }
                )
                _emit(
                    marker_callback,
                    "v7_moving_pml_sources",
                    status="complete",
                    source_count=len(screen_raw.get("sources", ())),
                )
                _emit(
                    marker_callback,
                    "v7_moving_pml_checkpoints",
                    status="complete",
                    mandatory_checkpoints=screen_raw.get("mandatory_checkpoints"),
                )
                screen_checker = check_moving_pml_screen(screen_raw)
                moving_result = {
                    "schema": V7_MOVING_PML_FULL_STATE_SCHEMA,
                    "method": V7_MOVING_PML_FULL_STATE_METHOD,
                    "profile": V7_MOVING_PML_FULL_STATE_PROFILE_ID,
                    "status": "completed_moving_pml_screen",
                    "raw_screen": screen_raw,
                    "checker": screen_checker,
                    "classification": screen_checker["classification"],
                    "route_signal": screen_checker["route_signal"],
                    "next_required_stage": screen_checker[
                        "next_required_stage"
                    ],
                    "evidence_valid": screen_checker["evidence_valid"],
                    "checker_pass": screen_checker["checker_pass"],
                    "pass": screen_checker["pass"],
                    "formal_adjudication": False,
                    "source_sha": str(source_sha),
                    "input_sha256": str(input_sha256),
                    "physical_model_sha256": str(physical_model_sha256),
                    "identity_preflight": _json_safe(identity_preflight),
                    "resource_preflight": _json_safe(resource_preflight),
                    "system_inventory": _json_safe(system.construction_inventory),
                    "support_audits": _json_safe(support_audits),
                    "group_rows": _json_safe(group_audit),
                    "rhs_source": "build_current_bare_f_rhs",
                    "rhs_vectors_loaded": len(rhs_by_label),
                    "qep_calls": 0,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "frozen_rhs_authority_root": str(frozen_root),
                    "frozen_rhs_authority_use": (
                        "identity_preflight_only_not_used_for_numeric_rhs"
                    ),
                    "exact_qualification": (
                        "intentional_not_run_by_v7_direct_mainline"
                    ),
                    "full_spectrum_continuation": "not_run_by_moving_pml_route",
                    "pde_solve": "moving_pml_full_state_screen",
                    "cleanup_stage": "v7_moving_pml_cleanup",
                }
                _write_json(rank_root / "v7_moving_pml.json", moving_result)
                if comm.rank == 0:
                    _write_json(output_root / "v7_moving_pml.json", moving_result)
                comm.barrier()
                moving_result = comm.bcast(
                    moving_result if comm.rank == 0 else None, root=0
                )
                return _json_safe(moving_result)
            finally:
                for rhs in rhs_by_label.values():
                    rhs.destroy()
                if moving_action is not None:
                    moving_action.destroy()
        if v8_full_spectrum_only:
            from src.solvers.hybrid_full_spectrum_screen import (
                run_v8_full_spectrum_two_source,
            )

            v8_marker_payload.update(
                {
                    "system": system,
                    "bare_operator": system.F,
                    "interface_operator": matrix,
                    "schur_action": action,
                    "factor_lifecycle": dict(action_before["factor_lifecycle"]),
                    "lower_gamma_layout": gamma_layouts["lower"],
                    "upper_gamma_layout": gamma_layouts["upper"],
                    "canonical_layout": canonical_layout,
                    "interface_supports": interface_supports,
                    "formal_exact_configuration": bound_exact_configuration,
                    "frozen_rhs_descriptors": bound_exact_configuration[
                        "descriptors"
                    ],
                    "base_directory": bound_exact_configuration["base_directory"],
                    "resource_callback": bound_exact_configuration[
                        "resource_callback"
                    ],
                    "formal_sequence_started": formal_sequence_started,
                    "selected_operator": {
                        "candidate": "D0_lower_memory",
                        "kind": "petsc_full_interface_schur",
                    },
                }
            )
            result = run_v8_full_spectrum_two_source(v8_marker_payload)
            result.update(
                {
                    "source_sha": str(source_sha),
                    "input_sha256": str(input_sha256),
                    "physical_model_sha256": str(physical_model_sha256),
                    "identity_preflight": _json_safe(identity_preflight),
                    "resource_preflight": _json_safe(resource_preflight),
                    "operator_semantics_audit": _json_safe(audit_file),
                    "system_inventory": _json_safe(system.construction_inventory),
                    "matrix_objects": _json_safe(system.dtn_objects_constructed),
                    "support_audits": _json_safe(support_audits),
                    "group_rows": _json_safe(group_audit),
                    "bare_f_operator_hash": str(bare_operator_hash),
                    "frozen_rhs_authority_root": str(frozen_root),
                    "formal_exact_configuration_bound": True,
                    "factor_lifecycle_before_cleanup": _json_safe(
                        action_before["factor_lifecycle"]
                    ),
                }
            )
            return result
        deterministic = [
            _one_identity_probe(comm, system.F, matrix, action, index)
            for index in range(3)
        ]
        zero_source = action.create_interface_vector()
        zero_target = matrix.createVecLeft()
        try:
            zero_source.set(0.0)
            zero_source.assemble()
            matrix.mult(zero_source, zero_target)
            zero_error = _global_max(comm, float(zero_target.norm()))
        finally:
            zero_target.destroy()
            zero_source.destroy()
        linearity_error = _linearity_probe(comm, matrix, action)
        factor_before = dict(action_before["factor_lifecycle"])
        layout_before = dict(action_before["interface_layout"])
        layout_gate = {
            "layout_coverage_exact": layout_before.get("coverage_exact") is True,
            "layout_counts_7560_plus_7560": (
                layout_before.get("lower_global_rows") == V6_2_INTERFACE_LOWER_COUNT
                and layout_before.get("upper_global_rows")
                == V6_2_INTERFACE_UPPER_COUNT
                and layout_before.get("global_size") == V6_2_INTERFACE_JOINT_COUNT
            ),
            "layout_canonical_l_then_u": (
                layout_before.get("canonical_order")
                == "Gamma_L_then_Gamma_U_by_physical_key"
            ),
            "layout_owner_distributed": layout_before.get("owner_distributed") is True,
            "layout_position_bijection": (
                layout_before.get("canonical_position_bijection") is True
            ),
        }
        lifecycle_gate = {
            "factor_ready_three_observed": factor_before.get("ready") == 3,
            "factor_simultaneous_max_three_observed": (
                factor_before.get("simultaneous_max") == 3
            ),
        }
        gate_before_cleanup = {
            "zero_map": zero_error <= V6_2_ZERO_TOLERANCE,
            "repeat": max(item["repeat_error"] for item in deterministic)
            <= V6_2_ROUNDTRIP_TOLERANCE,
            "linearity": linearity_error <= V6_2_ROUNDTRIP_TOLERANCE,
            "restriction_prolongation": max(
                item["roundtrip_error"] for item in deterministic
            )
            <= V6_2_ROUNDTRIP_TOLERANCE,
            "full_elimination_gamma": max(
                item["gamma_action_error"] for item in deterministic
            )
            <= V6_2_ACTION_TOLERANCE,
            "full_elimination_interior": max(
                item["full_interior_residual_error"] for item in deterministic
            )
            <= V6_2_ACTION_TOLERANCE,
            "three_deterministic_vectors": len(deterministic) == 3,
            "group_solve_count": all(item["solve_count"] == 3 for item in deterministic),
            "joint_size": int(action.global_size) == V6_2_INTERFACE_JOINT_COUNT,
            "numeric_allgather": not bool(action_before["numeric_allgather"]),
            "full_interface_replica": not bool(
                action_before["full_interface_numeric_replica"]
            ),
            **layout_gate,
            **lifecycle_gate,
        }
        _emit(
            marker_callback,
            "v6_2_identity_gate",
            checks=gate_before_cleanup,
            gate_pass=all(gate_before_cleanup.values()),
            vector_count=len(deterministic),
        )
        if v7_scale_normalized_identity:
            from benchmarks.check_task040_v7_scale_normalized_identity import (
                check_v7_scale_normalized_identity,
            )

            v7_identity_started = time.perf_counter()
            v7_raw_metrics = collect_v7_scale_normalized_identity_metrics(
                comm, system.F, matrix, action, oracle
            )
            v7_checker_result = check_v7_scale_normalized_identity(v7_raw_metrics)
            v7_identity_elapsed = max(
                0.0, time.perf_counter() - v7_identity_started
            )
            selected_candidate = v7_checker_result.get("selected_candidate")
            gate_candidates = v7_checker_result.get("gate_candidates", {})
            selected_operator = {
                "candidate": selected_candidate,
                "kind": (
                    "d1_reference_matshell"
                    if selected_candidate == "fixed_order_d1"
                    else "d0_matshell"
                    if selected_candidate is not None
                    else None
                ),
            }
            bundle_error: str | None = None
            try:
                v7_bundle_descriptor = _write_v7_identity_bundle(
                    rank_root=rank_root,
                    output_root=output_root,
                    raw_metrics=v7_raw_metrics,
                    checker_result=v7_checker_result,
                    source_sha=str(source_sha),
                    input_sha256=str(input_sha256),
                    physical_model_sha256=str(physical_model_sha256),
                    elapsed_seconds=v7_identity_elapsed,
                    selected_operator=selected_operator,
                )
            except Exception as exc:  # noqa: BLE001
                bundle_error = f"{type(exc).__name__}: {exc}"
            _collective_driver_error(
                comm, "V7 identity bundle write", bundle_error
            )
            v7_compact_consensus = _v7_compact_decision_consensus(
                comm,
                {
                    "mpi_size": int(comm.size),
                    "evidence_valid": bool(
                        v7_checker_result.get("evidence_valid")
                    ),
                    "checker_pass": bool(v7_checker_result.get("checker_pass")),
                    "d0_pass_candidate": bool(
                        gate_candidates.get("d0_pass_candidate")
                    ),
                    "d1_pass_candidate": bool(
                        gate_candidates.get("d1_pass_candidate")
                    ),
                    "formal_adjudication": False,
                    "selected_candidate": selected_candidate,
                    "next_required_stage": v7_checker_result.get(
                        "next_required_stage"
                    ),
                    "expected_next_required_stage": (
                        "formal_integration_requires_full_spectrum_continuation"
                    ),
                    "identity_elapsed_seconds": v7_identity_elapsed,
                    "bundle_readback_valid": bool(
                        v7_bundle_descriptor["readback_valid"]
                    ),
                },
            )
            v7_rank_bundle_descriptors = comm.allgather(v7_bundle_descriptor)
            v7_progress_gate = {
                **v7_compact_consensus,
                "rank_bundle_count": len(v7_rank_bundle_descriptors),
            }
            if not bool(v7_compact_consensus["evidence_valid"]):
                v7_classification = "V7_SCALE_NORMALIZED_IDENTITY_EVIDENCE_FAIL"
            elif not bool(v7_compact_consensus["checker_pass"]):
                v7_classification = "V7_SCALE_NORMALIZED_IDENTITY_CHECKER_FAIL"
            elif not bool(v7_compact_consensus["pass"]):
                v7_classification = "V7_SCALE_NORMALIZED_IDENTITY_METADATA_FAIL"
            else:
                v7_classification = (
                    "V7_SCALE_NORMALIZED_IDENTITY_CANDIDATE_PASS"
                )
            if bool(v7_progress_gate["pass"]):
                if selected_candidate == "fixed_order_d1":
                    v7_d1_matrix = build_petsc_d1_reference_interface_schur_mat(
                        action
                    )
                    v7_interface_operator = v7_d1_matrix
                elif selected_candidate in {"d0", "d0_lower_memory"}:
                    v7_interface_operator = matrix
                else:
                    v7_interface_operator = None
                if v7_interface_operator is not None:
                    v7_continuation_result = v7_continuation(
                        {
                            "system": system,
                            "formal_exact_configuration": bound_exact_configuration,
                            "frozen_rhs_descriptors": bound_exact_configuration[
                                "descriptors"
                            ],
                            "base_directory": bound_exact_configuration[
                                "base_directory"
                            ],
                            "resource_callback": bound_exact_configuration[
                                "resource_callback"
                            ],
                            "interface_operator": v7_interface_operator,
                            "d0_interface_operator": matrix,
                            "bare_operator": system.F,
                            "schur_action": action,
                            "lower_gamma_layout": gamma_layouts["lower"],
                            "upper_gamma_layout": gamma_layouts["upper"],
                            "interface_supports": interface_supports,
                            "canonical_layout": canonical_layout,
                            "factor_lifecycle": factor_before,
                            "selected_operator": selected_operator,
                            "v7_raw_metrics": v7_raw_metrics,
                            "v7_checker": v7_checker_result,
                            "v7_progress_gate": v7_progress_gate,
                            "selected_candidate": selected_candidate,
                        }
                    )
                    if not isinstance(v7_continuation_result, Mapping):
                        raise TypeError("V7 continuation must return a mapping")
                v7_factor_lifecycle_after_continuation = dict(
                    action.diagnostics["factor_lifecycle"]
                )
                shared_lifecycle = {
                    "status": "v7_identity_candidate_ready",
                    "same_live_action": True,
                    "interface_operator_selected": selected_candidate,
                    "factor_lifecycle_before_continuation": factor_before,
                    "factor_lifecycle_after_continuation": (
                        v7_factor_lifecycle_after_continuation
                    ),
                    "continuation": v7_continuation_result,
                }
            else:
                v7_factor_lifecycle_after_continuation = dict(
                    action.diagnostics["factor_lifecycle"]
                )
                shared_lifecycle = {
                    "status": "not_run_by_v7_progress_gate",
                    "same_live_action": False,
                    "factor_lifecycle_before_continuation": factor_before,
                    "factor_lifecycle_after_continuation": (
                        v7_factor_lifecycle_after_continuation
                    ),
                }
        elif not all(bool(value) for value in gate_before_cleanup.values()):
            shared_lifecycle = {
                "status": "not_run_by_v6_2_identity_gate",
                "same_live_action": False,
            }
        else:
            exact_checkpoint_callback = None
            if marker_callback is not None:

                def exact_checkpoint_callback(
                    label: str, row: Mapping[str, Any]
                ) -> None:
                    if not isinstance(row, Mapping):
                        raise TypeError("V6-2 exact checkpoint marker row is not a mapping")
                    _emit(
                        marker_callback,
                        "v6_2_exact_checkpoint",
                        status="complete",
                        label=str(label),
                        iteration=int(row["iteration"]),
                        checkpoint_kind=str(row["checkpoint_kind"]),
                        full_true_residual=float(
                            row["full_true_residual_norm"]
                        ),
                        full_true_residual_relative=float(
                            row["full_true_residual_relative"]
                        ),
                    )

            continuation_callback = v6_3_continuation
            if marker_callback is not None and v6_3_continuation is not None:

                def continuation_callback(
                    payload: Mapping[str, Any],
                ) -> Mapping[str, Any]:
                    continuation_result = v6_3_continuation(payload)
                    if not isinstance(continuation_result, Mapping):
                        return continuation_result
                    _emit(
                        marker_callback,
                        "v6_3_continuation",
                        status="complete",
                        classification=continuation_result.get("classification"),
                    )
                    return continuation_result

            shared_lifecycle = _run_v6_2_shared_current_lifecycle(
                action=action,
                system=system,
                interface_operator=matrix,
                bare_operator=system.F,
                exact_configuration=bound_exact_configuration,
                exact_runner=run_v6_2_exact_qualification_packets,
                expected_factor_count=int(factor_before["ready"]),
                gamma_layouts=gamma_layouts,
                canonical_layout=canonical_layout,
                continuation=continuation_callback,
                checkpoint_callback=exact_checkpoint_callback,
            )
            exact_result_for_marker = shared_lifecycle.get("exact_qualification")
            if isinstance(exact_result_for_marker, Mapping):
                _emit(
                    marker_callback,
                    "v6_2_exact_qualification",
                    status="complete",
                    classification=exact_result_for_marker.get("classification"),
                    all_sources_gate_pass=exact_result_for_marker.get(
                        "family", {}
                    ).get("all_sources_gate_pass")
                    if isinstance(exact_result_for_marker.get("family"), Mapping)
                    else False,
                )
        if v7_d1_matrix is not None:
            v7_d1_matrix.destroy()
            v7_d1_matrix = None
        matrix.destroy()
        matrix = None
        action.destroy()
        action_after = action.diagnostics
        factor_after = dict(action_after["factor_lifecycle"])
        cleanup_gate = {
            "factor_after_cleanup_zero_observed": (
                factor_after.get("after_cleanup") == 0
            ),
            "factor_action_destroyed": action_after.get("destroyed") is True,
        }
        identity_gate = {**gate_before_cleanup, **cleanup_gate}
        identity_gate_pass = all(identity_gate.values())
        action = None
        system.destroy()
        system = None
        _emit(
            marker_callback,
            "v6_2_cleanup",
            status="complete",
            factor_construction_count=int(factor_before.get("ready", 0)),
            factor_after_cleanup=int(factor_after.get("after_cleanup", -1)),
            action_destroyed=bool(action_after.get("destroyed")),
            system_destroyed=True,
        )
        if v7_scale_normalized_identity:
            selected_candidate = (
                None
                if v7_compact_consensus is None
                else v7_compact_consensus.get("selected_candidate")
            )
            v7_status = (
                str(v7_continuation_result.get("status"))
                if isinstance(v7_continuation_result, Mapping)
                and v7_continuation_result.get("status") is not None
                else (
                    "completed_v7_scale_normalized_identity_candidate"
                    if v7_progress_gate is not None
                    and bool(v7_progress_gate.get("pass"))
                    else "completed_v7_scale_normalized_identity_diagnostic"
                )
            )
            v7_next_required_stage = (
                v7_continuation_result.get("next_required_stage")
                if isinstance(v7_continuation_result, Mapping)
                and v7_continuation_result.get("next_required_stage") is not None
                else (
                    v7_compact_consensus.get("next_required_stage")
                    if isinstance(v7_compact_consensus, Mapping)
                    else "not_run_by_v7_continuation_gate"
                )
            )
            legacy_classification = (
                "V6_2_FULL_INTERFACE_SCHUR_PASS"
                if identity_gate_pass
                else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
            )
            v7_result = {
                "schema": V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA,
                "method": V7_SCALE_NORMALIZED_IDENTITY_METHOD,
                "profile": V7_SCALE_NORMALIZED_IDENTITY_PROFILE_ID,
                "status": v7_status,
                "classification": (
                    v7_continuation_result.get("classification")
                    if isinstance(v7_continuation_result, Mapping)
                    else "not_formal_adjudication"
                ),
                "formal_adjudication": (
                    bool(v7_continuation_result.get("formal_adjudication", False))
                    if isinstance(v7_continuation_result, Mapping)
                    else False
                ),
                "continuation_evidence": _json_safe(v7_continuation_result),
                "v7_scale_normalized_identity": True,
                "v7_classification": v7_classification,
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "identity_preflight": _json_safe(identity_preflight),
                "resource_preflight": _json_safe(resource_preflight),
                "system_created": True,
                "identity_gate": identity_gate,
                "gate_pass": identity_gate_pass,
                "legacy_classification": legacy_classification,
                "exact_qualification": (
                    "intentional_not_run_by_v7_direct_mainline"
                ),
                "full_spectrum_continuation": "required",
                "legacy_v6_2_absolute_diagnostic": _json_safe(
                    v7_raw_metrics.get("legacy_v6_2_absolute_diagnostic")
                    if isinstance(v7_raw_metrics, Mapping)
                    else None
                ),
                "v7_progress_gate": _json_safe(v7_progress_gate),
                "v7_bundle_descriptors": sorted(
                    v7_rank_bundle_descriptors,
                    key=lambda item: item["rank"],
                ),
                "v7_compact_consensus": _json_safe(v7_compact_consensus),
                "selected_operator": _json_safe(selected_operator),
                "factor_lifecycle": {
                    "before_continuation": _json_safe(factor_before),
                    "after_continuation": _json_safe(
                        v7_factor_lifecycle_after_continuation
                    ),
                    "after_cleanup": _json_safe(factor_after),
                },
                "continuation": {
                    "executed": v7_continuation_result is not None,
                    "status": (
                        v7_continuation_result.get("status")
                        if isinstance(v7_continuation_result, Mapping)
                        else "not_run_by_v7_progress_gate"
                    ),
                    "classification": (
                        v7_continuation_result.get("classification")
                        if isinstance(v7_continuation_result, Mapping)
                        else None
                    ),
                },
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
                "full_interface_numeric_replica": False,
                "next_required_stage": v7_next_required_stage,
            }
            if comm.rank == 0:
                _write_json(output_root / "v7_manifest.json", v7_result)
            v7_result = comm.bcast(v7_result if comm.rank == 0 else None, root=0)
            comm.barrier()
            return _json_safe(v7_result)
        exact_qualification_result = (
            None
            if shared_lifecycle is None
            else shared_lifecycle.get("exact_qualification")
        )
        exact_output_vectors_loaded = 0
        if isinstance(exact_qualification_result, Mapping):
            family_result = exact_qualification_result.get("family")
            if isinstance(family_result, Mapping):
                exact_output_vectors_loaded = sum(
                    1
                    for record in family_result.get("source_records", ())
                    if (
                        isinstance(record, Mapping)
                        and isinstance(record.get("fgmres"), Mapping)
                        and bool(
                            record["fgmres"].get("accepted_solution_consumed")
                        )
                        )
                    )
        exact_qualification_artifact: dict[str, Any] | None = None
        if isinstance(exact_qualification_result, Mapping):
            exact_rank_path = rank_root / "v6_2_exact_qualification.json"
            frozen_descriptor_hashes = exact_qualification_result.get(
                "frozen_rhs_descriptor_metadata_sha256", {}
            )
            exact_rank_payload = {
                "schema": "task040.v6_2.exact_qualification_rank_artifact.v1",
                "rank": int(comm.rank),
                "mpi_size": int(comm.size),
                "qualification_source_sha": str(source_sha),
                "bare_f_operator_hash": str(bare_operator_hash),
                "frozen_rhs_source_sha": str(
                    exact_qualification_result.get(
                        "frozen_rhs_source_provenance", {}
                    ).get("source_sha", "")
                ),
                "formal_sequence_start_scope": formal_sequence_start_scope,
                "frozen_rhs_source_provenance": _json_safe(
                    exact_qualification_result.get(
                        "frozen_rhs_source_provenance", {}
                    )
                ),
                "qualification_source_provenance": _json_safe(
                    exact_qualification_result.get(
                        "qualification_source_provenance", {}
                    )
                ),
                "frozen_rhs_descriptor_metadata_sha256": _json_safe(
                    frozen_descriptor_hashes
                ),
                "exact_result": _json_safe(exact_qualification_result),
            }
            exact_rank_sha = _write_json(exact_rank_path, exact_rank_payload)
            if hash_file_sha256(exact_rank_path) != exact_rank_sha:
                raise RuntimeError(
                    "V6-2 exact qualification rank artifact hash reread failed"
                )
            exact_qualification_artifact = (
                _build_exact_qualification_artifact_reference(
                    rank=int(comm.rank),
                    mpi_size=int(comm.size),
                    exact_rank_path=exact_rank_path,
                    output_root=output_root,
                    source_sha=str(source_sha),
                    exact_result=exact_qualification_result,
                    formal_sequence_start_scope=formal_sequence_start_scope,
                )
            )
            exact_qualification_artifact["sha256"] = exact_rank_sha
        exact_stage_summary = _compact_exact_stage_summary(
            exact_qualification_result
        )
        continuation_result = (
            None
            if shared_lifecycle is None
            else shared_lifecycle.get("continuation")
        )
        continuation_stage_summary = (
            _compact_exact_stage_summary(continuation_result)
            if continuation_result is not None
            else {
                "executed": False,
                "status": (
                    "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                ),
                "classification": None,
                "all_sources_gate_pass": False,
                "packet_aggregate_gate_pass": False,
            }
        )
        exact_pde_status = _exact_pde_status(exact_stage_summary)
        rank_artifact = {
            "schema": "task040.v6_2.rank_artifact.v1",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
            "formal_sequence_start_scope": formal_sequence_start_scope,
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "bare_f_operator_hash": str(bare_operator_hash),
            "identity_preflight": {
                "pass": bool(identity_preflight["pass"]),
                "observed": _json_safe(identity_preflight.get("observed", {})),
                "checks": _json_safe(identity_preflight.get("checks", {})),
            },
            "operator_semantics_audit": _json_safe(audit_file),
            "resource_preflight_pass": bool(resource_preflight["pass"]),
            "system_inventory": _json_safe(inventory),
            "matrix_objects": _json_safe(matrix_objects),
            "qep_calls": int(inventory["qep_calls"]),
            "canonical_interface_layout": _json_safe(action_before["interface_layout"]),
            "canonical_mapping_sha256": _local_mapping_sha256(
                canonical_layout.local_row_to_position
            ),
            "canonical_mapping_count": len(canonical_layout.local_row_to_position),
            "group_rows": _json_safe(group_audit),
            "support_audits": support_audits,
            "support_metadata_replicated": support_metadata_replicated,
            "deterministic_vectors": deterministic,
            "zero_error": float(zero_error),
            "linearity_error": float(linearity_error),
            "identity_gate": identity_gate,
            "gate_pass": identity_gate_pass,
            "classification": (
                "V6_2_FULL_INTERFACE_SCHUR_PASS"
                if identity_gate_pass
                else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
            ),
            "factor_lifecycle_observed": {
                "construction_count": int(factor_before["ready"]),
                "destruction_count": int(
                    factor_before["ready"] - factor_after["after_cleanup"]
                ),
                "simultaneous_max": int(factor_before["simultaneous_max"]),
                "after_cleanup": int(factor_after["after_cleanup"]),
            },
            "factor_lifecycle_before": _json_safe(
                action_before["factor_lifecycle"]
            ),
            "factor_lifecycle_after": _json_safe(
                action_after["factor_lifecycle"]
            ),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "numeric_allgather": False,
            "fe_numeric_allgather": False,
            "full_interface_numeric_replica": False,
            "raw_global_row_remap": False,
            "exact_output_vectors_loaded": int(exact_output_vectors_loaded),
            "exact_qualification_artifact": exact_qualification_artifact,
            "exact_qualification": exact_stage_summary,
            "v6_3_continuation": continuation_stage_summary,
            "pde_solve": exact_pde_status,
            "exact_qualification_plan": build_v6_2_exact_qualification_plan(),
        }
        rank_path = rank_root / "v6_2_rank_artifact.json"
        rank_sha = _write_json(rank_path, rank_artifact)
        rank_descriptor = {
            "rank": int(comm.rank),
            "path": str(rank_path.relative_to(output_root)),
            "sha256": rank_sha,
            "formal_sequence_start_scope": rank_artifact[
                "formal_sequence_start_scope"
            ],
            "canonical_mapping_count": len(canonical_layout.local_row_to_position),
            "canonical_mapping_sha256": rank_artifact["canonical_mapping_sha256"],
            "factor_lifecycle_after": rank_artifact["factor_lifecycle_after"],
            "exact_qualification": rank_artifact["exact_qualification"],
            "v6_3_continuation": rank_artifact["v6_3_continuation"],
            "exact_output_vectors_loaded": rank_artifact[
                "exact_output_vectors_loaded"
            ],
            "exact_qualification_artifact": rank_artifact[
                "exact_qualification_artifact"
            ],
            "pde_solve": rank_artifact["pde_solve"],
        }
        rank_descriptors = comm.gather(rank_descriptor, root=0)
        result = None
        if comm.rank == 0:
            rank_descriptors = sorted(rank_descriptors, key=lambda item: item["rank"])

            def consensus_value(key: str) -> tuple[bool, Any, list[Any]]:
                values = [item.get(key) for item in rank_descriptors]
                encoded = [
                    json.dumps(_json_safe(value), sort_keys=True)
                    for value in values
                ]
                return bool(encoded and len(set(encoded)) == 1), values[0], values

            exact_consensus, exact_summary, exact_summaries = consensus_value(
                "exact_qualification"
            )
            continuation_consensus, continuation_summary, continuation_summaries = (
                consensus_value("v6_3_continuation")
            )
            exact_count_consensus, exact_count, _exact_counts = consensus_value(
                "exact_output_vectors_loaded"
            )
            pde_consensus, pde_status, _pde_statuses = consensus_value("pde_solve")
            formal_scope_consensus, formal_scope, _formal_scopes = consensus_value(
                "formal_sequence_start_scope"
            )
            factor_after_by_rank = [
                item["factor_lifecycle_after"] for item in rank_descriptors
            ]
            construction_counts = [
                int(item["factor_lifecycle_after"]["ready"])
                for item in rank_descriptors
            ]
            destruction_counts = [
                int(item["factor_lifecycle_after"]["ready"])
                - int(item["factor_lifecycle_after"]["after_cleanup"])
                for item in rank_descriptors
            ]
            simultaneous_counts = [
                int(item["factor_lifecycle_after"]["simultaneous_max"])
                for item in rank_descriptors
            ]
            factor_lifecycle = {
                "before": _json_safe(action_before["factor_lifecycle"]),
                "after_by_rank": factor_after_by_rank,
                "construction_count": construction_counts[0]
                if len(set(construction_counts)) == 1
                else None,
                "destruction_count": destruction_counts[0]
                if len(set(destruction_counts)) == 1
                else None,
                "simultaneous_max": max(simultaneous_counts)
                if simultaneous_counts
                else None,
                "rank_consensus": (
                    len(set(construction_counts)) == 1
                    and len(set(destruction_counts)) == 1
                    and len(set(simultaneous_counts)) == 1
                    and exact_consensus
                    and continuation_consensus
                    and exact_count_consensus
                    and pde_consensus
                    and formal_scope_consensus
                ),
            }
            exact_qualification_artifacts = [
                item.get("exact_qualification_artifact")
                for item in rank_descriptors
            ]
            exact_artifact_chain_sha256 = hashlib.sha256(
                json.dumps(
                    exact_qualification_artifacts,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            exact_qualification_summary = {
                "rank_consensus": exact_consensus,
                "summary": exact_summary if exact_consensus else None,
                "by_rank": None if exact_consensus else exact_summaries,
            }
            continuation_summary = {
                "rank_consensus": continuation_consensus,
                "summary": continuation_summary if continuation_consensus else None,
                "by_rank": (
                    None if continuation_consensus else continuation_summaries
                ),
            }
            exact_executed = bool(
                exact_consensus
                and isinstance(exact_summary, Mapping)
                and exact_summary.get("executed")
            )
            continuation_executed = bool(
                continuation_consensus
                and isinstance(continuation_summary.get("summary"), Mapping)
                and continuation_summary["summary"].get("executed")
            )
            combined_status = _combined_v6_2_status(
                identity_gate_pass=identity_gate_pass,
                exact_consensus=exact_consensus,
                exact_executed=exact_executed,
                continuation_consensus=continuation_consensus,
                continuation_executed=continuation_executed,
            )
            result = {
                "schema": V6_2_INTERFACE_SCHUR_SCHEMA,
                "method": V6_2_INTERFACE_SCHUR_METHOD,
                "profile": V6_2_INTERFACE_SCHUR_PROFILE_ID,
                "mpi_size": int(comm.size),
                "formal_sequence_start_scope": (
                    formal_scope if formal_scope_consensus else None
                ),
                "status": combined_status,
                "classification": (
                    "V6_2_FULL_INTERFACE_SCHUR_PASS"
                    if identity_gate_pass
                    else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
                ),
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "identity_preflight": _json_safe(identity_preflight),
                "resource_preflight": _json_safe(resource_preflight),
                "operator_semantics_audit": _json_safe(audit_file),
                "system_created": True,
                "system_inventory": _json_safe(inventory),
                "matrix_objects": _json_safe(matrix_objects),
                "qep_calls": int(inventory["qep_calls"]),
                "bare_f_operator_hash": str(bare_operator_hash),
                "factored_operator": "none",
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "exact_output_vectors_loaded": (
                    int(exact_count) if exact_count_consensus else None
                ),
                "exact_qualification": exact_qualification_summary,
                "v6_3_continuation": continuation_summary,
                "pde_solve": pde_status if pde_consensus else "rank_disagreement",
                "canonical_interface_layout": _json_safe(
                    action_before["interface_layout"]
                ),
                "gamma_counts": {
                    "Gamma_L": V6_2_INTERFACE_LOWER_COUNT,
                    "Gamma_U": V6_2_INTERFACE_UPPER_COUNT,
                    "joint": V6_2_INTERFACE_JOINT_COUNT,
                },
                "group_rows": _json_safe(group_audit),
                "support_audits": support_audits,
                "support_metadata_replicated": support_metadata_replicated,
                "deterministic_vectors": deterministic,
                "zero_error": float(zero_error),
                "linearity_error": float(linearity_error),
                "identity_gate": identity_gate,
                "gate_pass": identity_gate_pass,
                "factor_lifecycle": factor_lifecycle,
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
                "full_interface_numeric_replica": False,
                "root_metadata_gather": True,
                "per_rank_full_interface_replica": False,
                "raw_global_row_remap": False,
                "rank_artifacts": rank_descriptors,
                "exact_qualification_artifacts": exact_qualification_artifacts,
                "exact_qualification_artifact_chain_sha256": (
                    exact_artifact_chain_sha256
                ),
                "downstream": {
                    "v6_3_full_spectrum": continuation_summary,
                    "v6_4_route_a_b": (
                        "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                    ),
                    "v6_5_moving_pml": (
                        "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                    ),
                    "v6_6_adaptive_schwarz": (
                        "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                    ),
                    "v6_7_factor_free_local_service": (
                        "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                    ),
                    "v6_8_full_hybrid": (
                        "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                    ),
                    "v6_9_capacity": (
                        "not_run_by_v6_2_exact_qualification_continuation_not_configured"
                    ),
                },
                "exact_qualification_plan": build_v6_2_exact_qualification_plan(),
                "research_only": True,
            }
            _write_json(output_root / "v6_2_manifest.json", result)
        result = comm.bcast(result, root=0)
        comm.barrier()
        return _json_safe(result)
    finally:
        if v7_d1_matrix is not None:
            v7_d1_matrix.destroy()
        v8_factor_lifecycle_after_cleanup: Mapping[str, Any] | None = None
        v8_action_apply_count: int | None = None
        if action is not None:
            action.destroy()
            if v8_full_spectrum_only and result is not None:
                action_diagnostics = action.diagnostics
                v8_factor_lifecycle_after_cleanup = action_diagnostics.get(
                    "factor_lifecycle", {}
                )
                v8_action_apply_count = action_diagnostics.get("apply_count")
                result["factor_lifecycle_after_cleanup"] = _json_safe(
                    v8_factor_lifecycle_after_cleanup
                )
        if matrix is not None:
            matrix.destroy()
        if system is not None:
            system.destroy()
            if v7_moving_pml_full_state:
                _emit(
                    marker_callback,
                    "v7_moving_pml_cleanup",
                    status="complete",
                    system_destroyed=True,
                )
            if v8_full_spectrum_only and result is not None:
                communication = result.get("communication", {})
                pc_apply_count = (
                    communication.get("apply_count")
                    if isinstance(communication, Mapping)
                    else None
                )
                cleanup_marker = _v8_mark(
                    v8_marker_payload,
                    "v8_full_spectrum_cleanup_complete",
                    formal_sequence_started,
                    v8_marker_resource_callback,
                    action,
                    status="complete",
                    factor_lifecycle=_json_safe(
                        v8_factor_lifecycle_after_cleanup or {}
                    ),
                    pc_apply_count=pc_apply_count,
                    action_apply_count=v8_action_apply_count,
                    source=None,
                    checkpoint=None,
                    system_destroyed=True,
                    action_destroyed=True,
                    matrix_destroyed=True,
                )
                result["cleanup"] = {
                    "status": "complete",
                    "system_destroyed": True,
                    "action_destroyed": True,
                    "matrix_destroyed": True,
                    "marker": cleanup_marker,
                }
                _write_json(rank_root / "v8_full_spectrum.json", result)
                if comm.rank == 0:
                    _write_json(output_root / "v8_manifest.json", result)
        if v8_adaptive_schwarz_only:
            result_generated = result is not None
            result_record: Mapping[str, Any] = result if result is not None else {}
            evidence_record = result_record.get("evidence", {})
            evidence_cleanup = (
                evidence_record.get("cleanup", {})
                if isinstance(evidence_record, Mapping)
                else {}
            )
            screen_cleanup = adaptive_marker_state["screen_cleanup"]
            adaptive_cleanup = {
                **dict(result_record.get("cleanup", {})),
                "status": "complete",
                "result_generated": result_generated,
                "system_destroyed": system is not None,
                "action_destroyed": bool(
                    evidence_cleanup.get("action_destroyed", False)
                ),
                "provider_destroyed": bool(
                    evidence_cleanup.get("provider_destroyed", False)
                ),
                "target_destroyed": bool(
                    evidence_cleanup.get("target_destroyed", False)
                ),
                "residual_destroyed": bool(
                    evidence_cleanup.get("residual_destroyed", False)
                ),
                "source_destroyed": bool(
                    result_record.get("source_destroyed", False)
                ),
                "bare_f_hash_before": evidence_cleanup.get(
                    "bare_f_hash_before", screen_cleanup.get("bare_f_hash_before")
                ),
                "bare_f_hash_after": evidence_cleanup.get(
                    "bare_f_hash_after", screen_cleanup.get("bare_f_hash_after")
                ),
                "factor_lifecycle_after_cleanup": (
                    evidence_cleanup.get("factor_lifecycle_after_cleanup", {})
                ),
                "screen_cleanup": screen_cleanup,
            }
            adaptive_mark(
                "v8_adaptive_cleanup_complete",
                result_generated=adaptive_cleanup["result_generated"],
                system_destroyed=adaptive_cleanup["system_destroyed"],
                factor_lifecycle=adaptive_cleanup[
                    "factor_lifecycle_after_cleanup"
                ],
                pc_apply_count=1 if evidence_record else 0,
                action_apply_count=int(
                    evidence_record.get("action_apply_count_after", 0)
                    if isinstance(evidence_record, Mapping)
                    else 0
                ),
                action_destroyed=adaptive_cleanup["action_destroyed"],
                provider_destroyed=adaptive_cleanup["provider_destroyed"],
                target_destroyed=adaptive_cleanup["target_destroyed"],
                residual_destroyed=adaptive_cleanup["residual_destroyed"],
                source_destroyed=adaptive_cleanup["source_destroyed"],
                bare_f_hash_before=adaptive_cleanup["bare_f_hash_before"],
                bare_f_hash_after=adaptive_cleanup["bare_f_hash_after"],
                source=None,
                checkpoint=None,
                cleanup=adaptive_cleanup,
            )
            if result is not None:
                result["cleanup"] = adaptive_cleanup
                _write_json(rank_root / "v8_adaptive_stage_a.json", result)
                if comm.rank == 0:
                    _write_json(output_root / "v8_adaptive_manifest.json", result)
            else:
                failure_record = {
                    "schema": V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA,
                    "method": V8_ADAPTIVE_SCHWARZ_ONLY_METHOD,
                    "profile": V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID,
                    "status": "adaptive_stage_a_exception",
                    "classification": "V8_ADAPTIVE_STAGE_A_IMPLEMENTATION_FAILURE",
                    "pass": None,
                    "formal_adjudication": False,
                    "executed": False,
                    "cleanup": adaptive_cleanup,
                    "error_propagated": True,
                }
                _write_json(
                    rank_root / "v8_adaptive_stage_a_failure.json", failure_record
                )
                if comm.rank == 0:
                    _write_json(
                        output_root / "v8_adaptive_failure_manifest.json",
                        failure_record,
                    )
