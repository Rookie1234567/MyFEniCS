"""MPI2/4 ownership/empty-rank/byte-stop witness; no FE assembly or solve."""

import os
import sys
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.bounded_port_provider import BoundedPortAction, BoundedPortProvider
from src.test.test_task042_v36_ports import Source, explicit


def main():
    comm = MPI.COMM_WORLD
    if comm.size not in (2, 4) or PETSc.ScalarType != np.complex128:
        raise ValueError("qualified MPI2/4 complex fixture")
    if len(os.sched_getaffinity(0)) != 1:
        raise RuntimeError("MPI fixture escaped the single audited CPU")
    n = 9
    # Last rank deliberately empty. Other ranks partition canonical rows.
    divisions = np.linspace(0, n, comm.size, dtype=int)
    owner = (
        (int(divisions[comm.rank]), int(divisions[comm.rank + 1]))
        if comm.rank < comm.size - 1
        else (n, n)
    )
    source = Source(n=n, owner=owner)

    def reduce(x):
        y = np.empty_like(x)
        comm.Allreduce(x, y, op=MPI.SUM)
        return y

    p = BoundedPortProvider(
        source.keys,
        source.rows,
        source,
        source_identity=source.key,
        global_rows=n,
        ownership_range=owner,
        max_modes=2,
        cache_bytes=2**20,
        collective_batch_stop=lambda stop: comm.allreduce(stop, op=MPI.MIN),
    )
    action = BoundedPortAction(p, allreduce=reduce)
    rng = np.random.default_rng(423613)
    x = rng.normal(size=n) + 1j * rng.normal(size=n)
    y = rng.normal(size=n) + 1j * rng.normal(size=n)
    A, C, D = explicit(Source())
    a, b = owner
    forward = action.apply(x[a:b])
    adjoint = action.apply(y[a:b], adjoint=True)
    port = action.recover(x[a:b])
    modal = action.modal_rhs(np.ones(5, complex))
    for actual, expected in [
        (forward, (A @ x)[a:b]),
        (adjoint, (A.conj().T @ y)[a:b]),
        (port, D @ x),
        (modal, (C @ np.ones(5, complex))[a:b]),
    ]:
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    p.clear()
    # A single rank unable to fit a mode must collectively reject, not hang.
    p.cache_bytes = 4 if comm.rank == 0 else 2**20
    try:
        action.apply(x[a:b])
    except MemoryError:
        pass
    else:
        raise AssertionError("single oversized rank not rejected everywhere")
    record = {
        "rank": comm.rank,
        "ownership": list(owner),
        "empty": a == b,
        "affinity": sorted(os.sched_getaffinity(0)),
        "stats": p.stats,
        "scalar": str(np.dtype(PETSc.ScalarType)),
        "local_forward": forward.tolist(),
        "local_adjoint": adjoint.tolist(),
        "port_amplitudes": port.tolist(),
        "local_modal_rhs": modal.tolist(),
    }
    rows = comm.gather(record, root=0)
    if comm.rank == 0:
        from src.runners.task042_shared import write_json

        full_forward = np.concatenate(
            [np.asarray(r["local_forward"], complex) for r in rows]
        )
        full_adjoint = np.concatenate(
            [np.asarray(r["local_adjoint"], complex) for r in rows]
        )
        np.testing.assert_allclose(full_forward, A @ x, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(full_adjoint, A.conj().T @ y, rtol=1e-12, atol=1e-12)
        write_json(
            Path(sys.argv[1]),
            {
                "status": "PASSED",
                "size": comm.size,
                "records": rows,
                "full_forward": full_forward,
                "full_adjoint": full_adjoint,
                "serial_forward": A @ x,
                "serial_adjoint": A.conj().T @ y,
                "complete_vector_serial_match": True,
            },
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
