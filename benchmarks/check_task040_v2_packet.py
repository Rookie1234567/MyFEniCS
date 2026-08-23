"""Independent checker for the Task040 V2-A1 interface packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks import check_task040_v1_run_b as v1_checker
from src.solvers.hybrid_interface_packet import (
    canonical_key_set_sha256,
    canonical_key_sha256,
    load_small_matrix,
)

PACKET_SCHEMA = "task040.interface_schur_packet.v1"
EXPECTED_MPI_SIZE = 8
EXPECTED_MODAL_SPAN_SIZES = (296, 776, 480)
CONDITION_LIMIT = 1.0e12
COMPLEMENT_ORTHOGONALITY_LIMIT = 1.0e-8
PRODUCER_METHOD = "task040_v2_interface_packet_producer"

__all__ = ["check_v2_packet", "main"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _descriptor_mapping_sha256(descriptors: list[dict[str, Any]]) -> str:
    identities = []
    for descriptor in sorted(descriptors, key=lambda item: int(item["rank"])):
        identities.append(
            {
                "rank": int(descriptor["rank"]),
                "ownership_range": [
                    int(item) for item in descriptor["ownership_range"]
                ],
                "key_count": int(descriptor["key_count"]),
                "owner_key_set_sha256": descriptor["owner_key_set_sha256"],
            }
        )
    return hashlib.sha256(_canonical_json(identities).encode("utf-8")).hexdigest()


def _read_shard(
    root: Path, descriptor: dict[str, Any], expected_span: int
) -> tuple[tuple[str, ...], int]:
    path = root / descriptor["path"]
    if _sha256(path) != descriptor["sha256"]:
        raise ValueError(f"shard hash mismatch: {path.name}")
    with np.load(path, allow_pickle=False) as arrays:
        keys = tuple(str(item) for item in arrays["keys"].tolist())
        values_u = np.asarray(arrays["U"])
        values_v = np.asarray(arrays["V"])
        if values_u.dtype != np.dtype("complex128") or values_v.dtype != np.dtype(
            "complex128"
        ):
            raise ValueError(f"shard dtype mismatch: {path.name}")
        if values_u.ndim != 2 or values_v.shape != values_u.shape:
            raise ValueError(f"shard U/V shape mismatch: {path.name}")
        if values_u.shape[1] != int(expected_span):
            raise ValueError(f"shard modal span mismatch: {path.name}")
        if not np.isfinite(values_u).all() or not np.isfinite(values_v).all():
            raise ValueError(f"shard U/V is nonfinite: {path.name}")
        if (
            _array_sha256(values_u) != descriptor["u_sha256"]
            or _array_sha256(values_v) != descriptor["v_sha256"]
        ):
            raise ValueError(f"shard U/V hash mismatch: {path.name}")
        if list(values_u.shape) != list(descriptor["u_shape"]):
            raise ValueError(f"shard U shape metadata mismatch: {path.name}")
        if list(values_v.shape) != list(descriptor["v_shape"]):
            raise ValueError(f"shard V shape metadata mismatch: {path.name}")
    if len(keys) != int(descriptor["key_count"]):
        raise ValueError(f"shard key count mismatch: {path.name}")
    if canonical_key_sha256(keys) != descriptor["key_order_sha256"]:
        raise ValueError(f"shard key-order hash mismatch: {path.name}")
    if canonical_key_set_sha256(keys) != descriptor["owner_key_set_sha256"]:
        raise ValueError(f"shard owner-key-set hash mismatch: {path.name}")
    first, last = (int(item) for item in descriptor["ownership_range"])
    if first < 0 or last < first or last - first != len(keys):
        raise ValueError(f"shard ownership mismatch: {path.name}")
    return keys, len(keys)


def _small_matrix_checks(
    root: Path, manifest: dict[str, Any], expected_span_sizes: tuple[int, ...]
) -> dict[str, Any]:
    records = manifest.get("small_matrices")
    if not isinstance(records, dict):
        raise ValueError("packet has no small matrix records")
    matrix_names = manifest.get("diagnostics", {}).get("projected_matrix_names")
    if not isinstance(matrix_names, dict):
        raise ValueError("packet has no projected matrix name map")
    groups: list[dict[str, Any]] = []
    for group, expected_span in zip(
        manifest["group_order"], expected_span_sizes, strict=True
    ):
        names = matrix_names.get(group)
        if not isinstance(names, dict) or set(names) != {"gram", "scalar", "exact"}:
            raise ValueError(f"{group} projected matrix name map is incomplete")
        matrices = {}
        for name, filename in names.items():
            if not isinstance(filename, str) or filename not in records:
                raise ValueError(f"{group} projected matrix record is missing")
            matrices[name] = load_small_matrix(root, filename)
        gram = matrices["gram"]
        expected_shape = (int(expected_span), int(expected_span))
        if gram.shape != expected_shape or not np.isfinite(gram).all():
            raise ValueError(f"{group} Gram is invalid")
        singular_values = np.linalg.svd(gram, compute_uv=False)
        rank = int(np.linalg.matrix_rank(gram))
        condition = (
            float(singular_values[0] / singular_values[-1])
            if singular_values.size and singular_values[-1] > 0.0
            else float("inf")
        )
        if rank != gram.shape[0] or condition > CONDITION_LIMIT:
            raise ValueError(f"{group} Gram rank/condition Gate failed")
        if (
            matrices["scalar"].shape != expected_shape
            or matrices["exact"].shape != expected_shape
            or not np.isfinite(matrices["scalar"]).all()
            or not np.isfinite(matrices["exact"]).all()
        ):
            raise ValueError(f"{group} projected matrix shape mismatch")
        groups.append(
            {
                "group": group,
                "gram_shape": list(gram.shape),
                "projected_scalar_shape": list(matrices["scalar"].shape),
                "projected_exact_shape": list(matrices["exact"].shape),
                "gram_rank": rank,
                "gram_singular_values": [float(item) for item in singular_values],
                "gram_condition": condition,
            }
        )
    return {"groups": groups, "condition_limit": CONDITION_LIMIT}


def _pair(value: Any) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("probe contraction is not a complex pair")
    result = complex(float(value[0]), float(value[1]))
    if not np.isfinite(result.real) or not np.isfinite(result.imag):
        raise ValueError("probe contraction is nonfinite")
    return result


def _report_checks(diagnostics: dict[str, Any]) -> dict[str, Any]:
    physical = diagnostics.get("physical_probe_reports")
    interface = diagnostics.get("interface_probe_reports")
    middle = diagnostics.get("middle_cross_interface_sampled_response")
    if not isinstance(physical, list) or len(physical) != 15:
        raise ValueError("packet physical probe reports are incomplete")
    if not isinstance(interface, list) or len(interface) != 8:
        raise ValueError("packet interface probe reports are incomplete")
    if not isinstance(middle, list) or len(middle) != 8:
        raise ValueError("packet middle-cross reports are incomplete")
    complement_count = 0
    for report in physical:
        if not isinstance(report, dict):
            raise ValueError("packet physical report is malformed")
        for name in (
            "scalar_exact_relative",
            "projected_exact_relative",
            "scalar_norm",
            "exact_norm",
            "projected_norm",
        ):
            value = report.get(name)
            if not isinstance(value, (int, float)) or not np.isfinite(value):
                raise ValueError(f"packet physical report field {name} is invalid")
        contractions = report.get("contractions")
        if not isinstance(contractions, dict):
            raise ValueError("packet probe contractions are missing")
        for name in (
            "source_h_source",
            "scalar_h_scalar",
            "exact_h_exact",
            "scalar_h_exact",
            "projected_h_projected",
            "projected_h_exact",
        ):
            _pair(contractions[name])
    for report in interface:
        if not isinstance(report, dict) or report.get("finite") is not True:
            raise ValueError("packet interface report is not finite")
        contractions = report.get("contractions")
        if not isinstance(contractions, dict):
            raise ValueError("packet probe contractions are missing")
        for name in (
            "source_h_source",
            "scalar_h_scalar",
            "exact_h_exact",
            "scalar_h_exact",
            "projected_h_projected",
            "projected_h_exact",
        ):
            _pair(contractions[name])
        if report.get("kind") == "complement":
            complement_count += 1
            before = [_pair(item) for item in report["YH_before_projection"]]
            after = [_pair(item) for item in report["YH_after_projection"]]
            ratio = np.linalg.norm(after) / max(float(np.linalg.norm(before)), 1.0e-30)
            if not np.isfinite(ratio) or ratio > COMPLEMENT_ORTHOGONALITY_LIMIT:
                raise ValueError("packet complement projection Gate failed")
    if complement_count != 4:
        raise ValueError("packet complement probe inventory is incomplete")
    for report in middle:
        if not isinstance(report, dict) or report.get("finite") is not True:
            raise ValueError("packet middle-cross report is not finite")
        contractions = report.get("contractions")
        if not isinstance(contractions, dict):
            raise ValueError("packet middle-cross contractions are missing")
        middle_norm_squared = _pair(contractions["middle_h_middle"]).real
        if middle_norm_squared < 0.0:
            raise ValueError("packet middle contraction is negative")
        same = float(report["same_interface_norm"])
        cross = float(report["cross_interface_norm"])
        total = float(report["total_norm"])
        if not all(np.isfinite(item) and item >= 0.0 for item in (same, cross, total)):
            raise ValueError("packet middle-cross norm is invalid")
        if not np.isclose(
            total * total, same * same + cross * cross, atol=1.0e-8, rtol=1.0e-8
        ):
            raise ValueError("packet middle-cross partition is inconsistent")
        if not np.isclose(total * total, middle_norm_squared, atol=1.0e-8, rtol=1.0e-8):
            raise ValueError("packet middle-cross contraction does not match norm")
    return {
        "physical_count": len(physical),
        "interface_count": len(interface),
        "middle_cross_count": len(middle),
        "complement_count": complement_count,
        "complement_limit": COMPLEMENT_ORTHOGONALITY_LIMIT,
    }


def _raw_authority_checks(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Reuse the V1 raw arithmetic/identity contracts without worker status."""

    physical = diagnostics.get("physical_probe_reports")
    interface = diagnostics.get("interface_probe_reports")
    reported = diagnostics.get("probes")

    def probe_identity(item: Any) -> tuple[Any, ...]:
        return (
            item.get("label"),
            item.get("group"),
            item.get("kind"),
            item.get("interface"),
            item.get("seed"),
        )

    checks = {
        "manifest_identity": v1_checker._identity_check(diagnostics),
        "representation": v1_checker._representation_check(diagnostics),
        "probe_inventory": v1_checker._probe_inventory_check(diagnostics),
        "incoming_neighbor_map": v1_checker._incoming_neighbor_map_check(diagnostics),
        "middle_cross": v1_checker._middle_cross_interface_check(diagnostics),
        "report_inventory_consistent": (
            isinstance(physical, list)
            and isinstance(interface, list)
            and isinstance(reported, list)
            and len(reported) == len(physical) + len(interface)
            and len({probe_identity(item) for item in reported}) == len(reported)
            and {probe_identity(item) for item in reported}
            == {probe_identity(item) for item in [*physical, *interface]}
        ),
    }
    metrics = v1_checker._probe_metrics(diagnostics)
    checks["contractions"] = len(metrics) == 23 and all(
        np.isfinite(
            [
                item["source_norm_squared"],
                item["original_scalar_exact_relative"],
                item["projected_exact_relative"],
            ]
        ).all()
        and item["source_norm_squared"] > 0.0
        for item in metrics
    )
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ValueError(f"packet raw authority evidence failed: {failed}")
    return {
        "checks": checks,
        "probe_count": len(metrics),
        "max_projected_exact_relative": max(
            item["projected_exact_relative"] for item in metrics
        ),
    }


def _provenance_check(provenance: Any) -> bool:
    if not isinstance(provenance, dict):
        return False
    frozen = json.loads(v1_checker.PROBE_MANIFEST.read_text(encoding="utf-8"))[
        "identity"
    ]
    source = provenance.get("source_sha")
    if (
        not isinstance(source, str)
        or len(source) != 40
        or any(character not in "0123456789abcdef" for character in source)
    ):
        return False
    expected = {
        "schema": "task040.v2.interface_packet_producer.v1",
        "input_sha256": frozen["input_sha256"],
        "physical_model_sha256": frozen["physical_model_sha256"],
        "selected_manifest_sha256": frozen["selected_manifest_sha256"],
        "exact_spool_catalog_sha256": frozen["exact_spool_catalog_sha256"],
        "probe_manifest_sha256": v1_checker.FROZEN_PROBE_MANIFEST_SHA256,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }
    return all(provenance.get(key) == value for key, value in expected.items())


def _watchdog_check(
    summary_path: str | Path, provenance: dict[str, Any]
) -> dict[str, Any]:
    summary_file = Path(summary_path)
    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        worker_summary = summary_file.parent / "worker" / "run_summary.json"
        run_summary_sha = _sha256(worker_summary) if worker_summary.is_file() else None
        hard_stop = int(summary["hard_stop_bytes"])
        peak_rss = int(summary["peak_rss_bytes"])
        peak_swap = int(summary["peak_swap_bytes"])
        peak_cgroup_swap = int(summary["peak_dedicated_cgroup_swap_bytes"])
        preferred_memory = int(summary["preferred_memory_bytes"])
        pass_gate = bool(
            summary["method"] == PRODUCER_METHOD
            and summary["source_sha"] == provenance["source_sha"]
            and hard_stop == 55 * 2**30
            and preferred_memory == 45 * 2**30
            and summary["termination_reason"] == "natural_exit"
            and int(summary["return_code"]) == 0
            and summary["run_summary_present"] is True
            and worker_summary.is_file()
            and summary["run_summary_sha256"] == run_summary_sha
            and summary["all_status_readable"] is True
            and summary["swap_authority_readable"] is True
            and (
                summary.get("dedicated_cgroup_present") is not True
                or summary.get("dedicated_cgroup_swap_readable") is True
            )
            and peak_swap == 0
            and peak_cgroup_swap == 0
            and peak_rss < hard_stop
        )
        preferred_class = (
            "preferred_le_45_gib"
            if peak_rss <= 45 * 2**30
            else "bounded_45_to_55_gib"
            if peak_rss < hard_stop
            else "hard_stop_or_invalid"
        )
        return {
            "bound": True,
            "pass": pass_gate,
            "preferred_class": preferred_class,
            "hard_stop_bytes": hard_stop,
            "peak_rss_bytes": peak_rss,
            "peak_swap_bytes": peak_swap,
            "peak_dedicated_cgroup_swap_bytes": peak_cgroup_swap,
        }
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"bound": True, "pass": False, "reason": str(exc)}


def check_v2_packet(
    packet_root: str | Path,
    *,
    expected_provenance: dict[str, Any] | None = None,
    expected_group_counts: tuple[int, int, int] | None = None,
    expected_rank_count: int = EXPECTED_MPI_SIZE,
    expected_span_sizes: tuple[int, int, int] = EXPECTED_MODAL_SPAN_SIZES,
    watchdog_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute packet identity, shard coverage, matrix conditioning and probes."""

    root = Path(packet_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("interface packet manifest is missing")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (
        manifest.get("schema") != PACKET_SCHEMA
        or manifest.get("packet_complete") is not True
    ):
        raise ValueError("packet manifest is incomplete or has the wrong schema")
    group_order = manifest.get("group_order")
    groups = manifest.get("groups")
    if not isinstance(group_order, list) or group_order != [
        "group0",
        "group1",
        "group2",
    ]:
        raise ValueError("packet group order is not frozen")
    if not isinstance(groups, dict) or set(groups) != set(group_order):
        raise ValueError("packet groups do not match group order")
    if int(manifest.get("rank_count", -1)) != int(expected_rank_count):
        raise ValueError("packet MPI rank count is not frozen")
    if len(expected_span_sizes) != len(group_order):
        raise ValueError("packet modal span authority is incomplete")
    diagnostic_groups = manifest.get("diagnostics", {}).get("groups")
    if not isinstance(diagnostic_groups, list) or len(diagnostic_groups) != 3:
        raise ValueError("packet Gamma diagnostics are incomplete")
    if [item.get("group") for item in diagnostic_groups] != [0, 1, 2]:
        raise ValueError("packet Gamma diagnostics group order is invalid")
    if (
        manifest.get("basis_global_replicated") is not False
        or manifest.get("numeric_allgather") is not False
        or manifest.get("fe_numeric_allgather") is not False
    ):
        raise ValueError("packet violates owner-local numeric contract")
    provenance = manifest.get("provenance")
    provenance_pass = _provenance_check(provenance)
    if expected_provenance is not None and provenance != expected_provenance:
        provenance_pass = False
    if not provenance_pass:
        raise ValueError("packet provenance mismatch")
    all_group_results: list[dict[str, Any]] = []
    for index, group in enumerate(group_order):
        record = groups[group]
        descriptors = list(record.get("shards", []))
        if len(descriptors) != int(expected_rank_count):
            raise ValueError(f"{group} does not have one shard per rank")
        ranks = {int(item.get("rank", -1)) for item in descriptors}
        if ranks != set(range(int(expected_rank_count))):
            raise ValueError(
                f"{group} shard ranks are not 0..{expected_rank_count - 1}"
            )
        seen: set[str] = set()
        count = 0
        for descriptor in sorted(descriptors, key=lambda item: int(item["rank"])):
            keys, local_count = _read_shard(
                root, descriptor, int(expected_span_sizes[index])
            )
            if seen.intersection(keys):
                raise ValueError(f"{group} has duplicate canonical keys")
            seen.update(keys)
            count += local_count
        if count != int(record["global_count"]):
            raise ValueError(f"{group} global key count mismatch")
        gamma_layout = diagnostic_groups[index].get("gamma_layout")
        if (
            not isinstance(gamma_layout, dict)
            or int(gamma_layout.get("global_row_count", -1)) != count
        ):
            raise ValueError(f"{group} diagnostics Gamma count mismatch")
        if index in (0, 2) and int(gamma_layout.get("global_size", -1)) != count:
            raise ValueError(f"{group} diagnostics Gamma size mismatch")
        if expected_group_counts is not None and count != int(
            expected_group_counts[index]
        ):
            raise ValueError(f"{group} global key count differs from test authority")
        ranges = [
            tuple(int(value) for value in item["ownership_range"])
            for item in sorted(descriptors, key=lambda item: int(item["rank"]))
        ]
        if ranges[0][0] != 0 or ranges[-1][1] != count:
            raise ValueError(f"{group} ownership does not cover global rows")
        if any(
            end - start != int(descriptor["key_count"])
            for descriptor, (start, end) in zip(
                sorted(descriptors, key=lambda item: int(item["rank"])),
                ranges,
                strict=True,
            )
        ):
            raise ValueError(f"{group} ownership/key count mismatch")
        if any(left[1] != right[0] for left, right in zip(ranges, ranges[1:])):
            raise ValueError(f"{group} ownership ranges are not contiguous")
        mapping = _descriptor_mapping_sha256(descriptors)
        if mapping != record["row_key_to_owner_mapping_sha256"]:
            raise ValueError(f"{group} owner mapping hash mismatch")
        if record.get("global_key_bijection") != "requires_independent_checker":
            raise ValueError(f"{group} bijection authority is invalid")
        all_group_results.append(
            {
                "group": group,
                "global_count": count,
                "unique_key_count": len(seen),
                "mapping_sha256": mapping,
            }
        )
    if all_group_results[1]["global_count"] != (
        all_group_results[0]["global_count"] + all_group_results[2]["global_count"]
    ):
        raise ValueError("group1 global Gamma count is not lower plus upper")
    matrix_result = _small_matrix_checks(root, manifest, expected_span_sizes)
    report_result = _report_checks(manifest.get("diagnostics", {}))
    raw_authority = _raw_authority_checks(manifest.get("diagnostics", {}))
    lifecycle = manifest.get("diagnostics", {}).get("factor_lifecycle", {})
    lifecycle_pass = bool(
        lifecycle.get("factor_count_ready") == 3
        and lifecycle.get("factor_count_after_cleanup") == 0
        and lifecycle.get("simultaneous_factor_count_max") == 3
        and lifecycle.get("exact_oracle_ready", {}).get("dense_materialization")
        is False
        and lifecycle.get("exact_oracle_after_cleanup", {}).get("destroyed") is True
    )
    watchdog_result = (
        _watchdog_check(watchdog_summary_path, provenance)
        if watchdog_summary_path is not None
        else {
            "bound": False,
            "pass": False,
            "reason": "watchdog summary is required",
        }
    )
    checks = {
        "manifest": True,
        "provenance": provenance_pass,
        "groups": True,
        "small_matrices": True,
        "probe_reports": True,
        "factor_lifecycle": lifecycle_pass,
        "raw_evidence": all(raw_authority["checks"].values()),
        "watchdog": watchdog_result["pass"],
    }
    return {
        "schema": "task040.v2.interface_packet.recomputed.v1",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "groups": all_group_results,
        "small_matrices": matrix_result,
        "probe_reports": report_result,
        "raw_authority": raw_authority,
        "factor_lifecycle": lifecycle,
        "watchdog": watchdog_result,
        "checks": checks,
        "packet_complete": bool(all(checks.values())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--watchdog-summary")
    args = parser.parse_args(argv)
    result = check_v2_packet(
        args.packet_root, watchdog_summary_path=args.watchdog_summary
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["packet_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
