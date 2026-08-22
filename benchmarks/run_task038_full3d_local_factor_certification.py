"""FC0 all-exact-class local-factor certification worker.

The worker builds only the frozen p6/h10 mesh, space, MPC, and cell-class
inventory.  It processes one representative B0 matrix at a time, writes only
ignored matrix/RHS evidence, and releases each dense matrix before the next
class.  The existing N2 watchdog is reused; no modes, coarse vectors,
physical action, RHS, residual, or PDE solve is constructed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterator, Mapping

import numpy as np

from src.solvers.fullspace_local_factor_certification import (
    CERTIFICATION_SCHEMA,
    MAX_CLASSES,
    TOTAL_FACTOR_BYTES_LIMIT,
    certify_dense_factor,
    fixed_rhs,
    summarize_certificates,
)


FC0_SCHEMA = "task038.full3d.local-factor-certification-v2.worker.v1"
FC0_CASES = {"p6-h10-mpi1": 1}
FC0_DEGREE = 6
FC0_MESH_TARGET_NM = 10.0
FC0_MARKERS = (
    "preflight",
    "mesh_space_mpc",
    "subdomain_inventory",
    "local_factor_build",
    "cleanup",
    "failure",
)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _class_order_sha256(values: tuple[str, ...]) -> str:
    payload = json.dumps(list(values), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    return value


def _write_array(path: Path, value: np.ndarray) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"FC0 artifact already exists: {path}")
    array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    np.save(path, array, allow_pickle=False)
    return {
        "path": str(path.resolve()),
        "sha256": _sha256_path(path),
        "bytes": int(path.stat().st_size),
        "shape": list(array.shape),
        "dtype": "complex128",
    }


def _class_identity(metadata: Mapping[str, Any]) -> dict[str, Any]:
    descriptors = tuple(metadata["canonical_free_row_descriptors"])
    descriptor_sha = hashlib.sha256(repr(descriptors).encode("utf-8")).hexdigest()
    return {
        "cell_key": _jsonable(metadata["cell_key"]),
        "tag": int(metadata["tag"]),
        "widths": [float(value) for value in metadata["widths"]],
        "row_count": len(metadata["free_rows"]),
        "canonical_free_row_descriptor_sha256": descriptor_sha,
    }


def _build_mesh_space_mpc(root: Path, args: argparse.Namespace, comm: Any) -> dict[str, Any]:
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space

    _specification, cfg, resolved = _resolve_case(
        root, args.input, FC0_DEGREE, FC0_MESH_TARGET_NM
    )
    mesh_data = build_airbox_mesh_3d(cfg, args.raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    return {
        "cfg": cfg,
        "resolved": resolved,
        "mesh_data": mesh_data,
        "raw_space": raw_space,
        "floquet_data": floquet_data,
        "space": floquet_data.mpc.function_space,
        "comm": comm,
    }


def _prepare_class_context(case: Mapping[str, Any]) -> dict[str, Any]:
    from src.solvers.fullspace_local_spectral_dolfinx import _prepare_real_context

    return _prepare_real_context(
        case["space"], case["mesh_data"], case["floquet_data"], case["cfg"]
    )


def _representative_matrices(
    context: Mapping[str, Any],
) -> Iterator[tuple[str, Mapping[str, Any], np.ndarray]]:
    from src.solvers.fullspace_local_spectral_dolfinx import (
        _cell_operators,
        _class_relative_template_order,
    )
    for digest in context["class_digests"]:
        metadata = next(
            item for item in context["cell_metadata"] if item["digest"] == digest
        )
        block, _unused, _mass = _cell_operators(metadata, context, with_mass=False)
        _template_keys, order = _class_relative_template_order(metadata)
        order_array = np.asarray(order, dtype=np.int64)
        matrix = np.ascontiguousarray(block[np.ix_(order_array, order_array)])
        del block, _unused, _mass
        yield str(digest), metadata, matrix
        del matrix, metadata, _template_keys, order_array


def _record_failure(args: argparse.Namespace, runtime: Mapping[str, Any], exc: BaseException, comm: Any) -> None:
    if comm.rank != 0 or args.record.exists():
        return
    payload = {
        "schema": FC0_SCHEMA,
        "classification": "controlled_negative",
        "stage": "fc0_all_class_certification",
        "case": args.case,
        "source_identity": _jsonable(runtime.get("source_identity", {
            "expected_sha": args.expected_sha,
            "source_git_sha": None,
            "tracked_status": "not_measured",
        })),
        "raw_dir": str(args.raw_dir.resolve()),
        "marker_dir": str(args.marker_dir.resolve()),
        "failure": {"exception_type": type(exc).__name__, "message": str(exc)},
        "not_run": ["remaining exact classes", "independent checker"],
    }
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _run_worker(args: argparse.Namespace) -> int:
    from mpi4py import MPI
    from benchmarks import run_task038_full3d_n2 as n2
    from src.solvers.fullspace_local_spectral import _PackedCholesky

    comm = MPI.COMM_WORLD
    root = Path.cwd().resolve()
    args.raw_dir = args.raw_dir.resolve()
    args.record = args.record.resolve()
    args.marker_dir = args.marker_dir.resolve()
    n2._prepare_paths(args.raw_dir, args.record, args.marker_dir, comm)
    runtime: dict[str, Any] = {}
    case = None
    context = None
    try:
        n2._write_marker(args.marker_dir, "preflight", args.expected_sha, comm, stage="fc0")
        runtime = n2._runtime_preflight(root, args.expected_sha, args.expected_mpi_size, comm.size)
        n2._write_marker(args.marker_dir, "mesh_space_mpc", args.expected_sha, comm, profile="full3d_scalable_v1")
        case = _build_mesh_space_mpc(root, args, comm)
        n2._write_marker(args.marker_dir, "subdomain_inventory", args.expected_sha, comm, api="_prepare_real_context", source_independent=True)
        context = _prepare_class_context(case)
        class_order = tuple(str(value) for value in context["class_digests"])
        if len(class_order) > MAX_CLASSES:
            raise RuntimeError(f"exact class count {len(class_order)} exceeds limit {MAX_CLASSES}")
        n2._write_marker(args.marker_dir, "local_factor_build", args.expected_sha, comm, class_count=len(class_order), sequential_dense_class=True)
        class_records: list[dict[str, Any]] = []
        representative_stream = _representative_matrices(context)
        for slot, (digest, metadata, matrix) in enumerate(representative_stream):
            rhs = fixed_rhs(matrix.shape[0])
            matrix_path = args.raw_dir / f"class_{slot:03d}_{digest[:16]}_B.npy"
            rhs_path = args.raw_dir / f"class_{slot:03d}_{digest[:16]}_rhs.npy"
            matrix_descriptor = _write_array(matrix_path, matrix)
            rhs_descriptor = _write_array(rhs_path, rhs)
            factor = _PackedCholesky(matrix)
            lower = factor.lower()
            metrics = certify_dense_factor(
                matrix,
                factor.solve,
                packed=factor.packed,
                lower=lower,
                rhs=rhs,
            )
            class_records.append({
                "digest": digest,
                "slot": int(slot),
                "representative_rank": int(comm.rank),
                "representative_cell": _class_identity(metadata),
                "matrix": matrix_descriptor,
                "rhs": rhs_descriptor,
                "metrics": _jsonable(metrics),
                "factor_owner_rank": 0,
            })
            del factor, lower, matrix, rhs, metrics
        del representative_stream
        summary = summarize_certificates(
            [record["metrics"] for record in class_records]
        )
        metadata_order = tuple(
            sorted({str(item["digest"]) for item in context["cell_metadata"]})
        )
        class_order_repeat_sha256 = _class_order_sha256(metadata_order)
        summary.update({
            "class_count": len(class_order),
            "class_order": list(class_order),
            "class_order_sha256": _class_order_sha256(class_order),
            "class_order_repeat": list(metadata_order),
            "class_order_repeat_sha256": class_order_repeat_sha256,
            "class_order_repeat_exact": class_order == metadata_order,
            "class_count_within_limit": len(class_order) <= MAX_CLASSES,
            "class_order_sorted_unique": class_order == tuple(sorted(set(class_order))),
            "all_classes_processed": len(class_records) == len(class_order),
            "duplicate_class_count": len(class_order) - len(set(class_order)),
            "missing_class_count": len(set(class_order) - set(metadata_order)),
            "global_factor_count": len(class_records),
            "factor_owner_closure": {
                "owner_rule": "sha256(exact_class_digest) mod mpi_size",
                "mpi_size": int(comm.size),
                "owner_rank_set": [0],
                "unique_factor_count": len(class_records),
                "duplicate_factor_count": 0,
            },
        })
        summary["overall_gate_pass"] = bool(
            summary["class_count_within_limit"]
            and summary["class_order_sorted_unique"]
            and summary["all_classes_processed"]
            and summary["all_class_certificates_pass"]
            and summary["all_class_factor_bytes_within_global_limit"]
        )
        resolved_config_sha256 = hashlib.sha256(case["resolved"]).hexdigest()
        resolved_config_bytes = len(case["resolved"])
        del context, case
        n2._write_marker(args.marker_dir, "cleanup", args.expected_sha, comm, dense_workspace_released=True)
        record = {
            "schema": FC0_SCHEMA,
            "certification_schema": CERTIFICATION_SCHEMA,
            "classification": "worker_facts_pending_independent_checker",
            "stage": "fc0_all_class_certification",
            "case": args.case,
            "degree": FC0_DEGREE,
            "mesh_target_nm": FC0_MESH_TARGET_NM,
            "mpi_size": int(comm.size),
            "profile": "full3d_scalable_v1",
            "source_identity": _jsonable(runtime["source_identity"]),
            "runtime": _jsonable(runtime),
            "input": {
                "path": str(args.input.resolve()),
                "file_sha256": _sha256_path(args.input.resolve()),
                "resolved_config_sha256": resolved_config_sha256,
                "resolved_config_bytes": resolved_config_bytes,
            },
            "fixed_rhs": "arange(rows)+(0.125+0.25j), complex128",
            "threshold_contract": {
                "eps64": float(np.finfo(np.float64).eps),
                "ordinary_relative_residual": 1.0e-10,
                "kappa2": 1.0e8,
                "factor_bytes": 6_230_448,
                "total_factor_bytes": TOTAL_FACTOR_BYTES_LIMIT,
            },
            "class_order": list(class_order),
            "class_order_sha256": _class_order_sha256(class_order),
            "class_order_repeat": list(metadata_order),
            "class_order_repeat_sha256": class_order_repeat_sha256,
            "class_order_repeat_exact": class_order == metadata_order,
            "classes": class_records,
            "summary": summary,
            "lifecycle": {
                "dense_class_max_live": 1,
                "dense_workspace_released": True,
                "modes_built": False,
                "regional_built": False,
                "top_built": False,
                "physical_action_built": False,
                "rho_run": False,
                "forbidden": {
                    "global_aij": False,
                    "global_schur": False,
                    "global_factor": False,
                    "numeric_allgather": False,
                },
            },
            "markers": {"directory": str(args.marker_dir), "ledger": n2._marker_ledger(args.marker_dir)},
            "resource_contract": {"status": "pending_external_watchdog"},
        }
        args.record.parent.mkdir(parents=True, exist_ok=True)
        if args.record.exists():
            raise FileExistsError(f"FC0 record already exists: {args.record}")
        args.record.write_text(json.dumps(_jsonable(record), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        if context is not None:
            del context
        if case is not None:
            del case
        try:
            n2._write_marker(args.marker_dir, "failure", args.expected_sha, comm, exception_type=type(exc).__name__, message=str(exc))
        finally:
            _record_failure(args, runtime, exc, comm)
        return 1


def _parse_worker(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FC0 all-class factor certification")
    parser.add_argument("--stage", choices=("fc0",), required=True)
    parser.add_argument("--case", choices=tuple(FC0_CASES), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--marker-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", dest="expected_sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    if args.expected_mpi_size != FC0_CASES[args.case]:
        parser.error("expected MPI size does not match frozen FC0 case")
    return args


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    if "--watchdog" in selected:
        from benchmarks import run_task038_full3d_n2 as n2

        return n2._watchdog_main([item for item in selected if item != "--watchdog"])
    return _run_worker(_parse_worker(selected))


if __name__ == "__main__":
    raise SystemExit(main())
