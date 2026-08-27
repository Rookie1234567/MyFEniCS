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
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_schur import (
    build_canonical_interface_layout,
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

__all__ = (
    "V6_2_INTERFACE_SCHUR_FLAG",
    "V6_2_INTERFACE_SCHUR_METHOD",
    "V6_2_INTERFACE_SCHUR_SCHEMA",
    "V6_2_INTERFACE_SCHUR_PROFILE_ID",
    "V6_2_INTERFACE_LOWER_COUNT",
    "V6_2_INTERFACE_UPPER_COUNT",
    "V6_2_INTERFACE_JOINT_COUNT",
    "V6_2_RESOURCE_HEADROOM_BYTES",
    "V6_2_MIN_DISK_FREE_BYTES",
    "V6_2_EXACT_QUALIFICATION_SOURCES",
    "V6_2_FROZEN_V5_RHS_PRODUCER_SOURCE_SHA",
    "build_v6_2_exact_qualification_plan",
    "run_v6_2_exact_qualification_packets",
    "run_v6_2_interface_schur",
)


def build_v6_2_exact_qualification_plan() -> dict[str, Any]:
    """Describe the post-identity qualification path without running it.

    This contract is emitted by the identity runner so a later formal run has
    one auditable sequence: the first two current-layout sources must pass
    before the remaining three are attempted.  It deliberately contains no
    numerical result and does not authorize a heavy run by itself.
    """

    return {
        "status": "designed_not_run",
        "source_order": list(V6_2_EXACT_QUALIFICATION_SOURCES),
        "rhs_layout": "current_canonical_active_keys_owner_local",
        "interface_rhs": "g=b_Gamma-A_GammaI*A_II^-1*b_I",
        "checkpoints": [16, 32, 64, 128],
        "conditional_checkpoints": [256, 512],
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
        "full_side_exact_factor": "not_constructed_in_identity_runner",
        "frozen_owner_row_arrays": (
            "not_loaded; complex PETSc owner-order values, never row ids"
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
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Read the one fixed V5 descriptor per source for this MPI rank.

    Formal callers may carry a descriptor mapping for convenience, but the
    authority is always the immutable ``rank%04d/bottom_<label>_rhs.json``
    file selected from the frozen V5 root.  Paths, metadata bytes, source
    semantics, and all six provenance fields are checked before the mapping
    is returned to the exact consumer.
    """

    descriptors: dict[str, dict[str, Any]] = {}
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
        descriptor = dict(payload)
        expected_metadata_path = relative_metadata.as_posix()
        if descriptor.get("metadata_path") != expected_metadata_path:
            raise ValueError(
                f"V6-2 frozen descriptor {label} metadata_path is not authority-bound"
            )
        if descriptor.get("label") != label:
            raise ValueError(
                f"V6-2 frozen descriptor label mismatch for {label}"
            )
        descriptor_provenance = descriptor.get("source_provenance")
        if not isinstance(descriptor_provenance, Mapping):
            raise ValueError(f"V6-2 frozen descriptor {label} lacks source_provenance")
        for field in _V6_2_EXACT_PROVENANCE_FIELDS:
            if descriptor_provenance.get(field) != frozen_rhs_provenance.get(field):
                raise ValueError(
                    f"V6-2 frozen descriptor {label} provenance mismatch for {field}"
                )
        _v6_2_recompute_source_definition(descriptor)
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
        for field in (
            "array_path",
            "owner_row_array_path",
            "canonical_layout_path",
        ):
            _v6_2_resolve_under(frozen_root, descriptor[field], field)
        descriptors[label] = descriptor
        metadata_hashes[label] = hashlib.sha256(raw).hexdigest()
    return descriptors, metadata_hashes


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
    descriptors, descriptor_metadata_hashes = _v6_2_load_frozen_rhs_descriptors(
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
                descriptors,
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
        "aggregate_root": str(aggregate_root),
        "frozen_input_root": str(frozen_input_root),
        "frozen_rhs_source_provenance": _json_safe(source_provenance),
        "qualification_source_provenance": _json_safe(current_provenance),
        "frozen_rhs_descriptor_metadata_sha256": _json_safe(
            descriptor_metadata_hashes
        ),
        "authority_identity_chain": {
            "frozen_rhs_source_provenance": _json_safe(frozen_provenance),
            "qualification_source_provenance": _json_safe(current_provenance),
            "frozen_rhs_descriptor_metadata_sha256": _json_safe(
                descriptor_metadata_hashes
            ),
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
        "packet_aggregate_gate_pass": bool(
            value.get("packet_aggregate_gate_pass", False)
        ),
        "source_residual_ledger": source_residual_ledger,
        "packet_aggregate_refs": packet_aggregate_refs,
        "authority_identity_chain": public_identity_chain,
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


def _emit(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(stage, detail)


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
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        )
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
    exact_qualification: Mapping[str, Any] | None = None,
    v6_3_continuation: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the V6-2 identity route after metadata/resource preflight."""

    from benchmarks.task040_level_a import (
        _v5_authority_identity_preflight,
        _v5_write_operator_semantics_audit,
        audit_artificial_z_interface_support,
        build_current_gamma_layout,
        _petsc_matrix_hash,
        assemble_current_bare_f_authority_system,
    )

    output_argument = Path(run_directory)
    if not output_argument.is_absolute():
        raise ValueError("V6-2 output root must be absolute")
    output_root, frozen_root = _assert_disjoint_roots(
        output_argument, exact_spool_root
    )
    if exact_qualification is not None:
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
        )

    resource_preflight = _resource_preflight(
        comm,
        output_root,
        hard_stop_bytes=int(hard_stop_bytes),
        watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
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
    shared_lifecycle: Mapping[str, Any] | None = None
    try:
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=float(profile.bottom_interface_nm),
            top_interface_z_nm=float(profile.top_interface_nm),
            source_work_directory=output_root / "source",
            selected_mode_provider=None,
            external_mode_authority=identity_preflight["external_mode_authority"],
            external_mode_current_resolved_config_sha256=str(
                identity_preflight["observed"]["resolved_config_sha256"]
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
        for name, z_value in (("lower", z_values[2]), ("upper", z_values[4])):
            support = audit_artificial_z_interface_support(
                system.V,
                system.static_condensation.condensed,
                float(z_value),
            )
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
        oracle = build_petsc_interface_schur_oracle(system.F, group_rows, supports)
        matrix, action = build_petsc_full_interface_schur_action(
            oracle,
            canonical_layout=canonical_layout,
            own_oracle=True,
        )
        action_before = action.diagnostics
        bare_operator_hash = _petsc_matrix_hash(system.F)
        bound_exact_configuration = exact_qualification
        if exact_qualification is not None:
            binding_error: str | None = None
            try:
                bound_exact_configuration = _bind_v6_2_formal_exact_configuration(
                    exact_qualification,
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
        if v6_3_continuation is not None and exact_qualification is None:
            raise ValueError(
                "V6-3 continuation requires the same-process exact qualification"
            )
        if exact_qualification is not None:
            if not all(bool(value) for value in gate_before_cleanup.values()):
                shared_lifecycle = {
                    "status": "not_run_by_v6_2_identity_gate",
                    "same_live_action": False,
                }
            else:
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
                    continuation=v6_3_continuation,
                )
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
            descriptor_binding_sha = exact_qualification_result.get(
                "frozen_rhs_descriptor_metadata_binding_sha256"
            )
            exact_rank_payload = {
                "schema": "task040.v6_2.exact_qualification_rank_artifact.v1",
                "rank": int(comm.rank),
                "mpi_size": int(comm.size),
                "qualification_source_sha": str(source_sha),
                "bare_f_operator_hash": str(bare_operator_hash),
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
                "frozen_rhs_descriptor_metadata_binding_sha256": _json_safe(
                    descriptor_binding_sha
                ),
                "exact_result": _json_safe(exact_qualification_result),
            }
            exact_rank_sha = _write_json(exact_rank_path, exact_rank_payload)
            if hash_file_sha256(exact_rank_path) != exact_rank_sha:
                raise RuntimeError(
                    "V6-2 exact qualification rank artifact hash reread failed"
                )
            exact_qualification_artifact = {
                "rank": int(comm.rank),
                "path": str(exact_rank_path.relative_to(output_root)),
                "sha256": exact_rank_sha,
                "qualification_source_sha": str(source_sha),
                "frozen_rhs_source_sha": str(
                    exact_qualification_result.get(
                        "frozen_rhs_source_provenance", {}
                    ).get("source_sha", "")
                ),
            }
        exact_stage_summary = _compact_exact_stage_summary(
            exact_qualification_result
        )
        continuation_result = (
            None
            if shared_lifecycle is None
            else shared_lifecycle.get("continuation")
        )
        continuation_stage_summary = _compact_exact_stage_summary(
            continuation_result
        )
        exact_pde_status = _exact_pde_status(exact_stage_summary)
        rank_artifact = {
            "schema": "task040.v6_2.rank_artifact.v1",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
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
                    "v6_4_route_a_b": "not_run_by_v6_2_identity_only",
                    "v6_5_moving_pml": "not_run_by_v6_2_identity_only",
                    "v6_6_adaptive_schwarz": "not_run_by_v6_2_identity_only",
                    "v6_7_factor_free_local_service": "not_run_by_v6_2_identity_only",
                    "v6_8_full_hybrid": "not_run_by_v6_2_identity_only",
                    "v6_9_capacity": "not_run_by_v6_2_identity_only",
                },
                "exact_qualification_plan": build_v6_2_exact_qualification_plan(),
                "research_only": True,
            }
            _write_json(output_root / "v6_2_manifest.json", result)
        result = comm.bcast(result, root=0)
        comm.barrier()
        return _json_safe(result)
    finally:
        if action is not None:
            action.destroy()
        if matrix is not None:
            matrix.destroy()
        if system is not None:
            system.destroy()
