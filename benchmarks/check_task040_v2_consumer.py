"""Independent raw checker for the Task040 V2-B packet consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_SOURCE_LABELS,
    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
    TASK040_V1_2_INPUT_SHA256,
    TASK040_V1_2_PHYSICAL_MODEL_SHA256,
    TASK040_V1_2_PROBE_MANIFEST_SHA256,
    TASK040_V1_2_SELECTED_MANIFEST_SHA256,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
    TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
)

EXPECTED_PACKET_SCHEMA = "task040.interface_schur_packet.v1"
EXPECTED_PRODUCER_SOURCE_SHA = "942c43881e4162085348c48b09c79fbbdac18cd9"
EXPECTED_GLOBAL_ROWS = (7560, 15120, 7560)
EXPECTED_SPANS = (296, 776, 480)
PREFERRED_LABELS = (
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
)
RESOURCE_LIMIT_BYTES = 45 * 2**30

__all__ = ["check_v2_consumer", "recompute_v2_consumer", "main"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and np.isfinite(float(value))


def _expected_provenance() -> dict[str, Any]:
    return {
        "schema": "task040.v2.interface_packet_producer.v1",
        "source_sha": EXPECTED_PRODUCER_SOURCE_SHA,
        "input_sha256": TASK040_V1_2_INPUT_SHA256,
        "physical_model_sha256": TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "exact_spool_catalog_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }


def _manifest_pass(manifest: Mapping[str, Any], manifest_sha256: str) -> bool:
    try:
        groups = manifest["groups"]
        diagnostics = manifest["diagnostics"]
        diagnostic_groups = diagnostics["groups"]
        provenance = manifest["provenance"]
        return bool(
            manifest_sha256 == TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256
            and manifest["schema"] == EXPECTED_PACKET_SCHEMA
            and manifest["packet_complete"] is True
            and manifest["group_order"] == ["group0", "group1", "group2"]
            and manifest["rank_count"] == 8
            and manifest["basis_global_replicated"] is False
            and manifest["numeric_allgather"] is False
            and manifest["fe_numeric_allgather"] is False
            and provenance == _expected_provenance()
            and set(groups) == set(manifest["group_order"])
            and len(diagnostic_groups) == 3
            and [item["group"] for item in diagnostic_groups] == [0, 1, 2]
            and all(
                int(groups[name]["global_count"]) == expected
                for name, expected in zip(
                    manifest["group_order"], EXPECTED_GLOBAL_ROWS, strict=True
                )
            )
            and all(
                int(item["gamma_layout"]["global_row_count"]) == expected
                and (
                    (
                        "global_size" not in item["gamma_layout"]
                        or item["gamma_layout"]["global_size"] is None
                    )
                    if index == 1
                    else int(item["gamma_layout"]["global_size"]) == expected
                )
                and int(item["span_size"]) == EXPECTED_SPANS[index]
                for index, (item, expected) in enumerate(
                    zip(diagnostic_groups, EXPECTED_GLOBAL_ROWS, strict=True)
                )
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _identity_pass(
    run: Mapping[str, Any],
    raw: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_sha256: str,
) -> bool:
    try:
        provenance = manifest["provenance"]
        observed = manifest["diagnostics"]["identity_observed"]
        labels = list(TASK040_LEVEL_A_SOURCE_LABELS[1:])
        exact_ids = observed["exact_output_identity_sha256"]
        return bool(
            _manifest_pass(manifest, manifest_sha256)
            and run["schema"] == TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA
            and run["method"] == TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD
            and run["profile"] == TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID
            and run["packet_manifest_sha256"] == manifest_sha256
            and run["packet_producer_source_sha"] == EXPECTED_PRODUCER_SOURCE_SHA
            and raw["packet_manifest_sha256"] == manifest_sha256
            and raw["producer_source_sha"] == EXPECTED_PRODUCER_SOURCE_SHA
            and raw["packet_consumer"] is True
            and raw["packet_provenance"] == provenance
            and run["input_sha256"] == TASK040_V1_2_INPUT_SHA256
            and run["physical_model_sha256"] == TASK040_V1_2_PHYSICAL_MODEL_SHA256
            and run["selected_manifest_sha256"] == TASK040_V1_2_SELECTED_MANIFEST_SHA256
            and run["exact_spool_catalog_sha256"]
            == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
            and observed["input_sha256"] == TASK040_V1_2_INPUT_SHA256
            and observed["physical_model_sha256"] == TASK040_V1_2_PHYSICAL_MODEL_SHA256
            and observed["selected_manifest_sha256"]
            == TASK040_V1_2_SELECTED_MANIFEST_SHA256
            and observed["spool_catalog_sha256"]
            == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
            and observed["probe_manifest_sha256"] == TASK040_V1_2_PROBE_MANIFEST_SHA256
            and set(exact_ids) == set(labels)
            and all(
                isinstance(value, str)
                and len(value) == 64
                and all(character in "0123456789abcdef" for character in value)
                for value in exact_ids.values()
            )
            and raw["source_loading"]["labels"] == list(TASK040_LEVEL_A_SOURCE_LABELS)
            and raw["source_loading"]["rhs_vectors_loaded"] == 6
            and raw["source_loading"]["exact_output_vectors_loaded"] == 0
            and raw["source_loading"]["exact_output_metadata_hash_validation_only"]
            is True
            and run["rhs_vectors_loaded"] == 6
            and {
                "qep",
                "exact_interface_oracle",
                "outer_ksp",
                "recovery",
                "top",
                "full_hybrid",
                "response_packet",
                "exact_output_vector_load",
            }.issubset(set(raw["forbidden_routes"]))
            and run["exact_output_vectors_loaded"] == 0
            and run["qep_calls"] == 0
            and run["pde_solve"] == "not_run"
        )
    except (KeyError, TypeError, ValueError):
        return False


def _representation_pass(raw: Mapping[str, Any]) -> bool:
    try:
        reports = raw["groups"]
        derived = []
        for item, expected_rows, expected_span in zip(
            reports, EXPECTED_GLOBAL_ROWS, EXPECTED_SPANS, strict=True
        ):
            local = item["local"]
            local_errors = (
                local["U_relative_error"],
                local["V_relative_error"],
                local["max_relative_error"],
            )
            local_pass = all(
                _finite(error) and float(error) <= 1.0e-12 for error in local_errors
            )
            collective_pass = (
                _finite(item["collective_max_relative_error"])
                and float(item["collective_max_relative_error"]) <= 1.0e-12
            )
            derived.append((expected_rows, expected_span, local_pass, collective_pass))
        return bool(
            raw["basis_global_replicated"] is False
            and raw["fe_numeric_allgather"] is False
            and len(reports) == 3
            and [item["group"] for item in reports] == [0, 1, 2]
            and all(
                item["global_row_count"] == expected_rows
                and item["span_size"] == expected_span
                and local_pass
                and collective_pass
                for item, (
                    expected_rows,
                    expected_span,
                    local_pass,
                    collective_pass,
                ) in zip(reports, derived, strict=True)
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _inventory_and_lifecycle_pass(raw: Mapping[str, Any]) -> bool:
    try:
        inventory = raw["factor_inventory"]
        projected = raw["projected_diagnostics"]
        lifecycle = raw["lifecycle"]
        after = lifecycle["worker_cleanup"]["factor_owner"]["after"]
        ready = lifecycle["worker_cleanup"]["factor_owner"]["ready"]
        return bool(
            inventory["factor_count_ready"] == 3
            and inventory["exact_interface_oracle_factor_count"] == 0
            and inventory["full_side_exact_factor_count"] == 0
            and inventory["global_direct_factor_count"] == 0
            and inventory["nested_ksp_count"] == 0
            and inventory["oracle_only"] is True
            and inventory["scalable_candidate"] is False
            and projected["projected_factor_count_ready"] == 3
            and projected["scalar_base_factor_count"] == 3
            and projected["projected_inverse_factor_count"] == 3
            and projected["basis_global_replicated"] is False
            and projected["fe_numeric_allgather"] is False
            and projected["exact_interface_oracle_factor_count"] == 0
            and projected["full_side_exact_factor_count"] == 0
            and projected["global_direct_factor_count"] == 0
            and projected["nested_ksp_count"] == 0
            and projected["oracle_only"] is True
            and projected["scalable_candidate"] is False
            and lifecycle["factor_count_ready"] == 3
            and lifecycle["factor_count_after_cleanup"] == 0
            and lifecycle["projected_inverse_count_after_cleanup"] == 0
            and lifecycle["simultaneous_factor_count_max"] == 3
            and lifecycle["action_destroyed"] is True
            and lifecycle["factor_destroyed"] is True
            and ready["factor_count_ready"] == 3
            and ready["auxiliary_owner_count"] == 3
            and after["factor_count_after_cleanup"] == 0
            and after["auxiliary_owner_count"] == 0
            and after["destroyed"] is True
        )
    except (KeyError, TypeError, ValueError):
        return False


def _one_apply_pass(raw: Mapping[str, Any]) -> bool:
    try:
        audit = raw["one_apply"]
        labels = list(TASK040_LEVEL_A_SOURCE_LABELS)
        reports = audit["reports"]
        if [report["label"] for report in reports] != labels:
            return False
        if len(reports) != 6:
            return False
        for report in reports:
            if (
                not all(
                    _finite(report.get(field))
                    for field in (
                        "source_norm",
                        "output_norm",
                        "true_residual_norm",
                        "repeat_error",
                    )
                )
                or report.get("finite") is not True
            ):
                return False
        physical = reports[0]
        physical_pass = bool(
            physical["physical_zero"] is True
            and physical["source_norm"] <= 1.0e-13
            and physical["output_norm"] <= 1.0e-13
        )
        mandatory_residual_pass = all(
            _finite(report.get("true_residual_relative")) for report in reports[1:]
        )
        repeat_pass = all(report["repeat_error"] <= 1.0e-10 for report in reports)
        identity = audit["action_identity"]
        identity_pass = all(
            (
                identity["carrier"] == "petsc_vecscatter",
                identity["global_numpy_copy"] is False,
                identity["subdomain_vectors_global_numpy_copy"] is False,
                identity["restriction_prolongation_pass"] is True,
                identity["bare_operator_unchanged"] is True,
            )
        )
        gate = audit["gate"]
        linearity_pass = (
            _finite(gate["linearity_relative_error"])
            and gate["linearity_relative_error"] <= 1.0e-10
        )
        inventory = audit["factor_inventory"]
        inventory_pass = all(
            (
                inventory["observed"] is True,
                inventory["factor_count_ready"] == 3,
                inventory["cross_section_factor_count_ready"] == 3,
                inventory["oracle_only"] is True,
                inventory["scalable_candidate"] is False,
                inventory["full_side_exact_factor_count"] == 0,
                inventory["global_direct_factor_count"] == 0,
                inventory["nested_ksp_count"] == 0,
            )
        )
        counts_pass = all(
            (
                audit["formal_source_apply_count"] == 6,
                audit["repeat_audit_apply_count"] == 6,
                audit["linearity_audit_apply_count"] == 1,
                audit["action_apply_count_delta"] == 13,
            )
        )
        return bool(
            physical_pass
            and mandatory_residual_pass
            and repeat_pass
            and identity_pass
            and linearity_pass
            and inventory_pass
            and counts_pass
        )
    except (KeyError, TypeError, ValueError):
        return False


def _checkpoint_value(record: Mapping[str, Any]) -> float | None:
    value = record.get("true_residual_relative")
    return float(value) if _finite(value) else None


def _preferred_checkpoint(
    phase1: Mapping[str, Any], phase2: Mapping[str, Any], labels: list[str]
) -> int | None:
    for checkpoint in ("4", "8", "16"):
        if phase1:
            values = {
                label: _checkpoint_value(phase1[label]["checkpoints"][checkpoint])
                for label in labels
            }
            if all(
                value is not None and value <= 1.0e-2 for value in values.values()
            ) and all(
                values[label] is not None and values[label] <= 1.0e-3
                for label in PREFERRED_LABELS
            ):
                return int(checkpoint)
    if phase2:
        values = {
            label: _checkpoint_value(phase2[label]["checkpoints"]["32"])
            for label in labels
        }
        if all(
            value is not None and value <= 1.0e-2 for value in values.values()
        ) and all(
            values[label] is not None and values[label] <= 1.0e-3
            for label in PREFERRED_LABELS
        ):
            return 32
    return None


def _screen_checks(raw: Mapping[str, Any]) -> dict[str, Any]:
    labels = list(TASK040_LEVEL_A_SOURCE_LABELS[1:])

    def contract_failure() -> dict[str, Any]:
        return {
            "contract_pass": False,
            "numerical_pass": False,
            "failure_classification": "IMPLEMENTATION_FAILURE",
        }

    try:
        screen = raw["fgmres_screen"]
        phase1 = screen["phase1"]
        phase2 = screen["phase2"]
        if (
            screen.get("schema") != "task040.v1_1.right_fgmres_batch.v1"
            or list(screen["labels"]) != labels
            or set(phase1) != set(labels)
        ):
            return contract_failure()
        if phase2 and set(phase2) != set(labels):
            return contract_failure()
        expected1 = {"0", "4", "8", "16"}
        expected2 = expected1 | {"32"}
        for phase, expected, max_it in (
            (phase1, expected1, 16),
            (phase2, expected2, 32),
        ):
            if not phase:
                continue
            for label in labels:
                item = phase[label]
                if set(item["checkpoints"]) != expected:
                    return contract_failure()
                if not all(
                    _finite(item["checkpoints"][key]["true_residual_relative"])
                    and item["checkpoints"][key]["finite"] is True
                    for key in expected
                ):
                    return contract_failure()
                if item["checkpoints"]["0"]["true_residual_relative"] != 1.0:
                    return contract_failure()
                if item["max_it"] != max_it:
                    return contract_failure()
                if item["restart"] != 32 or item["shared_ksp"] is not True:
                    return contract_failure()
                if (
                    item["zero_initial_guess"] is not True
                    or item["zero_initial_guess_count"] != 1
                ):
                    return contract_failure()
                if item["pc_side"] != "right" or item["ksp_breakdown"] is not False:
                    return contract_failure()
                if item["true_residual_matvec_count"] != len(expected) - 1:
                    return contract_failure()
        phase1_first = _preferred_checkpoint(phase1, {}, labels)
        r8 = [_checkpoint_value(phase1[label]["checkpoints"]["8"]) for label in labels]
        r16 = [
            _checkpoint_value(phase1[label]["checkpoints"]["16"]) for label in labels
        ]
        trend = all(
            a is not None and b is not None and b <= a * 10 ** (-0.25)
            for a, b in zip(r8, r16, strict=True)
        )
        boundary = screen["resource_at_phase_boundary"]
        boundary_pass = bool(
            _finite(boundary["rss_bytes"])
            and float(boundary["rss_bytes"]) < RESOURCE_LIMIT_BYTES
            and boundary["swap_bytes"] == 0
            and boundary["all_status_readable"] is True
        )
        phase1_finite = all(value is not None for value in r16)
        all_five_r16_ge_0p9 = bool(r16) and all(value >= 0.9 for value in r16)
        derived_authorized = bool(
            phase1_first is None
            and phase1_finite
            and trend
            and boundary_pass
            and not all_five_r16_ge_0p9
        )
        first = phase1_first
        if first is None and phase2:
            first = _preferred_checkpoint({}, phase2, labels)
        contract = bool(
            screen["ksp_setup_count"] == 1
            and screen["ksp_destroy_count"] == 1
            and screen["ksp_destroyed"] is True
            and screen["single_right_pc_setup"] is True
            and screen["zero_initial_guess_all_rhs"] is True
            and screen["stop_on_frozen_gate"] is True
            and screen["conditional_32_authorized"] is derived_authorized
            and (bool(phase2) is derived_authorized)
            and raw.get("first_preferred_checkpoint") == first
        )
        return {
            "contract_pass": contract,
            "numerical_pass": first is not None,
            "first_preferred_checkpoint": first,
            "conditional_32_authorized": derived_authorized,
            "phase1_trend_pass": trend,
            "all_five_r16_ge_0p9": all_five_r16_ge_0p9,
            "boundary_resource_pass": boundary_pass,
            "failure_classification": (
                "IMPLEMENTATION_FAILURE" if not contract else None
            ),
        }
    except (KeyError, TypeError, ValueError):
        return contract_failure()


def _watchdog_pass(
    run: Mapping[str, Any], watchdog: Mapping[str, Any], run_summary_sha256: str
) -> bool:
    try:
        return bool(
            watchdog["method"] == TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD
            and watchdog["source_sha"] == run["source_sha"]
            and watchdog["hard_stop_bytes"] == RESOURCE_LIMIT_BYTES
            and watchdog["termination_reason"] == "natural_exit"
            and watchdog["return_code"] == 0
            and watchdog["run_summary_present"] is True
            and watchdog["run_summary_sha256"] == run_summary_sha256
            and watchdog["all_status_readable"] is True
            and watchdog["sample_count"] > 0
            and watchdog["swap_authority_readable"] is True
            and watchdog["peak_swap_bytes"] == 0
            and watchdog["peak_dedicated_cgroup_swap_bytes"] == 0
            and watchdog["peak_rss_bytes"] < RESOURCE_LIMIT_BYTES
        )
    except (KeyError, TypeError, ValueError):
        return False


def _timeline_resource_audit(
    run: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    timeline_rows: Sequence[Mapping[str, Any]] | None,
    *,
    watchdog_raw_pass: bool,
    timeline_sha256: str | None,
    run_summary_sha256: str,
) -> dict[str, Any]:
    raw_status = watchdog.get("all_status_readable")
    raw_swap_status = watchdog.get("swap_authority_readable")
    base = {
        "available": timeline_rows is not None,
        "applicable": False,
        "pass": False,
        "raw_summary_all_status_readable": raw_status,
        "raw_summary_swap_authority_readable": raw_swap_status,
        "raw_sample_count": watchdog.get("sample_count"),
        "raw_peak_rss_bytes": watchdog.get("peak_rss_bytes"),
        "excluded_terminal_teardown_count": 0,
        "authoritative_sample_count": 0,
        "derived_all_status_readable": False,
        "derived_swap_authority_readable": False,
        "derived_peak_rss_bytes": 0,
        "derived_peak_swap_bytes": 0,
        "derived_peak_dedicated_cgroup_swap_bytes": 0,
        "timeline_sha256": timeline_sha256,
        "timeline_hash_bound": False,
        "count_binding_pass": False,
    }
    if watchdog_raw_pass or raw_status is not False or raw_swap_status is not False:
        return base
    base["applicable"] = True
    if timeline_rows is None:
        return base
    expected_timeline_sha = watchdog.get("artifact_hashes", {}).get(
        "process_tree_samples.jsonl"
    )
    base["timeline_hash_bound"] = bool(
        isinstance(timeline_sha256, str)
        and isinstance(expected_timeline_sha, str)
        and timeline_sha256 == expected_timeline_sha
    )
    rows = list(timeline_rows)
    if not rows or not base["timeline_hash_bound"]:
        return base
    if watchdog.get("sample_count") != len(rows):
        return base
    if any(
        field in row
        for row in rows
        for field in (
            "authoritative_sample",
            "terminal_teardown_excluded",
            "sample_process_alive_before",
            "sample_process_alive_after",
            "post_sample_return_code",
        )
    ):
        return base
    last = rows[-1]
    try:
        last_authority = last["resource_authority"]
        last_process_tree = last_authority["process_tree"]
        last_job_cgroup = last_authority.get("job_cgroup", {})
        last_ok = (
            last.get("stage") == "cleanup"
            and last.get("stage_status") == "complete"
            and last_process_tree["pids"]
            and last_process_tree["all_status_readable"] is False
            and last.get("swap_bytes") == 0
            and last_process_tree["swap_bytes"] == 0
            and (
                not last_job_cgroup.get("dedicated_job_cgroup")
                or last_job_cgroup.get("swap_current_bytes") == 0
            )
        )
    except (KeyError, TypeError, ValueError):
        return base
    if not last_ok:
        return base
    base["excluded_terminal_teardown_count"] = 1
    authoritative_rows = rows[:-1]
    if not authoritative_rows:
        return base
    peak_rss = 0
    peak_swap = 0
    peak_dedicated_swap = 0
    for row in authoritative_rows:
        try:
            authority = row["resource_authority"]
            process_tree = authority["process_tree"]
            job_cgroup = authority.get("job_cgroup", {})
            rss_bytes = row["rss_bytes"]
            swap_bytes = row["swap_bytes"]
            process_swap = process_tree["swap_bytes"]
            if (
                not process_tree["pids"]
                or process_tree["all_status_readable"] is not True
                or not _finite(rss_bytes)
                or float(rss_bytes) < 0
                or swap_bytes != 0
                or process_swap != 0
            ):
                return base
            peak_rss = max(peak_rss, int(rss_bytes))
            peak_swap = max(peak_swap, int(swap_bytes), int(process_swap))
            if job_cgroup.get("dedicated_job_cgroup"):
                dedicated_swap = job_cgroup.get("swap_current_bytes")
                if dedicated_swap is None:
                    return base
                peak_dedicated_swap = max(peak_dedicated_swap, int(dedicated_swap))
                if dedicated_swap != 0:
                    return base
        except (KeyError, TypeError, ValueError):
            return base
    derived_swap_readable = True
    base.update(
        {
            "authoritative_sample_count": len(authoritative_rows),
            "derived_all_status_readable": True,
            "derived_swap_authority_readable": derived_swap_readable,
            "derived_peak_rss_bytes": peak_rss,
            "derived_peak_swap_bytes": peak_swap,
            "derived_peak_dedicated_cgroup_swap_bytes": peak_dedicated_swap,
        }
    )
    excluded_count = int(base["excluded_terminal_teardown_count"])
    count_binding = watchdog.get("sample_count") == (
        len(authoritative_rows) + excluded_count
    )
    base["count_binding_pass"] = count_binding
    audited_watchdog = dict(watchdog)
    audited_watchdog.update(
        {
            "all_status_readable": True,
            "sample_count": len(authoritative_rows),
            "swap_authority_readable": derived_swap_readable,
            "peak_rss_bytes": peak_rss,
            "peak_swap_bytes": peak_swap,
            "peak_dedicated_cgroup_swap_bytes": peak_dedicated_swap,
        }
    )
    summary_matches = (
        watchdog.get("peak_rss_bytes") == peak_rss
        and watchdog.get("peak_swap_bytes") == peak_swap
        and watchdog.get("peak_dedicated_cgroup_swap_bytes") == peak_dedicated_swap
    )
    run_hash_valid = (
        watchdog.get("run_summary_present") is True
        and bool(run_summary_sha256)
        and watchdog.get("run_summary_sha256") == run_summary_sha256
    )
    base.update(
        {
            "summary_peak_matches_derived": summary_matches,
            "run_summary_hash_valid": run_hash_valid,
            "pass": bool(
                summary_matches
                and run_hash_valid
                and base["timeline_hash_bound"]
                and count_binding
                and _watchdog_pass(run, audited_watchdog, run_summary_sha256)
                and peak_rss < RESOURCE_LIMIT_BYTES
                and peak_swap == 0
                and peak_dedicated_swap == 0
            ),
        }
    )
    return base


def _source_binding_pass(
    run: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    expected_source_sha: str | None,
) -> bool:
    try:
        source = run["source_sha"]
        watchdog_source = watchdog["source_sha"]
        source_shape_pass = all(
            isinstance(value, str)
            and len(value) == 40
            and all(character in "0123456789abcdef" for character in value)
            for value in (source, watchdog_source)
        )
        return bool(
            source_shape_pass
            and source == watchdog_source
            and (
                expected_source_sha is None
                or (
                    isinstance(expected_source_sha, str)
                    and len(expected_source_sha) == 40
                    and all(
                        character in "0123456789abcdef"
                        for character in expected_source_sha
                    )
                    and source == expected_source_sha
                )
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def recompute_v2_consumer(
    run_summary: Mapping[str, Any],
    watchdog_summary: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    *,
    manifest_sha256: str = TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
    run_summary_sha256: str = "",
    expected_source_sha: str | None = None,
    timeline_rows: Sequence[Mapping[str, Any]] | None = None,
    timeline_sha256: str | None = None,
) -> dict[str, Any]:
    """Recompute V2-B evidence without reading worker status/pass fields."""

    raw = run_summary.get("interface_packet_raw", {})
    if not isinstance(raw, Mapping):
        raw = {}
    screen = _screen_checks(raw)
    watchdog_raw_pass = _watchdog_pass(
        run_summary, watchdog_summary, run_summary_sha256
    )
    timeline_audit = _timeline_resource_audit(
        run_summary,
        watchdog_summary,
        timeline_rows,
        timeline_sha256=timeline_sha256,
        watchdog_raw_pass=watchdog_raw_pass,
        run_summary_sha256=run_summary_sha256,
    )
    watchdog_pass = watchdog_raw_pass
    if timeline_audit["applicable"]:
        watchdog_pass = timeline_audit["pass"] is True
    checks = {
        "identity": _identity_pass(run_summary, raw, packet_manifest, manifest_sha256),
        "source_binding": _source_binding_pass(
            run_summary, watchdog_summary, expected_source_sha
        ),
        "representation": _representation_pass(raw),
        "inventory_lifecycle": _inventory_and_lifecycle_pass(raw),
        "one_apply_implementation": _one_apply_pass(raw),
        "fgmres_contract": screen["contract_pass"],
        "watchdog": watchdog_pass,
        "watchdog_raw": watchdog_raw_pass,
    }
    identity_pass = (
        checks["identity"] and checks["representation"] and checks["source_binding"]
    )
    implementation_pass = all(
        checks[name]
        for name in (
            "inventory_lifecycle",
            "one_apply_implementation",
            "fgmres_contract",
        )
    )
    resource_pass = checks["watchdog"] and screen.get("boundary_resource_pass", False)
    if not identity_pass:
        classification = "PACKET_COORDINATE_IDENTITY_FAIL"
    elif not implementation_pass:
        classification = "IMPLEMENTATION_FAILURE"
    elif not resource_pass:
        classification = "PROJECTED_CONSUMER_RESOURCE_FAIL"
    elif screen.get("numerical_pass") is True:
        classification = "PROJECTED_EXACT_TRANSMISSION_PASS"
    else:
        classification = "THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT"
    return {
        "schema": "task040.v2.consumer.recomputed.v1",
        "checks": checks,
        "derived": screen,
        "evidence_valid": identity_pass and implementation_pass,
        "resource_pass": resource_pass,
        "numerical_pass": screen.get("numerical_pass") is True,
        "classification": classification,
        "gate_pass": classification == "PROJECTED_EXACT_TRANSMISSION_PASS",
        "legacy_lifecycle_audit": timeline_audit,
    }


def check_v2_consumer(
    run_dir: str | Path,
    packet_root: str | Path,
    *,
    expected_source_sha: str,
    watchdog_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read a consumer run and recompute its independent V2-B result."""

    run_directory = Path(run_dir)
    run_path = run_directory / "worker" / "run_summary.json"
    watchdog_path = Path(
        watchdog_summary_path or run_directory / "watchdog_summary.json"
    )
    timeline_path = run_directory / "process_tree_samples.jsonl"
    manifest_path = Path(packet_root) / "manifest.json"
    run_summary = json.loads(run_path.read_text(encoding="utf-8"))
    packet_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    watchdog_summary = json.loads(watchdog_path.read_text(encoding="utf-8"))
    timeline_rows: list[dict[str, Any]] | None = None
    timeline_sha256: str | None = None
    if timeline_path.is_file():
        timeline_rows = []
        timeline_sha256 = _sha256(timeline_path)
        try:
            for line in timeline_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    timeline_rows.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            timeline_rows = []
    return recompute_v2_consumer(
        run_summary,
        watchdog_summary,
        packet_manifest,
        manifest_sha256=_sha256(manifest_path),
        run_summary_sha256=_sha256(run_path),
        expected_source_sha=expected_source_sha,
        timeline_rows=timeline_rows,
        timeline_sha256=timeline_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--watchdog-summary")
    parser.add_argument("--expected-source-sha", required=True)
    args = parser.parse_args(argv)
    result = check_v2_consumer(
        args.run_root,
        args.packet_root,
        expected_source_sha=args.expected_source_sha,
        watchdog_summary_path=args.watchdog_summary,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
