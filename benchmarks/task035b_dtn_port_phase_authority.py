"""Thin CLI for the Task035b artifact-only DtN-port phase audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from src.adaptivity.dtn_port_phase_authority import (
    build_dtn_port_phase_authority,
)


DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/dtn_port_phase_authority_v1.json"
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit accepted Task035b raw DtN-order artifacts without "
            "running a PDE."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--authority-manifest",
        type=Path,
        help="optional explicit SHA-bound manifest JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args(argv)


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest = None
    if args.authority_manifest is not None:
        manifest_path = _resolve(repo_root, args.authority_manifest)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = build_dtn_port_phase_authority(
        repo_root,
        manifest=manifest,
    )
    output = _resolve(repo_root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if record["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
