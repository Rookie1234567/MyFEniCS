from __future__ import annotations

from mpi4py import MPI
import numpy as np
import pytest
from scipy import sparse

from src.adaptivity.hcurl_hanging_trace import (
    build_hanging_face_reference_pair,
)
from src.adaptivity.hcurl_trace_constraint_graph import (
    LinearTraceRelation,
    PhysicalTraceRowKey,
    RawCellTraceRows,
    compose_and_flatten_trace_constraints,
)


def _rows(prefix: int, count: int) -> tuple[PhysicalTraceRowKey, ...]:
    return tuple(
        PhysicalTraceRowKey(
            entity_dimension=2,
            entity_geometry_key=(prefix,),
            degree=4,
            mode=mode,
        )
        for mode in range(count)
    )


def _hanging_graph():
    pair = build_hanging_face_reference_pair(4)
    coarse = _rows(10, 40)
    fine = _rows(20, 144)
    relation = LinearTraceRelation(
        kind="hanging",
        slave_rows=fine,
        master_rows=coarse,
        slave_from_master=pair.hcurl_unique_fine_from_coarse,
        provenance={"patch": "two-cell-fixture"},
    )
    cells = (
        RawCellTraceRows((0,), coarse),
        *(
            RawCellTraceRows(
                (child + 1,),
                tuple(fine[int(row)] for row in child_rows),
            )
            for child, child_rows in enumerate(pair.hcurl_child_rows)
        ),
    )
    graph = compose_and_flatten_trace_constraints(
        (*coarse, *fine),
        (relation,),
        cells=cells,
    )
    return pair, graph


def test_hanging_rows_flatten_before_global_numbering_and_schur() -> None:
    pair, graph = _hanging_graph()
    assert graph.audit["pass"] is True
    assert graph.audit["raw_trace_rows"] == 184
    assert graph.audit["independent_trace_rows"] == 40
    assert graph.audit["primary_slave_rows"] == 144
    assert graph.audit["maximum_chain_depth"] == 1
    assert graph.audit["cell_map_count"] == 5
    assert graph.raw_from_independent.shape == (184, 40)
    assert all(
        int(np.linalg.matrix_rank(cell.full_trace_from_independent))
        == len(cell.independent_rows)
        for cell in graph.cells
    )

    rng = np.random.default_rng(350199)
    coarse_raw = rng.standard_normal((40, 40)) + 1j * rng.standard_normal(
        (40, 40)
    )
    coarse_schur = coarse_raw.conj().T @ coarse_raw + 2.0 * np.eye(40)
    expected = coarse_schur.copy()
    raw_matrix = np.zeros((184, 184), dtype=np.complex128)
    raw_matrix[:40, :40] = coarse_schur
    for child, child_rows in enumerate(pair.hcurl_child_rows):
        child_raw = rng.standard_normal((40, 40)) + 1j * rng.standard_normal(
            (40, 40)
        )
        child_schur = (
            child_raw.conj().T @ child_raw
            + (3.0 + child) * np.eye(40)
        )
        raw_rows = 40 + np.asarray(child_rows, dtype=np.int64)
        raw_matrix[np.ix_(raw_rows, raw_rows)] += child_schur
        child_restriction = pair.quadrants[child].hcurl_from_parent
        expected += (
            child_restriction.conj().T
            @ child_schur
            @ child_restriction
        )
    observed = (
        graph.raw_from_independent.conj().T
        @ raw_matrix
        @ graph.raw_from_independent
    )
    np.testing.assert_allclose(observed, expected, rtol=2.0e-12, atol=2.0e-10)


def test_large_root_identity_audit_stays_sparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows(90, 1024)

    def reject_dense_identity(*_args, **_kwargs):
        raise AssertionError("large root identity audit allocated dense storage")

    monkeypatch.setattr(np, "eye", reject_dense_identity)
    monkeypatch.setattr(sparse.csr_matrix, "toarray", reject_dense_identity)
    graph = compose_and_flatten_trace_constraints(rows, ())

    assert sparse.issparse(graph.raw_from_independent)
    assert sparse.issparse(graph.component_gram)
    assert graph.audit["root_identity_error"] == 0.0
    assert graph.audit["independent_trace_rows"] == 1024


def _periodic_hanging_chain(*, fine_phase_shift: float = 0.0):
    pair = build_hanging_face_reference_pair(4)
    coarse_lower = _rows(10, 40)
    coarse_upper = _rows(11, 40)
    fine_lower = _rows(20, 144)
    fine_upper = _rows(21, 144)
    phase = np.exp(0.2j)
    relations = (
        LinearTraceRelation(
            "hanging_lower",
            fine_lower,
            coarse_lower,
            pair.hcurl_unique_fine_from_coarse,
        ),
        LinearTraceRelation(
            "floquet_x_coarse",
            coarse_upper,
            coarse_lower,
            phase * np.eye(40),
        ),
        LinearTraceRelation(
            "hanging_upper",
            fine_upper,
            coarse_upper,
            pair.hcurl_unique_fine_from_coarse,
        ),
        LinearTraceRelation(
            "floquet_x_fine_compatibility",
            fine_upper,
            fine_lower,
            np.exp((0.2 + fine_phase_shift) * 1j) * np.eye(144),
            primary=False,
        ),
    )
    return compose_and_flatten_trace_constraints(
        (*coarse_lower, *coarse_upper, *fine_lower, *fine_upper),
        relations,
    )


def test_hanging_and_complex_floquet_chain_flattens_and_is_mpi_stable() -> None:
    graph = _periodic_hanging_chain()
    assert graph.audit["pass"] is True
    assert graph.audit["raw_trace_rows"] == 368
    assert graph.audit["independent_trace_rows"] == 40
    assert graph.audit["primary_slave_rows"] == 328
    assert graph.audit["maximum_chain_depth"] == 2
    assert graph.audit["secondary_relation_count"] == 1
    assert graph.audit["maximum_relation_residual"] <= 5.0e-11
    assert graph.audit["graph_sha256"] == (
        "24ef1c17a8886a7e01afb10082ecfba440d9a37b2e47187fdd853d38f9ec2662"
    )
    hashes = MPI.COMM_WORLD.allgather(graph.audit["graph_sha256"])
    assert len(set(hashes)) == 1


def test_constraint_cycles_conflicts_and_bad_secondary_fail_closed() -> None:
    left = _rows(1, 1)
    right = _rows(2, 1)
    with pytest.raises(RuntimeError, match="cycle"):
        compose_and_flatten_trace_constraints(
            (*left, *right),
            (
                LinearTraceRelation(
                    "left_from_right",
                    left,
                    right,
                    np.ones((1, 1)),
                ),
                LinearTraceRelation(
                    "right_from_left",
                    right,
                    left,
                    np.ones((1, 1)),
                ),
            ),
        )
    with pytest.raises(RuntimeError, match="conflicting"):
        compose_and_flatten_trace_constraints(
            (*left, *right),
            (
                LinearTraceRelation(
                    "first",
                    right,
                    left,
                    np.ones((1, 1)),
                ),
                LinearTraceRelation(
                    "second",
                    right,
                    left,
                    2.0 * np.ones((1, 1)),
                ),
            ),
        )
    with pytest.raises(RuntimeError, match="incompatible"):
        _periodic_hanging_chain(fine_phase_shift=0.1)


def test_trace_relation_inputs_fail_closed() -> None:
    rows = _rows(1, 2)
    with pytest.raises(ValueError, match="zero slave"):
        LinearTraceRelation(
            "zero",
            rows[:1],
            rows[1:],
            np.zeros((1, 1)),
        )
    with pytest.raises(ValueError, match="unique"):
        compose_and_flatten_trace_constraints(
            (rows[0], rows[0]),
            (),
        )
    with pytest.raises(ValueError, match="outside raw"):
        compose_and_flatten_trace_constraints(
            rows[:1],
            (
                LinearTraceRelation(
                    "unknown",
                    rows[:1],
                    rows[1:],
                    np.ones((1, 1)),
                ),
            ),
        )
