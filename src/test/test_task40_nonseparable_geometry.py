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
    TASK40_COMPARISON_GROUP,
    TASK40_F1_REFERENCE_METRIC_RUN_ID,
    TASK40_F2_G0_M1_RUN_ID,
    TASK40_F3_G0_M2_RUN_ID,
    TASK40_F5_G1_M2_RUN_ID,
    TASK40_E1_RUN_ID,
    TASK40_E2_RUN_ID,
    TASK40_GX560_RUN_ID,
    TASK40_GZ528_RUN_ID,
    TASK40_GX784_RUN_ID,
    TASK40_REVIEW_V2_GROWTH_RUN_IDS,
    TASK40_AUTO_PROPAGATING_ENVELOPE_BY_MESH,
    TASK40_GEOMETRY_IDENTITY,
    TASK40_GEOMETRY_IDENTITY_BY_MESH,
    TASK40_PROFILE,
    TASK40_REFERENCE_METRIC_PROFILE,
    is_task40_geometry_identity,
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
from src.solvers.dtn_port_3d import _stage4_preserve_exact_geometry

ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
ELECTRICAL_AUTO_MODE_MANIFEST = (
    ROOT / "docs/task40extra_0p7nm_engineering/outcomes/records/"
    "electrical_size_auto_mode_envelopes_v1.json"
)
G0 = INPUT_ROOT / "nonseparable_g0_p6_q4.dat"
G1 = INPUT_ROOT / "nonseparable_g1_p6_q4.dat"
G0_REVIEW_V1 = INPUT_ROOT / "nonseparable_g0_p6_q4_review_v1.dat"
G1_REVIEW_V1 = INPUT_ROOT / "nonseparable_g1_p6_q4_review_v1.dat"
F1_REFERENCE_METRIC = INPUT_ROOT / "nonseparable_g1_p6_q4_reference_metric_f1.dat"
F2_G0_M1_MANUAL = INPUT_ROOT / "nonseparable_g0_p6_q4_manual_m1_f2.dat"
F3_G0_M2_MANUAL = INPUT_ROOT / "nonseparable_g0_p6_q4_manual_m2_f3.dat"
F5_G1_M2_MANUAL = INPUT_ROOT / "nonseparable_g1_p6_q4_manual_m2_f5.dat"
GX560_M2 = INPUT_ROOT / "nonseparable_gx560_p6_q4_manual_m2_v3.dat"
GZ528_M2 = INPUT_ROOT / "nonseparable_gz528_p6_q4_manual_m2_v3.dat"
GX784_M2 = INPUT_ROOT / "nonseparable_gx784_p6_q4_review_v5.dat"
E1_M2 = INPUT_ROOT / "nonseparable_e1_p6_q4_manual_m2_growth.dat"
E2_M2 = INPUT_ROOT / "nonseparable_e2_p6_q4_manual_m2_growth.dat"
G0_DIRECT = INPUT_ROOT / "nonseparable_g0_p6_direct_reference.dat"
B0_CONTROL = INPUT_ROOT / "b0_p4_balh_control_v10.dat"


def test_all_task40_inputs_resolve_to_the_frozen_physical_identity():
    resolved = [
        load_and_resolve(path)
        for path in (
            G0, G1, G0_DIRECT, G0_REVIEW_V1, G1_REVIEW_V1,
            F1_REFERENCE_METRIC, F2_G0_M1_MANUAL, F3_G0_M2_MANUAL,
            GX560_M2, GZ528_M2, GX784_M2,
        )
    ]
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
    assert resolved[3].physical_model_sha256 == resolved[0].physical_model_sha256
    assert resolved[4].physical_model_sha256 == resolved[1].physical_model_sha256
    assert resolved[3].method["kind"] == resolved[4].method["kind"] == (
        "full3d_iterative"
    )


def test_direct_reference_selects_exact_mesh_geometry_without_changing_old_profiles():
    specification = load_and_resolve(G0_DIRECT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())

    assert cfg.geometry_identity == TASK40_GEOMETRY_IDENTITY
    assert is_task40_geometry_identity(TASK40_GEOMETRY_IDENTITY)
    assert not is_task40_geometry_identity(None)
    assert cfg.stage4_full3d_assembly_backend == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    assert _stage4_preserve_exact_geometry(cfg) is True
    assert _stage4_preserve_exact_geometry(replace(cfg, geometry_identity=None)) is False
    assert all(
        _stage4_preserve_exact_geometry(
            replace(cfg, geometry_identity=TASK40_GEOMETRY_IDENTITY_BY_MESH[mesh_id])
        )
        for mesh_id in ("E1", "E2", "GX560", "GZ528", "GX784")
    )
    task40_gates = profile_facts(TASK40_PROFILE)["gates"]
    assert task40_gates["task40_geometry_identity_by_mesh"] == {
        mesh_id: TASK40_GEOMETRY_IDENTITY_BY_MESH[mesh_id]
        for mesh_id in ("G0", "G1", "E1", "E2", "GX560", "GZ528", "GX784")
    }


def test_review_v2_f5_and_electrical_inputs_bind_the_frozen_models():
    cases = (
        (F5_G1_M2_MANUAL, TASK40_F5_G1_M2_RUN_ID, "G1", 8, 2, 1.0),
        (E1_M2, TASK40_E1_RUN_ID, "E1", 10, 3, 1.25),
        (E2_M2, TASK40_E2_RUN_ID, "E2", 12, 3, 1.5),
    )
    base = load_and_resolve(G0_REVIEW_V1)
    for path, run_id, mesh_id, max_m, max_n, scale in cases:
        specification = load_and_resolve(path)
        config = specification.as_jsonable()
        validate_task40_input(config)
        plan = task40_mesh_plan(mesh_id)
        assert specification.identity["run_id"] == run_id
        assert specification.geometry["geometry_identity"] == (
            TASK40_GEOMETRY_IDENTITY_BY_MESH[mesh_id]
        )
        assert specification.incidence["wavelength_nm"] == 0.7
        assert specification.boundary["dtn_order_policy"] == "manual"
        assert specification.boundary["dtn_manual_order_max_m"] == max_m
        assert specification.boundary["dtn_manual_order_max_n"] == max_n
        assert specification.output["diffraction_order_max_m"] == max_m
        assert specification.output["diffraction_order_max_n"] == max_n
        assert specification.discretization["mesh_axis_cell_counts"] == tuple(
            plan["axis_interval_counts"][axis] for axis in ("x", "y", "z")
        )
        assert specification.discretization["mesh_plan_sha256"] == plan[
            "mesh_plan_sha256"
        ]
        assert specification.geometry["period_x_nm"] == pytest.approx(
            base.geometry["period_x_nm"] * scale
        )
        assert specification.geometry["air_void_box_nm"] == pytest.approx(
            tuple(value * scale for value in base.geometry["air_void_box_nm"])
        )
        assert specification.materials["n_substrate"] == base.materials[
            "n_substrate"
        ]


def test_task40_electrical_auto_modes_match_the_saved_ordered_manifest():
    from src.common.modes_3d import outgoing_port_modes_3d

    record = json.loads(ELECTRICAL_AUTO_MODE_MANIFEST.read_text(encoding="utf-8"))
    assert record["schema"] == "task40extra.electrical-size-auto-modes.v1"
    for mesh_id, path in (("E1", E1_M2), ("E2", E2_M2)):
        specification = load_and_resolve(path)
        cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
        auto_cfg = replace(
            cfg,
            stage4_dtn_order_policy="auto_propagating",
            diffraction_order_max_m=None,
            diffraction_order_max_n=None,
        )
        modes = outgoing_port_modes_3d(auto_cfg)
        actual_keys = [
            [mode.side, mode.m, mode.n, mode.polarization]
            for mode in modes if mode.propagating
        ]
        expected = record["cases"][mesh_id]
        assert actual_keys == expected["ordered_propagating_mode_keys"]
        assert len(actual_keys) == expected["propagating_mode_count"]
        input_bytes = path.read_bytes()
        assert sha256(input_bytes).hexdigest() == expected["input_sha256"]
        assert specification.physical_model_sha256 == expected[
            "physical_model_sha256"
        ]
        generator_sha256 = sha256(
            (ROOT / record["mode_generator"]["path"]).read_bytes()
        ).hexdigest()
        assert generator_sha256 == record["mode_generator"]["sha256"]
        digest = sha256(
            json.dumps(
                actual_keys, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        assert digest == expected["ordered_mode_keys_sha256"]
        envelope = (
            max(abs(row[1]) for row in actual_keys),
            max(abs(row[2]) for row in actual_keys),
        )
        assert envelope == tuple(expected["auto_propagating_envelope"])
        assert envelope == TASK40_AUTO_PROPAGATING_ENVELOPE_BY_MESH[mesh_id]
        assert tuple(expected["manual_m2_bounds"]) == (
            envelope[0] + 1,
            envelope[1] + 1,
        )
        assert len(outgoing_port_modes_3d(cfg)) == expected["manual_mode_count"]


def test_electrical_mesh_plans_scale_exact_planes_at_fixed_h():
    expected = {
        "G0": ((6, 4, 14), 336, 0.5185185185185185),
        "G1": ((10, 4, 22), 880, 0.3888888888888889),
        "E1": ((10, 4, 19), 760, 0.5185185185185185),
        "E2": ((10, 4, 22), 880, 0.5185185185185185),
        "GX560": ((10, 4, 14), 560, 0.5185185185185185),
        "GZ528": ((6, 4, 22), 528, 0.5185185185185185),
        "GX784": ((14, 4, 14), 784, 0.5185185185185185),
    }
    for mesh_id, (counts, cells, target_h) in expected.items():
        plan = task40_mesh_plan(mesh_id)
        assert tuple(plan["axis_interval_counts"][axis] for axis in "xyz") == counts
        assert plan["expected_hexahedra"] == cells
        assert plan["target_h_nm"] == pytest.approx(target_h, abs=1e-15)
    assert task40_mesh_plan("G0")["mesh_plan_sha256"] == (
        "d621678ed8f144246133a98a71a2805bf55d09104d3aa6ceeb55e3f16fb864f1"
    )
    assert task40_mesh_plan("G1")["mesh_plan_sha256"] == (
        "2e7e0a76c2161bfc0651c89d8c5e6edfa2a1ed37d1e2b5a674e314c6c5f5c27d"
    )
    assert task40_mesh_plan("GX784")["mesh_plan_sha256"] == (
        "00760c10b132911a40c84ae5950742dcbd0086af2b26732be628ea08346b88d1"
    )
    g0, g1 = task40_mesh_plan("G0"), task40_mesh_plan("G1")
    for mesh_id, sources in (
        ("GX560", {"x": g1, "y": g0, "z": g0}),
        ("GZ528", {"x": g0, "y": g0, "z": g1}),
    ):
        plan = task40_mesh_plan(mesh_id)
        assert plan["mesh_plan_id"] == f"task40extra.{mesh_id.lower()}.crossed_axes.v1"
        for axis, source in sources.items():
            assert plan["axis_coordinates_nm"][axis] == source["axis_coordinates_nm"][axis]
    gx560 = task40_mesh_plan("GX560")
    gx784 = task40_mesh_plan("GX784")
    for axis in ("y", "z"):
        assert gx784["axis_coordinates_nm"][axis] == gx560["axis_coordinates_nm"][axis]
    assert gx784["axis_segment_interval_counts"]["x"] == [4, 3, 3, 4]
    assert gx784["mesh_plan_id"] == "task40extra.gx784.review_v5.crossed_axes.v1"


def test_review_v3_crossed_inputs_bind_the_preregistered_m2_cases():
    cases = (
        (GX560_M2, TASK40_GX560_RUN_ID, "GX560", (10, 4, 14)),
        (GZ528_M2, TASK40_GZ528_RUN_ID, "GZ528", (6, 4, 22)),
        (GX784_M2, TASK40_GX784_RUN_ID, "GX784", (14, 4, 14)),
    )
    base = load_and_resolve(F3_G0_M2_MANUAL)
    for path, run_id, mesh_id, counts in cases:
        specification = load_and_resolve(path)
        validate_task40_input(specification.as_jsonable())
        plan = task40_mesh_plan(mesh_id)
        assert specification.identity["run_id"] == run_id
        assert specification.identity["comparison_group"] == TASK40_COMPARISON_GROUP
        assert specification.geometry == base.geometry
        assert specification.materials == base.materials
        assert specification.incidence == base.incidence
        assert specification.discretization["nedelec_degree"] == 6
        assert specification.discretization["mesh_axis_cell_counts"] == counts
        assert specification.discretization["mesh_plan_id"] == plan["mesh_plan_id"]
        assert specification.discretization["mesh_plan_sha256"] == plan[
            "mesh_plan_sha256"
        ]
        assert specification.boundary["dtn_order_policy"] == "manual"
        assert (
            specification.boundary["dtn_manual_order_max_m"],
            specification.boundary["dtn_manual_order_max_n"],
        ) == (8, 2)
        assert specification.solver["preconditioner"] == (
            TASK40_REFERENCE_METRIC_PROFILE
        )


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
        (B0_CONTROL, "B0", (4, 4, 5), {1: 42, 2: 16, 3: 22}, 2),
        (G0, "G0", (6, 4, 14), {1: 224, 2: 24, 3: 88}, 8),
        (G1, "G1", (10, 4, 22), {1: 536, 2: 80, 3: 264}, 24),
        (E1_M2, "E1", (10, 4, 19), {1: 460, 2: 80, 3: 220}, 20),
        (E2_M2, "E2", (10, 4, 22), {1: 536, 2: 80, 3: 264}, 24),
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
    if mesh_id == "B0":
        actual_axes = {
            axis: np.unique(mesh_data.mesh.geometry.x[:, index])
            for index, axis in enumerate(("x", "y", "z"))
        }
        for axis in ("x", "y", "z"):
            assert np.array_equal(
                actual_axes[axis], np.asarray(plan["axis_coordinates_nm"][axis])
            )
        assert cfg.geometry_model_variant == "original"
        assert cfg.geometry_identity == "task40extra_nonseparable_0p7nm_v1"
        assert audit["owned_void_box_cell_count"] == 2
        assert audit["non_air_tagged_void_box_cell_count"] == 0


def test_task40_same_mesh_levels_preserve_air_void_audit_metadata():
    from mpi4py import MPI
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels

    specification = load_and_resolve(G0)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6, 4), include_positive_coefficients=False
    )
    mesh_data = levels["mesh_data"]
    audit = mesh_data.rectangular_air_void_audit

    assert audit["status"] == "PASS"
    assert audit["geometry_identity"] == TASK40_GEOMETRY_IDENTITY
    assert audit["owned_void_box_cell_count"] == 8
    assert audit["non_air_tagged_void_box_cell_count"] == 0
    assert {axis: stats["num_cells"] for axis, stats in mesh_data.mesh_axis_cell_stats.items()} == {
        "x": 6,
        "y": 4,
        "z": 14,
    }
    assert mesh_data.material_plane_alignment["all_aligned"] is True


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


@pytest.mark.parametrize(
    "input_path",
    (G0_REVIEW_V1, F1_REFERENCE_METRIC, F5_G1_M2_MANUAL, E1_M2, E2_M2),
)
def test_task40_launcher_mock_keeps_service_scope_and_task_tree_swap_gate(
    input_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    specification = load_and_resolve(input_path)
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
    assert reservation["run_id"] == specification.identity["run_id"]
    assert reservation["comparison_group"] == TASK40_COMPARISON_GROUP
    assert observed["kwargs"]["time_policy"] == "observe_only"
    assert observed["kwargs"]["memory_policy"] == profile_facts(
        specification.solver["preconditioner"]
    )["resources"]["watchdog_memory_policy"]
    assert observed["kwargs"]["pss_sampling_policy"] == "disabled_by_profile"
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


def test_task40_p3_manual_inputs_select_exact_m1_m2_mode_sets(tmp_path: Path):
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest

    baseline = load_and_resolve(G0_REVIEW_V1)
    baseline_cfg = simulation_config_3d_from_normalized(baseline.as_jsonable())
    baseline_modes = outgoing_port_modes_3d(baseline_cfg)
    _, _, baseline_mode_sha = build_ordered_mode_manifest(baseline_modes, baseline_cfg)
    propagating = {
        (mode.side, mode.m, mode.n, mode.polarization)
        for mode in baseline_modes if mode.propagating
    }
    assert len(baseline_modes) == 80

    cases = (
        (F2_G0_M1_MANUAL, TASK40_F2_G0_M1_RUN_ID, (7, 1), 180),
        (F3_G0_M2_MANUAL, TASK40_F3_G0_M2_RUN_ID, (8, 2), 340),
    )
    prior_manual_mode_sha = None
    for path, run_id, bounds, expected_count in cases:
        specification = load_and_resolve(path)
        validate_task40_input(specification.as_jsonable())
        assert specification.identity["run_id"] == run_id
        assert specification.geometry == baseline.geometry
        assert specification.materials == baseline.materials
        assert specification.incidence == baseline.incidence
        assert specification.discretization["mesh_axis_cell_counts"] == (6, 4, 14)
        cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
        assert cfg.stage4_dtn_order_policy == "manual"
        assert (cfg.diffraction_order_max_m, cfg.diffraction_order_max_n) == bounds
        modes = outgoing_port_modes_3d(cfg)
        manifest, _, mode_sha = build_ordered_mode_manifest(modes, cfg)
        keys = {(mode.side, mode.m, mode.n, mode.polarization) for mode in modes}
        assert len(modes) == expected_count
        assert len(manifest) == expected_count
        assert mode_sha != baseline_mode_sha
        if prior_manual_mode_sha is not None:
            assert mode_sha != prior_manual_mode_sha
        prior_manual_mode_sha = mode_sha
        assert propagating <= keys
        assert {mode.polarization for mode in modes} <= {"s", "p"}
        assert min(mode.m for mode in modes) == -bounds[0]
        assert max(mode.m for mode in modes) == bounds[0]
        assert min(mode.n for mode in modes) == -bounds[1]
        assert max(mode.n for mode in modes) == bounds[1]
        assert specification.solver["preconditioner"] == (
            "task40extra_0p7nm_p6trace_p4_reference_metric_v2"
        )

    bad_missing_bound = tmp_path / "manual_missing_n.dat"
    bad_missing_bound.write_text(
        F2_G0_M1_MANUAL.read_text(encoding="utf-8").replace(
            "dtn_manual_order_max_n = 1\n", "", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="required with dtn_order_policy=manual"):
        load_and_resolve(bad_missing_bound)

    bad_report_bound = tmp_path / "manual_output_bound_too_small.dat"
    bad_report_bound.write_text(
        F2_G0_M1_MANUAL.read_text(encoding="utf-8").replace(
            "diffraction_order_max_m = 7", "diffraction_order_max_m = 6", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="must cover boundary"):
        load_and_resolve(bad_report_bound)

    m1_cfg = simulation_config_3d_from_normalized(
        load_and_resolve(F2_G0_M1_MANUAL).as_jsonable()
    )
    with pytest.raises(ValueError, match="retain every propagating order"):
        outgoing_port_modes_3d(replace(m1_cfg, diffraction_order_max_m=6))


def test_task40_review_v1_batch_separates_old_cost_and_shares_one_replay(
    tmp_path: Path,
):
    from src.runners.task038_full3d_iterative import _task40_worker_batch_identity
    from src.runners.workflow_timebase import clock_sample

    old_run_id = "task40extra_0p7nm_nonseparable_g0_iterative_v1"
    old_ledger_path = (
        tmp_path / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        "task40_nonseparable_0p7nm" / old_run_id / "shared_workflow_ledger.json"
    )
    old_ledger_path.parent.mkdir(parents=True)
    old_ledger_path.write_text(
        json.dumps(
            {
                "schema": "task40extra.nonseparable-0p7nm.shared-workflow-ledger.v1",
                "batch_identity": old_run_id,
                "unique_bug_replay_count": 3,
                "elapsed_seconds": 900.0,
                "conservative_allowance_seconds": 120.0,
                "fresh_worker_count": 4,
            }
        ),
        encoding="utf-8",
    )

    g0 = load_and_resolve(G0_REVIEW_V1)
    assert g0.physical_model_sha256 == load_and_resolve(G0).physical_model_sha256
    assert _task40_worker_batch_identity(g0.as_jsonable()) == g0.identity["run_id"]
    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-task40-fixture.service"
    )

    def reserve(specification, directory: str, source: str):
        return launcher._reserve_task40_0p7nm_budget(
            tmp_path,
            tmp_path / directory,
            source_sha=source,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start=clock_sample(),
            time_policy="observe_only",
            run_id=str(specification.identity["run_id"]),
            comparison_group=str(specification.identity["comparison_group"]),
            service_cgroup_path=service_cgroup,
        )

    g0_reservation = reserve(g0, "review-g0-run", "a" * 40)
    g0_ledger = json.loads(Path(g0_reservation["path"]).read_text(encoding="utf-8"))
    g0_accounting = json.loads(
        Path(g0_reservation["task40_batch_replay_accounting_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert g0_ledger["batch_identity"] == g0.identity["run_id"]
    assert g0_reservation["replay"] is False
    assert g0_accounting["legacy"]["unique_bug_replay_count"] == 3
    assert g0_accounting["legacy"]["elapsed_seconds"] == 900.0
    assert g0_accounting["review_v1"]["unique_bug_replay_count"] == 0
    assert g0_accounting["selected_bug_replay_limit"] == 1

    # Consume the one shared review-v1 repair allowance in G0.  G1 must see
    # this count, while the old 3-replay history stays in its own accounting.
    g0_ledger["unique_bug_replay_count"] = 1
    Path(g0_reservation["path"]).write_text(
        json.dumps(g0_ledger), encoding="utf-8"
    )
    g1 = load_and_resolve(G1_REVIEW_V1)
    assert g1.physical_model_sha256 == load_and_resolve(G1).physical_model_sha256
    assert _task40_worker_batch_identity(g1.as_jsonable()) == g1.identity["run_id"]
    g1_reservation = reserve(g1, "review-g1-run", "b" * 40)
    g1_accounting = json.loads(
        Path(g1_reservation["task40_batch_replay_accounting_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert g1_reservation["replay"] is False
    assert g1_accounting["legacy"]["unique_bug_replay_count"] == 3
    assert g1_accounting["review_v1"]["unique_bug_replay_count"] == 1
    assert g1_accounting["selected_bug_replay_limit"] == 0

    f1 = load_and_resolve(F1_REFERENCE_METRIC)
    assert f1.physical_model_sha256 == load_and_resolve(G1).physical_model_sha256
    assert _task40_worker_batch_identity(f1.as_jsonable()) == TASK40_F1_REFERENCE_METRIC_RUN_ID
    f1_reservation = reserve(f1, "review-v2-f1-run", "c" * 40)
    f1_accounting = json.loads(
        Path(f1_reservation["task40_batch_replay_accounting_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert f1_reservation["replay"] is False
    assert f1_accounting["selected_batch"] == "review_v2_f1"
    assert f1_accounting["legacy"]["unique_bug_replay_count"] == 3
    assert f1_accounting["review_v1"]["unique_bug_replay_count"] == 1
    assert f1_accounting["review_v2_f1"]["run_ids"] == [
        TASK40_F1_REFERENCE_METRIC_RUN_ID
    ]
    assert f1_accounting["selected_bug_replay_limit"] == 1


def test_task40_review_v2_p3_batches_share_only_their_own_replay_allowance(
    tmp_path: Path,
):
    from src.runners.task038_full3d_iterative import _task40_worker_batch_identity
    from src.runners.workflow_timebase import clock_sample

    ledger_root = (
        tmp_path / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        "task40_nonseparable_0p7nm"
    )
    def write_history(run_id: str, bug_replays: int, infra_recoveries: int = 0):
        path = ledger_root / run_id / "shared_workflow_ledger.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "task40extra.nonseparable-0p7nm.shared-workflow-ledger.v1",
            "batch_identity": run_id,
            "unique_bug_replay_count": bug_replays,
            "infrastructure_recovery_count": infra_recoveries,
            "elapsed_seconds": 0.0,
            "conservative_allowance_seconds": 0.0,
            "fresh_worker_count": 1,
        }), encoding="utf-8")
        return path

    write_history("task40extra_0p7nm_nonseparable_g0_iterative_v1", 4)
    write_history(TASK40_F1_REFERENCE_METRIC_RUN_ID, 2, 1)
    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-task40-fixture.service"
    )
    def reserve(path: Path, name: str, source: str):
        specification = load_and_resolve(path)
        assert _task40_worker_batch_identity(specification.as_jsonable()) == (
            specification.identity["run_id"]
        )
        return launcher._reserve_task40_0p7nm_budget(
            tmp_path, tmp_path / name, source_sha=source, stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start=clock_sample(), time_policy="observe_only",
            run_id=str(specification.identity["run_id"]),
            comparison_group=str(specification.identity["comparison_group"]),
            service_cgroup_path=service_cgroup,
        )

    f2_reservation = reserve(F2_G0_M1_MANUAL, "f2-m1", "d" * 40)
    f2_accounting = json.loads(
        Path(f2_reservation["task40_batch_replay_accounting_path"]).read_text()
    )
    assert f2_accounting["selected_batch"] == "review_v2_p3"
    assert f2_accounting["review_v2_p3"]["run_ids"] == sorted(
        [TASK40_F2_G0_M1_RUN_ID, TASK40_F3_G0_M2_RUN_ID]
    )
    assert f2_accounting["review_v2_p3"]["unique_bug_replay_count"] == 0
    assert f2_accounting["review_v2_f1"]["unique_bug_replay_count"] == 2
    assert f2_accounting["legacy"]["unique_bug_replay_count"] == 4
    assert f2_accounting["selected_bug_replay_limit"] == 1

    f2_ledger_path = Path(f2_reservation["path"])
    f2_ledger = json.loads(f2_ledger_path.read_text())
    f2_ledger["unique_bug_replay_count"] = 1
    f2_ledger_path.write_text(json.dumps(f2_ledger), encoding="utf-8")
    f3_reservation = reserve(F3_G0_M2_MANUAL, "f3-m2", "e" * 40)
    f3_accounting = json.loads(
        Path(f3_reservation["task40_batch_replay_accounting_path"]).read_text()
    )
    assert f3_accounting["selected_batch"] == "review_v2_p3"
    assert f3_accounting["review_v2_p3"]["unique_bug_replay_count"] == 1
    assert f3_accounting["review_v2_f1"]["unique_bug_replay_count"] == 2
    assert f3_accounting["selected_bug_replay_limit"] == 2


def test_task40_review_v2_growth_batch_admits_f5_e1_e2_and_keeps_old_costs(
    tmp_path: Path,
):
    from src.runners.task038_full3d_iterative import _task40_worker_batch_identity
    from src.runners.workflow_timebase import clock_sample

    legacy_run_id = "task40extra_0p7nm_nonseparable_g0_iterative_v1"
    legacy_ledger = (
        tmp_path / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
        "task40_nonseparable_0p7nm" / legacy_run_id / "shared_workflow_ledger.json"
    )
    legacy_ledger.parent.mkdir(parents=True)
    legacy_ledger.write_text(json.dumps({
        "schema": "task40extra.nonseparable-0p7nm.shared-workflow-ledger.v1",
        "batch_identity": legacy_run_id,
        "unique_bug_replay_count": 4,
        "elapsed_seconds": 900.0,
        "conservative_allowance_seconds": 120.0,
        "fresh_worker_count": 3,
    }), encoding="utf-8")
    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-task40-fixture.service"
    )

    for index, path in enumerate((F5_G1_M2_MANUAL, E1_M2, E2_M2)):
        specification = load_and_resolve(path)
        run_id = str(specification.identity["run_id"])
        assert _task40_worker_batch_identity(specification.as_jsonable()) == run_id
        reservation = launcher._reserve_task40_0p7nm_budget(
            tmp_path,
            tmp_path / f"growth-{index}",
            source_sha=chr(ord("a") + index) * 40,
            stage="Q4_ORIGINAL",
            stage_budget={"workflow_seconds": 43200.0},
            workflow_clock_start=clock_sample(),
            time_policy="observe_only",
            run_id=run_id,
            comparison_group=str(specification.identity["comparison_group"]),
            service_cgroup_path=service_cgroup,
        )
        accounting = json.loads(
            Path(reservation["task40_batch_replay_accounting_path"]).read_text(
                encoding="utf-8"
            )
        )
        assert reservation["replay"] is False
        assert accounting["selected_batch"] == "review_v2_growth"
        assert accounting["review_v2_growth"]["run_ids"] == sorted(
            TASK40_REVIEW_V2_GROWTH_RUN_IDS
        )
        assert accounting["legacy"]["unique_bug_replay_count"] == 4
        assert accounting["legacy"]["elapsed_seconds"] == 900.0
        assert accounting["selected_bug_replay_limit"] == (1 if index == 0 else 2)
        if index == 0:
            prior_growth_ledger = Path(reservation["path"])
            ledger = json.loads(prior_growth_ledger.read_text(encoding="utf-8"))
            ledger["unique_bug_replay_count"] = 1
            prior_growth_ledger.write_text(json.dumps(ledger), encoding="utf-8")


def test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task038_full3d_iterative import _task40_worker_batch_identity
    from src.runners.workflow_timebase import clock_sample

    specification = load_and_resolve(G0_REVIEW_V1)
    assert specification.physical_model_sha256 == load_and_resolve(G0).physical_model_sha256
    payload = specification.as_jsonable()
    run_id = str(specification.identity["run_id"])
    assert _task40_worker_batch_identity(payload) == run_id
    with pytest.raises(ValueError, match="frozen iterative case"):
        _task40_worker_batch_identity(load_and_resolve(G0_DIRECT).as_jsonable())

    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
        "app.slice/myfenics-case-task40-fixture.service"
    )
    source_sha = "a" * 40
    reservation = launcher._reserve_task40_0p7nm_budget(
        tmp_path,
        tmp_path / "reserved-run",
        source_sha=source_sha,
        stage="Q4_ORIGINAL",
        stage_budget={"workflow_seconds": 43200.0},
        workflow_clock_start=clock_sample(),
        time_policy="observe_only",
        run_id=run_id,
        comparison_group=str(specification.identity["comparison_group"]),
        service_cgroup_path=service_cgroup,
    )
    ledger = json.loads(Path(reservation["path"]).read_text(encoding="utf-8"))
    assert ledger["batch_identity"] == run_id
    assert reservation["replay"] is False
    monkeypatch.setenv("PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH", reservation["path"])
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX",
        str(reservation["attempt_index"]),
    )
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_MEMORY_POLICY",
        "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PSS_POLICY", "disabled_by_profile")
    contract = {
        "resources": {
            "watchdog_memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
            "pss_sampling_policy": "disabled_by_profile",
        }
    }
    runtime = _V14Runtime(
        tmp_path / "runtime",
        "Q4_ORIGINAL",
        contract,
        root=tmp_path,
        source_sha=source_sha,
        batch_identity=_task40_worker_batch_identity(payload),
        evidence_prefix="task40q4",
        require_zero_swap=True,
    )
    assert runtime.shared_attempt["source_sha"] == source_sha
    assert runtime.shared_attempt["status"] == "RESERVED"
    with pytest.raises(RuntimeError, match="parent ledger batch identity changed"):
        _V14Runtime(
            tmp_path / "wrong-runtime",
            "Q4_ORIGINAL",
            contract,
            root=tmp_path,
            source_sha=source_sha,
            batch_identity="task40extra_0p7nm_nonseparable_p6q4_v1",
            evidence_prefix="task40q4",
            require_zero_swap=True,
        )


def _task40_capacity_carrier(global_rows: int, sides: tuple[str, ...]):
    entries = []
    for side in sides:
        entries.append(
            SimpleNamespace(
                mode_identity={"side": side},
                coupling_rows=np.asarray([0], dtype=np.int32),
                coupling_values=np.asarray([1.0 + 0.0j], dtype=np.complex128),
                projection_rows=np.asarray([0], dtype=np.int32),
                projection_values=np.asarray([1.0 + 0.0j], dtype=np.complex128),
            )
        )
    return SimpleNamespace(global_rows=global_rows, entries=entries)


@pytest.mark.parametrize(
    ("input_path", "expected_mesh_id", "raw_classes", "oriented_classes"),
    (
        (G0, "G0", 3, 7),
        (G1, "G1", 5, 11),
        (E1_M2, "E1", 3, 7),
        (E2_M2, "E2", 5, 11),
    ),
)
def test_task40_capacity_context_binds_frozen_axes_and_live_class_metadata(
    input_path: Path,
    expected_mesh_id: str,
    raw_classes: int,
    oriented_classes: int,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.runners import physical_p4_schur_v14 as v14
    from src.runners import physical_dual_cell_condensed_lowmem_v20 as condensed
    from src.runners import physical_retained_outer_adapter as retained_outer
    from src.solvers import hcurl_assembly_time_condensation as capacity

    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    fine = _task40_capacity_carrier(100, ("top", "top", "bottom", "bottom"))
    coarse = _task40_capacity_carrier(20, ())
    common = {
        "cfg": cfg,
        "coarse_degree": 4,
        "fine": {"dtn_action": SimpleNamespace(carrier=fine)},
        "p4": {"dtn_action": SimpleNamespace(carrier=coarse)},
        "levels": {
            "mesh_data": SimpleNamespace(mesh=object(), cell_tags=object())
        },
    }
    p6_space_facts = {
        "full_rows": 100,
        "trace_rows": 12,
        "active_rows": 10,
        "slave_rows": 2,
        "slave_master_entry_count": 2,
        "appended_rows": 4,
        "local_tensor_dimension": 882,
        "local_interior_dimension": 450,
        "local_trace_dimension": 432,
    }
    p4_metadata = {
        "q4_raw_class_count": raw_classes,
        "q4_oriented_class_count": oriented_classes,
        "xiB_payload_estimate_bytes": 32,
    }
    captured_capacity_facts: dict[str, object] = {}
    captured_geometry_count: dict[str, object] = {}
    monkeypatch.setattr(
        v14,
        "_v14_balanced_apply_workspace_bytes",
        lambda *_args: 100,
    )
    monkeypatch.setattr(
        v14,
        "_v14_balanced_h6_setup_facts",
        lambda _common: {"component_payload_bytes": 40, "setup_estimate_bytes": 80},
    )
    monkeypatch.setattr(
        v14,
        "_v14_outer_krylov_workspace_bytes",
        lambda *_args, **_kwargs: 300,
    )
    monkeypatch.setattr(
        retained_outer,
        "_retained_outer_scratch_workspace_bytes",
        lambda *_args: 200,
    )

    def capacity_facts(**kwargs):
        captured_capacity_facts.update(kwargs)
        return {"retained_numeric_bytes_upper": 123, "workspace_bytes_upper": 456}

    monkeypatch.setattr(capacity, "assembly_time_condensation_capacity_facts", capacity_facts)

    def geometry_class_counts(mesh, cell_tags, *, preserve_exact_geometry):
        captured_geometry_count.update(
            {
                "mesh": mesh,
                "cell_tags": cell_tags,
                "preserve_exact_geometry": preserve_exact_geometry,
            }
        )
        return {
            "raw_class_count": raw_classes + 2,
            "oriented_class_count": oriented_classes + 3,
        }

    monkeypatch.setattr(
        capacity, "assembly_time_geometry_class_counts", geometry_class_counts
    )
    context = condensed.v22_capacity_context(
        common,
        cfg=cfg,
        p6_space_facts=p6_space_facts,
        p4_metadata=p4_metadata,
        coarse_degree=4,
        evidence_prefix="task40q4",
        task40_profile=True,
    )
    identity = context["identity"]
    assert context["schema"] == "task40extra.nonseparable-0p7nm.capacity-context.v1"
    assert identity["geometry_identity"] == TASK40_GEOMETRY_IDENTITY_BY_MESH[
        expected_mesh_id
    ]
    if expected_mesh_id in {"G0", "G1"}:
        expected_plan_id = (
            f"task40extra.{expected_mesh_id.lower()}.exact_planes.v1"
        )
    elif expected_mesh_id in {"GX560", "GZ528"}:
        expected_plan_id = (
            f"task40extra.{expected_mesh_id.lower()}.crossed_axes.v1"
        )
    else:
        expected_plan_id = (
            f"task40extra.{expected_mesh_id.lower()}.electrical_size_exact_planes.v1"
        )
    assert identity["mesh_plan_id"] == expected_plan_id
    assert identity["mesh_plan_sha256"] == cfg.mesh_plan_sha256
    assert identity["mesh_axis_cell_counts"] == list(cfg.mesh_axis_cell_counts_requested)
    assert identity["owned_cell_count"] == int(np.prod(cfg.mesh_axis_cell_counts_requested))
    assert identity["n6"] == 100 and identity["n4"] == 20
    assert identity["p6_port_count"] == 4
    assert identity["p6_full_rows"] == 100
    assert identity["p6_trace_rows"] == 12
    assert identity["p6_active_trace_rows"] == 10
    assert identity["p6_slave_rows"] == 2
    assert identity["coarse_class_counts"] == {
        "raw": raw_classes,
        "oriented": oriented_classes,
    }
    assert identity["p6_capacity_class_counts"] == {
        "raw": raw_classes + 2,
        "oriented": oriented_classes + 3,
    }
    assert captured_geometry_count["mesh"] is common["levels"]["mesh_data"].mesh
    assert captured_geometry_count["cell_tags"] is common["levels"]["mesh_data"].cell_tags
    assert captured_geometry_count["preserve_exact_geometry"] is True
    assert captured_capacity_facts["dimension"] == 882
    assert captured_capacity_facts["interior_dimension"] == 450
    assert captured_capacity_facts["trace_dimension"] == 432
    assert captured_capacity_facts["raw_class_count"] == raw_classes + 2
    assert captured_capacity_facts["oriented_class_count"] == oriented_classes + 3
    assert context["derived_sources"]["p6_class_capacity"]["classification"] == (
        "derived_estimate_from_live_exact_mesh_geometry_classes"
    )

    wrong_plan_cfg = replace(cfg, mesh_plan_sha256="0" * 64)
    with pytest.raises(ValueError, match="mesh plan SHA differs"):
        condensed.v22_capacity_context(
            common,
            cfg=wrong_plan_cfg,
            p6_space_facts=p6_space_facts,
            p4_metadata=p4_metadata,
            coarse_degree=4,
            evidence_prefix="task40q4",
            task40_profile=True,
        )
