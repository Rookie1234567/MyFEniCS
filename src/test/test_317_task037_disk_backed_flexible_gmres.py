from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.solvers.disk_backed_flexible_gmres import DiskBackedFlexibleGMRES


def _fixture() -> tuple[np.ndarray, np.ndarray]:
    rows = 9
    matrix = np.zeros((rows, rows), dtype=np.complex128)
    for row in range(rows):
        matrix[row, row] = 2.0 + 0.17j + 0.08 * row
        matrix[row, (row + 1) % rows] = 0.21 - 0.06j
        matrix[row, (row + 2) % rows] = -0.13 + 0.09j
        matrix[row, (row - 1) % rows] = 0.07 + 0.04j
        matrix[row, (row + 4) % rows] = -0.05 + 0.02j
    rhs = np.asarray(
        [1.0 + 0.11 * row + 1j * (-0.3 + 0.07 * row) for row in range(rows)],
        dtype=np.complex128,
    )
    return matrix, rhs


def _action_pc(matrix: np.ndarray):
    def action(values: np.ndarray) -> np.ndarray:
        return np.asarray(matrix @ values, dtype=np.complex128)

    def pc(values: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(values))
        scale = (0.84 + 0.03j) + (0.11 - 0.05j) / (1.0 + norm)
        return np.asarray(scale * values, dtype=np.complex128)

    return action, pc


def _reference(
    matrix: np.ndarray,
    rhs: np.ndarray,
    checkpoints: tuple[int, ...],
    max_steps: int,
):
    action, pc = _action_pc(matrix)
    x0 = np.zeros_like(rhs)
    residual = rhs - action(x0)
    beta = float(np.linalg.norm(residual))
    v_columns = [residual / beta]
    z_columns: list[np.ndarray] = []
    hessenberg = np.zeros((max_steps + 1, max_steps), dtype=np.complex128)
    least_squares_rhs = np.zeros(max_steps + 1, dtype=np.complex128)
    least_squares_rhs[0] = beta
    events = {}
    final_h_rows = 0

    for column in range(max_steps):
        z_column = pc(v_columns[column])
        z_columns.append(z_column.copy())
        work = action(z_column)
        operator_column_norm = float(np.linalg.norm(work))
        for _pass in range(2):
            for previous in range(column + 1):
                coefficient = np.vdot(v_columns[previous], work)
                hessenberg[previous, column] += coefficient
                work -= coefficient * v_columns[previous]
        next_norm = float(np.linalg.norm(work))
        hessenberg[column + 1, column] = next_norm
        h_rows = column + 2
        if next_norm <= 64.0 * np.finfo(float).eps * max(
            1.0, operator_column_norm
        ):
            h_rows = column + 1
        else:
            v_columns.append(work / next_norm)
        final_h_rows = h_rows

        iteration = column + 1
        if iteration in checkpoints:
            h = hessenberg[:h_rows, :iteration]
            coefficients = np.linalg.lstsq(
                h,
                least_squares_rhs[:h_rows],
                rcond=None,
            )[0]
            candidate = x0.copy()
            for index, z_column in enumerate(z_columns):
                candidate += coefficients[index] * z_column
            candidate_action = action(candidate)
            candidate_residual = rhs - candidate_action
            events[str(iteration)] = {
                "solution": candidate.copy(),
                "action": candidate_action.copy(),
                "residual": candidate_residual.copy(),
                "rhs": rhs.copy(),
                "true_relative_residual": float(
                    np.linalg.norm(candidate_residual) / np.linalg.norm(rhs)
                ),
                "hessenberg": h.copy(),
            }
        if h_rows == column + 1:
            break

    iterations = iteration
    h = hessenberg[:final_h_rows, :iterations]
    coefficients = np.linalg.lstsq(
        h,
        least_squares_rhs[:final_h_rows],
        rcond=None,
    )[0]
    solution = x0.copy()
    for index, z_column in enumerate(z_columns):
        solution += coefficients[index] * z_column
    return solution, h, events


def _run(
    root: Path,
    matrix: np.ndarray,
    rhs: np.ndarray,
):
    action, pc = _action_pc(matrix)
    observed = {}

    def observer(event):
        key = str(event["iteration"])
        observed[key] = {
            field: np.array(event[field], copy=True)
            for field in ("solution", "action", "residual", "rhs")
        }
        observed[key]["true_relative_residual"] = event["true_relative_residual"]

    solver = DiskBackedFlexibleGMRES(
        action,
        pc,
        max_steps=6,
        checkpoints=(1, 3, 6),
    )
    result = solver.solve(rhs, scratch_dir=root, observer=observer)
    return result, observed


def test_disk_backed_flexible_gmres_matches_memory_reference_and_repeats(tmp_path):
    matrix, rhs = _fixture()
    reference_solution, reference_hessenberg, reference_events = _reference(
        matrix,
        rhs,
        (1, 3, 6),
        6,
    )
    first, first_events = _run(tmp_path / "first", matrix, rhs)
    second, second_events = _run(tmp_path / "second", matrix, rhs)

    assert first.iterations == second.iterations == 6
    assert not first.happy_breakdown
    assert np.array_equal(first.solution, second.solution)
    assert np.array_equal(first.hessenberg, second.hessenberg)
    assert np.array_equal(first.solution, reference_solution)
    assert np.array_equal(first.hessenberg, reference_hessenberg)
    assert set(first_events) == set(reference_events) == {"1", "3", "6"}
    for key in first_events:
        for field in ("solution", "action", "residual", "rhs"):
            assert np.array_equal(first_events[key][field], second_events[key][field])
            assert np.allclose(
                first_events[key][field],
                reference_events[key][field],
                rtol=0.0,
                atol=1.0e-12,
            )
        assert first_events[key]["true_relative_residual"] == pytest.approx(
            reference_events[key]["true_relative_residual"],
            abs=1.0e-12,
        )
    assert first.final_relative_residual == pytest.approx(
        np.linalg.norm(matrix @ first.solution - rhs) / np.linalg.norm(rhs),
        abs=1.0e-12,
    )
    assert first.audit["action_count"] == second.audit["action_count"]
    assert first.audit["action_count"] == 9
    assert first.audit["initial_action_count"] == 0
    assert first.audit["pc_count"] == second.audit["pc_count"] == 6
    assert first.audit["checkpoint_count"] == 3
    assert first.audit["observer_count"] == 3
    assert first.audit["orthogonalization_passes"] == 2
    assert first.audit["mmap"] is False
    assert first.audit["basis_in_memory"] is False
    assert first.audit["retained_full_vector_count"] == 1
    assert first.audit["checkpoint_set_complete"] is True
    assert first.audit["bounded_full_vector_gate"] is True
    assert first.audit["v_basis"]["written_count"] == 7
    assert first.audit["z_basis"]["written_count"] == 6
    assert first.audit["v_basis"]["write_count"] == 7
    assert first.audit["z_basis"]["write_count"] == 6
    assert first.audit["v_basis"]["read_count"] == 42
    assert first.audit["z_basis"]["read_count"] == 10
    assert first.audit["scratch_bytes"] == (
        (7 + 6) * rhs.size * np.dtype(np.complex128).itemsize
    )
    with pytest.raises(FileExistsError):
        _run(tmp_path / "first", matrix, rhs)


def test_disk_backed_basis_file_sizes_and_p6_payload_contract(tmp_path):
    rows = 173_802
    itemsize = np.dtype(np.complex128).itemsize
    assert rows * 201 * itemsize == 558_947_232
    assert rows * 200 * itemsize == 556_166_400
    assert rows * (201 + 200) * itemsize == 1_115_113_632

    matrix, rhs = _fixture()
    result, _observed = _run(tmp_path / "files", matrix, rhs)
    v_basis = result.audit["v_basis"]
    z_basis = result.audit["z_basis"]
    assert Path(v_basis["path"]).stat().st_size == 7 * rhs.size * itemsize
    assert Path(z_basis["path"]).stat().st_size == 6 * rhs.size * itemsize
    assert v_basis["dtype"] == z_basis["dtype"] == "complex128"
    assert v_basis["mmap"] is z_basis["mmap"] is False
    assert result.audit["scratch_mmap"] is False
    assert result.audit["scratch_basis_in_memory"] is False
    assert result.audit["retained_full_vector_bytes"] == rhs.nbytes
    assert result.audit["bounded_full_vector_bytes"] <= 64 * 1024 * 1024


def test_breakdown_scale_uses_forward_column_norm(tmp_path):
    matrix = np.ones((3, 3), dtype=np.complex128)
    rhs = np.ones(3, dtype=np.complex128)
    solver = DiskBackedFlexibleGMRES(
        lambda values: matrix @ values,
        lambda values: values.copy(),
        max_steps=2,
        checkpoints=(1,),
    )
    result = solver.solve(rhs, scratch_dir=tmp_path / "breakdown")

    assert result.happy_breakdown is True
    assert result.iterations == 1
    assert result.audit["last_breakdown_scale"] == pytest.approx(3.0)
    assert result.audit["last_breakdown_threshold"] == pytest.approx(
        64.0 * np.finfo(float).eps * 3.0
    )
    assert result.audit["breakdown_rule"] == (
        "64*eps*max(1,norm(A*z_j before orthogonalization))"
    )
