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


def archive(cache, destination):
    cache = Path(cache).resolve()
    destination = Path(destination).resolve()
    root = Path("/home/fenics/Projects/NN-Lab/tmp/task042/v37").resolve()
    if not cache.is_relative_to(root) or not destination.is_relative_to(root):
        raise ValueError("V37-only generated cache cleanup")
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    began = perf_counter()
    for path in sorted(cache.iterdir()):
        if (
            path.suffix not in (".c", ".o", ".so")
            or not path.is_file()
            or path.is_symlink()
        ):
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
