"""Preserve V40 disposable synthetic fixtures losslessly, freeing test space.

Only the current batch's pytest basetemp is touched. Formal scientific packets,
old batches, logs, failed test receipts and sources remain at their paths.
"""

import gzip
import hashlib
import os
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_recovery_scope import window


def digest(path, *, zipped=False):
    h = hashlib.sha256()
    with gzip.open(path, "rb") if zipped else path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main():
    window.guard_worker_parent()
    out = Path(os.environ["TASK042_V36_AUX_DIRECTORY"])
    rows = []
    for folder in sorted(window.TMP.glob("aux_pre_*/fixtures")):
        for path in sorted(
            p for p in folder.rglob("*") if p.is_file() and not p.name.endswith(".gz")
        ):
            archive = path.with_name(path.name + ".gz")
            if archive.exists():
                raise FileExistsError("fixture archive collision")
            h = digest(path)
            raw_bytes = path.stat().st_size
            with path.open("rb") as source, archive.open("xb") as target:
                with gzip.GzipFile(
                    filename="", mode="wb", fileobj=target, compresslevel=1, mtime=0
                ) as stream:
                    while chunk := source.read(1 << 20):
                        stream.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if digest(archive, zipped=True) != h:
                raise ValueError("lossless fixture archive hash mismatch")
            rows.append(
                {
                    "original_path": str(path),
                    "sha256": h,
                    "bytes": raw_bytes,
                    "archive_path": str(archive),
                    "archive_sha256": digest(archive),
                    "archive_bytes": archive.stat().st_size,
                }
            )
            write_json(
                out / "fixture_archives.json",
                {"scope": "V40 synthetic pytest basetemp only", "files": rows},
            )
            path.unlink()
    print(
        {
            "preserved": len(rows),
            "raw_bytes": sum(r["bytes"] for r in rows),
            "archive_bytes": sum(r["archive_bytes"] for r in rows),
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
