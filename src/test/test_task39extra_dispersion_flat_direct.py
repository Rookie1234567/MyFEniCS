from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.geometry.dispersion_flat_axis_plan import (
    AXIS_PLAN_ID,
    flat_axis_plan,
    is_dispersion_flat_p6_plan,
    validate_frozen_dispersion_flat_axes,
)
from src.io.execution_plan import build_execution_plan
from src.io.input_loader import InputError
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    DISPERSION_FLAT_P6_PROFILE,
    DISPERSION_FLAT_P6_RAISED_RSS_PROFILE,
    DISPERSION_FLAT_RAISED_RSS_HARD_LIMIT_BYTES,
    DISPERSION_FLAT_RAISED_RSS_PLANNING_LIMIT_BYTES,
    DISPERSION_FLAT_RSS_HARD_LIMIT_BYTES,
    DISPERSION_FLAT_RSS_PLANNING_LIMIT_BYTES,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import (
    _direct_output_policy,
    _direct_run_contract,
    _dispersion_flat_mesh_evidence,
    _dispersion_flat_port_mpc_witness,
    _validate_resolved_profile,
    _write_direct_flat_reference_outputs,
)
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap, launch_specification

REPO = Path(__file__).resolve().parents[2]
INPUTS = REPO / "input/task39extra_para_workstation_capacity"


def _resolved(nx: int) -> dict:
    return load_and_resolve(
        INPUTS / f"dispersion_0p7nm_flat_p6_q160_nx{nx}_direct_v1.dat"
    ).as_jsonable()


def _resolved_input(path: Path) -> dict:
    return load_and_resolve(path).as_jsonable()


def test_direct_flat_reference_dispatch_passes_writer_contract(monkeypatch, tmp_path):
    import src.postprocessing.flat_layer_reference_3d as flat_reference

    cfg = object()
    comm = object()
    facts = {
        "port_metrics": {"R_total": 0.2},
        "diffraction_metrics": {"R_total": 0.19},
        "volume_metrics": {"A_volume_total": 0.6},
    }
    expected = object()
    calls = []

    def fake_writer(output_dir, actual_cfg, actual_comm, *, port_metrics, probe_metrics, volume_metrics):
        calls.append(
            (
                output_dir,
                actual_cfg,
                actual_comm,
                port_metrics,
                probe_metrics,
                volume_metrics,
            )
        )
        return expected

    monkeypatch.setattr(
        flat_reference, "write_flat_layer_reference_outputs", fake_writer
    )
    result = _write_direct_flat_reference_outputs(tmp_path, cfg, comm, facts)

    assert result is expected
    assert calls == [
        (
            tmp_path,
            cfg,
            comm,
            facts["port_metrics"],
            facts["diffraction_metrics"],
            facts["volume_metrics"],
        )
    ]


@pytest.mark.parametrize("nx", (2, 4, 8))
def test_flat_cases_resolve_to_frozen_p6_q15_q160_direct_contract(nx):
    resolved = _resolved(nx)
    facts = resolved["derived"]["native_capacity_profile"]
    _validate_resolved_profile(resolved)

    assert resolved["run_id"] == f"dispersion_0p7nm_flat_p6_q160_nx{nx}_direct_v1"
    assert facts["identity"] == DISPERSION_FLAT_P6_PROFILE
    assert facts["resources"]["rss_hard_limit_bytes"] == 32 * 1024**3
    assert facts["resources"]["planning_cap_bytes"] == 24 * 1024**3
    assert facts["resources"]["require_zero_swap"] is True
    assert facts["component_options"]["volume_quadrature"] == {
        "degree": 15,
        "rule": "default",
        "points_per_hexahedron": 512,
        "points_weights_sha256": (
            "e3cf565f440b60b083a065f4655124926e98b047edea40d869cdfa5c66df9175"
        ),
    }
    assert facts["component_options"]["surface_quadrature"]["degree"] == 160
    assert facts["component_options"]["surface_quadrature_witness"]["degree"] == 192
    assert facts["component_options"]["no_n0_filter"] is True
    assert facts["component_options"]["functional_store_policy"] == (
        "disabled_no_functional_store_config"
    )
    assert facts["backend"]["p4_operator"] == "NOT_BUILT"
    assert facts["backend"]["p4_factor"] == "NOT_BUILT"
    assert facts["fine_auxiliary"]["constructed"] is False
    assert facts["intermediate"]["operator"] == "NOT_BUILT_DIRECT_P6"
    assert facts["campaign_authorization"]["direct_route"]["degree"] == 6
    assert "max_iterations" not in facts["campaign_authorization"]
    assert "reference_p4_factors" not in facts["resources"]

    route = _direct_run_contract(DISPERSION_FLAT_P6_PROFILE)
    assert route["family"] == "dispersion_flat"
    assert route["truncated"] is False
    assert route["operator_scope"] == "all_auto_propagating_orders_flat_1nm_period"
    assert route["surface_quadrature_degree"] == 160
    route["active_count"] = 17  # Supplied from the live inventory before output.
    assert _direct_output_policy(route)["active_port_outputs_only"] is False
    assert _direct_output_policy(route)["dtn_output_mode_count"] == 17

    cfg = simulation_config_3d_from_normalized(resolved)
    assert tuple(cfg.mesh_axis_cell_counts_requested) == (nx, 2, 234)
    assert cfg.mesh_axis_y_values_requested == (0.0, 12.5, 25.0)
    assert cfg.mesh_axis_z_values_requested == tuple(flat_axis_plan(nx)["z_nm"])
    assert is_dispersion_flat_p6_plan(cfg)
    cfg.nedelec_degree = 4
    assert not is_dispersion_flat_p6_plan(cfg)


def test_nx8_rss_retry_has_raised_resource_profile_without_numerical_changes():
    previous = _resolved(8)
    retry = _resolved_input(
        INPUTS / "dispersion_0p7nm_flat_p6_q160_nx8_direct_v2.dat"
    )
    facts = retry["derived"]["native_capacity_profile"]

    assert retry["run_id"] == "dispersion_0p7nm_flat_p6_q160_nx8_direct_v2"
    assert facts["identity"] == DISPERSION_FLAT_P6_RAISED_RSS_PROFILE
    assert facts["resources"]["rss_hard_limit_bytes"] == 512 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] == (
        DISPERSION_FLAT_RAISED_RSS_HARD_LIMIT_BYTES
    )
    assert facts["resources"]["planning_cap_bytes"] == 448 * 1024**3
    assert facts["resources"]["planning_cap_bytes"] == (
        DISPERSION_FLAT_RAISED_RSS_PLANNING_LIMIT_BYTES
    )
    assert facts["campaign_authorization"]["memory_override"][
        "whole_process_tree_rss_cap_bytes"
    ] == 512 * 1024**3
    assert facts["campaign_authorization"]["memory_override"][
        "startup_headroom_bytes"
    ] == 64 * 1024**3

    for section in (
        "geometry",
        "materials",
        "incidence",
        "discretization",
        "boundary",
        "method",
    ):
        assert retry[section] == previous[section]
    assert retry["solver"]["linear_solver"] == previous["solver"]["linear_solver"]
    assert retry["execution"]["mpi_size"] == previous["execution"]["mpi_size"] == 1
    assert retry["execution"]["require_zero_swap"] is True

    route = _direct_run_contract(DISPERSION_FLAT_P6_RAISED_RSS_PROFILE)
    assert route["family"] == "dispersion_flat"
    assert route["surface_quadrature_degree"] == 160
    assert route["truncated"] is False
    _validate_resolved_profile(retry)


def test_flat_profile_is_isolated_from_v7_iterative_and_n0_contracts():
    facts = native_profile_facts(DISPERSION_FLAT_P6_PROFILE)
    assert "coarse_operator" not in facts
    assert "retained_condensed_v20" not in facts
    assert facts["outer"]["route"] == "P6_CONDENSED_DIRECT"
    assert facts["outer"]["screen"]["enabled"] is False
    assert facts["functional_store_policy"]["enabled"] is False
    assert facts["functional_store_policy"]["cross_mesh_fe_reuse"] is False
    assert facts["resources"]["rss_hard_limit_bytes"] == DISPERSION_FLAT_RSS_HARD_LIMIT_BYTES
    assert facts["resources"]["planning_cap_bytes"] == DISPERSION_FLAT_RSS_PLANNING_LIMIT_BYTES
    assert facts["resources"]["resource_stop_policy"] == "measured_tree_rss_only_v3"
    assert facts["campaign_authorization"]["resource_policy"]["zero_swap"] is True
    assert facts["campaign_authorization"]["direct_route"]["p4_and_outer_ksp"] == "not_built"


@pytest.mark.parametrize(
    ("identity", "hard_bytes", "planning_bytes"),
    (
        (
            DISPERSION_FLAT_P6_PROFILE,
            32 * 1024**3,
            24 * 1024**3,
        ),
        (
            DISPERSION_FLAT_P6_RAISED_RSS_PROFILE,
            512 * 1024**3,
            448 * 1024**3,
        ),
    ),
)
def test_flat_profile_satisfies_native_memory_envelope_reserve_schema(
    monkeypatch, identity, hard_bytes, planning_bytes
):
    from benchmarks import subreaper_watchdog

    monkeypatch.setenv("PHYSICAL_NATIVE_CAPACITY", identity)
    monkeypatch.setattr(subreaper_watchdog, "current_cgroup_path", lambda: None)
    monkeypatch.setattr(
        subreaper_watchdog,
        "wsl_memory_snapshot",
        lambda: {
            "mem_total_bytes": 1_000_000_000_000,
            "mem_available_bytes": 900_000_000_000,
        },
    )

    envelope = subreaper_watchdog.memory_envelope()

    assert envelope["reserve_bytes"] == 150_000_000_000
    assert envelope["launch_cap_bytes"] == hard_bytes
    assert envelope["planning_cap_bytes"] == planning_bytes


def test_flat_profile_uses_standard_run_case_native_capacity_dispatch(
    monkeypatch, capsys
):
    import json

    from scripts import run_case
    from src.runners import native_capacity

    calls = []

    def fake_launch(specification, *, setup_only=False):
        calls.append((specification.solver["native_capacity_profile"], setup_only))
        return {"exit_status": 0, "result_classification": "worker_exit0"}

    monkeypatch.setattr(native_capacity, "launch_native_capacity", fake_launch)
    result = run_case.main(
        [str(INPUTS / "dispersion_0p7nm_flat_p6_q160_nx2_direct_v1.dat")]
    )

    assert result == 0
    assert calls == [(DISPERSION_FLAT_P6_PROFILE, False)]
    assert json.loads(capsys.readouterr().out)["result_classification"] == "worker_exit0"


def test_flat_execution_plan_binds_interleave_and_worker_cpu_inside_mpiexec(tmp_path):
    specification = load_and_resolve(
        INPUTS / "dispersion_0p7nm_flat_p6_q160_nx2_direct_v1.dat"
    )
    plan = build_execution_plan(
        specification,
        tmp_path / "planned",
        source_sha="b" * 40,
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
    )
    assert plan.argv[:8] == (
        "/usr/bin/mpiexec",
        "-n",
        "1",
        "/usr/bin/numactl",
        "--interleave=0,1",
        "/usr/bin/taskset",
        "-c",
        "24",
    )
    assert plan.argv[8] == str(REPO / ".venv/bin/python")
    assert plan.argv.count(str(REPO / ".venv/bin/python")) == 1


def test_flat_worker_manifest_and_launcher_use_the_profile_32gib_contract(
    monkeypatch, tmp_path
):
    specification = replace(
        load_and_resolve(
            INPUTS / "dispersion_0p7nm_flat_p6_q160_nx2_direct_v1.dat"
        ),
        expected_output_parent=str(tmp_path),
    )
    resolved = specification.as_jsonable()
    facts = resolved["derived"]["native_capacity_profile"]
    plan = build_execution_plan(
        specification,
        tmp_path / "planned",
        source_sha="c" * 40,
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
    )
    run_directory = tmp_path / "bootstrap-run"
    run_directory.mkdir()
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha="c" * 40,
        adapter_identity=plan.adapter_identity,
        start_time="2026-10-15T00:00:00Z",
    )
    assert manifest["native_capacity_contract"]["rss_hard_limit_bytes"] == 32 * 1024**3
    checked, errors = _load_and_validate_worker_payload(
        resolved_config=run_directory / "resolved_config.json",
        manifest=run_directory / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha="c" * 40,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=plan.adapter_identity,
        expected_output_directory=run_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )
    assert errors == []
    assert checked["derived"]["native_capacity_profile"] == facts

    from benchmarks import subreaper_watchdog

    calls = []

    def fake_supervise(command, watchdog_directory, **kwargs):
        calls.append((tuple(command), Path(watchdog_directory), kwargs))
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "zero_supported_by_zero_global_activity",
            "launch_envelope": {"launch_cap_bytes": 32 * 1024**3},
            "rss_warning_bytes": 24 * 1024**3,
            "rss_hard_limit_bytes": 32 * 1024**3,
            "resource_stop_policy": "measured_process_tree_rss_hard_limit",
            "startup_headroom_bytes": 8 * 1024**3,
            "swap_policy": "require_zero_swap",
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
    launch_spec = replace(
        specification,
        expected_output_parent=str(tmp_path / "launch-output"),
    )
    (tmp_path / "launch-output").mkdir()
    result = launch_specification(
        launch_spec,
        source_sha="d" * 40,
        timestamp="20261015T000001.000001Z",
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
        prelaunch_isolation={"status": "fake_prelaunch"},
    )
    assert result["result_classification"] == "worker_exit0"
    assert len(calls) == 1
    command, _watchdog_directory, kwargs = calls[0]
    assert command[:8] == plan.argv[:8]
    assert kwargs["rss_hard_limit_bytes"] == 32 * 1024**3
    assert kwargs["rss_warning_bytes"] == 24 * 1024**3
    assert kwargs["stop_on_global_swap"] is True


@pytest.mark.parametrize("nx", (2, 4, 8))
def test_flat_input_rejects_axis_and_route_mutation(nx):
    resolved = _resolved(nx)
    bad_axes = deepcopy(resolved["discretization"])
    bad_axes["mesh_axis_z_values"][-1] += 1.0
    with pytest.raises(ValueError, match="differ from plan"):
        validate_frozen_dispersion_flat_axes(bad_axes)

    bad = deepcopy(resolved)
    bad["boundary"]["dtn_order_policy"] = "n0_filtered"
    with pytest.raises(InputError):
        validate_native_case(bad)


def _fake_flat_levels(nx: int = 2):
    plan = flat_axis_plan(nx)
    x, y, z = (np.asarray(plan[f"{axis}_nm"], dtype=float) for axis in ("x", "y", "z"))
    xx, yy, zz = np.meshgrid(x, y, z, indexing="ij")
    geometry = SimpleNamespace(x=np.column_stack((xx.ravel(), yy.ravel(), zz.ravel())))
    counts = plan["axis_cell_counts"]
    nz_sub = sum(right <= 0.0 for _left, right in pairwise(z))
    cells = int(np.prod(counts))
    tags = np.asarray(
        [2] * (nx * 2 * nz_sub) + [1] * (cells - nx * 2 * nz_sub),
        dtype=np.int32,
    )

    class _IndexMap:
        size_global = cells

    class _Topology:
        dim = 3

        @staticmethod
        def index_map(_dim):
            return _IndexMap()

        @staticmethod
        def cell_name():
            return "hexahedron"

        @staticmethod
        def create_entity_permutations():
            return None

        @staticmethod
        def get_cell_permutation_info():
            return np.zeros(cells, dtype=np.uint32)

    mesh = SimpleNamespace(geometry=geometry, topology=_Topology())
    cfg = SimpleNamespace(
        mesh_plan_id=AXIS_PLAN_ID,
        mesh_plan_sha256=plan["plan_sha256"],
        mesh_axis_cell_counts_requested=tuple(counts),
        mesh_axis_x_values_requested=tuple(plan["x_nm"]),
        mesh_axis_y_values_requested=tuple(plan["y_nm"]),
        mesh_axis_z_values_requested=tuple(plan["z_nm"]),
        interface_z=0.0,
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
    )
    return {"mesh_data": SimpleNamespace(mesh=mesh, cell_tags=SimpleNamespace(values=tags))}, cfg


def test_flat_mesh_evidence_checks_real_axis_tag_and_orientation_shape():
    levels, cfg = _fake_flat_levels()
    evidence = _dispersion_flat_mesh_evidence(levels, cfg)
    assert evidence["status"] == "PASS"
    assert evidence["actual_global_cell_count"] == 936
    assert evidence["axis_cell_counts"] == [2, 2, 234]
    assert evidence["actual_material_tag_counts"] == {
        "1": 868,
        "2": 68,
        "3": 0,
    }
    assert sum(evidence["actual_cell_orientation_histogram"].values()) == 936

    levels["mesh_data"].cell_tags.values[0] = 3
    with pytest.raises(ValueError, match="material tags"):
        _dispersion_flat_mesh_evidence(levels, cfg)


def _fake_port_bundle(floquet):
    entries = [object(), object()]
    carrier = SimpleNamespace(entries=entries)
    action = SimpleNamespace(carrier=carrier)
    return {
        "setup": {"floquets": {6: floquet}},
        "modes": [object(), object()],
        "mode_sha256": "a" * 64,
        "dtn_quadrature_degree": 160,
        "dtn_action": action,
    }


def _fake_floquet():
    return SimpleNamespace(
        mpc=object(),
        phase_x=1.0 + 0.0j,
        phase_y=0.0 + 1.0j,
        phase_corner=0.0 + 1.0j,
        constraint_mode_resolved="topological_trace_p6",
        num_constraints=12,
        num_x_constraints=4,
        num_y_constraints=4,
        num_corner_constraints=4,
        num_slave_edges=6,
        num_slave_faces=4,
        num_edge_constraints=8,
        num_face_constraints=4,
        max_masters_per_slave=1,
        max_face_pairing_coordinate_error=0.0,
        edge_corner_phase_mismatch=0.0,
        max_edge_midpoint_pairing_error=0.0,
        max_face_midpoint_pairing_error=0.0,
        max_face_transform_fit_residual=0.0,
    )


def test_actual_port_mpc_witness_validates_phase_inventory_and_nonzero_rhs():
    floquet = _fake_floquet()
    bundle = _fake_port_bundle(floquet)
    facts = _dispersion_flat_port_mpc_witness(
        floquet,
        bundle,
        rhs_size=4,
        rhs_values=np.asarray([1.0 + 0j, 0j, -2j, 0j]),
        rhs_norm=np.sqrt(5.0),
        rhs_facts={
            "generation": "dtn_port_modal_physical_rhs",
            "role": "physical_maxwell_rhs",
            "degree": 6,
            "phase_application": "finalized_floquet_mpc_once",
            "mode_count": 2,
            "mode_manifest_sha256": "a" * 64,
        },
    )
    assert facts["status"] == "ACTUAL_PRODUCTION_PORT_MPC_RHS_VERIFIED"
    assert facts["constraint_mode_resolved"] == "topological_trace_p6"
    assert facts["dtn_mode_count"] == facts["carrier_entry_count"] == 2
    assert facts["dtn_quadrature_degree"] == 160
    assert facts["rhs_nonzero_entries"] == 2
    assert facts["finalized_mpc_used_by_physical_rhs"] is True


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"constraint_mode_resolved": "topological_trace_p4"}, "topological_trace_p6"),
        ({"num_y_constraints": 0}, "x/y periodic"),
        ({"phase_corner": -1.0 + 0j}, "corner phase"),
        ({"phase_x": complex(float("nan"), 0.0)}, "non-finite"),
    ],
)
def test_actual_port_mpc_witness_fails_closed(changes, message):
    values = vars(_fake_floquet()).copy()
    values.update(changes)
    floquet = SimpleNamespace(**values)
    with pytest.raises((ValueError, FloatingPointError), match=message):
        _dispersion_flat_port_mpc_witness(
            floquet,
            _fake_port_bundle(floquet),
            rhs_size=2,
            rhs_values=np.asarray([1.0 + 0j, 0j]),
            rhs_norm=1.0,
            rhs_facts={
                "generation": "dtn_port_modal_physical_rhs",
                "phase_application": "finalized_floquet_mpc_once",
                "degree": 6,
                "mode_count": 2,
                "mode_manifest_sha256": "a" * 64,
            },
        )
