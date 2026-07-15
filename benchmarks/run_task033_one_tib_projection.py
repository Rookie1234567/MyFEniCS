from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.task033_one_tib_projection import (
    build_one_tib_projection,
    validate_one_tib_projection,
)
from benchmarks.task033_variable_p_capability import (
    inspect_repository_source,
    qualify_formal_source,
)


ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Classify the Task032 0.7 nm local-row scenario using a sourced "
            "Task033 measured compression; missing evidence stays not_qualified."
        )
    )
    parser.add_argument("--measured-compression", type=float)
    parser.add_argument(
        "--measurement-identity",
        choices=("measured", "derived", "predicted"),
    )
    parser.add_argument("--evidence-record")
    parser.add_argument(
        "--compression-evidence",
        type=Path,
        help=(
            "Reviewed adaptive or equal-accuracy formal JSON; the record type "
            "is detected automatically and strict validation is required for "
            "a classified result."
        ),
    )
    parser.add_argument(
        "--formal",
        action="store_true",
        help="Require complete clean/stable Git source and same-SHA evidence.",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    return parser


def _load_evidence(path: Path | None) -> dict | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.compression_evidence is not None and (
            args.measured_compression is not None
            or args.measurement_identity is not None
            or args.evidence_record is not None
        ):
            raise ValueError(
                "--compression-evidence cannot be combined with manual "
                "compression or evidence-identity arguments"
            )
        before = (
            inspect_repository_source(args.repo_root) if args.formal else None
        )
        evidence = _load_evidence(args.compression_evidence)
        provisional_source = (
            qualify_formal_source(before, before) if before is not None else None
        )
        record = build_one_tib_projection(
            measured_compression=args.measured_compression,
            measurement_identity=args.measurement_identity,
            evidence_record=(
                str(args.compression_evidence)
                if args.compression_evidence is not None
                else args.evidence_record
            ),
            compression_evidence=evidence,
            formal_source=provisional_source,
        )
        if before is not None:
            after = inspect_repository_source(args.repo_root)
            record["formal_source"] = qualify_formal_source(before, after)
        validate_one_tib_projection(record)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked_fail_closed",
                    "problems": [str(exc)],
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0 if not args.formal or record["status"] == "classified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
