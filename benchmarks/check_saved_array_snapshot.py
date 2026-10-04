"""Read back a frozen primitive-array snapshot; no FE, solve or factor."""

import hashlib
import argparse
import json
import os
from pathlib import Path

from src.runners.frozen_source_snapshot import sha256


def verify_saved_snapshot(report, raw_directory):
    import numpy as np

    raw = Path(raw_directory).resolve()
    snapshot = report.get("snapshot", {})
    members, roles = snapshot.get("members"), snapshot.get("roles")
    if not isinstance(members, list) or not members or not isinstance(roles, dict):
        raise ValueError("complete nonempty saved snapshot required")
    names = [m.get("name") for m in members]
    if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        raise ValueError("unique canonical member names required")
    by_name = dict(zip(names, members, strict=True))
    if any(not isinstance(v, dict) or v.get("name") not in by_name
           or v != by_name[v["name"]] for v in roles.values()):
        raise ValueError("logical role/member binding differs")
    if set(by_name) != {v["name"] for v in roles.values()}:
        raise ValueError("orphan saved member")
    if any(roles.get(n) != m for n, m in by_name.items()):
        raise ValueError("canonical member's original role is missing")
    expected = {hashlib.sha256(n.encode()).hexdigest() + ".npy" for n in names}
    actual = {p.name for p in raw.iterdir()}
    if expected != actual or any(p.is_symlink() or not p.is_file() for p in raw.iterdir()):
        raise ValueError("missing, extra or symlinked raw member")
    rows, numeric_bytes, file_bytes = [], 0, 0
    for member in members:
        path = raw / (hashlib.sha256(member["name"].encode()).hexdigest() + ".npy")
        if member.get("callback_reference") != str(path):
            raise ValueError("saved path is not the canonical raw member")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        try:
            if (list(array.shape) != member.get("shape") or str(array.dtype) != member.get("dtype")
                    or array.dtype.kind not in "biufc" or array.nbytes != member.get("numeric_bytes")
                    or path.stat().st_size != array.offset + array.nbytes):
                raise ValueError("saved shape/dtype/byte extent differs")
            digest = hashlib.sha256(repr((array.shape, str(array.dtype))).encode())
            iterator = (array,) if array.ndim < 2 else array
            for row in iterator:
                if not np.isfinite(row).all():
                    raise ValueError("nonfinite raw member")
                digest.update(row.tobytes(order="C"))
            if digest.hexdigest() != member.get("sha256"):
                raise ValueError("saved numeric digest differs")
            size = path.stat().st_size
            numeric_bytes += array.nbytes
            file_bytes += size
            rows.append({"name": member["name"], "file": path.name,
                         "numeric_sha256": digest.hexdigest(), "file_sha256": sha256(path),
                         "numeric_bytes": int(array.nbytes), "file_bytes": size})
        finally:
            array._mmap.close()
    if (snapshot.get("unique_member_count") != len(rows)
            or snapshot.get("numeric_bytes") != numeric_bytes
            or snapshot.get("archive_members_bytes_upper") != numeric_bytes + 4096 * len(rows)
            or snapshot["archive_members_bytes_upper"] > snapshot.get("archive_payload_limit_bytes", -1)):
        raise ValueError("saved count/byte budget differs")
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    descriptor = os.open(raw, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {"schema": "frozen-array-snapshot-readback.v1", "verified": True,
            "scope": "local filesystem directory fsync plus independent reopen and streamed payload/file digests",
            "cross_machine_storage_qualified": False, "power_failure_tested": False,
            "members": rows, "member_manifest_sha256": hashlib.sha256(encoded).hexdigest(),
            "unique_member_count": len(rows), "logical_role_count": len(roles),
            "numeric_bytes": numeric_bytes, "file_bytes": file_bytes,
            "new_FE_actions": 0, "new_factors": 0, "new_solves": 0}


def main(argv=None):
    from src.runners.fresh_component_receiver import atomic_json

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "report-sha256", "raw-directory", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    if sha256(args.report) != args.report_sha256:
        raise ValueError("frozen producer report digest changed")
    if Path(args.output).exists():
        raise ValueError("readback output already exists")
    result = verify_saved_snapshot(json.loads(Path(args.report).read_text()), args.raw_directory)
    result["producer_report_sha256"] = args.report_sha256
    atomic_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
