"""Independent dense/off-diagonal check of the distributed ``C^H A C`` path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.cross_section_floquet import reduce_matrix_hermitian


def _petsc_dense(values: np.ndarray, comm) -> PETSc.Mat:
    rows, columns = values.shape
    matrix = PETSc.Mat().createDense(size=(rows, columns), comm=comm)
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValues(row, np.arange(columns, dtype=np.int32), values[row])
    matrix.assemble()
    return matrix


def _global_array(matrix: PETSc.Mat, comm) -> np.ndarray:
    first, last = map(int, matrix.getOwnershipRange())
    columns = np.arange(matrix.getSize()[1], dtype=np.int32)
    local = np.vstack([
        np.asarray(matrix.getValues([row], columns))[0]
        for row in range(first, last)
    ]) if last > first else np.empty((0, len(columns)), dtype=np.complex128)
    chunks = comm.allgather((first, last, local))
    result = np.empty(matrix.getSize(), dtype=np.complex128)
    for start, stop, values in chunks:
        result[start:stop] = values
    return result


def run_probe(source_sha: str) -> dict:
    comm = MPI.COMM_WORLD
    phase_x = np.exp(1j * 0.37)
    phase_y = np.exp(-1j * 0.23)
    # Rows 4 and 5 emulate two slave/corner constraints with complex phases.
    c_numpy = np.asarray([
        [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1],
        [phase_x, 0, 0.2j, 0], [0, phase_y, 0.15, phase_x * phase_y],
    ], dtype=np.complex128)
    indices = np.arange(36, dtype=np.float64).reshape(6, 6)
    a_numpy = (
        0.07 * np.sin(0.31 * (indices + 1.0))
        + 0.04j * np.cos(0.23 * (indices + 2.0))
    )
    a_numpy += np.diag(1.0 + 0.03 * np.arange(6))
    expected = c_numpy.conj().T @ a_numpy @ c_numpy
    a_petsc = _petsc_dense(a_numpy, comm)
    c_petsc = _petsc_dense(c_numpy, comm)
    reduced = reduce_matrix_hermitian(a_petsc, c_petsc)
    actual = _global_array(reduced, comm)
    absolute = float(np.max(np.abs(actual - expected)))
    relative = float(np.linalg.norm(actual - expected) / np.linalg.norm(expected))
    off_diagonal_fraction = float(
        np.linalg.norm(a_numpy - np.diag(np.diag(a_numpy))) / np.linalg.norm(a_numpy)
    )
    result = {
        "schema_version": "task002.m2c-dense-floquet-probe.v1",
        "source_sha": source_sha, "mpi_ranks": comm.size,
        "matrix_shape": [6, 6], "transform_shape": [6, 4],
        "off_diagonal_norm_fraction": off_diagonal_fraction,
        "max_abs_error": absolute, "relative_frobenius_error": relative,
        "independent_reference": "NumPy C.conj().T @ A @ C",
        "gates": {
            "genuinely_off_diagonal": off_diagonal_fraction > 0.05,
            "max_abs_le_1e-13": absolute <= 1.0e-13,
            "relative_le_1e-13": relative <= 1.0e-13,
        },
    }
    reduced.destroy(); c_petsc.destroy(); a_petsc.destroy()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args.source_sha)
    if MPI.COMM_WORLD.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
