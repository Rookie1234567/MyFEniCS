from __future__ import annotations

from inspect import signature

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.static_condensed_iterative import (
    _solve_static_condensed_fgmres_core,
    _task037_g2_build_lor_hx_contraction_audit,
    _task037_g2_deterministic_vectors,
    _task037_g2_measure_lor_hx_source,
    _task037_g2_owner_vector_sha256,
    solve_never_materialized_overlap0125_partition_fgmres,
)
from src.solvers.static_fullspace_slab_oracle import (
    FullSpaceSlabBlockRecord,
    FullSpaceSlabCellRecord,
    apply_fullspace_slab_schur_action,
)

def _tiny_cells() -> tuple[tuple[FullSpaceSlabCellRecord, ...], np.ndarray]:
    a_ii = np.asarray([[2.0 + 0.2j]], dtype=np.complex128)
    a_it = np.asarray([[0.6 - 0.1j, -0.25 + 0.2j]], dtype=np.complex128)
    a_ti = np.asarray([[0.3 + 0.2j], [-0.15 + 0.1j]], dtype=np.complex128)
    a_tt = np.asarray(
        [
            [2.1 + 0.1j, 0.2 - 0.05j],
            [-0.1 + 0.04j, 1.7 + 0.3j],
        ],
        dtype=np.complex128,
    )
    recovery = np.linalg.solve(a_ii, -a_it)
    block = FullSpaceSlabBlockRecord(
        a_ii=a_ii,
        a_it=a_it,
        a_ti=a_ti,
        a_tt=a_tt,
        schur=a_tt + a_ti @ recovery,
    )
    cell = FullSpaceSlabCellRecord(
        block=block,
        canonical_cell_id=17,
        trace_expansion=np.eye(2, dtype=np.complex128),
        active_positions=np.asarray([0, 1], dtype=np.int64),
    )
    trace_shift = np.asarray([0.08j, -0.11j], dtype=np.complex128)
    return (cell,), trace_shift


class _DifferentProxy:
    def __init__(self) -> None:
        self.one_calls = 0
        self.two_calls = 0
        self._one = np.asarray(
            [[1.35 + 0.1j, 0.12 - 0.03j], [-0.08 + 0.02j, 1.1 - 0.04j]],
            dtype=np.complex128,
        )
        self._two = self._one @ self._one

    def apply_one_trace(self, rhs: np.ndarray) -> np.ndarray:
        self.one_calls += 1
        return np.linalg.solve(self._one, rhs)

    def apply_two_trace(self, rhs: np.ndarray) -> np.ndarray:
        self.two_calls += 1
        return np.linalg.solve(self._two, rhs)


def test_contraction_helper_uses_exact_action_and_two_repeated_applies():
    cells, trace_shift = _tiny_cells()
    owner_rows = np.asarray([101, 205], dtype=np.int64)
    deterministic = _task037_g2_deterministic_vectors(owner_rows)
    mixed = deterministic[0] + (0.5 - 0.25j) * deterministic[1]
    mixed -= 0.125j * deterministic[2]
    mixed /= np.linalg.norm(mixed)
    sources = (
        ("real_m3a_iter0", 0, np.asarray([1.0 + 0.2j, -0.35 + 0.5j])),
        ("real_m3a_iter20", 20, np.asarray([0.4 - 0.1j, 0.7 + 0.3j])),
        ("manufactured_mixed_high", None, mixed),
    )
    proxy = _DifferentProxy()
    comm = MPI.COMM_SELF
    proxy_difference_seen = False
    for label, iteration, source in sources:
        source = np.asarray(source, dtype=np.complex128)
        source_before = source.copy()
        current_matrix = np.asarray(
            [[1.8 + 0.1j, 0.05j], [0.02 - 0.04j, 1.55 + 0.08j]],
            dtype=np.complex128,
        )
        b4_matrix = np.asarray(
            [[1.25 + 0.2j, -0.1j], [0.03 + 0.05j, 1.4 - 0.1j]],
            dtype=np.complex128,
        )

        result = _task037_g2_measure_lor_hx_source(
            source_label=label,
            source_kind=(
                "real_m3a_screen_residual"
                if iteration is not None
                else "deterministic_normalized_manufactured_mixed_high"
            ),
            source_iteration=iteration,
            source_formula="fixed component fixture source",
            source_hash_domain=f"task037.g2.contraction.{label}.v1",
            source_values=source,
            owner_rows=owner_rows,
            owner_row_hash="owner-row-fixture-v1",
            cells=cells,
            active_size=2,
            trace_shift=trace_shift,
            owner=0,
            comm=comm,
            current_ilu_apply=lambda: np.linalg.solve(current_matrix, source),
            b4_apply=lambda: np.linalg.solve(b4_matrix, source),
            lor_hx_oracle=proxy,
            b4_step_count=4,
        )
        assert np.array_equal(source, source_before)
        assert result["status"] == "measurement_complete"
        assert result["source"]["label"] == label
        assert result["source"]["iteration"] == iteration
        assert result["source"]["owner_row_count"] == 2
        assert result["source"]["normalized"] is bool(
            np.isclose(np.linalg.norm(source), 1.0)
        )
        assert result["source"]["sha256"] == _task037_g2_owner_vector_sha256(
            owner_rows,
            source,
            domain=f"task037.g2.contraction.{label}.v1",
        )
        exact_matrix = np.column_stack(
            [
                apply_fullspace_slab_schur_action(
                    cells,
                    basis,
                    active_size=2,
                    trace_shift=trace_shift,
                )
                for basis in np.eye(2, dtype=np.complex128)
            ]
        )
        for method in (
            "current_trace_ilu",
            "b4_fixed_gmres4",
            "lor_hx_1v",
            "lor_hx_2v",
        ):
            record = result[method]
            assert record["apply_count"] == 2
            assert record["finite"] is True
            assert record["deterministic"] is True
            assert record["input_norm"] == pytest.approx(np.linalg.norm(source))
            correction = (
                np.linalg.solve(current_matrix, source)
                if method == "current_trace_ilu"
                else np.linalg.solve(b4_matrix, source)
                if method == "b4_fixed_gmres4"
                else np.linalg.solve(proxy._one, source)
                if method == "lor_hx_1v"
                else np.linalg.solve(proxy._two, source)
            )
            expected_post = source - exact_matrix @ correction
            expected_rho = np.linalg.norm(expected_post) / np.linalg.norm(source)
            assert record["rho"] == pytest.approx(expected_rho, rel=0.0, abs=1.0e-14)
            assert record["repeat_rho"] == pytest.approx(
                expected_rho, rel=0.0, abs=1.0e-14
            )
            if method == "current_trace_ilu":
                proxy_self_rho = np.linalg.norm(source - correction) / np.linalg.norm(
                    source
                )
                proxy_difference_seen = proxy_difference_seen or bool(
                    abs(expected_rho - proxy_self_rho) > 1.0e-8
                )
        assert result["b4_fixed_gmres4"]["fixed_local_krylov_steps"] == 4

    assert proxy.one_calls == 2 * len(sources)
    assert proxy.two_calls == 2 * len(sources)
    assert np.linalg.norm(mixed) == pytest.approx(1.0, rel=0.0, abs=1.0e-15)
    assert proxy_difference_seen is True


def _synthetic_measurement(
    best_rho: float,
    b4_rho: float,
    ilu_rho: float,
    one_seconds: float,
    two_seconds: float,
) -> dict[str, object]:
    method = {
        "finite": True,
        "deterministic": True,
    }
    return {
        "status": "measurement_complete",
        "best_lor_rho": best_rho,
        "current_trace_ilu": {
            **method,
            "rho": ilu_rho,
            "first_apply_seconds": 1.0,
        },
        "b4_fixed_gmres4": {
            **method,
            "rho": b4_rho,
            "first_apply_seconds": 2.0,
        },
        "lor_hx_1v": {
            **method,
            "rho": best_rho,
            "first_apply_seconds": one_seconds,
        },
        "lor_hx_2v": {
            **method,
            "rho": best_rho + 0.1,
            "first_apply_seconds": two_seconds,
        },
    }


def test_contraction_audit_aggregates_measured_gates_and_pending_iter20():
    measurements = {
        "real_m3a_iter0": _synthetic_measurement(1.0, 1.8, 0.5, 10.0, 12.0),
        "real_m3a_iter20": _synthetic_measurement(1.0, 1.5, 0.5, 10.0, 12.0),
        "manufactured_mixed_high": _synthetic_measurement(
            0.5, 0.75, 0.5, 10.0, 12.0
        ),
    }
    audit = _task037_g2_build_lor_hx_contraction_audit(measurements)
    assert audit["minimum_b4_comparison"] == {
        "real_m3a_iter20": True,
        "manufactured_mixed_high": True,
    }
    assert audit["minimum_b4_gate_pass"] is True
    assert audit["strong_ilu_comparison"] == {
        "real_m3a_iter0": True,
        "real_m3a_iter20": True,
    }
    assert audit["strong_ilu_gate_pass"] is True
    assert all(
        values["at_least_one_lor_hx_pass"]
        for values in audit["apply_time_comparison"].values()
    )
    assert audit["apply_time_gate_pass"] is True

    pending = dict(measurements)
    del pending["real_m3a_iter20"]
    pending_audit = _task037_g2_build_lor_hx_contraction_audit(pending)
    assert pending_audit["status"] == "pending_iter20"
    assert pending_audit["minimum_b4_gate_pass"] is False
    assert pending_audit["strong_ilu_gate_pass"] is False
    assert pending_audit["apply_time_gate_pass"] is False


def test_contraction_opt_in_signature_and_build_audit_stay_separate(
    monkeypatch,
):
    core_parameters = signature(_solve_static_condensed_fgmres_core).parameters
    public_parameters = signature(
        solve_never_materialized_overlap0125_partition_fgmres
    ).parameters
    contraction_name = "task037_extra_g2_slab14_lor_hx_contraction"
    oracle_name = "task037_extra_g2_slab14_lor_hx_oracle"
    assert core_parameters[contraction_name].default is False
    assert public_parameters[contraction_name].default is False
    assert core_parameters[oracle_name].default is False
    assert public_parameters[oracle_name].default is False

    forwarded = {}

    def fake_core(request, **kwargs):
        forwarded.update(kwargs)
        return "snapshot", {"build_only": True}

    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative._solve_static_condensed_fgmres_core",
        fake_core,
    )
    result = solve_never_materialized_overlap0125_partition_fgmres(
        object(),
        task037_extra_g2_slab14_identity=True,
        task037_extra_g2_slab14_lor_transfer=True,
        task037_extra_g2_slab14_lor_hx_oracle=True,
        task037_extra_g2_slab14_lor_hx_contraction=True,
    )
    assert result == ("snapshot", {"build_only": True})
    assert forwarded["task037_extra_g2_slab14_lor_hx_contraction"] is True
    assert forwarded["task037_extra_g2_slab14_lor_hx_oracle"] is True
