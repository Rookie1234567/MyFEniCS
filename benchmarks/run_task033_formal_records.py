"""Stdout-only CLI for Task033 Case091 formal evidence orchestration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.task033_formal_records import (
    FormalRecordError,
    build_adaptive_evidence,
    build_formal_manifest,
    build_interface_buffer_tradeoff,
    build_qep_order_study,
    build_uniform_p_h_matrix,
)


ROOT = Path(__file__).resolve().parents[1]


def _bindings(values: list[str], *, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, raw_path = value.partition("=")
        if not separator or not key or not raw_path:
            raise FormalRecordError(f"{label} binding must use KEY=PATH: {value!r}")
        if key in result:
            raise FormalRecordError(f"duplicate {label} binding for {key!r}")
        result[key] = Path(raw_path)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build Task033 formal JSON records from existing evidence. "
            "All subcommands are read-only and emit JSON to stdout only."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    qep = subparsers.add_parser(
        "qep-order-study", help="Aggregate the native 36-shard QEP h/p study."
    )
    qep.add_argument("records", nargs="+", type=Path)
    qep.add_argument("--mpi-size", type=int, choices=(1, 2, 4), default=1)

    matrix = subparsers.add_parser(
        "uniform-matrix",
        help="Bind all 20 resource rows to funnels, an anchor, or memory NOT_RUN.",
    )
    matrix.add_argument("--resource-matrix", type=Path, required=True)
    matrix.add_argument(
        "--funnel",
        action="append",
        default=[],
        metavar="MATRIX_KEY=PATH",
    )
    matrix.add_argument(
        "--anchor",
        action="append",
        default=[],
        metavar="MATRIX_KEY=PATH",
    )
    matrix.add_argument(
        "--watchdog",
        action="append",
        default=[],
        metavar="MATRIX_KEY=PATH",
        help="Measured Hybrid watchdog summary for one matrix row.",
    )

    adaptive = subparsers.add_parser(
        "adaptive", help="Recompute one h5/h3 measured same-accuracy gate."
    )
    adaptive.add_argument("--graded-plan", type=Path, required=True)
    adaptive.add_argument("--reference-evidence", type=Path, required=True)
    adaptive.add_argument("--candidate-evidence", type=Path, required=True)

    tradeoff = subparsers.add_parser(
        "buffer-tradeoff",
        help="Build the four-buffer measured local/modal joint-cost tradeoff.",
    )
    tradeoff.add_argument("funnels", nargs=4, type=Path)

    manifest = subparsers.add_parser(
        "formal-manifest", help="Build the frozen 16-role SHA256 manifest."
    )
    manifest.add_argument(
        "--role",
        action="append",
        default=[],
        required=True,
        metavar="ROLE=REPO_RELATIVE_PATH",
    )
    manifest.add_argument("--repo-root", type=Path, default=ROOT)
    return parser


def _dispatch(args: argparse.Namespace) -> dict:
    if args.command == "qep-order-study":
        return build_qep_order_study(args.records, mpi_size=args.mpi_size)
    if args.command == "uniform-matrix":
        return build_uniform_p_h_matrix(
            args.resource_matrix,
            funnel_paths=_bindings(args.funnel, label="funnel"),
            anchor_paths=_bindings(args.anchor, label="anchor"),
            watchdog_paths=_bindings(args.watchdog, label="watchdog"),
        )
    if args.command == "adaptive":
        return build_adaptive_evidence(
            args.graded_plan,
            args.reference_evidence,
            args.candidate_evidence,
        )
    if args.command == "buffer-tradeoff":
        return build_interface_buffer_tradeoff(args.funnels)
    if args.command == "formal-manifest":
        return build_formal_manifest(
            _bindings(args.role, label="role"), repo_root=args.repo_root
        )
    raise FormalRecordError(f"unsupported subcommand {args.command!r}")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _dispatch(_parser().parse_args(argv))
    except (FormalRecordError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "task033.formal-record-blocker.v1",
                    "status": "blocked_fail_closed",
                    "problems": [str(exc)],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
