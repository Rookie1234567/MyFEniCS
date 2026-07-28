#!/usr/bin/env python3
"""Create one immutable, reference-blind Task035e initial-space bundle."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from src.adaptivity.task035e_initial_space import (
    Task035eInitialSpacePlan,
    build_task035e_initial_space_plan,
)
from src.common.config_3d import target_stage4_config


_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_PATH_H_NM = {"A": 20.0, "B": 15.0}
_RECEIPT_SCHEMA = "task035e.blind-initial-space-write-receipt.v1"


@dataclass(frozen=True, slots=True)
class InitialSpaceWriteReceipt:
    """Non-physical receipt for an immutable plan and its authority."""

    path_id: str
    source_sha: str
    plan_path: Path
    plan_sha256: str
    authority_path: Path
    authority_sha256: str


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_mode_0600(path: Path, payload: bytes) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return _sha256_bytes(payload)


def write_initial_space_bundle(
    *,
    path_id: str,
    source_sha: str,
    plan_path: Path,
    authority_path: Path,
    mpi_size: int = 8,
) -> InitialSpaceWriteReceipt:
    """Build and atomically publish one path-A/B initial space."""

    normalized_path = str(path_id).upper()
    if normalized_path not in _PATH_H_NM:
        raise ValueError("path_id must be A or B")
    if _SOURCE_SHA_RE.fullmatch(str(source_sha)) is None:
        raise ValueError("source_sha must be a 40-character lowercase Git SHA")
    if int(mpi_size) != 8:
        raise ValueError("formal Task035e initial spaces require MPI8")
    if plan_path.resolve() == authority_path.resolve():
        raise ValueError("plan and authority paths must differ")

    h_nm = _PATH_H_NM[normalized_path]
    plan: Task035eInitialSpacePlan = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=h_nm),
        path_id=normalized_path,
        source_sha=source_sha,
        comm_size=8,
    )
    plan_payload = plan.plan_payload()
    plan_bytes = _canonical_bytes(plan_payload)
    canonical_plan_sha256 = hashlib.sha256(
        json.dumps(
            plan_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    if canonical_plan_sha256 != plan.audit["plan_payload_sha256"]:
        raise RuntimeError("initial-space plan identity drifted before writing")

    authority_payload = {
        **dict(plan.audit),
        "plan_file_sha256": _sha256_bytes(plan_bytes),
        "plan_content_sha256": canonical_plan_sha256,
        "formal_mpi_size": 8,
        "nominal_h_nm": h_nm,
    }
    authority_bytes = _canonical_bytes(authority_payload)
    plan_file_sha256 = _atomic_mode_0600(plan_path, plan_bytes)
    try:
        authority_file_sha256 = _atomic_mode_0600(
            authority_path,
            authority_bytes,
        )
    except BaseException:
        # The plan is immutable evidence once published.  A partial bundle is
        # kept rather than silently deleting evidence; the caller can use a
        # fresh destination after recording the failed publication.
        raise
    return InitialSpaceWriteReceipt(
        path_id=normalized_path,
        source_sha=source_sha,
        plan_path=plan_path,
        plan_sha256=plan_file_sha256,
        authority_path=authority_path,
        authority_sha256=authority_file_sha256,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path-id", choices=("A", "B"), required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--mpi-size", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = write_initial_space_bundle(
            path_id=args.path_id,
            source_sha=args.verified_clean_sha,
            plan_path=args.plan,
            authority_path=args.authority,
            mpi_size=args.mpi_size,
        )
    except (FileExistsError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "schema_version": _RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": _RECEIPT_SCHEMA,
                "status": "completed",
                "path_id": receipt.path_id,
                "source_sha": receipt.source_sha,
                "plan_path": str(receipt.plan_path),
                "plan_sha256": receipt.plan_sha256,
                "authority_path": str(receipt.authority_path),
                "authority_sha256": receipt.authority_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "InitialSpaceWriteReceipt",
    "write_initial_space_bundle",
]
