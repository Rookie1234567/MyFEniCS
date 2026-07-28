from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest
from scipy import sparse

from src.adaptivity.variable_p_transfer import (
    PETScSelectedRowLayout,
)
from src.solvers.hcurl_variable_p_reduction import (
    _reduced_trace_auxiliary_norms,
)


def _distributed_vector(global_size: int) -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(
        (PETSc.DECIDE, global_size),
        comm=MPI.COMM_WORLD,
    )
    start, stop = map(int, vector.getOwnershipRange())
    rows = np.arange(start, stop, dtype=np.float64)
    vector.getArray()[:] = rows + 1j * (0.25 * rows + 1.0)
    vector.assemble()
    return vector


def _expected_values(rows: np.ndarray) -> np.ndarray:
    values = np.asarray(rows, dtype=np.float64)
    return values + 1j * (0.25 * values + 1.0)


def test_selected_row_layout_empty_and_duplicate_requests() -> None:
    if MPI.COMM_WORLD.size not in {1, 8}:
        pytest.skip("selected-row layout qualifies serial and MPI8")
    vector = _distributed_vector(3 * MPI.COMM_WORLD.size + 2)
    try:
        with PETScSelectedRowLayout.create(
            vector,
            np.empty(0, dtype=np.int64),
        ) as empty:
            assert empty.gather(vector).shape == (0,)
            assert empty.audit["selected_unique_row_count_local"] == 0
            assert empty.audit["replicated_full_vector_bytes_per_rank"] == 0

        mixed_request = (
            np.empty(0, dtype=np.int64)
            if MPI.COMM_WORLD.size == 8 and MPI.COMM_WORLD.rank == 0
            else np.asarray([0, vector.getSize() - 1], dtype=np.int64)
        )
        with PETScSelectedRowLayout.create(
            vector,
            mixed_request,
        ) as mixed:
            np.testing.assert_allclose(
                mixed.gather(vector),
                _expected_values(mixed.global_rows),
                rtol=0.0,
                atol=0.0,
            )

        start, stop = map(int, vector.getOwnershipRange())
        first = min(start, vector.getSize() - 1)
        last = max(first, stop - 1)
        requested = np.asarray(
            [first, last, first, vector.getSize() - 1],
            dtype=np.int64,
        )
        with PETScSelectedRowLayout.create(vector, requested) as layout:
            observed = layout.gather(vector)
            np.testing.assert_allclose(
                observed,
                _expected_values(layout.global_rows),
                rtol=0.0,
                atol=0.0,
            )
            assert layout.audit["duplicate_request_count_local"] >= 1
            np.testing.assert_array_equal(
                layout.positions(layout.global_rows),
                np.arange(len(layout.global_rows)),
            )
    finally:
        vector.destroy()


def test_selected_row_layout_reads_remote_ownership_boundaries_mpi8() -> None:
    if MPI.COMM_WORLD.size != 8:
        pytest.skip("remote selected-row contract is an MPI8 qualification")
    vector = _distributed_vector(4 * MPI.COMM_WORLD.size)
    try:
        start, stop = map(int, vector.getOwnershipRange())
        previous_remote = (start - 1) % vector.getSize()
        next_remote = stop % vector.getSize()
        requested = np.asarray(
            [
                start,
                stop - 1,
                previous_remote,
                next_remote,
                next_remote,
            ],
            dtype=np.int64,
        )
        with PETScSelectedRowLayout.create(vector, requested) as layout:
            observed = layout.gather(vector)
            np.testing.assert_allclose(
                observed,
                _expected_values(layout.global_rows),
                rtol=0.0,
                atol=0.0,
            )
            assert previous_remote in layout.global_rows
            assert next_remote in layout.global_rows
            assert layout.audit["full_vector_allgather_used"] is False
    finally:
        vector.destroy()


def test_work_owned_component_norm_matches_global_math() -> None:
    if MPI.COMM_WORLD.size not in {1, 8}:
        pytest.skip("component norms qualify serial and MPI8")
    trace_rows = 2 * MPI.COMM_WORLD.size + 1
    auxiliary_rows = 3
    diagonal = 1.5 + 0.05 * np.arange(trace_rows)
    gram = sparse.diags(diagonal, format="lil", dtype=np.complex128)
    for row in range(0, trace_rows - 1, 2):
        gram[row, row + 1] = 0.125
        gram[row + 1, row] = 0.125
    gram = sparse.csr_matrix(gram)
    system = SimpleNamespace(
        active_trace_rows=trace_rows,
        appended_rows=auxiliary_rows,
        trace_constraints=SimpleNamespace(component_gram=gram),
        entity_map=SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_WORLD)
        ),
    )
    vector = _distributed_vector(trace_rows + auxiliary_rows)
    factor_cache: dict[str, object] = {}
    try:
        observed, first_audit = _reduced_trace_auxiliary_norms(
            system,
            (
                ("primal", vector, "primal"),
                ("dual", vector, "dual"),
            ),
            factor_cache=factor_cache,
        )
        second, second_audit = _reduced_trace_auxiliary_norms(
            system,
            (("dual", vector, "dual"),),
            factor_cache=factor_cache,
        )
        rows = np.arange(trace_rows + auxiliary_rows)
        values = _expected_values(rows)
        trace = values[:trace_rows]
        auxiliary = values[trace_rows:]
        expected_primal = np.sqrt(
            np.vdot(trace, gram @ trace).real
            + np.vdot(auxiliary, auxiliary).real
        )
        expected_dual = np.sqrt(
            np.vdot(
                trace,
                sparse.linalg.spsolve(gram.tocsc(), trace),
            ).real
            + np.vdot(auxiliary, auxiliary).real
        )
        assert observed["primal"] == pytest.approx(
            expected_primal,
            rel=3.0e-13,
        )
        assert observed["dual"] == pytest.approx(
            expected_dual,
            rel=3.0e-13,
        )
        assert second["dual"] == pytest.approx(
            expected_dual,
            rel=3.0e-13,
        )
        assert first_audit["global_component_gram_factorizations"] == 0
        assert first_audit["local_component_factorizations_new"] >= 0
        assert second_audit["local_component_factorizations_new"] == 0
        assert (
            second_audit["local_component_factor_cache_hits"]
            == second_audit["work_owned_component_count_local"]
        )
        assert second_audit["replicated_reduced_vector_bytes_per_rank"] == 0
    finally:
        vector.destroy()


def test_formal_recovery_sources_do_not_call_allgather() -> None:
    sources = (
        Path("src/adaptivity/variable_p_transfer.py"),
        Path("src/solvers/hcurl_variable_p_reduction.py"),
    )
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "allgather"
        ]
        assert calls == [], f"{path} retains a Python allgather call"
