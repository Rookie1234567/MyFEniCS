"""Review V28 L3: bounded multi-column local p4 RHS reduction/recovery."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter, process_time

import dolfinx_mpc
import numpy as np
import ufl
from basix.ufl import element
from dolfinx import fem, mesh
from mpi4py import MPI
from petsc4py import PETSc
from scipy.sparse import csr_matrix

from src.solvers import p4_cell_condensed_inverse as core
from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hcurl_cell_static_condensation import (
    owned_hcurl_cell_interior_dofs,
)


ROOT = Path(__file__).resolve().parents[2]


class _Factor:
    def __init__(self, matrix):
        self.backend = _MumpsFactor(matrix)
        self.backend.set_icntl(35, 0)
        self.backend.set_icntl(10, 0)
        self.backend.symbolic(matrix)
        self.backend.numeric(matrix)
        self.calls = 0
        self.destroyed = False

    def solve_repeated(self, rhs, output):
        self.backend.solve_repeated(rhs, output)
        self.calls += 1

    def destroy(self):
        self.backend.destroy()
        self.destroyed = True


def test_l3_bounded_batch_matches_legacy_on_same_factor_and_fixed_rhs():
    if MPI.COMM_WORLD.size != 1:
        raise AssertionError("the frozen L3 local fixture requires MPI1")
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 6, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tags = mesh.meshtags(
        domain,
        3,
        np.arange(6, dtype=np.int32),
        np.ones(6, dtype=np.int32),
    )
    space = fem.functionspace(
        domain, element("N1curl", domain.basix_cell(), 2)
    )
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    form = fem.form(
        ufl.inner(ufl.curl(trial), ufl.curl(test))
        * dx(1, metadata={"quadrature_degree": 4})
        + 1.7
        * ufl.inner(trial, test)
        * dx(1, metadata={"quadrature_degree": 4})
    )
    interior = np.concatenate(owned_hcurl_cell_interior_dofs(space))
    n = int(space.dofmap.index_map.size_global)
    trace = np.setdiff1d(np.arange(n), interior)
    master, slave = int(trace[0]), int(trace[-1])
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.array([slave], dtype=np.int32),
        np.array([master], dtype=np.int64),
        np.array([0.83 + 0.27j], dtype=np.complex128),
        np.array([0], dtype=np.int32),
        np.array([0, 1], dtype=np.int32),
    )
    mpc.finalize()
    full = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
    full.assemble()
    condensed = build_unconstrained_assembly_time_condensation(
        form,
        space,
        tags,
        mpc=mpc,
        appended_global_rows=2,
        appended_support_owned_cell_groups=(np.arange(6, dtype=np.int32),),
        appended_support_group_by_row=(0, 0),
        defer_final_assembly=True,
        dense_appended_block=True,
        sum_duplicate_cell_integrals=True,
    )
    factor = inverse = None
    vectors = []
    try:
        rng = np.random.default_rng(39030)
        port_indices = np.array([0, 1], dtype=PETSc.IntType)
        terms = {}
        B = np.zeros((n, 2), dtype=np.complex128)
        D = np.zeros((2, n), dtype=np.complex128)
        H = np.zeros((2, 2), dtype=np.complex128)
        for index, cell in enumerate(condensed.cell_recovery_maps):
            ni = len(cell.interior_original_dofs)
            nt = len(cell.trace_original_dofs)
            bi = 0.02 * (
                rng.normal(size=(ni, 2)) + 1j * rng.normal(size=(ni, 2))
            )
            di = 0.015 * (
                rng.normal(size=(2, ni)) + 1j * rng.normal(size=(2, ni))
            )
            bt = 0.006 * (
                rng.normal(size=(nt, 2)) + 1j * rng.normal(size=(nt, 2))
            )
            dt = 0.005 * (
                rng.normal(size=(2, nt)) + 1j * rng.normal(size=(2, nt))
            )
            if slave in cell.trace_original_dofs:
                slave_local = int(np.flatnonzero(cell.trace_original_dofs == slave)[0])
                bt[slave_local, :] = 0.0
                dt[:, slave_local] = 0.0
            h_local = np.zeros((2, 2), dtype=np.complex128)
            if index == 0:
                h_local[:] = np.array(
                    [[1.2 + 0.4j, 0.13 - 0.08j], [-0.05 + 0.11j, 0.9 - 0.2j]],
                    dtype=np.complex128,
                )
            terms[index] = core.CellPortTerms(
                Bi=bi,
                Di=di,
                port_indices=port_indices,
                Bt=bt,
                Dt=dt,
                H=h_local,
            )
            B[cell.interior_original_dofs] += bi
            B[cell.trace_original_dofs] += bt
            D[:, cell.interior_original_dofs] += di
            D[:, cell.trace_original_dofs] += dt
            H += h_local
        assert np.linalg.norm(D - B.conj().T) > 0.0
        class_sizes = {}
        for cell in condensed.cell_recovery_maps:
            class_sizes[cell.class_key] = class_sizes.get(cell.class_key, 0) + 1
        class_count = len(class_sizes)
        cell_count = len(condensed.cell_recovery_maps)
        assert max(class_sizes.values()) >= 3
        core.assemble_port_condensed_terms(condensed, terms)

        indptr, indices, values = full.getValuesCSR()
        V = csr_matrix((values, indices, indptr), shape=(n, n)).toarray()
        augmented = np.block([[V, B], [-D, H]])
        expected_schur_rows = np.r_[
            condensed.trace_constraints.owned_active_original_dofs,
            n + np.arange(2),
        ]
        interiors = np.concatenate(
            [cell.interior_original_dofs for cell in condensed.cell_recovery_maps]
        )
        expected_schur = augmented[np.ix_(expected_schur_rows, expected_schur_rows)]
        expected_schur -= (
            augmented[np.ix_(expected_schur_rows, interiors)]
            @ np.linalg.solve(
                augmented[np.ix_(interiors, interiors)],
                augmented[np.ix_(interiors, expected_schur_rows)],
            )
        )
        sp, sj, sa = condensed.matrix.getValuesCSR()
        actual_schur = csr_matrix(
            (sa, sj, sp), shape=expected_schur.shape
        ).toarray()
        assert np.linalg.norm(actual_schur - expected_schur) / np.linalg.norm(
            expected_schur
        ) <= 1e-10

        factor = _Factor(condensed.matrix)
        inverse = core.P4CellCondensedInverse(
            condensed,
            factor,
            port_terms=terms,
            owns_factor=True,
            owns_condensed=True,
            local_rhs_batch_size=1,
        )
        rng = np.random.default_rng(39031)
        rhs_values = rng.normal(size=n) + 1j * rng.normal(size=n)
        rhs_values[slave] = 0.0
        rhs = full.createVecRight()
        rhs.array[:] = rhs_values
        vectors.append(rhs)
        expected = np.linalg.solve(augmented, np.r_[rhs_values, np.zeros(2)])
        samples = []
        baseline_result = None
        candidate_result = None
        for round_index in range(3):
            for mode, batch_size in (("legacy_per_cell", 1), ("bounded_batch", 3)):
                inverse.local_rhs_batch_size = batch_size
                wall_start, cpu_start = perf_counter(), process_time()
                output = inverse.apply(rhs)
                wall_seconds = perf_counter() - wall_start
                cpu_seconds = process_time() - cpu_start
                vectors.append(output)
                output_values = output.array.copy()
                alpha = inverse.last_port_solution.copy()
                residual = augmented @ np.r_[output_values, alpha] - np.r_[
                    rhs_values, np.zeros(2)
                ]
                assert np.linalg.norm(residual) / np.linalg.norm(rhs_values) <= 1e-10
                np.testing.assert_allclose(
                    output_values, expected[:n], rtol=1e-10, atol=1e-11
                )
                np.testing.assert_allclose(
                    alpha, expected[n:], rtol=1e-10, atol=1e-11
                )
                if mode == "legacy_per_cell":
                    baseline_result = output_values
                else:
                    candidate_result = output_values
                    reduce_batch = inverse.last_audit["reduce_batch"]
                    recover_batch = inverse.last_audit["recover_batch"]
                    assert reduce_batch["mode"] == "bounded_multicolumn"
                    assert recover_batch["mode"] == "bounded_multicolumn"
                    assert reduce_batch["batch_group_count"] == class_count
                    assert recover_batch["batch_group_count"] == class_count
                    assert reduce_batch["batch_count"] < cell_count
                    assert recover_batch["batch_count"] < cell_count
                    assert reduce_batch["local_lu_solve_calls"] < cell_count
                    assert recover_batch["local_lu_solve_calls"] < cell_count
                    assert reduce_batch["max_batch_columns"] > 1
                    assert recover_batch["max_batch_columns"] > 1
                    assert reduce_batch["max_visible_batch_ndarray_bytes"] > (
                        reduce_batch["max_rhs_panel_bytes"]
                    )
                    assert recover_batch["max_visible_batch_ndarray_bytes"] > (
                        recover_batch["max_rhs_panel_bytes"]
                    )
                    np.testing.assert_allclose(
                        output_values, baseline_result, rtol=1e-10, atol=1e-11
                    )
                samples.append(
                    {
                        "round": round_index,
                        "mode": mode,
                        "batch_size": batch_size,
                        "wall_seconds": wall_seconds,
                        "process_cpu_seconds": cpu_seconds,
                        "audit": dict(inverse.last_audit),
                    }
                )
        assert factor.calls == inverse.solve_count == 6
        assert candidate_result is not None
        tracked_diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], cwd=ROOT, check=True,
            capture_output=True,
        ).stdout
        record = {
            "schema": "task39extra.v30.l3.bounded-local-rhs-batch.v1",
            "status": "PASS",
            "attempt_history": [
                {
                    "attempt": 1,
                    "status": "CONTROLLED_FIXTURE_DESIGN_STOP",
                    "reason": "two-cell fixture produced two singleton orientation classes, so it could not exercise a multi-column batch",
                    "correction": "expanded the uniform structured grid to six cells and require a repeated existing class before measuring",
                }
            ],
            "source_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                capture_output=True, text=True,
            ).stdout.strip(),
            "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "solver_source_sha256": hashlib.sha256(
                (ROOT / "src/solvers/p4_cell_condensed_inverse.py").read_bytes()
            ).hexdigest(),
            "fixture": {
                "cells": cell_count,
                "nedelec_degree": 2,
                "same_existing_class_key_count": class_count,
                "largest_existing_class_population": max(class_sizes.values()),
                "complex_mpc": True,
                "nonzero_Bi_Di_Bt_Dt": True,
                "nonhermitian_port_operator": True,
                "nonzero_interior_rhs": True,
                "fixed_global_factor_count": 1,
                "fixed_rhs_sha256": hashlib.sha256(rhs_values.tobytes()).hexdigest(),
                "factor_solve_call_count": factor.calls,
            },
            "expected_solution_sha256": hashlib.sha256(expected.tobytes()).hexdigest(),
            "batch_equivalence_max_abs": float(
                np.max(np.abs(candidate_result - baseline_result))
            ),
            "legacy_vs_candidate_local_call_counts": {
                "legacy_reduction_lu_calls_per_nonzero_cell": cell_count,
                "legacy_recovery_lu_calls_per_cell": cell_count,
                "candidate_reduction_lu_calls": samples[-1]["audit"]["reduce_batch"]["local_lu_solve_calls"],
                "candidate_recovery_lu_calls": samples[-1]["audit"]["recover_batch"]["local_lu_solve_calls"],
            },
            "interleaved_same_factor_samples": samples,
            "performance_claim": "component_fixture_only_no_physical_80_mode_or_full_C_claim",
        }
        record_path = ROOT / (
            "docs/task039_extra_physical_multilevel/outcomes/records/"
            "workstation_guided_local_v30_l3_batch.json"
        )
        if os.environ.get("TASK39EXTRA_V30_SAVE_L3_RECORD") == "1":
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    finally:
        for vector in vectors:
            vector.destroy()
        if inverse is not None:
            inverse.destroy()
        elif factor is not None:
            factor.destroy()
        if inverse is None:
            condensed.destroy()
        full.destroy()



def test_l3_real_p4_80_mode_local_batch_qualification(tmp_path):
    """Measure only p4 local C kernels on the real 80-mode V30 carrier.

    A fixed-output factor object keeps every global-vector input identical and
    avoids building a numerical global factor. This qualifies the local
    reduction/recovery kernels; it does not claim a complete C timing.
    """
    if MPI.COMM_WORLD.size != 1:
        raise AssertionError("the V30 real 80-mode local fixture requires MPI1")

    from src.test.test_task39extra_v30_streamed_ports import (
        _real_v30_80_mode_case,
    )

    with _real_v30_80_mode_case(
        tmp_path,
        degree=4,
        materialize_global_matrix=True,
        build_port_actions=False,
    ) as case:
        condensed = case["condensed"]
        carrier = case["carrier"]
        physical_action = case["physical"]["physical_action"]
        degree = case["degree"]
        assert len(carrier.entries) == 80
        assert condensed.matrix is not None

        port_terms = core.assemble_condensed_ports(condensed, carrier)
        port_terms_audit = condensed.build_audit["port_condensed_terms"]
        assert port_terms_audit["carrier_rows_are_mpc_processed"]

        rng = np.random.default_rng(39082)
        storage = np.zeros(condensed.full_rows, dtype=np.complex128)
        active_original = condensed.trace_constraints.owned_active_original_dofs
        storage[active_original] = (
            0.1 * rng.normal(size=len(active_original))
            + 0.1j * rng.normal(size=len(active_original))
        )
        interiors = np.unique(
            np.concatenate(
                [cell.interior_original_dofs for cell in condensed.cell_recovery_maps]
            )
        )
        storage[interiors] = (
            0.1 * rng.normal(size=len(interiors))
            + 0.1j * rng.normal(size=len(interiors))
        )
        slaves = np.asarray(
            case["levels"]["floquets"][degree].mpc.slaves,
            dtype=np.int64,
        )
        storage[slaves] = 0.0
        alpha = np.asarray(
            [
                np.dot(entry.projection_values, storage[entry.projection_rows])
                / entry.normalization_h
                for entry in carrier.entries
            ],
            dtype=np.complex128,
        )
        active = np.empty(condensed.active_rows, dtype=np.complex128)
        for original in active_original:
            active_id = condensed.trace_constraints.original_to_active[int(original)]
            active[active_id] = storage[int(original)]
        fixed_global_output = np.concatenate((active, alpha))

        def native_apply(field):
            source_vector = PETSc.Vec().createSeq(
                condensed.full_rows, comm=PETSc.COMM_SELF
            )
            target_vector = source_vector.duplicate()
            try:
                source_vector.array[:] = field
                source_vector.assemble()
                physical_action.apply(source_vector, target_vector)
                return np.asarray(
                    target_vector.array, dtype=np.complex128
                ).copy()
            finally:
                target_vector.destroy()
                source_vector.destroy()

        rhs_values = native_apply(storage)
        assert np.linalg.norm(rhs_values) > 0.0
        assert np.linalg.norm(rhs_values[interiors]) > 0.0
        rhs = PETSc.Vec().createSeq(condensed.full_rows, comm=PETSc.COMM_SELF)
        rhs.array[:] = rhs_values
        rhs.assemble()

        class _FixedOutputFactor:
            def __init__(self, values):
                self.values = np.asarray(values, dtype=np.complex128).copy()
                self.solve_calls = 0

            def solve_repeated(self, _rhs, output):
                self.solve_calls += 1
                output.array[:] = self.values
                output.assemble()

        factor = _FixedOutputFactor(fixed_global_output)
        inverse = core.P4CellCondensedInverse(
            condensed,
            factor,
            port_terms=port_terms,
            local_rhs_batch_size=1,
        )
        try:
            warmups = []
            for route, batch_size in (("legacy_per_cell", 1), ("bounded_multicolumn", 3)):
                inverse.local_rhs_batch_size = batch_size
                started_wall, started_cpu = perf_counter(), process_time()
                output = inverse.apply(rhs)
                wall = float(perf_counter() - started_wall)
                cpu = float(process_time() - started_cpu)
                try:
                    values = np.asarray(output.array, dtype=np.complex128).copy()
                    returned_alpha = inverse.last_port_solution.copy()
                    audit = dict(inverse.last_audit)
                    assert np.isfinite(values).all()
                    assert np.isfinite(returned_alpha).all()
                    warmups.append({
                        "route": route,
                        "batch_size": batch_size,
                        "wall_seconds": wall,
                        "process_cpu_seconds": cpu,
                        "reduce_seconds": float(audit["reduce_seconds"]),
                        "solve_seconds": float(audit["solve_seconds"]),
                        "recover_seconds": float(audit["recover_seconds"]),
                        "local_reduce_lu_solve_calls": int(
                            audit["reduce_batch"]["local_lu_solve_calls"]
                        ),
                        "local_recover_lu_solve_calls": int(
                            audit["recover_batch"]["local_lu_solve_calls"]
                        ),
                        "output_relative_to_seed": float(
                            np.linalg.norm(values - storage)
                            / max(np.linalg.norm(storage), np.finfo(float).tiny)
                        ),
                        "alpha_relative_to_seed": float(
                            np.linalg.norm(returned_alpha - alpha)
                            / max(np.linalg.norm(alpha), np.finfo(float).tiny)
                        ),
                    })
                finally:
                    output.destroy()

            samples = []
            paired = []
            schedule = (
                (0, (("legacy_per_cell", 1), ("bounded_multicolumn", 3))),
                (1, (("bounded_multicolumn", 3), ("legacy_per_cell", 1))),
                (2, (("legacy_per_cell", 1), ("bounded_multicolumn", 3))),
            )
            for round_index, routes in schedule:
                pair_outputs = {}
                pair_samples = {}
                for route, batch_size in routes:
                    inverse.local_rhs_batch_size = batch_size
                    started_wall, started_cpu = perf_counter(), process_time()
                    output = inverse.apply(rhs)
                    wall = float(perf_counter() - started_wall)
                    cpu = float(process_time() - started_cpu)
                    try:
                        values = np.asarray(output.array, dtype=np.complex128).copy()
                        returned_alpha = inverse.last_port_solution.copy()
                        audit = dict(inverse.last_audit)
                        projected = np.asarray(
                            [
                                np.dot(entry.projection_values, values[entry.projection_rows])
                                for entry in carrier.entries
                            ],
                            dtype=np.complex128,
                        )
                        normalized_alpha = np.asarray(
                            [
                                entry.normalization_h * returned_alpha[index]
                                for index, entry in enumerate(carrier.entries)
                            ],
                            dtype=np.complex128,
                        )
                        closure = -projected + normalized_alpha
                        closure_scale = max(
                            np.linalg.norm(projected) + np.linalg.norm(normalized_alpha),
                            np.finfo(float).tiny,
                        )
                        sample = {
                            "round": round_index,
                            "route": route,
                            "batch_size": batch_size,
                            "wall_seconds": wall,
                            "process_cpu_seconds": cpu,
                            "reduce_seconds": float(audit["reduce_seconds"]),
                            "solve_seconds": float(audit["solve_seconds"]),
                            "recover_seconds": float(audit["recover_seconds"]),
                            "local_reduce_lu_solve_calls": int(
                                audit["reduce_batch"]["local_lu_solve_calls"]
                            ),
                            "local_recover_lu_solve_calls": int(
                                audit["recover_batch"]["local_lu_solve_calls"]
                            ),
                            "port_closure_relative": float(
                                np.linalg.norm(closure) / closure_scale
                            ),
                            "output_relative_to_seed": float(
                                np.linalg.norm(values - storage)
                                / max(np.linalg.norm(storage), np.finfo(float).tiny)
                            ),
                            "alpha_relative_to_seed": float(
                                np.linalg.norm(returned_alpha - alpha)
                                / max(np.linalg.norm(alpha), np.finfo(float).tiny)
                            ),
                            "output_sha256": hashlib.sha256(
                                values.astype("<c16", copy=False).tobytes()
                            ).hexdigest(),
                            "alpha_sha256": hashlib.sha256(
                                returned_alpha.astype("<c16", copy=False).tobytes()
                            ).hexdigest(),
                        }
                        samples.append(sample)
                        pair_samples[route] = sample
                        pair_outputs[route] = (values, returned_alpha)
                    finally:
                        output.destroy()
                legacy_values, legacy_alpha = pair_outputs["legacy_per_cell"]
                batch_values, batch_alpha = pair_outputs["bounded_multicolumn"]
                paired.append({
                    "round": round_index,
                    "route_order": [route for route, _size in routes],
                    "relative_field_difference": float(
                        np.linalg.norm(batch_values - legacy_values)
                        / max(np.linalg.norm(legacy_values), np.finfo(float).tiny)
                    ),
                    "relative_alpha_difference": float(
                        np.linalg.norm(batch_alpha - legacy_alpha)
                        / max(np.linalg.norm(legacy_alpha), np.finfo(float).tiny)
                    ),
                    "legacy_reduction_lu_calls": pair_samples["legacy_per_cell"][
                        "local_reduce_lu_solve_calls"
                    ],
                    "batch_reduction_lu_calls": pair_samples["bounded_multicolumn"][
                        "local_reduce_lu_solve_calls"
                    ],
                    "legacy_recovery_lu_calls": pair_samples["legacy_per_cell"][
                        "local_recover_lu_solve_calls"
                    ],
                    "batch_recovery_lu_calls": pair_samples["bounded_multicolumn"][
                        "local_recover_lu_solve_calls"
                    ],
                })

            assert len(paired) == 3
            assert max(
                max(item["relative_field_difference"], item["relative_alpha_difference"])
                for item in paired
            ) <= 1.0e-10
            assert max(sample["port_closure_relative"] for sample in samples) <= 1.0e-10
            assert max(sample["output_relative_to_seed"] for sample in samples) <= 1.0e-10
            assert max(sample["alpha_relative_to_seed"] for sample in samples) <= 1.0e-10
            assert max(sample["output_relative_to_seed"] for sample in warmups) <= 1.0e-10
            assert max(sample["alpha_relative_to_seed"] for sample in warmups) <= 1.0e-10
            assert max(sample["local_reduce_lu_solve_calls"] for sample in warmups) <= len(
                condensed.cell_recovery_maps
            )
            assert max(sample["local_recover_lu_solve_calls"] for sample in warmups) <= len(
                condensed.cell_recovery_maps
            )
            assert max(sample["local_reduce_lu_solve_calls"] for sample in samples) <= len(
                condensed.cell_recovery_maps
            )
            assert max(sample["local_recover_lu_solve_calls"] for sample in samples) <= len(
                condensed.cell_recovery_maps
            )
            assert factor.solve_calls == inverse.solve_count == len(warmups) + len(samples)
            legacy_samples = [
                sample for sample in samples if sample["route"] == "legacy_per_cell"
            ]
            batch_samples = [
                sample for sample in samples if sample["route"] == "bounded_multicolumn"
            ]
            legacy_by_round = {sample["round"]: sample for sample in legacy_samples}
            batch_by_round = {sample["round"]: sample for sample in batch_samples}
            timing_pairs = [
                (legacy_by_round[index], batch_by_round[index])
                for index in sorted(legacy_by_round)
            ]
            median_cpu = {
                "legacy_per_cell": float(np.median([
                    sample["process_cpu_seconds"] for sample in legacy_samples
                ])),
                "bounded_multicolumn": float(np.median([
                    sample["process_cpu_seconds"] for sample in batch_samples
                ])),
            }
            median_wall = {
                "legacy_per_cell": float(np.median([
                    sample["wall_seconds"] for sample in legacy_samples
                ])),
                "bounded_multicolumn": float(np.median([
                    sample["wall_seconds"] for sample in batch_samples
                ])),
            }
            repeated_local_gain = all(
                batch["process_cpu_seconds"] < legacy["process_cpu_seconds"]
                and batch["wall_seconds"] < legacy["wall_seconds"]
                for legacy, batch in timing_pairs
            )

            tracked_diff = subprocess.run(
                ["git", "diff", "--binary", "HEAD"], cwd=ROOT, check=True,
                capture_output=True,
            ).stdout
            record = {
                "schema": "task039extra.v30.l3.real-p4-80-mode-local-kernel.v1",
                "classification": "DIAGNOSTIC_REAL_P4_80_MODE_LOCAL_REDUCE_RECOVERY",
                "status": "PASS_LOCAL_EQUIVALENCE",
                "input_path": "input/task39extra/v30_workstation_guided_original_h7p5.dat",
                "input_sha256": case["resolved"].input_sha256,
                "physical_model_sha256": case["resolved"].physical_model_sha256,
                "mode_manifest_sha256": case["physical"]["mode_sha256"],
                "attempt_history": [
                    {
                        "attempt": 1,
                        "status": "FAILED_DIAGNOSTIC_FIXTURE_SETUP",
                        "stage": "global_condensed_matrix_preallocation",
                        "exception": "ValueError: trace preallocation input validation failed: rank 0: ValueError: every appended row requires an explicit support group",
                        "interpretation": "No numerical global factor or PDE solve started; the diagnostic stopped while validating appended-row preallocation metadata.",
                        "correction": "Supply a conservative support group containing every locally owned cell and map all 80 carrier rows to group 0.",
                    },
                    {
                        "attempt": 2,
                        "status": "FAILED_DIAGNOSTIC_FIXTURE_SETUP",
                        "stage": "carrier_port_term_matrix_assembly",
                        "exception": "PETSc MatSetValues error 63: new nonzero at (2208,2208) caused a malloc",
                        "interpretation": "Explicit cell supports were accepted, but no dense port block was reserved and the condensed matrix had already completed final assembly; no numerical global factor or PDE solve started.",
                        "correction": "Enable dense_appended_block for the materialized diagnostic matrix and rerun.",
                    },
                    {
                        "attempt": 3,
                        "status": "FAILED_DIAGNOSTIC_FIXTURE_SETUP",
                        "stage": "carrier_port_term_matrix_assembly",
                        "exception": "PETSc MatSetValues error 63: new nonzero at (2208,2208) caused a malloc",
                        "interpretation": "Dense appended-block preallocation was present, but the matrix still had completed final assembly before carrier terms were added.",
                        "correction": "Set defer_final_assembly=True for the materialized local-identity fixture, matching the existing condensed-port assembly contract.",
                    },
                    {
                        "attempt": 4,
                        "status": "FAILED_DIAGNOSTIC_ASSERTION",
                        "stage": "carrier_support_validation",
                        "exception": "AssertionError: expected nonzero interior Bi/Di for the real V30 carrier",
                        "interpretation": "The actual 80-mode carrier has MPC-processed trace support but no cell-interior Bi/Di terms; the synthetic component fixture remains the separate nonzero-interior-port algebra check.",
                        "correction": "Retain the physical carrier and record its actual support audit instead of requiring interior port terms in this real FE local-kernel timing.",
                    }
                ],
                "fixture": {
                    "nedelec_degree": degree,
                    "mesh_target_nm": float(case["cfg"].mesh_target_size),
                    "cell_count": len(condensed.cell_recovery_maps),
                    "mode_count": len(carrier.entries),
                    "full_storage_rows": int(condensed.full_rows),
                    "active_trace_rows": int(condensed.active_rows),
                    "global_condensed_matrix_materialized": True,
                    "matrix_used_for": "carrier-port-term assembly input; no global numeric factorization",
                    "global_numeric_factor_built": False,
                    "MPC_slave_zero": True,
                    "nonzero_interior_rhs_norm": float(np.linalg.norm(rhs_values[interiors])),
                    "carrier_term_support": {
                        "nonzero_Bi": bool(port_terms_audit["nonzero_Bi"]),
                        "nonzero_Di": bool(port_terms_audit["nonzero_Di"]),
                        "carrier_rows_are_mpc_processed": bool(
                            port_terms_audit["carrier_rows_are_mpc_processed"]
                        ),
                    },
                    "carrier_port_term_cells": int(port_terms_audit["cells_with_port_terms"]),
                    "local_existing_class_count": len({cell.class_key for cell in condensed.cell_recovery_maps}),
                },
                "global_solve_scope": {
                    "factor_object": "fixed-output vector injection stub",
                    "one_factor_object_reused_for_all_routes": True,
                    "stub_solve_calls": factor.solve_calls,
                    "true_global_MatSolve_count": 0,
                    "complete_C_performance_claim": False,
                },
                "rhs_sha256": hashlib.sha256(rhs_values.astype("<c16", copy=False).tobytes()).hexdigest(),
                "fixed_active_alpha_sha256": hashlib.sha256(fixed_global_output.astype("<c16", copy=False).tobytes()).hexdigest(),
                "warmups": warmups,
                "interleaved_samples": samples,
                "paired_rounds": paired,
                "timing_summary": {
                    "median_process_cpu_seconds": median_cpu,
                    "median_wall_seconds": median_wall,
                    "bounded_batch_slower_pairs": {
                        "process_cpu": sum(
                            batch["process_cpu_seconds"]
                            > legacy["process_cpu_seconds"]
                            for legacy, batch in timing_pairs
                        ),
                        "wall": sum(
                            batch["wall_seconds"] > legacy["wall_seconds"]
                            for legacy, batch in timing_pairs
                        ),
                    },
                },
                "candidate_selection": {
                    "decision": (
                        "LOCAL_TIMING_POSITIVE_REQUIRES_MAIN_REVIEW"
                        if repeated_local_gain else "NOT_SELECTED"
                    ),
                    "selection_rule": (
                        "Select only if every paired round has lower process CPU "
                        "and wall time for bounded batching."
                    ),
                    "candidate_selected_for_formal_route": False,
                    "full_C_performance": "unknown_not_measured",
                },
                "max_relative_field_difference": max(item["relative_field_difference"] for item in paired),
                "max_relative_alpha_difference": max(item["relative_alpha_difference"] for item in paired),
                "max_port_closure_relative": max(sample["port_closure_relative"] for sample in samples),
                "candidate_selected_for_formal_route": False,
                "candidate_selection_pending_timing_review": False,
                "performance_scope": "real p4 FE/carrier local reduce/recovery only; fixed global vector stub; excludes a numeric p4 factor, native A4 repair loop, and complete C timing",
                "source_head": subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                    capture_output=True, text=True,
                ).stdout.strip(),
                "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
                "test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "runner_source_sha256": hashlib.sha256(
                    (ROOT / "src/runners/physical_p4_schur_v14.py").read_bytes()
                ).hexdigest(),
                "test_command": "source scripts/activate_myfenics_wsl.sh && TASK39EXTRA_V30_SAVE_L3_REAL80_RECORD=1 python -m pytest -q src/test/test_task39extra_v30_local_rhs_batch.py::test_l3_real_p4_80_mode_local_batch_qualification",
            }
            record_path = ROOT / (
                "docs/task039_extra_physical_multilevel/outcomes/records/"
                "workstation_guided_local_v30_l3_real80_local_kernel.json"
            )
            if os.environ.get("TASK39EXTRA_V30_SAVE_L3_REAL80_RECORD") == "1":
                record_path.parent.mkdir(parents=True, exist_ok=True)
                record_path.write_text(
                    json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        finally:
            inverse.destroy()
            rhs.destroy()
