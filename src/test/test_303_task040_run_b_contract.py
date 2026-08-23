"""Pure raw/checker contracts for the Task040 Run-B path."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

import benchmarks.check_task040_v1_run_b as run_b_checker
from benchmarks.check_task040_v1_run_b import recompute_v1_2_gate
from benchmarks.check_task040_v1_run_b import recompute_v1_2_small_contractions
from benchmarks.task040_level_a import _v1_2_identity_pass
from benchmarks.task040_level_a import _v1_2_lower_mode_count
from benchmarks.task040_level_a import _v1_2_seed_interface_active_row


@pytest.fixture(autouse=True)
def _small_projected_span_contract(monkeypatch):
    monkeypatch.setattr(run_b_checker, "EXPECTED_SPAN_SIZES", (2, 2, 2))


def _pair(real: float, imag: float = 0.0) -> list[float]:
    return [real, imag]


def _matrix(size: int, value: float) -> list[list[list[float]]]:
    return [
        [_pair(value if row == column else 0.0) for column in range(size)]
        for row in range(size)
    ]


def _contractions() -> dict[str, list[float]]:
    return {
        "source_h_source": _pair(1.0),
        "scalar_h_scalar": _pair(1.0),
        "exact_h_exact": _pair(1.0),
        "projected_h_projected": _pair(1.0),
        "scalar_h_exact": _pair(1.0),
        "projected_h_exact": _pair(1.0),
    }


def _identity() -> dict[str, object]:
    manifest_path = Path(
        "benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/"
        "task040_v1_2_probe_manifest_v1.json"
    )
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    identity = dict(manifest["identity"])
    identity["probe_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    identity["upper_mode_key_sha256"] = (
        "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
    )
    identity["upper_beta_sha256"] = (
        "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
    )
    identity["lower_mode_key_sha256"] = (
        "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
    )
    identity["lower_resolved_mode_metadata_sha256"] = (
        run_b_checker.FROZEN_LOWER_RESOLVED_MODE_METADATA_SHA256
    )
    identity["lower_legacy_beta_metadata_sha256"] = (
        "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
    )
    identity["resolved_config_sha256"] = identity["exact_spool_resolved_config_sha256"]
    identity["spool_catalog_sha256"] = identity["exact_spool_catalog_sha256"]
    identity["selected_identity_physical_sha256"] = identity["physical_model_sha256"]
    identity["exact_output_identity_sha256"] = dict(
        manifest["physical_probes"]["exact_output_identity_sha256"]
    )
    return identity


def _probe(
    label: str, *, kind: str = "physical", group: int = 0, seed: int | None = None
) -> dict[str, object]:
    probe: dict[str, object] = {
        "label": label,
        "kind": kind,
        "group": group,
        "contractions": _contractions(),
    }
    if seed is not None:
        probe["seed"] = seed
    if kind == "complement":
        probe["YH_before_projection"] = [_pair(1.0), _pair(0.0)]
        probe["YH_after_projection"] = [_pair(0.0), _pair(0.0)]
    return probe


def _interface_probe(
    interface: str, group: int, kind: str, seed: int, interface_index: int
) -> dict[str, object]:
    probe = _probe(
        f"{interface}_{kind}_{seed}",
        kind=kind,
        group=group,
        seed=seed,
    )
    probe["interface"] = interface_index
    return probe


def _middle_cross_reports() -> list[dict[str, object]]:
    interface_rows = {
        "lower": (41, 7, 83),
        "upper": (5, 91, 12),
    }
    reports = []
    for interface, seeds in (
        ("lower", (1729, 1730, 3729, 3730)),
        ("upper", (2729, 2730, 4729, 4730)),
    ):
        for seed in seeds:
            kind = "modal_combination" if seed < 3700 else "complement"
            reports.append(
                {
                    "label": f"middle_{interface}_{kind}_{seed}",
                    "interface": interface,
                    "group": 1,
                    "source_group": 1,
                    "kind": kind,
                    "seed": seed,
                    "response": "middle_group1_schur",
                    "direction": "apply_group",
                    "source_norm": 1.0,
                    "middle_norm": 1.0,
                    "same_interface_norm": 0.8,
                    "cross_interface_norm": 0.6,
                    "total_norm": 1.0,
                    "partition_disjoint": True,
                    "partition_complete": True,
                    "cross_to_total": 0.6,
                    "finite": True,
                    "contractions": {
                        "source_h_source": _pair(1.0),
                        "middle_h_middle": _pair(1.0),
                        "source_h_middle": _pair(0.25),
                    },
                }
            )
            if kind == "complement":
                rows = interface_rows[interface]
                index = seed % len(rows)
                reports[-1].update(
                    {
                        "selected_active_row": rows[index],
                        "interface_row_index": index,
                        "interface_size": len(rows),
                        "interface_rows_global_order_sha256": hashlib.sha256(
                            np.asarray(rows, dtype=np.int64).tobytes()
                        ).hexdigest(),
                    }
                )
    return reports


def _middle_cross_identity() -> dict[str, dict[str, object]]:
    result = {}
    for interface, rows in (
        ("lower", (41, 7, 83)),
        ("upper", (5, 91, 12)),
    ):
        result[interface] = {
            "global_rows": list(rows),
            "size": len(rows),
            "sha256": hashlib.sha256(
                np.asarray(rows, dtype=np.int64).tobytes()
            ).hexdigest(),
        }
    return result


def _raw() -> dict[str, object]:
    labels = [
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    ]
    return {
        "identity_observed": _identity(),
        "basis_global_replicated": False,
        "fe_numeric_allgather": False,
        "probe_manifest_sha256": _identity()["probe_manifest_sha256"],
        "lower": {"mode_count": 296},
        "upper": {
            "mode_count": 480,
            "qep_calls": 0,
            "branch_authority": "positive/forward",
        },
        "exact_output_identity_sha256": _identity()["exact_output_identity_sha256"],
        "groups": [
            {
                "group": group,
                "span_size": run_b_checker.EXPECTED_SPAN_SIZES[group],
                "gamma_layout": {
                    "basis_global_replicated": False,
                    "fe_numeric_allgather": False,
                    **(
                        {
                            "global_size": 3,
                            "gamma_rows_global_order_sha256": (
                                _middle_cross_identity()["lower"]["sha256"]
                            ),
                        }
                        if group == 0
                        else {
                            "global_size": 3,
                            "gamma_rows_global_order_sha256": (
                                _middle_cross_identity()["upper"]["sha256"]
                            ),
                        }
                        if group == 2
                        else {}
                    ),
                },
                "projected_contractions": {
                    "gram": _matrix(2, 1.0),
                    "scalar": _matrix(2, 1.0),
                    "exact": _matrix(2, 2.0),
                },
            }
            for group in range(3)
        ],
        "probes": [_probe(label, group=group) for label in labels for group in range(3)]
        + [
            _interface_probe(interface, group, kind, seed, interface_index)
            for interface, group, interface_index in (
                ("lower", 0, 0),
                ("upper", 2, 1),
            )
            for kind, seeds in (
                (
                    "modal_combination",
                    (1729, 1730) if interface == "lower" else (2729, 2730),
                ),
                (
                    "complement",
                    (3729, 3730) if interface == "lower" else (4729, 4730),
                ),
            )
            for seed in seeds
        ],
        "incoming_neighbor_map": {
            "map": "block_diagonal_neighbor_transmission",
            "response": "apply_directed_neighbor",
            "probe_count": 8,
        },
        "middle_cross_interface_sampled_response": _middle_cross_reports(),
        "middle_cross_interface_identity": _middle_cross_identity(),
        "factor_inventory": {
            "ready": 3,
            "after": 0,
            "simultaneous_max": 3,
            "full_side": 0,
            "global_direct": 0,
            "nested_ksp": 0,
        },
        "lifecycle": {
            "exact_factor_count_ready": 3,
            "exact_factor_count_after_cleanup": 0,
            "action_destroyed": True,
            "factor_destroyed": True,
        },
        "exact_oracle_after_cleanup": {"destroyed": True},
        "resource_samples": [
            {
                "rss_bytes": 2**30,
                "swap_bytes": 0,
                "dedicated_cgroup_swap_bytes": 0,
                "readable": True,
            }
        ],
        "gate": {"pass": False},
        "status": "worker-status-is-not-authoritative",
    }


def _with_v1_3(raw: dict[str, object]) -> dict[str, object]:
    result = deepcopy(raw)
    labels = [
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    ]
    checkpoints = {
        str(iteration): {
            "reported_relative_residual": 1.0 if iteration == 0 else 5.0e-4,
            "true_residual_relative": 1.0 if iteration == 0 else 5.0e-4,
            "finite": True,
        }
        for iteration in (0, 4, 8, 16)
    }
    phase1 = {
        label: {
            "checkpoints": deepcopy(checkpoints),
            "max_it": 16,
            "zero_initial_guess": True,
            "zero_initial_guess_count": 1,
            "pc_side": "right",
            "ksp_breakdown": False,
            "restart": 32,
            "right_pc_apply_count": 3,
            "shared_ksp": True,
            "true_residual_matvec_count": 3,
        }
        for label in labels
    }
    reports = [
        {
            "label": "physical_side_rhs",
            "source_norm": 0.0,
            "output_norm": 0.0,
            "true_residual_relative": None,
            "repeat_error": 0.0,
            "finite": True,
            "physical_zero": True,
        }
    ] + [
        {
            "label": label,
            "source_norm": 1.0,
            "output_norm": 1.0,
            "true_residual_relative": 5.0e-4,
            "repeat_error": 0.0,
            "finite": True,
            "physical_zero": False,
        }
        for label in labels
    ]
    result["v1_3_one_apply"] = {
        "reports": reports,
        "scalar_contractions": {
            "labels": labels,
            "BHB": _matrix(5, 1.0),
            "BHY": _matrix(5, 1.0),
            "YHY": _matrix(5, 1.0),
        },
        "formal_source_apply_count": 6,
        "repeat_audit_apply_count": 6,
        "linearity_audit_apply_count": 1,
        "action_apply_count_delta": 13,
        "gate": {"linearity_relative_error": 0.0},
    }
    result["v1_3_screen"] = {
        "schema": "task040.v1_1.right_fgmres_batch.v1",
        "labels": labels,
        "phase1": phase1,
        "phase2": {},
        "resource_at_phase_boundary": {
            "rss_bytes": 2**30,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
        "ksp_setup_count": 1,
        "ksp_destroy_count": 1,
        "ksp_destroyed": True,
        "single_right_pc_setup": True,
        "zero_initial_guess_all_rhs": True,
        "right_pc_apply_count": 15,
        "phase1_frozen_gate": True,
        "stop_on_frozen_gate": True,
        "conditional_32_authorized": False,
    }
    result["v1_3_factor_inventory"] = {
        "factor_count_ready": 3,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "nested_ksp_count": 0,
    }
    result["lifecycle"]["worker_cleanup"] = {
        "factor_owner": {
            "ready": {"factor_count_ready": 3, "auxiliary_owner_count": 3},
            "after": {
                "factor_count_after_cleanup": 0,
                "auxiliary_owner_count": 0,
                "destroyed": True,
            },
        }
    }
    return result


def test_run_b_checker_recomputes_raw_and_ignores_worker_status() -> None:
    raw = _with_v1_3(_raw())
    first = recompute_v1_2_small_contractions(raw)
    raw["gate"]["pass"] = True
    raw["status"] = "fake-pass"
    second = recompute_v1_2_small_contractions(raw)
    assert second == first
    raw["probes"][0]["contractions"]["exact_h_exact"] = _pair(4.0)
    changed = recompute_v1_2_small_contractions(raw)
    assert changed["probes"][0]["original_scalar_exact_relative"] > 0.0


def test_run_b_middle_seed_uses_interface_row_identity() -> None:
    lower_rows = (41, 7, 83)
    upper_rows = (5, 91, 12)
    assert _v1_2_seed_interface_active_row(1, lower_rows) == 7
    assert _v1_2_seed_interface_active_row(1, upper_rows) == 91
    assert _v1_2_seed_interface_active_row(1, lower_rows) != (
        _v1_2_seed_interface_active_row(1, upper_rows)
    )


def test_run_b_worker_identity_rejects_wrong_lower_resolved_metadata() -> None:
    manifest_path = Path(
        "benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/"
        "task040_v1_2_probe_manifest_v1.json"
    )
    manifest = json.loads(manifest_path.read_text())
    observed = _identity()
    assert _v1_2_identity_pass(
        identity_observed=observed,
        frozen_identity=manifest["identity"],
        manifest=manifest,
        exact_identities=observed["exact_output_identity_sha256"],
    )
    observed["lower_resolved_mode_metadata_sha256"] = "0" * 64
    assert not _v1_2_identity_pass(
        identity_observed=observed,
        frozen_identity=manifest["identity"],
        manifest=manifest,
        exact_identities=observed["exact_output_identity_sha256"],
    )


def test_run_b_lower_mode_count_reads_resolved_per_side_schema() -> None:
    resolved_modes = {"counts": {"per_side": {"bottom": 296}}}
    assert _v1_2_lower_mode_count(resolved_modes) == 296


def _write_run(root: Path, raw: dict[str, object]) -> None:
    worker = root / "worker"
    worker.mkdir(parents=True)
    worker_path = worker / "run_summary.json"
    worker_path.write_text(
        json.dumps({"source_sha": "c" * 40, "interface_schur_raw": raw})
    )
    sample = {
        "rss_bytes": 2**30,
        "swap_bytes": 0,
        "resource_authority": {
            "memory_authority_bytes": 2**30,
            "process_tree": {
                "rss_bytes": 2**30,
                "swap_bytes": 0,
                "all_status_readable": True,
            },
            "job_cgroup": {"swap_current_bytes": 0},
        },
    }
    (root / "process_tree_samples.jsonl").write_text(
        json.dumps(sample) + "\n" + json.dumps(sample) + "\n"
    )
    worker_hash = hashlib.sha256(worker_path.read_bytes()).hexdigest()
    (root / "watchdog_summary.json").write_text(
        json.dumps(
            {
                "source_sha": "c" * 40,
                "return_code": 0,
                "termination_reason": "natural_exit",
                "run_summary_present": True,
                "all_status_readable": True,
                "hard_stop_bytes": 45 * 2**30,
                "peak_rss_bytes": 2**30,
                "peak_swap_bytes": 0,
                "peak_dedicated_cgroup_swap_bytes": 0,
                "run_summary_sha256": worker_hash,
            }
        )
    )


def test_run_b_checker_reads_jsonl_and_rejects_raw_tamper(tmp_path) -> None:
    raw = _with_v1_3(_raw())
    _write_run(tmp_path, raw)
    assert recompute_v1_2_gate(tmp_path)["gate_pass"] is True

    raw = _raw()
    raw["identity_observed"]["input_sha256"] = "0" * 64
    _write_run(tmp_path / "identity", raw)
    assert recompute_v1_2_gate(tmp_path / "identity")["checks"]["identity"] is False

    raw = _raw()
    raw["upper"]["qep_calls"] = 1
    _write_run(tmp_path / "representation", raw)
    assert (
        recompute_v1_2_gate(tmp_path / "representation")["checks"]["representation"]
        is False
    )

    raw = _raw()
    raw["factor_inventory"]["simultaneous_max"] = 4
    _write_run(tmp_path / "factor", raw)
    assert (
        recompute_v1_2_gate(tmp_path / "factor")["checks"]["factor_inventory"] is False
    )

    raw = _raw()
    raw["exact_oracle_after_cleanup"]["destroyed"] = False
    _write_run(tmp_path / "lifecycle", raw)
    assert recompute_v1_2_gate(tmp_path / "lifecycle")["checks"]["lifecycle"] is False

    raw = _raw()
    raw["probes"][-1]["YH_after_projection"] = [_pair(1.0), _pair(0.0)]
    _write_run(tmp_path / "complement", raw)
    assert (
        recompute_v1_2_gate(tmp_path / "complement")["checks"]["complement_projection"]
        is False
    )

    raw = _raw()
    _write_run(tmp_path / "resource", raw)
    samples_path = tmp_path / "resource" / "process_tree_samples.jsonl"
    rows = [json.loads(line) for line in samples_path.read_text().splitlines()]
    rows[0]["rss_bytes"] = 45 * 2**30
    samples_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    assert recompute_v1_2_gate(tmp_path / "resource")["checks"]["resource"] is False

    raw = _with_v1_3(_raw())
    raw["middle_cross_interface_sampled_response"][0]["cross_interface_norm"] = 0.9
    _write_run(tmp_path / "middle", raw)
    assert (
        recompute_v1_2_gate(tmp_path / "middle")["checks"]["middle_cross_interface"]
        is False
    )

    raw = _with_v1_3(_raw())
    raw["middle_cross_interface_sampled_response"][0]["contractions"][
        "middle_h_middle"
    ] = _pair(4.0)
    _write_run(tmp_path / "middle-contraction", raw)
    assert (
        recompute_v1_2_gate(tmp_path / "middle-contraction")["checks"][
            "middle_cross_interface"
        ]
        is False
    )

    raw = _with_v1_3(_raw())
    raw["groups"][1]["span_size"] = 1
    _write_run(tmp_path / "shape", raw)
    assert recompute_v1_2_gate(tmp_path / "shape")["checks"]["span_shapes"] is False

    raw = _raw()
    raw["groups"][0]["projected_contractions"]["gram"] = _matrix(1, 1.0)
    _write_run(tmp_path / "actual-shape", raw)
    assert (
        recompute_v1_2_gate(tmp_path / "actual-shape")["checks"]["span_shapes"] is False
    )

    raw = _with_v1_3(_raw())
    _write_run(tmp_path / "watchdog", raw)
    watchdog_path = tmp_path / "watchdog" / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text())
    watchdog["return_code"] = 2
    watchdog_path.write_text(json.dumps(watchdog))
    watchdog_result = recompute_v1_2_gate(tmp_path / "watchdog")
    assert watchdog_result["checks"]["watchdog"] is False
    assert watchdog_result["classification"] == "IMPLEMENTATION_OR_RESOURCE_FAILURE"
    assert watchdog_result["gate_pass"] is False


def test_run_b_decision_tree_requires_v1_3_after_v1_2_pass() -> None:
    stage_only = recompute_v1_2_small_contractions(_raw())
    assert stage_only["v1_2_gate_pass"] is True
    assert stage_only["v1_3_present"] is False
    assert stage_only["decision_tree_contract"] is False
    assert stage_only["gate_pass"] is False

    complete = recompute_v1_2_small_contractions(_with_v1_3(_raw()))
    assert complete["v1_2_gate_pass"] is True
    assert complete["v1_3_present"] is True
    assert complete["decision_tree_contract"] is True
    assert complete["gate_pass"] is True

    missing_v1_3 = _with_v1_3(_raw())
    for field in ("v1_3_one_apply", "v1_3_screen", "v1_3_factor_inventory"):
        missing_v1_3.pop(field)
    tampered = recompute_v1_2_small_contractions(missing_v1_3)
    assert tampered["classification"] == "IMPLEMENTATION_OR_RESOURCE_FAILURE"
    assert tampered["gate_pass"] is False


def test_run_b_checker_recomputes_v1_3_apply_counts() -> None:
    raw = _with_v1_3(_raw())
    derived = recompute_v1_2_small_contractions(raw)
    assert derived["v1_3"]["pass"] is True
    raw["v1_3_one_apply"]["action_apply_count_delta"] = 12
    tampered = recompute_v1_2_small_contractions(raw)
    assert tampered["v1_3"]["pass"] is False


def test_run_b_checker_rejects_v1_3_warm_start_contract_tamper() -> None:
    raw = _with_v1_3(_raw())
    raw["v1_3_screen"]["phase1"]["modal_traction_positive"]["zero_initial_guess"] = (
        False
    )
    tampered = recompute_v1_2_small_contractions(raw)
    assert tampered["v1_3"]["phase1"] is False
    assert tampered["v1_3"]["pass"] is False


def test_run_b_checker_rejects_probe_inventory_tamper() -> None:
    raw = _raw()
    raw["probes"] = [
        item
        for item in raw["probes"]
        if not (item["kind"] == "physical" and item["group"] == 1)
    ]
    assert recompute_v1_2_small_contractions(raw)["checks"]["probe_inventory"] is False

    raw = _raw()
    interface_probe = next(
        item
        for item in raw["probes"]
        if item["kind"] == "modal_combination" and item["interface"] == 0
    )
    interface_probe["seed"] += 1
    assert recompute_v1_2_small_contractions(raw)["checks"]["probe_inventory"] is False
