"""Hash-bound opt-in execution contract; never changes quadrature/physics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def numerical_source_digest(source_root=None):
    """Bind production Python bytes, not documentation/input-only Git changes.

    The launch still binds the full Git commit. This second identity lets
    unchanged numerical code reuse exact cache shards after a new case's input
    or documentation was committed. Compiled kernels/ABI are bound separately.
    """
    root = (
        Path(source_root)
        if source_root is not None
        else Path(__file__).resolve().parents[1]
    )
    h = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if "test" in relative.parts or "__pycache__" in relative.parts:
            continue
        h.update(relative.as_posix().encode() + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
        count += 1
    if not count:
        raise ValueError("empty numerical source identity")
    return h.hexdigest()


def load_exact_cache_contract(path, expected_sha256, *, source_sha, resolved_payload):
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(c not in "0123456789abcdef" for c in source_sha)
    ):
        raise ValueError("exact-cache requires a frozen source commit")
    raw = Path(path).read_bytes()
    if not expected_sha256 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("exact-cache contract file hash mismatch")
    document = json.loads(raw)
    if (
        document.get("schema") != "exact-cache-execution.v1"
        or document.get("source_sha") != source_sha
    ):
        raise ValueError("exact-cache source/schema mismatch")
    payload_sha = hashlib.sha256(
        json.dumps(
            resolved_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    if document.get("resolved_payload_sha256") != payload_sha:
        raise ValueError("exact-cache resolved payload mismatch")
    cpus = document.get("worker_cpus", [])
    if (
        len(cpus) not in (1, 4, 8, 16, 32)
        or any(type(c) is not int or c < 0 for c in cpus)
        or len(set(cpus)) != len(cpus)
    ):
        raise ValueError("exact-cache needs distinct admitted worker CPUs")
    for name in ("tensor_root", "carrier_root"):
        if (
            not isinstance(document.get(name), str)
            or not Path(document[name]).is_absolute()
        ):
            raise ValueError("exact-cache roots must be absolute")
    source_digest = numerical_source_digest()
    return {
        "contract_sha256": expected_sha256,
        "raw": {
            "root": document["tensor_root"],
            "cpus": cpus,
            "operator_identity": {
                "numerical_source_sha256": source_digest,
                "scalar": "complex128",
                "q": 21,
                "degree": 6,
            },
            "minimum_available_bytes": 68719476736,
        },
        "carrier": {
            "root": document["carrier_root"],
            "numerical_source_sha256": source_digest,
        },
    }
