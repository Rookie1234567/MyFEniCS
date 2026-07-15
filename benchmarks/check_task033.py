"""CLI for the Task033 planning/formal evidence checker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.task033_evidence_checker import (
    DEFAULT_FORMAL_MANIFEST,
    ROOT,
    check_task033,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify committed Task033 planning evidence, or fail closed over a "
            "complete Case090/091 formal evidence manifest."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--formal-manifest",
        type=Path,
        help="Formal manifest to verify; providing it enables formal mode.",
    )
    parser.add_argument(
        "--require-formal",
        action="store_true",
        help=(
            "Require the complete formal role set. Without --formal-manifest, "
            f"the committed {DEFAULT_FORMAL_MANIFEST.as_posix()} is checked and "
            "therefore remains fail-closed while it is NOT_RUN."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = check_task033(
        root=args.repo_root,
        formal_manifest=args.formal_manifest,
        require_formal=args.require_formal,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    print(rendered, end="")
    return 0 if report["verified"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
