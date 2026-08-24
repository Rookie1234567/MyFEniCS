"""Independent V3-1 checker for the immutable Task040 interface packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks import check_task040_v1_run_b as v1_checker
from benchmarks.check_task040_v2_packet import check_v2_packet, load_small_matrix
from src.solvers.hybrid_interface_coupled import (
    CONDITION_LIMIT,
    EXPECTED_SPAN_SIZES,
    assemble_coupled_interface_matrices,
    matrix_diagnostics,
)

FROZEN_PACKET_MANIFEST_SHA256 = (
    "19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0"
)
FROZEN_PRODUCER_SOURCE_SHA = "942c43881e4162085348c48b09c79fbbdac18cd9"
FROZEN_LOWER_MODE_KEY_SHA256 = (
    "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
)
FROZEN_UPPER_MODE_KEY_SHA256 = (
    "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
)
FROZEN_UPPER_BETA_SHA256 = (
    "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
)
AUGMENTED_PRODUCER_SOURCE_SHA = "fa1720d8f137de81023cd45d6a43262d386e6521"
AUGMENTED_PACKET_MANIFEST_SHA256 = (
    "f480189663ef293ec4f809818e322186d75a205f725a3aa35dc12c2d24aad209"
)
AUGMENTED_RUN_SUMMARY_SHA256 = (
    "b44700081d48c96f4380e3111cd5f25ff57dfc64f0fab24afbd7a8a710f2bc7a"
)
AUGMENTED_WATCHDOG_SUMMARY_SHA256 = (
    "cb61e59830443c2169bd388af7710de2af95d5e2ec59d128c207c1bbd05dbf03"
)
AUGMENTED_MATRIX_SCHEMA = "task040.v3.middle_group_schur_projection.v1"

__all__ = [
    "recompute_v3_1_augmented_packet",
    "recompute_v3_1_packet",
    "main",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and np.isfinite(float(value))


def _load_projected_matrices(
    root: Path, manifest: dict[str, Any]
) -> tuple[list[dict[str, np.ndarray]], dict[str, Any]]:
    names = manifest.get("diagnostics", {}).get("projected_matrix_names")
    records = manifest.get("small_matrices")
    if not isinstance(names, dict) or not isinstance(records, dict):
        raise ValueError("packet projected matrix descriptors are missing")
    groups: list[dict[str, np.ndarray]] = []
    descriptors: list[dict[str, Any]] = []
    for group, span in zip(manifest["group_order"], EXPECTED_SPAN_SIZES, strict=True):
        group_names = names.get(group)
        if not isinstance(group_names, dict):
            raise ValueError(f"{group} projected matrix descriptors are missing")
        if set(group_names) != {"gram", "scalar", "exact"}:
            raise ValueError(f"{group} projected matrix descriptors are incomplete")
        matrices: dict[str, np.ndarray] = {}
        for name, filename in group_names.items():
            if not isinstance(filename, str) or filename not in records:
                raise ValueError(f"{group}.{name} descriptor is invalid")
            matrix = load_small_matrix(root, filename)
            record = records[filename]
            if not isinstance(record, dict):
                raise ValueError(f"{group}.{name} matrix record is invalid")
            path = root / str(record["path"])
            if _sha256(path) != record["sha256"]:
                raise ValueError(f"{group}.{name} matrix hash mismatch")
            expected_shape = (int(span), int(span))
            if (
                matrix.dtype != np.dtype(np.complex128)
                or matrix.shape != expected_shape
            ):
                raise ValueError(f"{group}.{name} shape or dtype is invalid")
            if not np.isfinite(matrix).all():
                raise ValueError(f"{group}.{name} is nonfinite")
            matrices[
                {
                    "gram": "gram",
                    "scalar": "projected_scalar",
                    "exact": "projected_exact",
                }[name]
            ] = matrix
            descriptors.append(
                {
                    "group": group,
                    "name": name,
                    "filename": filename,
                    "path": str(record["path"]),
                    "sha256": record["sha256"],
                    "shape": [int(item) for item in matrix.shape],
                    "dtype": "complex128",
                }
            )
        groups.append(matrices)
    return groups, {"matrices": descriptors}


def _load_augmented_middle_matrix(
    root: Path, manifest: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    name = "projected_middle_group_schur"
    records = manifest.get("small_matrices")
    diagnostics = manifest.get("diagnostics", {})
    additional = diagnostics.get("additional_projected_matrices", {})
    record = records.get(name) if isinstance(records, dict) else None
    metadata = additional.get(name) if isinstance(additional, dict) else None
    if not isinstance(record, dict) or not isinstance(metadata, dict):
        raise ValueError("augmented middle Schur descriptor is missing")
    if metadata.get("schema") != AUGMENTED_MATRIX_SCHEMA:
        raise ValueError("augmented middle Schur schema is invalid")
    if metadata.get("semantic") != "Y1^H [oracle.apply_group(1)] Z1":
        raise ValueError("augmented middle Schur semantic is invalid")
    if metadata.get("matrix_name") != name or metadata.get("name") != name:
        raise ValueError("augmented middle Schur name is invalid")
    matrix = load_small_matrix(root, name)
    expected_shape = (EXPECTED_SPAN_SIZES[1], EXPECTED_SPAN_SIZES[1])
    if matrix.shape != expected_shape or not np.isfinite(matrix).all():
        raise ValueError("augmented middle Schur shape or finite check failed")
    recomputed = matrix_diagnostics(matrix, expected_shape=expected_shape)
    if _sha256(root / str(record["path"])) != record.get("sha256"):
        raise ValueError("augmented middle Schur file hash mismatch")
    if (
        record.get("shape") != list(expected_shape)
        or record.get("dtype") != "complex128"
    ):
        raise ValueError("augmented middle Schur record shape or dtype is invalid")
    if (
        metadata.get("shape") != list(expected_shape)
        or metadata.get("dtype") != "complex128"
    ):
        raise ValueError("augmented middle Schur metadata shape or dtype is invalid")
    if (
        metadata.get("finite") is not True
        or metadata.get("apply_count") != expected_shape[0]
    ):
        raise ValueError("augmented middle Schur metadata is incomplete")
    if metadata.get("rank") != recomputed["rank"] or not _finite(
        metadata.get("condition")
    ):
        raise ValueError("augmented middle Schur diagnostics are inconsistent")
    if not np.isclose(
        float(metadata["condition"]),
        float(recomputed["condition"]),
        rtol=1.0e-12,
        atol=0.0,
    ):
        raise ValueError("augmented middle Schur condition mismatch")
    return matrix, {
        "record": {
            "name": name,
            "path": str(record["path"]),
            "sha256": record["sha256"],
            "shape": list(record["shape"]),
            "dtype": record["dtype"],
        },
        "metadata": metadata,
        "recomputed": recomputed,
    }


def _maximum(metrics: list[dict[str, Any]], name: str) -> float | None:
    values = [float(item[name]) for item in metrics if _finite(item.get(name))]
    return max(values) if values else None


def _failure_decomposition(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Reuse V1's contraction reductions and expose V3's failure groups."""

    probe_metrics = v1_checker._probe_metrics(diagnostics)

    def probe_group(kind: str) -> dict[str, Any]:
        metrics = [item for item in probe_metrics if item["kind"] == kind]
        return {
            "count": len(metrics),
            "scalar_exact_relative_max": _maximum(
                metrics, "original_scalar_exact_relative"
            ),
            "projected_exact_relative_max": _maximum(
                metrics, "projected_exact_relative"
            ),
            "in_span_projection_relative_max": (
                _maximum(metrics, "projected_exact_relative")
                if kind == "modal_combination"
                else None
            ),
            "complement_orthogonality_max": _maximum(
                metrics, "complement_orthogonality"
            )
            if kind == "complement"
            else None,
            "cross_energy_ratio_max": None,
        }

    middle = diagnostics["middle_cross_interface_sampled_response"]
    direction: dict[str, dict[str, Any]] = {}
    for interface, name in (
        ("lower", "middle_lower_to_upper"),
        ("upper", "middle_upper_to_lower"),
    ):
        reports = [item for item in middle if item.get("interface") == interface]
        direction[name] = {
            "count": len(reports),
            "scalar_exact_relative_max": None,
            "projected_exact_relative_max": None,
            "in_span_projection_relative_max": None,
            "complement_orthogonality_max": None,
            "cross_energy_ratio_max": max(
                (float(item["cross_to_total"]) for item in reports), default=None
            ),
        }
    return {
        "physical": probe_group("physical"),
        "modal_combination": probe_group("modal_combination"),
        "complement": probe_group("complement"),
        **direction,
    }


def _semantic_mapping(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """State what the V2 matrices mean before applying V3 algebra to them."""

    incoming = diagnostics.get("incoming_neighbor_map", {})
    middle = diagnostics.get("middle_cross_interface_sampled_response", [])
    middle_cross_present = (
        len(middle) == 8
        and all(item.get("response") == "middle_group1_schur" for item in middle)
        and any(float(item.get("cross_to_total", 0.0)) > 0.0 for item in middle)
    )
    local_middle_matrix = diagnostics.get("additional_projected_matrices", {}).get(
        "projected_middle_group_schur"
    )
    return {
        "incoming_neighbor_map": {
            "map": incoming.get("map"),
            "response": incoming.get("response"),
        },
        "projected_scalar_semantics": "Y^H S_scalar Z",
        "projected_exact_semantics": "directed_neighbor_transmission",
        "old_group_semantics": {
            "group0": "Y0^H R_1_to_0 Z0, the lower restriction of middle S1",
            "group1": "Y1^H blockdiag(S0,S2) Z1",
            "group2": "Y2^H R_1_to_2 Z2, the upper restriction of middle S1",
        },
        "review_required_semantics": {
            "group0": "Y0^H S0 Z0",
            "group1": "Y1^H S1 Z1, including S1_LU and S1_UL",
            "group2": "Y2^H S2 Z2",
            "joint": "E1 + blockdiag(E0,E2)",
        },
        "incoming_neighbor_map_bound": (
            incoming.get("map") == "block_diagonal_neighbor_transmission"
            and incoming.get("response") == "apply_directed_neighbor"
        ),
        "middle_cross_sampled_response_present": middle_cross_present,
        "missing_local_middle_projected_exact": local_middle_matrix is None,
        "missing_middle_cross_blocks": local_middle_matrix is None,
        "missing_local_middle_blocks": (
            ["S1_LU", "S1_UL"] if local_middle_matrix is None else []
        ),
        "local_group_schur_evidence_pass": local_middle_matrix is not None,
        "z_gamma_in_packet": False,
        "y_reconstructible_from_v_g": True,
        "z_reconstructible_from_u": False,
        "factor_semantics": (
            "U=delta=(directed_neighbor-scalar)Z; V=Y G^-H; "
            "V G^H recovers Y, but U does not determine Z in general"
        ),
    }


def _joint_checks(
    assembled: dict[str, Any],
    group_matrices: list[dict[str, np.ndarray]],
) -> dict[str, Any]:
    diagnostics = assembled["diagnostics"]
    group_checks: list[bool] = []
    for index, group in enumerate(diagnostics["groups"]):
        expected = EXPECTED_SPAN_SIZES[index]
        group_checks.extend(
            [
                group["gram"]["shape"] == [expected, expected],
                group["gram"]["rank"] == expected,
                _finite(group["gram"]["condition"])
                and group["gram"]["condition"] <= CONDITION_LIMIT,
            ]
        )
    scalar = diagnostics["joint"]["projected_scalar"]
    exact = diagnostics["joint"]["projected_exact"]
    expected = EXPECTED_SPAN_SIZES[1]
    scalar_diagnostic_pass = (
        scalar["shape"] == [expected, expected]
        and isinstance(scalar["rank"], int)
        and _finite(scalar["condition"])
        and all(_finite(value) for value in scalar["singular_values"])
    )
    exact_gate_pass = (
        exact["shape"] == [expected, expected]
        and exact["rank"] == expected
        and _finite(exact["condition"])
        and exact["condition"] <= CONDITION_LIMIT
    )
    block_shapes = {
        "LL": [EXPECTED_SPAN_SIZES[0], EXPECTED_SPAN_SIZES[0]],
        "LU": [EXPECTED_SPAN_SIZES[0], EXPECTED_SPAN_SIZES[2]],
        "UL": [EXPECTED_SPAN_SIZES[2], EXPECTED_SPAN_SIZES[0]],
        "UU": [EXPECTED_SPAN_SIZES[2], EXPECTED_SPAN_SIZES[2]],
    }
    blocks = diagnostics["joint_exact_blocks"]
    ordering_pass = True
    for name, shape in block_shapes.items():
        block = blocks[name]
        ordering_pass = ordering_pass and (
            block["shape"] == shape
            and isinstance(block["rank"], int)
            and isinstance(block["sha256"], str)
            and len(block["sha256"]) == 64
        )
    block_checks: list[bool] = []
    for name in ("projected_scalar", "projected_exact"):
        item = diagnostics["joint"][name]
        block_checks.append(
            _finite(item["condition"])
            and all(_finite(value) for value in item["singular_values"])
        )
    block_finite = all(
        _finite(block["frobenius_norm"])
        and _finite(block["relative_frobenius_norm"])
        and block["condition"] is None
        for block in blocks.values()
    )
    return {
        "group_gram_pass": all(group_checks),
        "joint_scalar_diagnostic_pass": scalar_diagnostic_pass and block_checks[0],
        "joint_exact_structural_diagnostic_pass": exact_gate_pass and block_checks[1],
        "joint_exact_blocks_pass": block_finite and ordering_pass,
        "ordering_pass": ordering_pass,
        "block_shapes": block_shapes,
        "joint_exact_block_norms": {
            name: float(block["frobenius_norm"]) for name, block in blocks.items()
        },
        "gram_is_group_local": True,
        "joint_gram_defined": False,
        "projected_matrix_convention": (
            "projected_scalar/projected_exact are already Y^H S Z contractions; "
            "joint assembly is additive and does not sum Grams"
        ),
        "group_count": len(group_matrices),
    }


def _relative_error(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _augmented_joint_checks(
    group_matrices: list[dict[str, np.ndarray]], middle_matrix: np.ndarray
) -> dict[str, Any]:
    lower_span, _middle_span, upper_span = EXPECTED_SPAN_SIZES
    legacy_assembled = assemble_coupled_interface_matrices(group_matrices)
    legacy_checks = _joint_checks(legacy_assembled, group_matrices)
    joint = middle_matrix + group_matrices[1]["projected_exact"]
    joint_diagnostic = matrix_diagnostics(
        joint, expected_shape=(EXPECTED_SPAN_SIZES[1], EXPECTED_SPAN_SIZES[1])
    )
    slices = {
        "LL": (slice(0, lower_span), slice(0, lower_span)),
        "LU": (slice(0, lower_span), slice(lower_span, lower_span + upper_span)),
        "UL": (slice(lower_span, lower_span + upper_span), slice(0, lower_span)),
        "UU": (
            slice(lower_span, lower_span + upper_span),
            slice(lower_span, lower_span + upper_span),
        ),
    }
    full_norm = max(float(np.linalg.norm(joint, ord="fro")), np.finfo(float).tiny)
    block_diagnostics = {}
    for name, (row_slice, column_slice) in slices.items():
        block = np.asarray(joint[row_slice, column_slice], dtype=np.complex128)
        block_diagnostics[name] = {
            **matrix_diagnostics(block, square=False),
            "frobenius_norm": float(np.linalg.norm(block, ord="fro")),
            "relative_frobenius_norm": float(
                np.linalg.norm(block, ord="fro") / full_norm
            ),
        }
    middle_diagnostic = matrix_diagnostics(
        middle_matrix, expected_shape=(EXPECTED_SPAN_SIZES[1], EXPECTED_SPAN_SIZES[1])
    )
    lower_error = _relative_error(
        middle_matrix[:lower_span, :lower_span], group_matrices[0]["projected_exact"]
    )
    upper_error = _relative_error(
        middle_matrix[lower_span:, lower_span:], group_matrices[2]["projected_exact"]
    )
    legacy_difference = _relative_error(
        joint, legacy_assembled["joint_projected_exact"]
    )
    expected_shapes = {
        "LL": [lower_span, lower_span],
        "LU": [lower_span, upper_span],
        "UL": [upper_span, lower_span],
        "UU": [upper_span, upper_span],
    }
    blocks_pass = all(
        item["shape"] == expected_shapes[name]
        and item["dtype"] == "complex128"
        and _finite(item["rank"])
        and isinstance(item["sha256"], str)
        and len(item["sha256"]) == 64
        for name, item in block_diagnostics.items()
    )
    exact_gate_pass = (
        joint_diagnostic["rank"] == EXPECTED_SPAN_SIZES[1]
        and _finite(joint_diagnostic["condition"])
        and joint_diagnostic["condition"] <= CONDITION_LIMIT
    )
    return {
        "joint": joint,
        "legacy_structural_joint": legacy_assembled["joint_projected_exact"],
        "joint_diagnostics": joint_diagnostic,
        "joint_exact_blocks": block_diagnostics,
        "additional_middle_diagnostics": middle_diagnostic,
        "lower_identity_relative_error": lower_error,
        "upper_identity_relative_error": upper_error,
        "legacy_structural_difference_relative": legacy_difference,
        "group_gram_pass": legacy_checks["group_gram_pass"],
        "joint_scalar_diagnostic_pass": legacy_checks["joint_scalar_diagnostic_pass"],
        "joint_exact_structural_diagnostic_pass": exact_gate_pass,
        "joint_exact_blocks_pass": blocks_pass,
        "ordering_pass": all(
            item["shape"] == expected_shapes[name]
            for name, item in block_diagnostics.items()
        ),
        "joint_exact_block_norms": {
            name: float(item["frobenius_norm"])
            for name, item in block_diagnostics.items()
        },
        "joint_exact_block_ranks": {
            name: int(item["rank"]) for name, item in block_diagnostics.items()
        },
        "joint_exact_block_hashes": {
            name: item["sha256"] for name, item in block_diagnostics.items()
        },
    }


def recompute_v3_1_augmented_packet(
    packet_root: str | Path,
    *,
    watchdog_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute the V3-1 packet after the middle-group Schur extension."""

    root = Path(packet_root)
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != AUGMENTED_PACKET_MANIFEST_SHA256:
        raise ValueError("augmented packet manifest hash is not frozen")
    if (
        manifest.get("provenance", {}).get("source_sha")
        != AUGMENTED_PRODUCER_SOURCE_SHA
    ):
        raise ValueError("augmented packet producer source is not frozen")
    packet_result = check_v2_packet(
        root,
        expected_span_sizes=EXPECTED_SPAN_SIZES,
        watchdog_summary_path=watchdog_summary_path,
    )
    group_matrices, matrix_files = _load_projected_matrices(root, manifest)
    middle_matrix, middle_files = _load_augmented_middle_matrix(root, manifest)
    augmented = _augmented_joint_checks(group_matrices, middle_matrix)
    diagnostics = manifest["diagnostics"]
    decomposition = _failure_decomposition(diagnostics)
    semantic_mapping = _semantic_mapping(diagnostics)
    group_diagnostics = diagnostics["groups"]
    ordering_identity = {
        "producer_source_sha": manifest["provenance"].get("source_sha"),
        "lower_mode_count": diagnostics.get("lower", {}).get("mode_count"),
        "lower_mode_key_sha256": diagnostics.get("lower", {}).get("mode_key_sha256"),
        "upper_mode_count": diagnostics.get("upper", {}).get("mode_count"),
        "upper_mode_key_sha256": diagnostics.get("upper", {}).get("mode_key_sha256"),
        "upper_beta_sha256": diagnostics.get("upper", {}).get("beta_sha256"),
        "upper_branch_authority": diagnostics.get("upper", {}).get("branch_authority"),
        "upper_qep_calls": diagnostics.get("upper", {}).get("qep_calls"),
        "group1_span_size": group_diagnostics[1].get("span_size"),
        "group1_planes": group_diagnostics[1]
        .get("gamma_layout", {})
        .get("plane_identity", {})
        .get("planes"),
        "contract": "build_group_basis_columns: lower then upper",
    }
    ordering_identity_pass = (
        ordering_identity["producer_source_sha"] == AUGMENTED_PRODUCER_SOURCE_SHA
        and ordering_identity["lower_mode_count"] == EXPECTED_SPAN_SIZES[0]
        and ordering_identity["lower_mode_key_sha256"] == FROZEN_LOWER_MODE_KEY_SHA256
        and ordering_identity["upper_mode_count"] == EXPECTED_SPAN_SIZES[2]
        and ordering_identity["upper_mode_key_sha256"] == FROZEN_UPPER_MODE_KEY_SHA256
        and ordering_identity["upper_beta_sha256"] == FROZEN_UPPER_BETA_SHA256
        and ordering_identity["upper_branch_authority"] == "positive/forward"
        and ordering_identity["upper_qep_calls"] == 0
        and ordering_identity["group1_span_size"] == EXPECTED_SPAN_SIZES[1]
        and ordering_identity["group1_planes"] == ["lower", "upper"]
    )
    middle_metadata = middle_files["metadata"]
    middle_diagnostic = augmented["additional_middle_diagnostics"]
    middle_metadata_pass = (
        middle_metadata.get("schema") == AUGMENTED_MATRIX_SCHEMA
        and middle_metadata.get("semantic") == "Y1^H [oracle.apply_group(1)] Z1"
        and middle_metadata.get("apply_count") == EXPECTED_SPAN_SIZES[1]
        and middle_metadata.get("rank") == middle_diagnostic["rank"]
        and middle_metadata.get("finite") is True
        and _finite(middle_metadata.get("condition"))
        and augmented["lower_identity_relative_error"] <= 1.0e-12
        and augmented["upper_identity_relative_error"] <= 1.0e-12
    )
    watchdog_hash_pass = False
    run_summary_hash_pass = False
    if watchdog_summary_path is not None:
        summary_path = Path(watchdog_summary_path)
        worker_summary = summary_path.parent / "worker" / "run_summary.json"
        watchdog_hash_pass = _sha256(summary_path) == AUGMENTED_WATCHDOG_SUMMARY_SHA256
        run_summary_hash_pass = _sha256(worker_summary) == AUGMENTED_RUN_SUMMARY_SHA256
    checks = {
        "manifest_hash": manifest_sha256 == AUGMENTED_PACKET_MANIFEST_SHA256,
        "producer_source": ordering_identity_pass,
        "packet_authority": packet_result["packet_complete"] is True,
        "group_order": manifest.get("group_order") == ["group0", "group1", "group2"],
        "span_sizes": packet_result["small_matrices"]["groups"]
        and [
            item["gram_shape"][0] for item in packet_result["small_matrices"]["groups"]
        ]
        == list(EXPECTED_SPAN_SIZES),
        "group_gram_diagnostics": augmented["group_gram_pass"],
        "joint_scalar_diagnostics": augmented["joint_scalar_diagnostic_pass"],
        "middle_matrix": middle_metadata_pass,
        "joint_exact": augmented["joint_exact_structural_diagnostic_pass"],
        "joint_exact_blocks": augmented["joint_exact_blocks_pass"],
        "ordering_identity": ordering_identity_pass,
        "report_decomposition": decomposition["physical"]["count"] == 15
        and decomposition["modal_combination"]["count"] == 4
        and decomposition["complement"]["count"] == 4
        and decomposition["middle_lower_to_upper"]["count"] == 4
        and decomposition["middle_upper_to_lower"]["count"] == 4,
        "local_middle_schur_evidence": semantic_mapping[
            "local_group_schur_evidence_pass"
        ],
        "watchdog_hash": watchdog_hash_pass,
        "run_summary_hash": run_summary_hash_pass,
    }
    identity_checks = (
        "manifest_hash",
        "producer_source",
        "packet_authority",
        "group_order",
        "span_sizes",
        "ordering_identity",
        "report_decomposition",
        "local_middle_schur_evidence",
    )
    if not all(checks[name] for name in identity_checks):
        classification = "COUPLED_PACKET_INFORMATION_INCOMPLETE"
    elif not checks["joint_exact"]:
        classification = "COUPLED_INTERFACE_NUMERICAL_GATE_FAIL"
    elif not checks["watchdog_hash"] or not checks["run_summary_hash"]:
        classification = "COUPLED_INTERFACE_RESOURCE_GATE_FAIL"
    elif not all(checks.values()):
        classification = "COUPLED_INTERFACE_IMPLEMENTATION_FAILURE"
    else:
        classification = "COUPLED_INTERFACE_ALGEBRA_EVIDENCE_VALID"
    return {
        "schema": "task040.v3.coupled_interface.augmented.recomputed.v1",
        "augmented": True,
        "manifest_sha256": manifest_sha256,
        "producer_source_sha": manifest["provenance"]["source_sha"],
        "group_order": manifest["group_order"],
        "span_sizes": list(EXPECTED_SPAN_SIZES),
        "matrix_files": {
            "groups": matrix_files,
            "projected_middle_group_schur": middle_files,
        },
        "joint_diagnostics": augmented["joint_diagnostics"],
        "joint_exact_blocks": augmented["joint_exact_blocks"],
        "additional_middle_diagnostics": middle_diagnostic,
        "additional_middle_metadata": middle_metadata,
        "identity_relative_errors": {
            "lower": augmented["lower_identity_relative_error"],
            "upper": augmented["upper_identity_relative_error"],
        },
        "legacy_structural_difference_relative": augmented[
            "legacy_structural_difference_relative"
        ],
        "semantic_mapping": semantic_mapping,
        "ordering_identity": ordering_identity,
        "failure_decomposition": decomposition,
        "v2_packet_checks": packet_result["checks"],
        "watchdog": packet_result["watchdog"],
        "checks": checks,
        "classification": classification,
        "packet_sufficient": all(checks.values()),
    }


def recompute_v3_1_packet(
    packet_root: str | Path,
    *,
    watchdog_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute V3-1 joint algebra from packet small matrices and reports."""

    root = Path(packet_root)
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != FROZEN_PACKET_MANIFEST_SHA256:
        raise ValueError("V2 packet manifest hash is not frozen")
    packet_result = check_v2_packet(
        root,
        expected_span_sizes=EXPECTED_SPAN_SIZES,
        watchdog_summary_path=watchdog_summary_path,
    )
    group_matrices, matrix_files = _load_projected_matrices(root, manifest)
    assembled = assemble_coupled_interface_matrices(group_matrices)
    joint = _joint_checks(assembled, group_matrices)
    decomposition = _failure_decomposition(manifest["diagnostics"])
    diagnostics = manifest["diagnostics"]
    semantic_mapping = _semantic_mapping(diagnostics)
    group_diagnostics = diagnostics["groups"]
    ordering_identity = {
        "producer_source_sha": manifest["provenance"].get("source_sha"),
        "lower_mode_count": diagnostics.get("lower", {}).get("mode_count"),
        "lower_mode_key_sha256": diagnostics.get("lower", {}).get("mode_key_sha256"),
        "upper_mode_count": diagnostics.get("upper", {}).get("mode_count"),
        "upper_mode_key_sha256": diagnostics.get("upper", {}).get("mode_key_sha256"),
        "upper_beta_sha256": diagnostics.get("upper", {}).get("beta_sha256"),
        "upper_branch_authority": diagnostics.get("upper", {}).get("branch_authority"),
        "upper_qep_calls": diagnostics.get("upper", {}).get("qep_calls"),
        "group1_span_size": group_diagnostics[1].get("span_size"),
        "group1_planes": group_diagnostics[1]
        .get("gamma_layout", {})
        .get("plane_identity", {})
        .get("planes"),
        "contract": "build_group_basis_columns: lower then upper",
    }
    ordering_identity_pass = (
        ordering_identity["producer_source_sha"] == FROZEN_PRODUCER_SOURCE_SHA
        and ordering_identity["lower_mode_count"] == EXPECTED_SPAN_SIZES[0]
        and ordering_identity["lower_mode_key_sha256"] == FROZEN_LOWER_MODE_KEY_SHA256
        and ordering_identity["upper_mode_count"] == EXPECTED_SPAN_SIZES[2]
        and ordering_identity["upper_mode_key_sha256"] == FROZEN_UPPER_MODE_KEY_SHA256
        and ordering_identity["upper_beta_sha256"] == FROZEN_UPPER_BETA_SHA256
        and ordering_identity["upper_branch_authority"] == "positive/forward"
        and ordering_identity["upper_qep_calls"] == 0
        and ordering_identity["group1_span_size"] == EXPECTED_SPAN_SIZES[1]
        and ordering_identity["group1_planes"] == ["lower", "upper"]
    )
    checks = {
        "manifest_hash": manifest_sha256 == FROZEN_PACKET_MANIFEST_SHA256,
        "packet_authority": packet_result["packet_complete"] is True,
        "group_order": assembled["group_order"] == ["group0", "group1", "group2"],
        "span_sizes": assembled["span_sizes"] == list(EXPECTED_SPAN_SIZES),
        "group_gram_diagnostics": joint["group_gram_pass"],
        "joint_scalar_diagnostics": joint["joint_scalar_diagnostic_pass"],
        "joint_exact_structural_diagnostic": joint[
            "joint_exact_structural_diagnostic_pass"
        ],
        "joint_exact_blocks": joint["joint_exact_blocks_pass"],
        "ordering_identity": ordering_identity_pass,
        "report_decomposition": decomposition["physical"]["count"] == 15
        and decomposition["modal_combination"]["count"] == 4
        and decomposition["complement"]["count"] == 4
        and decomposition["middle_lower_to_upper"]["count"] == 4
        and decomposition["middle_upper_to_lower"]["count"] == 4,
        "local_middle_schur_evidence": semantic_mapping[
            "local_group_schur_evidence_pass"
        ],
    }
    identity_checks = (
        "manifest_hash",
        "packet_authority",
        "group_order",
        "span_sizes",
        "ordering_identity",
        "report_decomposition",
        "local_middle_schur_evidence",
    )
    if not all(checks[name] for name in identity_checks):
        classification = "COUPLED_PACKET_INFORMATION_INCOMPLETE"
    elif not checks["joint_exact_structural_diagnostic"]:
        classification = "COUPLED_INTERFACE_NUMERICAL_GATE_FAIL"
    elif not all(checks.values()):
        classification = "COUPLED_INTERFACE_IMPLEMENTATION_FAILURE"
    else:
        classification = "COUPLED_INTERFACE_ALGEBRA_EVIDENCE_VALID"
    return {
        "schema": "task040.v3.coupled_interface.recomputed.v1",
        "manifest_sha256": manifest_sha256,
        "producer_source_sha": manifest["provenance"]["source_sha"],
        "group_order": assembled["group_order"],
        "span_sizes": assembled["span_sizes"],
        "matrix_files": matrix_files,
        "group_diagnostics": assembled["diagnostics"]["groups"],
        "joint_diagnostics": assembled["diagnostics"]["joint"],
        "joint_exact_blocks": assembled["diagnostics"]["joint_exact_blocks"],
        "joint_scalar_blocks": assembled["diagnostics"]["joint_scalar_blocks"],
        "joint_checks": joint,
        "semantic_mapping": semantic_mapping,
        "ordering_identity": ordering_identity,
        "failure_decomposition": decomposition,
        "v2_packet_checks": packet_result["checks"],
        "checks": checks,
        "classification": classification,
        "packet_sufficient": all(checks.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--watchdog-summary")
    parser.add_argument("--output")
    parser.add_argument("--augmented", action="store_true")
    args = parser.parse_args(argv)
    try:
        checker = (
            recompute_v3_1_augmented_packet if args.augmented else recompute_v3_1_packet
        )
        result = checker(args.packet_root, watchdog_summary_path=args.watchdog_summary)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "task040.v3.coupled_interface.recomputed.v1",
            "error": str(exc),
            "packet_sufficient": False,
        }
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result.get("packet_sufficient") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
