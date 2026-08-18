"""Research-only feasibility audit for fixed low-M Q-D candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

M_EFF = (240, 320, 400)
ARRAY_NAMES = ("positive_right", "positive_left", "negative_right", "negative_left")
NOT_ESTABLISHED_GATES = {
    "reduced_linear_residual": "numeric reduced operator and RHS are not persisted",
    "reduced_R_T_A_A_volume": "no reduced solve or reduced field reconstruction was run",
    "reduced_selected_E_H": "selected E/H authority is solution-specific M480 output",
    "reduced_normal_flux_power_channels": "no reduced port projection/channel map is persisted",
    "reduced_interface_residual": "no reduced trace/traction action is persisted",
    "reduced_resource_reduction": "no M_eff process-tree RSS measurement exists",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _git_provenance() -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], text=True
    )
    return {"source_head": head, "git_clean": not status}


def _check_branch(manifest: Mapping[str, Any], mode: str) -> dict[str, Any]:
    selection = manifest["selection"][mode]
    if len(selection["beta"]) != manifest["mode_count"]:
        raise ValueError(f"{mode} beta count does not match mode_count")
    if len(selection["mode_keys"]) != manifest["mode_count"]:
        raise ValueError(f"{mode} mode metadata count does not match mode_count")
    if len(selection["groups"]) != manifest["mode_count"]:
        raise ValueError(f"{mode} group count does not match mode_count")
    if not all(selection["passive_branch_valid"]):
        raise ValueError(f"{mode} contains an invalid passive branch")
    kinds = Counter(item["kind"] for item in selection["mode_keys"])
    directions = Counter(item["direction"] for item in selection["mode_keys"])
    beta_imag = [abs(float(beta[1])) for beta in selection["beta"]]
    middle_length = manifest["_direct_middle_length_nm"]
    full_counts = Counter(selection["groups"])
    nested = True
    boundaries = {}
    for current, size in enumerate(M_EFF):
        prefix = selection["groups"][:size]
        prefix_counts = Counter(prefix)
        partial = sorted(
            group
            for group, count in prefix_counts.items()
            if count != full_counts[group]
        )
        boundaries[str(size)] = {
            "indices": [0, size],
            "group_complete": not partial,
            "partial_group_ids": partial,
            "prefix_group_count": len(prefix_counts),
        }
        if current and size <= M_EFF[current - 1]:
            nested = False
    return {
        "mode_count": len(selection["beta"]),
        "direction": directions,
        "sign": selection["sign"],
        "kind_counts": kinds,
        "all_selected_labeled_lossy_propagating": (
            len(kinds) == 1 and next(iter(kinds)) == "lossy_propagating"
        ),
        "all_passive_branch_valid": True,
        "group_count": len(full_counts),
        "group_boundaries": boundaries,
        "nested_prefixes": nested,
        "beta_abs_imag_range": [min(beta_imag), max(beta_imag)],
        "decay_exponent_range_at_middle_length_nm": [
            min(beta_imag) * middle_length,
            max(beta_imag) * middle_length,
        ],
        "weak_decay_eta": {"status": "not_selected", "value": None},
    }


def _storage_proxy(manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    filesystem_bytes = 0
    array_payload_bytes = 0
    rows = 0
    files = 0
    for shard in manifest["shards"]:
        start, end = shard["ownership_range"]
        if end - start != shard["rows"]:
            raise ValueError("ownership rows do not match shard descriptor")
        rows += shard["rows"]
        for name in ARRAY_NAMES:
            descriptor = shard["files"][name]
            if descriptor["shape"] != [manifest["mode_count"], shard["rows"]]:
                raise ValueError(f"{name} shape is not mode-major owner-row storage")
            if (
                descriptor["dtype"] != "complex128"
                or descriptor["layout"] != "mode_major"
            ):
                raise ValueError(
                    f"{name} storage descriptor is not complex128 mode-major"
                )
            path = root / descriptor["path"]
            if not path.is_file():
                raise FileNotFoundError(path)
            filesystem_bytes += path.stat().st_size
            array_payload_bytes += descriptor["shape"][0] * descriptor["shape"][1] * 16
            files += 1
    if rows != manifest["global_size"] or files != 32:
        raise ValueError(
            "packet shard ownership or file count is not the M480 authority"
        )
    return {
        "full_mode_count": manifest["mode_count"],
        "array_file_count": files,
        "filesystem_bytes_stat": filesystem_bytes,
        "array_payload_bytes": array_payload_bytes,
        "status": "derived_not_rss",
        "formula": (
            "filesystem bytes include fixed .npy headers; only shape*complex128 itemsize "
            "array payload bytes are scaled linearly by M_eff / 480; not RSS"
        ),
        "M_eff": {
            str(size): {
                "linear_scaled_array_payload_bytes": round(
                    array_payload_bytes * size / manifest["mode_count"]
                ),
                "status": "derived_not_rss",
            }
            for size in M_EFF
        },
    }


def audit_qd(
    manifest_path: Path, identity_path: Path, direct_summary_path: Path
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    identity = json.loads(identity_path.read_text())
    direct = json.loads(direct_summary_path.read_text())
    if manifest["identity"] != identity or manifest[
        "identity_sha256"
    ] != _canonical_sha256(identity):
        raise ValueError("packet identity does not match manifest authority")
    if manifest["mode_count"] != 480 or manifest["rank_count"] != 8:
        raise ValueError("Q-D requires the fixed M480/MPI8 authority")
    direct_case = direct["case"]
    manifest["_direct_middle_length_nm"] = direct_case["middle_length_nm"]
    branches = {
        mode: _check_branch(manifest, mode) for mode in ("positive", "negative")
    }
    payload = direct["physical_field_reconstruction"]["task039_direct_payload"]
    ledger = direct["object_payload_ledger"]
    missing = dict(NOT_ESTABLISHED_GATES)
    gates = {
        name: {"status": "NOT_ESTABLISHED", "pass": None, "reason": reason}
        for name, reason in missing.items()
    }
    provenance = _git_provenance()
    return {
        "schema": "task039.v4-9-q-d-feasibility-audit.v1",
        "classification": "Q_D_FEASIBILITY_NOT_ESTABLISHED",
        "provenance": {
            "source_head": provenance["source_head"],
            "git_clean": provenance["git_clean"],
            "audit_path": "benchmarks/task039_v4_q9_qd_feasibility_audit.py",
        },
        "inputs": {
            "manifest": {"path": str(manifest_path), "sha256": _sha256(manifest_path)},
            "identity": {"path": str(identity_path), "sha256": _sha256(identity_path)},
            "direct_summary": {
                "path": str(direct_summary_path),
                "sha256": _sha256(direct_summary_path),
            },
        },
        "authority": {
            "scope": manifest["scope"],
            "mode_count": manifest["mode_count"],
            "rank_count": manifest["rank_count"],
            "global_size": manifest["global_size"],
            "external_keys": manifest["identity"]["external_keys"],
            "branches": branches,
            "qep_workspace_persisted": manifest["qep_workspace_persisted"],
            "direct_payload_inventory": {
                "path": payload["path"],
                "sha256": payload["sha256"],
                "keys": payload["keys"],
                "arrays": payload["arrays"],
            },
            "reduced_vectors": ledger["reduced_vectors"],
            "qep_workspace_bytes": ledger["qep_workspace_bytes"],
        },
        "storage_capacity_proxy": _storage_proxy(manifest, manifest_path.parent),
        "missing_authority": missing,
        "gates": gates,
        "limits": {
            "M_eff": list(M_EFF),
            "eta": {"status": "not_selected", "value": None},
            "proxy_is_not_rss": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-manifest", type=Path, required=True)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--direct-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_qd(
        args.packet_manifest.resolve(),
        args.identity_json.resolve(),
        args.direct_summary.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
