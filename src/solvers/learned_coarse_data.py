"""Task042 streamed original-equation teacher packets and oracle helpers."""

import hashlib
import time
from pathlib import Path

import numpy as np


class BorrowedMatrixAction:
    def __init__(self, matrix):
        self.matrix = matrix
        self.source = matrix.createVecRight()
        self.target = matrix.createVecLeft()
        self.calls = 0
        self.seconds = 0.0

    def __call__(self, values):
        started = time.perf_counter()
        self.source.array[:] = values
        self.matrix.mult(self.source, self.target)
        result = self.target.array.copy()
        self.calls += 1
        self.seconds += time.perf_counter() - started
        return result

    def destroy(self):
        self.source.destroy()
        self.target.destroy()


def reference_array_solve(matrix, action, rhs, factor):
    b = matrix.createVecRight()
    x, residual, correction = (b.duplicate() for _ in range(3))
    try:
        b.array[:] = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
        x.set(0.0)
        factor.solve_repeated(b, x)
        norm = max(float(np.linalg.norm(b.array)), np.finfo(float).tiny)
        refinements = 0
        for _ in range(3):
            matrix.mult(x, residual)
            residual.array[:] = b.array - residual.array
            if np.linalg.norm(residual.array) / norm <= 1.0e-13:
                break
            factor.solve_repeated(residual, correction)
            x.axpy(1.0, correction)
            refinements += 1
        return x.array.copy(), refinements
    finally:
        for vector in (b, x, residual, correction):
            vector.destroy()


def mapped_original_residual(action, reduced_residual):
    """Original native FE residual from Schur residual plus original Hp.

    The F1 independently native-vs-augmented identity qualifies this map.
    It is rechecked independently with native A4 at F2. No CSR duplicate.
    """
    return action.inject_trace_port(reduced_residual) - action.apply_B_full(
        action.original_hp_solve(reduced_residual[action.condensed.active_rows :])
    )


def save_teacher_batches(matrix, action, native, factor, packets, count, directory):
    """All inputs carry split/whole-problem identities; audit every pair."""
    from src.runners.task042_shared import write_json

    directory = Path(directory)
    directory.mkdir()
    records, files, batch = [], [], []
    for index, (label, rhs) in enumerate(packets):
        started = time.perf_counter()
        solution, refinements = reference_array_solve(matrix, action, rhs, factor)
        audit = action.evaluate_native_residual(
            solution, rhs.fe, native, port_rhs=rhs.port
        )
        metrics = {
            name: audit[name]
            for name in (
                "native_residual_relative",
                "port_residual_relative",
                "internal_residual_relative",
                "native_identity_relative",
                "schur_port_identity_relative",
            )
        }
        passed = all(v <= 1.0e-10 and np.isfinite(v) for v in metrics.values())
        records.append(
            {
                "index": index,
                "label": label,
                "refinements": refinements,
                "seconds": time.perf_counter() - started,
                "passed": passed,
                "metrics": metrics,
            }
        )
        write_json(directory / "teacher_residuals.json", records)
        if not passed:
            np.savez(
                directory / f"rejected_{index:04d}.npz",
                rhs_fe=rhs.fe,
                rhs_port=rhs.port,
                solution=solution,
            )
            raise ValueError(
                "TEACHER_REFERENCE_NOT_QUALIFIED: original A4/port/recovery"
            )
        raw = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
        scale = (
            max(float(np.linalg.norm(raw)), np.finfo(float).tiny)
            if np.any(raw)
            else 1.0
        )
        batch.append(
            {
                "raw": raw / scale,
                "solution": solution / scale,
                "rhs_fe": rhs.fe / scale,
                "rhs_port": rhs.port / scale,
                "native_rhs_scale": audit["native_rhs_operation_scale"] / scale,
                "normalization_scale": scale,
            }
        )
        if len(batch) == 32 or index + 1 == count:
            path = directory / f"batch_{len(files):03d}.npz"
            np.savez(
                path, **{key: np.stack([row[key] for row in batch]) for key in batch[0]}
            )
            files.append(
                {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "rows": len(batch),
                }
            )
            batch.clear()
    return records, files


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def offline_reference_factor(matrix, directory, marker):
    """Offline teacher only; bound symbolic prediction before numeric LU."""
    import os

    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.runners.task042_shared import write_json
    from src.solvers.fullspace_p4_reference import reference_budget
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

    started = time.perf_counter()
    factor = _MumpsFactor(matrix)
    try:
        factor.set_icntl(22, 0)
        factor.set_icntl(23, 8192)
        factor.symbolic(matrix)
        raw = factor.info((1, 7, 16, 22, 29))
        sample = process_tree_snapshot(
            int(os.environ["TASK042_WATCHDOG_PARENT_PID"]),
            "teacher_symbolic",
            include_pss=False,
        )
        sample.update(launch_cap_bytes=16 * 2**30, planning_cap_bytes=16 * 2**30)
        budget = reference_budget(sample, raw, 2**30, marker=marker)
        write_json(directory / "reference_symbolic_budget.json", budget)
        factor.numeric(matrix)
        facts = {
            "setup_seconds": time.perf_counter() - started,
            "offline_only": True,
            "global_p4_factor_created": True,
            "factor_info": factor.info((1, 7, 16, 22, 29)),
            "icntl22": factor.get_icntl(22),
            "icntl23": factor.get_icntl(23),
        }
        if facts["icntl22"] != 0 or facts["icntl23"] != 8192:
            raise RuntimeError("Offline factor OOC/workspace readback differs")
        write_json(directory / "reference_factor.json", facts)
        marker("offline_teacher_factor_created", facts)
        return factor
    except BaseException:
        factor.destroy()
        raise
