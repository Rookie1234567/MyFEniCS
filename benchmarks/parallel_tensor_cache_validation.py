"""Small actual mapped mesh serial/exec-parallel equality and resource witness."""

from __future__ import annotations

import argparse
import gc
import time
from pathlib import Path

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    condense_unconstrained_vector_to_active_trace,
    recover_owned_cell_interiors,
)
from src.solvers.parallel_tensor_cache import atomic_json
from src.test.test_task40_gate_cd_mapped_p6_condensation import (
    _compile_form,
    _relative_matrix_difference,
    _small_gate_cd_swept_fixture,
)


def run(directory, degree, cpus, levels):
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "RUNNING",
        "degree": degree,
        "q": 21,
        "cells": 8,
        "runs": [],
        "started_monotonic": time.monotonic(),
        "scope": "actual mapped Q1 mesh, nontrivial double Floquet MPC, condensed matrix/nonzero RHS/interior recovery; no global factor/PDE/VTK",
    }
    msh, tags, data, cfg = _small_gate_cd_swept_fixture()
    V = fem.functionspace(
        msh, element("N1curl", "hexahedron", degree, dtype=default_real_type)
    )
    cfg.nedelec_degree = degree
    floquet = build_double_floquet_mpc(V, data, cfg)
    form = _compile_form(V, tags, 21)
    baseline = None
    reference_rhs = None
    reference_recovery = None
    rng = np.random.default_rng(20261102)
    full_rhs = PETSc.Vec().createSeq(V.dofmap.index_map.size_global)
    full_rhs.getArray()[:] = rng.standard_normal(
        full_rhs.getSize()
    ) + 1j * rng.standard_normal(full_rhs.getSize())
    full_rhs.assemble()
    active = None
    for workers in [0, *levels]:
        label = "serial" if workers == 0 else f"workers{workers}"
        report["phase"] = label
        atomic_json(directory / "report.json", report)
        # The 8-cell equivalence test separately labels the effective class concurrency.
        config = (
            None
            if not workers
            else {
                "root": str(directory / "parallel-cache"),
                "cpus": cpus[:workers],
                "operator_identity": {
                    "benchmark": "mapped-eight-cell-v1",
                    "degree": degree,
                    "q": 21,
                },
                "progress": lambda done, total, result, label=label: atomic_json(
                    directory / f"{label}-progress.json",
                    {"done": done, "total": total, "last": result},
                ),
            }
        )
        start = time.perf_counter()
        started_monotonic = time.monotonic()
        system = build_unconstrained_assembly_time_condensation(
            form,
            V,
            tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
            geometry_identity_policy="mapped_exact",
            mapped_geometry_translation_invariant=True,
            raw_tensor_execution_config=config,
        )
        elapsed = time.perf_counter() - start
        if active is None:
            active = rng.standard_normal(system.active_rows) + 1j * rng.standard_normal(
                system.active_rows
            )
        rhs = condense_unconstrained_vector_to_active_trace(
            system, full_rhs, side="right", relative_tolerance=0.0
        )
        recovery = [
            (d.copy(), v.copy())
            for d, v in recover_owned_cell_interiors(system, active, full_rhs=full_rhs)
        ]
        if baseline is None:
            baseline = system.matrix.copy()
            reference_rhs = rhs.copy()
            reference_recovery = recovery
            matrix_error = rhs_error = recovery_error = 0.0
        else:
            matrix_error = _relative_matrix_difference(system.matrix, baseline)
            delta = rhs.copy()
            delta.axpy(-1, reference_rhs)
            rhs_error = float(delta.norm() / reference_rhs.norm())
            delta.destroy()
            numerator = denominator = 0.0
            for (d, v), (dr, vr) in zip(recovery, reference_recovery, strict=True):
                assert np.array_equal(d, dr)
                numerator += float(np.vdot(v - vr, v - vr).real)
                denominator += float(np.vdot(vr, vr).real)
            recovery_error = float(np.sqrt(numerator / denominator))
        record = {
            "requested_workers": workers or 1,
            "serial_baseline": workers == 0,
            "wall_seconds": elapsed,
            "started_monotonic": started_monotonic,
            "ended_monotonic": time.monotonic(),
            "matrix_relative": matrix_error,
            "rhs_relative": rhs_error,
            "recovery_relative": recovery_error,
            "audit": system.build_audit.get("raw_tensor_execution"),
        }
        # Find nested raw-cache audit without assuming a future display layout.
        for value in system.build_audit.values():
            if isinstance(value, dict) and "raw_tensor_execution" in value:
                record["audit"] = value["raw_tensor_execution"]
        report["runs"].append(record)
        atomic_json(directory / "report.json", report)
        assert max(matrix_error, rhs_error, recovery_error) < 2e-10
        system.destroy()
        rhs.destroy()
        gc.collect()
    baseline.destroy()
    reference_rhs.destroy()
    full_rhs.destroy()
    report["status"] = "PASS_SMALL_MAPPED_ASSEMBLY_EQUIVALENCE"
    report["phase"] = "complete"
    atomic_json(directory / "report.json", report)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--degree", type=int, default=6)
    p.add_argument("--cpus", required=True)
    p.add_argument("--levels", default="4,8,16,32")
    a = p.parse_args()
    run(
        a.directory,
        a.degree,
        list(map(int, a.cpus.split(","))),
        list(map(int, a.levels.split(","))),
    )
