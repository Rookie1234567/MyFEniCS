"""Focused Review V19 PML double-sweep contracts and one real p2 anchor."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task038_v19_oracles as v19_runner
import benchmarks.task038_v19_oracle_checker as v19_checker
from benchmarks.run_task038_v19_oracles import _p2_fixture
from src.solvers.fullspace_pml_double_sweep import (
    CORE_COUNT,
    OwnerMap,
    PMLDoubleSweep,
    PMLQuartilePlan,
    SWEEP_ORDER,
    _extended_local_z_axis,
    build_z_quartile_plan,
    count_unique_structural_pairs,
    mpc_global_row_replacements,
    pml_profile_facts,
    quadratic_stretch,
)


ROOT = Path(__file__).parents[2]
INPUT = ROOT / "input" / "templates" / "full3d_pml_double_sweep_v19.dat"


def _fake_plan() -> PMLQuartilePlan:
    rows = [
        np.asarray((index, index + 1), dtype=np.int64)
        for index in range(4)
    ]
    plan = build_z_quartile_plan(
        np.asarray((0.0, 10.0, 25.0, 40.0, 60.0), dtype=np.float64),
        rows,
    )
    return replace(plan, audit={**plan.audit, "pml_rows_materialized": True})


def test_v19_plan_pml_profile_and_updated_double_sweep_are_frozen() -> None:
    plan = _fake_plan()
    assert len(plan.subdomains) == CORE_COUNT
    assert tuple(SWEEP_ORDER) == (0, 1, 2, 3, 3, 2, 1, 0)
    assert plan.audit["interface_tie_rule"] == "nearest plane; lower z on equal distance"
    assert plan.audit["interface_trace_count_kind"].startswith("raw adjacent-core")
    assert plan.audit["overlap_intersection_storage_row_counts"] == [3, 3, 3]
    assert plan.audit["interface_trace_row_counts"] == [1, 1, 1]
    for subdomain in plan.subdomains:
        for side, layers in subdomain.pml_layers.items():
            assert len(layers) == (2 if side in subdomain.pml_sides else 0)

    values = np.arange(plan.global_size, dtype=np.float64).astype(np.complex128)
    sweep = PMLDoubleSweep(plan)
    result = sweep.apply(
        values,
        lambda _subdomain, local_rhs: 0.25 * local_rhs,
        lambda correction: 2.0 * correction,
    )
    assert result.audit["sweep_order"] == list(SWEEP_ORDER)
    assert result.audit["residual_updated_between_visits"] is True
    assert result.audit["input_unchanged"] is True
    assert result.audit["exact_action_count"] == len(SWEEP_ORDER)

    thickness = 2.0
    assert quadratic_stretch(0.0, thickness) == pytest.approx(1.0 + 0.0j)
    profile = pml_profile_facts(thickness)
    assert profile["outgoing_amplitude_at_thickness"] == pytest.approx(0.01)


def test_v19_structural_pairs_expand_exact_nonzero_mpc_support() -> None:
    cells = [np.asarray((0, 1), dtype=np.int64), np.asarray((1, 2), dtype=np.int64)]
    without_mpc = count_unique_structural_pairs(cells, 3)
    with_mpc = count_unique_structural_pairs(
        cells,
        4,
        row_replacements={1: (0, 2, 3)},
    )
    assert without_mpc == 7
    assert with_mpc == 9


def test_v19_pml_endpoints_and_exact_mpc_support_are_not_midpoints() -> None:
    local_z, _left_layers, _right_layers, _thicknesses = _extended_local_z_axis(
        np.asarray((0.0, 10.0, 20.0, 30.0, 40.0), dtype=np.float64),
        1,
        3,
    )
    assert local_z[2] == pytest.approx(10.0)
    assert local_z[-3] == pytest.approx(30.0)
    for thickness in (10.0, 10.0):
        assert quadratic_stretch(0.0, thickness) == pytest.approx(1.0 + 0.0j)
        assert pml_profile_facts(thickness)["outgoing_amplitude_at_thickness"] == pytest.approx(0.01)

    mpc = type(
        "MPC",
        (),
        {
            "slaves": np.asarray((1,), dtype=np.int32),
            "coefficients": lambda self: (
                np.asarray((1.0 + 0.0j, 1.0e-20 + 0.0j), dtype=np.complex128),
                np.asarray((0, 0, 2), dtype=np.int64),
            ),
            "masters": type(
                "Masters",
                (),
                {"links": lambda self, _slave: np.asarray((0, 2), dtype=np.int32)},
            )(),
        },
    )()
    index_map = type(
        "IndexMap",
        (),
        {"local_to_global": lambda self, values: np.asarray(values, dtype=np.int64)},
    )()
    space = type("Space", (), {"dofmap": type("DofMap", (), {"index_map": index_map})()})()
    replacements = mpc_global_row_replacements(
        space,
        type("Floquet", (), {"mpc": mpc})(),
    )
    assert replacements == {1: (0, 2)}


def test_v19_sweep_discards_pml_slots_and_updates_eight_times() -> None:
    physical_map = OwnerMap(
        np.asarray((0, 1), dtype=np.int64),
        np.ones(2, dtype=np.complex128),
        local_positions=np.asarray((0, 2), dtype=np.int64),
        local_size=3,
    )
    subdomains = tuple(
        SimpleNamespace(
            physical_map=physical_map,
            weights=np.asarray((0.25, 0.25), dtype=np.float64),
        )
        for _ in range(4)
    )
    plan = SimpleNamespace(
        global_size=2,
        subdomains=subdomains,
        audit={
            "pml_rows_materialized": True,
            "partition_of_unity_max_abs_error": 0.0,
        },
    )
    sweep = PMLDoubleSweep(plan)
    action_inputs: list[np.ndarray] = []

    def solve_local(_subdomain, local_rhs):
        result = local_rhs.copy()
        result[1] = 100.0 + len(action_inputs)
        return result

    def action(delta):
        action_inputs.append(delta.copy())
        return delta.copy()

    result = sweep.apply(np.asarray((1.0 + 0.0j, 2.0 + 0.0j)), solve_local, action)
    assert len(action_inputs) == len(SWEEP_ORDER) == 8
    assert np.allclose(action_inputs[0], (0.25, 0.5))
    assert all(np.all(np.isfinite(item)) for item in action_inputs)
    assert result.audit["exact_action_count"] == 8
    assert result.audit["residual_updated_between_visits"] is True
    assert sum(item.weights[0] for item in subdomains) == pytest.approx(1.0)
    assert plan.audit["partition_of_unity_max_abs_error"] == 0.0


@pytest.mark.parametrize(
    ("returncode", "stop_reason", "expected_rc", "expected_classification"),
    (
        (0, None, 0, "R0_P6_SYMBOLIC_ANALYSIS_COMPLETE_PENDING_REVIEW"),
        (1, None, 1, "R0_P6_SYMBOLIC_PRECHECK_OR_ENGINEERING_STOP"),
        (1, "process_tree_rss_watchdog", 1, "R0_P6_SYMBOLIC_RESOURCE_CONTROLLED_STOP"),
    ),
)
def test_v19_p6_symbolic_parent_uses_existing_watchdog_and_lexical_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stop_reason: str | None,
    expected_rc: int,
    expected_classification: str,
) -> None:
    root = tmp_path / "p6-symbolic"
    record = root / "parent_record.json"
    input_path = tmp_path / "input.dat"
    input_path.write_text("frozen input", encoding="utf-8")
    budget = {
        "formula": "test-budget",
        "launch_cap_bytes": 8_830_377_984,
        "warning_bytes": 10_000_000_000,
        "hard_limit_bytes": 12_000_000_000,
        "numeric_and_solve_forbidden": True,
    }
    monkeypatch.setattr(
        v19_runner,
        "_p6_symbolic_source_facts",
        lambda _sha, _path: {
            "source_sha": "a" * 40,
            "input_relative_path": "input.dat",
            "input_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(v19_runner, "_p6_symbolic_launch_budget", lambda: budget)
    captured: dict[str, object] = {}

    def fake_run_parent_child(command, sample_path, stage, stdout_path, stderr_path, **kwargs):
        worker_record = Path(command[command.index("--record") + 1])
        worker_record.write_text("{}\n", encoding="utf-8")
        captured.update(
            {
                "command": command,
                "sample_path": sample_path,
                "stage": stage,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "kwargs": kwargs,
            }
        )
        return {
            "argv": command,
            "returncode": returncode,
            "stop_reason": stop_reason,
            "process_group_gone": True,
            "peak_rss_bytes": 100,
            "max_swap_bytes": 0,
            "all_status_readable": True,
            "sample_count": 1,
            "lifecycle_failure": False,
            "signals": [],
            "rss_watchdog_bytes": kwargs["rss_watchdog_bytes"],
        }

    monkeypatch.setattr(
        "benchmarks.run_task038_full3d_physical_pcoarse_q1._run_parent_child",
        fake_run_parent_child,
    )
    assert v19_runner.run_p6_symbolic_parent(root, record, "a" * 40, input_path) == expected_rc
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0:3] == ["mpiexec", "-n", "1"]
    assert command[3] == str(ROOT / ".venv" / "bin" / "python")
    assert "--mode" in command and command[command.index("--mode") + 1] == "worker"
    assert "--phase" in command and command[command.index("--phase") + 1] == v19_runner.P6_SYMBOLIC_PHASE
    assert captured["kwargs"] == {
        "rss_watchdog_bytes": budget["launch_cap_bytes"],
        "rss_warning_bytes": budget["warning_bytes"],
    }
    parent = json.loads(record.read_text(encoding="utf-8"))
    assert parent["budget"]["launch_cap_bytes"] == budget["launch_cap_bytes"]
    assert parent["numeric_factor_and_solve"] is False
    assert parent["worker_complete"] == (returncode == 0)
    assert parent["status"] == (
        "RAW_COMPLETE_PENDING_REVIEW"
        if returncode == 0
        else "RAW_INCOMPLETE_PENDING_REVIEW"
    )
    assert parent["classification"] == expected_classification
    assert json.loads(
        (root / "markers" / "04_release_complete.json").read_text(encoding="utf-8")
    )["worker_released"] is True


def test_v19_p6_checker_recomputes_timeline_cap_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    timeline_path = tmp_path / "parent_process.jsonl"
    timeline_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "authority": {
                        "process_tree": {
                            "rss_bytes": rss,
                            "swap_bytes": 0,
                            "all_status_readable": True,
                        }
                    }
                },
                sort_keys=True,
            )
            for rss in (7_000_000_000, 8_000_000_000)
        )
        + "\n",
        encoding="utf-8",
    )
    timeline = v19_checker._read_process_timeline(timeline_path)
    mem_total = 10_000_000_000
    reserve = max(4 * 1024**3, int(0.1 * mem_total))
    launch_cap = 8_000_000_000
    preflight = {
        "mem_total_bytes": mem_total,
        "mem_available_bytes": launch_cap + reserve,
        "reserve_bytes": reserve,
        "launch_cap_bytes": launch_cap,
        "formula": "min(12000000000, MemAvailable - max(4GiB, 0.1*MemTotal))",
    }
    process = {
        "sample_count": 2,
        "peak_rss_bytes": launch_cap,
        "max_swap_bytes": 0,
        "all_status_readable": True,
    }
    worker = {
        **process,
        "rss_watchdog_bytes": launch_cap,
        "stop_reason": "process_tree_rss_watchdog",
    }
    budget = {"launch_cap_bytes": launch_cap}
    errors: list[str] = []
    gates: list[str] = []
    assert v19_checker._check_p6_resource_observation(
        timeline, process, worker, preflight, budget, errors, gates
    ) == launch_cap
    assert errors == []
    assert gates == ["process_tree_rss_watchdog"]

    bad_errors: list[str] = []
    bad_gates: list[str] = []
    bad_timeline = {**timeline, "peak_rss_bytes": launch_cap - 1}
    v19_checker._check_p6_resource_observation(
        bad_timeline, process, worker, preflight, budget, bad_errors, bad_gates
    )
    assert any("timeline peak" in item for item in bad_errors)


def test_v19_real_p2_pml_form_action_and_mumps_anchor() -> None:
    pytest.importorskip("mpi4py")
    pytest.importorskip("dolfinx")
    pytest.importorskip("dolfinx_mpc")
    pytest.importorskip("petsc4py")
    from mpi4py import MPI

    from src.io.input_validation import load_and_resolve, simulation_config_3d_from_normalized

    specification = load_and_resolve(INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    facts = _p2_fixture(cfg, MPI.COMM_SELF)

    assert facts["degree"] == 2
    assert facts["local_action_relative"] <= 1.0e-10
    assert facts["local_action_repeat_relative"] <= 1.0e-10
    assert facts["stretch_one_local_maxwell_relative"] <= 1.0e-10
    assert facts["stretch_one_original_maxwell_relative"] <= 1.0e-10
    assert facts["map_dual_primal_relative"] <= 1.0e-10
    assert facts["map_hermitian_pairing_relative"] <= 1.0e-10
    assert facts["pou_max_error"] <= 1.0e-12
    assert facts["map_input_unchanged"] is True
    assert facts["input_unchanged"] is True
    assert facts["source_finite"] is True
    assert facts["output_finite"] is True
    assert facts["finite"] is True
    assert facts["owned_slave_max"] == 0.0
    form_sides = {item["side"]: item for item in facts["form_facts"]["pml_sides"]}
    local_mesh = facts["pml_local_mesh_facts"][1]
    z_local = np.asarray(local_mesh["z_values_nm"], dtype=np.float64)
    for side, item in form_sides.items():
        endpoint = z_local[2] if side == "left" else z_local[-3]
        assert item["interface_z_nm"] == pytest.approx(float(endpoint))
        thickness = float(local_mesh["pml_thicknesses_nm"][side])
        assert quadratic_stretch(0.0, thickness) == pytest.approx(1.0 + 0.0j)
        assert pml_profile_facts(thickness)["outgoing_amplitude_at_thickness"] == pytest.approx(0.01)

    mumps = facts["mumps"]
    analysis = mumps["analysis"]
    solve = mumps["solve"]
    preflight = mumps["resource_preflight"]
    assert analysis["analysis_only"] is True
    assert analysis["symbolic_calls"] == 1
    assert analysis["numeric_calls"] == 0
    assert analysis["solve_calls"] == 0
    assert preflight["predicted_peak_bytes"] == preflight["post_analysis_process_tree_rss_bytes"] + max(preflight["infog16"], 0) * 1_000_000
    assert preflight["predicted_peak_bytes"] < preflight["hard_limit_bytes"]
    assert solve["resource_preflight"] == "passed"
    assert solve["numeric_factor_called"] is True
    assert solve["solve_called"] is True
    assert solve["symbolic_calls"] == 1
    assert solve["numeric_calls"] == 1
    assert solve["solve_calls"] == 1
    assert mumps["explicit_residual_relative"] <= 1.0e-10
    assert mumps["finite"] is True
    assert mumps["release"]["factor_destroyed"] is True
    print(
        "r0_p2_real_facts="
        + json.dumps(
            {
                "local_action_relative": facts["local_action_relative"],
                "local_action_repeat_relative": facts["local_action_repeat_relative"],
                "stretch_one_local_maxwell_relative": facts[
                    "stretch_one_local_maxwell_relative"
                ],
                "stretch_one_original_maxwell_relative": facts[
                    "stretch_one_original_maxwell_relative"
                ],
                "map_dual_primal_relative": facts["map_dual_primal_relative"],
                "map_hermitian_pairing_relative": facts[
                    "map_hermitian_pairing_relative"
                ],
                "pou_max_error": facts["pou_max_error"],
                "mumps_explicit_residual_relative": mumps[
                    "explicit_residual_relative"
                ],
                "mumps_infog16": preflight["infog16"],
                "mumps_post_analysis_rss_bytes": preflight[
                    "post_analysis_process_tree_rss_bytes"
                ],
                "mumps_predicted_peak_bytes": preflight["predicted_peak_bytes"],
                "owned_slave_count": facts["owned_slave_count"],
                "owned_slave_max": facts["owned_slave_max"],
                "finite": facts["finite"],
                "input_unchanged": facts["input_unchanged"],
            },
            sort_keys=True,
        )
    )
