from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.task033_variable_p_capability import (
    build_variable_p_capability_audit,
    inspect_repository_source,
    qualify_formal_source,
)


ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit current-runtime public APIs for Task033 variable-p H(curl); "
            "symbol presence never substitutes for semantic/MPI qualification."
        )
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--formal",
        action="store_true",
        help="Require a complete clean/stable Git checkout and attach formal_source.",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        before = (
            inspect_repository_source(args.repo_root) if args.formal else None
        )
        record = build_variable_p_capability_audit()
        if before is not None:
            after = inspect_repository_source(args.repo_root)
            record["identity"]["is_formal_record"] = True
            record["formal_source"] = qualify_formal_source(before, after)
    except (OSError, RuntimeError, ValueError) as exc:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
