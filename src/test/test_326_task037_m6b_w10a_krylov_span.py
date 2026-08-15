from __future__ import annotations

import inspect

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
from src.solvers import krylov_span_diagnostic as span


def _basis_fixture(tmp_path, *, deficient=False):
    path = tmp_path / "v_basis.bin"
    values = np.asarray(
        [
            [1.0 + 0.1j, 0.2 - 0.1j, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.1 + 0.2j, 0.2 + 0.1j, 0.0, 0.0, 0.0],
            [0.1j, 0.0, 0.9 - 0.1j, 0.2, 0.0, 0.0],
            [0.0, 0.1, 0.0, 1.2 + 0.3j, 0.0, 0.0],
        ],
        dtype=np.complex128,
    )
    if deficient:
        values[3] = values[2]
    mapped = np.memmap(path, dtype=np.complex128, mode="w+", shape=values.shape, order="C")
    mapped[:] = values
    mapped.flush()
    del mapped
    return path, values


def test_w10a_streaming_projection_and_q_removed_actionable_formula(tmp_path):
    path, basis = _basis_fixture(tmp_path)
    coefficients = np.asarray([0.4 - 0.2j, -0.3 + 0.1j, 0.7 + 0.2j, -0.1 - 0.4j])
    control = basis.T @ coefficients
    target = basis.T @ np.asarray([0.2 + 0.1j, -0.4j, 0.3, 0.5 - 0.2j])
    target += np.asarray([0, 0, 0, 0, 0.4 + 0.1j, -0.2j], dtype=np.complex128)
    residuals = {"control_w5_iter200": control, "target_w7_cumulative400": target}
    first = span.analyze_v_basis(path, residuals, rows=6, columns=4, row_block=3)
    second = span.analyze_v_basis(path, residuals, rows=6, columns=4, row_block=3)

    assert first["pass"] is True
    assert first["rank"] == 4
    assert first["finite"] is True
    assert first["gram_valid"] is True
    assert first["eig_min"] >= -first["negative_eigenvalue_limit"]
    assert first["eig_max"] > 0.0
    assert first["audit"] == {
        "basis_path": str(path.resolve()),
        "rows": 6,
        "columns": 4,
        "dtype": "complex128",
        "layout": "C-order columns-contiguous",
        "row_block": 3,
        "block_count": 2,
        "column_read_count": 8,
        "mmap": True,
        "basis_in_memory": False,
        "retained_heap_basis_bytes": 0,
        "mapped_file_bytes": 4 * 6 * 16,
        "explicit_copied_block_bytes": 4 * 3 * 16,
        "explicit_copied_block_scope": "row-block copy only; conjugate and BLAS temporaries excluded",
        "gram_bytes": 4 * 4 * 16,
    }
    assert np.array_equal(first["gram"], second["gram"])
    assert all(np.array_equal(first["h"][name], second["h"][name]) for name in residuals)

    q = control / np.linalg.norm(control)
    target_measurement = first["measurements"]["target_w7_cumulative400"]
    q_overlap = abs(np.vdot(q, target)) ** 2 / np.linalg.norm(target) ** 2
    expected_actionable = max(target_measurement["captured_energy_ratio"] - q_overlap, 0.0)
    actionable = span.add_actionable_projection(target_measurement, q_overlap)
    assert actionable["captured_actionable_energy_ratio"] == pytest.approx(expected_actionable)
    assert actionable["rho_optimistic"] == pytest.approx(np.sqrt(1.0 - expected_actionable))
    assert first["measurements"]["control_w5_iter200"]["rho_full"] <= 1.0e-10


def test_w10a_rank_file_layout_and_non_solver_scope_fail_closed(tmp_path, monkeypatch):
    path, _ = _basis_fixture(tmp_path, deficient=True)
    values = np.ones(6, dtype=np.complex128)
    result = span.analyze_v_basis(
        path,
        {"control_w5_iter200": values, "target_w7_cumulative400": values},
        rows=6,
        columns=4,
        row_block=3,
    )
    assert result["pass"] is False
    assert result["rank"] < 4
    monkeypatch.setattr(span.np.linalg, "eigvalsh", lambda _gram: np.asarray([-1.0, 1.0, 2.0, 3.0]))
    negative = span.analyze_v_basis(
        path,
        {"control_w5_iter200": values, "target_w7_cumulative400": values},
        rows=6,
        columns=4,
        row_block=3,
    )
    assert negative["pass"] is False
    assert negative["problems"] == ["negative_eigenvalue"]
    with pytest.raises(ValueError):
        span.analyze_v_basis(
            path,
            {"control_w5_iter200": values, "target_w7_cumulative400": values},
            rows=5,
            columns=4,
            row_block=3,
        )
    source = inspect.getsource(runner._run_m6b_w10a_check)
    assert all(token not in source for token in ("dolfinx", "PETSc", "MPI", "build_m6b_outer_mat"))
    assert source.count("analyze_v_basis(") == 1
    assert "project_from_gram" in source

    invalid_analysis = {
        "rank": 0,
        "gram_valid": False,
        "gram_hermitian_defect": 0.0,
        "eig_min": -1.0,
        "eig_max": 1.0,
        "negative_eigenvalue_limit": 1.0e-12,
        "finite": True,
    }
    unavailable = {
        "control_w5_iter200": {"available": False, "actionable_available": False, "finite": False},
        "target_w7_cumulative400": {"available": False, "actionable_available": False, "finite": False},
    }
    gate = runner._m6b_w10a_numeric_gate(invalid_analysis, unavailable, False)
    assert gate["pass"] is False
    assert "target_rho" in gate["problems"]


def test_w10a_scratch_hash_path_and_compact_audit_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", 6)
    monkeypatch.setattr(runner, "M6B_W10A_COLUMNS", 4)
    monkeypatch.setattr(runner, "M6B_W10A_BASIS_BYTES", 4 * 6 * 16)
    raw = tmp_path / "raw"
    basis = raw / runner.M6B_W10A_BASIS_RELATIVE_PATH
    basis.parent.mkdir(parents=True)
    basis.write_bytes(b"\0" * runner.M6B_W10A_BASIS_BYTES)
    audit = {
        "rows": 6,
        "capacity": 4,
        "written_count": 4,
        "allocated_bytes": 4 * 6 * 16,
        "dtype": "complex128",
        "path": str(basis.resolve()),
    }
    record = {"screen": {"core_audit": {"v_basis": audit}}}
    checked = runner._m6b_w10a_basis_authority(raw, record)
    assert checked["current_scratch_hash_bound"] is True
    assert checked["historical_producer_hash_available"] is False
    assert checked["sha256"] == runner._sha256_file(basis)

    missing = {"screen": {"core_audit": {"v_basis": dict(audit)}}}
    del missing["screen"]["core_audit"]["v_basis"]["written_count"]
    with pytest.raises(ValueError):
        runner._m6b_w10a_basis_authority(raw, missing)
    wrong_path = {"screen": {"core_audit": {"v_basis": dict(audit, path=str(tmp_path / "other.bin"))}}}
    with pytest.raises(ValueError):
        runner._m6b_w10a_basis_authority(raw, wrong_path)


def test_w10a_parser_and_target_gate_do_not_trust_top_level_pass(tmp_path):
    args = runner._parser().parse_args(
        [
            "m6b-w10a-check",
            "--w5-raw-dir", str(tmp_path / "w5"),
            "--w5-compact", str(tmp_path / "w5.json"),
            "--w7-raw-dir", str(tmp_path / "w7"),
            "--w7-compact", str(tmp_path / "w7.json"),
            "--output", str(tmp_path / "out.json"),
            "--expected-source-sha", "a" * 40,
        ]
    )
    assert args.command == "m6b-w10a-check"
    analysis = {
        "rank": 201,
        "gram_hermitian_defect": 0.0,
        "gram_valid": True,
        "eig_min": 0.5,
        "eig_max": 1.0,
        "negative_eigenvalue_limit": 1.0e-12,
        "finite": True,
    }
    measurements = {
        "control_w5_iter200": {
            "finite": True,
            "normal_closure": 0.0,
            "captured_energy_ratio": 1.0,
            "captured_actionable_energy_ratio": 0.0,
            "rho_full": 0.0,
            "rho_optimistic": 1.0,
        },
        "target_w7_cumulative400": {
            "finite": True,
            "normal_closure": 0.0,
            "captured_energy_ratio": 0.05,
            "captured_actionable_energy_ratio": 0.05,
            "rho_full": 0.99,
            "rho_optimistic": 0.95,
            "pass": True,
        },
    }
    gate = runner._m6b_w10a_numeric_gate(analysis, measurements, True)
    assert gate["pass"] is False
    assert gate["problems"] == ["target_rho"]


def test_w10a_captured_energy_range_is_fail_closed():
    invalid = span.project_from_gram(
        np.eye(1, dtype=np.complex128),
        np.asarray([2.0 + 0.0j]),
        1.0,
        1.0,
    )
    assert invalid["finite"] is False
    assert invalid["problems"] == ["captured_energy_range"]
    measurement = {"finite": True, "captured_energy_ratio": -1.0e-4}
    with pytest.raises(ValueError):
        span.add_actionable_projection(measurement, 0.0)
    measurement["captured_energy_ratio"] = 1.1
    with pytest.raises(ValueError):
        span.add_actionable_projection(measurement, 0.0)


def test_w10a_invalid_projection_record_is_json_safe_and_not_actionable():
    record = runner._m6b_w10a_measurement_record(
        {
            "finite": False,
            "normal_closure": float("nan"),
            "captured_energy": float("nan"),
            "captured_energy_ratio": float("nan"),
            "captured_energy_ratio_raw": float("nan"),
            "rho_full": float("nan"),
            "coefficient_norm": float("nan"),
        },
        0.0,
        span,
        allow_actionable=False,
    )
    assert record["finite"] is False
    assert record["actionable_available"] is False
    assert all(value is None for key, value in record.items() if key in {
        "normal_closure", "captured_energy", "captured_energy_ratio", "rho_full", "coefficient_norm"
    })
