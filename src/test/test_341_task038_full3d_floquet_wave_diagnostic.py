from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.fullspace_physical_wave_diagnostic import (
    V15_MODE_MANIFEST_SHA256,
    V15_SELECTED_MODE_INDICES,
    V15_SELECTOR_PAYLOAD_SHA256,
    hermitian_dot,
    project_onto_q,
    relative_error,
    select_v15_modes,
    two_pass_mgs,
    two_pass_mgs_append,
)


ROOT = Path(__file__).resolve().parents[2]
RUNNER = "benchmarks.run_task038_full3d_floquet_wave_small_oracle"
CHECKER = "benchmarks.task038_full3d_floquet_wave_small_oracle_checker"


def _manifest() -> dict:
    selected = {index: rank for rank, index in enumerate(V15_SELECTED_MODE_INDICES)}
    rows = []
    for index in range(80):
        rank = selected.get(index)
        rows.append(
            {
                "mode_index": index,
                "classification": "propagating" if index < 78 else "evanescent",
                "side": "top" if rank is not None and rank < 16 else "bottom",
                "polarization": "s" if rank is not None and rank % 2 == 0 else "p",
                "beta": {
                    "real": float(rank if rank is not None else 100 + index),
                    "imag": 0.0,
                },
                "refractive_index": {"real": 1.0, "imag": 0.0},
            }
        )
    return {
        "mode_manifest_sha256": V15_MODE_MANIFEST_SHA256,
        "wavelength_nm": 13.5,
        "modes": rows,
    }


def _partition(size: int, rank: int, count: int) -> tuple[int, int]:
    base, remainder = divmod(count, size)
    start = rank * base + min(rank, remainder)
    stop = start + base + (rank < remainder)
    return start, stop


def test_selector_fixed_indices_and_payload_authority() -> None:
    selection = select_v15_modes(
        _manifest()["modes"],
        wavelength_nm=13.5,
        mode_manifest_sha256=V15_MODE_MANIFEST_SHA256,
    )
    assert tuple(selection["selected_mode_indices"]) == V15_SELECTED_MODE_INDICES
    assert selection["selector_payload_sha256"] == V15_SELECTOR_PAYLOAD_SHA256
    assert selection["selected_side_counts"] == {"top": 16, "bottom": 16}
    assert selection["selected_polarization_counts"] == {"s": 16, "p": 16}


def test_synthetic_algebra_identity_linearity_repeat_and_adjoint() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in {1, 2}:
        pytest.skip("F1 oracle is specified for MPI1/MPI2")
    start, stop = _partition(comm.size, comm.rank, 24)
    indices = np.arange(start, stop, dtype=float)
    x = (0.25 + 0.01 * indices) + 1j * (0.5 - 0.02 * indices)
    y = (0.75 - 0.03 * indices) + 1j * (0.1 + 0.015 * indices)
    x_before = x.copy()

    def modal(value: np.ndarray) -> np.ndarray:
        return (1.25 - 0.1j) * value

    def pc(value: np.ndarray) -> np.ndarray:
        return (0.8 + 0.05j) * value

    modal_once = modal(x)
    modal_repeat = modal(x)
    assert relative_error(modal_once, modal_repeat, comm) <= 1e-12
    assert relative_error(modal(x + y), modal(x) + modal(y), comm) <= 1e-12
    assert relative_error(modal_once, (1.25 - 0.1j) * x, comm) <= 1e-12
    pc_once = pc(modal_once)
    assert relative_error(pc_once, (0.8 + 0.05j) * modal_once, comm) <= 1e-12
    assert np.array_equal(x, x_before)

    basis = np.column_stack(
        [
            0.1 + 0.01 * indices,
            0.2 - 0.02j * indices,
            (0.3 + 0.01j) * np.ones_like(indices),
        ]
    )
    coefficient = np.array([0.3 - 0.1j, -0.2 + 0.4j, 0.15 + 0.05j])
    embedded = basis @ coefficient
    adjoint_local = basis.conj().T @ y
    adjoint = np.asarray(comm.allreduce(adjoint_local), dtype=np.complex128)
    lhs = hermitian_dot(embedded, y, comm)
    rhs = np.vdot(coefficient, adjoint)
    assert abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-30) <= 1e-11


@pytest.mark.skipif(
    os.environ.get("RUN_V15_REAL_SMALL_ORACLE") != "1",
    reason="real MPI1/MPI2 oracle is an explicit qualified command",
)
def test_real_small_runner_checker_cli_mpi1_mpi2(tmp_path: Path) -> None:
    """Exercise the production runner twice; the checker owns the comparison."""

    if MPI.COMM_WORLD.size != 1:
        pytest.skip("launch this CLI contract from an MPI1 pytest process")
    input_path = ROOT / "input/templates/full3d_iterative_example.dat"
    source_sha = subprocess.check_output(
        [
            "git",
            "--git-dir",
            str(ROOT / ".git-codex"),
            "--work-tree",
            str(ROOT),
            "rev-parse",
            "HEAD",
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    records = {}
    for mpi_size in (1, 2):
        root = tmp_path / f"mpi{mpi_size}"
        record_path = root / "record.json"
        command = [
            "mpiexec",
            "-n",
            str(mpi_size),
            str(ROOT / ".venv/bin/python"),
            "-m",
            RUNNER,
            "--mode",
            "real-small-p3-h50",
            "--record",
            str(record_path),
            "--source-sha",
            source_sha,
            "--input",
            str(input_path),
            "--cache-dir",
            str(root / "cache"),
            "--expected-mpi-size",
            str(mpi_size),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        records[mpi_size] = record_path

    checker_path = tmp_path / "checker.json"
    checker = [
        sys.executable,
        "-m",
        CHECKER,
        "--mode",
        "real-small-p3-h50",
        "--record",
        str(records[1]),
        "--compare-record",
        str(records[2]),
        "--expected-mpi-size",
        "1",
        "--expected-source-sha",
        source_sha,
        "--output",
        str(checker_path),
    ]
    subprocess.run(checker, cwd=ROOT, check=True)
    checked = json.loads(checker_path.read_text(encoding="utf-8"))
    assert checked["passed"] is True
    assert checked["classification"] == "F1_REAL_SMALL_ORACLE_PASS"


def test_two_pass_mgs_and_projection_synthetic() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in {1, 2}:
        pytest.skip("F1 oracle is specified for MPI1/MPI2")
    start, stop = _partition(comm.size, comm.rank, 24)
    indices = np.arange(start, stop, dtype=float)
    columns = [
        (1.0 + 0.02 * indices) + 1j * 0.1,
        (0.2 - 0.01 * indices) + 1j * (0.8 + 0.01 * indices),
        (0.5 + 0.03j) * np.cos(indices / 7.0),
    ]
    q, r = two_pass_mgs(columns, comm)
    original = np.column_stack(columns)
    assert relative_error(q @ r, original, comm) <= 1e-12
    appended, coefficients, norm = two_pass_mgs_append(
        q[:, :2], original[:, 2], comm
    )
    assert relative_error(appended, q[:, 2], comm) <= 1e-12
    assert relative_error(coefficients, r[:2, 2], comm) <= 1e-12
    assert abs(norm - r[2, 2].real) / max(abs(r[2, 2].real), 1e-30) <= 1e-12
    gram = np.asarray(
        [
            [hermitian_dot(q[:, i], q[:, j], comm) for j in range(q.shape[1])]
            for i in range(q.shape[1])
        ]
    )
    assert np.linalg.norm(gram - np.eye(3), ord=2) <= 1e-12
    metrics = project_onto_q(q, original[:, 0], comm)
    assert metrics["rho"] <= 1e-12
    assert metrics["captured_energy"] >= 1.0 - 1e-12


def test_selector_runner_checker_and_mutation(tmp_path: Path) -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("subprocess contract test runs once under MPI1")
    manifest_path = tmp_path / "manifest.json"
    record_path = tmp_path / "record.json"
    checker_path = tmp_path / "checker.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    source_sha = "a" * 40
    runner = [
        sys.executable,
        "-m",
        RUNNER,
        "--manifest",
        str(manifest_path),
        "--record",
        str(record_path),
        "--source-sha",
        source_sha,
    ]
    subprocess.run(runner, cwd=ROOT, check=True)
    checker = [
        sys.executable,
        "-m",
        CHECKER,
        "--record",
        str(record_path),
        "--manifest",
        str(manifest_path),
        "--expected-source-sha",
        source_sha,
        "--output",
        str(checker_path),
    ]
    subprocess.run(checker, cwd=ROOT, check=True)
    assert json.loads(checker_path.read_text(encoding="utf-8"))["passed"] is True
    mutated = json.loads(record_path.read_text(encoding="utf-8"))
    mutated["selector"]["selected_mode_indices"][0] += 1
    bad_record = tmp_path / "bad_record.json"
    bad_output = tmp_path / "bad_checker.json"
    bad_record.write_text(json.dumps(mutated), encoding="utf-8")
    bad_checker = checker[:-1] + [str(bad_output)]
    bad_checker[bad_checker.index(str(record_path))] = str(bad_record)
    result = subprocess.run(bad_checker, cwd=ROOT)
    assert result.returncode != 0
    assert json.loads(bad_output.read_text(encoding="utf-8"))["passed"] is False

    for suffix, malformed in (
        (
            "missing-selector",
            {key: value for key, value in mutated.items() if key != "selector"},
        ),
        ("wrong-selector-type", {**mutated, "selector": []}),
    ):
        malformed_record = tmp_path / f"{suffix}.json"
        malformed_output = tmp_path / f"{suffix}-checker.json"
        malformed_record.write_text(json.dumps(malformed), encoding="utf-8")
        malformed_checker = checker[:-1] + [str(malformed_output)]
        malformed_checker[malformed_checker.index(str(record_path))] = str(malformed_record)
        malformed_result = subprocess.run(malformed_checker, cwd=ROOT)
        assert malformed_result.returncode != 0
        malformed_checked = json.loads(malformed_output.read_text(encoding="utf-8"))
        assert malformed_checked["passed"] is False
        assert malformed_checked["classification"] == "F1_SELECTOR_CONTRACT_INVALID"


def test_f1_files_are_lazy_and_do_not_open_p6_stack() -> None:
    helper_path = ROOT / "src/solvers/fullspace_physical_wave_diagnostic.py"
    runner_path = ROOT / "benchmarks/run_task038_full3d_floquet_wave_small_oracle.py"
    checker_path = ROOT / "benchmarks/task038_full3d_floquet_wave_small_oracle_checker.py"
    helper_tree = ast.parse(helper_path.read_text(encoding="utf-8"))
    checker_tree = ast.parse(checker_path.read_text(encoding="utf-8"))
    for tree in (helper_tree, checker_tree):
        imported = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert not any(name.startswith(("dolfinx", "petsc4py", "mpi4py")) for name in imported)
    runner_tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            name.startswith(("dolfinx", "petsc4py", "mpi4py"))
            for name in (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
            )
        )
        for node in runner_tree.body
    )
    checker_text = checker_path.read_text(encoding="utf-8")
    runner_text = runner_path.read_text(encoding="utf-8")
    assert '"--abbrev-ref"' in runner_text
    assert '"@{upstream}"' in runner_text
    assert "run_task038" not in checker_text
    assert "src.solvers" not in checker_text
