"""Build the Task035b 12-channel response-direction evidence.

This is an exclusive-create, SHA-bound, pure postprocessor.  It reads completed
watchdog/comparator records only; it never imports or invokes a PDE runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from src.adaptivity.channel_response_matrix import (
    normalized_error_vector,
    reference_channel_contract,
    restricted_response_subspace,
    response_matrix_evidence,
    topology_resource_row,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = (
    "codex/20260723-task35b-high-order-local-hp-resource-envelope"
)
RECORDS = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
DEFAULT_OUTPUT = (
    RECORDS / "channel_response_matrix_directionality_v1.json"
)
SOURCE_FILES = (
    "benchmarks/task035b_channel_response_matrix.py",
    "src/adaptivity/channel_response_matrix.py",
)
DEFAULT_AUTHORITIES = {
    "significant_reference_v1": {
        "path": RECORDS / "significant_channel_reference_v1.json",
        "sha256": (
            "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3"
        ),
    },
    "fixed_h15_seed": {
        "path": RECORDS / "fixed_p5trace_p6interior_h15_mpi8.json",
        "sha256": (
            "84c9b898100bc2f223913a144d9b7a9a324ef17d9164610c622b3ecc480d870a"
        ),
    },
    "z_h14": {
        "path": (
            RECORDS / "fixed_p5trace_p6interior_h14_directional_z_mpi8.json"
        ),
        "sha256": (
            "e93f50155b3c8517292794cb9735730ebf738410aecafe00f43f7959c150a127"
        ),
    },
    "z_h13": {
        "path": (
            RECORDS / "fixed_p5trace_p6interior_h13_directional_z_mpi8.json"
        ),
        "sha256": (
            "81ba43d91c4c9a35121676ae40368d56116f3a381e4559d630fb547a94dc4a5c"
        ),
    },
    "x_only": {
        "path": (
            RECORDS / "fixed_p5trace_p6interior_h15_directional_x_mpi8.json"
        ),
        "sha256": (
            "0e469bd9f952652f102c33d8d0d7c14827a0a492bb2611971cafdc66a3b7bd2c"
        ),
    },
    "y_raw_watchdog": {
        "path": RECORDS / "global_hexa_p4_p5_h15_directional_y_mpi8.json",
        "sha256": (
            "8070ff6a7df90490421724fe1f399a60cbe168b55d153f7f9b0a2cf5e8d1b192"
        ),
    },
    "y_comparison": {
        "path": (
            RECORDS / "y_only_global_p5_directional_control_comparison_v1.json"
        ),
        "sha256": (
            "6263db07dc6bc3d9b4a2d2be8af529a0f471f0b0e123a9c77044fef129cc9236"
        ),
    },
    "dtn_buffer1": {
        "path": (
            RECORDS
            / "fixed_p5trace_p6interior_h15_dtn_evanescent_"
            "buffer1_scaled_mpi8.json"
        ),
        "sha256": (
            "2f76568d7013662602293e18ce75e33f6ecd625d723bc1cf745964a1a4541206"
        ),
    },
}
LANE_ORDER = ("z_h14", "z_h13", "x_only", "y_only", "dtn_buffer1")
FULL3D_EQUIVALENT_DOF_LIMIT = 90_000
COMPATIBLE_PAIRS = {
    frozenset(("z_h14", "x_only")),
    frozenset(("z_h14", "dtn_buffer1")),
    frozenset(("z_h13", "x_only")),
    frozenset(("z_h13", "dtn_buffer1")),
    frozenset(("x_only", "dtn_buffer1")),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _full_git_sha(value: Any) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 40 and all(
        character in "0123456789abcdef"
        for character in normalized
    )


def _full_sha256(value: Any) -> bool:
    normalized = str(value).lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef"
        for character in normalized
    )


def _verified_source_identity(
    repo_root: Path,
    verified_clean_sha: str,
) -> dict[str, Any]:
    verified = str(verified_clean_sha).strip().lower()
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "full_verified_sha": _full_git_sha(verified),
        "head_matches_verified_sha": head == verified,
        "expected_branch": branch == EXPECTED_BRANCH,
        "tracked_and_untracked_worktree_clean": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "channel-response source gate failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "commit_sha": head,
        "verified_clean_sha": verified,
        "branch": branch,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "status_before": status,
        "checks": checks,
    }


def _reverify_source_before_write(
    repo_root: Path,
    source_before: Mapping[str, Any],
) -> dict[str, Any]:
    head = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    status = _git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    checks = {
        "head_stable_after_build": head == source_before.get("commit_sha"),
        "branch_stable_after_build": (
            branch == source_before.get("branch") == EXPECTED_BRANCH
        ),
        "tracked_and_untracked_worktree_clean_after_build": status == "",
    }
    if not all(checks.values()):
        raise SystemExit(
            "channel-response source changed before evidence write: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return {
        "head_after_sha": head,
        "branch_after": branch,
        "status_after_before_record_write": status,
        "stable_and_clean_after": True,
        "checks": checks,
    }


def _validated_source(source: Mapping[str, Any]) -> dict[str, Any]:
    checks = source.get("checks")
    valid = bool(
        _full_git_sha(source.get("commit_sha"))
        and source.get("commit_sha") == source.get("verified_clean_sha")
        and source.get("branch") == EXPECTED_BRANCH
        and source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_before") is True
        and source.get("head_after_sha") == source.get("commit_sha")
        and source.get("branch_after") == EXPECTED_BRANCH
        and source.get("status_after_before_record_write") == ""
        and source.get("stable_and_clean_after") is True
        and isinstance(checks, Mapping)
        and bool(checks)
        and all(value is True for value in checks.values())
    )
    if not valid:
        raise ValueError("channel-response source identity is unqualified")
    return dict(source)


def _resolve(repo_root: Path, path: Path | str) -> Path:
    result = Path(path)
    if not result.is_absolute():
        result = repo_root / result
    return result.resolve()


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _load_authorities(
    repo_root: Path,
    definitions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payloads: dict[str, dict[str, Any]] = {}
    manifest: dict[str, dict[str, Any]] = {}
    required = set(DEFAULT_AUTHORITIES)
    if set(definitions) != required:
        missing = sorted(required - set(definitions))
        extra = sorted(set(definitions) - required)
        raise ValueError(
            f"authority definition mismatch; missing={missing}, extra={extra}"
        )
    for name, definition in definitions.items():
        expected = str(definition.get("sha256", "")).lower()
        if not _full_sha256(expected):
            raise ValueError(f"{name} expected SHA256 is invalid")
        path = _resolve(repo_root, definition["path"])
        if not path.is_file():
            raise ValueError(f"{name} authority is unreadable: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"{name} SHA256 mismatch: expected {expected}, got {actual}"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{name} authority must contain a JSON object")
        payloads[name] = payload
        source = payload.get("source") or {}
        manifest[name] = {
            "path": _display_path(repo_root, path),
            "sha256": actual,
            "schema_version": payload.get("schema_version"),
            "status": payload.get("status"),
            "source_commit_sha": source.get("commit_sha"),
        }
    return payloads, manifest


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _qualified_record_source(
    record: Mapping[str, Any],
    *,
    label: str,
) -> None:
    source = record.get("source")
    _require(isinstance(source, Mapping), f"{label} source is absent")
    commit = source.get("commit_sha")
    _require(_full_git_sha(commit), f"{label} source SHA is invalid")
    _require(
        commit == source.get("verified_clean_sha"),
        f"{label} source SHA was not verified",
    )
    _require(
        source.get("tracked_source_dirty") is False,
        f"{label} was produced from dirty tracked source",
    )
    _require(
        source.get("head_after_sha") == commit
        and source.get("status_after_before_record_write") == ""
        and source.get("stable_and_clean_after") is True,
        f"{label} source was not stable through record creation",
    )


def _qualified_watchdog(
    record: Mapping[str, Any],
    *,
    label: str,
    fixed_trace: bool,
) -> None:
    expected_schema = (
        "task035b.fixed-trace-watchdog.v1"
        if fixed_trace
        else "task035.actual-global-r5-watchdog.v1"
    )
    _require(
        record.get("schema_version") == expected_schema,
        f"{label} schema mismatch",
    )
    qualification = record.get("qualification")
    _require(
        isinstance(qualification, Mapping)
        and qualification.get("pass") is True
        and qualification.get("failures") == [],
        f"{label} qualification failed",
    )
    checks = qualification.get("checks")
    _require(
        isinstance(checks, Mapping)
        and bool(checks)
        and all(value is True for value in checks.values()),
        f"{label} contains a false qualification check",
    )
    _require(
        record.get("terminated_for_memory") is False
        and record.get("terminated_for_timeout") is False,
        f"{label} did not complete normally",
    )
    _qualified_record_source(record, label=label)
    result = record.get("candidate" if fixed_trace else "enriched")
    _require(isinstance(result, Mapping), f"{label} result is absent")
    _require(
        result.get("official_result") is True
        and result.get("mpi_size") == 8,
        f"{label} is not an official MPI8 result",
    )
    residual = (
        (result.get("cell_static_condensation") or {})
        .get("full_explicit_true_residual", {})
        .get("linear_system_relative_residual")
    )
    try:
        residual_value = float(residual)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} true residual is invalid") from error
    _require(
        0.0 <= residual_value <= 1.0e-9,
        f"{label} full explicit true residual fails",
    )


def _comparison_channels(
    comparison: Mapping[str, Any],
    *,
    label: str,
    allow_all_80: bool,
) -> list[Mapping[str, Any]]:
    channels = comparison.get("channels")
    _require(isinstance(channels, list), f"{label} channels are absent")
    if allow_all_80:
        _require(
            comparison.get("significant_channel_count") == 12
            and len(channels) == 80
            and sum(entry.get("significant") is True for entry in channels)
            == 12,
            f"{label} does not contain the expected frozen 12 of 80",
        )
    else:
        _require(
            comparison.get("frozen_significant_channel_count") == 12
            and len(channels) == 12
            and comparison.get("thresholds_relaxed") is False,
            f"{label} does not use the unchanged frozen 12-channel Gate",
        )
    _require(
        comparison.get("analytic_channel_identity_pass") is True,
        f"{label} analytic identity failed",
    )
    return channels


def _validate_y_pair(
    *,
    raw: Mapping[str, Any],
    raw_manifest: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    _qualified_watchdog(
        raw,
        label="y_raw_watchdog",
        fixed_trace=False,
    )
    _require(
        raw.get("status") == "actual_global_r5_pass",
        "y raw watchdog did not pass",
    )
    classification = raw.get("structured_axis_control_classification")
    _require(
        isinstance(classification, Mapping)
        and classification.get("role")
        == "y_only_global_p5_directional_control"
        and classification.get("diagnostic_only") is True
        and classification.get("formal_candidate_eligible") is False
        and classification.get("thresholds_relaxed") is False,
        "y raw watchdog role is not the authorized diagnostic control",
    )
    _require(
        comparison.get("schema_version")
        == "task035b.y-only-global-p5-directional-control-comparison.v1"
        and comparison.get("status")
        == "controlled_negative_y_directional_control_signal"
        and comparison.get("diagnostic_only") is True
        and comparison.get("formal_candidate_eligible") is False
        and comparison.get("thresholds_relaxed") is False,
        "y comparison classification is not qualified",
    )
    qualification = comparison.get("qualification")
    _require(
        isinstance(qualification, Mapping)
        and qualification.get("pass") is True
        and qualification.get("failures") == []
        and all(
            value is True
            for value in (qualification.get("checks") or {}).values()
        ),
        "y comparison qualification failed",
    )
    _qualified_record_source(comparison, label="y_comparison")
    bound_raw = (
        (comparison.get("authorities") or {}).get("y_control_watchdog") or {}
    )
    _require(
        bound_raw.get("sha256") == raw_manifest.get("sha256"),
        "y comparison does not bind the supplied raw watchdog",
    )
    return _comparison_channels(
        comparison.get("candidate_significant_channel_comparison") or {},
        label="y_comparison",
        allow_all_80=False,
    )


def _validate_fixed_lane(
    record: Mapping[str, Any],
    *,
    label: str,
    expected_statuses: set[str],
) -> list[Mapping[str, Any]]:
    _qualified_watchdog(
        record,
        label=label,
        fixed_trace=True,
    )
    _require(
        record.get("status") in expected_statuses,
        f"{label} status is not an accepted controlled-negative class",
    )
    return _comparison_channels(
        record.get("diffraction_channel_comparison") or {},
        label=label,
        allow_all_80=False,
    )


def _source_file_sha256(repo_root: Path) -> dict[str, str]:
    return {
        path: _sha256(repo_root / path)
        for path in SOURCE_FILES
    }


def _findings(
    response: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = response["lane_metrics"]
    combinations_rows = response["linearized_pairwise_combinations"]
    worthwhile = [
        row["lane"]
        for row in metrics
        if row["classification"]
        in {"worth_followup", "worth_targeted_discriminator_only"}
    ]
    unsupported = [
        row["lane"]
        for row in metrics
        if row["classification"]
        in {
            "not_worth_repeat",
            "not_supported_as_standalone_lane",
        }
    ]
    worthwhile_pairs = [
        [row["lane_a"], row["lane_b"]]
        for row in combinations_rows
        if row["classification"] == "worth_one_targeted_discriminator"
    ]
    not_supported_pairs = [
        {
            "lanes": [row["lane_a"], row["lane_b"]],
            "classification": row["classification"],
            "reason": row["reason"],
        }
        for row in combinations_rows
        if row["classification"] != "worth_one_targeted_discriminator"
    ]
    best = min(metrics, key=lambda row: row["normalized_joint_l2"])
    restricted = response["z_h13_remaining_failure_subspace"]
    effective_rank = restricted["effective_rank"]
    z_h13_pairs = [
        {
            "other_lane": (
                row["lane_b"]
                if row["lane_a"] == "z_h13"
                else row["lane_a"]
            ),
            "classification": row["classification"],
            "relative_joint_improvement_over_best_single": row.get(
                "relative_joint_improvement_over_best_single"
            ),
        }
        for row in combinations_rows
        if "z_h13" in {row["lane_a"], row["lane_b"]}
    ]
    return {
        "best_measured_individual_lane_by_joint_normalized_l2": best["lane"],
        "worthwhile_individual_followups": worthwhile,
        "unsupported_or_negligible_individual_lanes": unsupported,
        "worthwhile_linearized_pair_discriminators": worthwhile_pairs,
        "unsupported_or_noncomposable_pairs": not_supported_pairs,
        "z_h13_remaining_failure_subspace_conclusion": {
            "channel_count": restricted["selected_channel_count"],
            "channels": restricted["selected_channel_labels"],
            "power_effectively_low_rank_at_99_percent": (
                effective_rank["power_at_99_percent_energy"] <= 2
            ),
            "complex_effectively_low_rank_at_99_percent": (
                effective_rank["complex_at_99_percent_energy"] <= 2
            ),
            "power_rank_at_99_percent": effective_rank[
                "power_at_99_percent_energy"
            ],
            "complex_rank_at_99_percent": effective_rank[
                "complex_at_99_percent_energy"
            ],
            "decision": (
                "power responses are approximately rank-2, but complex "
                "responses retain a third material direction; one scalar "
                "recovery knob is not supported for the remaining 12/12 Gate"
            ),
        },
        "z_h13_pair_projection_conclusion": {
            "pairs": z_h13_pairs,
            "any_supported_pair": any(
                row["classification"]
                == "worth_one_targeted_discriminator"
                for row in combinations_rows
                if "z_h13" in {row["lane_a"], row["lane_b"]}
            ),
        },
        "decision_thresholds": {
            "material_norm_reduction": 0.05,
            "maximum_nonmaterial_family_regression": 0.01,
            "negligible_response_relative_size": 1.0e-6,
            "pair_improvement_over_best_single": 0.05,
            "formal_gate_relaxed": False,
        },
        "scope": (
            "diagnostic prioritization only; a worthwhile projection still "
            "requires one actual MPI8 candidate and the unchanged 12/12 Gate"
        ),
    }


def build_channel_response_evidence(
    *,
    authorities: Mapping[str, Mapping[str, Any]],
    authority_manifest: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, Any],
    source_file_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Validate bound inputs and build the complete pure-postprocess record."""

    _require(
        set(authorities) == set(DEFAULT_AUTHORITIES),
        "the complete authority set is required",
    )
    _require(
        set(authority_manifest) == set(DEFAULT_AUTHORITIES),
        "the complete authority manifest is required",
    )
    qualified_source = _validated_source(source)
    hashes = dict(source_file_sha256)
    _require(
        set(hashes) == set(SOURCE_FILES)
        and all(_full_sha256(value) for value in hashes.values()),
        "source-file hashes are incomplete or invalid",
    )

    reference = authorities["significant_reference_v1"]
    contract = reference_channel_contract(reference)

    seed_record = authorities["fixed_h15_seed"]
    _qualified_watchdog(
        seed_record,
        label="fixed_h15_seed",
        fixed_trace=True,
    )
    _require(
        seed_record.get("status") == "actual_fixed_trace_controlled_negative",
        "fixed h15 seed status is not accepted",
    )
    seed_channels = _comparison_channels(
        seed_record.get("diffraction_channel_comparison") or {},
        label="fixed_h15_seed",
        allow_all_80=True,
    )

    lane_channels: dict[str, list[Mapping[str, Any]]] = {}
    for lane in ("z_h14", "z_h13", "x_only"):
        lane_channels[lane] = _validate_fixed_lane(
            authorities[lane],
            label=lane,
            expected_statuses={"actual_fixed_trace_controlled_negative"},
        )
    lane_channels["dtn_buffer1"] = _validate_fixed_lane(
        authorities["dtn_buffer1"],
        label="dtn_buffer1",
        expected_statuses={
            "actual_fixed_trace_port_diagnostic_controlled_negative"
        },
    )
    port_diagnostic = authorities["dtn_buffer1"].get("port_diagnostic")
    _require(
        isinstance(port_diagnostic, Mapping)
        and port_diagnostic.get("classification_complete") is True
        and port_diagnostic.get("formal_candidate_eligible") is False
        and port_diagnostic.get("evanescent_buffer") == 1
        and port_diagnostic.get("thresholds_relaxed") is False,
        "buffer1 is not the qualified isolated port diagnostic",
    )
    lane_channels["y_only"] = _validate_y_pair(
        raw=authorities["y_raw_watchdog"],
        raw_manifest=authority_manifest["y_raw_watchdog"],
        comparison=authorities["y_comparison"],
    )

    seed_vector = normalized_error_vector(
        contract,
        seed_channels,
        lane="fixed_h15_seed",
    )
    lane_vectors = [
        normalized_error_vector(
            contract,
            lane_channels[lane],
            lane=lane,
        )
        for lane in LANE_ORDER
    ]
    response = response_matrix_evidence(
        contract=contract,
        seed=seed_vector,
        lanes=lane_vectors,
        compatible_pairs=COMPATIBLE_PAIRS,
    )
    z_h13_vector = next(
        lane for lane in lane_vectors if lane["lane"] == "z_h13"
    )
    z_h13_failed_labels = [
        row["label"]
        for row in z_h13_vector["channels"]
        if not (
            row["power_pass_recomputed"]
            and row["complex_amplitude_pass_recomputed"]
        )
    ]
    response["z_h13_remaining_failure_subspace"] = (
        restricted_response_subspace(
            response,
            selected_channel_labels=z_h13_failed_labels,
        )
    )

    seed_resource = topology_resource_row(
        lane="fixed_h15_seed",
        record=seed_record,
        result_field="candidate",
        seed_row=None,
    )
    resource_rows = [seed_resource]
    for lane in LANE_ORDER:
        raw_lane = (
            authorities["y_raw_watchdog"]
            if lane == "y_only"
            else authorities[lane]
        )
        result_field = "enriched" if lane == "y_only" else "candidate"
        resource_rows.append(
            topology_resource_row(
                lane=lane,
                record=raw_lane,
                result_field=result_field,
                seed_row=seed_resource,
            )
        )
    metrics_by_lane = {
        row["lane"]: row
        for row in response["lane_metrics"]
    }
    topology_response_marginals: list[dict[str, Any]] = []
    for row in resource_rows:
        joined = dict(row)
        joined["full3d_equivalent_dof_limit"] = (
            FULL3D_EQUIVALENT_DOF_LIMIT
        )
        joined["full3d_equivalent_dof_headroom"] = (
            FULL3D_EQUIVALENT_DOF_LIMIT
            - row["full3d_equivalent_dofs"]
        )
        joined["within_full3d_equivalent_dof_limit"] = (
            row["full3d_equivalent_dofs"]
            <= FULL3D_EQUIVALENT_DOF_LIMIT
        )
        if row["lane"] != "fixed_h15_seed":
            metric = metrics_by_lane[row["lane"]]
            marginal = row["marginal_to_fixed_h15_seed"]
            delta_rows = marginal["delta_active_rows"]
            delta_factor_nnz = marginal["delta_factor_nnz"]
            joint_reduction = metric["joint_relative_reduction_from_seed"]
            joined["response_marginal"] = {
                "joint_relative_error_reduction": joint_reduction,
                "joint_reduction_per_1000_added_rows": (
                    joint_reduction * 1000.0 / delta_rows
                    if delta_rows > 0
                    else None
                ),
                "joint_reduction_per_1e6_added_factor_nnz": (
                    joint_reduction * 1.0e6 / delta_factor_nnz
                    if delta_factor_nnz > 0
                    else None
                ),
                "power_pass_count_recomputed": metric[
                    "power_pass_count_recomputed"
                ],
                "complex_amplitude_pass_count_recomputed": metric[
                    "complex_amplitude_pass_count_recomputed"
                ],
                "classification": metric["classification"],
            }
        topology_response_marginals.append(joined)

    evidence = {
        "schema_version": "task035b.channel-response-directionality.v1",
        "status": "channel_response_directionality_diagnostic_complete",
        "pass": True,
        "purpose": (
            "separate signed 12-channel power and complex-amplitude response "
            "directions and prioritize the smallest next discriminator"
        ),
        "source": qualified_source,
        "source_file_sha256": hashes,
        "authorities": {
            name: dict(authority_manifest[name])
            for name in DEFAULT_AUTHORITIES
        },
        "authority_binding_checks": {
            "significant_reference_v1_sha_bound": True,
            "fixed_h15_seed_sha_bound": True,
            "z_h14_and_h13_sha_bound": True,
            "x_only_sha_bound": True,
            "y_comparison_and_raw_watchdog_sha_bound": True,
            "buffer1_sha_bound": True,
            "all_authority_source_records_clean_and_qualified": True,
        },
        "response_analysis": response,
        "topology_rows_nnz_factor_peak_marginals": (
            topology_response_marginals
        ),
        "findings": _findings(response),
        "execution_contract": {
            "pure_postprocess": True,
            "pde_solve_count": 0,
            "mesh_build_count": 0,
            "matrix_assembly_count": 0,
            "factorization_count": 0,
            "mpi_launch_count": 0,
            "ordinary_default_changed": False,
            "thresholds_relaxed": False,
            "irregular_geometry_run": False,
            "formal_candidate_eligible": False,
        },
    }
    json.dumps(evidence, allow_nan=False)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    for name, definition in DEFAULT_AUTHORITIES.items():
        option = name.replace("_", "-")
        parser.add_argument(
            f"--{option}-record",
            type=Path,
            default=definition["path"],
        )
        parser.add_argument(
            f"--{option}-sha256",
            default=definition["sha256"],
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source_before = _verified_source_identity(
        ROOT,
        args.verified_clean_sha,
    )
    definitions = {
        name: {
            "path": getattr(args, f"{name}_record"),
            "sha256": getattr(args, f"{name}_sha256"),
        }
        for name in DEFAULT_AUTHORITIES
    }
    authorities, manifest = _load_authorities(ROOT, definitions)
    source_hashes = _source_file_sha256(ROOT)
    source_after = _reverify_source_before_write(ROOT, source_before)
    source = dict(source_before)
    source.update(source_after)
    combined_checks = dict(source_before["checks"])
    combined_checks.update(source_after["checks"])
    source["checks"] = combined_checks
    evidence = build_channel_response_evidence(
        authorities=authorities,
        authority_manifest=manifest,
        source=source,
        source_file_sha256=source_hashes,
    )
    source_final = _reverify_source_before_write(ROOT, source_before)
    final_source = dict(source_before)
    final_source.update(source_final)
    final_checks = dict(source_before["checks"])
    final_checks.update(source_final["checks"])
    final_source["checks"] = final_checks
    if _source_file_sha256(ROOT) != source_hashes:
        raise SystemExit(
            "channel-response source files changed before evidence write"
        )
    evidence["source"] = _validated_source(final_source)
    output = _resolve(ROOT, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            evidence,
            stream,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
