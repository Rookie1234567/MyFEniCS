"""Validate the Task035b source-branch file-level selective-merge manifest."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess


BASE_SHA = "5002636852ffb67b4711443da70eb536c303e34e"
MANIFEST = Path(
    "docs/task035b_high_order_local_hp_resource_envelope/outcomes/"
    "selective_merge_manifest_v1.csv"
)
REQUIRED_COLUMNS = (
    "path",
    "dependency_group",
    "public_behavior_change",
    "ordinary_default_change",
    "required_tests",
    "fresh_PDE_evidence",
    "merge_order",
    "reason",
)
ALLOWED_GROUPS = {
    "production_core",
    "research_api_opt_in",
    "reusable_benchmark",
    "compact_evidence",
    "project_docs",
    "do_not_merge",
}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_paths(root: Path, *args: str) -> set[str]:
    output = subprocess.check_output(
        ["git", *args],
        cwd=root,
        text=True,
    )
    return {line for line in output.splitlines() if line}


def check_manifest(
    path: Path | None = None,
    *,
    root: Path | None = None,
    compare_live_diff: bool = True,
) -> dict[str, object]:
    root = repository_root() if root is None else Path(root)
    path = root / MANIFEST if path is None else Path(path)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        columns = tuple(reader.fieldnames or ())
    errors: list[str] = []

    if columns != REQUIRED_COLUMNS:
        errors.append(
            f"columns differ: expected={REQUIRED_COLUMNS}, actual={columns}"
        )
    paths = [row.get("path", "") for row in rows]
    if len(paths) != len(set(paths)):
        errors.append("manifest contains duplicate paths")
    for row in rows:
        path_value = row.get("path", "")
        group = row.get("dependency_group", "")
        if group not in ALLOWED_GROUPS:
            errors.append(f"{path_value}: invalid dependency_group={group!r}")
        if row.get("ordinary_default_change") != "no":
            errors.append(f"{path_value}: ordinary default may not change")
        if not row.get("reason"):
            errors.append(f"{path_value}: missing reason")
        if group == "do_not_merge" and row.get("merge_order") != "never":
            errors.append(f"{path_value}: excluded path has merge order")

    if compare_live_diff:
        expected = _git_paths(root, "diff", "--name-only", BASE_SHA)
        expected.update(
            _git_paths(
                root,
                "ls-files",
                "--others",
                "--exclude-standard",
            )
        )
        actual = set(paths)
        if actual != expected:
            for missing in sorted(expected - actual):
                errors.append(f"changed path missing from manifest: {missing}")
            for extra in sorted(actual - expected):
                errors.append(f"manifest path absent from live diff: {extra}")

    return {
        "status": "pass" if not errors else "fail",
        "manifest_path": str(path.relative_to(root)),
        "row_count": len(rows),
        "unique_path_count": len(set(paths)),
        "compare_live_diff": compare_live_diff,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--no-live-diff",
        action="store_true",
    )
    args = parser.parse_args(argv)
    audit = check_manifest(
        args.manifest,
        compare_live_diff=not args.no_live_diff,
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
