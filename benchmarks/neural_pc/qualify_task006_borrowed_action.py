from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import scipy.sparse as sp
from mpi4py import MPI

from src.solvers.physical_slab_two_level import DistributedPhysicalSlabSmoother


TINY = np.finfo(float).tiny


def _csr_fingerprint(
    shape: tuple[int, int],
    indptr: np.ndarray,
    indices: np.ndarray,
    values: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    digest.update(np.asarray(shape, dtype=np.int64).tobytes())
    digest.update(np.asarray(indptr, dtype=np.int64).tobytes())
    digest.update(np.asarray(indices, dtype=np.int64).tobytes())
    digest.update(np.asarray(values, dtype=np.complex128).tobytes())
    return digest.hexdigest()


def _deterministic_probes(size: int, slab_id: int) -> tuple[np.ndarray, ...]:
    index = np.arange(size, dtype=np.float64)
    base = np.sin(0.013 * (index + 1.0) * (slab_id + 1.0)) + 1j * np.cos(
        0.017 * (index + 2.0)
    )
    scaled_phase = (
        1.0e-8 * np.exp(1j * (0.23 + 0.11 * slab_id)) * base
    )
    sparse = np.zeros(size, dtype=np.complex128)
    sparse[[0, size // 2, size - 1]] = (
        1.0 + 0.25j,
        -0.4 + 0.7j,
        0.2 - 0.9j,
    )
    high_frequency = ((-1.0) ** np.arange(size)) * (
        1.0 + 0.1j * np.sin(0.031 * (index + slab_id))
    )
    return (
        np.asarray(base, dtype=np.complex128),
        np.asarray(scaled_phase, dtype=np.complex128),
        sparse,
        np.asarray(high_frequency, dtype=np.complex128),
    )


def qualify_borrowed_action(
    smoother: DistributedPhysicalSlabSmoother,
    *,
    reference_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Qualify borrowed action against one ephemeral CSR slab at a time."""

    comm = smoother.comm
    rank = int(comm.rank)
    auditor = smoother.create_borrowed_exact_auditor()
    expected_fingerprints = dict(smoother.factor_fingerprints)
    rows: list[dict[str, Any]] = []
    maximum_ephemeral_reference_bytes = 0
    started = time.perf_counter()

    for slab_id, owner in enumerate(smoother.subdomain_owners):
        reference_matrix: sp.csr_matrix | None = None
        probes: tuple[np.ndarray, ...] = ()
        fingerprint = ""
        ephemeral_bytes = 0
        if rank == owner:
            path = reference_root / f"slab_{slab_id:03d}" / "operator.npz"
            with np.load(path) as payload:
                indptr = np.asarray(payload["indptr"], dtype=np.int64)
                indices = np.asarray(payload["indices"], dtype=np.int64)
                values = np.asarray(payload["values"], dtype=np.complex128)
                shape = tuple(int(value) for value in payload["shape"])
                fingerprint = _csr_fingerprint(
                    shape, indptr, indices, values
                )
                reference_matrix = sp.csr_matrix(
                    (values, indices, indptr), shape=shape, copy=False
                )
                probes = _deterministic_probes(shape[1], slab_id)
                ephemeral_bytes = int(
                    indptr.nbytes + indices.nbytes + values.nbytes
                )
        identity = comm.bcast(
            (fingerprint, ephemeral_bytes) if rank == owner else None,
            root=owner,
        )
        fingerprint, ephemeral_bytes = identity
        if fingerprint != expected_fingerprints[slab_id]:
            raise RuntimeError(
                f"slab {slab_id} reference fingerprint does not match live operator"
            )
        maximum_ephemeral_reference_bytes = max(
            maximum_ephemeral_reference_bytes, ephemeral_bytes
        )

        for probe_id in range(4):
            correction = probes[probe_id] if rank == owner else None
            if rank == owner:
                assert reference_matrix is not None
                reference_action = np.asarray(
                    reference_matrix @ correction, dtype=np.complex128
                )
                perturbation = np.zeros(reference_action.size, dtype=np.complex128)
                if probe_id:
                    perturbation[(37 * probe_id + slab_id) % reference_action.size] = (
                        1.0e-5
                        * max(float(np.linalg.norm(reference_action)), TINY)
                        * np.exp(1j * 0.19 * probe_id)
                    )
                rhs = reference_action + perturbation
                reference_residual_norm = float(
                    np.linalg.norm(rhs - reference_action)
                )
                rhs_norm = float(np.linalg.norm(rhs))
                reference_rho = reference_residual_norm / max(rhs_norm, TINY)
            else:
                reference_action = None
                rhs = None
                reference_rho = 0.0

            result = auditor.audit(
                slab_id,
                rhs=rhs,
                correction=correction,
            )
            if rank == owner:
                assert result.local_action is not None
                action_relative_error = float(
                    np.linalg.norm(result.local_action - reference_action)
                    / max(float(np.linalg.norm(reference_action)), TINY)
                )
                rho_absolute_error = abs(result.rho - reference_rho)
                local_row = {
                    **result.summary(),
                    "probe_id": probe_id,
                    "action_relative_error": action_relative_error,
                    "reference_rho": reference_rho,
                    "rho_absolute_error": rho_absolute_error,
                }
            else:
                local_row = None
            rows.append(comm.bcast(local_row, root=owner))

        if rank == owner:
            del reference_action
            del rhs
            del correction
            del reference_matrix
            del probes
            del indptr
            del indices
            del values

    diagnostics = auditor.diagnostics
    diagnostics_by_rank = comm.allgather(diagnostics)
    maximum_ephemeral_reference_bytes = int(
        comm.allreduce(maximum_ephemeral_reference_bytes, op=MPI.MAX)
    )
    action_max = max(float(row["action_relative_error"]) for row in rows)
    rho_max = max(float(row["rho_absolute_error"]) for row in rows)
    result = {
        "schema": "myfenics.task006.borrowed_action_qualification.v1",
        "slabs": len(smoother.subdomain_owners),
        "probes_per_slab": 4,
        "row_count": len(rows),
        "action_relative_error_max": action_max,
        "rho_absolute_error_max": rho_max,
        "equivalence_tolerance": 1.0e-12,
        "equivalence_pass": action_max <= 1.0e-12 and rho_max <= 1.0e-12,
        "private_persistent_local_csr_bytes": diagnostics[
            "private_persistent_local_csr_bytes"
        ],
        "maximum_ephemeral_reference_csr_bytes": (
            maximum_ephemeral_reference_bytes
        ),
        "auditor_diagnostics_by_rank": diagnostics_by_rank,
        "elapsed_s": time.perf_counter() - started,
        "rows": rows,
    }
    if not result["equivalence_pass"]:
        raise RuntimeError("borrowed exact action failed the 1e-12 equivalence Gate")
    if result["private_persistent_local_csr_bytes"] != 0:
        raise RuntimeError("borrowed exact auditor retained private CSR storage")
    if rank == 0:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result
