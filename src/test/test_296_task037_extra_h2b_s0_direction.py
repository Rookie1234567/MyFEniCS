from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task037_extra_h2b as runner
from src.solvers.hcurl_h2b_block_smoother import (
    build_h2b_constrained_block_smoother,
)


class _FakeStore:
    def __init__(self, cells: tuple[tuple[int, ...], ...]) -> None:
        self.cells = tuple(
            SimpleNamespace(class_id=0, independent_global_rows=np.asarray(rows))
            for rows in cells
        )
        self.audit = {
            "factor_plus_metadata_bytes": 128,
            "unique_factor_count": 1,
            "per_cell_factor_count": 0,
            "slab_factor_count": 0,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "schur_materialized": False,
            "factor_plus_metadata_basis": "synthetic",
        }

    def solve(self, class_id: int, rhs: np.ndarray) -> np.ndarray:
        assert class_id == 0
        return np.ascontiguousarray(rhs, dtype=np.complex128).copy()


def _smoother(action):
    return build_h2b_constrained_block_smoother(
        _FakeStore(((0, 1), (1, 2), (2, 3))),
        global_row_count=5,
        owned_slave_identity_rows=np.asarray((4,), dtype=np.int64),
        action=action,
        task037_extra_h2b=True,
    )


def test_s0_modes_have_fixed_operational_counts_and_shared_additive_rhs():
    rhs = np.asarray((1.0 + 0.2j, -0.4 + 0.8j, 0.7 - 0.1j, 0.2 + 0.3j, 1.5 - 0.4j))
    for strategy, expected in (("additive", 1), ("forward", 2), ("symmetric", 4)):
        calls: list[np.ndarray] = []

        def action(source, target):
            assert source[4] == 0.0
            calls.append(source.copy())
            target[:] = source

        smoother = _smoother(action)
        first = smoother.apply_s0(rhs, strategy)
        assert smoother.audit["last_strategy"] == strategy
        assert smoother.audit["action_count"] == expected
        assert smoother.audit["expected_action_count"] == expected
        assert len(calls) == expected
        if strategy == "additive":
            expected_delta = np.asarray(
                (rhs[0], rhs[1], rhs[2], rhs[3], 0.0j),
                dtype=np.complex128,
            )
            assert np.array_equal(calls[0], expected_delta)
        assert first[4] == rhs[4]


def _source_record(label: str, strategy: str) -> dict[str, object]:
    rhs = np.asarray((1.0 + 0.0j, -2.0 + 0.5j, 0.25 - 0.75j))
    correction = rhs / 2.0
    residual = -rhs
    q = 2.0 * rhs
    result = runner._s0_oracle_metrics(
        rhs,
        correction,
        residual,
        q,
        repeat_correction=correction,
        repeat_residual=residual,
        repeat_diagnostic_action=q,
        operational_action_count=runner.H2B_S0_OPERATIONAL_ACTION_COUNTS[strategy],
        diagnostic_action_count=2,
    )
    result.update(
        {
            "label": label,
            "definition": runner.H2B_SOURCE_DEFINITIONS[label],
            "definition_sha256": runner._source_definition_sha(label),
            "vector_sha256": runner._s0_array_sha(rhs),
            "apply_seconds": [1.0, 1.1],
            "diagnostic_action_seconds": [0.2, 0.3],
            "wall_seconds": 2.6,
            "rho_norm_scope": "all_fullspace_rows",
            "external_slave_mask": False,
        }
    )
    return result


def _s0_payload() -> dict[str, object]:
    combinations = [
        {
            "strategy": strategy,
            "wall_seconds": float(index + 1),
            "sources": [
                _source_record(label, strategy)
                for label in runner.H2B_SOURCE_LABELS
            ],
        }
        for index, strategy in enumerate(runner.H2B_S0_STRATEGIES)
    ]
    return {
        "scope": runner._s0_scope(),
        "identity": runner._fixed_identity(),
        "p6": {
            "global_cells": 252,
            "local_cells": 252,
            "local_nloc": 882,
            "global_rows": 173802,
            "constraint_count": 9210,
        },
        "factor": {
            "class_count": 24,
            "cell_count": 252,
            "unique_factor_count": 16,
            "factor_plus_metadata_bytes": 201933812,
            "finite": True,
            "deterministic": True,
        },
        "combinations": combinations,
        "resource": {
            "process_tree_peak_rss_bytes": 900_000_000,
            "process_tree_swap_bytes": 0,
        },
    }


def test_s0_oracle_recomputes_rho_and_selects_additive():
    payload = _s0_payload()
    checked = runner._s0_check_payload(payload)
    assert checked["pass"] is True
    assert checked["status"] == "pass"
    assert checked["measurements"]["selection"]["selected_strategy"] == "additive"
    assert checked["measurements"]["selection"]["route"] == "H2B-K"
    assert checked["measurements"]["combinations"][0]["sources"][0]["rho_star"] <= 1.0e-14

    broken = {
        **payload,
        "combinations": [
            {
                **combination,
                "sources": [
                    {**source, "scaled_residual_norm": 2.0 * source["r_norm"]}
                    for source in combination["sources"]
                ],
            }
            for combination in payload["combinations"]
        ],
    }
    failed = runner._s0_check_payload(broken)
    assert failed["pass"] is False
    assert failed["status"] == "STOP_ANOMALY"
    assert "combinations_valid" in failed["problems"]
    assert failed["measurements"] is None


def _set_rhos(combinations, values):
    return [
        {
            **combination,
            "sources": [
                {
                    **source,
                    "scaled_residual_norm": source["r_norm"] * values[source["label"]],
                    "rho_star": values[source["label"]],
                }
                for source in combination["sources"]
            ],
        }
        for combination in combinations
    ]


def test_s0_validity_is_separate_from_direction_qualification():
    values = {
        "gradient-dominated": 0.96,
        "curl-dominated": 0.96,
        "mixed": 0.86,
        "checkerboard/high-frequency": 0.71,
        "physical-RHS-like": 0.96,
    }
    payload = _s0_payload()
    payload["combinations"] = [
        payload["combinations"][0],
        *_set_rhos(payload["combinations"][1:], values),
    ]
    checked = runner._s0_check_payload(payload)
    assert checked["pass"] is True
    assert checked["route"] == "H2B-K"
    assert checked["s0_direction_gate_pass"] is True
    assert checked["measurements"]["selection"]["selected_strategy"] == "additive"
    assert checked["measurements"]["selection"]["valid_strategies"] == list(runner.H2B_S0_STRATEGIES)
    assert checked["measurements"]["selection"]["passing_strategies"] == ["additive"]

    payload = _s0_payload()
    payload["combinations"] = _set_rhos(payload["combinations"], values)
    checked = runner._s0_check_payload(payload)
    assert checked["pass"] is True
    assert checked["route"] == "H2B-P"
    assert checked["s0_direction_gate_pass"] is False
    assert len(checked["measurements"]["combinations"]) == 3
    assert checked["measurements"]["selection"]["passing_strategies"] == []


@pytest.mark.parametrize(
    "resource",
    [
        {"process_tree_peak_rss_bytes": runner.H2B_S0_RSS_LIMIT_BYTES, "process_tree_swap_bytes": 0},
        {"process_tree_peak_rss_bytes": 900_000_000, "process_tree_swap_bytes": 1},
    ],
)
def test_s0_resource_stop_never_routes_to_patch(resource):
    payload = _s0_payload()
    payload["resource"] = resource
    checked = runner._s0_check_payload(payload)
    assert checked["pass"] is False
    assert checked["status"] == "STOP_RESOURCE"
    assert checked["route"] == "STOP_RESOURCE"
    assert checked["failure_measurements"]["resource"] == resource


def test_s0_oracle_accepts_negative_imaginary_inner_product():
    rhs = np.asarray((1.0 - 1.0j,))
    q = np.asarray((1.0 + 0.0j,))
    metrics = runner._s0_oracle_metrics(
        rhs,
        np.zeros_like(rhs),
        rhs - q,
        q,
        repeat_correction=np.zeros_like(rhs),
        repeat_residual=rhs - q,
        repeat_diagnostic_action=q,
        operational_action_count=1,
        diagnostic_action_count=2,
    )
    metrics.update(
        {
            "label": "gradient-dominated",
            "definition": runner.H2B_SOURCE_DEFINITIONS["gradient-dominated"],
            "definition_sha256": runner._source_definition_sha("gradient-dominated"),
            "vector_sha256": runner._s0_array_sha(rhs),
            "apply_seconds": [1.0, 1.1],
            "diagnostic_action_seconds": [0.2, 0.3],
            "wall_seconds": 2.6,
            "rho_norm_scope": "all_fullspace_rows",
            "external_slave_mask": False,
        }
    )
    assert metrics["omega_imag"] < 0.0
    assert metrics["rho_star"] <= metrics["rho_unit"]
    assert runner._s0_source_valid(metrics["label"], metrics) is True


def test_s0_zero_diagnostic_action_fails_closed():
    values = np.ones(3, dtype=np.complex128)
    with pytest.raises(ValueError, match="diagnostic action norm"):
        runner._s0_oracle_metrics(
            values,
            values,
            values,
            np.zeros_like(values),
            repeat_correction=values,
            repeat_residual=values,
            repeat_diagnostic_action=np.zeros_like(values),
            operational_action_count=1,
            diagnostic_action_count=2,
        )


def test_s0_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="additive, forward, or symmetric"):
        _smoother(lambda source, target: target.__setitem__(slice(None), source)).apply_s0(
            np.ones(5, dtype=np.complex128), "damped"
        )


def test_s0_apply_matches_legacy_symmetric_apply():
    rhs = np.asarray((1.0 + 0.2j, -0.4 + 0.8j, 0.7 - 0.1j, 0.2 + 0.3j, 1.5 - 0.4j))

    def action(source, target):
        target[:] = source

    legacy = _smoother(action)
    s0 = _smoother(action)
    assert np.array_equal(legacy.apply(rhs), s0.apply_s0(rhs, "symmetric"))
    assert np.array_equal(legacy.last_residual, s0.last_residual)


def test_s0_events_and_authority_fields_are_fail_closed(tmp_path):
    path = tmp_path / "progress.jsonl"
    path.write_text(
        "\n".join(
            runner.json.dumps(
                {"schema": runner.H2B_PROGRESS_SCHEMA, "phase": "s0", "event": event}
            )
            for event in runner.H2B_S0_EVENTS
        )
        + "\n",
        encoding="utf-8",
    )
    assert runner._progress_events(path, "s0") == list(runner.H2B_S0_EVENTS)
    payload = _s0_payload()
    del payload["combinations"][0]["sources"][0]["vector_sha256"]
    failed = runner._s0_check_payload(payload)
    assert failed["status"] == "STOP_ANOMALY"
    assert "combinations_valid" in failed["problems"]
    assert runner._forms_match({}, {}, tmp_path) is False

    scope_failed = _s0_payload()
    scope_failed["combinations"][0]["sources"][0]["rho_norm_scope"] = "masked_rows"
    assert runner._s0_check_payload(scope_failed)["status"] == "STOP_ANOMALY"
    mask_failed = _s0_payload()
    mask_failed["combinations"][0]["sources"][0]["external_slave_mask"] = True
    assert runner._s0_check_payload(mask_failed)["status"] == "STOP_ANOMALY"
    eta_failed = _s0_payload()
    eta_failed["combinations"][0]["sources"][0]["eta"] = 1.0 + 1.0e-6
    assert runner._s0_check_payload(eta_failed)["status"] == "STOP_ANOMALY"
    rho_failed = _s0_payload()
    rho_source = rho_failed["combinations"][0]["sources"][0]
    rho_source["scaled_residual_norm"] = (rho_source["rho_unit"] + 0.1) * rho_source["r_norm"]
    rho_source["rho_star"] = rho_source["rho_unit"] + 0.1
    assert runner._s0_check_payload(rho_failed)["status"] == "STOP_ANOMALY"
    wall_failed = _s0_payload()
    wall_failed["combinations"][0]["wall_seconds"] = 0.0
    assert runner._s0_check_payload(wall_failed)["status"] == "STOP_ANOMALY"
    priority_failed = _s0_payload()
    priority_failed["resource"] = {
        "process_tree_peak_rss_bytes": runner.H2B_S0_RSS_LIMIT_BYTES,
        "process_tree_swap_bytes": 0,
    }
    del priority_failed["combinations"][0]["sources"][0]["vector_sha256"]
    assert runner._s0_check_payload(priority_failed)["status"] == "STOP_ANOMALY"


def test_s0_campaign_peak_is_projected_without_source_window_claims():
    payload = _s0_payload()
    resource = payload["resource"]
    projected = runner._s0_project_campaign_sources(payload["combinations"], resource)
    assert len(projected) == len(runner.H2B_S0_STRATEGIES)
    for combination in projected:
        for source in combination["sources"]:
            assert source["process_tree_peak_rss_bytes"] == resource["process_tree_peak_rss_bytes"]
            assert source["process_tree_swap_bytes"] == resource["process_tree_swap_bytes"]
            assert source["process_tree_peak_scope"] == "whole_s0_online_campaign"


def test_s0_watchdog_artifact_hashes_are_bound_to_disk(tmp_path):
    for name in runner.H2B_S0_ARTIFACT_NAMES:
        path = tmp_path / name
        path.write_bytes(name.encode("utf-8"))
    recorded = {
        name: runner._artifact(tmp_path, name) for name in runner.H2B_S0_ARTIFACT_NAMES
    }
    assert runner._s0_artifacts_match(tmp_path, recorded) is True
    (tmp_path / "s0_summary.json").write_bytes(b"changed")
    assert runner._s0_artifacts_match(tmp_path, recorded) is False


@pytest.mark.parametrize(
    ("reason", "peak", "swap", "expected"),
    [
        ("process_tree_rss_at_or_over_limit", runner.H2B_S0_RSS_LIMIT_BYTES, 0, "STOP_RESOURCE"),
        ("timeout", 900_000_000, 0, "STOP_ANOMALY"),
    ],
)
def test_s0_missing_summary_preserves_controlled_stop(tmp_path, monkeypatch, reason, peak, swap, expected):
    watchdog_path = tmp_path / "h2b_s0_watchdog_summary.json"
    watchdog_path.write_text("{}", encoding="utf-8")
    watchdog = runner._attach_evidence(
        {
            "schema": runner.H2B_S0_WATCHDOG_SCHEMA,
            "s0": {"return_code": 1, "termination": {"reason": reason}},
            "raw_artifacts": {"s0_summary.json": {"path": "s0_summary.json", "present": False}},
        }
    )
    monkeypatch.setattr(
        runner,
        "_timeline_metrics",
        lambda path, phase: {
            "live_sample_count": 3,
            "peak_rss_bytes": peak,
            "swap_bytes": swap,
        },
    )
    result = runner._s0_controlled_missing_summary(tmp_path, watchdog)
    assert result is not None
    assert result["status"] == expected
    assert result["measurements"] is None
    assert result["failure_measurements"]["termination_reason"] == reason
    assert result["failure_measurements"]["online_measurement_formed"] is False


def test_s0_fixed_commands_and_resource_boundary():
    assert runner.H2B_S0_TIMEOUT_SECONDS == 3600.0
    assert runner._s0_scope()["online_timeout_seconds"] == 3600.0
    command = runner._worker_command("/repo/.venv/bin/python", "s0-worker", "/tmp/s0")
    assert command == [
        "/repo/.venv/bin/python",
        "-m",
        "benchmarks.run_task037_extra_h2b",
        "s0-worker",
        "--run-dir",
        "/tmp/s0",
    ]
    with pytest.raises(ValueError, match="fixed"):
        runner._worker_command("/repo/.venv/bin/python", "s0-extra", "/tmp/s0")
    payload = _s0_payload()
    payload["resource"] = {
        "process_tree_peak_rss_bytes": runner.H2B_S0_RSS_LIMIT_BYTES,
        "process_tree_swap_bytes": 0,
    }
    checked = runner._s0_check_payload(payload)
    assert checked["pass"] is False
    assert checked["status"] == "STOP_RESOURCE"
