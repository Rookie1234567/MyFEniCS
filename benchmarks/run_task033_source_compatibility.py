from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.task033_source_compatibility import (
    DEFAULT_FULL3D_SOURCE,
    DEFAULT_HYBRID_SOURCE,
    ROOT,
    build_full3d_hybrid_source_compatibility_audit,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Task033 p3/h5 full3D and Hybrid source compatibility "
            "without running a PDE."
        )
    )
    parser.add_argument("--full3d-source", default=DEFAULT_FULL3D_SOURCE)
    parser.add_argument("--hybrid-source", default=DEFAULT_HYBRID_SOURCE)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-compatible", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    record = build_full3d_hybrid_source_compatibility_audit(
        full3d_source=args.full3d_source,
        hybrid_source=args.hybrid_source,
        repo_root=args.repo_root,
    )
    rendered = json.dumps(
        record, ensure_ascii=False, indent=2, allow_nan=False
    ) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return (
        2
        if args.require_compatible and not record["compatible"]
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
