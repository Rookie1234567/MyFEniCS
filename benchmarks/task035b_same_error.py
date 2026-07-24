#!/usr/bin/env python3
"""Generate a SHA-bound Task035b cross-mesh same-error audit record."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys

from src.adaptivity.high_order_same_error import audit_global_p6_same_error


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _source_preflight(verified_clean_sha: str) -> dict:
    head = _git("rev-parse", "HEAD")
    complete_status = _git("status", "--short", "--untracked-files=all")
    if head != str(verified_clean_sha):
        raise ValueError(
            f"verified clean SHA {verified_clean_sha} does not match HEAD {head}"
        )
    if complete_status:
        raise ValueError(
            "Task035b same-error audit requires a fully clean worktree: "
            + complete_status
        )
    return {
        "commit_sha": head,
        "tracked_source_dirty": False,
        "tracked_source_verification": "host_git_clean_attestation",
        "verified_clean_sha": str(verified_clean_sha),
    }


def run(args: argparse.Namespace) -> dict:
    source = _source_preflight(args.verified_clean_sha)
    record = audit_global_p6_same_error(
        control_record_path=args.control_record,
        control_record_sha256=args.control_sha256,
        candidate_record_path=args.candidate_record,
        candidate_record_sha256=args.candidate_sha256,
    )
    head_after = _git("rev-parse", "HEAD")
    status_after = _git("status", "--short", "--untracked-files=all")
    source.update(
        {
            "head_after_sha": head_after,
            "status_after_before_record_write": status_after,
            "stable_and_clean_after": (
                head_after == source["commit_sha"] and not status_after
            ),
        }
    )
    if source["stable_and_clean_after"] is not True:
        raise RuntimeError("tracked source identity changed during same-error audit")
    record.update(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "command": " ".join(shlex.quote(value) for value in sys.argv),
            "source": source,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return record


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-record", type=Path, required=True)
    parser.add_argument("--control-sha256", required=True)
    parser.add_argument("--candidate-record", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    record = run(args)
    print(
        json.dumps(
            {
                "status": record["status"],
                "pass": record["pass"],
                "failed_gates": record["failed_gates"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
