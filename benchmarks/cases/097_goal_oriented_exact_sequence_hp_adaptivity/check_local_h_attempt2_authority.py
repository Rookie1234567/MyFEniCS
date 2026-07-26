#!/usr/bin/env python3
"""Independent fail-closed checker for Task035d Attempt2 authorities."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
CHECKER_RELATIVE = (
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "check_local_h_attempt2_authority.py"
)
SCHEMA = "case097.local-h-attempt2-authority.v3"
EXPECTED_NAMES = {
    1: "local_h_attempt2_mpi1_v3.json",
    2: "local_h_attempt2_mpi2_v3.json",
    8: "local_h_attempt2_mpi8_v3.json",
}
FORMAL_OUTPUT_NAME = "local_h_attempt2_mpi_identity_v3.json"
FIXTURE_CONFIG = {
    "root_cells": [3, 3, 1],
    "refined_root": [0, 0, 0, 0, 0],
    "periodic_axes": ["x", "y"],
    "trace_degree": 5,
    "cell_interior_degree": 6,
    "phase_x": [float(np.cos(0.2)), float(np.sin(0.2))],
    "phase_y": [float(np.cos(-0.3)), float(np.sin(-0.3))],
    "form": "curlcurl + (2.5+0.17j) mass",
}
NUMERICAL_RELATIVE_FILES = (
    "src/adaptivity/dyadic_hexa_refinement.py",
    "src/adaptivity/dyadic_hexa_broken_mesh.py",
    "src/adaptivity/hcurl_hanging_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_trace_constraint_graph.py",
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/constraints/high_order_floquet_trace.py",
    "src/solvers/hcurl_assembly_time_condensation.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/solvers/hcurl_variable_p_assembly.py",
    "src/solvers/hcurl_variable_p_reduction.py",
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "generate_local_h_attempt2_authority.py"
    ),
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "check_local_h_attempt2_authority.py"
    ),
)
PRIOR_AUTHORITY_SHA256 = {
    "phase_a_compact": (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/compact_authority_v1.json",
        "2e896ef45bbfc5c11901503269d11c0321106c9e41f71729ac7c6fc722687403",
    ),
    "phase_a_reference_active_space": (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/reference_active_space_authority_v1.json",
        "4c1c5e68540dca4ddcc4165b0cc175abb4671ad254a44c1aa3518e4c9398ea9b",
    ),
    "local_h_attempt1_mpi_identity": (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "records/local_h_attempt1_mpi_identity_v1.json",
        "d341ad69dd52df6bbedcec8a522084cd75ae99fd9fd7d751bab7bfb73655fe44",
    ),
}
ATTEMPT2_HISTORY = {
    "mpi1_v1": (
        "local_h_attempt2_mpi1_v1.json",
        "ebe88241242603971eaaba89735c893a5445f416486e02c0fa1b0647a44ddfbc",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi2_v1": (
        "local_h_attempt2_mpi2_v1.json",
        "05c526a728538065bb00b49e0d578365173babad18933fd607e4b46d0546e354",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi8_v1": (
        "local_h_attempt2_mpi8_v1.json",
        "c0bf2e9b14fd5852d3d65f71aa2fea7c6362ffa96d997eb020bb312ec11df5cd",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "identity_v1_controlled_failure": (
        "local_h_attempt2_mpi_identity_v1.json",
        "9afcacd1e855ed08dd2609ae54b5c1de1fb3d97a783bc29d12b76bb767398411",
        "local_h_attempt2_evidence_fail",
        False,
    ),
    "mpi1_v2": (
        "local_h_attempt2_mpi1_v2.json",
        "6a4ae7312402e94653206b68ed54a825703f89bef7bbb787d2abf777d3d5a6af",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi2_v2": (
        "local_h_attempt2_mpi2_v2.json",
        "b135f618880883d0b9360be3483c0cf0aa786710588a61479db5e845981f2405",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi8_v2": (
        "local_h_attempt2_mpi8_v2.json",
        "7814a3bac9da53557218947afec48f9fd8a544eed9cb3c59cafd94baeff08f12",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "identity_v2_controlled_failure": (
        "local_h_attempt2_mpi_identity_v2.json",
        "d72d3bb204c6ed0f2bb57fa701ce81b55f61ee090c2d9247c59679f1df5bed9a",
        "local_h_attempt2_evidence_fail",
        False,
    ),
    "identity_v2_checker_fix1": (
        "local_h_attempt2_mpi_identity_v2_checker_fix1.json",
        "63a5aea0c8f10984e7959ce9f186cc36bb5a4a06d207f8f184bcaf2284b10bcd",
        "local_h_attempt2_component_pass_pde_blocked",
        True,
    ),
}
EXPECTED_P5_RESTRICTION_SHA256 = (
    "90bd8eb7c612f044c0026ce0551c2f96d8241adc9b63b8e402652b5b738ccf2a"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _balanced_ranges(total: int, size: int) -> list[tuple[int, int]]:
    quotient, remainder = divmod(int(total), int(size))
    ranges: list[tuple[int, int]] = []
    start = 0
    for rank in range(int(size)):
        stop = start + quotient + (1 if rank < remainder else 0)
        ranges.append((start, stop))
        start = stop
    return ranges


def _canonical_entity_catalog(
    payload: Any,
) -> tuple[list[tuple[int, tuple[int, ...]]], list[list[Any]]]:
    entities = [
        (int(row[0]), tuple(map(int, row[1])))
        for row in payload
    ]
    canonical = sorted(entities)
    canonical_payload = [
        [dimension, list(geometry_key)]
        for dimension, geometry_key in canonical
    ]
    if len(set(entities)) != len(entities) or payload != canonical_payload:
        raise ValueError("physical entity catalog is not canonical")
    return canonical, canonical_payload


def _strict_load(path: Path) -> Mapping[str, Any]:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject,
    )
    if not isinstance(payload, dict):
        raise TypeError("record root must be an object")
    return payload


def _all_finite(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_finite(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def _solver_blob_manifest(source_sha: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("solver source SHA is invalid")
    result = {}
    for relative in NUMERICAL_RELATIVE_FILES:
        content = subprocess.check_output(
            ("git", "show", f"{source_sha}:{relative}"),
            cwd=ROOT,
        )
        result[relative] = hashlib.sha256(content).hexdigest()
    return result


def _live_numerical_source_identity(head: str) -> dict[str, Any]:
    committed = _solver_blob_manifest(head)
    live = {
        relative: _sha256(ROOT / relative)
        for relative in NUMERICAL_RELATIVE_FILES
    }
    status_lines = [
        line
        for line in subprocess.check_output(
            (
                "git",
                "status",
                "--short",
                "--untracked-files=all",
                "--",
                *NUMERICAL_RELATIVE_FILES,
            ),
            cwd=ROOT,
            text=True,
        ).splitlines()
        if line
    ]
    mismatched_files = sorted(
        relative
        for relative in NUMERICAL_RELATIVE_FILES
        if live.get(relative) != committed.get(relative)
    )
    return {
        "live_sha256": live,
        "committed_sha256": committed,
        "status_lines": status_lines,
        "mismatched_files": mismatched_files,
        "verified_clean_numerical_source": (
            not status_lines and not mismatched_files
        ),
    }


def _live_checker_identity() -> dict[str, Any]:
    head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        text=True,
    ).strip()
    committed = subprocess.check_output(
        ("git", "show", f"{head}:{CHECKER_RELATIVE}"),
        cwd=ROOT,
    )
    status_lines = [
        line
        for line in subprocess.check_output(
            (
                "git",
                "status",
                "--short",
                "--untracked-files=all",
                "--",
                CHECKER_RELATIVE,
            ),
            cwd=ROOT,
            text=True,
        ).splitlines()
        if line
    ]
    live_sha256 = _sha256(Path(__file__))
    committed_sha256 = hashlib.sha256(committed).hexdigest()
    numerical_source = _live_numerical_source_identity(head)
    return {
        "path": CHECKER_RELATIVE,
        "git_head": head,
        "live_sha256": live_sha256,
        "committed_sha256": committed_sha256,
        "status_lines": status_lines,
        "verified_clean_checker": (
            live_sha256 == committed_sha256 and not status_lines
        ),
        "numerical_source": numerical_source,
        "verified_clean_numerical_source": numerical_source[
            "verified_clean_numerical_source"
        ],
    }


def _prior_authority_manifest() -> dict[str, Any]:
    records = {}
    for name, (relative, expected_sha) in PRIOR_AUTHORITY_SHA256.items():
        path = ROOT / relative
        payload = _strict_load(path)
        if _sha256(path) != expected_sha or payload.get("pass") is not True:
            raise RuntimeError(f"prior authority drifted or failed: {name}")
        records[name] = {
            "path": relative,
            "sha256": expected_sha,
            "status": payload.get("status"),
            "pass": True,
        }
        if name == "local_h_attempt1_mpi_identity":
            restriction = payload["stable_identity"][
                "canonical_hcurl_restriction_sha256"
            ]["5"]
            if restriction != EXPECTED_P5_RESTRICTION_SHA256:
                raise RuntimeError("Attempt1 p5 restriction hash drifted")
            records[name]["p5_hanging_restriction_sha256"] = restriction
    return {
        "records": records,
        "phase_a_exact_sequence_hash_bound": True,
        "attempt1_orientation_restriction_hash_bound": True,
        "p5_hanging_restriction_sha256": (
            EXPECTED_P5_RESTRICTION_SHA256
        ),
    }


def _attempt2_history_immutability_manifest() -> dict[str, Any]:
    records: dict[str, Any] = {}
    for name, (
        filename,
        expected_sha,
        expected_status,
        expected_pass,
    ) in ATTEMPT2_HISTORY.items():
        path = RECORD_DIR / filename
        payload = _strict_load(path)
        if (
            _sha256(path) != expected_sha
            or payload.get("status") != expected_status
            or payload.get("pass") is not expected_pass
        ):
            raise RuntimeError(
                f"Attempt2 historical evidence drifted: {name}"
            )
        records[name] = {
            "path": f"records/{filename}",
            "sha256": expected_sha,
            "expected_status": expected_status,
            "expected_pass": expected_pass,
        }
    return {
        "records": records,
        "historical_failure_evidence_preserved": True,
        "history_file_count": len(records),
    }


def _validate_record(
    path: Path,
    payload: Mapping[str, Any],
    *,
    prior_manifest: Mapping[str, Any],
    history_manifest: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    try:
        mpi_size = int(payload["mpi_size"])
        source_sha = str(payload["source_sha"])
        if path.resolve().parent != RECORD_DIR.resolve():
            failures.append("record_directory")
        if path.name != EXPECTED_NAMES.get(mpi_size):
            failures.append("record_filename")
        if payload["schema_version"] != SCHEMA:
            failures.append("schema")
        if not _all_finite(payload):
            failures.append("nonfinite")
        if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
            failures.append("source_sha")
        source = payload["source_identity"]
        if not (
            source["head"] == source_sha
            and source["verified_clean_numerical_source"] is True
            and source["disallowed_status_lines"] == []
        ):
            failures.append("generation_source_identity")
        if not (
            payload["fixture_config"] == FIXTURE_CONFIG
            and payload["fixture_config_sha256"]
            == _json_sha256(FIXTURE_CONFIG)
        ):
            failures.append("fixture_config")
        if payload["prior_authorities"] != prior_manifest:
            failures.append("prior_authorities")
        if payload["attempt2_history_immutability"] != history_manifest:
            failures.append("attempt2_history_immutability")
        environment = payload["environment"]
        rank_env = environment["rank_environments"]
        comparable = [
            {key: value for key, value in row.items() if key != "rank"}
            for row in rank_env
        ]
        if not (
            environment["qualified_activation"] == "1"
            and environment["petsc_scalar_type"] == "complex128"
            and environment["petsc_int_type"] == "int32"
            and environment["rank_ids"] == list(range(mpi_size))
            and environment["all_ranks_identical"] is True
            and len(rank_env) == mpi_size
            and [row["rank"] for row in rank_env] == list(range(mpi_size))
            and all(row == comparable[0] for row in comparable[1:])
        ):
            failures.append("rank_abi")

        fixture = payload["p5_trace_p6_interior_hanging_floquet"]
        forest = fixture["forest_audit"]
        carrier = fixture["carrier_audit"]
        entity_map = fixture["entity_map_audit"]
        physical = fixture["physical_trace_audit"]
        trace = fixture["cell_trace_binding_audit"]
        routing = trace["owner_routed_trace_cache_audit"]
        assembly = fixture["assembly_audit"]
        diagnostic = fixture["raw_oracle_assembly_audit"]
        observables = fixture["observables"]
        if not (
            "canonical physical roots"
            in observables["active_rhs_semantics"]
            and "canonical forest leaf"
            in observables["full_recovery_signature_semantics"]
        ):
            failures.append("canonical_observable_semantics")
        if not (
            fixture["trace_degree"] == 5
            and fixture["cell_interior_degree"] == 6
            and forest["pass"] is True
            and carrier["pass"] is True
            and entity_map["pass"] is True
            and physical["pass"] is True
            and trace["pass"] is True
            and assembly["pass"] is True
        ):
            failures.append("component_authorities")
        if not (
            entity_map["global_entity_counts"]
            == {"1": 260, "2": 170, "3": 37}
            and entity_map["active_rows"] == 24750
            and entity_map["active_trace_rows"] == 8100
            and physical["physical_edge_count"] == 260
            and physical["physical_face_count"] == 170
            and trace["global_cell_count"] == 37
            and trace["raw_trace_rows"] == 8100
            and trace["independent_trace_rows"] == 5430
            and assembly["matrix_rows"] == 5430
            and assembly["matrix_nnz"] == 2758850
            and diagnostic["matrix_rows"] == 8100
            and diagnostic["matrix_nnz"] == 3143400
        ):
            failures.append("frozen_fixture_structure")
        if not (
            physical["periodic_axes"] == ["x", "y"]
            and physical["maximum_relation_residual"] <= 5.0e-11
            and physical["periodic_cycle_error"] <= 5.0e-11
            and physical["mpi_physical_catalog_identity_qualified"] is True
            and physical["mpi_constraint_row_ownership_qualified"] is False
            and physical["mpi_ghost_expansion_qualified"] is False
        ):
            failures.append("physical_graph")
        if not (
            trace["constraint_kinds"] == ["hanging", "floquet"]
            and trace["raw_trace_rows"]
            - trace["independent_trace_rows"]
            == trace["eliminated_hanging_or_floquet_rows"]
            and trace["maximum_entity_transform_orthogonality_error"]
            <= 5.0e-11
            and trace["maximum_cell_transform_error"] <= 5.0e-11
            and trace["maximum_unpermuted_cell_chart_error"] <= 5.0e-11
            and trace["maximum_trace_interior_mixing_error"] <= 5.0e-11
            and trace["maximum_cell_expansion_condition"] > 1.0e8
            and trace["cell_expansion_inverse_used"] is False
            and trace["distributed_scalability_qualified"] is False
        ):
            failures.append("cell_trace_binding")
        request_counts = list(map(int, routing["request_counts_by_rank"]))
        received_request_counts = list(
            map(int, routing["received_request_counts_by_rank"])
        )
        reply_counts = list(map(int, routing["reply_counts_by_rank"]))
        received_reply_counts = list(
            map(int, routing["received_reply_counts_by_rank"])
        )
        work_counts = list(
            map(int, routing["work_owned_block_counts_by_rank"])
        )
        work_bytes = list(
            map(int, routing["work_owned_native_array_bytes_by_rank"])
        )
        cache_bytes = list(
            map(int, routing["local_cache_native_array_bytes_by_rank"])
        )
        unique_owner_bytes = list(
            map(
                int,
                routing[
                    "unique_dolfinx_owner_native_array_bytes_by_rank"
                ],
            )
        )
        trace_work_ranges = [
            tuple(map(int, row))
            for row in routing["active_trace_work_ownership_ranges"]
        ]
        expected_trace_work_ranges = _balanced_ranges(
            trace["raw_trace_rows"],
            mpi_size,
        )
        unique_owner_bytes_total = sum(unique_owner_bytes)
        expected_duplication = (
            sum(cache_bytes) / unique_owner_bytes_total
            if unique_owner_bytes_total > 0
            else -1.0
        )
        if not (
            trace["petsc_constraint_row_ownership_qualified"] is True
            and trace["mpi_ghost_expansion_qualified"] is True
            and trace["pde_launch_ownership_gate"] is True
            and trace["full_dense_entity_catalog_replicated"] is False
            and trace["remote_resolution_audit_is_count_and_digest_only"]
            is True
            and routing["pass"] is True
            and routing["dense_global_entity_catalog_replicated"] is False
            and routing["declaration_catalog_is_metadata_only"] is True
            and routing["request_reply_count_closes"] is True
            and fixture["stable_identity"][
                "owner_routed_canonical_content_sha256"
            ]
            == routing["canonical_content_sha256"]
            and len(request_counts)
            == len(received_request_counts)
            == len(reply_counts)
            == len(received_reply_counts)
            == len(work_counts)
            == len(work_bytes)
            == len(cache_bytes)
            == len(unique_owner_bytes)
            == mpi_size
            and len(trace_work_ranges) == mpi_size
            and trace_work_ranges == expected_trace_work_ranges
            and all(
                value >= 0
                for value in (
                    *request_counts,
                    *received_request_counts,
                    *reply_counts,
                    *received_reply_counts,
                    *work_counts,
                )
            )
            and reply_counts == received_request_counts
            and received_reply_counts == request_counts
            and sum(request_counts)
            == sum(received_request_counts)
            == sum(reply_counts)
            == sum(received_reply_counts)
            and sum(work_counts) == routing["declaration_count"]
            and sum(trace["dolfinx_entity_owner_counts_by_rank"])
            == routing["declaration_count"]
            and all(value > 0 for value in work_bytes)
            and all(value > 0 for value in cache_bytes)
            and all(value > 0 for value in unique_owner_bytes)
            and unique_owner_bytes_total
            == routing[
                "unique_dolfinx_owner_native_array_bytes_global_sum"
            ]
            and sum(cache_bytes)
            == routing["retained_cache_native_array_bytes_global_sum"]
            and max(cache_bytes)
            == routing["retained_cache_native_array_bytes_max"]
            and np.isclose(
                routing["retained_cache_duplication_factor"],
                expected_duplication,
                rtol=0.0,
                atol=1.0e-15,
            )
            and routing["retained_cache_duplication_factor"] >= 1.0
            and routing[
                "native_array_bytes_are_logical_not_rss_pss_peak"
            ]
            is True
            and trace_work_ranges[0][0] == 0
            and trace_work_ranges[-1][1] == trace["raw_trace_rows"]
            and all(
                left[1] == right[0]
                for left, right in zip(
                    trace_work_ranges[:-1],
                    trace_work_ranges[1:],
                    strict=True,
                )
            )
            and all(
                routing[name] == 0
                for name in (
                    "missing_reply_count",
                    "duplicate_reply_count",
                    "unrequested_reply_count",
                    "wrong_owner_reply_count",
                    "stale_or_corrupt_reply_count",
                )
            )
            and all(
                isinstance(digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", digest)
                for digest in (
                    routing["canonical_content_sha256"],
                    routing["owner_assignment_sha256"],
                    trace["physical_entity_owner_sha256"],
                    trace["constraint_relation_owner_sha256"],
                )
            )
        ):
            failures.append("owner_routed_cache")
        remote_digests = trace[
            "remote_entity_lookup_local_digests_by_rank"
        ]
        root_digests = trace[
            "off_process_root_reference_local_digests_by_rank"
        ]
        remote_counts = list(
            map(int, trace["remote_entity_lookup_counts_by_rank"])
        )
        remote_hanging_lookup_counts = list(
            map(
                int,
                trace[
                    "cross_rank_hanging_remote_lookup_counts_by_rank"
                ],
            )
        )
        root_counts = list(
            map(int, trace["off_process_root_reference_counts_by_rank"])
        )
        (
            hanging_participants,
            hanging_participant_payload,
        ) = _canonical_entity_catalog(
            trace["cross_rank_hanging_participant_entities"]
        )
        (
            remote_hanging_participants,
            remote_hanging_participant_payload,
        ) = _canonical_entity_catalog(
            trace[
                "cross_rank_hanging_remote_participant_entities"
            ]
        )
        remote_resolution_payload = {
            "remote_entity_lookup_counts_by_rank": remote_counts,
            "remote_entity_lookup_local_digests_by_rank": remote_digests,
            "off_process_root_reference_counts_by_rank": root_counts,
            "off_process_root_reference_local_digests_by_rank": root_digests,
        }
        if not (
            len(remote_digests)
            == len(root_digests)
            == len(remote_counts)
            == len(remote_hanging_lookup_counts)
            == len(root_counts)
            == mpi_size
            and all(
                value >= 0
                for value in (
                    *remote_counts,
                    *remote_hanging_lookup_counts,
                    *root_counts,
                )
            )
            and all(
                isinstance(digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", digest)
                for digest in (*remote_digests, *root_digests)
            )
            and trace["remote_resolution_sha256"]
            == _json_sha256(remote_resolution_payload)
            and len(hanging_participants)
            == trace["cross_rank_hanging_participant_entity_count"]
            and trace["cross_rank_hanging_participant_entity_sha256"]
            == _json_sha256(hanging_participant_payload)
            and len(remote_hanging_participants)
            == trace[
                "cross_rank_hanging_remote_participant_entity_count"
            ]
            and trace[
                "cross_rank_hanging_remote_participant_entity_sha256"
            ]
            == _json_sha256(remote_hanging_participant_payload)
            and set(remote_hanging_participants).issubset(
                hanging_participants
            )
            and sum(remote_hanging_lookup_counts) <= sum(remote_counts)
            and len(trace["hanging_cell_ghost_counts_by_rank"])
            == mpi_size
            and all(
                int(count) == 0
                for count in trace["hanging_cell_ghost_counts_by_rank"]
            )
            and (
                (
                    mpi_size == 1
                    and trace["cross_rank_hanging_patch_count"] == 0
                    and trace["cross_rank_hanging_relation_count"] == 0
                    and sum(request_counts) == 0
                    and sum(remote_counts) == 0
                    and sum(remote_hanging_lookup_counts) == 0
                    and sum(root_counts) == 0
                    and not hanging_participants
                    and not remote_hanging_participants
                )
                or (
                    mpi_size > 1
                    and trace["cross_rank_hanging_patch_count"] > 0
                    and trace["cross_rank_hanging_relation_count"] > 0
                    and trace[
                        "cross_rank_hanging_participant_entity_count"
                    ]
                    > 0
                    and sum(remote_hanging_lookup_counts) > 0
                    and bool(remote_hanging_participants)
                    and sum(remote_counts) > 0
                    and sum(root_counts) > 0
                    and sum(request_counts) > 0
                )
            )
        ):
            failures.append("cross_rank_hanging_owner_path")
        if not (
            assembly["trace_constraint_kinds"] == ["floquet", "hanging"]
            and assembly["matrix_rows"] == trace["independent_trace_rows"]
            and assembly["hanging_or_floquet_slave_rows"]
            == trace["eliminated_hanging_or_floquet_rows"]
            and assembly["matrix_nnz"]
            == assembly["matrix_nnz_preallocated"]
            == assembly["matrix_nnz_allocated"]
            and assembly["matrix_mallocs"] == 0
            and diagnostic["matrix_nnz"]
            == diagnostic["matrix_nnz_preallocated"]
            == diagnostic["matrix_nnz_allocated"]
            and diagnostic["matrix_mallocs"] == 0
            and assembly["compiled_p6_tensor_builder"] is True
            and assembly[
                "compiled_trace_constraint_binding_complete"
            ]
            is True
            and assembly["full_p6_global_matrix_constructed"] is False
            and assembly["full_active_global_matrix_constructed"] is False
            and assembly[
                "hanging_or_floquet_slave_rows_globally_numbered"
            ]
            is False
            and assembly[
                "trace_constraint_owner_routing_qualified"
            ]
            is True
            and assembly[
                "trace_constraint_dense_global_entity_catalog_replicated"
            ]
            is False
            and assembly[
                "trace_constraint_distributed_scalability_qualified"
            ]
            is False
        ):
            failures.append("matrix_structure")
        residual_fields = (
            assembly["interior_recovery_operator_residual_max"],
            assembly["interior_adjoint_operator_residual_max"],
            observables["full_trace_recovery_max_abs_error"],
            observables[
                "full_active_rhs_recovery_mapping_max_abs_error"
            ],
            observables[
                "zero_rhs_recovered_interior_equation_relative_residual"
            ],
            observables[
                "nonzero_rhs_recovered_interior_equation_relative_residual"
            ],
        )
        if any(float(value) > 5.0e-11 for value in residual_fields):
            failures.append("recovery_residual")
        congruence = observables["implementation_congruence_errors"]
        if any(
            float(congruence[name]) > 5.0e-10
            for name in (
                "action_root_max_relative",
                "action_probe_max_relative",
                "bilinear_relative",
                "right_rhs_max_relative",
                "left_rhs_max_relative",
                "zero_rhs_recovery_max_relative",
                "nonzero_rhs_recovery_max_relative",
            )
        ):
            failures.append("implementation_congruence")
        gram = observables["component_gram"]
        if not (
            gram["rows"] == trace["independent_trace_rows"]
            and gram["hermitian_max_abs_error"] <= 5.0e-11
            and gram["dual_solve_relative_residual"] <= 5.0e-9
            and gram["primal_norm_relative_error"] <= 5.0e-11
            and gram["dual_norm_relative_error"] <= 5.0e-9
        ):
            failures.append("component_gram")
        ranges = [
            tuple(map(int, row)) for row in fixture["petsc_ownership_ranges"]
        ]
        rows = int(trace["independent_trace_rows"])
        if not (
            len(ranges) == mpi_size
            and ranges[0][0] == 0
            and ranges[-1][1] == rows
            and all(0 <= start <= stop <= rows for start, stop in ranges)
            and sum(stop - start for start, stop in ranges) == rows
            and all(
                left[1] == right[0]
                for left, right in zip(
                    ranges[:-1], ranges[1:], strict=True
                )
            )
        ):
            failures.append("petsc_ownership_ranges")
        if not (
            payload["pass"] is True
            and payload["failures"] == []
            and fixture["pass"] is True
            and fixture["failures"] == []
            and payload["status"]
            == "local_h_attempt2_owner_routed_component_pass_mpi_gate_pending"
            and payload["distributed_scalability_qualified"] is False
            and payload["pde_launch_ownership_gate"] is True
            and payload["pde_launch_gate"] is False
            and payload["heavy_pde_started"] is False
            and payload["pde_accuracy_credit"] is False
            and payload["ordinary_default_changed"] is False
        ):
            failures.append("declared_scope")
        ledger = payload["component_resource_ledger"]
        outgoing_reply_bytes = list(
            map(int, ledger["outgoing_reply_logical_bytes_by_rank"])
        )
        incoming_reply_bytes = list(
            map(int, ledger["incoming_reply_logical_bytes_by_rank"])
        )
        owned_cell_expansion_bytes = list(
            map(int, ledger["owned_cell_expansion_bytes_by_rank"])
        )
        if not (
            ledger["raw_oracle_and_candidate_co_resident"] is True
            and ledger[
                "process_peak_is_not_candidate_memory_authority"
            ]
            is True
            and ledger["factorization_or_pde_solve_memory_measured"]
            is False
            and ledger["timings_are_per_stage_mpi_max_not_rank_sum"]
            is True
            and ledger["full_dense_entity_catalog_replicated"] is False
            and ledger["replicated_entity_block_bytes_per_rank"] == 0
            and ledger[
                "native_array_bytes_are_logical_not_rss_pss_peak"
            ]
            is True
            and ledger[
                "remote_resolution_audit_is_count_and_digest_only"
            ]
            is True
            and ledger[
                "unique_dolfinx_owner_entity_block_bytes_by_rank"
            ]
            == unique_owner_bytes
            and ledger["retained_entity_block_cache_bytes_by_rank"]
            == cache_bytes
            and ledger["work_owned_entity_block_bytes_by_rank"]
            == work_bytes
            and ledger["work_owner_straddling_block_count"]
            == routing["work_owner_straddling_block_count"]
            and ledger[
                "retained_entity_block_cache_duplication_factor"
            ]
            == routing["retained_cache_duplication_factor"]
            and ledger["retained_entity_block_cache_bytes_global_sum"]
            == sum(cache_bytes)
            and ledger["retained_entity_block_cache_bytes_max"]
            == max(cache_bytes)
            and len(outgoing_reply_bytes)
            == len(incoming_reply_bytes)
            == len(owned_cell_expansion_bytes)
            == mpi_size
            and outgoing_reply_bytes
            == list(map(int, routing["reply_native_array_bytes_by_rank"]))
            and incoming_reply_bytes
            == list(
                map(
                    int,
                    routing[
                        "received_reply_native_array_bytes_by_rank"
                    ],
                )
            )
            and sum(outgoing_reply_bytes) == sum(incoming_reply_bytes)
            and all(value >= 0 for value in outgoing_reply_bytes)
            and all(value >= 0 for value in incoming_reply_bytes)
            and all(value > 0 for value in owned_cell_expansion_bytes)
            and owned_cell_expansion_bytes
            == list(map(int, trace["owned_cell_expansion_bytes_by_rank"]))
            and ledger["owned_cell_expansion_bytes_global_sum"]
            == sum(owned_cell_expansion_bytes)
            == trace["owned_cell_expansion_bytes_global_sum"]
            and ledger["replicated_component_gram_bytes_per_rank"]
            == trace["replicated_component_gram_bytes_per_rank"]
            and ledger["candidate_matrix_rows"]
            == assembly["matrix_rows"]
            and ledger["candidate_matrix_nnz"] == assembly["matrix_nnz"]
            and ledger["diagnostic_raw_matrix_rows"]
            == diagnostic["matrix_rows"]
            and ledger["diagnostic_raw_matrix_nnz"]
            == diagnostic["matrix_nnz"]
        ):
            failures.append("resource_semantics")
    except (KeyError, TypeError, ValueError, IndexError):
        failures.append("required_field_or_type")
    return sorted(set(failures))


def _signature_matches(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    try:
        if (
            int(left["size"]) != int(right["size"])
            or left["sample_indices"] != right["sample_indices"]
        ):
            return False
        for name in ("linf", "l2"):
            if not np.isclose(
                float(left[name]),
                float(right[name]),
                rtol=3.0e-10,
                atol=3.0e-11,
            ):
                return False
        left_scale = float(left["linf"])
        right_scale = float(right["linf"])
        if not (
            math.isfinite(left_scale)
            and math.isfinite(right_scale)
            and left_scale > 0.0
            and right_scale > 0.0
        ):
            return False
        # Raw sums can be strongly cancellation-conditioned.  Compare their
        # scale-free moments so an MPI reduction-order perturbation is judged
        # relative to the vector, rather than to a nearly cancelled component.
        for name in ("sum", "weighted_sum"):
            left_moment = np.asarray(left[name], dtype=np.float64)
            right_moment = np.asarray(right[name], dtype=np.float64)
            if (
                left_moment.shape != right_moment.shape
                or not np.all(np.isfinite(left_moment))
                or not np.all(np.isfinite(right_moment))
                or not np.allclose(
                    left_moment / left_scale,
                    right_moment / right_scale,
                    rtol=3.0e-10,
                    atol=3.0e-10,
                )
            ):
                return False
        left_samples = np.asarray(
            left["normalized_samples"],
            dtype=np.float64,
        )
        right_samples = np.asarray(
            right["normalized_samples"],
            dtype=np.float64,
        )
        if (
            left_samples.shape != right_samples.shape
            or not np.all(np.isfinite(left_samples))
            or not np.all(np.isfinite(right_samples))
            or not np.allclose(
                left_samples,
                right_samples,
                rtol=3.0e-10,
                atol=3.0e-10,
            )
        ):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def check_records(records: tuple[Path, ...]) -> dict[str, Any]:
    failures: list[str] = []
    payloads: list[Mapping[str, Any] | None] = []
    load_failures: dict[str, list[str]] = {}
    try:
        checker_identity = _live_checker_identity()
        if checker_identity["verified_clean_checker"] is not True:
            failures.append("checker_source_identity")
        if (
            checker_identity["verified_clean_numerical_source"]
            is not True
        ):
            failures.append("live_numerical_source_identity")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        checker_identity = {
            "verified_clean_checker": False,
            "probe_failure": type(exc).__name__,
        }
        failures.append("checker_source_identity")
    try:
        prior = _prior_authority_manifest()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        prior = {}
        failures.append(f"prior_authority_probe:{type(exc).__name__}")
    try:
        history = _attempt2_history_immutability_manifest()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        history = {}
        failures.append(f"history_immutability_probe:{type(exc).__name__}")
    for path in records:
        try:
            payload = _strict_load(path)
            record_failures = _validate_record(
                path,
                payload,
                prior_manifest=prior,
                history_manifest=history,
            )
        except (OSError, ValueError, TypeError) as exc:
            payload = None
            record_failures = [f"load:{type(exc).__name__}"]
        payloads.append(payload)
        load_failures[path.name] = record_failures
        failures.extend(f"{path.name}:{item}" for item in record_failures)

    valid_payloads = [payload for payload in payloads if payload is not None]
    source_sha = None
    solver_blobs: dict[str, str] = {}
    cross_checks: dict[str, bool] = {}
    digest_diagnostics: dict[str, bool] = {}
    if len(records) != 3:
        failures.append("record_count")
    if len(valid_payloads) == 3 and not failures:
        mpi_sizes = {int(payload["mpi_size"]) for payload in valid_payloads}
        sources = {str(payload["source_sha"]) for payload in valid_payloads}
        source_sha = next(iter(sources)) if len(sources) == 1 else None
        try:
            solver_blobs = (
                _solver_blob_manifest(source_sha)
                if source_sha is not None
                else {}
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            solver_blobs = {}
        abi = [
            {
                key: payload["environment"]["rank_environments"][0][key]
                for key in (
                    "qualified_activation",
                    "python_executable",
                    "dolfinx",
                    "basix",
                    "petsc4py",
                    "mpi4py",
                    "petsc_scalar_type",
                    "petsc_int_type",
                    "mpi_vendor",
                    "mpi_library_version",
                )
            }
            for payload in valid_payloads
        ]
        fixture_name = "p5_trace_p6_interior_hanging_floquet"
        observable_names = (
            "matrix_action_root",
            "matrix_action_probe",
            "right_reduced_rhs",
            "left_reduced_rhs",
            "zero_rhs_full_recovery",
            "nonzero_rhs_full_recovery",
        )
        cross_checks = {
            "mpi_sizes_are_1_2_8": mpi_sizes == {1, 2, 8},
            "same_solver_source_sha": len(sources) == 1,
            "live_checker_blob_matches_record_source": (
                source_sha is not None
                and checker_identity.get("verified_clean_checker") is True
                and checker_identity.get("git_head") == source_sha
                and checker_identity.get("live_sha256")
                == solver_blobs.get(CHECKER_RELATIVE)
            ),
            "live_numerical_source_matches_record_source": (
                source_sha is not None
                and checker_identity.get(
                    "verified_clean_numerical_source"
                )
                is True
                and checker_identity.get("git_head") == source_sha
                and checker_identity.get("numerical_source", {}).get(
                    "live_sha256"
                )
                == solver_blobs
            ),
            "same_solver_blob_manifest": all(
                payload["numerical_files"]
                == valid_payloads[0]["numerical_files"]
                == solver_blobs
                for payload in valid_payloads
            ),
            "same_fixture_identity": all(
                payload[fixture_name]["stable_identity"]
                == valid_payloads[0][fixture_name]["stable_identity"]
                for payload in valid_payloads[1:]
            ),
            "same_abi": all(row == abi[0] for row in abi[1:]),
            "owner_routing_subgate_all_mpi": all(
                payload["pde_launch_ownership_gate"] is True
                and payload[fixture_name]["cell_trace_binding_audit"][
                    "pde_launch_ownership_gate"
                ]
                is True
                and payload[fixture_name]["assembly_audit"][
                    "trace_constraint_owner_routing_qualified"
                ]
                is True
                for payload in valid_payloads
            ),
            "mpi2_mpi8_cross_rank_hanging_owner_path": all(
                payload[fixture_name]["cell_trace_binding_audit"][
                    "cross_rank_hanging_patch_count"
                ]
                > 0
                and payload[fixture_name]["cell_trace_binding_audit"][
                    "cross_rank_hanging_relation_count"
                ]
                > 0
                and payload[fixture_name]["cell_trace_binding_audit"][
                    "cross_rank_hanging_participant_entity_count"
                ]
                > 0
                and payload[fixture_name]["cell_trace_binding_audit"][
                    "cross_rank_hanging_remote_participant_entity_count"
                ]
                > 0
                and sum(
                    payload[fixture_name][
                        "cell_trace_binding_audit"
                    ][
                        "cross_rank_hanging_remote_lookup_counts_by_rank"
                    ]
                )
                > 0
                for payload in valid_payloads
                if int(payload["mpi_size"]) > 1
            ),
            "owner_routed_cache_not_full_catalog": all(
                payload[fixture_name]["cell_trace_binding_audit"][
                    "full_dense_entity_catalog_replicated"
                ]
                is False
                and payload[fixture_name]["cell_trace_binding_audit"][
                    "owner_routed_trace_cache_audit"
                ]["request_reply_count_closes"]
                is True
                for payload in valid_payloads
            ),
        }
        for observable_name in observable_names:
            reference = valid_payloads[0][fixture_name]["observables"][
                observable_name
            ]
            cross_checks[f"{observable_name}_mpi_identity"] = all(
                _signature_matches(
                    reference,
                    payload[fixture_name]["observables"][observable_name],
                )
                for payload in valid_payloads[1:]
            )
            digest_diagnostics[f"{observable_name}_digest_equal"] = all(
                payload[fixture_name]["observables"][observable_name][
                    "normalized_quantized_1e10_sha256"
                ]
                == reference["normalized_quantized_1e10_sha256"]
                for payload in valid_payloads[1:]
            )
        failures.extend(
            f"cross:{name}"
            for name, passed in cross_checks.items()
            if not passed
        )
    elif not failures:
        failures.append("valid_record_count")

    return {
        "schema_version": "case097.local-h-attempt2-independent-check.v3",
        "status": (
            "local_h_attempt2_owner_routed_component_pass_pde_launch_ready"
            if not failures
            else "local_h_attempt2_evidence_fail"
        ),
        "pass": not failures,
        "source_sha": source_sha,
        "input_records": [
            {"path": f"records/{path.name}", "sha256": _sha256(path)}
            for path in records
            if path.exists()
        ],
        "record_failures": load_failures,
        "checker_identity": checker_identity,
        "attempt2_history_immutability": history,
        "cross_checks": cross_checks,
        "non_gating_digest_diagnostics": digest_diagnostics,
        "signature_identity_semantics": {
            "norm_rtol": 3.0e-10,
            "norm_atol": 3.0e-11,
            "moment_rtol": 3.0e-10,
            "normalized_moment_atol": 3.0e-10,
            "normalized_sample_rtol": 3.0e-10,
            "normalized_sample_atol": 3.0e-10,
            "raw_moments_scaled_by_each_vector_linf": True,
            "quantized_digest_is_gating": False,
        },
        "solver_commit_numerical_files": solver_blobs,
        "failures": failures,
        "component_only": True,
        "pde_launch_ownership_gate": not failures,
        "pde_launch_gate": not failures,
        "pde_launch_scope": (
            "minimal local-h PDE may start; no PDE accuracy or "
            "distributed-scalability credit is granted"
        ),
        "pde_accuracy_credit": False,
        "distributed_scalability_qualified": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--records",
        type=Path,
        nargs=3,
        required=True,
        metavar=("MPI1", "MPI2", "MPI8"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _validate_cli_paths(
    records: tuple[Path, ...],
    output: Path,
) -> Path:
    expected_records = tuple(
        (RECORD_DIR / EXPECTED_NAMES[mpi_size]).resolve()
        for mpi_size in (1, 2, 8)
    )
    observed_records = tuple(path.resolve() for path in records)
    if observed_records != expected_records:
        raise ValueError(
            "independent checker inputs must be the ordered formal "
            "MPI1/MPI2/MPI8 v3 records"
        )
    expected_output = (RECORD_DIR / FORMAL_OUTPUT_NAME).resolve()
    if output.resolve() != expected_output:
        raise ValueError(
            "independent checker output must be the formal v3 identity record"
        )
    if output.exists():
        raise FileExistsError(
            "formal v3 identity evidence already exists and is immutable"
        )
    return output


def main() -> int:
    args = _parse_args()
    records = tuple(args.records)
    output = _validate_cli_paths(records, args.output)
    result = check_records(records)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": _sha256(output),
                "status": result["status"],
                "pass": result["pass"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
