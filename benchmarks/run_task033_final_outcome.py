from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.task033_final_outcome import FinalOutcomeError, build_final_outcome


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the independent fail-closed Task033 final outcome record. "
            "Clean MPI2/MPI4 QEP wall-timeouts remain partial evidence only."
        )
    )
    parser.add_argument("--case090-core", type=Path, required=True)
    parser.add_argument("--qep-mpi1-aggregate", type=Path, required=True)
    parser.add_argument("--qep-mpi2-timeout-negative", type=Path, required=True)
    parser.add_argument("--qep-mpi4-timeout-negative", type=Path, required=True)
    parser.add_argument("--augmented-vs-minimal-p1", type=Path, required=True)
    parser.add_argument("--augmented-vs-minimal-p3", type=Path, required=True)
    parser.add_argument("--uniform-p-h-matrix", type=Path, required=True)
    parser.add_argument("--equal-accuracy", type=Path, required=True)
    parser.add_argument("--adaptive-p2-h5", type=Path, required=True)
    parser.add_argument("--adaptive-p2-h3", type=Path, required=True)
    parser.add_argument("--interface-buffer-tradeoff", type=Path, required=True)
    parser.add_argument("--variable-p-capability-audit", type=Path, required=True)
    parser.add_argument("--one-tib-projection", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-nonfailed",
        action="store_true",
        help="Return exit 2 when the successfully classified outcome is failed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        record = build_final_outcome(
            case090_core=args.case090_core,
            qep_mpi1_aggregate=args.qep_mpi1_aggregate,
            qep_mpi2_timeout_negative=args.qep_mpi2_timeout_negative,
            qep_mpi4_timeout_negative=args.qep_mpi4_timeout_negative,
            augmented_vs_minimal_p1=args.augmented_vs_minimal_p1,
            augmented_vs_minimal_p3=args.augmented_vs_minimal_p3,
            uniform_p_h_matrix=args.uniform_p_h_matrix,
            equal_accuracy=args.equal_accuracy,
            adaptive_p2_h5=args.adaptive_p2_h5,
            adaptive_p2_h3=args.adaptive_p2_h3,
            interface_buffer_tradeoff=args.interface_buffer_tradeoff,
            variable_p_capability_audit=args.variable_p_capability_audit,
            one_tib_projection=args.one_tib_projection,
            expected_source_sha=args.expected_source_sha,
        )
    except (FinalOutcomeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "blocked_fail_closed", "problems": [str(exc)]},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    rendered = json.dumps(
        record,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    failed = record["classifications"]["overall"]["disposition"] == "failed"
    return 2 if args.require_nonfailed and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
