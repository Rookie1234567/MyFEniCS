from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.task033_equal_accuracy import ROOT, build_equal_accuracy_from_paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare canonical qualified Task033 Hybrid funnels at equal physical "
            "accuracy using their selected-M external-watchdog records."
        )
    )
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    record = build_equal_accuracy_from_paths(
        args.reference,
        args.candidate,
        repo_root=args.repo_root,
    )
    rendered = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output} status={record['status']}")
    return 2 if args.require_qualified and record["status"] != "qualified" else 0


if __name__ == "__main__":
    raise SystemExit(main())
