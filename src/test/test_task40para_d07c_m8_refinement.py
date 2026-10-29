"""Formal M8 inventory, exact B-y bisection, and worker identity tests; no PDE."""

from pathlib import Path

import numpy as np
import pytest

from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_d07c_axis_plan import d07c_axis_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import native_profile_facts
from src.runners.p6_condensed_direct import _direct_run_contract
from src.runners.task038_launcher import _write_bootstrap, build_execution_plan
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
from src.test.test_task40para_d07c_manifest_worker_contract import _worker_validate

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "case,cells,tags",
    [
        ("b", 936, {"1": 600, "2": 312, "3": 24}),
        ("y3", 1872, {"1": 1200, "2": 624, "3": 48}),
    ],
)
def test_formal_m8_input_mode_inventory_and_worker(case, cells, tags, tmp_path):
    spec = load_and_resolve(
        ROOT
        / f"input/task40para_phi90_mesh_modes_direct/d07c_{case}_m8_nminus143_to1_p6_direct.dat"
    )
    profile = spec.as_jsonable()["solver"]["native_capacity_profile"]
    route = _direct_run_contract(profile)
    facts = native_profile_facts(profile)
    assert route["expected_global_cell_count"] == cells
    assert route["task40_expected_material_tag_counts"] == tags
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["resources"]["concurrent_neighbor_authorized"] is False
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    axes = stage4_axis_plan(cfg, comm_size=1)
    assert np.prod(axes.mesh_cells_resolved) == cells
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(
        route["signed_rectangle_bounds_mn"]
    )
    cfg.stage4_dtn_quadrature_degree = route["surface_quadrature_degree"]
    cfg.task40_port_boundary_amplitude_scale_policy = route["mode_basis_scale_policy"]
    modes, rows, digest = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == 9860
    assert (
        digest
        == route["active_sha256"]
        == "5524a412514e85d243665050d7bf0f272c7f1347da338b03e2fbda22d257b057"
    )
    assert sum(m.propagating for m in modes) == 9664
    assert sum(m.power_per_unit_amplitude > 0 for m in modes) == 9764
    assert {(m.side, m.m, m.n, m.polarization) for m in modes} == {
        (side, m, n, pol)
        for side in ("top", "bottom")
        for m in range(-8, 9)
        for n in range(-143, 2)
        for pol in ("s", "p")
    }
    assert route["surface_quadrature_degree"] == 81
    directory = tmp_path / case
    directory.mkdir()
    import sys

    plan = build_execution_plan(
        spec,
        directory,
        source_sha="d07c" * 10,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
    )
    _, resolved_sha = _write_bootstrap(
        spec,
        directory,
        source_sha="d07c" * 10,
        adapter_identity=plan.adapter_identity,
        start_time="2026-10-29T00:00:00Z",
    )
    _, errors = _worker_validate(spec, directory, resolved_sha, plan)
    assert not errors


def test_y3_bisects_all_actual_b_y_edges_and_keeps_x_z():
    b, y = d07c_axis_plan("B"), d07c_axis_plan("Y3")
    for axis in ("x", "z"):
        assert b["axes_nm"][axis] == y["axes_nm"][axis]
        assert b["axis_sha256_le_f64"][axis] == y["axis_sha256_le_f64"][axis]
    np.testing.assert_array_equal(y["axes_nm"]["y"][::2], b["axes_nm"]["y"])
    np.testing.assert_array_equal(
        y["axes_nm"]["y"][1::2],
        (np.array(b["axes_nm"]["y"][:-1]) + b["axes_nm"]["y"][1:]) / 2,
    )
    assert y["segment_cell_counts"]["y"] == [20, 12, 20]
