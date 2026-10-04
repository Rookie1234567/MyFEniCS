"""Read-only, hash-bound component dependencies from existing Git objects.

This creates a source cache, not a clone or a worktree. No numerical source
is rewritten, and no external checkout or branch is modified.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_manifest(record):
    if record.get("schema") != "frozen-component-source.v1":
        raise ValueError("unknown component source schema")
    commit = record.get("commit", "")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("a complete immutable dependency commit is required")
    rows = record.get("files", [])
    if not rows or len({r["path"] for r in rows}) != len(rows):
        raise ValueError("empty or duplicate dependency paths")
    for row in rows:
        path = PurePosixPath(row["path"])
        if path.is_absolute() or ".." in path.parts or str(path) != row["path"]:
            raise ValueError("dependency path escapes the source cache")
        if row["bytes"] < 0 or len(row["sha256"]) != 64:
            raise ValueError("invalid dependency content binding")
    return record


def materialize(root, manifest_path, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if not destination.is_relative_to(root / "benchmarks/artifacts/task42extra"):
        raise ValueError("component source cache must remain task-local")
    record = validate_manifest(json.loads(Path(manifest_path).read_text()))
    if not destination.exists():
        destination.mkdir(parents=True)
        for row in record["files"]:
            data = subprocess.check_output(
                ["git", "show", record["commit"] + ":" + row["path"]], cwd=root
            )
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("Git object differs from the frozen dependency manifest")
            target = destination / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o444)
    verify_snapshot(record, destination)
    return record


def verify_snapshot(record, destination):
    record = validate_manifest(record)
    destination = Path(destination).resolve()
    expected = {row["path"] for row in record["files"]}
    actual = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
    if actual != expected or any(p.is_symlink() for p in destination.rglob("*")):
        raise ValueError("source cache has missing, extra, or symlinked members")
    for row in record["files"]:
        path = destination / row["path"]
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise ValueError("frozen source cache member changed: " + row["path"])
    return {"dependency_commit": record["commit"], "members": len(expected),
            "bytes": sum(r["bytes"] for r in record["files"]), "verified": True}
