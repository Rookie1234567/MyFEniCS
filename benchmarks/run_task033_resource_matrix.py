from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from benchmarks.task033_resource_gates import (
    build_reduced_equal_accuracy_resource_matrix,
    build_resource_matrix,
)


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def flatten_entry(entry: dict[str, Any]) -> dict[str, str]:
    """Flatten every JSON entry leaf into a lossless CSV cell.

    Scalar and list leaves use canonical JSON text, so a consumer can apply
    ``json.loads`` to every non-empty cell and recover the JSON value exactly.
    Missing optional paths are represented by an empty CSV cell.
    """

    flattened: dict[str, str] = {}

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                child = f"{prefix}.{key}" if prefix else str(key)
                visit(child, value[key])
            return
        flattened[prefix] = _json_cell(value)

    visit("", entry)
    return flattened


def _write_csv(path: Path, entries: list[dict[str, Any]]) -> None:
    flattened = [flatten_entry(entry) for entry in entries]
    fields = sorted({field for row in flattened for field in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in flattened:
            writer.writerow(row)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write deterministic Task033 p1-4/h5-h1.5 resource predictions; "
            "no PDE is run and runtime gates default to unknown/fail-closed."
        )
    )
    parser.add_argument(
        "--container-limit-gib",
        type=float,
        help=(
            "Refreshed numeric Docker/cgroup limit. Omit to use the measured "
            "Phase-0 Docker Engine limit of 13.6485 GiB."
        ),
    )
    parser.add_argument("--source-clean-verified", action="store_true", default=None)
    parser.add_argument("--no-swap-verified", action="store_true", default=None)
    parser.add_argument(
        "--watchdog-enabled-verified", action="store_true", default=None
    )
    parser.add_argument("--one-large-case-verified", action="store_true", default=None)
    parser.add_argument("--p3-qualified", action="store_true")
    parser.add_argument("--p4-qualified", action="store_true")
    parser.add_argument("--conditional-clean-record", action="append", default=[])
    parser.add_argument("--locked-override", action="append", default=[])
    parser.add_argument(
        "--reduced-equal-accuracy",
        action="store_true",
        help=(
            "Write only the review-v5 p3/h10 and conditional p3/h7.5 "
            "candidate predictions."
        ),
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-csv", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    qualified = []
    if args.p3_qualified:
        qualified.append(3)
    if args.p4_qualified:
        qualified.append(4)
    if args.reduced_equal_accuracy:
        record = build_reduced_equal_accuracy_resource_matrix(
            container_limit_gib=args.container_limit_gib,
        )
    else:
        record = build_resource_matrix(
            container_limit_gib=args.container_limit_gib,
            source_clean=args.source_clean_verified,
            swap_activity_detected=(
                False if args.no_swap_verified is True else None
            ),
            watchdog_enabled=args.watchdog_enabled_verified,
            one_large_case_at_a_time=args.one_large_case_verified,
            qualified_high_order_degrees=qualified,
            conditional_clean_records=args.conditional_clean_record,
            locked_overrides=args.locked_override,
        )
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output_json is None:
        print(payload, end="")
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    if args.output_csv is not None:
        _write_csv(args.output_csv, record["entries"])


if __name__ == "__main__":
    main()
