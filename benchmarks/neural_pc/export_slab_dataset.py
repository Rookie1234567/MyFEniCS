from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from benchmarks.neural_pc.data_contract import load_operator, save_dataset
from src.solvers.local_slab_solver import LocalCsrOperator


def _toy_operator(size: int) -> LocalCsrOperator:
    matrix = np.diag(3.0 + 0.05j * np.arange(size))
    matrix += np.diag((-0.7 + 0.1j) * np.ones(size - 1), 1)
    matrix += np.diag((-0.4 - 0.05j) * np.ones(size - 1), -1)
    rows, columns = np.nonzero(matrix)
    order = np.lexsort((columns, rows))
    rows, columns = rows[order], columns[order]
    indptr = np.zeros(size + 1, dtype=np.int64)
    np.add.at(indptr, rows + 1, 1)
    np.cumsum(indptr, out=indptr)
    return LocalCsrOperator(
        shape=(size, size),
        indptr=indptr,
        indices=columns.astype(np.int64),
        values=matrix[rows, columns],
        metadata={
            "slab_id": 0,
            "identity": "complex_sparse_toy",
            "source": "deterministic_smoke",
        },
    )


def export_dataset(args: argparse.Namespace) -> dict[str, object]:
    operator = load_operator(Path(args.operator_dir)) if args.operator_dir else _toy_operator(args.toy_size)
    if args.validation_real_krylov_dir:
        if not args.validation_operator_dir:
            raise ValueError(
                "--validation-operator-dir is required with independent real validation samples"
            )
        validation_operator = load_operator(Path(args.validation_operator_dir))
        if validation_operator.fingerprint != operator.fingerprint:
            raise ValueError(
                "validation operator fingerprint does not match the training operator"
            )
    use_sparse_teacher = operator.shape[0] * operator.shape[1] > args.maximum_teacher_entries
    if use_sparse_teacher:
        try:
            import scipy.sparse as sp
            import scipy.sparse.linalg as spla
        except ImportError as error:
            raise RuntimeError("production-size teacher export requires SciPy") from error
        matrix = sp.csr_matrix(
            (operator.values, operator.indices, operator.indptr), shape=operator.shape
        )
        factor = spla.splu(matrix.tocsc())
        teacher_solve = factor.solve
    else:
        matrix = operator.dense(maximum_entries=args.maximum_teacher_entries)

        def teacher_solve(value: np.ndarray) -> np.ndarray:
            return np.linalg.solve(matrix, value)
    rng = np.random.default_rng(args.seed)
    rhs_rows: list[np.ndarray] = []
    target_rows: list[np.ndarray] = []
    kinds: list[str] = []
    splits: list[str] = []
    for _ in range(args.synthetic_samples):
        error = rng.standard_normal(operator.shape[1]) + 1j * rng.standard_normal(operator.shape[1])
        # Mix smooth and oscillatory content rather than independent white noise alone.
        error = np.convolve(error, np.asarray([0.2, 0.6, 0.2]), mode="same")
        rhs_rows.append(np.asarray(matrix @ error, dtype=np.complex128))
        target_rows.append(error)
        kinds.append("synthetic_error")
        splits.append("train")
    for _ in range(args.teacher_samples):
        sample_rhs = rng.standard_normal(operator.shape[0]) + 1j * rng.standard_normal(operator.shape[0])
        rhs_rows.append(sample_rhs)
        target_rows.append(np.asarray(teacher_solve(sample_rhs), dtype=np.complex128))
        kinds.append("teacher_solve")
        splits.append("train")
    base_count = len(rhs_rows)
    validation_count = max(1, int(round(args.validation_fraction * base_count)))
    validation_indices = rng.choice(base_count, size=validation_count, replace=False)
    validation_rng = np.random.default_rng(args.seed + 1)
    for index in validation_indices:
        splits[index] = "validation"
        if kinds[index] == "synthetic_error":
            error = validation_rng.standard_normal(operator.shape[1]) + 1j * validation_rng.standard_normal(operator.shape[1])
            error = np.convolve(error, np.asarray([0.2, 0.6, 0.2]), mode="same")
            rhs_rows[index] = np.asarray(matrix @ error, dtype=np.complex128)
            target_rows[index] = error
        else:
            sample_rhs = validation_rng.standard_normal(operator.shape[0]) + 1j * validation_rng.standard_normal(operator.shape[0])
            rhs_rows[index] = sample_rhs
            target_rows[index] = np.asarray(teacher_solve(sample_rhs), dtype=np.complex128)
    real_sample_count = 0
    ilu_residual_count = 0

    def append_real_samples(directory: str | None, split: str) -> int:
        nonlocal real_sample_count, ilu_residual_count
        if not directory:
            return 0
        paths = sorted(Path(directory).glob("**/sample_*.npz"))
        if args.real_krylov_limit:
            paths = paths[: args.real_krylov_limit]
        for path in paths:
            with np.load(path, allow_pickle=False) as payload:
                sample_rhs = np.asarray(payload["rhs"], dtype=np.complex128)
                local_correction = np.asarray(
                    payload["local_correction"], dtype=np.complex128
                )
            exact = np.asarray(teacher_solve(sample_rhs), dtype=np.complex128)
            rhs_rows.append(sample_rhs)
            target_rows.append(exact)
            kinds.append("real_krylov_rhs")
            splits.append(split)
            real_sample_count += 1
            ilu_residual = sample_rhs - operator.action(local_correction)
            rhs_rows.append(ilu_residual)
            target_rows.append(exact - local_correction)
            kinds.append("ilu_residual")
            splits.append(split)
            ilu_residual_count += 1
        return len(paths)

    training_real_count = append_real_samples(args.real_krylov_dir, "train")
    validation_real_count = append_real_samples(
        args.validation_real_krylov_dir, "validation"
    )
    rhs = np.stack(rhs_rows)
    target = np.stack(target_rows)
    kinds_array = np.asarray(kinds, dtype="U32")
    split = np.asarray(splits, dtype="U16")
    sample_count = rhs.shape[0]
    permutation = rng.permutation(sample_count)
    rhs = rhs[permutation]
    target = target[permutation]
    kinds_array = kinds_array[permutation]
    split = split[permutation]
    validation_count = int(np.count_nonzero(split == "validation"))
    validation_separated = not training_real_count or bool(validation_real_count)
    save_dataset(
        Path(args.output),
        operator=operator,
        rhs=rhs,
        target=target,
        sample_kind=kinds_array,
        split=split,
        metadata={
            "generation_seed": args.seed,
            "validation_generation_seed": args.seed + 1,
            "validation_separated_by_seed_or_run": validation_separated,
            "contains_real_krylov_rhs": bool(real_sample_count),
            "contains_ilu_residual": bool(ilu_residual_count),
            "real_krylov_sample_count": real_sample_count,
            "ilu_residual_sample_count": ilu_residual_count,
            "training_real_krylov_sample_count": training_real_count,
            "validation_real_krylov_sample_count": validation_real_count,
            "teacher_backend": "scipy_splu" if use_sparse_teacher else "numpy_dense_solve",
            "qualification": "synthetic_smoke_only" if not args.operator_dir else "offline_local_operator",
        },
    )
    return {
        "operator_fingerprint": operator.fingerprint,
        "sample_count": sample_count,
        "validation_count": validation_count,
        "output": str(Path(args.output)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a portable local-slab training dataset")
    parser.add_argument("--operator-dir")
    parser.add_argument("--output", required=True)
    parser.add_argument("--real-krylov-dir")
    parser.add_argument("--validation-real-krylov-dir")
    parser.add_argument("--validation-operator-dir")
    parser.add_argument("--real-krylov-limit", type=int, default=0)
    parser.add_argument("--toy-size", type=int, default=24)
    parser.add_argument("--synthetic-samples", type=int, default=192)
    parser.add_argument("--teacher-samples", type=int, default=64)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--maximum-teacher-entries", type=int, default=4_000_000)
    args = parser.parse_args()
    if args.synthetic_samples < 1 or args.teacher_samples < 1:
        parser.error("both sample families require at least one sample")
    if not 0.0 < args.validation_fraction < 1.0:
        parser.error("validation fraction must lie in (0,1)")
    print(json.dumps(export_dataset(args), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
