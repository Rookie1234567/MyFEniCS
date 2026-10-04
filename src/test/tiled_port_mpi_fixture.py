"""MPI2/4 synthetic shared rows, empty owner and collective preallocation stop."""

import os
import sys
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.runners.task042_shared import write_json
from src.test.test_boundary_witness import TileSource, action
from src.test.test_task042_v36_ports import Source, explicit


def main():
    comm = MPI.COMM_WORLD
    if (
        comm.size not in (2, 4)
        or PETSc.ScalarType != np.complex128
        or len(os.sched_getaffinity(0)) != 1
    ):
        raise RuntimeError("qualified MPI/affinity")
    n = 9
    div = np.linspace(0, n, comm.size, dtype=int)
    owner = (
        (int(div[comm.rank]), int(div[comm.rank + 1]))
        if comm.rank < comm.size - 1
        else (n, n)
    )
    source = TileSource(owner)

    def reduce(x):
        out = np.empty_like(x)
        comm.Allreduce(x, out, op=MPI.SUM)
        return out

    a = action(
        source,
        reduce_sum=reduce,
        collective_all=lambda x: comm.allreduce(x, op=MPI.LAND),
    )
    A, C, D = explicit(Source())
    rng = np.random.default_rng(423701)
    x = rng.normal(size=n) + 1j * rng.normal(size=n)
    y = rng.normal(size=n) + 1j * rng.normal(size=n)
    lo, hi = owner
    f = a.apply(x[lo:hi])
    h = a.apply(y[lo:hi], adjoint=True)
    ports = a.recover(x[lo:hi])
    modal = a.modal_rhs(np.ones(5, complex))
    for got, want in [
        (f, (A @ x)[lo:hi]),
        (h, (A.conj().T @ y)[lo:hi]),
        (ports, D @ x),
        (modal, (C @ np.ones(5))[lo:hi]),
    ]:
        np.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-12)
    a.tile_bytes = 4 if comm.rank == 0 else 2**20
    try:
        a.apply(x[lo:hi])
    except MemoryError:
        pass
    else:
        raise AssertionError("collective rejection missing")
    # A local failure must propagate before a peer enters the next reduction.
    bad = TileSource(owner)
    if comm.rank == 0:
        bad.rows[0]["projection_denominator"] = -1
    try:
        action(
            bad,
            reduce_sum=reduce,
            collective_all=lambda x: comm.allreduce(x, op=MPI.LAND),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("single-rank bad H did not propagate")
    bad = TileSource(owner)
    if comm.rank == 0:
        bad.expected_hash = lambda *_: "bad"
    broken = action(
        bad, reduce_sum=reduce, collective_all=lambda x: comm.allreduce(x, op=MPI.LAND)
    )
    try:
        broken.apply(x[lo:hi])
    except ValueError:
        pass
    else:
        raise AssertionError("single-rank bad hash did not propagate")
    rows = comm.gather(
        {
            "owner": owner,
            "forward": f,
            "adjoint": h,
            "port": ports,
            "stats": a.stats,
            "affinity": sorted(os.sched_getaffinity(0)),
        },
        root=0,
    )
    if comm.rank == 0:
        np.testing.assert_allclose(
            np.concatenate([r["forward"] for r in rows]), A @ x, rtol=1e-12, atol=1e-12
        )
        write_json(
            Path(sys.argv[1]),
            {
                "status": "PASSED",
                "size": comm.size,
                "records": rows,
                "real_FE_MPI_qualification": False,
            },
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
