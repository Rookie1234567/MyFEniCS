"""Independent raw checker for the Task040 V3-2 full-span screen."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.check_task040_v3_coupled import recompute_v3_1_augmented_packet
from src.solvers.hybrid_interface_packet import load_small_matrix
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_SOURCE_LABELS,
    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
    TASK040_V1_2_INPUT_SHA256,
    TASK040_V1_2_PHYSICAL_MODEL_SHA256,
    TASK040_V1_2_PROBE_MANIFEST_SHA256,
    TASK040_V1_2_SELECTED_MANIFEST_SHA256,
    TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
    TASK040_V3_2_COUPLED_INTERFACE_FLAG,
    TASK040_V3_2_COUPLED_INTERFACE_METHOD,
    TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID,
    TASK040_V3_2_PRODUCER_SOURCE_SHA,
    TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
)

RESOURCE_LIMIT_BYTES = 45 * 2**30
EXPECTED_SPANS = (296, 776, 480)
EXPECTED_GROUP_ORDER = ("group0", "group1", "group2")
ALL_SOURCE_LABELS = tuple(TASK040_LEVEL_A_SOURCE_LABELS)
NONZERO_LABELS = ALL_SOURCE_LABELS[1:]
STRICT_LABELS = NONZERO_LABELS[:3]
FROZEN_LOWER_BETA_SHA256 = (
    "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
)
FORBIDDEN_ROUTES = {
    "exact_interface_oracle",
    "exact_output_vector_load",
    "full_side_factor",
    "global_hybrid_outer_ksp",
    "qep",
    "pde_solve",
    "recovery",
    "top",
    "full_hybrid",
    "response_packet",
}
PACKET_CHECK_EXCLUSIONS = {"watchdog_hash", "run_summary_hash"}
EXPECTED_PACKET_CHECKS = {
    "manifest_hash",
    "producer_source",
    "packet_authority",
    "group_order",
    "span_sizes",
    "group_gram_diagnostics",
    "joint_scalar_diagnostics",
    "middle_matrix",
    "joint_exact",
    "joint_exact_blocks",
    "ordering_identity",
    "report_decomposition",
    "local_middle_schur_evidence",
}
EXPECTED_BLOCK_NORMS = {
    "LL": 1052857.3530587784,
    "LU": 36531.317719106126,
    "UL": 9728.7850526928,
    "UU": 6371.749206867203,
}
EXPECTED_BLOCK_HASHES = {
    "LL": "4be30638ca6ca7e6d6980ef45fa53250755d76961b336b60360f4b06a187dbe0",
    "LU": "1033fcc0d2d5ff2b0a3a018870f839b6e131d39a01de4d205fd3d496fc97db9e",
    "UL": "969e15b2d61f185bb276bab40904235343f118ef0a4d1aef2a6b05c61c048972",
    "UU": "3935fc7fbd064d333dfdc53fb738076a0273b9c2529274d648e11777369c6d09",
}
EXPECTED_JOINT_CONDITION = 72530856.63880321

__all__ = ["check_v3_full_span", "recompute_v3_full_span", "main"]


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and np.isfinite(float(value))
    )


def _sha256_text(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _matrix_content_sha256(matrix: np.ndarray) -> str:
    values = np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128))
    return hashlib.sha256(values.tobytes()).hexdigest()


def _ordering_pass(audit: Mapping[str, Any]) -> bool:
    identity = audit.get("ordering_identity")
    if not isinstance(identity, Mapping):
        return False
    return bool(
        identity.get("producer_source_sha") == TASK040_V3_2_PRODUCER_SOURCE_SHA
        and identity.get("lower_mode_count") == EXPECTED_SPANS[0]
        and identity.get("upper_mode_count") == EXPECTED_SPANS[2]
        and identity.get("lower_mode_key_sha256")
        == "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
        and identity.get("upper_mode_key_sha256")
        == "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
        and identity.get("upper_beta_sha256")
        == "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
        and identity.get("upper_branch_authority") == "positive/forward"
        and identity.get("upper_qep_calls") == 0
        and identity.get("group1_span_size") == EXPECTED_SPANS[1]
        and identity.get("group1_planes") == ["lower", "upper"]
        and identity.get("contract") == "build_group_basis_columns: lower then upper"
    )


def _packet_checks(
    packet_audit: Mapping[str, Any], manifest_sha256: str
) -> dict[str, Any]:
    """Recheck packet/algebra evidence; worker packet status is never used."""

    supplied_checks = packet_audit.get("checks", {})
    checks: dict[str, bool] = {
        "manifest_hash": manifest_sha256
        == TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256
        and packet_audit.get("manifest_sha256") == manifest_sha256,
        "producer_source": packet_audit.get("producer_source_sha")
        == TASK040_V3_2_PRODUCER_SOURCE_SHA,
        "group_order": packet_audit.get("group_order") == list(EXPECTED_GROUP_ORDER),
        "span_sizes": packet_audit.get("span_sizes") == list(EXPECTED_SPANS),
        "ordering_identity": _ordering_pass(packet_audit),
        "v3_1_checks": (
            isinstance(supplied_checks, Mapping)
            and EXPECTED_PACKET_CHECKS.issubset(supplied_checks)
            and all(
                supplied_checks.get(name) is True for name in EXPECTED_PACKET_CHECKS
            )
            and all(
                value is True
                for name, value in supplied_checks.items()
                if name not in PACKET_CHECK_EXCLUSIONS
            )
        ),
    }
    derived_blocks: dict[str, dict[str, Any]] | None = None
    try:
        joint = dict(packet_audit["joint_diagnostics"])
        derived_blocks = {
            name: dict(value)
            for name, value in packet_audit["joint_exact_blocks"].items()
        }
        joint_hash = joint.get("content_sha256", joint.get("sha256"))
        joint_pass = bool(
            joint.get("shape") == [776, 776]
            and joint.get("dtype") == "complex128"
            and joint.get("rank") == 776
            and _finite(joint.get("condition"))
            and float(joint["condition"]) <= 1.0e12
            and joint_hash == TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256
        )
        block_pass = True
        for name, expected_shape in {
            "LL": [296, 296],
            "LU": [296, 480],
            "UL": [480, 296],
            "UU": [480, 480],
        }.items():
            block = derived_blocks[name]
            block_norm = block.get("norm", block.get("frobenius_norm"))
            block_pass = block_pass and bool(
                block.get("shape") == expected_shape
                and block.get("dtype") == "complex128"
                and block.get("rank")
                == {"LL": 296, "LU": 296, "UL": 296, "UU": 480}[name]
                and _finite(block_norm)
                and np.isclose(
                    float(block_norm),
                    EXPECTED_BLOCK_NORMS[name],
                    rtol=1.0e-12,
                    atol=1.0e-9,
                )
                and block.get("sha256") == EXPECTED_BLOCK_HASHES[name]
            )
        middle = packet_audit.get("additional_middle_metadata", {})
        middle_diagnostic = packet_audit.get("additional_middle_diagnostics", {})
        middle_pass = bool(
            isinstance(middle, Mapping)
            and isinstance(middle_diagnostic, Mapping)
            and middle.get("schema") == "task040.v3.middle_group_schur_projection.v1"
            and middle.get("semantic") == "Y1^H [oracle.apply_group(1)] Z1"
            and middle.get("shape") == [776, 776]
            and middle.get("dtype") == "complex128"
            and middle.get("finite") is True
            and middle.get("apply_count") == 776
            and middle.get("rank") == middle_diagnostic.get("rank")
            and middle_diagnostic.get("shape") == [776, 776]
            and middle_diagnostic.get("dtype") == "complex128"
            and isinstance(middle_diagnostic.get("sha256"), str)
            and len(middle_diagnostic["sha256"]) == 64
            and _finite(middle_diagnostic.get("condition"))
        )
        decomposition = packet_audit.get("failure_decomposition", {})
        report_pass = all(
            isinstance(decomposition.get(name), Mapping)
            and decomposition[name].get("count") == count
            for name, count in {
                "physical": 15,
                "modal_combination": 4,
                "complement": 4,
                "middle_lower_to_upper": 4,
                "middle_upper_to_lower": 4,
            }.items()
        )
        checks.update(
            {
                "joint_matrix": joint_pass,
                "joint_blocks": block_pass,
                "middle_matrix": middle_pass,
                "report_decomposition": report_pass,
            }
        )
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
        checks.update(
            {
                "joint_matrix": False,
                "joint_blocks": False,
                "middle_matrix": False,
                "report_decomposition": False,
            }
        )
        joint = {}
        derived_blocks = {}
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "joint_diagnostics": joint,
        "joint_exact_blocks": derived_blocks,
    }


def _raw(run_summary: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = run_summary.get("coupled_interface_raw")
    return raw if isinstance(raw, Mapping) else {}


def _source_binding(
    run: Mapping[str, Any], watchdog: Mapping[str, Any], expected_source_sha: str
) -> bool:
    return bool(
        isinstance(expected_source_sha, str)
        and len(expected_source_sha) == 40
        and expected_source_sha == expected_source_sha.lower()
        and all(c in "0123456789abcdef" for c in expected_source_sha)
        and run.get("source_sha") == expected_source_sha
        and watchdog.get("source_sha") == expected_source_sha
    )


def _identity_checks(
    run: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    raw: Mapping[str, Any],
    packet: Mapping[str, Any],
    expected_source_sha: str,
    manifest_sha256: str,
) -> dict[str, bool]:
    command = watchdog.get("command", [])
    forbidden = raw.get("forbidden_routes", [])
    return {
        "schema_method_profile": (
            run.get("schema") == "task040.v3_2.coupled_interface.v1"
            and run.get("method") == TASK040_V3_2_COUPLED_INTERFACE_METHOD
            and run.get("profile") == TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID
        ),
        "source_sha": _source_binding(run, watchdog, expected_source_sha),
        "input_physical": (
            run.get("input_sha256") == TASK040_V1_2_INPUT_SHA256
            and run.get("physical_model_sha256") == TASK040_V1_2_PHYSICAL_MODEL_SHA256
        ),
        "selected_spool": (
            run.get("selected_manifest_sha256") == TASK040_V1_2_SELECTED_MANIFEST_SHA256
            and run.get("exact_spool_catalog_sha256")
            == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
        ),
        "probe_manifest": packet.get("probe_manifest_sha256")
        in (None, TASK040_V1_2_PROBE_MANIFEST_SHA256),
        "producer_manifest": (
            run.get("packet_manifest_sha256")
            == TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256
            and raw.get("packet_manifest_sha256")
            == TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256
            and manifest_sha256 == TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256
            and run.get("packet_producer_source_sha")
            == TASK040_V3_2_PRODUCER_SOURCE_SHA
            and raw.get("producer_source_sha") == TASK040_V3_2_PRODUCER_SOURCE_SHA
        ),
        "packet_dependent": raw.get("packet_dependent") is True,
        "source_loading": (
            run.get("rhs_vectors_loaded") == 6
            and run.get("exact_output_vectors_loaded") == 0
            and _raw(run).get("one_apply", {}).get("labels") == list(NONZERO_LABELS)
        ),
        "qep_pde": run.get("qep_calls") == 0 and run.get("pde_solve") == "not_run",
        "forbidden_routes": FORBIDDEN_ROUTES.issubset(set(forbidden)),
        "v3_worker_flag": (
            TASK040_V3_2_COUPLED_INTERFACE_FLAG in command
            and "--v2-interface-packet-consumer" not in command
            and "--v2-interface-packet-producer" not in command
        ),
        "no_replication": (
            raw.get("basis_global_replicated") is False
            and raw.get("fe_numeric_allgather") is False
        ),
    }


def _representation_checks(
    raw: Mapping[str, Any], packet_audit: Mapping[str, Any]
) -> dict[str, bool]:
    remap = raw.get("group1_remap", {})
    audit = remap.get("audit", {}) if isinstance(remap, Mapping) else {}
    z = raw.get("z_reconstruction", {})
    gram_block_errors = z.get("gram_block_relative_errors")
    gram_blocks_pass = True
    if gram_block_errors is not None:
        gram_blocks_pass = bool(
            isinstance(gram_block_errors, Mapping)
            and all(
                name in gram_block_errors
                and _finite(gram_block_errors[name])
                and float(gram_block_errors[name]) <= 1.0e-10
                for name in ("LL", "LU", "UL", "UU")
            )
        )
    transfer = z.get("right_transfer", {})
    cross_gram = transfer.get("cross_gram", {})
    cross_blocks = cross_gram.get("blocks", {})
    transfer_blocks = transfer.get("right_transfer", {}).get("blocks", {})
    expected_shapes = {
        "LL": [296, 296],
        "LU": [296, 480],
        "UL": [480, 296],
        "UU": [480, 480],
    }
    expected_cross_ranks = {"LL": 296, "LU": 0, "UL": 0, "UU": 480}
    cross_blocks_pass = bool(
        isinstance(cross_blocks, Mapping)
        and all(
            isinstance(cross_blocks.get(name), Mapping)
            and cross_blocks[name].get("shape") == expected_shapes[name]
            and cross_blocks[name].get("rank") == expected_cross_ranks[name]
            and _finite(cross_blocks[name].get("norm"))
            and _sha256_text(cross_blocks[name].get("sha256"))
            and _finite(cross_blocks[name].get("relative_to_packet"))
            and (
                _finite(cross_blocks[name].get("condition"))
                if name in {"LL", "UU"}
                else cross_blocks[name].get("condition") is None
            )
            for name in expected_shapes
        )
    )
    transfer_blocks_pass = bool(
        isinstance(transfer_blocks, Mapping)
        and all(
            isinstance(transfer_blocks.get(name), Mapping)
            and _finite(transfer_blocks[name].get("condition"))
            and _finite(transfer_blocks[name].get("transfer_condition"))
            and _finite(transfer_blocks[name].get("residual_relative"))
            and float(transfer_blocks[name]["residual_relative"]) <= 1.0e-10
            and transfer_blocks[name].get("rank") == expected_cross_ranks[name]
            for name in ("LL", "UU")
        )
    )
    cross_offdiagonal_pass = bool(
        isinstance(cross_gram, Mapping)
        and all(
            _finite(cross_gram.get("offdiagonal_norm", {}).get(name))
            and float(cross_gram["offdiagonal_norm"][name]) <= 1.0e-12
            for name in ("LU", "UL")
        )
        and _sha256_text(cross_gram.get("sha256"))
    )
    transfer_offdiagonal_pass = bool(
        isinstance(transfer.get("right_transfer"), Mapping)
        and all(
            _finite(transfer["right_transfer"].get("offdiagonal_norm", {}).get(name))
            and float(transfer["right_transfer"]["offdiagonal_norm"][name]) <= 1.0e-12
            for name in ("LU", "UL")
        )
    )
    post_transfer_pass = bool(
        transfer.get("schema") == "task040.v3.packet_dual_right_transfer.v1"
        and transfer.get("y_authority") == "packet_dual_from_VG"
        and transfer.get("z_authority")
        == "fresh_lower_fourier_upper_selected_right_transfer"
        and _sha256_text(transfer.get("post_gram_sha256"))
        and transfer.get("post_gram_sha256") == z.get("recomputed_gram_sha256")
        and _finite(transfer.get("post_gram_relative_error"))
        and float(transfer["post_gram_relative_error"]) <= 1.0e-10
        and isinstance(transfer.get("post_block_relative_errors"), Mapping)
        and all(
            _finite(transfer["post_block_relative_errors"].get(name))
            and float(transfer["post_block_relative_errors"][name]) <= 1.0e-10
            for name in expected_shapes
        )
        and cross_blocks_pass
        and transfer_blocks_pass
        and cross_offdiagonal_pass
        and transfer_offdiagonal_pass
    )
    return {
        "remap": (
            _finite(remap.get("collective_max_relative_error"))
            and float(remap["collective_max_relative_error"]) <= 1.0e-12
            and _finite(audit.get("max_relative_error"))
            and float(audit["max_relative_error"]) <= 1.0e-12
        ),
        "z_identity": (
            z.get("qep_calls") == 0
            and z.get("lower_mode_key_sha256")
            == "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
            and z.get("lower_beta_sha256") == FROZEN_LOWER_BETA_SHA256
            and z.get("upper_mode_key_sha256")
            == "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
            and z.get("upper_beta_sha256")
            == "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
            and _finite(z.get("gram_relative_error"))
            and float(z["gram_relative_error"]) <= 1.0e-10
            and z.get("y_authority") == "packet_dual_from_VG"
            and z.get("z_authority")
            == "fresh_lower_fourier_upper_selected_right_transfer"
            and z.get("packet_gram_sha256")
            == packet_audit.get("group1_gram_content_sha256")
            and _sha256_text(z.get("recomputed_gram_sha256"))
            and gram_blocks_pass
            and post_transfer_pass
        ),
        "bare_f_unchanged": (
            raw.get("bare_f_identity", {}).get("before")
            == raw.get("bare_f_identity", {}).get("after")
            and raw.get("bare_f_identity", {}).get("unchanged") is True
        ),
    }


def _joint_binding_checks(
    run: Mapping[str, Any], raw: Mapping[str, Any]
) -> dict[str, bool]:
    joint = raw.get("joint", {})
    blocks = joint.get("blocks", {}) if isinstance(joint, Mapping) else {}
    expected_shapes = {
        "LL": [296, 296],
        "LU": [296, 480],
        "UL": [480, 296],
        "UU": [480, 480],
    }
    expected_ranks = {"LL": 296, "LU": 296, "UL": 296, "UU": 480}
    block_pass = all(
        isinstance(blocks.get(name), Mapping)
        and blocks[name].get("shape") == expected_shapes[name]
        and blocks[name].get("rank") == expected_ranks[name]
        and _finite(blocks[name].get("norm"))
        and np.isclose(
            float(blocks[name]["norm"]),
            EXPECTED_BLOCK_NORMS[name],
            rtol=1.0e-12,
            atol=1.0e-9,
        )
        and blocks[name].get("sha256") == EXPECTED_BLOCK_HASHES[name]
        for name in expected_shapes
    )
    return {
        "run_joint_hash": run.get("true_joint_content_sha256")
        == TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
        "raw_joint": (
            isinstance(joint, Mapping)
            and joint.get("shape") == [776, 776]
            and joint.get("rank") == 776
            and _finite(joint.get("condition"))
            and np.isclose(
                float(joint["condition"]),
                EXPECTED_JOINT_CONDITION,
                rtol=1.0e-12,
                atol=1.0e-9,
            )
            and joint.get("content_sha256") == TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256
        ),
        "raw_joint_blocks": block_pass,
    }


def _one_apply_checks(raw: Mapping[str, Any]) -> dict[str, bool]:
    audit = raw.get("one_apply", {})
    reports = audit.get("reports", [])
    physical = audit.get("physical_zero_report", {})
    required = (
        "source_norm",
        "output_norm",
        "true_residual_norm",
        "true_residual_relative",
        "repeat_relative",
        "first_coarse_residual_relative",
        "second_coarse_residual_relative",
        "coarse_residual_repeat_relative",
    )
    report_flags = (
        "first_coarse_residual_finite",
        "second_coarse_residual_finite",
        "coarse_residual_finite",
    )
    audit_labels_pass = audit.get("labels") == list(NONZERO_LABELS)
    report_labels_pass = bool(
        [row.get("label") for row in reports] == list(NONZERO_LABELS)
        and len(reports) == 5
    )
    report_finite = bool(
        report_labels_pass
        and all(
            row.get("finite") is True
            and all(_finite(row.get(name)) for name in required)
            and all(row.get(name) is True for name in report_flags)
            for row in reports
        )
    )
    factor = raw.get("factor_inventory", {})
    physical_zero = (
        physical.get("finite") is True
        and _finite(physical.get("source_norm"))
        and _finite(physical.get("output_norm"))
        and float(physical["source_norm"]) <= 1.0e-13
        and float(physical["output_norm"]) <= 1.0e-13
        and physical.get("physical_zero") is True
    )
    zero_map = bool(
        _finite(audit.get("zero_output_norm"))
        and float(audit["zero_output_norm"]) <= 1.0e-13
    )
    repeat = bool(
        report_finite
        and all(float(row["repeat_relative"]) <= 1.0e-10 for row in reports)
    )
    linearity = bool(
        _finite(audit.get("linearity_relative"))
        and float(audit["linearity_relative"]) <= 1.0e-10
    )
    factor_pass = bool(
        factor.get("cross_section_group_factor_count") == 3
        and factor.get("reduced_dense_factor_count") == 1
        and factor.get("exact_interface_schur_oracle_object_count") == 0
        and factor.get("full_side_exact_factor_count") == 0
        and factor.get("global_direct_factor_count") == 0
        and factor.get("nested_ksp_count") == 0
    )
    coarse = bool(
        report_finite
        and all(
            _finite(row.get("first_coarse_residual_relative"))
            and _finite(row.get("second_coarse_residual_relative"))
            and _finite(row.get("coarse_residual_repeat_relative"))
            for row in reports
        )
    )
    action_identity = bool(
        zero_map
        and physical_zero
        and report_finite
        and repeat
        and linearity
        and factor_pass
        and coarse
    )
    raw_fields = {
        "zero_map_pass": zero_map,
        "physical_zero_pass": physical_zero,
        "source_reports_finite": report_finite,
        "repeat_pass": repeat,
        "linearity_pass": linearity,
        "factor_inventory_pass": factor_pass,
        "coarse_residual_finite": coarse,
        "action_identity_pass": action_identity,
    }
    consistency = all(audit.get(name) is value for name, value in raw_fields.items())
    return {
        "schema": audit.get("schema") == "task040.v3_2.full_side_one_apply.v1",
        "audit_labels": audit_labels_pass,
        "reports_labels": report_labels_pass,
        "physical_label": physical.get("label") == ALL_SOURCE_LABELS[0],
        "physical_zero": physical_zero,
        "zero_map": zero_map,
        "reports_finite": report_finite,
        "repeat": repeat,
        "linearity": linearity,
        "coarse_residual": coarse,
        "factor_inventory": factor_pass,
        "action_identity": action_identity,
        "action_apply_count": audit.get("action_apply_count") == 15,
        "reported_gate_consistency": consistency,
    }


def _lifecycle_checks(raw: Mapping[str, Any]) -> dict[str, bool]:
    life = raw.get("lifecycle", {})
    return {
        "ready_inventory": (
            life.get("factor_count_ready") == 3
            and life.get("reduced_dense_factor_count_ready") == 1
            and life.get("exact_interface_schur_oracle_object_count") == 0
            and life.get("full_side_exact_factor_count") == 0
            and life.get("global_direct_factor_count") == 0
            and life.get("nested_ksp_count") == 0
        ),
        "cleanup": (
            life.get("factor_count_after_cleanup") == 0
            and life.get("reduced_dense_factor_count_after_cleanup") == 0
            and life.get("projected_inverse_count_after_cleanup") == 0
            and life.get("action_destroyed") is True
            and life.get("factor_destroyed") is True
        ),
    }


def _checkpoint_gate(
    phase: Mapping[str, Mapping[str, Any]], labels: Sequence[str], checkpoint: str
) -> bool:
    try:
        values = [phase[label]["checkpoints"][checkpoint] for label in labels]
        residuals = [row["true_residual_relative"] for row in values]
        return bool(
            all(
                row.get("finite") is True and _finite(value)
                for row, value in zip(values, residuals, strict=True)
            )
            and all(float(value) <= 1.0e-2 for value in residuals)
            and all(
                float(phase[label]["checkpoints"][checkpoint]["true_residual_relative"])
                <= 1.0e-3
                for label in STRICT_LABELS
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _trend(
    phase: Mapping[str, Mapping[str, Any]], labels: Sequence[str], start: int, end: int
) -> bool:
    for label in labels:
        history = phase.get(label, {}).get("reported_residual_history", [])
        rows = sorted(
            [
                item
                for item in history
                if isinstance(item, Mapping)
                and start <= int(item.get("iteration", -1)) <= end
            ],
            key=lambda item: int(item["iteration"]),
        )
        if [int(item["iteration"]) for item in rows] != list(range(start, end + 1)):
            return False
        values = [item.get("relative_residual") for item in rows]
        if not all(_finite(value) for value in values):
            return False
        if not all(
            float(values[i]) <= float(values[i - 1]) for i in range(1, len(values))
        ):
            return False
    return True


def _phase_contract(
    phase: Mapping[str, Mapping[str, Any]],
    labels: Sequence[str],
    checkpoint: str,
    max_it: int,
) -> bool:
    expected_true_matvec_count = {16: 4, 32: 2, 64: 2}[max_it]
    expected = {"0", checkpoint}
    if checkpoint in {"4", "8", "16"}:
        expected = {"0", "4", "8", "16"}
    if not phase or set(phase) != set(labels):
        return False
    for label in labels:
        row = phase[label]
        if set(row.get("checkpoints", {})) != expected:
            return False
        if not all(
            item.get("finite") is True and _finite(item.get("true_residual_relative"))
            for item in row["checkpoints"].values()
        ):
            return False
        if (
            row.get("restart") != 32
            or row.get("max_it") != max_it
            or row.get("zero_initial_guess") is not True
            or row.get("zero_initial_guess_count") != 1
            or row.get("shared_ksp") is not True
            or row.get("ksp_breakdown") is not False
            or row.get("true_residual_matvec_count") != expected_true_matvec_count
            or row.get("postsolve_true_residual_finite") is not True
            or not _finite(row.get("postsolve_true_residual_norm"))
            or not _finite(row.get("postsolve_true_residual_relative"))
            or row.get("iterations") != max_it
            or row.get("final_iteration") != max_it
            or not isinstance(row.get("final_reason"), int)
            or row.get("missing_checkpoints") != []
            or row.get("happy_breakdown") is not False
            or row.get("early_stop") is not False
            or not isinstance(row.get("right_pc_apply_count_delta"), int)
            or row.get("right_pc_apply_count_delta") <= 0
        ):
            return False
        history = row.get("reported_residual_history", [])
        if not history or not all(
            isinstance(item, Mapping) and _finite(item.get("relative_residual"))
            for item in history
        ):
            return False
    return True


def _screen_checks(raw: Mapping[str, Any]) -> dict[str, Any]:
    screen = raw.get("fgmres_screen", {})
    phase1 = screen.get("phase1", {})
    phase2 = screen.get("phase2", {})
    phase3 = screen.get("phase3", {})
    structural = bool(
        screen.get("schema") == "task040.v3_2.full_span_right_fgmres.v1"
        and screen.get("labels") == list(NONZERO_LABELS)
        and screen.get("ksp_setup_count") == 1
        and screen.get("ksp_destroy_count") == 1
        and screen.get("ksp_destroyed") is True
        and screen.get("single_right_pc_setup") is True
        and screen.get("zero_initial_guess_all_rhs") is True
    )
    if structural:
        structural = _phase_contract(phase1, NONZERO_LABELS, "16", 16)
    if phase2:
        structural = structural and _phase_contract(phase2, NONZERO_LABELS, "32", 32)
    if phase3:
        structural = structural and _phase_contract(phase3, NONZERO_LABELS, "64", 64)
    phase1_early = next(
        (
            int(checkpoint)
            for checkpoint in ("4", "8", "16")
            if _checkpoint_gate(phase1, NONZERO_LABELS, checkpoint)
        ),
        None,
    )
    phase1_trend = bool(
        phase1
        and all(
            _finite(phase1[label]["checkpoints"]["8"]["true_residual_relative"])
            and _finite(phase1[label]["checkpoints"]["16"]["true_residual_relative"])
            and float(phase1[label]["checkpoints"]["16"]["true_residual_relative"])
            <= 10 ** (-0.25)
            * float(phase1[label]["checkpoints"]["8"]["true_residual_relative"])
            for label in NONZERO_LABELS
        )
    )
    boundaries = screen.get("resource_boundaries", [])

    def boundary_resource(name: str) -> bool:
        matches = [
            item
            for item in boundaries
            if isinstance(item, Mapping) and item.get("boundary") == name
        ]
        return bool(
            len(matches) == 1
            and _finite(matches[0].get("rss_bytes"))
            and float(matches[0]["rss_bytes"]) < RESOURCE_LIMIT_BYTES
            and matches[0].get("swap_bytes") == 0
            and matches[0].get("all_status_readable") is True
        )

    phase1_resource = boundary_resource("after_phase1")
    conditional32 = bool(phase1_early is None and phase1_trend and phase1_resource)
    phase2_pass = bool(phase2 and _checkpoint_gate(phase2, NONZERO_LABELS, "32"))
    phase2_trend = bool(phase2 and _trend(phase2, NONZERO_LABELS, 16, 32))
    phase2_resource = boundary_resource("after_phase2")
    conditional64 = bool(
        conditional32
        and phase2
        and not phase2_pass
        and phase2_trend
        and phase2_resource
        and all(
            _finite(phase2[label]["checkpoints"]["32"]["true_residual_relative"])
            and float(phase2[label]["checkpoints"]["32"]["true_residual_relative"])
            <= 0.1
            and float(phase2[label]["checkpoints"]["32"]["true_residual_relative"])
            < float(phase1[label]["checkpoints"]["16"]["true_residual_relative"])
            for label in NONZERO_LABELS
        )
    )
    phase3_trend = bool(phase3 and _trend(phase3, NONZERO_LABELS, 48, 64))
    phase3_pass = bool(phase3 and _checkpoint_gate(phase3, NONZERO_LABELS, "64"))
    first = phase1_early or (32 if phase2_pass else 64 if phase3_pass else None)
    expected_boundary_names = ["after_phase1"]
    if conditional32:
        expected_boundary_names.append("after_phase2")
    if conditional64:
        expected_boundary_names.append("after_phase3")
    boundary_names = [
        item.get("boundary") for item in boundaries if isinstance(item, Mapping)
    ]
    boundary_structure_pass = boundary_names == expected_boundary_names
    reported_first = raw.get(
        "first_preferred_checkpoint", screen.get("first_preferred_checkpoint")
    )
    structural = bool(
        structural
        and (bool(phase2) is conditional32)
        and (bool(phase3) is conditional64)
        and screen.get("conditional_32_authorized") is conditional32
        and screen.get("conditional_64_authorized") is conditional64
        and reported_first == first
        and boundary_structure_pass
    )
    boundary_resource_pass = bool(
        boundary_structure_pass
        and all(
            _finite(item.get("rss_bytes"))
            and float(item["rss_bytes"]) < RESOURCE_LIMIT_BYTES
            and item.get("swap_bytes") == 0
            and item.get("all_status_readable") is True
            for item in boundaries
        )
    )
    return {
        "contract_pass": structural,
        "boundary_structure_pass": boundary_structure_pass,
        "numerical_pass": first is not None,
        "phase1_early_preferred_checkpoint": phase1_early,
        "conditional_32_authorized": conditional32,
        "phase2_pass": phase2_pass,
        "phase2_trend_pass": phase2_trend,
        "conditional_64_authorized": conditional64,
        "phase3_pass": phase3_pass,
        "phase3_trend_pass": phase3_trend,
        "first_preferred_checkpoint": first,
        "boundary_resource_pass": boundary_resource_pass,
    }


def _timeline_checks(
    run: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    timeline_sha256: str | None,
    run_summary_sha256: str,
    expected_source_sha: str,
    expected_packet_root: str | None,
) -> dict[str, Any]:
    authority_rows = [row for row in rows if row.get("authoritative_sample") is True]
    terminal_rows = [
        row for row in rows if row.get("terminal_teardown_excluded") is True
    ]
    values = []
    swap_values = []
    readable = True
    authority_semantics = bool(rows) and all(
        (
            row.get("authoritative_sample") is True
            and row.get("terminal_teardown_excluded") is False
        )
        or (
            row.get("terminal_teardown_excluded") is True
            and row.get("authoritative_sample") is False
        )
        for row in rows
    )
    cgroup_swap = []
    for row in rows:
        if not _finite(row.get("rss_bytes")) or not _finite(row.get("swap_bytes")):
            readable = False
            continue
        values.append(int(row["rss_bytes"]))
        swap_values.append(int(row["swap_bytes"]))
        authority = row.get("resource_authority", {})
        process_tree = (
            authority.get("process_tree", {}) if isinstance(authority, Mapping) else {}
        )
        if row.get("authoritative_sample") is True and (
            process_tree.get("all_status_readable") is not True
            or not process_tree.get("pids")
        ):
            readable = False
        job = authority.get("job_cgroup", {}) if isinstance(authority, Mapping) else {}
        if (
            isinstance(job, Mapping)
            and job.get("dedicated_job_cgroup") is True
            and _finite(job.get("swap_current_bytes"))
        ):
            cgroup_swap.append(int(job["swap_current_bytes"]))
    peak = max(values, default=-1)
    peak_swap = max(swap_values, default=-1)
    peak_cgroup_swap = max(cgroup_swap, default=0)
    hash_bound = bool(
        timeline_sha256
        and watchdog.get("artifact_hashes", {}).get("process_tree_samples.jsonl")
        == timeline_sha256
    )
    count_bound = bool(
        watchdog.get("sample_count") == len(authority_rows)
        and watchdog.get("authoritative_sample_count", len(authority_rows))
        == len(authority_rows)
        and watchdog.get("terminal_teardown_excluded_count", len(terminal_rows))
        == len(terminal_rows)
        and len(rows) == len(authority_rows) + len(terminal_rows)
        and len(rows) > 0
    )
    run_summary_hash_pass = watchdog.get("run_summary_sha256") == run_summary_sha256
    argv = watchdog.get("command", [])

    def argv_value(flag: str) -> str | None:
        if not isinstance(argv, list) or argv.count(flag) != 1:
            return None
        index = argv.index(flag)
        value = argv[index + 1] if index + 1 < len(argv) else None
        return value if isinstance(value, str) else None

    argv_pass = bool(
        isinstance(argv, list)
        and TASK040_V3_2_COUPLED_INTERFACE_FLAG in argv
        and argv.count(TASK040_V3_2_COUPLED_INTERFACE_FLAG) == 1
        and "mpiexec" in argv
        and "-n" in argv
        and argv[argv.index("-n") + 1 : argv.index("-n") + 2] == ["8"]
        and "-m" in argv
        and argv[argv.index("-m") + 1 : argv.index("-m") + 2]
        == ["benchmarks.task040_level_a"]
        and argv_value("--source-sha") == expected_source_sha
        and (
            expected_packet_root is None
            or argv_value("--interface-packet-root") == str(expected_packet_root)
        )
        and "--v2-interface-packet-consumer" not in argv
        and "--v2-interface-packet-producer" not in argv
    )
    watchdog_identity_pass = bool(
        watchdog.get("method") == TASK040_V3_2_COUPLED_INTERFACE_METHOD
        and watchdog.get("source_sha") == expected_source_sha
        and watchdog.get("hard_stop_bytes") == RESOURCE_LIMIT_BYTES
        and watchdog.get("termination_reason") == "natural_exit"
        and watchdog.get("return_code") == 0
        and watchdog.get("run_summary_present") is True
        and watchdog.get("sample_count", 0) > 0
    )
    summary_peak_match = bool(
        watchdog.get("peak_rss_bytes") == peak
        and watchdog.get("peak_swap_bytes") == peak_swap
        and watchdog.get("peak_dedicated_cgroup_swap_bytes", 0) == peak_cgroup_swap
    )
    telemetry_integrity_pass = bool(
        watchdog_identity_pass
        and run_summary_hash_pass
        and hash_bound
        and count_bound
        and authority_semantics
        and readable
        and summary_peak_match
        and watchdog.get("all_status_readable") is True
        and watchdog.get("swap_authority_readable") is True
        and argv_pass
    )
    resource_pass = bool(
        peak < RESOURCE_LIMIT_BYTES and peak_swap == 0 and peak_cgroup_swap == 0
    )
    return {
        "pass": telemetry_integrity_pass and resource_pass,
        "telemetry_integrity_pass": telemetry_integrity_pass,
        "resource_pass": resource_pass,
        "timeline_hash_bound": hash_bound,
        "count_binding_pass": count_bound,
        "authority_semantics_pass": authority_semantics,
        "argv_pass": argv_pass,
        "run_summary_hash_pass": run_summary_hash_pass,
        "summary_peak_match": summary_peak_match,
        "raw_sample_count": watchdog.get("sample_count"),
        "authoritative_count": len(authority_rows),
        "terminal_teardown_count": len(terminal_rows),
        "peak_rss_bytes": peak,
        "peak_swap_bytes": peak_swap,
        "peak_dedicated_cgroup_swap_bytes": peak_cgroup_swap,
        "all_status_readable": readable,
    }


def recompute_v3_full_span(
    run_summary: Mapping[str, Any],
    watchdog_summary: Mapping[str, Any],
    packet_audit: Mapping[str, Any],
    timeline_rows: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha: str,
    manifest_sha256: str,
    run_summary_sha256: str,
    timeline_sha256: str | None,
    expected_packet_root: str | None = None,
) -> dict[str, Any]:
    """Recompute V3-2 evidence from raw fields and an independent packet audit."""

    raw = _raw(run_summary)
    packet = _packet_checks(packet_audit, manifest_sha256)
    identity = _identity_checks(
        run_summary,
        watchdog_summary,
        raw,
        packet_audit,
        expected_source_sha,
        manifest_sha256,
    )
    representation = _representation_checks(raw, packet_audit)
    joint = _joint_binding_checks(run_summary, raw)
    one_apply = _one_apply_checks(raw)
    lifecycle = _lifecycle_checks(raw)
    screen = _screen_checks(raw)
    timeline = _timeline_checks(
        run_summary,
        watchdog_summary,
        timeline_rows,
        timeline_sha256=timeline_sha256,
        run_summary_sha256=run_summary_sha256,
        expected_source_sha=expected_source_sha,
        expected_packet_root=expected_packet_root,
    )
    evidence_valid = bool(
        packet["pass"]
        and all(identity.values())
        and all(representation.values())
        and all(joint.values())
        and all(one_apply.values())
        and all(lifecycle.values())
        and screen["contract_pass"]
        and timeline["telemetry_integrity_pass"]
    )
    if not packet["pass"]:
        classification = "COUPLED_PACKET_INFORMATION_INCOMPLETE"
    elif not evidence_valid:
        classification = "IMPLEMENTATION_FAILURE"
    elif not screen["boundary_resource_pass"] or not timeline["resource_pass"]:
        classification = "COUPLED_INTERFACE_FULL_SPAN_RESOURCE_FAIL"
    elif screen["numerical_pass"]:
        classification = "COUPLED_INTERFACE_FULL_SPAN_PASS"
    else:
        classification = "COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL"
    return {
        "schema": "task040.v3_2.full_span.recomputed.v1",
        "checks": {
            "packet": packet["pass"],
            "identity": all(identity.values()),
            "representation": all(representation.values()),
            "joint": all(joint.values()),
            "one_apply": all(one_apply.values()),
            "lifecycle": all(lifecycle.values()),
            "screen_contract": screen["contract_pass"],
            "telemetry_integrity": timeline["telemetry_integrity_pass"],
            "resource": screen["boundary_resource_pass"] and timeline["resource_pass"],
        },
        "packet": packet,
        "identity": identity,
        "representation": representation,
        "joint": joint,
        "one_apply": one_apply,
        "lifecycle": lifecycle,
        "screen": screen,
        "resource": timeline,
        "evidence_valid": evidence_valid,
        "numerical_pass": screen["numerical_pass"],
        "classification": classification,
        "gate_pass": classification == "COUPLED_INTERFACE_FULL_SPAN_PASS",
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def check_v3_full_span(
    run_root: str | Path,
    packet_root: str | Path,
    *,
    expected_source_sha: str,
    watchdog_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    run_directory = Path(run_root)
    run_path = run_directory / "worker" / "run_summary.json"
    watchdog_path = Path(
        watchdog_summary_path or run_directory / "watchdog_summary.json"
    )
    timeline_path = run_directory / "process_tree_samples.jsonl"
    manifest_path = Path(packet_root) / "manifest.json"
    run = _load_json(run_path)
    watchdog = _load_json(watchdog_path)
    manifest_sha256 = _sha256(manifest_path)
    timeline_sha256 = _sha256(timeline_path)
    rows = [
        json.loads(line)
        for line in timeline_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    try:
        packet_audit = recompute_v3_1_augmented_packet(packet_root)
        packet_audit = dict(packet_audit)
        packet_audit["group1_gram_content_sha256"] = _matrix_content_sha256(
            load_small_matrix(Path(packet_root), "gram_group1")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        packet_audit = {"error": str(exc), "manifest_sha256": manifest_sha256}
    return recompute_v3_full_span(
        run,
        watchdog,
        packet_audit,
        rows,
        expected_source_sha=expected_source_sha,
        manifest_sha256=manifest_sha256,
        run_summary_sha256=_sha256(run_path),
        timeline_sha256=timeline_sha256,
        expected_packet_root=str(Path(packet_root).resolve()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--watchdog-summary")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = check_v3_full_span(
            args.run_root,
            args.packet_root,
            expected_source_sha=args.expected_source_sha,
            watchdog_summary_path=args.watchdog_summary,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "task040.v3_2.full_span.recomputed.v1",
            "error": str(exc),
            "classification": "COUPLED_PACKET_INFORMATION_INCOMPLETE",
            "gate_pass": False,
        }
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result.get("gate_pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
