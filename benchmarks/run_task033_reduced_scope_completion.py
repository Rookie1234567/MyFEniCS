from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.task033_reduced_scope_completion import (
    DEFAULT_RECORD,
    ROOT,
    build_reduced_scope_completion,
    verify_reduced_scope_completion,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build or verify the no-PDE Task033 reduced-scope completion "
            "record approved by Review V6."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify:
        result = verify_reduced_scope_completion(
            args.record,
            repo_root=args.repo_root,
        )
    else:
        result = build_reduced_scope_completion(repo_root=args.repo_root)
        if args.output is not None:
            output = (
                args.output
                if args.output.is_absolute()
                else args.repo_root / args.output
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
    print(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
