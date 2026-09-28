"""One bounded, canonical cell-trace/all-port weighted Schwarz PC.

The input supports come from the existing FE cell/MPC trace map, never row
number intervals. Principal blocks borrow the original assembled Schur matrix.
There is no global LU, shift, fallback, private CSR or tunable overlap sweep.
"""

import time
import warnings

import numpy as np
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

from .coarse_inverse_protocol import FactorDeclaration


def cell_port_indices(cell_supports, trace_rows, ports):
    if trace_rows <= 0 or not 0 < ports <= 2048:
        raise ValueError("positive trace space and bounded complete ports required")
    result = []
    port_indices = np.arange(trace_rows, trace_rows + ports, dtype=np.int64)
    for support in cell_supports:
        trace = np.unique(np.asarray(support, dtype=np.int64))
        if not len(trace) or trace[0] < 0 or trace[-1] >= trace_rows:
            raise ValueError("invalid canonical FE cell trace support")
        indices = np.r_[trace, port_indices]
        indices.flags.writeable = False
        result.append(indices)
    return tuple(result)


def overlap_budget(rows, patches, cell_factor_bytes=0):
    """Validate the entire list and capacity BEFORE reading/factoring any block."""
    if rows <= 1 or not patches:
        raise ValueError("nonempty bounded patch inventory required")
    sizes = []
    multiplicity = np.zeros(rows, dtype=np.int64)
    for indices in patches:
        if indices.ndim != 1 or not 0 < len(indices) < rows or len(indices) > 6000:
            raise ValueError("patch must be bounded and smaller than global p4")
        if indices[0] < 0 or indices[-1] >= rows or np.any(np.diff(indices) <= 0):
            raise ValueError("patch rows must be sorted, unique and in range")
        multiplicity[indices] += 1
        sizes.append(len(indices))
    if np.any(multiplicity == 0):
        raise ValueError("patches must cover all trace and all port unknowns")
    if not np.any(multiplicity > 1):
        raise ValueError("geometric comparison requires actual overlap")
    factors = sum(n * n * 16 + n * 4 for n in sizes)
    indices_bytes = sum(a.nbytes for a in patches)
    # Multiplicity/weights, input/output plus spare vectors and local solves.
    representation = indices_bytes + rows * (8 + 8 + 6 * 16) + max(sizes) * 4 * 16
    # Reader + Fortran copy + conservative LAPACK scratch; only one local block.
    construction_temporary = 3 * max(sizes) ** 2 * 16 + max(sizes) * 8 * 16
    if factors + cell_factor_bytes > 512 * 2**20:
        raise ValueError("preconstruction all-factor capacity exceeds 512 MiB")
    if representation + construction_temporary > 512 * 2**20:
        raise ValueError("preconstruction representation/temp exceeds 512 MiB")
    return {
        "patch_count": len(patches),
        "max_patch_rows": max(sizes),
        "patch_factor_bytes": factors,
        "cell_port_factor_bytes": cell_factor_bytes,
        "all_factor_bytes": factors + cell_factor_bytes,
        "representation_bytes": representation,
        "one_block_construction_temporary_bytes": construction_temporary,
        "patch_sizes": sizes,
        "multiplicity_histogram": {
            str(k): int(np.count_nonzero(multiplicity == k))
            for k in np.unique(multiplicity)
        },
    }, multiplicity


class CellPortOverlapPC:
    def __init__(self, rows, patches, block_reader, *, cell_factor_bytes=0):
        self.budget, multiplicity = overlap_budget(rows, patches, cell_factor_bytes)
        self.rows, self.patches = rows, patches
        self.weights = 1.0 / multiplicity
        self.weights.flags.writeable = False
        self.factors = []
        self.seconds = 0.0
        started = time.perf_counter()
        for indices in patches:
            block = np.array(
                block_reader(indices), dtype=np.complex128, order="F", copy=True
            )
            if (
                block.shape != (len(indices), len(indices))
                or not np.isfinite(block).all()
            ):
                raise ValueError("invalid original principal subdomain block")
            with warnings.catch_warnings():
                warnings.simplefilter("error", LinAlgWarning)
                factor = lu_factor(block, overwrite_a=True, check_finite=False)
            self.factors.append((indices, factor))
        self.factor_bytes = sum(a.nbytes + p.nbytes for _, (a, p) in self.factors)
        if self.factor_bytes != self.budget["patch_factor_bytes"]:
            raise ValueError("local LU payload differs from preconstruction bound")
        self.representation_bytes = self.budget["representation_bytes"]
        self.setup_seconds = time.perf_counter() - started

    def apply_array(self, source):
        started = time.perf_counter()
        source = np.asarray(source)
        if (
            source.shape != (self.rows,)
            or source.dtype != np.complex128
            or not np.isfinite(source).all()
        ):
            raise ValueError("complete complex128 residual required")
        target = np.zeros_like(source)
        for indices, factor in self.factors:
            target[indices] += lu_solve(factor, source[indices], check_finite=False)
        target *= self.weights
        self.seconds += time.perf_counter() - started
        return target

    def apply(self, _pc, source, target):
        target.array[:] = self.apply_array(source.getArray(readonly=True))

    @property
    def declarations(self):
        return tuple(
            FactorDeclaration("patch", len(indices), a.nbytes + p.nbytes)
            for indices, (a, p) in self.factors
        )
