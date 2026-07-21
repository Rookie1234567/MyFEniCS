"""Check Task034 changed-files and selective-merge manifest against Git trees."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

INCLUDE_ACTIONS = {
    "merge_with_group",
    "merge_with_portability_group",
    "evidence_only",
}
EXCLUDE_ACTIONS = {
    "historical_compatibility_optional",
    "research_only_do_not_merge_yet",
    "review_only_do_not_merge_to_production",
}
ALREADY_ACTION = "already_on_master_dependency"
TABLE_ROW = re.compile(r"^\| ([A-Z][0-9]*) \| (.+) \|$")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_changed(root: Path, base: str, source: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _git(root, "diff", "--name-status", base, source, "--").stdout.splitlines():
        fields = line.split("\t")
        status = fields[0]
        path = fields[-1]
        if path in result:
            raise ValueError(f"duplicate Git changed path: {path}")
        result[path] = status
    return result


def read_changed_files(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TABLE_ROW.match(line)
        if not match:
            continue
        status, name = match.groups()
        if name in result:
            raise ValueError(f"duplicate changed_files path: {name}")
        result[name] = status
    return result


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _tree_path_exists(root: Path, revision: str, path: str) -> bool:
    return _git(root, "cat-file", "-e", f"{revision}:{path}", check=False).returncode == 0


def _trees_identical(root: Path, base: str, source: str, path: str) -> bool:
    if not _tree_path_exists(root, base, path) or not _tree_path_exists(root, source, path):
        return False
    return _git(root, "diff", "--quiet", f"{base}:{path}", f"{source}:{path}", check=False).returncode == 0


def validate(
    *,
    root: Path,
    base: str,
    source: str,
    changed: Mapping[str, str],
    changed_files: Mapping[str, str],
    manifest: Iterable[Mapping[str, str]],
) -> dict[str, object]:
    rows = list(manifest)
    counts = Counter(row["path"] for row in rows)
    duplicates = sorted(path for path, count in counts.items() if count != 1)
    if duplicates:
        raise ValueError(f"manifest paths must be unique: {duplicates}")

    if dict(changed_files) != dict(changed):
        missing = sorted(set(changed) - set(changed_files))
        extra = sorted(set(changed_files) - set(changed))
        wrong = sorted(
            path for path in set(changed) & set(changed_files)
            if changed[path] != changed_files[path]
        )
        raise ValueError(
            f"changed_files mismatch: missing={missing}, extra={extra}, status={wrong}"
        )

    by_path = {row["path"]: row for row in rows}
    missing = sorted(set(changed) - set(by_path))
    if missing:
        raise ValueError(f"manifest missing changed paths: {missing}")

    extras = sorted(set(by_path) - set(changed))
    for path in extras:
        row = by_path[path]
        if row["merge_action"] != ALREADY_ACTION:
            raise ValueError(f"non-changed manifest extra is not already-on-master: {path}")
        if row["status"] != "already_on_master":
            raise ValueError(f"already-on-master status mismatch: {path}")
        if not _trees_identical(root, base, source, path):
            raise ValueError(f"already-on-master path is absent or differs: {path}")

    allowed = INCLUDE_ACTIONS | EXCLUDE_ACTIONS | {ALREADY_ACTION}
    bad_actions = sorted(
        (row["path"], row["merge_action"])
        for row in rows
        if row["merge_action"] not in allowed
    )
    if bad_actions:
        raise ValueError(f"unsupported merge actions: {bad_actions}")

    for path, status in changed.items():
        row = by_path[path]
        if row["status"] != status:
            raise ValueError(
                f"manifest status mismatch for {path}: {row['status']} != {status}"
            )
        if row["merge_action"] == ALREADY_ACTION:
            raise ValueError(f"changed path cannot be already-on-master: {path}")

    required_research = {
        "benchmarks/run_task034_adaptive_mechanism.py",
        "benchmarks/task034_adaptive_compression.py",
        "src/geometry/task034_adaptive_mesh.py",
        "src/test/test_82_task034_adaptive_mesh.py",
        "src/test/test_83_task034_adaptive_mechanism_record.py",
        "src/test/test_84_task034_adaptive_compression.py",
    }
    for path in required_research:
        row = by_path.get(path)
        if row is None or row["merge_action"] != "research_only_do_not_merge_yet":
            raise ValueError(f"research-only boundary missing: {path}")

    included = [r for r in rows if r["merge_action"] in INCLUDE_ACTIONS]
    excluded = [r for r in rows if r["merge_action"] in EXCLUDE_ACTIONS]
    already = [r for r in rows if r["merge_action"] == ALREADY_ACTION]
    return {
        "base": base,
        "source": source,
        "manifest_rows": len(rows),
        "changed_paths": len(changed),
        "included_paths": len(included),
        "excluded_paths": len(excluded),
        "already_on_master_paths": len(already),
        "include_actions": sorted(INCLUDE_ACTIONS),
        "exclude_actions": sorted(EXCLUDE_ACTIONS),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base", default="origin/master")
    parser.add_argument("--source", default="HEAD")
    parser.add_argument(
        "--changed-files",
        type=Path,
        default=Path(
            "docs/task034_workstation_wsl_adaptive_scalability/outcomes/changed_files.md"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "docs/task034_workstation_wsl_adaptive_scalability/outcomes/"
            "selective_merge_manifest.csv"
        ),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    result = validate(
        root=root,
        base=args.base,
        source=args.source,
        changed=git_changed(root, args.base, args.source),
        changed_files=read_changed_files(root / args.changed_files),
        manifest=read_manifest(root / args.manifest),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
