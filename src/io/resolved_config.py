"""Stable JSON serialization for a resolved Task38 specification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .run_specification import RunSpecification


def canonical_json_bytes(value: Any) -> bytes:
    """Encode finite JSON data with the Task38 canonical separators/order."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def resolved_config_bytes(specification: RunSpecification) -> bytes:
    return canonical_json_bytes(specification.as_jsonable()) + b"\n"


def resolved_config_sha256(specification: RunSpecification) -> str:
    return hashlib.sha256(resolved_config_bytes(specification)).hexdigest()


def write_resolved_config(
    specification: RunSpecification,
    target: str | Path,
) -> str:
    """Write one explicit resolved-config path without creating directories."""

    target_path = Path(target)
    payload = resolved_config_bytes(specification)
    target_path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
