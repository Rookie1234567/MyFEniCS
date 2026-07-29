"""Actual analytic/algebraic double-Floquet probes for Task002 M2B."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.cross_section_floquet import (
    build_cross_section_floquet_constraints,
    build_distributed_constraint_transform,
    reduce_matrix_hermitian,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)


def _vec_global(vec: PETSc.Vec, comm) -> np.ndarray:
    start, stop = map(int, vec.getOwnershipRange())
    chunks = comm.allgather((start, stop, np.asarray(vec.getArray(readonly=True)).copy()))
    result = np.empty(vec.getSize(), dtype=np.complex128)
    for first, last, values in chunks:
        result[first:last] = values
    return result


def run_probe(degree: int, grazing: float, azimuth: float) -> dict:
    comm = MPI.COMM_WORLD
    cfg = target_stage4_config(degree=degree, h_nm=10.0)
    cfg.incident_theta_deg = 90.0 - grazing
    cfg.incident_phi_deg = azimuth
    cross_section = build_matching_cross_section(cfg, "air", comm=comm)
    spaces = build_cross_section_spaces(
        cross_section, transverse_degree=degree, longitudinal_degree=degree,
    )
    constraints = build_cross_section_floquet_constraints(
        cross_section, spaces, kx=complex(cfg.kx), ky=complex(cfg.ky),
    )
    transform = build_distributed_constraint_transform(spaces, constraints)
    q = PETSc.Vec().createMPI(
        (transform.reduced_local_size, transform.reduced_global_size), comm=comm,
    )
    start, stop = map(int, q.getOwnershipRange())
    indices = np.arange(start, stop, dtype=np.float64)
    q.getArray()[:] = np.sin(0.173 * (indices + 1.0)) + 1j * np.cos(0.117 * (indices + 2.0))
    q.assemble()
    full = transform.matrix.createVecLeft()
    transform.matrix.mult(q, full)
    global_full = _vec_global(full, comm)
    local_row_error = 0.0
    local_row_scale = 0.0
    for row, slave in enumerate(constraints.slave_global):
        begin, end = int(constraints.offsets[row]), int(constraints.offsets[row + 1])
        expected = np.dot(
            constraints.coefficients[begin:end],
            global_full[constraints.master_global[begin:end]],
        )
        actual = global_full[int(slave)]
        local_row_error = max(local_row_error, abs(actual - expected))
        local_row_scale = max(local_row_scale, abs(actual), abs(expected))
    max_row_error = comm.allreduce(local_row_error, op=MPI.MAX)
    max_row_scale = comm.allreduce(local_row_scale, op=MPI.MAX)

    full_size = transform.full_global_size
    local_full = transform.full_local_size
    A = PETSc.Mat().createAIJ(
        size=((local_full, full_size), (local_full, full_size)), nnz=1, comm=comm,
    )
    row_start, row_stop = A.getOwnershipRange()
    for row in range(int(row_start), int(row_stop)):
        A.setValue(row, row, 1.0 + 0.001 * (row + 1))
    A.assemble()
    reduced = reduce_matrix_hermitian(A, transform.matrix)
    direct_action = A.createVecLeft()
    A.mult(full, direct_action)
    transform_h = PETSc.Mat()
    transform.matrix.hermitianTranspose(transform_h)
    explicit = transform_h.createVecLeft()
    transform_h.mult(direct_action, explicit)
    product = reduced.createVecLeft()
    reduced.mult(q, product)
    product.axpy(-1.0, explicit)
    action_error = float(product.norm() / max(float(explicit.norm()), 1.0e-30))
    digest = hashlib.sha256(global_full.tobytes()).hexdigest()
    result = {
        "schema_version": "task002.m2b-floquet-probe.v1",
        "degree": degree, "mpi_ranks": comm.size,
        "grazing_deg": grazing, "azimuth_deg": azimuth,
        "phase_x": {"real": constraints.phase_x.real, "imag": constraints.phase_x.imag},
        "phase_y": {"real": constraints.phase_y.real, "imag": constraints.phase_y.imag},
        "analytic_quasiperiodic_reconstruction_relative_residual": (
            constraints.max_probe_residual
        ),
        "random_free_vector_max_slave_row_relative_residual": float(
            max_row_error / max(max_row_scale, 1.0e-30)
        ),
        "explicit_chac_action_relative_error": action_error,
        "deterministic_full_vector_sha256": digest,
        "full_global_size": transform.full_global_size,
        "reduced_global_size": transform.reduced_global_size,
        "global_slave_count": transform.global_slave_count,
        "transverse_constraint_count": comm.allreduce(
            constraints.transverse_constraint_count, op=MPI.SUM,
        ),
        "longitudinal_constraint_count": comm.allreduce(
            constraints.longitudinal_constraint_count, op=MPI.SUM,
        ),
        "actual_probe_not_constant": constraints.max_probe_residual != 0.0,
        "gates": {
            "analytic_probe_le_5e-12": constraints.max_probe_residual <= 5.0e-12,
            "slave_rows_le_1e-13": max_row_error / max(max_row_scale, 1.0e-30) <= 1.0e-13,
            "explicit_chac_le_1e-13": action_error <= 1.0e-13,
        },
    }
    product.destroy(); explicit.destroy(); transform_h.destroy(); direct_action.destroy()
    reduced.destroy(); A.destroy(); full.destroy(); q.destroy(); transform.matrix.destroy()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, required=True)
    parser.add_argument("--grazing-deg", type=float, required=True)
    parser.add_argument("--azimuth-deg", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args.degree, args.grazing_deg, args.azimuth_deg)
    if MPI.COMM_WORLD.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
