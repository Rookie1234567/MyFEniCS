from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.task033_reduced_equal_accuracy import ROOT, build_reduced_equal_accuracy


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate the review-v5 reduced Task033 equal-accuracy campaign."
    )
    parser.add_argument("--provisional-reference", type=Path, required=True)
    parser.add_argument("--p2-h3-reference", type=Path, required=True)
    parser.add_argument("--p3-h10-reference", type=Path, required=True)
    parser.add_argument("--p3-h7p5-reference", type=Path, required=True)
    parser.add_argument("--p2-h3-hybrid-watchdog", type=Path, required=True)
    parser.add_argument("--p3-h10-m120", type=Path, required=True)
    parser.add_argument("--p3-h10-m160", type=Path, required=True)
    parser.add_argument("--p3-h7p5-m120", type=Path, required=True)
    parser.add_argument("--p3-h7p5-m160", type=Path, required=True)
    parser.add_argument("--source-compatibility-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    record = build_reduced_equal_accuracy(
        provisional_reference=args.provisional_reference,
        p2_h3_reference=args.p2_h3_reference,
        p3_h10_reference=args.p3_h10_reference,
        p3_h7p5_reference=args.p3_h7p5_reference,
        p2_h3_hybrid_watchdog=args.p2_h3_hybrid_watchdog,
        p3_h10_m120=args.p3_h10_m120,
        p3_h10_m160=args.p3_h10_m160,
        p3_h7p5_m120=args.p3_h7p5_m120,
        p3_h7p5_m160=args.p3_h7p5_m160,
        source_compatibility_audit=args.source_compatibility_audit,
        repo_root=args.repo_root,
    )
    output = args.output if args.output.is_absolute() else args.repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": record["status"],
                "selected_candidate": record["decision"]["selected_candidate"],
                "output": str(output),
                "payload_sha256": record["payload_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if record["decision"]["selected_candidate"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
