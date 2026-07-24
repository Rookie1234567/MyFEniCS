"""Build the SHA-bound Task035b significant-channel reference v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from src.adaptivity.significant_channel_reference import (
    build_significant_channel_reference,
    render_significant_channel_markdown,
)


DEFAULT_OUTPUT = Path(
    "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
    "records/significant_channel_reference_v1.json"
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate accepted Task034/Case095 raw authorities and freeze "
            "the Task035b 12-channel reference without running a PDE."
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
        help=(
            "optional explicit manifest JSON; the frozen in-code manifest is "
            "used by default"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        help="optional standalone Markdown data table; no existing docs change",
    )
    return parser.parse_args(argv)


def _resolve_output(repo_root: Path, output: Path) -> Path:
    return output if output.is_absolute() else repo_root / output


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest = None
    if args.authority_manifest is not None:
        manifest_path = _resolve_output(
            repo_root,
            args.authority_manifest,
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = build_significant_channel_reference(
        repo_root,
        manifest=manifest,
    )
    output = _resolve_output(repo_root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.markdown_output is not None:
        markdown_output = _resolve_output(
            repo_root,
            args.markdown_output,
        )
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(
            render_significant_channel_markdown(record),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
