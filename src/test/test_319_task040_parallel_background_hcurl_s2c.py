"""Task040 S2c: owner-local constant-background harmonic service."""

from __future__ import annotations

import json
import math
import resource
import time
from dataclasses import replace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    target_stage4_config,
)
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

_TINY = np.finfo(float).tiny
_RESIDUAL_LIMIT = 1.0e-9


class _S2cAuditStop(RuntimeError):
    def __init__(self, evidence):
        super().__init__("S2c audit completed before the ordinary solver path")
        self.evidence = evidence


class _BoundedPc:
    def __init__(self, service):
        self.service = service
        self.apply_count = 0
        self.destroyed = False

    def apply(self, _pc, source, target):
        if self.destroyed:
            raise RuntimeError("S2c PC context has been destroyed")
        self.service.apply(source, target)
        self.apply_count += 1

    def destroy(self, _pc=None):
        self.destroyed = True
        self.service.destroy()


def _config(ordinary, substrate, case_name):
    return replace(
        ordinary,
        case_name=case_name,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        stage4_dtn_order_policy="zero_order",
        n_substrate=substrate,
        n_grating=ordinary.n_air,
        grating_width_x=ordinary.period_x,
        grating_width_y=ordinary.period_y,
        grating_height=ordinary.grating_height,
        mesh_axis_cell_counts=(3, 2, 4),
        mesh_spacing_mode="auto",
        unique_output=False,
    )


def _matrix_evidence(request):
    info = request.A.getInfo()
    return {
        "rows": int(request.A.getSize()[0]),
        "cols": int(request.A.getSize()[1]),
        "n_fe": int(request.n_fe),
        "n_aux": int(request.n_aux),
        "nnz": int(info["nz_used"]),
        "ownership": list(map(int, request.A.getOwnershipRange())),
        "phase_x": [float(complex(request.floquet_data.phase_x).real), float(complex(request.floquet_data.phase_x).imag)],
        "phase_y": [float(complex(request.floquet_data.phase_y).real), float(complex(request.floquet_data.phase_y).imag)],
    }


def _checkpoints(record):
    points = {int(iteration): float(value) for iteration, value in record["monitor"]}
    return {
        "r0": float(record["initial_true_residual"]),
        "r8": points.get(8),
        "r16": points.get(16),
        "r32": points.get(32),
    }


def _record(record):
    result = {key: value for key, value in record.items() if key != "x"}
    result["checkpoints"] = _checkpoints(record)
    return result


def _run_b0(A, b, service):
    x = A.createVecRight()
    pc_context = _BoundedPc(service)
    ksp = PETSc.KSP().create(A.getComm())
    history = []
    rhs_norm = float(b.norm())
    if not math.isfinite(rhs_norm) or rhs_norm <= 0.0:
        x.destroy()
        ksp.destroy()
        raise AssertionError("S2c RHS norm must be finite and nonzero")
    try:
        x.set(0.0)
        initial = _relative_residual(A, b, x)

        def monitor(_ksp, iteration, residual_norm):
            history.append([int(iteration), float(residual_norm) / max(rhs_norm, _TINY)])

        ksp.setOperators(A)
        ksp.setType("fgmres")
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        ksp.setTolerances(rtol=1.0e-12, atol=0.0, max_it=32)
        ksp.getPC().setType(PETSc.PC.Type.PYTHON)
        ksp.getPC().setPythonContext(pc_context)
        ksp.setMonitor(monitor)
        started = time.perf_counter()
        ksp.solve(b, x)
        wall = time.perf_counter() - started
        final = _relative_residual(A, b, x)
        record = {
            "pc_type": str(ksp.getPC().getType()),
            "reason": int(ksp.getConvergedReason()),
            "iterations": int(ksp.getIterationNumber()),
            "reported_relative_residual": float(ksp.getResidualNorm()) / max(rhs_norm, _TINY),
            "initial_true_residual": initial,
            "final_true_residual": final,
            "monitor": history,
            "wall_seconds": wall,
            "rhs_norm": rhs_norm,
            "x_ownership": list(map(int, x.getOwnershipRange())),
            "no_global_factor": True,
            "pc_apply_count": pc_context.apply_count,
            "factor_solve_count_local": service.solve_count,
            "x": x,
        }
        numeric = [record[key] for key in (
            "reported_relative_residual", "initial_true_residual",
            "final_true_residual", "wall_seconds", "rhs_norm",
        )] + [point[1] for point in history]
        if not all(math.isfinite(float(value)) for value in numeric):
            raise AssertionError("S2c B0 baseline recorded a nonfinite value")
        x = None
        return record
    finally:
        ksp.destroy()
        pc_context.destroy()
        if x is not None:
            x.destroy()


def _relative(operator, rhs, solution):
    return _relative_residual(operator, rhs, solution)


def _relative_residual(operator, rhs, solution):
    image = operator.createVecLeft()
    residual = rhs.duplicate()
    operator.mult(solution, image)
    rhs.copy(residual)
    residual.axpy(PETSc.ScalarType(-1.0), image)
    value = float(residual.norm()) / max(float(rhs.norm()), _TINY)
    image.destroy()
    residual.destroy()
    return value


def _rss_mib():
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_task040_s2c_bounded_harmonic_service(tmp_path):
    comm = MPI.COMM_WORLD
    ordinary = target_stage4_config(degree=2, h_nm=100.0)
    assert ordinary.stage4_full3d_assembly_backend == STANDARD_FULL_ASSEMBLY_BACKEND
    background = _config(
        ordinary, ordinary.n_air, "task040_v9_e_s2c_background_p2_h100"
    )
    target = _config(
        ordinary, ordinary.n_substrate, "task040_v9_e_s2c_target_p2_h100"
    )
    assert background.eps_substrate == background.eps_air
    assert background.eps_grating == background.eps_air
    assert target.n_substrate == ordinary.n_substrate
    assert target.n_grating == target.n_air
    packet_holder = {}

    def background_port(request):
        transforms = None
        local = {"rank": comm.rank, "matrix": _matrix_evidence(request)}
        try:
            layout = build_active_trace_bloch_layout(request)
            transforms = create_active_trace_bloch_transforms(layout)
            packet = build_bounded_harmonic_packet(request, transforms)
            audit = packet.setup_audit
            assert audit["block_rows"] == [84, 80, 80, 80, 80, 80]
            assert audit["background_column_apply_count"] == 484
            assert audit["factor_count_global"] == 6
            assert audit["additional_absorbing_shift"] == 0.0
            assert max(audit["off_block_max"]) <= 1.0e-10
            factor_keys = (
                "solve_relative_residual", "normwise_backward_error",
                "repeat_error", "linearity_error",
            )
            assert all(
                all(
                    math.isfinite(float(item[key])) and item[key] <= 1.0e-10
                    for key in factor_keys
                )
                for item in audit["factor_solve_audit"]
            )
            local["layout_hash"] = packet.layout_hash
            local["audit"] = audit
            packet_holder["packet"] = packet
            packet_holder["layout_hash"] = packet.layout_hash
        finally:
            if transforms is not None:
                transforms.destroy()
            local["lifecycle"] = {
                "background_QT_destroyed": transforms is None or transforms._destroyed,
                "background_packet_has_petcs": False,
                "background_A_borrowed": True,
            }
        local["rss_mib"] = _rss_mib()
        raise _S2cAuditStop({"status": "S2C_BACKGROUND_READY", "local": local})

    with pytest.raises(_S2cAuditStop) as background_caught:
        run_stage4b_block_grating_3d_case(
            background, tmp_path / "background", linear_solver_port=background_port
        )
    background_local = background_caught.value.evidence["local"]
    packet = packet_holder["packet"]
    background_rank_evidence = comm.allgather(background_local)
    assert all(item["audit"]["factor_count_local"] >= 0 for item in background_rank_evidence)
    assert sum(item["audit"]["factor_count_local"] for item in background_rank_evidence) == 6

    target_holder = {}

    def target_port(request):
        transforms = None
        service = None
        baselines = {}
        local = {"rank": comm.rank, "matrix": _matrix_evidence(request)}
        selected_x = None
        try:
            layout = build_active_trace_bloch_layout(request)
            transforms = create_active_trace_bloch_transforms(layout)
            assert canonical_layout_hash(layout) == packet.layout_hash
            service = create_bounded_harmonic_service(packet, transforms)
            baselines["identity"] = _run_baseline(request.A, request.b, "none")
            baselines["jacobi"] = _run_baseline(request.A, request.b, "jacobi")
            baselines["b0"] = _run_b0(request.A, request.b, service)
            best = min(
                baselines[name]["final_true_residual"] for name in ("identity", "jacobi")
            )
            b0 = baselines["b0"]
            improvement = best / max(b0["final_true_residual"], _TINY)
            b0_positive = b0["final_true_residual"] <= 0.1 or improvement >= 8.0
            official_ready = b0["reason"] > 0 and b0["final_true_residual"] <= _RESIDUAL_LIMIT
            local.update(
                {
                    "layout_hash": canonical_layout_hash(layout),
                    "baselines": {name: _record(value) for name, value in baselines.items()},
                    "best_identity_jacobi": best,
                    "improvement": improvement,
                    "b0_positive": b0_positive,
                    "official_candidate": official_ready,
                    "apply_count": service.apply_count,
                    "factor_solve_count_local": service.solve_count,
                }
            )
            if not official_ready:
                target_holder["local"] = local
                raise _S2cAuditStop(
                    {"status": "S2C_B0_OFFICIAL_NOT_RUN", "local": local}
                )
            selected_x = baselines["b0"].pop("x")
            return Stage4ExternalLinearSolverSnapshot(
                x=selected_x,
                converged_reason=b0["reason"],
                iterations=b0["iterations"],
                reported_relative_residual=b0["reported_relative_residual"],
                condensed_true_residual=b0["final_true_residual"],
                full_augmented_true_residual=b0["final_true_residual"],
                ksp_type="fgmres",
                pc_type="python",
                residual_limit=_RESIDUAL_LIMIT,
                no_global_factor=True,
                solver_profile="s2c_owner_local_bounded_harmonic",
                reduced_residual_norm=b0["final_true_residual"] * b0["rhs_norm"],
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

    target_summary = None
    target_stop = None
    try:
        target_summary = run_stage4b_block_grating_3d_case(
            target, tmp_path / "target", linear_solver_port=target_port
        )
    except _S2cAuditStop as exc:
        target_stop = exc.value
    rank_target = comm.allgather(target_holder["local"])
    if target_stop is not None:
        assert target_summary is None
        assert target_stop["status"] == "S2C_B0_OFFICIAL_NOT_RUN"
    else:
        assert target_summary is not None
        assert target_summary["external_linear_solver_port"] is True
    if comm.rank == 0:
        payload = {
            "status": (
                "S2C_B0_OFFICIAL_CANDIDATE"
                if target_stop is None
                else target_stop["status"]
            ),
            "background": {
                "ranks": background_rank_evidence,
                "layout_hash": packet.layout_hash,
            },
            "target": rank_target,
            "summary": None
            if target_summary is None
            else {
                key: target_summary.get(key)
                for key in (
                    "case_status", "official_result", "external_rta_gate_pass",
                    "postprocess_skipped", "num_augmented_rows",
                    "stage4_dtn_num_auxiliary_dofs",
                )
            },
            "rss_mib": _rss_mib(),
        }
        print("S2C_EVIDENCE " + json.dumps(payload, default=str, sort_keys=True))
