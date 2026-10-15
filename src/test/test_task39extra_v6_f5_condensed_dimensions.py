from __future__ import annotations

import json
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from src.io.input_validation import load_and_resolve
from src.io.native_capacity_profile import (
    V6_F5_P6_DIRECT_FULL600_PROFILE,
    V6_F5_P6_DIRECT_N0_PROFILE,
    V7_ANISO_N0_P6_DIRECT_PROFILE,
)
from src.runners.p6_condensed_direct import (
    _build_f5_n0_inventory,
    _direct_output_policy,
    _direct_run_contract,
    _f5_mesh_evidence,
    _validate_direct_condensed_dimensions,
)
from src.runners.task038_input_worker import _dispatch_resolved_payload
from src.runners.task038_launcher import launch_specification

REPO = Path(__file__).resolve().parents[2]
F5_INPUTS = (
    (
        REPO
        / "input/task39extra_para_workstation_capacity/"
        "v6_5nm_p6_condensed_direct_full600_y2.dat",
        V6_F5_P6_DIRECT_FULL600_PROFILE,
        600,
    ),
    (
        REPO
        / "input/task39extra_para_workstation_capacity/"
        "v6_5nm_p6_condensed_direct_n0_y2.dat",
        V6_F5_P6_DIRECT_N0_PROFILE,
        80,
    ),
)


def test_f5_mesh_evidence_uses_actual_mesh_not_absent_wrapper_metadata():
    x, y, z = (0.0, 1.0, 2.0), (0.0, 1.0), (0.0, 1.0, 2.0)
    geometry_x = np.asarray(list(product(x, y, z)), dtype=np.float64)

    class FakeTopology:
        dim = 3

        @staticmethod
        def index_map(_dimension):
            return SimpleNamespace(size_global=4)

        @staticmethod
        def cell_name():
            return "hexahedron"

    # _build_same_mesh_levels currently returns this deliberately small wrapper:
    # it owns the DOLFINx mesh and tags, not resolved-count convenience fields.
    mesh_data = SimpleNamespace(
        mesh=SimpleNamespace(
            geometry=SimpleNamespace(x=geometry_x), topology=FakeTopology()
        ),
        cell_tags=SimpleNamespace(values=np.asarray([1, 2, 1, 0], dtype=np.int32)),
    )
    cfg = SimpleNamespace(
        mesh_axis_x_values_requested=x,
        mesh_axis_y_values_requested=y,
        mesh_axis_z_values_requested=z,
        x_min=0.0,
        x_max=2.0,
        grating_x_min=0.0,
        grating_x_max=1.0,
        domain_z_min=0.0,
        interface_z=1.0,
        grating_z_min=1.0,
        grating_z_max=2.0,
        tags=SimpleNamespace(air=0, substrate=1, grating=2),
    )

    evidence = _f5_mesh_evidence({"mesh_data": mesh_data}, cfg)

    assert evidence["status"] == "PASS"
    assert evidence["actual_global_cell_count"] == 4
    assert evidence["axis_cell_counts"] == [2, 1, 2]
    assert evidence["cell_type"] == "hexahedron"
    assert evidence["material_tag_counts"] == {"0": 1, "1": 2, "2": 1}


def _periodic_slave_condensed():
    trace_rows = 100
    active_rows = 98
    trace_constraints = SimpleNamespace(
        full_trace_rows=trace_rows,
        active_rows=active_rows,
        slave_rows=2,
        # Two periodic slave rows are represented through the expansion map;
        # they are not extra active matrix rows and are not cell interiors.
        expansion_by_original={row: None for row in range(trace_rows)},
        original_to_active={row: row for row in range(active_rows)},
    )
    return SimpleNamespace(
        full_rows=1000,
        trace_rows=trace_rows,
        active_rows=active_rows,
        interior_rows=900,
        appended_rows=4,
        trace_constraints=trace_constraints,
    )


def test_condensed_dimensions_accept_trace_partition_with_periodic_slaves():
    condensed = _periodic_slave_condensed()

    # The former active+interior check incorrectly yielded 98+900 != 1000.
    _validate_direct_condensed_dimensions(
        condensed,
        full_p6_rows=1000,
        appended_rows=4,
        matrix_size=(102, 102),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("trace_partition", "dimensions"),
        ("active_slave_partition", "dimensions"),
        ("trace_map_count", "dimensions"),
        ("active_map_count", "dimensions"),
        ("matrix_size", "dimensions"),
    ],
)
def test_condensed_dimensions_reject_inconsistent_trace_or_slave_maps(
    mutation, message
):
    condensed = _periodic_slave_condensed()
    matrix_size = (102, 102)
    if mutation == "trace_partition":
        condensed.interior_rows = 899
    elif mutation == "active_slave_partition":
        condensed.trace_constraints.slave_rows = 1
    elif mutation == "trace_map_count":
        condensed.trace_constraints.expansion_by_original.pop(99)
    elif mutation == "active_map_count":
        condensed.trace_constraints.original_to_active.pop(97)
    elif mutation == "matrix_size":
        matrix_size = (100, 100)

    with pytest.raises(ValueError, match=message):
        _validate_direct_condensed_dimensions(
            condensed,
            full_p6_rows=1000,
            appended_rows=4,
            matrix_size=matrix_size,
        )


def test_f5_n0_output_policy_exports_only_active_modes_without_v7_alias():
    f5_n0 = _direct_run_contract(V6_F5_P6_DIRECT_N0_PROFILE)
    policy = _direct_output_policy(f5_n0)
    assert f5_n0["active_count"] == 80
    assert policy["active_port_outputs_only"] is False
    assert policy["dtn_output_mode_count"] == 80
    assert policy["omitted_dtn_channels"] == "NOT_COMPUTED"
    assert policy["diffraction_source"] == (
        "field_sample_based_independent_of_dtn_mode_list"
    )

    full600 = _direct_output_policy(
        _direct_run_contract(V6_F5_P6_DIRECT_FULL600_PROFILE)
    )
    assert full600["active_port_outputs_only"] is False
    assert full600["dtn_output_mode_count"] == 600
    assert full600["omitted_dtn_channels"] == "NONE"

    # The helper's 572-only path remains reserved for its original V7 route.
    v7 = _direct_output_policy(
        _direct_run_contract(V7_ANISO_N0_P6_DIRECT_PROFILE)
    )
    assert v7["active_port_outputs_only"] is True
    assert v7["dtn_output_mode_count"] == 572


@pytest.mark.parametrize(("input_path", "profile", "active_modes"), F5_INPUTS)
def test_f5_direct_inputs_resolve_exact_y2_axis_counts(input_path, profile, active_modes):
    specification = load_and_resolve(input_path)
    resolved = specification.as_jsonable()
    assert resolved["run_id"].endswith("_y2")
    assert resolved["method"]["kind"] == "full3d_direct"
    assert resolved["solver"]["native_capacity_profile"] == profile
    assert resolved["derived"]["mesh_cells"] == [15, 2, 36]
    assert resolved["derived"]["mesh_cells_source"] == "explicit_frozen_axis_plan"
    assert resolved["derived"]["native_capacity_profile"]["component_options"][
        "active_mode_count"
    ] == active_modes


def test_f5_n0_selection_uses_actual_full_parent_and_keeps_q37_authority():
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    input_path, _profile, _active_count = F5_INPUTS[1]
    resolved = load_and_resolve(input_path).as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    parent = build_dynamic_mode_inventory(cfg)
    active, selection, indices = _build_f5_n0_inventory(parent, cfg)

    assert len(parent[0]) == 600
    assert parent[2] == "dde3aee7ee25bc5d68617a503eebec720a1527c9d044125bfb09acaa6d0b6645"
    assert len(active[0]) == 80
    assert active[2] == "36337e70f52f959b4f8b7e1727ee8babccd3e84d2e25d70bd32e87c79040e012"
    assert all(int(mode.n) == 0 for mode in active[0])
    assert indices != tuple(range(80))
    assert selection["side_polarization_counts"] == {
        "bottom_s": 20,
        "bottom_p": 20,
        "top_s": 20,
        "top_p": 20,
    }
    options = resolved["derived"]["native_capacity_profile"]["component_options"]
    assert options["surface_quadrature"]["degree"] == 37
    assert options["surface_quadrature"]["authority"] == "full600_parent_inventory_even_for_n0_subset"


@pytest.mark.parametrize(
    ("input_path", "profile", "timestamp"),
    [
        (F5_INPUTS[0][0], F5_INPUTS[0][1], "20261015T000000.000001Z"),
        (F5_INPUTS[1][0], F5_INPUTS[1][1], "20261015T000001.000001Z"),
    ],
)
def test_f5_full3d_direct_worker_and_launcher_contract_without_fe(
    input_path, profile, timestamp, monkeypatch, tmp_path
):
    specification = replace(
        load_and_resolve(input_path), expected_output_parent=str(tmp_path)
    )
    resolved = specification.as_jsonable()
    calls = []
    fake_module = ModuleType("src.runners.p6_condensed_direct")

    def fake_runner(payload, directory, *, source_sha):
        calls.append((payload["run_id"], Path(directory), source_sha))
        return {"passed": True, "errors": []}

    fake_module.run_p6_condensed_direct = fake_runner
    monkeypatch.setitem(sys.modules, "src.runners.p6_condensed_direct", fake_module)
    status, errors = _dispatch_resolved_payload(
        resolved,
        expected_method="full3d_direct",
        output_directory=tmp_path,
        expected_source_sha="a" * 40,
    )
    assert (status, errors) == (0, [])
    assert calls == [(resolved["run_id"], tmp_path, "a" * 40)]

    from benchmarks import subreaper_watchdog

    profile_facts = resolved["derived"]["native_capacity_profile"]
    resources = profile_facts["resources"]
    launch_commands = []

    def fake_supervise(command, directory, **kwargs):
        launch_commands.append((tuple(command), Path(directory), kwargs))
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "observed_only",
            "launch_envelope": {"launch_cap_bytes": resources["rss_hard_limit_bytes"]},
            "rss_warning_bytes": resources["rss_warning_bytes"],
            "rss_hard_limit_bytes": resources["rss_hard_limit_bytes"],
            "resource_stop_policy": resources["resource_stop_policy"],
            "startup_headroom_bytes": resources["startup_headroom_bytes"],
            "swap_policy": resources["swap_policy"],
            "memory_scope": "sampled_process_tree",
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    monkeypatch.setattr(
        "src.runners.task038_launcher._physical_source_gate",
        lambda _cwd, source: {
            "source_sha": source,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    launched = launch_specification(
        specification,
        source_sha="a" * 40,
        timestamp=timestamp,
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
        prelaunch_isolation={"status": "fake_prelaunch"},
    )
    assert launched["result_classification"] == "worker_exit0"
    assert len(launch_commands) == 1
    plan, watchdog_directory, kwargs = launch_commands[0]
    assert watchdog_directory == Path(launched["run_directory"]) / "watchdog"
    assert kwargs["rss_hard_limit_bytes"] == 1_800_000_000_000
    assert plan[:8] == (
        "/usr/bin/mpiexec",
        "-n",
        "1",
        "/usr/bin/numactl",
        "--interleave=0,1",
        "/usr/bin/taskset",
        "-c",
        "24",
    )
    assert plan[8] == str(REPO / ".venv/bin/python")
    assert profile_facts["identity"] == profile


@pytest.mark.parametrize(
    ("input_path", "profile"),
    [(input_path, profile) for input_path, profile, _count in F5_INPUTS],
)
def test_f5_inputs_use_standard_run_case_native_capacity_entry(
    input_path, profile, monkeypatch, capsys
):
    from scripts import run_case
    from src.io.native_capacity_profile import NATIVE_PROFILES
    from src.runners import native_capacity

    assert profile in NATIVE_PROFILES
    calls = []

    def fake_native_launch(specification, *, setup_only=False):
        calls.append((specification.solver["native_capacity_profile"], setup_only))
        return {"exit_status": 0, "result_classification": "worker_exit0"}

    monkeypatch.setattr(native_capacity, "launch_native_capacity", fake_native_launch)
    result = run_case.main([str(input_path)])
    assert result == 0
    assert calls == [(profile, False)]
    assert json.loads(capsys.readouterr().out)["result_classification"] == "worker_exit0"

