"""Linux CLI for one Task000 forward case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .forward_model import ForwardModel
from .schema import ForwardParameters, RunConfig, parameter_catalog


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.forward_data.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--formal", action="store_true")
    run.add_argument("--timeout-seconds", type=int, default=1800)
    schema = sub.add_parser("schema")
    schema.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "schema":
        rendered = json.dumps(parameter_catalog(), indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    try:
        payload = json.loads(args.config.read_text(encoding="utf-8"))
        parameters = ForwardParameters.from_mapping(payload)
        result = ForwardModel().evaluate(
            parameters,
            RunConfig(
                output=args.output.resolve(), dry_run=args.dry_run,
                formal=args.formal, timeout_seconds=args.timeout_seconds,
            ),
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "preflight_failed", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result.status,
        "return_code": result.return_code,
        "run_directory": str(result.run_directory),
        "observables": result.observables,
    }, sort_keys=True))
    if result.status == "physics_gate_failed":
        return 4
    return 0 if result.return_code == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
