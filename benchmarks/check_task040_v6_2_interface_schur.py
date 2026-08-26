"""Independent raw checker for the V6-2 full-interface Schur route."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "task040.v6_2.full_interface_schur_checker.v1"
EXPECTED_FORMAL_SCHEMA = "task040.v6_2.full_interface_schur.v1"
EXPECTED_RANK_SCHEMA = "task040.v6_2.rank_artifact.v1"
EXPECTED_MPI_SIZE = 8
EXPECTED_LOWER_COUNT = 7560
EXPECTED_UPPER_COUNT = 7560
EXPECTED_JOINT_COUNT = EXPECTED_LOWER_COUNT + EXPECTED_UPPER_COUNT
ZERO_TOLERANCE = 1.0e-13
ROUNDTRIP_TOLERANCE = 1.0e-11
ACTION_TOLERANCE = 1.0e-10
HEX_DIGITS = frozenset("0123456789abcdef")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise TypeError(f"JSON root is not an object: {path}")
    return payload, _sha256(path)


def _is_hex(value: Any, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in HEX_DIGITS for character in value)
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _all_true(mapping: Any) -> bool:
    return isinstance(mapping, Mapping) and bool(mapping) and all(
        value is True for value in mapping.values()
    )


def _operator_audit_check(
    root: Path,
    manifest: Mapping[str, Any],
    read_files: list[dict[str, str]],
) -> bool:
    descriptor = manifest.get("operator_semantics_audit")
    if not isinstance(descriptor, Mapping):
        return False
    relative = descriptor.get("path")
    expected_sha = descriptor.get("sha256")
    if not isinstance(relative, str) or not _is_hex(expected_sha):
        return False
    path = (root / relative).resolve()
    if not _inside(path, root) or path.suffix != ".json" or not path.is_file():
        return False
    actual_sha = _sha256(path)
    read_files.append({"path": str(path.relative_to(root)), "sha256": actual_sha})
    return actual_sha == expected_sha


def _vector_gate_checks(manifest: Mapping[str, Any]) -> dict[str, bool]:
    deterministic = manifest.get("deterministic_vectors")
    if not isinstance(deterministic, Sequence) or isinstance(deterministic, (str, bytes)):
        return {"three_deterministic_vectors": False}
    checks = {"three_deterministic_vectors": len(deterministic) == 3}
    max_repeat = 0.0
    max_roundtrip = 0.0
    max_action = 0.0
    max_interior = 0.0
    solve_counts: list[int] = []
    for item in deterministic:
        if not isinstance(item, Mapping):
            checks["vector_records_well_formed"] = False
            continue
        required = (
            "vector_index",
            "gamma_action_error",
            "full_interior_residual_error",
            "solve_count",
            "roundtrip_error",
            "repeat_error",
        )
        if not all(key in item for key in required):
            checks["vector_records_well_formed"] = False
            continue
        numeric = [item[key] for key in required if key != "solve_count"]
        if not all(_finite(value) and float(value) >= 0.0 for value in numeric):
            checks["vector_records_finite"] = False
            continue
        solve_counts.append(int(item["solve_count"]))
        max_repeat = max(max_repeat, float(item["repeat_error"]))
        max_roundtrip = max(max_roundtrip, float(item["roundtrip_error"]))
        max_action = max(max_action, float(item["gamma_action_error"]))
        max_interior = max(max_interior, float(item["full_interior_residual_error"]))
    checks.update(
        {
            "vector_records_well_formed": checks.get("vector_records_well_formed", True),
            "vector_records_finite": checks.get("vector_records_finite", True),
            "solve_count_three_each": solve_counts == [3, 3, 3],
            "repeat_le_1e-11": max_repeat <= ROUNDTRIP_TOLERANCE,
            "roundtrip_le_1e-11": max_roundtrip <= ROUNDTRIP_TOLERANCE,
            "gamma_action_le_1e-10": max_action <= ACTION_TOLERANCE,
            "interior_residual_le_1e-10": max_interior <= ACTION_TOLERANCE,
            "zero_map_le_1e-13": _finite(manifest.get("zero_error"))
            and float(manifest["zero_error"]) <= ZERO_TOLERANCE,
            "linearity_le_1e-11": _finite(manifest.get("linearity_error"))
            and float(manifest["linearity_error"]) <= ROUNDTRIP_TOLERANCE,
        }
    )
    return checks


def _json_signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _rank_gate_checks(
    rank_artifacts: Sequence[Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "rank_artifacts_complete": len(rank_artifacts) == EXPECTED_MPI_SIZE,
        "rank_artifacts_are_mappings": all(
            isinstance(artifact, Mapping) for artifact in rank_artifacts
        ),
        "rank_artifact_schema": True,
        "rank_identity_pass": True,
        "rank_resource_pass": True,
        "rank_system_forbidden_zero": True,
        "rank_no_numeric_allgather": True,
        "rank_no_full_replica": True,
        "rank_mapping_matches_layout": True,
        "rank_mapping_count_observed": True,
        "rank_mpi_size": True,
        "rank_factor_lifecycle": True,
        "rank_factor_lifecycle_observed": True,
        "rank_factor_lifecycle_consistent": True,
        "rank_deterministic_scalars_consistent": True,
        "rank_zero_linearity_consistent": True,
        "rank_identity_gate_consistent": True,
        "rank_provenance_consistent": True,
        "rank_mapping_count_sum": False,
    }
    ranks: list[int] = []
    operator_hashes: list[str] = []
    mapping_hashes: list[str] = []
    mapping_counts: list[int] = []
    deterministic_signatures: list[str] = []
    identity_signatures: list[str] = []
    zero_values: list[float] = []
    linearity_values: list[float] = []
    lifecycle_by_rank: dict[int, Any] = {}
    for artifact in rank_artifacts:
        if not isinstance(artifact, Mapping):
            checks["rank_artifact_schema"] = False
            continue
        ranks.append(int(artifact.get("rank", -1)))
        checks["rank_artifact_schema"] &= artifact.get("schema") == EXPECTED_RANK_SCHEMA
        checks["rank_mpi_size"] = checks.get("rank_mpi_size", True) and (
            artifact.get("mpi_size") == EXPECTED_MPI_SIZE
        )
        checks["rank_identity_pass"] &= artifact.get("identity_preflight", {}).get("pass") is True
        checks["rank_resource_pass"] &= artifact.get("resource_preflight_pass") is True
        checks["rank_system_forbidden_zero"] &= artifact.get("matrix_objects") == {
            "C": 0,
            "D": 0,
            "H": 0,
        }
        checks["rank_system_forbidden_zero"] &= artifact.get("qep_calls") == 0
        checks["rank_no_numeric_allgather"] &= (
            artifact.get("numeric_allgather") is False
            and artifact.get("fe_numeric_allgather") is False
        )
        checks["rank_no_full_replica"] &= artifact.get("full_interface_numeric_replica") is False
        layout = artifact.get("canonical_interface_layout", {})
        checks["rank_mapping_matches_layout"] &= (
            layout.get("owner_local_mapping_count") == artifact.get("canonical_mapping_count")
        )
        mapping_count = artifact.get("canonical_mapping_count")
        if isinstance(mapping_count, int) and not isinstance(mapping_count, bool):
            mapping_counts.append(mapping_count)
        else:
            checks["rank_mapping_count_observed"] = False
            checks["rank_mapping_matches_layout"] = False
        deterministic = artifact.get("deterministic_vectors")
        if isinstance(deterministic, Sequence) and not isinstance(
            deterministic, (str, bytes)
        ):
            deterministic_signatures.append(_json_signature(deterministic))
        else:
            checks["rank_deterministic_scalars_consistent"] = False
        if _finite(artifact.get("zero_error")) and _finite(
            artifact.get("linearity_error")
        ):
            zero_values.append(float(artifact["zero_error"]))
            linearity_values.append(float(artifact["linearity_error"]))
        else:
            checks["rank_zero_linearity_consistent"] = False
        identity_gate = artifact.get("identity_gate")
        if isinstance(identity_gate, Mapping):
            identity_signatures.append(_json_signature(identity_gate))
        else:
            checks["rank_identity_gate_consistent"] = False
        after = artifact.get("factor_lifecycle_after", {})
        lifecycle_observed = isinstance(after, Mapping) and all(
            key in after
            and isinstance(after[key], int)
            and not isinstance(after[key], bool)
            for key in ("ready", "after_cleanup", "simultaneous_max")
        )
        checks["rank_factor_lifecycle_observed"] &= lifecycle_observed
        if lifecycle_observed:
            lifecycle_by_rank[int(artifact["rank"])] = after
        checks["rank_factor_lifecycle"] &= (
            lifecycle_observed
            and after.get("ready") == 3
            and after.get("after_cleanup") == 0
            and after.get("simultaneous_max") == 3
        )
        operator_hash = artifact.get("bare_f_operator_hash")
        if _is_hex(operator_hash):
            operator_hashes.append(operator_hash)
        mapping_hash = artifact.get("canonical_mapping_sha256")
        if _is_hex(mapping_hash):
            mapping_hashes.append(mapping_hash)
        checks["rank_provenance_consistent"] &= (
            artifact.get("source_sha") == manifest.get("source_sha")
            and artifact.get("input_sha256") == manifest.get("input_sha256")
            and artifact.get("physical_model_sha256")
            == manifest.get("physical_model_sha256")
        )
    checks["ranks_exactly_0_to_7"] = sorted(ranks) == list(range(EXPECTED_MPI_SIZE))
    checks["operator_hashes_present_and_equal"] = (
        len(operator_hashes) == EXPECTED_MPI_SIZE
        and len(set(operator_hashes)) == 1
        and operator_hashes[0] == manifest.get("bare_f_operator_hash")
    )
    checks["mapping_hashes_present"] = len(mapping_hashes) == EXPECTED_MPI_SIZE
    checks["rank_mapping_count_sum"] = (
        len(mapping_counts) == EXPECTED_MPI_SIZE
        and sum(mapping_counts) == EXPECTED_JOINT_COUNT
    )
    checks["rank_mapping_count_observed"] &= len(mapping_counts) == EXPECTED_MPI_SIZE
    manifest_after_by_rank = manifest.get("factor_lifecycle", {}).get(
        "after_by_rank"
    )
    checks["rank_factor_lifecycle_consistent"] = (
        isinstance(manifest_after_by_rank, Sequence)
        and not isinstance(manifest_after_by_rank, (str, bytes))
        and len(manifest_after_by_rank) == EXPECTED_MPI_SIZE
        and sorted(lifecycle_by_rank) == list(range(EXPECTED_MPI_SIZE))
        and all(
            _json_signature(manifest_after_by_rank[rank])
            == _json_signature(lifecycle_by_rank[rank])
            for rank in range(EXPECTED_MPI_SIZE)
        )
    )
    checks["rank_deterministic_scalars_consistent"] &= (
        len(deterministic_signatures) == EXPECTED_MPI_SIZE
        and len(set(deterministic_signatures)) == 1
        and deterministic_signatures[0]
        == _json_signature(manifest.get("deterministic_vectors"))
    )
    checks["rank_zero_linearity_consistent"] &= (
        len(zero_values) == EXPECTED_MPI_SIZE
        and len(linearity_values) == EXPECTED_MPI_SIZE
        and len(set(zero_values)) == 1
        and len(set(linearity_values)) == 1
        and zero_values[0] == manifest.get("zero_error")
        and linearity_values[0] == manifest.get("linearity_error")
    )
    checks["rank_identity_gate_consistent"] &= (
        len(identity_signatures) == EXPECTED_MPI_SIZE
        and len(set(identity_signatures)) == 1
        and identity_signatures[0] == _json_signature(manifest.get("identity_gate"))
    )
    checks["rank_identity_gate_all_true"] = bool(
        rank_artifacts
        and all(
            isinstance(artifact, Mapping)
            and isinstance(artifact.get("identity_gate"), Mapping)
            and _all_true(artifact["identity_gate"])
            for artifact in rank_artifacts
        )
    )
    checks["rank_scalar_records_finite"] = bool(
        len(zero_values) == EXPECTED_MPI_SIZE
        and len(linearity_values) == EXPECTED_MPI_SIZE
    )
    checks["rank_mapping_sum_is_joint_size"] = checks["rank_mapping_count_sum"]
    checks["rank_artifacts_are_mappings"] &= len(
        [artifact for artifact in rank_artifacts if isinstance(artifact, Mapping)]
    ) == EXPECTED_MPI_SIZE
    return checks


def check_v6_2_interface_schur(
    *,
    formal_root: str | Path,
    formal_source_sha: str,
    checker_source_sha: str,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute V6-2 evidence and gates from JSON artifacts only."""

    root = Path(formal_root).resolve()
    output_path = None if output is None else Path(output).resolve()
    if output_path is not None and _inside(output_path, root):
        raise ValueError("checker output must be outside the formal root")
    read_files: list[dict[str, str]] = []
    evidence: dict[str, bool] = {}
    gate: dict[str, bool] = {}
    manifest_path = root / "v6_2_manifest.json"
    if not root.is_dir() or not manifest_path.is_file():
        raise FileNotFoundError(f"V6-2 manifest is missing: {manifest_path}")
    manifest, manifest_sha = _read_json(manifest_path)
    read_files.append({"path": str(manifest_path.relative_to(root)), "sha256": manifest_sha})

    evidence["formal_schema"] = manifest.get("schema") == EXPECTED_FORMAL_SCHEMA
    evidence["source_sha"] = manifest.get("source_sha") == str(formal_source_sha)
    evidence["checker_source_sha_input"] = _is_hex(checker_source_sha, 40)
    evidence["mpi_size"] = manifest.get("mpi_size") == EXPECTED_MPI_SIZE
    evidence["identity_preflight"] = (
        manifest.get("identity_preflight", {}).get("pass") is True
        and _all_true(manifest.get("identity_preflight", {}).get("checks"))
    )
    evidence["resource_preflight"] = (
        manifest.get("resource_preflight", {}).get("pass") is True
        and _all_true(manifest.get("resource_preflight", {}).get("checks"))
    )
    evidence["operator_semantics_audit"] = _operator_audit_check(
        root, manifest, read_files
    )
    evidence["input_hashes_present"] = _is_hex(manifest.get("input_sha256")) and _is_hex(
        manifest.get("physical_model_sha256")
    )
    evidence["system_created"] = manifest.get("system_created") is True
    evidence["matrix_objects_zero"] = manifest.get("matrix_objects") == {
        "C": 0,
        "D": 0,
        "H": 0,
    }
    evidence["qep_zero"] = manifest.get("qep_calls") == 0
    evidence["no_forbidden_factors"] = (
        manifest.get("full_side_exact_factor_count") == 0
        and manifest.get("global_direct_factor_count") == 0
        and manifest.get("exact_output_vectors_loaded") == 0
    )
    evidence["pde_not_run"] = manifest.get("pde_solve") == "not_run"
    evidence["owner_distributed_contract"] = (
        manifest.get("numeric_allgather") is False
        and manifest.get("fe_numeric_allgather") is False
        and manifest.get("full_interface_numeric_replica") is False
        and manifest.get("root_metadata_gather") is True
        and manifest.get("per_rank_full_interface_replica") is False
        and manifest.get("raw_global_row_remap") is False
    )
    evidence["support_metadata_distinction"] = (
        manifest.get("root_metadata_gather") is True
        and manifest.get("support_metadata_replicated") is True
        and manifest.get("per_rank_full_interface_replica") is False
        and manifest.get("numeric_allgather") is False
    )

    layout = manifest.get("canonical_interface_layout", {})
    canonical_layout_gate = (
        layout.get("global_size") == EXPECTED_JOINT_COUNT
        and layout.get("lower_global_rows") == EXPECTED_LOWER_COUNT
        and layout.get("upper_global_rows") == EXPECTED_UPPER_COUNT
        and layout.get("canonical_order") == "Gamma_L_then_Gamma_U_by_physical_key"
        and layout.get("canonical_position_bijection") is True
        and layout.get("coverage_exact") is True
        and layout.get("owner_distributed") is True
        and layout.get("root_metadata_gather") is True
        and layout.get("per_rank_full_interface_replica") is False
        and layout.get("numeric_allgather") is False
        and layout.get("value_basis") == "current_raw_active_coefficients"
        and layout.get("canonical_block_transforms_applied") is False
    )
    evidence["canonical_layout_recorded"] = isinstance(layout, Mapping) and all(
        key in layout
        for key in (
            "global_size",
            "lower_global_rows",
            "upper_global_rows",
            "canonical_order",
            "canonical_position_bijection",
            "coverage_exact",
            "owner_distributed",
            "root_metadata_gather",
            "per_rank_full_interface_replica",
            "numeric_allgather",
            "value_basis",
            "canonical_block_transforms_applied",
        )
    )
    gamma_counts = manifest.get("gamma_counts", {})
    gamma_counts_gate = gamma_counts == {
        "Gamma_L": EXPECTED_LOWER_COUNT,
        "Gamma_U": EXPECTED_UPPER_COUNT,
        "joint": EXPECTED_JOINT_COUNT,
    }
    evidence["gamma_counts_recorded"] = isinstance(gamma_counts, Mapping) and all(
        isinstance(gamma_counts.get(key), int)
        and not isinstance(gamma_counts.get(key), bool)
        for key in ("Gamma_L", "Gamma_U", "joint")
    )

    rank_descriptors = manifest.get("rank_artifacts")
    if not isinstance(rank_descriptors, Sequence) or isinstance(rank_descriptors, (str, bytes)):
        rank_descriptors = []
    rank_artifacts: list[Mapping[str, Any]] = []
    descriptor_paths: set[str] = set()
    descriptor_hashes: list[str] = []
    for descriptor in rank_descriptors:
        if not isinstance(descriptor, Mapping):
            evidence["rank_descriptor_contract"] = False
            continue
        relative = descriptor.get("path")
        expected_sha = descriptor.get("sha256")
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or not _is_hex(expected_sha)
            or relative in descriptor_paths
        ):
            evidence["rank_descriptor_contract"] = False
            continue
        path = (root / relative).resolve()
        if not _inside(path, root) or path.suffix != ".json" or not path.is_file():
            evidence["rank_descriptor_contract"] = False
            continue
        descriptor_paths.add(relative)
        artifact, actual_sha = _read_json(path)
        read_files.append({"path": relative, "sha256": actual_sha})
        descriptor_hashes.append(actual_sha)
        if (
            actual_sha != expected_sha
            or artifact.get("rank") != descriptor.get("rank")
            or artifact.get("canonical_mapping_count")
            != descriptor.get("canonical_mapping_count")
            or artifact.get("canonical_mapping_sha256")
            != descriptor.get("canonical_mapping_sha256")
            or artifact.get("factor_lifecycle_after")
            != descriptor.get("factor_lifecycle_after")
        ):
            evidence["rank_descriptor_hashes"] = False
        rank_artifacts.append(artifact)
    evidence["rank_descriptor_contract"] = evidence.get("rank_descriptor_contract", True) and len(rank_descriptors) == EXPECTED_MPI_SIZE
    evidence["rank_descriptor_hashes"] = evidence.get("rank_descriptor_hashes", True) and len(descriptor_hashes) == EXPECTED_MPI_SIZE
    evidence["no_npy_read"] = all(not item["path"].lower().endswith(".npy") for item in read_files)
    rank_checks = _rank_gate_checks(rank_artifacts, manifest)
    rank_integrity_names = (
        "rank_artifacts_complete",
        "rank_artifacts_are_mappings",
        "rank_artifact_schema",
        "rank_mpi_size",
        "rank_identity_pass",
        "rank_resource_pass",
        "rank_system_forbidden_zero",
        "rank_no_numeric_allgather",
        "rank_no_full_replica",
        "rank_mapping_matches_layout",
        "rank_mapping_count_observed",
        "rank_factor_lifecycle_observed",
        "rank_factor_lifecycle_consistent",
        "rank_deterministic_scalars_consistent",
        "rank_zero_linearity_consistent",
        "rank_identity_gate_consistent",
        "rank_provenance_consistent",
        "ranks_exactly_0_to_7",
        "operator_hashes_present_and_equal",
        "mapping_hashes_present",
        "rank_scalar_records_finite",
    )
    rank_gate_names = (
        "rank_factor_lifecycle",
        "rank_identity_gate_all_true",
        "rank_mapping_count_sum",
    )
    rank_integrity_checks = {
        name: bool(rank_checks.get(name, False)) for name in rank_integrity_names
    }
    rank_gate_checks = {
        name: bool(rank_checks.get(name, False)) for name in rank_gate_names
    }
    evidence.update(
        {f"evidence_{name}": value for name, value in rank_integrity_checks.items()}
    )
    evidence["rank_integrity"] = all(rank_integrity_checks.values())

    lifecycle = manifest.get("factor_lifecycle", {})
    after_by_rank = lifecycle.get("after_by_rank")
    after_is_valid = isinstance(after_by_rank, Sequence) and not isinstance(
        after_by_rank, (str, bytes)
    ) and len(after_by_rank) == EXPECTED_MPI_SIZE and all(
        isinstance(item, Mapping)
        and all(
            key in item
            and isinstance(item[key], int)
            and not isinstance(item[key], bool)
            for key in ("ready", "after_cleanup", "simultaneous_max")
        )
        for item in after_by_rank
    )
    derived_construction = (
        [int(item["ready"]) for item in after_by_rank]
        if after_is_valid
        else []
    )
    derived_destruction = (
        [int(item["ready"]) - int(item["after_cleanup"]) for item in after_by_rank]
        if after_is_valid
        else []
    )
    derived_simultaneous = (
        [int(item["simultaneous_max"]) for item in after_by_rank]
        if after_is_valid
        else []
    )
    evidence["factor_lifecycle_recorded"] = (
        after_is_valid
        and all(
            isinstance(lifecycle.get(name), int)
            and not isinstance(lifecycle.get(name), bool)
            for name in ("construction_count", "destruction_count", "simultaneous_max")
        )
    )
    lifecycle_gate = (
        evidence["factor_lifecycle_recorded"]
        and len(set(derived_construction)) == 1
        and len(set(derived_destruction)) == 1
        and len(set(derived_simultaneous)) == 1
        and derived_construction[0] == 3
        and derived_destruction[0] == 3
        and derived_simultaneous[0] == 3
        and lifecycle.get("construction_count") == derived_construction[0]
        and lifecycle.get("destruction_count") == derived_destruction[0]
        and lifecycle.get("simultaneous_max") == max(derived_simultaneous)
        and lifecycle.get("rank_consensus") is True
    )
    qualification = manifest.get("exact_qualification_plan")
    evidence["exact_qualification_plan"] = (
        isinstance(qualification, Mapping)
        and qualification.get("status") == "designed_not_run"
        and qualification.get("source_order") == [
            "external_dtn_coupling",
            "fixed_random_repeat_0",
            "modal_traction_positive",
            "modal_traction_negative",
            "fixed_random_repeat_1",
        ]
        and qualification.get("checkpoints") == [16, 32, 64, 128]
        and qualification.get("conditional_checkpoints") == [256, 512]
        and qualification.get("rhs_layout")
        == "current_canonical_active_keys_owner_local"
        and qualification.get("interface_rhs")
        == "g=b_Gamma-A_GammaI*A_II^-1*b_I"
        and qualification.get("solution_recovery")
        == "x_I=A_II^-1*(b_I-A_I,Gamma*x_Gamma)"
        and qualification.get("full_residual")
        == "independent_current_bare_F_mult"
        and qualification.get("first_two_gate")
        == "each relative true residual <= 1e-9"
        and qualification.get("one_cell_source_factor") == "not_reexecuted"
        and qualification.get("frozen_owner_row_arrays")
        == "not_loaded; complex PETSc owner-order values, never row ids"
    )

    gate.update(_vector_gate_checks(manifest))
    gate["factor_lifecycle"] = lifecycle_gate
    gate["rank_factor_lifecycle"] = rank_gate_checks["rank_factor_lifecycle"]
    gate["rank_identity_gate"] = rank_gate_checks["rank_identity_gate_all_true"]
    gate["rank_deterministic_scalars"] = rank_checks[
        "rank_deterministic_scalars_consistent"
    ]
    gate["rank_mapping_count_sum"] = rank_gate_checks["rank_mapping_count_sum"]
    gate["rank_owner_mapping"] = (
        rank_checks["rank_artifacts_complete"]
        and rank_checks["ranks_exactly_0_to_7"]
        and rank_checks["rank_mapping_matches_layout"]
    )
    gate["canonical_layout"] = canonical_layout_gate
    gate["gamma_counts"] = gamma_counts_gate
    gate["forbidden_objects_zero"] = evidence["matrix_objects_zero"] and evidence["qep_zero"] and evidence["no_forbidden_factors"]
    gate["exact_qualification_plan_recorded"] = evidence["exact_qualification_plan"]
    gate_pass = bool(all(gate.values()))
    evidence_valid = bool(all(evidence.values()))
    checker_pass = evidence_valid
    if not evidence_valid:
        classification = "IMPLEMENTATION_FAILURE"
    elif gate_pass:
        classification = "V6_2_FULL_INTERFACE_SCHUR_PASS"
    else:
        classification = "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
    return {
        "schema": SCHEMA,
        "formal_root": str(root),
        "formal_root_sha256": manifest_sha,
        "formal_source_sha": str(formal_source_sha),
        "checker_source_sha": str(checker_source_sha),
        "evidence_valid": evidence_valid,
        "checker_pass": checker_pass,
        "gate_pass": gate_pass,
        "classification": classification,
        "evidence_checks": evidence,
        "gate_checks": gate,
        "rank_integrity_checks": rank_integrity_checks,
        "rank_gate_checks": rank_gate_checks,
        "read_files": read_files,
        "npy_read": False,
        "output_disjoint_from_formal_root": (
            None if output_path is None else not _inside(output_path, root)
        ),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(
        json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", required=True)
    parser.add_argument("--formal-source-sha", required=True)
    parser.add_argument("--checker-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    root = Path(args.formal_root).resolve()
    output = Path(args.output).resolve()
    if _inside(output, root):
        print("V6-2 checker output must be outside formal root")
        return 2
    try:
        result = check_v6_2_interface_schur(
            formal_root=root,
            formal_source_sha=args.formal_source_sha,
            checker_source_sha=args.checker_source_sha,
            output=output,
        )
    except Exception as exc:  # evidence corruption is a checker failure, not a solver result
        result = {
            "schema": SCHEMA,
            "formal_root": str(root),
            "formal_source_sha": str(args.formal_source_sha),
            "checker_source_sha": str(args.checker_source_sha),
            "evidence_valid": False,
            "checker_pass": False,
            "gate_pass": False,
            "classification": "IMPLEMENTATION_FAILURE",
            "error": f"{type(exc).__name__}: {exc}",
            "read_files": [],
            "npy_read": False,
            "output_disjoint_from_formal_root": True,
        }
    _write_json(output, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["checker_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
