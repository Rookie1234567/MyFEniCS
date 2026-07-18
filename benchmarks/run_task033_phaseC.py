from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from benchmarks.run_task033_qep_matrix import _resource_environment_snapshot
from benchmarks.task033_phaseC import (
    build_phasec_preflight,
    build_phasec_summary_from_paths,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESOURCE_MATRIX = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "resource_matrix.json"
)


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
    ).strip()


def _object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return payload


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _preflight(args: argparse.Namespace) -> int:
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--short", "--untracked-files=all")
    if head != args.verified_clean_sha or status:
        raise SystemExit(
            "Phase C0 requires exact HEAD and a completely clean nonignored worktree."
        )
    snapshot = _resource_environment_snapshot()
    required = (
        "memory_limit_bytes",
        "host_available_memory_bytes",
        "memory_current_bytes",
        "swap_current_bytes",
        "pswpin_pages",
        "pswpout_pages",
    )
    missing = [name for name in required if snapshot.get(name) is None]
    if missing:
        raise SystemExit(f"Phase C0 live environment fields are unreadable: {missing}")
    record = build_phasec_preflight(
        _object(args.resource_matrix),
        source_commit_full_sha=head,
        container_limit_bytes=int(snapshot["memory_limit_bytes"]),
        host_available_memory_bytes=int(snapshot["host_available_memory_bytes"]),
        container_current_bytes=int(snapshot["memory_current_bytes"]),
        container_swap_current_bytes=int(snapshot["swap_current_bytes"]),
        pswpin_pages=int(snapshot["pswpin_pages"]),
        pswpout_pages=int(snapshot["pswpout_pages"]),
    )
    _write(args.output, record)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": record["status"],
                "qualification": record["qualification"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if record["qualification"]["hybrid_component_chain_launchable"] else 2


def _aggregate(args: argparse.Namespace) -> int:
    record = build_phasec_summary_from_paths(
        preflight_path=args.preflight,
        funnel_path=args.funnel,
        hybrid_paths=args.hybrid,
        augmented_path=args.augmented,
    )
    _write(args.output, record)
    print(f"wrote {args.output} status={record['status']}")
    return 0 if not record["failures"] else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Task033 review-v3 Phase C0 and p3/h5 partial-chain tools."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--verified-clean-sha", required=True)
    preflight.add_argument(
        "--resource-matrix", type=Path, default=DEFAULT_RESOURCE_MATRIX
    )
    preflight.add_argument("--output", type=Path, required=True)
    preflight.set_defaults(handler=_preflight)

    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--preflight", type=Path, required=True)
    aggregate.add_argument("--funnel", type=Path, required=True)
    aggregate.add_argument(
        "--hybrid", type=Path, nargs=3, metavar=("M80", "M120", "M160")
    )
    aggregate.add_argument("--augmented", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    aggregate.set_defaults(handler=_aggregate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
