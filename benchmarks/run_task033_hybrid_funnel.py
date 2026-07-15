from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.task033_hybrid_funnel import build_hybrid_funnel_from_paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate clean Task033 Hybrid M80/M120/M160 watchdog summaries; "
            "M240 is accepted only as the conditional final funnel point."
        )
    )
    parser.add_argument("records", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    record = build_hybrid_funnel_from_paths(args.records)
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
