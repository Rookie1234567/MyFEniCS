"""Hash-bound opt-in execution contract; never changes quadrature/physics."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .task40_gate_cd_formal_admission import GATE_CD_PARALLEL32_WORKERS

EXACT_CACHE_TEMPLATE_SCHEMA = "exact-cache-execution-template.v1"
GATE_CD_EXACT_CACHE_WORKER_POLICY = (
    "gate_cd_lease_selected_32_distinct_physical_cores_v1"
)
EXACT_CACHE_TEMPLATE_PATH_ENV = "TASK40_EXACT_CACHE_TEMPLATE_PATH"
EXACT_CACHE_TEMPLATE_SHA_ENV = "TASK40_EXACT_CACHE_TEMPLATE_SHA256"
EXACT_CACHE_CONTRACT_PATH_ENV = "TASK40_EXACT_CACHE_CONTRACT"
EXACT_CACHE_CONTRACT_SHA_ENV = "TASK40_EXACT_CACHE_CONTRACT_SHA256"
EXACT_CACHE_WORKER_CPUS_ENV = "TASK40_EXACT_CACHE_WORKER_CPUS"
EXACT_CACHE_ATTEMPT_ID_ENV = "TASK40_EXACT_CACHE_ATTEMPT_ID"
EXACT_CACHE_RUNTIME_TEMPLATE_SHA_ENV = "TASK40_EXACT_CACHE_RUNTIME_TEMPLATE_SHA256"


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


def _payload_sha256(resolved_payload):
    return hashlib.sha256(
        json.dumps(
            resolved_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def materialize_gate_cd_exact_cache_contract(
    template_path,
    expected_template_sha256,
    *,
    target_path,
    source_sha,
    resolved_payload,
    runtime_cache_root,
    worker_cpus,
    attempt_id,
):
    """Bind a reviewed policy template to one exact lease and dynamic CPU set."""
    template_path = Path(template_path).resolve(strict=True)
    raw = template_path.read_bytes()
    template_sha256 = hashlib.sha256(raw).hexdigest()
    if template_sha256 != str(expected_template_sha256).lower():
        raise ValueError("Gate-CD exact-cache template SHA256 mismatch")
    template = json.loads(raw)
    payload_sha256 = _payload_sha256(resolved_payload)
    if (
        template.get("schema") != EXACT_CACHE_TEMPLATE_SCHEMA
        or template.get("source_sha") != source_sha
        or template.get("resolved_payload_sha256") != payload_sha256
        or template.get("worker_cpu_policy") != GATE_CD_EXACT_CACHE_WORKER_POLICY
        or template.get("worker_count") != GATE_CD_PARALLEL32_WORKERS
        or template.get("tensor_root_policy") != "attempt_cache_root/tensor"
        or template.get("carrier_root_policy") != "attempt_cache_root/carrier"
        or template.get("operator_identity")
        != {"scalar": "complex128", "q": 21, "degree": 6}
    ):
        raise ValueError("Gate-CD exact-cache template differs from its reviewed contract")
    if (
        not isinstance(attempt_id, str)
        or not attempt_id
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in attempt_id)
    ):
        raise ValueError("Gate-CD exact-cache attempt id is invalid")
    cpus = list(worker_cpus)
    if (
        len(cpus) != GATE_CD_PARALLEL32_WORKERS
        or any(type(cpu) is not int or cpu < 0 for cpu in cpus)
        or len(set(cpus)) != GATE_CD_PARALLEL32_WORKERS
    ):
        raise ValueError("Gate-CD exact-cache requires its 32 distinct admitted CPUs")
    requested_root = Path(runtime_cache_root)
    if requested_root.is_symlink():
        raise ValueError("Gate-CD exact-cache attempt root must not be a symlink")
    root = requested_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Gate-CD exact-cache attempt root is missing or symlinked")
    tensor_root = root / "tensor"
    carrier_root = root / "carrier"
    if any(path.is_symlink() or not path.is_dir() for path in (tensor_root, carrier_root)):
        raise ValueError("Gate-CD exact-cache shard roots must be existing attempt directories")
    requested_target = Path(target_path)
    if requested_target.is_symlink():
        raise ValueError("Gate-CD exact-cache runtime contract path must not be a symlink")
    target = requested_target.resolve()
    document = {
        "schema": "exact-cache-execution.v1",
        "source_sha": source_sha,
        "resolved_payload_sha256": payload_sha256,
        "worker_cpu_policy": GATE_CD_EXACT_CACHE_WORKER_POLICY,
        "worker_count": GATE_CD_PARALLEL32_WORKERS,
        "worker_cpus": cpus,
        "tensor_root": str(tensor_root),
        "carrier_root": str(carrier_root),
        "operator_identity": {"scalar": "complex128", "q": 21, "degree": 6},
        "attempt_id": attempt_id,
        "attempt_cache_root": str(root),
        "template_sha256": template_sha256,
    }
    encoded = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("Gate-CD exact-cache runtime contract already exists") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "path": str(target),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "template_path": str(template_path),
        "template_sha256": template_sha256,
        "attempt_id": attempt_id,
        "worker_cpus": cpus,
        "tensor_root": str(tensor_root),
        "carrier_root": str(carrier_root),
    }


def load_exact_cache_contract(
    path,
    expected_sha256,
    *,
    source_sha,
    resolved_payload,
    expected_worker_cpus=None,
    expected_attempt_id=None,
    expected_template_sha256=None,
    expected_cache_root=None,
):
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
    payload_sha = _payload_sha256(resolved_payload)
    if document.get("resolved_payload_sha256") != payload_sha:
        raise ValueError("exact-cache resolved payload mismatch")
    cpus = document.get("worker_cpus", [])
    if (
        len(cpus) not in (1, 4, 8, 16, 32)
        or any(type(c) is not int or c < 0 for c in cpus)
        or len(set(cpus)) != len(cpus)
    ):
        raise ValueError("exact-cache needs distinct admitted worker CPUs")
    if expected_worker_cpus is not None and cpus != list(expected_worker_cpus):
        raise ValueError("exact-cache CPU list differs from the exact runtime lease")
    if "worker_cpu_policy" in document:
        if (
            document.get("worker_cpu_policy") != GATE_CD_EXACT_CACHE_WORKER_POLICY
            or document.get("worker_count") != GATE_CD_PARALLEL32_WORKERS
            or len(cpus) != GATE_CD_PARALLEL32_WORKERS
            or document.get("operator_identity")
            != {"scalar": "complex128", "q": 21, "degree": 6}
        ):
            raise ValueError("Gate-CD exact-cache runtime policy is malformed")
        if expected_attempt_id is not None and document.get("attempt_id") != expected_attempt_id:
            raise ValueError("Gate-CD exact-cache attempt id differs from its lease")
        if (
            expected_template_sha256 is not None
            and document.get("template_sha256") != expected_template_sha256
        ):
            raise ValueError("Gate-CD exact-cache template identity differs from review")
        if expected_cache_root is not None:
            root = Path(expected_cache_root).resolve()
            if (
                Path(document.get("attempt_cache_root", "")).resolve() != root
                or Path(document["tensor_root"]).resolve() != root / "tensor"
                or Path(document["carrier_root"]).resolve() != root / "carrier"
            ):
                raise ValueError("Gate-CD exact-cache roots differ from this attempt")
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
