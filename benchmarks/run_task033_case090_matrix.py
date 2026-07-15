from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.validation.task033_high_order_floquet_fixtures import (
    build_case090_record,
)


def _load_core_gate(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("The core gate record must be a JSON object.")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic Case090 analytic oracles and a fail-closed "
            "p/mesh/MPI execution plan. This command never runs a PDE."
        )
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--core-gate-record", type=Path)
    parser.add_argument(
        "--require-core-gate-pass",
        action="store_true",
        help="Return exit code 2 when the supplied core gate is absent or invalid.",
    )
    args = parser.parse_args()

    record = build_case090_record(
        core_gate_payload=_load_core_gate(args.core_gate_record)
    )
    rendered = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    if args.require_core_gate_pass and record["core_gate"]["status"] != "passed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
