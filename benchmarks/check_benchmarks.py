from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "benchmarks"


@dataclass
class Gate:
    name: str
    passed: bool
    observed: Any
    expected: Any
    evidence: str


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-300)


def _iterative_peak_rss(record: dict[str, Any]) -> float | None:
    if record.get("peak_total_rss_including_rta_gb") is not None:
        return float(record["peak_total_rss_including_rta_gb"])
    values = [record.get("final_peak_total_gb")]
    values.append((record.get("official_rta") or {}).get("rta_peak_total_gb"))
    available = [float(value) for value in values if value is not None]
    return max(available) if available else None


def _metadata_complete(record: dict[str, Any]) -> tuple[bool, list[str]]:
    metadata = record.get("metadata", {})
    required = (
        "commit_sha",
        "branch",
        "git_dirty",
        "command",
        "timestamp_utc",
        "container_image",
        "container_digest",
        "host_environment_id",
        "provenance",
    )
    missing = [key for key in required if metadata.get(key) in (None, "")]
    return not missing, missing


def _commit_relation(commit: str | None, provenance: str | None) -> str:
    if provenance == "reviewed_reference_not_rerun":
        return "reviewed_reference_exempt"
    if commit is None or re.fullmatch(r"[0-9a-f]{7,40}", commit) is None:
        return "invalid_commit"
    checkout = _git("rev-parse", "HEAD")
    if checkout is None:
        return "checkout_unavailable_sha_valid"
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", commit, checkout],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return "not_checkout_ancestor"
    return "exact_checkout" if commit == checkout else "checkout_ancestor"


def _record_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else BENCHMARKS / path


def evaluate() -> tuple[list[Gate], list[dict[str, Any]]]:
    expected = _load_json(BENCHMARKS / "expected" / "gates.json")
    canonical_config = _load_json(BENCHMARKS / "configs" / "workstation_p2.json")
    with (BENCHMARKS / "benchmark_manifest.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        manifest = list(csv.DictReader(stream))

    gates: list[Gate] = []
    records: dict[str, dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []
    for row in manifest:
        raw_path = row.get("canonical_record", "").strip()
        if not raw_path:
            continue
        path = _record_path(raw_path)
        exists = path.is_file()
        gates.append(
            Gate(f"record_exists:{row['benchmark_id']}", exists, exists, True, raw_path)
        )
        if not exists:
            continue
        record = _load_json(path)
        records[row["benchmark_id"]] = record
        record_benchmark_id = record.get("benchmark_id")
        gates.append(
            Gate(
                f"benchmark_id_matches_manifest:{row['benchmark_id']}",
                record_benchmark_id == row["benchmark_id"],
                record_benchmark_id,
                row["benchmark_id"],
                raw_path,
            )
        )
        complete, missing = _metadata_complete(record)
        gates.append(
            Gate(
                f"metadata_complete:{row['benchmark_id']}",
                complete,
                missing or "complete",
                "no missing required metadata",
                raw_path,
            )
        )
        metadata = record.get("metadata", {})
        relation = _commit_relation(
            metadata.get("commit_sha"), metadata.get("provenance")
        )
        accepted_relations = set(expected["record_commit_relations_accepted"])
        gates.append(
            Gate(
                f"record_commit_consistent:{row['benchmark_id']}",
                relation in accepted_relations,
                relation,
                sorted(accepted_relations),
                raw_path,
            )
        )
        summaries.append(
            {
                "benchmark_id": row["benchmark_id"],
                "category": row["category"],
                "h_nm": record.get("h_nm", record.get("mesh_target_size_nm")),
                "mpi": record.get("mpi_size", 1),
                "iterations": record.get("iterations"),
                "true_residual": record.get(
                    "full_augmented_true_residual",
                    record.get(
                        "linear_system_relative_residual",
                        record.get("reduced_linear_residual"),
                    ),
                ),
                "peak_total_rss_gb": record.get(
                    "peak_total_rss_including_rta_gb",
                    _iterative_peak_rss(record)
                    or record.get(
                        "total_peak_rss_gb", record.get("total_peak_rss_upper_gb")
                    ),
                ),
                "R": (record.get("official_rta") or {}).get(
                    "R_total", record.get("R_total")
                ),
                "T": (record.get("official_rta") or {}).get(
                    "T_total", record.get("T_total")
                ),
                "A_volume": (record.get("official_rta") or {}).get(
                    "A_volume_total", record.get("A_volume_total")
                ),
                "status": row["status"],
                "record": raw_path,
            }
        )

    iterative_ids = ["l3_iterative_h5", "l3_iterative_h3", "l3_iterative_h2"]
    iterative = [records.get(name) for name in iterative_ids]
    present = all(record is not None for record in iterative)
    gates.append(
        Gate(
            "iterative_h5_h3_h2_present",
            present,
            present,
            True,
            ",".join(iterative_ids),
        )
    )
    if present:
        iterative_records = [record for record in iterative if record is not None]
        profiles = {record.get("profile") for record in iterative_records}
        gates.append(
            Gate(
                "iterative_profile_consistent",
                len(profiles) == 1,
                sorted(profiles),
                1,
                "records",
            )
        )
        for name, record in zip(iterative_ids, iterative_records, strict=True):
            config_mapping = {
                "profile": "profile",
                "mpi_size": "mpi_size",
                "coarse_slabs": "coarse_slabs",
                "coarse_dimension": "coarse_dimension",
                "num_slabs": "num_physical_slabs",
                "overlap_layers": "overlap_layers",
                "absorption_shift": "absorption_shift",
                "ilu_levels": "ilu_levels",
                "smoother_iterations": "smoother_iterations",
                "restart": "restart",
                "rtol": "rtol",
                "max_it": "max_it",
            }
            config_differences = {
                record_key: {
                    "record": record.get(record_key),
                    "config": canonical_config[config_key],
                }
                for record_key, config_key in config_mapping.items()
                if record.get(record_key) != canonical_config[config_key]
            }
            gates.append(
                Gate(
                    f"record_matches_canonical_config:{name}",
                    not config_differences,
                    config_differences or "match",
                    "all canonical profile fields match",
                    name,
                )
            )
            metadata = record.get("metadata", {})
            provenance_fields = {
                "actual_source_command": metadata.get("actual_source_command"),
                "actual_source_artifact_root": metadata.get(
                    "actual_source_artifact_root"
                ),
                "canonical_rerun_command": metadata.get("canonical_rerun_command"),
                "canonical_artifact_root": metadata.get("canonical_artifact_root"),
                "artifact_provenance": metadata.get("artifact_provenance"),
            }
            missing_provenance = [
                key for key, value in provenance_fields.items() if value in (None, "")
            ]
            gates.append(
                Gate(
                    f"artifact_provenance_complete:{name}",
                    not missing_provenance,
                    missing_provenance or "complete",
                    "actual and canonical source fields present",
                    name,
                )
            )
            artifact_consistent = (
                metadata.get("command") == metadata.get("actual_source_command")
                and record.get("artifact_root")
                == metadata.get("actual_source_artifact_root")
                and metadata.get("canonical_artifact_root")
                == canonical_config.get("artifact_root")
                and str(metadata.get("canonical_artifact_root", ""))
                in str(metadata.get("canonical_rerun_command", ""))
            )
            gates.append(
                Gate(
                    f"artifact_provenance_consistent:{name}",
                    artifact_consistent,
                    {
                        "command_is_actual": metadata.get("command")
                        == metadata.get("actual_source_command"),
                        "record_root_is_actual": record.get("artifact_root")
                        == metadata.get("actual_source_artifact_root"),
                        "canonical_root": metadata.get("canonical_artifact_root"),
                    },
                    "actual source and canonical rerun identities are not conflated",
                    name,
                )
            )
            clean_provenance = str(metadata.get("provenance", "")).startswith(
                "clean_rerun"
            )
            gates.append(
                Gate(
                    f"clean_rerun_git_clean:{name}",
                    (not clean_provenance) or metadata.get("git_dirty") is False,
                    metadata.get("git_dirty"),
                    False,
                    name,
                )
            )
            gates.extend(
                (
                    Gate(
                        f"qualified_profile:{name}",
                        record.get("qualified_profile") is True
                        and not record.get("qualification_deviations"),
                        {
                            "qualified": record.get("qualified_profile"),
                            "deviations": record.get("qualification_deviations"),
                        },
                        "qualified=true and no deviations",
                        name,
                    ),
                    Gate(
                        f"ksp_converged:{name}",
                        int(record.get("ksp_reason", 0)) > 0,
                        record.get("ksp_reason"),
                        "> 0",
                        name,
                    ),
                    Gate(
                        f"coarse_condition:{name}",
                        record.get("coarse_condition") is not None
                        and float(record["coarse_condition"])
                        <= expected["coarse_condition_max"],
                        record.get("coarse_condition"),
                        expected["coarse_condition_max"],
                        name,
                    ),
                    Gate(
                        f"physical_model:{name}",
                        record.get("physical_model")
                        == canonical_config.get("physical_model"),
                        record.get("physical_model"),
                        canonical_config.get("physical_model"),
                        name,
                    ),
                )
            )
            reported = float(record["reported_relative_residual"])
            condensed = float(record["condensed_true_residual"])
            full = float(record["full_augmented_true_residual"])
            gates.extend(
                (
                    Gate(
                        f"residual_max:{name}",
                        max(reported, condensed, full)
                        <= expected["full_augmented_true_residual_max"],
                        max(reported, condensed, full),
                        expected["full_augmented_true_residual_max"],
                        name,
                    ),
                    Gate(
                        f"reported_condensed_match:{name}",
                        _relative_difference(reported, condensed)
                        <= expected["reported_condensed_relative_difference_max"],
                        _relative_difference(reported, condensed),
                        expected["reported_condensed_relative_difference_max"],
                        name,
                    ),
                    Gate(
                        f"reported_full_match:{name}",
                        _relative_difference(reported, full)
                        <= expected["reported_full_relative_difference_max"],
                        _relative_difference(reported, full),
                        expected["reported_full_relative_difference_max"],
                        name,
                    ),
                    Gate(
                        f"coarse_rank:{name}",
                        record.get("coarse_rank") == expected["coarse_rank_required"],
                        record.get("coarse_rank"),
                        expected["coarse_rank_required"],
                        name,
                    ),
                )
            )
            official = record.get("official_rta") or {}
            gates.append(
                Gate(
                    f"official_rta:{name}",
                    all(
                        official.get(key) is not None
                        for key in ("R_total", "T_total", "A_volume_total")
                    ),
                    sorted(official),
                    "R_total,T_total,A_volume_total",
                    name,
                )
            )
            closure = official.get("energy_closure_error")
            gates.append(
                Gate(
                    f"energy_closure:{name}",
                    closure is not None
                    and abs(float(closure)) <= expected["energy_closure_abs_max"],
                    closure,
                    expected["energy_closure_abs_max"],
                    name,
                )
            )
        counts = [int(record["iterations"]) for record in iterative_records]
        ratio = max(counts) / min(counts)
        gates.append(
            Gate(
                "iteration_ratio_h5_h3_h2",
                ratio <= expected["iteration_ratio_h5_h3_h2_max"],
                ratio,
                expected["iteration_ratio_h5_h3_h2_max"],
                "iterative records",
            )
        )
        h2_rss = _iterative_peak_rss(iterative_records[2])
        gates.append(
            Gate(
                "h2_peak_total_rss_gb",
                h2_rss is not None and h2_rss <= expected["h2_peak_total_rss_gb_max"],
                h2_rss,
                expected["h2_peak_total_rss_gb_max"],
                iterative_ids[2],
            )
        )

    for label in ("h5", "h3"):
        direct = records.get(f"l3_direct_{label}")
        iterative_record = records.get(f"l3_iterative_{label}")
        if direct is None or iterative_record is None:
            continue
        official = iterative_record.get("official_rta") or {}
        for quantity, direct_key in (
            ("R", "R_total"),
            ("T", "T_total"),
            ("A_volume", "A_volume_total"),
        ):
            delta = abs(float(direct[direct_key]) - float(official[direct_key]))
            tolerance = expected["direct_iterative_abs_tolerance"][label][quantity]
            gates.append(
                Gate(
                    f"direct_iterative_{quantity}:{label}",
                    delta <= tolerance,
                    delta,
                    tolerance,
                    f"l3_direct_{label},l3_iterative_{label}",
                )
            )

    h2_direct = records.get("l3_direct_h2")
    h2_status = None if h2_direct is None else h2_direct.get("status")
    gates.append(
        Gate(
            "h2_direct_reviewed_reference",
            h2_status == "reviewed_reference_not_rerun_in_task028",
            h2_status,
            "reviewed_reference_not_rerun_in_task028",
            "l3_direct_h2",
        )
    )
    environment = _load_json(BENCHMARKS / "environment.json")
    environment_status = environment.get("reproducibility_status")
    gates.append(
        Gate(
            "environment_reproducibility_declared",
            environment_status in {"reproducible", "qualified_local_image"},
            environment_status,
            "reproducible or qualified_local_image",
            "environment.json",
        )
    )
    ordinary = all(
        record.get("ordinary_default_changed") is False
        for record in iterative
        if record
    )
    gates.append(
        Gate(
            "ordinary_default_unchanged", ordinary, ordinary, True, "iterative records"
        )
    )
    return gates, summaries


def _write_outputs(gates: list[Gate], summaries: list[dict[str, Any]]) -> None:
    summary_path = BENCHMARKS / "benchmark_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        fieldnames = list(summaries[0])
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)
    payload = {
        "checkout_commit": _git("rev-parse", "HEAD"),
        "checkout_dirty": bool(_git("status", "--short")),
        "checkout_dirty_note": (
            "This reports the checkout at checker execution time. It is independent "
            "of metadata.git_dirty, which records the original benchmark run. Writing "
            "this report can itself make the checkout dirty."
        ),
        "passed": all(gate.passed for gate in gates),
        "passed_count": sum(gate.passed for gate in gates),
        "total_count": len(gates),
        "gates": [gate.__dict__ for gate in gates],
    }
    path = BENCHMARKS / "records" / "benchmark_gate_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate canonical Task28 benchmark records"
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Check without refreshing summary/report files",
    )
    args = parser.parse_args()
    gates, summaries = evaluate()
    if not args.no_write:
        _write_outputs(gates, summaries)
    failed = [gate for gate in gates if not gate.passed]
    for gate in gates:
        print(f"{'PASS' if gate.passed else 'FAIL'} {gate.name}: {gate.observed!r}")
    print(f"benchmark gates: {len(gates) - len(failed)}/{len(gates)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
