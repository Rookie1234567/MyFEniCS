"""Source and artifact identity helpers for Task000 records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


EXPECTED_BRANCH = "codex/only-one-13p5nm-surrogate-inversion"
EXPECTED_UPSTREAM = f"origin/{EXPECTED_BRANCH}"
EXPECTED_ORIGIN = "https://github.com/Rookie1234567/MyFEniCS.git"


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
    ).strip()


def source_identity(root: Path) -> dict[str, Any]:
    status = _git(root, "status", "--short", "--untracked-files=all")
    identity = {
        "repository_root": str(root.resolve()),
        "origin": _git(root, "remote", "get-url", "origin"),
        "branch": _git(root, "branch", "--show-current"),
        "upstream": _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        "source_sha": _git(root, "rev-parse", "HEAD"),
        "dirty": bool(status),
        "status": status,
    }
    if identity["origin"] != EXPECTED_ORIGIN:
        raise RuntimeError("unexpected origin")
    if identity["branch"] != EXPECTED_BRANCH:
        raise RuntimeError("unexpected branch")
    if identity["upstream"] != EXPECTED_UPSTREAM:
        raise RuntimeError("unexpected upstream")
    return identity


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_dataset_identity(manifests: list[dict[str, Any]]) -> dict[str, str]:
    """Reject dirty or mixed-source/schema records before dataset assembly."""

    if not manifests:
        raise ValueError("dataset requires at least one manifest")
    identities = {
        (
            item.get("source", {}).get("source_sha"),
            item.get("source", {}).get("dirty"),
            item.get("parameter_schema_version"),
            item.get("observable_schema_version"),
        )
        for item in manifests
    }
    if len(identities) != 1:
        raise ValueError("dataset manifests mix source or schema identities")
    source_sha, dirty, parameter_schema, observable_schema = identities.pop()
    if dirty is not False or not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("dataset manifests require one clean full source SHA")
    if not parameter_schema or not observable_schema:
        raise ValueError("dataset manifests require both schema versions")
    return {
        "source_sha": source_sha,
        "parameter_schema_version": str(parameter_schema),
        "observable_schema_version": str(observable_schema),
    }
