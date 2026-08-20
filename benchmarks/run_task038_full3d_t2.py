"""Bounded Task038 T2 full-space matrix-free action runner and checker.

The runner is action-only: it builds the current 13.5 nm Full3D form and
double Floquet MPC, writes owner-layout vectors and physical canonical packets
only for the MPI peer case, and never creates a KSP or solves a PDE.  The
checker reads those artifacts and scalar audits; it does not rebuild or apply
an operator.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

from benchmarks.task038_full3d_t2_checker import (
    T2_CASES,
    T2_PROFILE,
    T2_REPEATS,
    T2_SCHEMA,
    check_t2_aggregate,
    check_t2_record,
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]

    def run_git(*arguments: str) -> str:
        result = subprocess.run(
            [
                "git",
                "--git-dir=.git-codex",
                "--work-tree=.",
                *arguments,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git identity probe failed")
        return result.stdout.strip()

    return {
        "commit_sha": run_git("rev-parse", "HEAD"),
        "tracked_status": run_git("status", "--short", "--untracked-files=all"),
    }


def _rss_bytes() -> int:
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError) as exc:
        raise RuntimeError("current VmRSS is unavailable") from exc
    raise RuntimeError("current VmRSS is unavailable")


def _swap_used_bytes() -> int:
    values: dict[str, int] = {}
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.partition(":")
                if key in {"SwapTotal", "SwapFree"}:
                    values[key] = int(value.split()[0]) * 1024
    except (OSError, ValueError):
        return -1
    if "SwapTotal" not in values or "SwapFree" not in values:
        return -1
    return max(values["SwapTotal"] - values["SwapFree"], 0)


def _case_config(case: str):
    if case not in T2_CASES:
        raise ValueError(f"unsupported T2 case {case!r}")
    from dataclasses import replace

    from src.common.config_3d import target_stage4_config

    spec = T2_CASES[case]
    cfg = target_stage4_config(
        degree=int(spec["degree"]),
        h_nm=float(spec["h_nm"]),
    )
    return replace(
        cfg,
        incident_phi_deg=23.0,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        matrix_diagnostics_assemble_unconstrained=False,
        unique_output=False,
        stage4_full3d_assembly_backend="standard_full",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _write_canonical_vector(
    vector: Any,
    raw_dir: Path,
    relative_path: str,
    *,
    function_space: Any,
    floquet_data: Any,
    canonical_role: str,
    write_canonical: bool = True,
) -> dict[str, Any]:
    """Write a raw vector and an owner-local physical canonical packet set."""

    import numpy as np
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from mpi4py import MPI
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_packets,
    )

    path = raw_dir / relative_path
    comm = vector.getComm().tompi4py()
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    start, stop = (int(value) for value in vector.getOwnershipRange())
    global_size = int(vector.getSize())
    local = np.ascontiguousarray(
        np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    )
    if local.size != stop - start:
        raise RuntimeError("PETSc ownership range does not match local vector storage")
    finite = bool(np.all(np.isfinite(local)))
    finite = bool(comm.allreduce(finite, op=MPI.LAND))
    handle = MPI.File.Open(
        comm,
        str(path),
        MPI.MODE_WRONLY | MPI.MODE_CREATE,
    )
    handle.Set_size(global_size * np.dtype(np.complex128).itemsize)
    handle.Write_at_all(start * np.dtype(np.complex128).itemsize, local)
    handle.Close()
    comm.barrier()
    ranges = comm.allgather([start, stop])
    descriptor = {
        "relative_path": relative_path,
        "bytes": int(path.stat().st_size) if comm.rank == 0 else None,
        "file_sha256": _sha256_path(path) if comm.rank == 0 else None,
        "array_sha256": _sha256_path(path) if comm.rank == 0 else None,
        "dtype": "complex128",
        "shape": [global_size],
        "finite": finite,
        "canonical_order": "global_petsc_row_order",
        "ownership_ranges": ranges,
    }
    if not write_canonical:
        return comm.bcast(descriptor, root=0)

    packets, extractor_audit = extract_canonical_full_fe_packets(
        function_space, vector, floquet_data
    )
    canonical_dir = raw_dir / "canonical"
    if comm.rank == 0:
        canonical_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = canonical_dir / f"{canonical_role}.rank{comm.rank:04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shards = comm.gather(shard, root=0)
    manifest_relative = f"canonical/{canonical_role}.manifest.json"
    if comm.rank == 0:
        manifest = canonical_shard_manifest(
            role=canonical_role,
            mpi_size=comm.size,
            shard_metadata=shards,
            extractor_audit=_jsonable(dict(extractor_audit)),
        )
        manifest_path = raw_dir / manifest_relative
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor.update(
            {
                "bytes": int(path.stat().st_size),
                "file_sha256": _sha256_path(path),
                "array_sha256": _sha256_path(path),
                "canonical_order": "physical_hcurl_packet_key",
                "canonical_manifest_relative_path": manifest_relative,
                "canonical_manifest_bytes": int(manifest_path.stat().st_size),
                "canonical_manifest_sha256": manifest_sha,
                "canonical_packet_count": int(manifest["global_summed_packet_count"]),
            }
        )
    else:
        descriptor = None
    return comm.bcast(descriptor, root=0)


def _relative_difference_to_file(vector: Any, path: Path, start: int, stop: int) -> float:
    import numpy as np
    from mpi4py import MPI

    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    global_size = path.stat().st_size // np.dtype(np.complex128).itemsize
    baseline_file = np.memmap(
        path,
        dtype=np.complex128,
        mode="r",
        shape=(global_size,),
    )
    try:
        if local.size != stop - start:
            raise ValueError("local ownership size does not match offset")
        delta = local - baseline_file[start:stop]
        local_difference_sq = float(np.vdot(delta, delta).real)
        local_reference_sq = float(
            np.vdot(baseline_file[start:stop], baseline_file[start:stop]).real
        )
        comm = vector.getComm().tompi4py()
        difference_sq = float(comm.allreduce(local_difference_sq, op=MPI.SUM))
        reference_sq = float(comm.allreduce(local_reference_sq, op=MPI.SUM))
        return math.sqrt(difference_sq) / max(math.sqrt(reference_sq), 1.0e-300)
    finally:
        del baseline_file


def _run_case(
    *,
    case: str,
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
) -> dict[str, Any]:
    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_mpc_action import (
        build_fullspace_mpc_form_action,
    )
    from src.solvers.mpc_form_action import MpcFormActionContext

    comm = MPI.COMM_WORLD
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("T2 requires complex128 PETSc")
    if comm.size != int(expected_mpi_size) or comm.size not in {1, 2}:
        raise RuntimeError(
            f"T2 requires the declared MPI size 1 or 2; got {comm.size}"
        )
    source_start = _source_identity()
    if (
        source_start["commit_sha"] != expected_source_sha
        or source_start["tracked_status"]
    ):
        raise RuntimeError("T2 source preflight is not clean at start")
    if raw_dir.exists() or record_path.exists():
        raise FileExistsError("T2 raw directory or record already exists")
    if comm.rank == 0:
        raw_dir.mkdir(parents=True)
    comm.barrier()

    cfg = _case_config(case)
    mesh_data = build_airbox_mesh_3d(cfg, raw_dir / "mesh")
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, mesh_data, cfg)
    bilinear_form, _rhs = _build_variational_forms(
        mesh_data.mesh,
        mesh_data,
        cfg,
        V,
        field_formulation="total_field",
    )

    source_field = None
    source_vector = None
    candidate = None
    reference_context = None
    reference_vector = None
    assembled = None
    expected_vector = None
    try:
        from src.solvers.common_3d_fields import plane_wave_electric_field

        source_field = plane_wave_electric_field(V, cfg)
        source_vector = source_field.x.petsc_vec.duplicate()
        source_field.x.petsc_vec.copy(source_vector)
        source_field = None
        gc.collect()

        spec = T2_CASES[case]
        reference_kind = str(spec["reference"])
        reference_descriptor = None
        reference_error = None
        reference_started = time.perf_counter()
        if reference_kind == "assembled":
            import dolfinx_mpc
            from dolfinx import fem

            assembled = dolfinx_mpc.assemble_matrix(
                fem.form(bilinear_form), floquet_data.mpc, bcs=[]
            )
            assembled.assemble()
            expected_vector = assembled.createVecLeft()
            assembled.mult(source_vector, expected_vector)
            reference_descriptor = _write_canonical_vector(
                expected_vector,
                raw_dir,
                "vectors/reference_action.bin",
                function_space=V,
                floquet_data=floquet_data,
                canonical_role="reference_action",
                write_canonical=False,
            )
        elif reference_kind == "independent":
            reference_context = MpcFormActionContext(
                bilinear_form, floquet_data.mpc
            )
            reference_vector = source_vector.duplicate()
            reference_context.mult(None, source_vector, reference_vector)
            reference_descriptor = _write_canonical_vector(
                reference_vector,
                raw_dir,
                "vectors/reference_action.bin",
                function_space=V,
                floquet_data=floquet_data,
                canonical_role="reference_action",
                write_canonical=False,
            )

        reference_seconds = float(
            comm.allreduce(time.perf_counter() - reference_started, op=MPI.MAX)
        )
        reference_rss_bytes = int(comm.allreduce(_rss_bytes(), op=MPI.MAX))
        if reference_context is not None:
            reference_context.destroy()
            reference_context = None
        if reference_vector is not None:
            reference_vector.destroy()
            reference_vector = None
        if expected_vector is not None:
            expected_vector.destroy()
            expected_vector = None
        if assembled is not None:
            assembled.destroy()
            assembled = None
        gc.collect()
        reference_closed_before_repeats = True

        candidate = build_fullspace_mpc_form_action(
            bilinear_form,
            V,
            mpc=floquet_data.mpc,
        )
        source_descriptor = _write_canonical_vector(
            source_vector,
            raw_dir,
            "vectors/source_before.bin",
            function_space=V,
            floquet_data=floquet_data,
            canonical_role="source_before",
            write_canonical=case == "p6-h10",
        )
        start, stop = (int(value) for value in source_vector.getOwnershipRange())
        elapsed_seconds: list[float] = []
        rss_bytes: list[int] = []
        swap_used_bytes: list[int] = []
        relative_differences: list[float] = []
        output_hashes: list[str] = []
        output_descriptor = None
        for repeat in range(T2_REPEATS):
            started = time.perf_counter()
            result = candidate.apply(source_vector)
            elapsed_seconds.append(
                float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
            )
            rss_bytes.append(int(comm.allreduce(_rss_bytes(), op=MPI.MAX)))
            swap_used_bytes.append(
                int(comm.allreduce(_swap_used_bytes(), op=MPI.MAX))
            )
            first = repeat == 0
            repeat_descriptor = _write_canonical_vector(
                result,
                raw_dir,
                "vectors/action.bin" if first else "vectors/repeat_tmp.bin",
                function_space=V,
                floquet_data=floquet_data,
                canonical_role="action" if first else "repeat_tmp",
                write_canonical=first and case == "p6-h10",
            )
            output_hashes.append(repeat_descriptor["file_sha256"])
            if first:
                output_descriptor = repeat_descriptor
                reference_path = (
                    raw_dir / reference_descriptor["relative_path"]
                    if reference_descriptor is not None
                    else None
                )
                if reference_path is not None:
                    reference_error = _relative_difference_to_file(
                        result, reference_path, start, stop
                    )
                relative_differences.append(0.0)
            else:
                relative_differences.append(
                    _relative_difference_to_file(
                        result,
                        raw_dir / output_descriptor["relative_path"],
                        start,
                        stop,
                    )
                )

        if comm.rank == 0:
            (raw_dir / "vectors/repeat_tmp.bin").unlink(missing_ok=True)
            (raw_dir / "canonical/repeat_tmp.manifest.json").unlink(missing_ok=True)
        (raw_dir / f"canonical/repeat_tmp.rank{comm.rank:04d}.jsonl").unlink(
            missing_ok=True
        )
        comm.barrier()

        source_after_descriptor = _write_canonical_vector(
            source_vector,
            raw_dir,
            "vectors/source_after.bin",
            function_space=V,
            floquet_data=floquet_data,
            canonical_role="source_after",
            write_canonical=case == "p6-h10",
        )
        candidate_audit = _jsonable(dict(candidate.audit))
        candidate_audit["retained_numeric_payload_components"] = _jsonable(
            dict(candidate_audit["retained_numeric_payload_components"])
        )
        candidate.destroy()
        candidate = None
        gc.collect()

        source_end = _source_identity()
        config_json = _jsonable(cfg.as_jsonable())
        config_sha = hashlib.sha256(_canonical_json(config_json)).hexdigest()
        model = {
            "config_sha256": config_sha,
            "config": config_json,
            "wavelength_nm": float(cfg.lambda0),
            "global_rows": int(candidate_audit["global_rows"])
            if "global_rows" in candidate_audit
            else int(source_vector.getSize()),
            "local_owned_rows": int(candidate_audit["local_owned_rows"])
            if "local_owned_rows" in candidate_audit
            else int(source_vector.getLocalSize()),
            "nedelec_degree": int(cfg.nedelec_degree),
            "floquet_constraint_mode": floquet_data.constraint_mode_resolved,
            "edge_constraints": int(floquet_data.num_edge_constraints),
            "face_constraints": int(floquet_data.num_face_constraints),
            "x_constraints": int(floquet_data.num_x_constraints),
            "y_constraints": int(floquet_data.num_y_constraints),
            "floquet_phases": {
                "x": _jsonable(cfg.floquet_phase_x),
                "y": _jsonable(cfg.floquet_phase_y),
                "x_nontrivial": bool(
                    abs(cfg.floquet_phase_x - 1.0) > 1.0e-8
                ),
                "y_nontrivial": bool(
                    abs(cfg.floquet_phase_y - 1.0) > 1.0e-8
                ),
            },
        }
        record = {
            "schema": T2_SCHEMA,
            "case": case,
            "profile": T2_PROFILE,
            "raw_dir": str(raw_dir.resolve()),
            "source": {
                "expected_sha": expected_source_sha,
                "commit_sha_start": source_start["commit_sha"],
                "commit_sha_end": source_end["commit_sha"],
                "tracked_status_start": source_start["tracked_status"],
                "tracked_status_end": source_end["tracked_status"],
            },
            "mpi": {
                "size": int(comm.size),
                "expected_size": int(expected_mpi_size),
            },
            "model": model,
            "artifacts": {
                "source": source_descriptor,
                "source_after": source_after_descriptor,
                "action": output_descriptor,
                "reference_action": reference_descriptor,
            },
            "reference": {
                "kind": reference_kind,
                "relative_error": reference_error,
                "matrix_destroyed_before_repeats": reference_closed_before_repeats,
                "setup_seconds": reference_seconds,
                "setup_self_rss_bytes": reference_rss_bytes,
                "setup_rss_semantics": "mpi_rank_max_current_self_rss",
            },
            "repeats": {
                "count": T2_REPEATS,
                "elapsed_seconds": elapsed_seconds,
                "rss_bytes": rss_bytes,
                "swap_used_bytes": swap_used_bytes,
                "output_sha256": output_hashes,
                "relative_differences": relative_differences,
            },
            "resource": {
                "rss_semantics": "mpi_rank_max_current_self_rss",
                "process_tree_evidence": "not_measured_t2",
            },
            "candidate_audit": candidate_audit,
        }
        return record
    finally:
        if candidate is not None:
            candidate.destroy()
        if reference_context is not None:
            reference_context.destroy()
        if reference_vector is not None:
            reference_vector.destroy()
        if expected_vector is not None:
            expected_vector.destroy()
        if assembled is not None:
            assembled.destroy()
        if source_vector is not None:
            source_vector.destroy()
        gc.collect()


def _write_record(record_path: Path, record: Mapping[str, Any]) -> None:
    if record_path.exists():
        raise FileExistsError(f"refusing to overwrite T2 record: {record_path}")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(_canonical_json(record) + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task038 T2 action-only runner/checker")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--case", choices=tuple(T2_CASES), required=True)
    run.add_argument("--raw-dir", type=Path, required=True)
    run.add_argument("--record", type=Path, required=True)
    run.add_argument("--expected-source-sha", required=True)
    run.add_argument("--expected-mpi-size", type=int, required=True)
    check = sub.add_parser("check")
    check.add_argument("--record", type=Path, required=True)
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--p2-mpi1-record", type=Path, required=True)
    aggregate.add_argument("--p3-mpi1-record", type=Path, required=True)
    aggregate.add_argument("--p6-h10-mpi1-record", type=Path, required=True)
    aggregate.add_argument("--p6-h10-mpi2-record", type=Path, required=True)
    aggregate.add_argument("--p6-h5-mpi1-record", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check":
        result = check_t2_record(args.record)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["passed"] else 1
    if args.command == "aggregate":
        result = check_t2_aggregate(
            p2_record_path=args.p2_mpi1_record,
            p3_record_path=args.p3_mpi1_record,
            p6_h10_mpi1_record_path=args.p6_h10_mpi1_record,
            p6_h10_mpi2_record_path=args.p6_h10_mpi2_record,
            p6_h5_record_path=args.p6_h5_mpi1_record,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["passed"] else 1
    try:
        from mpi4py import MPI

        record = _run_case(
            case=args.case,
            raw_dir=args.raw_dir,
            record_path=args.record,
            expected_source_sha=args.expected_source_sha,
            expected_mpi_size=args.expected_mpi_size,
        )
        if MPI.COMM_WORLD.rank == 0:
            _write_record(args.record, record)
        MPI.COMM_WORLD.barrier()
        return 0
    except Exception as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
