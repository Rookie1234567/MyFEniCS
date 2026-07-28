"""Read-only launch gate for Task035d coarse nested-p snapshot shards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np


_SHARD_SCHEMA = "task035d.variable-p-nested-coarse-shard.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def task035d_coarse_snapshot_artifact_gate(
    manifest_path: str | Path,
    manifest: Mapping[str, Any],
    *,
    expected_mpi_size: int = 8,
    expected_cell_count: int = 134,
) -> dict[str, Any]:
    """Validate every shard before launching the enriched heavy PDE."""

    path = Path(manifest_path).resolve()
    failures: list[str] = []
    shard_rows = manifest.get("shards")
    if not isinstance(shard_rows, list):
        shard_rows = []
        failures.append("shards_not_a_list")
    observed_ranks: list[int] = []
    ownership_ranges: list[tuple[int, int]] = []
    canonical_leaves: list[int] = []
    shard_reports: list[dict[str, Any]] = []
    for index, raw in enumerate(shard_rows):
        report: dict[str, Any] = {
            "manifest_index": index,
            "pass": False,
        }
        try:
            if not isinstance(raw, dict):
                raise ValueError("shard metadata is not an object")
            rank = int(raw["rank"])
            name = raw["path"]
            if (
                not isinstance(name, str)
                or Path(name).is_absolute()
                or Path(name).name != name
            ):
                raise ValueError("shard path is not a safe basename")
            shard_path = (path.parent / name).resolve()
            if shard_path.parent != path.parent:
                raise ValueError("shard escapes the manifest directory")
            if not shard_path.is_file():
                raise FileNotFoundError(f"missing shard {name}")
            observed_sha = _sha256(shard_path)
            if observed_sha != raw.get("sha256"):
                raise ValueError("shard SHA256 mismatch")
            if (
                isinstance(raw.get("bytes"), int)
                and int(raw["bytes"]) != shard_path.stat().st_size
            ):
                raise ValueError("shard byte count mismatch")
            with np.load(shard_path, allow_pickle=False) as archive:
                required = {
                    "schema_version",
                    "rank",
                    "mpi_size",
                    "ownership_range",
                    "state_b_owned",
                    "rhs_b_owned",
                    "matrix_action_b_on_b_owned",
                    "residual_b_owned",
                    "canonical_leaves",
                }
                if not required.issubset(archive.files):
                    raise ValueError("shard header fields are incomplete")
                if str(archive["schema_version"][0]) != _SHARD_SCHEMA:
                    raise ValueError("shard schema mismatch")
                if int(archive["rank"][0]) != rank:
                    raise ValueError("shard rank mismatch")
                if int(archive["mpi_size"][0]) != expected_mpi_size:
                    raise ValueError("shard MPI size mismatch")
                ownership = tuple(
                    map(int, np.asarray(archive["ownership_range"]))
                )
                if (
                    len(ownership) != 2
                    or ownership[0] < 0
                    or ownership[1] < ownership[0]
                    or list(ownership)
                    != list(raw.get("ownership_range", ()))
                ):
                    raise ValueError("shard ownership range is invalid")
                owned_count = ownership[1] - ownership[0]
                for key in (
                    "state_b_owned",
                    "rhs_b_owned",
                    "matrix_action_b_on_b_owned",
                    "residual_b_owned",
                ):
                    if np.asarray(archive[key]).shape != (owned_count,):
                        raise ValueError(
                            f"shard owned vector length mismatch: {key}"
                        )
                leaves = list(
                    map(
                        int,
                        np.asarray(archive["canonical_leaves"]),
                    )
                )
            if leaves != list(map(int, raw.get("canonical_leaves", ()))):
                raise ValueError("shard canonical leaves mismatch")
            if (
                isinstance(raw.get("owned_value_count"), int)
                and int(raw["owned_value_count"]) != owned_count
            ):
                raise ValueError("shard owned value count mismatch")
            if (
                isinstance(raw.get("owned_cell_count"), int)
                and int(raw["owned_cell_count"]) != len(leaves)
            ):
                raise ValueError("shard owned cell count mismatch")
            observed_ranks.append(rank)
            ownership_ranges.append(ownership)
            canonical_leaves.extend(leaves)
            report.update(
                {
                    "pass": True,
                    "rank": rank,
                    "path": name,
                    "sha256": observed_sha,
                    "ownership_range": list(ownership),
                    "owned_cell_count": len(leaves),
                }
            )
        except Exception as exc:
            failures.append(
                f"shard_{index}:{type(exc).__name__}:{exc}"
            )
            report["error"] = f"{type(exc).__name__}: {exc}"
        shard_reports.append(report)

    ordered = sorted(
        zip(observed_ranks, ownership_ranges, strict=True),
        key=lambda row: row[0],
    )
    ranks_pass = [rank for rank, _ in ordered] == list(
        range(expected_mpi_size)
    )
    if not ranks_pass:
        failures.append("shard_rank_coverage")
    ordered_ranges = [values for _, values in ordered]
    cursor = 0
    ownership_pass = len(ordered_ranges) == expected_mpi_size
    for start, end in ordered_ranges:
        ownership_pass = ownership_pass and start == cursor
        cursor = end
    expected_global_size = manifest.get("vector_identity", {}).get(
        "global_size"
    )
    ownership_pass = bool(
        ownership_pass
        and isinstance(expected_global_size, int)
        and cursor == expected_global_size
        and [
            list(values) for values in ordered_ranges
        ]
        == manifest.get("same_trace_identity", {}).get(
            "matrix_vector_ownership_ranges"
        )
    )
    if not ownership_pass:
        failures.append("shard_ownership_closure")
    leaf_pass = sorted(canonical_leaves) == list(
        range(expected_cell_count)
    )
    if not leaf_pass:
        failures.append("canonical_leaf_coverage")
    checks = {
        "shard_count": len(shard_rows) == expected_mpi_size,
        "all_shards_valid": (
            len(shard_reports) == expected_mpi_size
            and all(report["pass"] for report in shard_reports)
        ),
        "rank_coverage": ranks_pass,
        "ownership_closure": ownership_pass,
        "canonical_leaf_coverage": leaf_pass,
    }
    return {
        "schema_version": "task035d.coarse-snapshot-artifact-gate.v1",
        "pass": not failures and all(checks.values()),
        "checks": checks,
        "failures": failures,
        "manifest_path": str(path),
        "expected_mpi_size": expected_mpi_size,
        "expected_cell_count": expected_cell_count,
        "shards": shard_reports,
    }


__all__ = ["task035d_coarse_snapshot_artifact_gate"]
