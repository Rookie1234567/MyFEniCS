"""Losslessly archive only this task's generated JIT copies, then unlink.

Each member is re-read and hashed through gzip before its original is removed.
A failed write/check leaves the original. This is cleanup, not qualification.
"""

import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from time import perf_counter

from src.runners.task042_shared import write_json


def archive(
    cache,
    destination,
    *,
    namespace="v37",
    suffixes=(".c", ".o", ".so"),
    reuse_root=None,
):
    cache = Path(cache).resolve()
    destination = Path(destination).resolve()
    if namespace not in ("v37", "v38") or not set(suffixes) <= {".c", ".o", ".so"}:
        raise ValueError("explicit generated cache cleanup scope")
    root = Path("/home/fenics/Projects/NN-Lab/tmp/task042") / namespace
    root = root.resolve()
    if not cache.is_relative_to(root) or not destination.is_relative_to(root):
        raise ValueError("V37-only generated cache cleanup")
    destination.mkdir(parents=True, exist_ok=True)
    prior = {}
    if reuse_root is not None:
        base = Path(reuse_root).resolve()
        if not base.is_relative_to(root):
            raise ValueError("archive reuse scope")
        for manifest in base.glob("jit_archive_*/manifest.json"):
            for row in json.loads(manifest.read_text())["members"]:
                prior[row["original"]] = row
    records = []
    began = perf_counter()
    for path in sorted(cache.iterdir()):
        if path.suffix not in suffixes or not path.is_file() or path.is_symlink():
            continue
        old = prior.get(str(path))
        if (
            old is not None
            and path.stat().st_size == old["bytes"]
            and hashlib.sha256(path.read_bytes()).hexdigest() == old["sha256"]
        ):
            h = hashlib.sha256()
            n = 0
            with gzip.open(old["archive"], "rb") as stream:
                while block := stream.read(2**20):
                    h.update(block)
                    n += len(block)
            if n != old["bytes"] or h.hexdigest() != old["sha256"]:
                raise ValueError("archived raw identity")
            records.append(dict(old, reused_immutable_archive=True))
            write_json(
                destination / "manifest.json",
                {"members": records, "elapsed_seconds": perf_counter() - began},
            )
            path.unlink()
            continue
        output = destination / (path.name + ".gz")
        temporary = output.with_suffix(".gz.partial")
        before = hashlib.sha256()
        size = 0
        with (
            path.open("rb") as original,
            gzip.open(temporary, "wb", compresslevel=1) as compressed,
        ):
            while block := original.read(2**20):
                before.update(block)
                size += len(block)
                compressed.write(block)
        after = hashlib.sha256()
        actual = 0
        with gzip.open(temporary, "rb") as check:
            while block := check.read(2**20):
                after.update(block)
                actual += len(block)
        if before.digest() != after.digest() or size != actual:
            raise ValueError("lossless JIT archive readback")
        os.replace(temporary, output)
        row = {
            "original": str(path),
            "archive": str(output),
            "sha256": before.hexdigest(),
            "bytes": size,
            "archive_bytes": output.stat().st_size,
            "lossless_readback": True,
        }
        records.append(row)
        write_json(
            destination / "manifest.json",
            {"members": records, "elapsed_seconds": perf_counter() - began},
        )
        path.unlink()
    return {"members": records, "elapsed_seconds": perf_counter() - began}


def restore_cached_sources(cache, archive_root, *, namespace="v38"):
    """FFCx uses source-file presence as its cache lock; restore exact bytes.

    No empty marker, library replacement or installed FFCx change is used.
    Restored generated copies may be reclaimed against the same archive later.
    """
    cache = Path(cache).resolve()
    base = Path(archive_root).resolve()
    allowed = Path("/home/fenics/Projects/NN-Lab/tmp/task042") / namespace
    if (
        namespace != "v38"
        or not cache.is_relative_to(allowed)
        or not base.is_relative_to(allowed)
    ):
        raise ValueError("cached source restore scope")
    sources = {}
    for file in base.glob("jit_archive_*/manifest.json"):
        for row in json.loads(file.read_text())["members"]:
            path = Path(row["original"])
            if path.suffix == ".c" and path.parent == cache:
                sources[str(path)] = row
    for name, row in sources.items():
        path = Path(name)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("existing generated source identity")
            continue
        temp = path.with_suffix(".restore.partial")
        h = hashlib.sha256()
        n = 0
        with gzip.open(row["archive"], "rb") as src, temp.open("wb") as dst:
            while block := src.read(2**20):
                dst.write(block)
                h.update(block)
                n += len(block)
        if n != row["bytes"] or h.hexdigest() != row["sha256"]:
            raise ValueError("restored raw source identity")
        os.replace(temp, path)
    return {
        "sources": len(sources),
        "raw_bytes": sum(r["bytes"] for r in sources.values()),
        "exact_byte_restore": True,
    }


if __name__ == "__main__":
    result = archive(sys.argv[1], sys.argv[2])
    print(
        json.dumps(
            {
                "files": len(result["members"]),
                "seconds": result["elapsed_seconds"],
                "compressed_bytes": sum(r["archive_bytes"] for r in result["members"]),
            }
        ),
        flush=True,
    )
