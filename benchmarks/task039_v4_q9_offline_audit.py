"""Research-only ownership/storage/lifetime audit for a selected-mode packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

ARRAY_NAMES = ("positive_right", "positive_left", "negative_right", "negative_left")
TRACE_ENTRIES = {
    "positive_right_trace": 480,
    "positive_left_trace": 480,
    "negative_right_raw": 480,
    "negative_right_canonical": 480,
    "negative_left_trace": 0,
}


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _resource(path: Path | None) -> dict[str, Any]:
    result = {"source": str(path) if path else None}
    names = {
        "rss": "process_tree_peak_rss_mb",
        "swap": "process_tree_peak_swap_mb",
        "pss": "peak_pss_mb",
        "uss": "peak_uss_mb",
    }
    if path is None:
        return {
            **result,
            **{name: {"status": "not_measured", "value": None} for name in names},
        }
    authority = _json(path).get("resource_authority")
    if not isinstance(authority, Mapping):
        raise ValueError(f"resource_authority is missing: {path}")
    status = authority.get("telemetry_status")
    for name, field in names.items():
        if field not in authority:
            raise ValueError(f"resource field is missing: {field}")
        value = authority[field]
        if value is None:
            if name not in {"pss", "uss"} or status != "not_measured":
                raise ValueError(
                    f"null resource field without not_measured status: {field}"
                )
            result[name] = {"status": "not_measured", "value": None}
        elif not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError(f"resource field is not finite: {field}")
        else:
            result[name] = {"status": "measured", "value": float(value), "unit": "MiB"}
    result["telemetry_status"] = status
    return result


def _worker(
    path: Path | None, required: tuple[str, ...]
) -> tuple[dict[str, Any] | None, Path | None]:
    if path is None:
        return None, None
    if not path.exists():
        return None, path
    data = _json(path)
    if not all(key in data for key in required):
        raise ValueError(f"worker evidence schema mismatch: {path}")
    return data, path


def _counts(path: Path | None) -> dict[str, Any]:
    data, actual = _worker(path, ("producer_qep", "selection"))
    if data is None:
        return {"status": "not_measured", "source": str(actual) if actual else None}
    fields = (
        "requested_modes",
        "converged_modes",
        "iteration_count",
        "convergence_reason",
    )
    qep = {
        branch: {key: data["producer_qep"][branch].get(key) for key in fields}
        for branch in ("positive", "negative")
    }
    selection = {
        branch: {
            key: data["selection"][branch].get(key)
            for key in ("candidate_modes", "selected_modes")
        }
        for branch in ("positive", "negative")
    }
    return {
        "status": "measured",
        "source": str(actual),
        "worker_status": data.get("status"),
        "producer_qep": qep,
        "selection": selection,
        "packet_write": data.get("packet_write", {}),
        "consumer_qep_required": data.get("consumer_qep_required"),
    }


def _telemetry(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "not_measured", "source": None, "entries": []}
    keys = (
        "replicated_numpy_array_bytes_per_rank",
        "replicated_numpy_array_bytes_process_tree",
        "distributed_petsc_5mat_payload_lower_bound_bytes",
    )
    entries = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        detail = row.get("detail", row)
        if any(key in detail for key in keys):
            entries.append(
                {
                    "marker": row.get("name", row.get("stage")),
                    "provenance": "derived",
                    "classification": detail.get(
                        "classification", "derived_buffer_accounting"
                    ),
                    "values": {key: detail[key] for key in keys if key in detail},
                    "formula": detail.get("replicated_array_formula"),
                }
            )
    return {"status": "derived", "source": str(path), "entries": entries}


def _input(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "sha256": None, "status": "not_provided"}
    if not path.exists():
        return {"path": str(path), "sha256": None, "status": "missing"}
    return {"path": str(path), "sha256": _sha256(path), "status": "present"}


def _packet(manifest_path: Path) -> dict[str, Any]:
    manifest = _json(manifest_path)
    root = manifest_path.parent.resolve()
    rank_count, mode_count, global_size = (
        int(manifest[key]) for key in ("rank_count", "mode_count", "global_size")
    )
    shards = sorted(manifest["shards"], key=lambda row: int(row["rank"]))
    if min(rank_count, mode_count, global_size) <= 0 or len(shards) != rank_count:
        raise ValueError("invalid packet dimensions")
    previous, validated, per_rank = 0, 0, []
    for expected_rank, shard in enumerate(shards):
        rank = int(shard["rank"])
        start, end = (int(value) for value in shard["ownership_range"])
        if rank != expected_rank or start != previous or end <= start:
            raise ValueError("packet ownership is not rank-contiguous")
        rows = end - start
        files = shard.get("files")
        if not isinstance(files, Mapping) or set(files) != set(ARRAY_NAMES):
            raise ValueError("packet shard file set mismatch")
        rank_bytes = 0
        for name in ARRAY_NAMES:
            descriptor = files[name]
            shape = [mode_count, rows]
            if (
                descriptor.get("layout") != "mode_major"
                or descriptor.get("dtype") != "complex128"
                or list(descriptor.get("shape", ())) != shape
            ):
                raise ValueError(f"packet descriptor mismatch: {name}")
            path = (root / str(descriptor["path"])).resolve()
            try:
                path.relative_to(root)
            except ValueError as error:
                raise ValueError("packet shard escapes manifest directory") from error
            actual_bytes = path.stat().st_size
            expected_bytes = descriptor.get("bytes", descriptor.get("size_bytes"))
            if expected_bytes is not None and int(expected_bytes) != actual_bytes:
                raise ValueError(f"packet file size mismatch: {name}")
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            if array.dtype != np.dtype("complex128") or list(array.shape) != shape:
                raise ValueError(f"packet file shape/dtype mismatch: {name}")
            if _sha256(path) != descriptor["sha256"]:
                raise ValueError(f"packet shard hash mismatch: {name}")
            rank_bytes += actual_bytes
            validated += 1
        per_rank.append(
            {
                "rank": rank,
                "ownership_range": [start, end],
                "rows": rows,
                "four_array_bytes": rank_bytes,
            }
        )
        previous = end
    if previous != global_size:
        raise ValueError("packet ownership does not cover global_size")
    npy_bytes = sum(row["four_array_bytes"] for row in per_rank)
    identity = root / "identity.json"
    return {
        "schema": manifest.get("schema"),
        "scope": manifest.get("scope"),
        "mode_count": mode_count,
        "rank_count": rank_count,
        "global_size": global_size,
        "identity_sha256": manifest.get("identity_sha256"),
        "manifest_sha256": _sha256(manifest_path),
        "qep_workspace_persisted": manifest.get("qep_workspace_persisted"),
        "consumer_qep_required": manifest.get("consumer_qep_required"),
        "array_names": list(ARRAY_NAMES),
        "validated_file_count": validated,
        "ownership": per_rank,
        "npy_total_bytes": npy_bytes,
        "total_persisted_bytes": manifest_path.stat().st_size
        + (identity.stat().st_size if identity.exists() else 0)
        + npy_bytes,
        "owner_only_already_implemented": True,
        "owner_only_basis": "source_contract_and_rank_shard_validation",
    }


def _lifetime(
    direct_path: Path | None, iterative_path: Path | None, source_sha: str | None
) -> dict[str, Any]:
    direct, direct_actual = _worker(
        direct_path, ("selected_mode_packet_consumer", "object_payload_ledger")
    )
    iterative, iterative_actual = _worker(
        iterative_path, ("selected_mode_packet_consumer",)
    )
    packet = direct.get("selected_mode_packet_consumer", {}) if direct else {}
    ledger = direct.get("object_payload_ledger", {}) if direct else {}
    released = packet.get("modes_released_before_factor", {})
    source = {
        "status": "source_contract",
        "source_sha": source_sha,
        "source": "ModalTraceProjection/build_hybrid_internal_mode_coupling",
    }
    return {
        "trace_copies": {
            **source,
            "entries": {
                name: {
                    "count": count,
                    "status": "source_contract",
                    **({"note": "not_materialized"} if count == 0 else {}),
                }
                for name, count in TRACE_ENTRIES.items()
            },
        },
        "direct_packet_release": {
            "status": "measured" if direct else "not_measured",
            "source": str(direct_actual) if direct_actual else None,
            "first_bundle_destroyed": released.get("packet_bundle_destroyed"),
            "vector_count_after_destroy": released.get("vector_count_after_destroy"),
            "modal_bases_detached": released.get("modal_bases_detached"),
            "factor_modes_overlap": released.get("factor_modes_overlap"),
            "post_factor_rehydrate": bool(packet.get("post_factor_rehydrate")),
            "retained_right_left_eigenvector_bytes": ledger.get(
                "retained_right_left_eigenvector_bytes"
            ),
        },
        "iterative_full_basis_lifetime": {
            "status": "not_measured",
            "source": str(iterative_actual)
            if iterative_actual
            else str(iterative_path)
            if iterative_path
            else None,
            "value": None,
            "reason": "formal iterative record has no trusted resident full-basis byte/lifetime field",
        },
    }


def audit_q_a(
    *,
    manifest_path: Path,
    mode_prep_summary_path: Path | None,
    mode_prep_worker_summary_path: Path | None,
    direct_summary_path: Path | None,
    direct_worker_summary_path: Path | None,
    iterative_summary_path: Path | None,
    iterative_worker_summary_path: Path | None,
    direct_telemetry_path: Path | None,
    iterative_telemetry_path: Path | None,
    output_path: Path,
    audit_source_sha: str | None = None,
    git_clean: bool | None = None,
) -> dict[str, Any]:
    summary_paths = {
        "mode_prep": Path(mode_prep_summary_path) if mode_prep_summary_path else None,
        "direct": Path(direct_summary_path) if direct_summary_path else None,
        "iterative": Path(iterative_summary_path) if iterative_summary_path else None,
    }
    input_paths = {
        "manifest": Path(manifest_path),
        "mode_prep_summary": summary_paths["mode_prep"],
        "mode_prep_worker_summary": mode_prep_worker_summary_path,
        "direct_summary": summary_paths["direct"],
        "direct_worker_summary": direct_worker_summary_path,
        "iterative_summary": summary_paths["iterative"],
        "iterative_worker_summary": iterative_worker_summary_path,
        "direct_telemetry": direct_telemetry_path,
        "iterative_telemetry": iterative_telemetry_path,
    }
    result = {
        "schema": "task039.v4-9-q-a-offline-audit.v1",
        "scope": "q_a_only",
        "status": "pass_with_not_measured_fields",
        "provenance": {"audit_source_sha": audit_source_sha, "git_clean": git_clean},
        "inputs": {name: _input(path) for name, path in input_paths.items()},
        "packet": _packet(Path(manifest_path)),
        "resources": {
            f"{name}_process_tree": _resource(path)
            for name, path in summary_paths.items()
        },
        "mode_prep": _counts(mode_prep_worker_summary_path),
        "derived_buffer_accounting": {
            "provenance": "derived",
            "not_rss": True,
            "direct": _telemetry(direct_telemetry_path),
            "iterative": _telemetry(iterative_telemetry_path),
        },
        "lifetime": _lifetime(
            direct_worker_summary_path, iterative_worker_summary_path, audit_source_sha
        ),
        "remaining_replication_direction": {
            "status": "source_contract",
            "description": "dense lift/projection and coupling-side buffers remain replicated derived arrays; persisted selected modes are owner-row distributed",
        },
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "mode_prep_summary",
        "mode_prep_worker_summary",
        "direct_summary",
        "direct_worker_summary",
        "iterative_summary",
        "iterative_worker_summary",
        "direct_telemetry",
        "iterative_telemetry",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path)
    parser.add_argument("--audit-source-sha")
    parser.add_argument("--git-clean", action="store_true")
    args = parser.parse_args()
    audit_q_a(
        manifest_path=args.manifest,
        mode_prep_summary_path=args.mode_prep_summary,
        mode_prep_worker_summary_path=args.mode_prep_worker_summary,
        direct_summary_path=args.direct_summary,
        direct_worker_summary_path=args.direct_worker_summary,
        iterative_summary_path=args.iterative_summary,
        iterative_worker_summary_path=args.iterative_worker_summary,
        direct_telemetry_path=args.direct_telemetry,
        iterative_telemetry_path=args.iterative_telemetry,
        output_path=args.output,
        audit_source_sha=args.audit_source_sha,
        git_clean=args.git_clean,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
