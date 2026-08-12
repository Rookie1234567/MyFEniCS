from __future__ import annotations

from pathlib import Path

import numpy as np

import benchmarks.run_task037_extra_h2b as h2b_runner
import benchmarks.run_task037_extra_m as m2_runner

from src.solvers.hcurl_h2b_m2_complement import (
    M2_HIGH_DIMENSION,
    M2_LOW_DIMENSION,
    M2_PATCH_DIMENSION,
    build_h2b_m2_cell_injection,
    build_h2b_m2_complement,
    measure_h2b_m2_source,
)
from src.solvers.hcurl_h2b_block_smoother import _p0_numeric_sha


def test_m2_runner_helper_ownership_and_cli(monkeypatch) -> None:
    """Exercise the M2-to-H2B helper bindings without entering a worker."""

    assert m2_runner._lazy_h2a is h2b_runner._lazy_h2a
    assert m2_runner._h2b_p1_authority is h2b_runner._p1_authority
    assert m2_runner.H2B_R2_MANIFEST is h2b_runner.H2B_R2_MANIFEST
    assert m2_runner._p0_numeric_sha is _p0_numeric_sha
    assert callable(m2_runner._h2b_source_arrays)
    assert callable(m2_runner._h2b_residual_source_arrays)

    sentinel = object()
    monkeypatch.setattr(m2_runner, "_lazy_h2a", lambda: sentinel)
    assert m2_runner._lazy_h2a() is sentinel

    for argv in (
        ("m2-worker", "--run-dir", "/tmp/m2"),
        ("m2-watchdog", "--run-dir", "/tmp/m2"),
        ("m2-check", "--run-dir", "/tmp/m2", "--output", "/tmp/m2.json"),
    ):
        assert m2_runner._parser().parse_args(argv).command == argv[0]
    assert "m2_patch_rows.npy" in m2_runner._m2_recorded_artifacts(Path("/tmp/m2"))


def test_m2_checker_source_scope_is_fail_closed() -> None:
    source = {
        "finite": True,
        "rho_scope": "complete_882_patch_rows",
        "global_rho_scope": "full_global_rows_diagnostic_only",
        "projected_high_closure_relative": 1.0e-14,
        "action_closure_relative": 2.0e-14,
        "full_space_rho_star": 0.2,
        "full_space_rho_unit": 0.3,
    }
    assert m2_runner._m2_source_gate_valid(source, 0.7)
    wrong_scope = dict(source, rho_scope="full_global_rows")
    assert not m2_runner._m2_source_gate_valid(wrong_scope, 0.7)
    nonfinite_projected = dict(source, projected_high_closure_relative=float("inf"))
    assert not m2_runner._m2_source_gate_valid(nonfinite_projected, 0.7)


class _Solve:
    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        return np.linalg.solve(self.matrix, rhs)


def test_m2_fixed_dimensions_and_deterministic_qr_carrier() -> None:
    assert (M2_PATCH_DIMENSION, M2_LOW_DIMENSION, M2_HIGH_DIMENSION) == (
        882,
        300,
        582,
    )
    injection = np.asarray(
        (
            (1.0 + 0.0j, 0.2 - 0.1j),
            (0.1 + 0.2j, 1.1 + 0.0j),
            (0.3 + 0.0j, -0.4 + 0.1j),
            (0.2 - 0.2j, 0.5 + 0.3j),
            (-0.1 + 0.4j, 0.7 - 0.2j),
            (0.9 + 0.1j, -0.2 + 0.5j),
        ),
        dtype=np.complex128,
        order="C",
    )
    first = build_h2b_m2_complement(
        injection,
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    second = build_h2b_m2_complement(
        injection.copy(),
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    assert first.audit["rank"] == 2
    assert first.audit["q_high_dimension"] == 4
    assert first.audit["rank_threshold"] == (
        first.audit["rank_threshold_factor"] * first.audit["injection_2_norm"]
    )
    assert first.audit["q_orthogonality_error"] <= 1.0e-12
    assert first.audit["split_reconstruction_error"] <= 1.0e-11
    assert np.array_equal(first.q_low, second.q_low)
    assert np.array_equal(first.q_high, second.q_high)
    assert first.q_low.flags.writeable is False
    assert first.q_high.flags.writeable is False
    assert first.retained_transform_bytes == first.q_low.nbytes + first.q_high.nbytes
    assert first.audit["retained_transform_bytes"] == first.retained_transform_bytes
    assert first.audit["dense_qh_retained"] is True
    assert first.audit["dense_qh_count"] == 1


def test_m2_constrained_cell_injection_uses_orientation_and_mpc_once() -> None:
    calls: list[tuple[int, int]] = []

    def local_apply(values: np.ndarray, cell_info: int) -> np.ndarray:
        calls.append((cell_info, values.size))
        return np.asarray(
            (values[0], values[1], values[0] - values[1], 2.0 * values[1]),
            dtype=np.complex128,
        )

    def p4_lift(values: np.ndarray) -> None:
        values[1] = (0.37 + 0.11j) * values[0]

    def p6_lift(values: np.ndarray) -> None:
        values[3] = (-0.2 + 0.4j) * values[0]

    injection = build_h2b_m2_cell_injection(
        patch_rows=np.asarray((20, 21, 22, 23), dtype=np.int64),
        p4_global_rows=np.asarray((10, 11), dtype=np.int64),
        p4_cell_dofs=np.asarray((0, 1), dtype=np.int32),
        p6_global_rows=np.asarray((20, 21, 22, 23), dtype=np.int64),
        p6_cell_dofs=np.asarray((0, 1, 2, 3), dtype=np.int32),
        p4_local_rows=2,
        p6_local_rows=4,
        cell_info=7,
        local_apply=local_apply,
        p4_lift=p4_lift,
        p6_lift=p6_lift,
    )
    assert injection.shape == (4, 2)
    assert np.all(np.isfinite(injection))
    assert calls == [(7, 2), (7, 2)]
    assert np.array_equal(
        injection[:, 0],
        np.asarray((1.0, 0.37 + 0.11j, 1.0 - (0.37 + 0.11j), (-0.2 + 0.4j)), dtype=np.complex128),
    )


def test_m2_full_space_source_oracle_binds_projected_patch_action() -> None:
    injection = np.asarray(
        (
            (1.0 + 0.0j, 0.0 + 0.0j),
            (0.0 + 0.0j, 1.0 + 0.0j),
            (1.0 + 0.0j, 1.0 + 0.0j),
            (0.2 + 0.1j, -0.3 + 0.2j),
            (0.5 - 0.2j, 0.7 + 0.1j),
            (-0.4 + 0.3j, 0.2 - 0.6j),
        ),
        dtype=np.complex128,
        order="C",
    )
    carrier = build_h2b_m2_complement(
        injection,
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    operator = np.asarray(
        (
            (3.0, 0.2, 0.0, 0.1, 0.0, 0.0),
            (0.2, 2.7, 0.1, 0.0, 0.0, 0.0),
            (0.0, 0.1, 2.5, 0.0, 0.2, 0.0),
            (0.1, 0.0, 0.0, 2.2, 0.0, 0.3),
            (0.0, 0.0, 0.2, 0.0, 2.9, 0.1),
            (0.0, 0.0, 0.0, 0.3, 0.1, 2.4),
        ),
        dtype=np.complex128,
        order="C",
    )
    high_matrix = np.ascontiguousarray(carrier.q_high.conj().T @ operator @ carrier.q_high)
    factor = _Solve(high_matrix)
    rhs = np.asarray((1.0 + 0.3j, -0.4 + 0.2j, 0.7 - 0.1j, 0.1 + 0.6j, -0.3j, 0.9 + 0.2j), dtype=np.complex128)
    first = measure_h2b_m2_source(
        rhs,
        np.arange(6, dtype=np.int64),
        carrier,
        factor,
        lambda values: operator @ values,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    second = measure_h2b_m2_source(
        rhs,
        np.arange(6, dtype=np.int64),
        carrier,
        factor,
        lambda values: operator @ values,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    assert first["action_closure_relative"] <= 1.0e-11
    assert first["projected_high_closure_relative"] <= 1.0e-11
    assert first["rho_scope"] == "complete_6_patch_rows"
    assert first["global_rho_scope"] == "full_global_rows_diagnostic_only"
    assert np.isfinite(first["full_space_rho_star"])
    assert first["correction_sha256"] == second["correction_sha256"]
    assert first["action_sha256"] == second["action_sha256"]
    assert abs(
        first["p4_low_energy_fraction"]
        + first["high_complement_energy_fraction"]
        - 1.0
    ) <= 1.0e-14
    assert np.array_equal(first["correction"], second["correction"])

    bad_action = lambda values: operator @ values + carrier.q_low @ np.asarray(
        (0.25 + 0.0j, -0.17 + 0.0j), dtype=np.complex128
    )
    bad = measure_h2b_m2_source(
        rhs,
        np.arange(6, dtype=np.int64),
        carrier,
        factor,
        bad_action,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    assert bad["projected_high_closure_relative"] <= 1.0e-11
    assert bad["action_closure_relative"] > 1.0e-6


def test_m2_rho_gate_uses_patch_rows_not_off_patch_spill() -> None:
    injection = np.asarray(
        (
            (1.0 + 0.0j, 0.0 + 0.0j),
            (0.0 + 0.0j, 1.0 + 0.0j),
            (1.0 + 0.0j, 1.0 + 0.0j),
            (0.2 + 0.1j, -0.3 + 0.2j),
            (0.5 - 0.2j, 0.7 + 0.1j),
            (-0.4 + 0.3j, 0.2 - 0.6j),
        ),
        dtype=np.complex128,
        order="C",
    )
    carrier = build_h2b_m2_complement(
        injection,
        expected_patch_dimension=6,
        expected_low_dimension=2,
    )
    operator = np.diag(
        np.asarray((2.0, 2.2, 2.4, 2.6, 2.8, 3.0), dtype=np.complex128)
    )
    high_matrix = np.ascontiguousarray(
        carrier.q_high.conj().T @ operator @ carrier.q_high
    )
    factor = _Solve(high_matrix)
    rows = np.arange(1, 7, dtype=np.int64)
    rhs = np.zeros(8, dtype=np.complex128)
    rhs[rows] = np.asarray(
        (1.0 + 0.3j, -0.4 + 0.2j, 0.7 - 0.1j, 0.1 + 0.6j, -0.3j, 0.9 + 0.2j),
        dtype=np.complex128,
    )
    rhs[0] = 1.7 - 0.2j
    rhs[-1] = -0.8 + 0.4j

    def action_without_spill(values: np.ndarray) -> np.ndarray:
        result = np.zeros_like(values)
        result[rows] = operator @ values[rows]
        return result

    def action_with_spill(values: np.ndarray) -> np.ndarray:
        result = action_without_spill(values)
        result[0] = 4.0 + 0.5j
        result[-1] = -3.0 + 0.25j
        return result

    base = measure_h2b_m2_source(
        rhs,
        rows,
        carrier,
        factor,
        action_without_spill,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    spill = measure_h2b_m2_source(
        rhs,
        rows,
        carrier,
        factor,
        action_with_spill,
        patch_matrix=operator,
        high_patch_matrix=high_matrix,
    )
    assert np.isclose(base["full_space_rho_star"], spill["full_space_rho_star"])
    assert np.isclose(base["full_space_rho_unit"], spill["full_space_rho_unit"])
    assert base["global_action_norm"] != spill["global_action_norm"]
    assert base["global_rho_star"] != spill["global_rho_star"]
