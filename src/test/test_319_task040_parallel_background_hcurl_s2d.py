"""Task040 S2d: same-config z-layered bounded harmonic service."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.solvers.dtn_port_3d import Stage4ExternalLinearSolverSnapshot
from src.solvers.floquet_background_hcurl_block_service import (
    build_bounded_harmonic_packet,
    canonical_layout_hash,
    create_bounded_harmonic_service,
)
from src.solvers.floquet_background_hcurl_block_transform import (
    build_active_trace_bloch_layout,
    create_active_trace_bloch_transforms,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)
from src.test.test_319_task040_parallel_background_hcurl_s2a import _run_baseline
from src.test.test_319_task040_parallel_background_hcurl_s2c import (
    _config,
    _matrix_evidence,
    _record,
    _relative_residual,
    _rss_mib,
    _run_b0,
)

_RESIDUAL_LIMIT = 1.0e-9


class _S2dAuditStop(RuntimeError):
    def __init__(self, evidence):
        super().__init__("S2d audit completed before the ordinary solver path")
        self.evidence = evidence


def _assert_factor_audit(audit):
    keys = (
        "solve_relative_residual", "normwise_backward_error",
        "repeat_error", "linearity_error",
    )
    for item in audit["factor_solve_audit"]:
        for key in keys:
            assert math.isfinite(float(item[key]))
            assert item[key] <= 1.0e-10


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_task040_s2d_same_config_z_layered_bounded_service(tmp_path):
    comm = MPI.COMM_WORLD
    ordinary = target_stage4_config(degree=2, h_nm=100.0)
    background = _config(
        ordinary, ordinary.n_substrate, "task040_v9_e_s2d_background_p2_h100"
    )
    target = _config(
        ordinary, ordinary.n_substrate, "task040_v9_e_s2d_target_p2_h100"
    )
    assert background.n_substrate == target.n_substrate == ordinary.n_substrate
    assert background.n_grating == target.n_grating == ordinary.n_air
    assert background.stage4_dtn_order_policy == target.stage4_dtn_order_policy == "zero_order"
    packet_holder = {}

    def background_port(request):
        transforms = None
        local = {"rank": comm.rank, "matrix": _matrix_evidence(request)}
        try:
            layout = build_active_trace_bloch_layout(request)
            assert (layout.nx, layout.ny, layout.nz) == (3, 2, 4)
            assert (layout.active_rows, layout.auxiliary_rows) == (480, 4)
            transforms = create_active_trace_bloch_transforms(layout)
            packet = build_bounded_harmonic_packet(request, transforms)
            audit = packet.setup_audit
            assert audit["block_rows"] == [84, 80, 80, 80, 80, 80]
            assert audit["background_column_apply_count"] == 484
            assert audit["factor_count_global"] == 6
            assert audit["additional_absorbing_shift"] == 0.0
            assert max(audit["off_block_max"]) <= 1.0e-10
            _assert_factor_audit(audit)
            local.update({"layout_hash": packet.layout_hash, "audit": audit})
            packet_holder["packet"] = packet
        finally:
            if transforms is not None:
                transforms.destroy()
            local["lifecycle"] = {
                "background_QT_destroyed": transforms is None or transforms._destroyed,
                "background_packet_has_petcs": False,
                "background_A_borrowed": True,
            }
        local["rss_mib"] = _rss_mib()
        raise _S2dAuditStop({"status": "S2D_BACKGROUND_READY", "local": local})

    with pytest.raises(_S2dAuditStop) as background_caught:
        run_stage4b_block_grating_3d_case(
            background, tmp_path / "background", linear_solver_port=background_port
        )
    background_local = background_caught.value.evidence["local"]
    packet = packet_holder["packet"]
    assert packet.additional_absorbing_shift == 0.0j
    background_ranks = comm.allgather(background_local)
    assert sum(item["audit"]["factor_count_local"] for item in background_ranks) == 6

    target_holder = {}

    def target_port(request):
        transforms = None
        service = None
        baselines = {}
        local = {"rank": comm.rank, "matrix": _matrix_evidence(request)}
        selected_x = None
        try:
            layout = build_active_trace_bloch_layout(request)
            assert (layout.nx, layout.ny, layout.nz) == (3, 2, 4)
            assert (layout.active_rows, layout.auxiliary_rows) == (480, 4)
            transforms = create_active_trace_bloch_transforms(layout)
            assert canonical_layout_hash(layout) == packet.layout_hash
            service = create_bounded_harmonic_service(packet, transforms)
            direct_x = request.A.createVecRight()
            try:
                service.apply(request.b, direct_x)
                direct_residual = _relative_residual(request.A, request.b, direct_x)
            finally:
                direct_x.destroy()
            assert math.isfinite(direct_residual)
            direct_identity_pass = direct_residual <= _RESIDUAL_LIMIT
            baselines["identity"] = _run_baseline(request.A, request.b, "none")
            baselines["jacobi"] = _run_baseline(request.A, request.b, "jacobi")
            baselines["b1"] = _run_b0(request.A, request.b, service)
            best = min(
                baselines[name]["final_true_residual"]
                for name in ("identity", "jacobi")
            )
            b1 = baselines["b1"]
            improvement = best / max(b1["final_true_residual"], np.finfo(float).tiny)
            positive = improvement >= 8.0
            official_candidate = (
                b1["reason"] > 0
                and b1["final_true_residual"] <= _RESIDUAL_LIMIT
                and direct_identity_pass
            )
            local.update(
                {
                    "layout_hash": canonical_layout_hash(layout),
                    "baselines": {
                        name: _record(value) for name, value in baselines.items()
                    },
                    "direct_composite_true_residual": direct_residual,
                    "direct_composite_apply_count": 1,
                    "direct_composite_identity_pass": direct_identity_pass,
                    "best_identity_jacobi": best,
                    "improvement": improvement,
                    "b1_positive": positive,
                    "official_candidate": official_candidate,
                    "service_apply_count": service.apply_count,
                    "factor_solve_count_local": service.solve_count,
                }
            )
            if not positive or not official_candidate:
                raise _S2dAuditStop(
                    {
                        "status": "S2D_B1_GATE_NOT_CLOSED",
                        "local": local,
                    }
                )
            selected_x = baselines["b1"].pop("x")
            return Stage4ExternalLinearSolverSnapshot(
                x=selected_x,
                converged_reason=b1["reason"],
                iterations=b1["iterations"],
                reported_relative_residual=b1["reported_relative_residual"],
                condensed_true_residual=b1["final_true_residual"],
                full_augmented_true_residual=b1["final_true_residual"],
                ksp_type="fgmres",
                pc_type="python",
                residual_limit=_RESIDUAL_LIMIT,
                no_global_factor=True,
                solver_profile="s2d_same_config_z_layered_bounded_harmonic",
                reduced_residual_norm=b1["final_true_residual"] * b1["rhs_norm"],
            )
        finally:
            for value in baselines.values():
                if "x" in value:
                    value["x"].destroy()
            if service is not None:
                service.destroy()
            if transforms is not None:
                transforms.destroy()
            local["lifecycle"] = {
                "target_QT_destroyed": transforms is None or transforms._destroyed,
                "target_service_destroyed": service is None or service.destroyed,
                "target_A_borrowed": True,
                "background_petcs_retained": False,
                "selected_x_transferred": selected_x is not None,
            }
            local["rss_mib"] = _rss_mib()
            target_holder["local"] = local

    target_summary = run_stage4b_block_grating_3d_case(
        target, tmp_path / "target", linear_solver_port=target_port
    )
    target_ranks = comm.allgather(target_holder["local"])
    assert target_summary["external_linear_solver_port"] is True
    assert target_summary["external_rta_gate_pass"] is True
    assert target_summary["official_result"] is True
    assert target_summary["postprocess_skipped"] is False
    if comm.rank == 0:
        print(
            "S2D_EVIDENCE "
            + json.dumps(
                {
                    "status": "S2D_B1_SAME_CONFIG_READY",
                    "background": background_ranks,
                    "target": target_ranks,
                    "summary": {
                        key: target_summary.get(key)
                        for key in (
                            "case_status", "official_result",
                            "external_rta_gate_pass", "num_augmented_rows",
                            "stage4_dtn_num_auxiliary_dofs", "elapsed_seconds",
                        )
                    },
                },
                default=str,
                sort_keys=True,
            )
        )
