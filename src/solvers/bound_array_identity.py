"""Strict streaming evidence readers; no solver, implicit large copy or fallback."""

import ast
import hashlib
import json
import subprocess
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def member_hash(array):
    if not array.flags.c_contiguous or array.dtype.hasobject:
        raise ValueError("bound array must be contiguous and contain no objects")
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def read_json(receipt, root):
    path = Path(receipt["path"]).resolve()
    if not path.is_relative_to(Path(root).resolve()) or path.stat().st_size > 8 * 2**20:
        raise ValueError("bound metadata path/size")
    if file_hash(path) != receipt["sha256"]:
        raise ValueError("bound metadata hash")
    return json.loads(path.read_text())


def read_arrays(receipt, root, *, names=None):
    """Validate full storage inventory; hash selected members without bytes copies."""
    import numpy as np

    path = Path(receipt["path"]).resolve()
    if not path.is_relative_to(Path(root).resolve()) or file_hash(path) != receipt["sha256"]:
        raise ValueError("bound array path/file hash")
    members, aliases = receipt["members"], receipt.get("aliases", {})
    if not set(aliases) <= set(members) or any(
        v not in members or v in aliases for v in aliases.values()
    ):
        raise ValueError("bound alias inventory")
    selected = set(members) if names is None else set(names)
    if not selected <= set(members):
        raise ValueError("required member missing")
    out = {}
    with np.load(path, allow_pickle=False) as stored:
        if len(stored.files) != len(set(stored.files)) or set(stored.files) != set(members) - set(aliases):
            raise ValueError("bound storage inventory")
        for name in sorted(selected):
            meta = members[name]
            value = stored[aliases.get(name, name)]
            if list(value.shape) != meta["shape"] or value.dtype.str != meta["dtype"] or member_hash(value) != meta["sha256"]:
                raise ValueError("bound member shape/dtype/hash: " + name)
            out[name] = value
    return out


def source_identity(source_bytes, snapshot, *, blob):
    """Derive degree from literal source, source SHA from bound publication content."""
    tree = ast.parse(source_bytes)
    degrees = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "nedelec_degree" and isinstance(node.value, ast.Constant):
            degrees.add(node.value.value)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "degree" and isinstance(value, ast.Constant):
                    degrees.add(value.value)
    if len(degrees) > 1:
        raise ValueError("conflicting original degree evidence")
    return {
        "degree": next(iter(degrees)) if degrees else "unknown",
        "scale": snapshot.get("physical_scale", "unknown"),
        "mode_inventory": snapshot.get("complete_mode_inventory", "unknown"),
        "source_sha": snapshot.get("source_head", "unknown"),
        "source_blob": blob,
        "source_content_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "provenance": "original source AST and bound compact content, no execution",
    }


def consume_identity(required, actual, consumer):
    mismatches = {
        key: {"required": value, "actual": actual.get(key, "unknown")}
        for key, value in required.items()
        if value == "unknown" or actual.get(key, "unknown") == "unknown" or actual.get(key) != value
    }
    if mismatches:
        return {"accepted": False, "mismatches": mismatches, "consumer_called": False}
    return {"accepted": True, "consumer_called": True, "result": consumer(actual)}


def original_source(root, commit, path, blob):
    """Read an already present Git object; never fetch or change another ref."""
    prefix = ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false"]
    actual = subprocess.check_output(prefix + ["rev-parse", commit + ":" + path], cwd=root, text=True).strip()
    if actual != blob:
        raise ValueError("original source blob differs")
    return subprocess.check_output(prefix + ["show", commit + ":" + path], cwd=root)
