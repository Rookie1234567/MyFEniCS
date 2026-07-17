from __future__ import annotations

import argparse
from pathlib import Path
import sys
import traceback

from benchmarks.task033_case090_pde_core import (
    DEGREES,
    MPI_SIZES,
    aggregate_core_records,
    build_shard_plan,
    build_shard_record,
    extract_case_artifact_validation,
    extract_pde_result,
    failed_pde_result,
    inspect_tracked_source,
    read_json_object,
    run_algebra_probe,
    run_pde_case,
    write_json_object,
)


ROOT = Path(__file__).resolve().parents[1]


def _run_shard(args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    if comm.size not in MPI_SIZES:
        if comm.rank == 0:
            print(
                f"Case090 shard requires MPI size {MPI_SIZES}, got {comm.size}.",
                file=sys.stderr,
            )
        return 2
    output = Path(args.output).resolve()
    work_dir = Path(args.work_dir).resolve()
    source_at_start = inspect_tracked_source(ROOT)
    algebra_probes: list[dict] = []
    results: list[dict] = []

    try:
        algebra_failed = False
        for degree in DEGREES:
            probe = None
            probe_error = None
            try:
                probe = run_algebra_probe(
                    degree=degree,
                    mpi_size=comm.size,
                    out_dir=work_dir / "algebra" / f"p{degree}",
                )
            except Exception as exc:
                probe_error = f"{type(exc).__name__}: {exc}"
            algebra_failed = bool(
                comm.allreduce(probe_error is not None, op=MPI.LOR)
            )
            if comm.rank == 0:
                if algebra_failed:
                    algebra_probes.append(
                        {
                            "degree": degree,
                            "mpi_size": comm.size,
                            "core_algebra_gates_passed": False,
                            "error": probe_error
                            or "algebra probe failed on a non-root rank",
                        }
                    )
                elif probe is not None:
                    algebra_probes.append(probe)
            if algebra_failed:
                break

        if not algebra_failed:
            for entry in build_shard_plan(comm.size):
                summary = None
                artifact_validation = None
                local_error = None
                case_out_dir = work_dir / str(entry["matrix_id"])
                try:
                    summary = run_pde_case(entry, case_out_dir)
                except Exception as exc:
                    local_error = f"{type(exc).__name__}: {exc}"
                failed = bool(
                    comm.allreduce(
                        local_error is not None
                        or summary is None
                        or summary.get("case_status") != "completed",
                        op=MPI.LOR,
                    )
                )
                if not failed and entry["fixture"] == "fixture_b_flat_air_si":
                    try:
                        artifact_validation = extract_case_artifact_validation(
                            entry, case_out_dir
                        )
                    except Exception as exc:
                        local_error = f"artifact oracle {type(exc).__name__}: {exc}"
                    failed = bool(
                        comm.allreduce(local_error is not None, op=MPI.LOR)
                    )
                if comm.rank == 0:
                    if failed or summary is None:
                        results.append(
                            failed_pde_result(
                                entry,
                                local_error
                                or "PDE case failed or raised on a non-root rank",
                            )
                        )
                    else:
                        results.append(
                            extract_pde_result(
                                entry,
                                summary,
                                artifact_validation=artifact_validation,
                            )
                        )
                if failed:
                    break

                if comm.rank == 0:
                    progress = build_shard_record(
                        mpi_size=comm.size,
                        source_at_start=source_at_start,
                        source_at_end=inspect_tracked_source(ROOT),
                        algebra_probes=algebra_probes,
                        results=results,
                    )
                    write_json_object(output, progress)
    except Exception as exc:
        if comm.rank == 0:
            print(
                f"Case090 algebra/PDE shard aborted: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            traceback.print_exc()

    comm.barrier()
    source_at_end = inspect_tracked_source(ROOT)
    if comm.rank == 0:
        record = build_shard_record(
            mpi_size=comm.size,
            source_at_start=source_at_start,
            source_at_end=source_at_end,
            algebra_probes=algebra_probes,
            results=results,
        )
        write_json_object(output, record)
        print(
            f"wrote {output} status={record['status']} "
            f"cases={record['coverage']['observed_case_count']}"
        )
        return_code = 0 if record["status"] == "passed" else 2
    else:
        return_code = 0
    return int(comm.bcast(return_code, root=0))


def _run_aggregate(args: argparse.Namespace) -> int:
    shards = [read_json_object(path) for path in args.shards]
    memory_summaries = [
        read_json_object(path) for path in args.memory_summaries
    ]
    record = aggregate_core_records(shards, memory_summaries)
    if args.output is None:
        import json

        print(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        write_json_object(args.output, record)
        print(
            f"wrote {Path(args.output).resolve()} "
            f"all_core_gates_passed={record['all_core_gates_passed']}"
        )
    if args.require_pass and record["all_core_gates_passed"] is not True:
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one real Case090 MPI PDE shard or aggregate exactly the clean "
            "MPI1/MPI2/MPI4 shard records into the existing core-gate format."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    shard = subparsers.add_parser(
        "shard", help="Run the exact 48-entry PDE matrix for this MPI communicator."
    )
    shard.add_argument("--output", type=Path, required=True)
    shard.add_argument("--work-dir", type=Path, required=True)
    shard.set_defaults(func=_run_shard)

    aggregate = subparsers.add_parser(
        "aggregate", help="Aggregate exactly three clean MPI shard records."
    )
    aggregate.add_argument("shards", type=Path, nargs=3)
    aggregate.add_argument(
        "--memory-summaries",
        type=Path,
        nargs=3,
        required=True,
        help="Exactly the MPI1/MPI2/MPI4 external watchdog summaries.",
    )
    aggregate.add_argument("--output", type=Path)
    aggregate.add_argument("--require-pass", action="store_true")
    aggregate.set_defaults(func=_run_aggregate)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
