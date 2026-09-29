"""Research-only sparse positive Riesz factor, with symbolic admission first."""

import ctypes
import gc
import hashlib
import os
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
from scipy import sparse


def rss_bytes():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("RSS unavailable")


def library():
    source = Path(__file__).with_suffix(".py").with_name("feinn_cholmod.c")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = Path(os.environ["TASK42EXTRA_ROOT"]) / "tmp/task42extra/ml/cholmod"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (digest + ".so")
    if not path.exists():
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                "-O2",
                "-I/usr/include/suitesparse",
                str(source),
                "-lcholmod",
                "-o",
                str(path),
            ],
            check=True,
        )
    lib = ctypes.CDLL(str(path))
    ip = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
    dp = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
    lib.riesz_symbolic.argtypes = [ctypes.c_int64, ctypes.c_int64, ip, ip, dp]
    lib.riesz_symbolic.restype = ctypes.c_void_p
    lib.riesz_stats.argtypes = [ctypes.c_void_p, dp]
    lib.riesz_numeric.argtypes = [ctypes.c_void_p]
    lib.riesz_numeric.restype = ctypes.c_int
    lib.riesz_solve.argtypes = [ctypes.c_void_p, dp, dp]
    lib.riesz_solve.restype = ctypes.c_int
    lib.riesz_free.argtypes = [ctypes.c_void_p]
    return lib, dict(
        c_source_sha256=digest,
        library_path=str(path),
        library_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        backend="installed CHOLMOD int64 complex FP64 simplicial LLH/AMD",
    )


class SparseRiesz:
    label = "RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR"

    def __init__(self, matrix, design, marker=lambda *_: None):
        start = perf_counter()
        self.handle = None
        self.solves = 0
        self.solve_seconds = 0.0
        self.max_relative = 0.0
        self.G = sparse.csr_matrix(matrix, dtype=np.complex128)
        self.G.sort_indices()
        if self.G.shape[0] != self.G.shape[1] or not np.isfinite(self.G.data).all():
            raise ValueError("finite square sparse Gram required")
        defect = sparse.linalg.norm(self.G - self.G.conj().T) / sparse.linalg.norm(
            self.G
        )
        if defect > 1e-12:
            raise ValueError("RIESZ_NOT_HERMITIAN")
        self.lib, backend = library()
        upper = sparse.triu(self.G, format="csc")
        p, i = upper.indptr.astype(np.int64), upper.indices.astype(np.int64)
        x = np.ascontiguousarray(upper.data, dtype=np.complex128)
        self.record = dict(
            label=self.label,
            **backend,
            rows=self.G.shape[0],
            nnz=self.G.nnz,
            hermitian_relative=float(defect),
            csr_payload_bytes=sum(
                a.nbytes for a in (self.G.data, self.G.indices, self.G.indptr)
            ),
            rss_before_symbolic_bytes=rss_bytes(),
        )
        t = perf_counter()
        self.handle = self.lib.riesz_symbolic(
            self.G.shape[0], len(x), p, i, x.view(np.float64)
        )
        if not self.handle:
            raise RuntimeError("RIESZ_SYMBOLIC_FAILED")
        self.record["symbolic_seconds"] = perf_counter() - t
        symbolic = self.stats()
        # Exact symbolic fill; conservative workspace/allocator reserve, not a proven RSS bound.
        predicted = int(
            1.5 * symbolic["symbolic_l_nnz"] * 24 + 64 * self.G.shape[0] + 64 * 2**20
        )
        self.record.update(
            symbolic=symbolic,
            factor_workspace_budget_bytes=predicted,
            rss_after_symbolic_bytes=rss_bytes(),
            prediction_kind="symbolic fill plus conservative workspace reserve",
        )
        marker("riesz_symbolic", self.record)
        if (
            predicted > design["riesz"]["factor_payload_cap_bytes"]
            or rss_bytes() + predicted > design["riesz"]["planning_cap_bytes"]
        ):
            self.close()
            raise RuntimeError("RIESZ_RESOURCE_BLOCKED")
        t = perf_counter()
        if not self.lib.riesz_numeric(self.handle):
            self.record["failed_numeric_stats"] = self.stats()
            marker("riesz_numeric_failed", self.record)
            self.close()
            raise RuntimeError("RIESZ_NOT_POSITIVE_DEFINITE")
        self.record.update(
            numeric_seconds=perf_counter() - t,
            numeric=self.stats(),
            rss_after_numeric_bytes=rss_bytes(),
        )
        del upper, p, i, x
        self.setup_seconds = perf_counter() - start
        self.record["setup_seconds"] = self.setup_seconds
        marker("riesz_numeric", self.record)

    def stats(self):
        values = np.zeros(7, dtype=np.float64)
        self.lib.riesz_stats(self.handle, values)
        return dict(
            zip(
                (
                    "symbolic_l_nnz",
                    "symbolic_flops",
                    "cholmod_current_bytes",
                    "cholmod_peak_bytes",
                    "factor_allocated_nnz",
                    "positive_pivots",
                    "status",
                ),
                values.tolist(),
                strict=True,
            )
        )

    def solve(self, rhs):
        start = perf_counter()
        rhs = np.ascontiguousarray(rhs, dtype=np.complex128)
        if rhs.shape != (self.G.shape[0],) or not np.isfinite(rhs).all():
            raise ValueError("finite complex full Gram RHS required")
        q = np.empty_like(rhs)
        if not self.lib.riesz_solve(
            self.handle, rhs.view(np.float64), q.view(np.float64)
        ):
            raise RuntimeError("RIESZ_SOLVE_FAILED")
        norm = np.linalg.norm(rhs)
        relative = (
            float(np.linalg.norm(self.G @ q - rhs) / norm)
            if norm
            else float(np.linalg.norm(q))
        )
        self.solves += 1
        self.solve_seconds += perf_counter() - start
        self.max_relative = max(self.max_relative, relative)
        if relative > 1e-11 or not np.isfinite(q).all():
            raise RuntimeError(f"RIESZ_SOLVE_NOT_QUALIFIED: {relative}")
        return q

    def close(self):
        if self.handle:
            self.record["rss_before_release_bytes"] = rss_bytes()
            self.lib.riesz_free(self.handle)
            self.handle = None
            self.G = None
            gc.collect()
            self.record["rss_after_release_bytes"] = rss_bytes()
            self.record.update(
                solve_count=self.solves,
                solve_seconds=self.solve_seconds,
                max_solve_true_relative=self.max_relative,
            )
