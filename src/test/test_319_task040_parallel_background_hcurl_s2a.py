"""Task040 S2a: physical-DtN external identity/Jacobi baseline plumbing."""

from __future__ import annotations

import json
import math
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
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)

_TINY = np.finfo(float).tiny
_RESIDUAL_LIMIT = 1.0e-9


def _relative_residual(A, b, x):
    residual = b.duplicate()
    A.mult(x, residual)
    residual.axpy(PETSc.ScalarType(-1), b)
    value = float(residual.norm()) / max(float(b.norm()), _TINY)
    residual.destroy()
    return value


def _run_baseline(A, b, pc_name):
    x = A.createVecRight()
    ksp = PETSc.KSP().create(A.getComm())
    history = []
    rhs_norm = float(b.norm())
    if not math.isfinite(rhs_norm) or rhs_norm <= 0.0:
        raise AssertionError("S2a RHS norm must be finite and nonzero")
    try:
        x.set(0)
        initial = _relative_residual(A, b, x)
        def monitor(_ksp, iteration, residual_norm):
            history.append(
                [int(iteration), float(residual_norm) / max(rhs_norm, _TINY)]
            )
        ksp.setOperators(A)
        ksp.setType("fgmres")
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        ksp.setTolerances(rtol=1.0e-12, atol=0.0, max_it=32)
        ksp.getPC().setType(pc_name)
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
            "x": x,
        }
        numeric = [record[key] for key in (
            "reported_relative_residual", "initial_true_residual",
            "final_true_residual", "wall_seconds", "rhs_norm",
        )] + [point[1] for point in history]
        if not all(math.isfinite(float(value)) for value in numeric):
            raise AssertionError("S2a baseline recorded a nonfinite value")
        x = None
        return record
    finally:
        ksp.destroy()
        if x is not None:
            x.destroy()


def _complex_pair(value):
    value = complex(value)
    return [float(value.real), float(value.imag)]


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_task040_s2a_external_baseline_identity_jacobi(tmp_path):
    comm = MPI.COMM_WORLD
    ordinary = target_stage4_config(degree=2, h_nm=100.0)
    assert ordinary.stage4_full3d_assembly_backend == STANDARD_FULL_ASSEMBLY_BACKEND
    cfg = replace(
        ordinary,
        case_name="task040_v9_e_s2a_external_baseline_p2_h100",
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        stage4_dtn_order_policy="zero_order",
        n_grating=ordinary.n_air,
        unique_output=False,
    )
    assert cfg.n_grating == cfg.n_air
    assert cfg.eps_grating == cfg.eps_r
    assert abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_y) - 1.0) <= 1.0e-12
    evidence = {}
    def external_port(request):
        A, b = request.A, request.b
        rows, cols = map(int, A.getSize())
        evidence["request"] = {
            "n_fe": int(request.n_fe), "n_aux": int(request.n_aux),
            "rows": rows, "cols": cols,
            "A_ownership": list(map(int, A.getOwnershipRange())),
            "b_ownership": list(map(int, b.getOwnershipRange())),
            "phase_x": _complex_pair(request.config.floquet_phase_x),
            "phase_y": _complex_pair(request.config.floquet_phase_y),
        }
        baselines = {
            "identity": _run_baseline(A, b, "none"),
            "jacobi": _run_baseline(A, b, "jacobi"),
        }
        selected_name = min(
            baselines, key=lambda name: baselines[name]["final_true_residual"]
        )
        loser_name = next(name for name in baselines if name != selected_name)
        baselines[loser_name]["x"].destroy()
        selected = baselines[selected_name]
        selected_x = selected.pop("x")
        evidence["selected"] = selected_name
        evidence["baselines"] = {
            name: {key: value for key, value in record.items() if key != "x"}
            for name, record in baselines.items()
        }
        evidence["lifecycle"] = {
            "borrowed_A_b": True, "ksp_destroyed": True,
            "loser_x_destroyed": True, "selected_x_transferred": True,
            "factor_created": False,
        }
        return Stage4ExternalLinearSolverSnapshot(
            x=selected_x,
            converged_reason=selected["reason"],
            iterations=selected["iterations"],
            reported_relative_residual=selected["reported_relative_residual"],
            # S2a deliberately has no second condensed operator.
            condensed_true_residual=selected["final_true_residual"],
            full_augmented_true_residual=selected["final_true_residual"],
            ksp_type="fgmres",
            pc_type=selected["pc_type"],
            residual_limit=_RESIDUAL_LIMIT,
            no_global_factor=True,
            solver_profile="s2a_direct_augmented_baseline",
            reduced_residual_norm=(
                selected["final_true_residual"] * selected["rhs_norm"]
            ),
        )

    summary = run_stage4b_block_grating_3d_case(
        cfg, tmp_path / "s2a", linear_solver_port=external_port
    )
    rank_evidence = comm.allgather(evidence)
    request = rank_evidence[0]["request"]
    assert request["n_aux"] == 4
    assert request["rows"] == request["cols"] == request["n_fe"] + request["n_aux"]
    for rank in rank_evidence:
        item = rank["request"]
        assert item["A_ownership"] == item["b_ownership"]
        for baseline in rank["baselines"].values():
            assert baseline["no_global_factor"] is True
            assert baseline["x_ownership"] == item["A_ownership"]
            values = tuple(baseline[key] for key in (
                "initial_true_residual", "final_true_residual",
                "reported_relative_residual", "wall_seconds",
            ))
            assert all(math.isfinite(float(value)) for value in values)
            assert all(math.isfinite(float(point[1])) for point in baseline["monitor"])
    matrix_stats = summary["stage4_dtn_augmented_matrix_stats_after_finalize"]
    assert matrix_stats["matrix_rows"] == request["rows"]
    assert matrix_stats["matrix_nnz_used"] is not None
    assert summary["num_augmented_rows"] == request["rows"]
    assert summary["num_active_trace_dofs"] == request["n_fe"]
    assert summary["stage4_dtn_num_auxiliary_dofs"] == 4
    backend_audit = summary["stage4_full3d_assembly_backend_audit"]
    assert backend_audit["ordinary_default_unchanged"] is True
    assert backend_audit["ordinary_default_selected"] is False
    assert summary["stage4_dtn_factor_inventory"] is None
    assert summary["case_status"] in {
        "completed", "external_solver_not_converged",
        "external_residual_gate_failed", "failed_stage4_energy_balance",
    }
    official_gate, official = summary["external_rta_gate_pass"], summary["official_result"]
    if official:
        assert official_gate is True
        assert all(math.isfinite(float(summary[key])) for key in (
            "R_total", "T_total", "A_volume_total",
        ))
    else:
        assert summary["postprocess_skipped"] is True
    fields = (
        "case_status", "official_result", "external_rta_gate_pass",
        "postprocess_skipped", "stage4_dtn_num_auxiliary_dofs",
        "num_mesh_cells", "num_nedelec_dofs", "num_active_trace_dofs",
        "num_augmented_rows", "stage4_dtn_augmented_matrix_stats_after_finalize",
        "stage4_dtn_base_matrix_stats", "stage4_dtn_condensed_matrix_stats",
    )
    payload = {
        "status": "S2A_EXTERNAL_BASELINE_READY", "request": request,
        "rank_evidence": rank_evidence,
        "summary": {key: summary.get(key) for key in fields},
    }
    if comm.rank == 0:
        print("S2A_EVIDENCE " + json.dumps(payload, default=str, sort_keys=True))
