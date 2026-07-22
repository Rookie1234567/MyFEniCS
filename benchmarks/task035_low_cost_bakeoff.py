from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from src.validation.task035_low_cost_bakeoff import build_low_cost_bakeoff_entry


ROOT = Path(__file__).resolve().parents[1]
RECORDS = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real-fe-record", type=Path, default=RECORDS / "real_fe_mpi1.json"
    )
    parser.add_argument(
        "--identity-record",
        type=Path,
        default=RECORDS / "real_fe_mpi_identity.json",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    record = build_low_cost_bakeoff_entry(
        json.loads(args.real_fe_record.read_text(encoding="utf-8")),
        json.loads(args.identity_record.read_text(encoding="utf-8")),
    )
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
