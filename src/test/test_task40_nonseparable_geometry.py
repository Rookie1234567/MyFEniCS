"""Task40 exact input, mesh and supervised-launch contracts."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import sys
import subprocess
import pytest

from src.common.config_3d import ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.task40_nonseparable_plan import (
    TASK40_GEOMETRY_IDENTITY,
    TASK40_PROFILE,
    task40_mesh_plan,
    validate_task40_input,
)
from src.io import InputError, load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
from src.io.physical_intermediate_profile import (
    PROJECTION_LAYOUT_V31_PROFILE,
    profile_facts,
)
from src.runners import task038_launcher as launcher

ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
G0 = INPUT_ROOT / "nonseparable_g0_p6_q4.dat"
G1 = INPUT_ROOT / "nonseparable_g1_p6_q4.dat"
G0_DIRECT = INPUT_ROOT / "nonseparable_g0_p6_direct_reference.dat"


def test_all_task40_inputs_resolve_to_the_frozen_physical_identity():
    resolved = [load_and_resolve(path) for path in (G0, G1, G0_DIRECT)]
    for specification in resolved:
        validate_task40_input(specification.as_jsonable())
        assert specification.geometry["geometry_identity"] == TASK40_GEOMETRY_IDENTITY
        assert specification.geometry["air_void_box_nm"] == resolved[0].geometry[
            "air_void_box_nm"
        ]
        assert specification.materials["n_substrate"] == resolved[0].materials[
            "n_substrate"
        ]
    assert resolved[0].discretization["mesh_axis_cell_counts"] == (6, 4, 14)
    assert resolved[1].discretization["mesh_axis_cell_counts"] == (10, 4, 22)
    assert resolved[2].method["kind"] == "full3d_direct"
    assert resolved[2].discretization["assembly_backend"] == (
        "assembly_time_static_condensed"
    )
    assert resolved[0].solver["preconditioner"] == TASK40_PROFILE


def _task40_tiny_n2_config():
    specification = load_and_resolve(G0)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    scale = 7.0 / 135.0
    axes = {
        "x": tuple(value * scale for value in (0, 16.5, 25, 33.5, 50)),
        "y": tuple(value * scale for value in (0, 6.25, 18.75, 25)),
        "z": tuple(value * scale for value in (-10, 0, 40, 80, 120, 130)),
    }
    plan_payload = {
        "identity": "task40extra.n2_tiny_diagnostic_60cells.v1",
        "axes_nm": {axis: list(values) for axis, values in axes.items()},
        "p": 2,
        "role": "diagnostic_only_not_g0_or_g1",
    }
    plan_sha256 = sha256(
        json.dumps(plan_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return replace(
        cfg,
        nedelec_degree=2,
        visualization_degree=2,
        mesh_target_size=max(
            max(np.diff(np.asarray(values, dtype=np.float64)))
            for values in axes.values()
        ),
        mesh_spacing_mode="boundary_fitted",
        mesh_axis_cell_counts=(4, 3, 5),
        mesh_axis_x_values=axes["x"],
        mesh_axis_y_values=axes["y"],
        mesh_axis_z_values=axes["z"],
        mesh_axis_z_profile=plan_payload["identity"],
        mesh_plan_id=plan_payload["identity"],
        mesh_plan_sha256=plan_sha256,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    )


def test_n2_tiny_task40_stage4_static_condensed_diagnostic(tmp_path: Path):
    """One 60-cell p2 diagnostic only; no claim about p6/A4 or official G0."""

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_vector,
        _dtn_surface_quadrature_degree,
        _incident_top_traction_form,
        outgoing_port_modes_3d,
    )
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    cfg = _task40_tiny_n2_config()
    assert cfg.lambda0 == pytest.approx(0.7)
    assert cfg.n_substrate == pytest.approx(0.9998851703688496 + 4.3236152269189515e-6j)
    assert cfg.n_grating == cfg.n_substrate
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / "mesh")
    assert math.prod(mesh_data.mesh_cells_resolved) == 60
    assert mesh_data.rectangular_air_void_audit["status"] == "PASS"
    assert mesh_data.rectangular_air_void_audit["owned_void_box_cell_count"] == 1

    V = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet = build_double_floquet_mpc(V, mesh_data, cfg)
    modes = tuple(outgoing_port_modes_3d(cfg))
    rhs = _assemble_mpc_vector(
        _incident_top_traction_form(V, mesh_data, cfg),
        floquet.mpc,
        quadrature_degree=_dtn_surface_quadrature_degree(cfg, list(modes)),
    )
    try:
        rhs_norm = float(rhs.norm())
    finally:
        rhs.destroy()
    assert modes
    assert math.isfinite(rhs_norm) and rhs_norm > 0.0

    result = run_stage4b_block_grating_3d_case(
        cfg, tmp_path / "diagnostic-run", mesh_data_override=mesh_data
    )
    assert result["case_status"] == "completed"
    assert result["stage4_assembly_time_cell_static_condensation"] is True
    assert math.isfinite(float(result["linear_system_relative_residual"]))
    assert float(result["linear_system_relative_residual"]) <= 1.0e-8
    for key in ("R_total", "T_total", "A_volume_total"):
        assert math.isfinite(float(result[key]))


def test_task40_rejects_a_different_void_even_if_it_remains_inside_the_grating(
    tmp_path: Path,
):
    source = G0.read_text(encoding="utf-8")
    old = (
        "air_void_box_nm = [1.2962962962962963, 1.7370370370370369,"
        " 0.32407407407407407, 0.97222222222222221, 2.074074074074074,"
        " 4.1481481481481479]"
    )
    new = old.replace("1.7370370370370369", "1.75")
    assert old in source
    candidate = tmp_path / G0.name
    candidate.write_text(source.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(InputError, match="air_void_box_nm differs from the exact 3D notch"):
        load_and_resolve(candidate)


@pytest.mark.parametrize(
    ("input_path", "mesh_id", "expected_axes", "expected_tags", "expected_void_cells"),
    [
        (G0, "G0", (6, 4, 14), {1: 224, 2: 24, 3: 88}, 8),
        (G1, "G1", (10, 4, 22), {1: 536, 2: 80, 3: 264}, 24),
    ],
)
def test_actual_mesh_builder_preserves_task40_void_and_material_counts(
    input_path: Path,
    mesh_id: str,
    expected_axes: tuple[int, int, int],
    expected_tags: dict[int, int],
    expected_void_cells: int,
    tmp_path: Path,
):
    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    plan = task40_mesh_plan(mesh_id)
    assert cfg.mesh_axis_cell_counts_requested == expected_axes
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / mesh_id)
    tags = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    counts = {tag: int(np.count_nonzero(tags == tag)) for tag in expected_tags}
    assert mesh_data.mesh_cells_resolved == expected_axes
    assert len(tags) == plan["expected_hexahedra"]
    assert counts == expected_tags
    audit = mesh_data.rectangular_air_void_audit
    assert audit["status"] == "PASS"
    assert audit["owned_void_box_cell_count"] == expected_void_cells
    assert audit["non_air_tagged_void_box_cell_count"] == 0
    assert audit["box_boundary_vertex_alignment_serial"] == {
        "x": True,
        "y": True,
        "z": True,
    }
    assert all(audit["nonseparable_extent_axes"].values())


def test_process_tree_snapshot_records_stable_process_identities():
    sample = process_tree_snapshot(
        os.getpid(), "task40_identity_test", pss_sampling_policy="disabled_by_profile"
    )
    assert sample["all_status_readable"] is True
    assert sample["identity_complete"] is True
    root = next(member for member in sample["members"] if member["pid"] == os.getpid())
    assert isinstance(root["start_ticks"], int)
    assert root["start_ticks"] > 0


def test_task40_profile_and_dispatch_retain_v31_kernel_and_a4_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    task40 = profile_facts(TASK40_PROFILE)
    v31 = profile_facts(PROJECTION_LAYOUT_V31_PROFILE)
    for key in v31["route_selection"]:
        assert task40["route_selection"][key] == v31["route_selection"][key]
    for key in (
        "thread_selection",
        "p4_repair_policy",
        "coarse_refinement_exhaustion_policy",
        "a4_verification_action",
        "a4_action_oracle",
    ):
        assert task40[key] == v31[key]

    worker: dict[str, object] = {}

    def fake_worker(_payload, _run_directory, **kwargs):
        worker.update(kwargs)
        return {"mock_worker": True}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem
    from src.runners import task038_full3d_iterative as dispatch

    monkeypatch.setattr(
        lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_worker
    )
    specification = load_and_resolve(G0)
    result = dispatch.run_full3d_iterative(
        specification.as_jsonable(), tmp_path / "task40-worker", source_sha="b" * 40
    )
    assert result == {"mock_worker": True}
    assert worker["profile_identity"] == TASK40_PROFILE
    assert worker["coarse_degree"] == 4
    assert worker["allowed_stages"] == ("Q4_ORIGINAL",)
    assert worker["predecessor_by_stage"]["Q4_ORIGINAL"][
        "accepted_v31_route"
    ] == PROJECTION_LAYOUT_V31_PROFILE
    assert worker["write_rectangular_air_void_audit"] is True
    assert worker["write_geometry_audit"] is False


def test_real_watchdog_qualifies_a_small_child_tree_with_task_scope_swap(
    tmp_path: Path,
):
    source = """
import json
import math
from dataclasses import replace
from hashlib import sha256
import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import PHYSICAL_MEMORY_PRESSURE_POLICY, supervise
authority = supervise(
    [sys.executable, '-c', 'import time; time.sleep(1.0)'],
    Path(sys.argv[1]) / 'watchdog',
    wall_seconds=10.0, interval=0.1, grace_seconds=1.0,
    hard_stop_immediate=True, stop_on_global_swap=False,
    allow_swap_observation=False,
    memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
    pss_sampling_policy='disabled_by_profile',
)
keys = (
    'classification', 'process_tree_samples', 'process_tree_swap_gate_enforced',
    'global_swap_gate_enforced', 'process_tree_all_status_readable',
    'process_tree_identity_coverage', 'observed_child_identity_coverage',
    'sampled_process_tree_swap_peak_bytes', 'descendants_cleared',
)
print(json.dumps({key: authority.get(key) for key in keys}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    authority = json.loads(completed.stdout.strip().splitlines()[-1])
    assert authority["classification"] == "COMPLETED"
    assert authority["process_tree_samples"] >= 3
    assert authority["process_tree_swap_gate_enforced"] is True
    assert authority["global_swap_gate_enforced"] is False
    assert authority["process_tree_all_status_readable"] is True
    assert authority["process_tree_identity_coverage"] == "complete"
    assert authority["observed_child_identity_coverage"] == "complete"
    assert authority["sampled_process_tree_swap_peak_bytes"] == 0
    assert authority["descendants_cleared"] is True


def test_task40_swap_qualification_uses_task_tree_and_keeps_global_delta_diagnostic():
    authority = {
        "classification": "COMPLETED",
        "descendants_cleared": True,
        "process_tree_swap_gate_enforced": True,
        "process_tree_all_status_readable": True,
        "process_tree_identity_coverage": "complete",
        "observed_child_identity_coverage": "complete",
        "process_tree_samples": 12,
        "sampled_process_tree_swap_peak_bytes": 0,
        "global_swap_gate_enforced": False,
        "job_swap_activity": "UNRESOLVED_global_activity_cannot_be_attributed",
        "global_swap_activity": {"delta": {"pswpout": 1}},
    }
    qualified = launcher._task40_swap_qualification(authority)
    assert qualified["status"] == "qualified_zero"
    assert qualified["global_swap_activity"] == authority["global_swap_activity"]
    authority["process_tree_identity_coverage"] = "incomplete_or_not_sampled"
    assert launcher._task40_swap_qualification(authority)["status"] == "UNRESOLVED"


def test_task40_launcher_mock_keeps_service_scope_and_task_tree_swap_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    specification = load_and_resolve(G0)
    run_directory = tmp_path / "task40-launch"
    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-task40.service"
    )
    reservation: dict[str, object] = {}
    observed: dict[str, object] = {}

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir(parents=True, exist_ok=True)
        return run_directory

    def reserve(_repo_root, _run_directory, **kwargs):
        reservation.update(kwargs)
        return None

    monkeypatch.setattr(launcher, "_timestamp_directory", timestamp_directory)
    monkeypatch.setattr(launcher, "_reserve_task40_0p7nm_budget", reserve)
    monkeypatch.setattr(launcher, "current_cgroup_path", lambda: service_cgroup)
    monkeypatch.setattr(
        launcher,
        "_physical_source_gate",
        lambda *_args, **_kwargs: {
            "source_sha": "a" * 40,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    monkeypatch.setattr(
        launcher,
        "build_execution_plan",
        lambda *_args, **_kwargs: SimpleNamespace(
            adapter_available=True, argv=("mock-worker",), contract_probe=False
        ),
    )
    from benchmarks import subreaper_watchdog

    def fake_supervise(argv, *_args, **kwargs):
        observed["argv"] = list(argv)
        observed["kwargs"] = dict(kwargs)
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "UNRESOLVED_global_activity_cannot_be_attributed",
            "global_swap_activity": {"delta": {"pswpout": 1}},
            "launch_envelope": {"effective_total_bytes": 14 * 1024**3},
            "memory_scope": "dedicated subreaper plus every descendant",
            "samples": 12,
            "process_tree_samples": 12,
            "process_tree_swap_gate_enforced": True,
            "global_swap_gate_enforced": False,
            "process_tree_all_status_readable": True,
            "process_tree_identity_coverage": "complete",
            "observed_child_identity_coverage": "complete",
            "sampled_process_tree_swap_peak_bytes": 0,
            "descendants_cleared": True,
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    result = launcher.launch_specification(
        specification, source_sha="a" * 40, v14_time_policy="observe_only"
    )
    assert reservation["service_cgroup_path"] == service_cgroup
    assert observed["kwargs"]["allow_swap_observation"] is False
    assert observed["kwargs"]["stop_on_global_swap"] is False
    assert result["result_classification"] == "worker_exit0"
    assert result["swap_gate_enforced"] is True
    assert result["job_swap_qualification"] == "qualified_zero"
    assert result["task40_swap_qualification"]["global_swap_activity"] == {
        "delta": {"pswpout": 1}
    }
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["effective_watchdog_authority"][
        "legacy_resource_fields_enforced"
    ] is False
    assert manifest["effective_watchdog_authority"][
        "global_swap_gate_enforced"
    ] is False
    assert manifest["effective_watchdog_authority"][
        "process_tree_swap_gate_enforced"
    ] is True
    assert manifest["requested_legacy_resource_fields"]["terminate_memory_gib"] == 10.0
