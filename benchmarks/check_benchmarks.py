from __future__ import annotations

import argparse
import csv
import hashlib
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if record.get("peak_rss_gb_including_rta") is not None:
        return float(record["peak_rss_gb_including_rta"])
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

    case_requirements = {
        "001_2d_tm_pml_floquet": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "002_2d_tm_dtn_equivalence": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "003_2d_te_tm_complex_absorption": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "010_3d_stage1_airbox": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "011_3d_stage2a_floquet": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "012_3d_stage2b_pml": ("README.md", "config.json", "expected.json", "run.sh"),
        "013_3d_stage2c_fresnel": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "020_3d_stage4a_flat_dtn": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
        ),
        "021_3d_stage4b_direct": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "022_dtn_condensation_equivalence": (
            "README.md",
            "fixture.json",
            "expected.json",
            "test_command.txt",
        ),
        "030_mumps_ooc_blr": (
            "README.md",
            "config.json",
            "expected.json",
            "test_command.txt",
        ),
        "031_workstation_iterative": (
            "README.md",
            "config.json",
            "expected.json",
            "run.sh",
            "records",
        ),
        "040_mpi_p_algebra_regression": (
            "README.md",
            "fixture.json",
            "expected.json",
            "test_command.txt",
        ),
        "050_stage4_direct_memory_forensics": (
            "README.md",
            "config.json",
            "expected.json",
            "run_h5.sh",
            "run_h3.sh",
            "run_h2_guarded.sh",
            "records",
        ),
        "060_multilevel_hcurl_iterative_solver": (
            "README.md",
            "config.json",
            "expected.json",
            "expected/gates.json",
            "run.sh",
            "records/h5_baseline.json",
            "records/hierarchy_contract.json",
            "records/transfer_contract.json",
            "records/candidate_screen_summary.json",
            "records/best_h5.json",
            "records/best_h3.json",
            "records/best_h2.json",
        ),
    }
    cases_root = BENCHMARKS / "cases"
    for case_name, required_names in case_requirements.items():
        missing = [
            name
            for name in required_names
            if not (cases_root / case_name / name).exists()
        ]
        gates.append(
            Gate(
                f"case_contract:{case_name}",
                not missing,
                missing or "complete",
                "all case-contained contract files exist",
                f"cases/{case_name}",
            )
        )

    reference_files = (
        "010_3d_stage1_airbox/records/canonical_reference.json",
        "021_3d_stage4b_direct/records/h5_reference.json",
        "021_3d_stage4b_direct/records/h3_reference.json",
        "021_3d_stage4b_direct/records/h2_reviewed_reference.json",
        "031_workstation_iterative/records/h5_reference.json",
        "031_workstation_iterative/records/h3_reference.json",
        "031_workstation_iterative/records/h2_reference.json",
    )
    for relative_reference in reference_files:
        reference_path = cases_root / relative_reference
        if not reference_path.is_file():
            gates.append(
                Gate(
                    f"case_reference:{relative_reference}",
                    False,
                    "missing reference file",
                    "sha256-pinned canonical reference",
                    f"cases/{relative_reference}",
                )
            )
            continue
        reference = _load_json(reference_path)
        canonical_path = ROOT / str(reference.get("canonical_record", ""))
        observed_hash = _sha256(canonical_path) if canonical_path.is_file() else None
        expected_hash = reference.get("sha256")
        gates.append(
            Gate(
                f"case_reference:{relative_reference}",
                observed_hash == expected_hash,
                observed_hash,
                expected_hash,
                str(reference.get("canonical_record")),
            )
        )

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
        if (
            metadata.get("provenance")
            == "canonical_lightweight_rerun_from_frozen_case_contract"
        ):
            tracked_source_dirty = metadata.get("tracked_source_dirty")
            gates.append(
                Gate(
                    f"canonical_lightweight_tracked_source_clean:{row['benchmark_id']}",
                    tracked_source_dirty is False,
                    tracked_source_dirty,
                    False,
                    raw_path,
                )
            )
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
                        record.get(
                            "reduced_linear_residual",
                            (record.get("solver") or {}).get("linear_true_residual"),
                        ),
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
                    "A_volume_total",
                    (record.get("official_rta") or {}).get(
                        "A_volume", record.get("A_volume_total")
                    ),
                ),
                "status": row["status"],
                "record": raw_path,
            }
        )

    case002_comparison_path = (
        cases_root / "002_2d_tm_dtn_equivalence" / "records" / "comparison.json"
    )
    case002_comparison = (
        _load_json(case002_comparison_path)
        if case002_comparison_path.is_file()
        else None
    )
    gates.append(
        Gate(
            "case002_comparison_exists",
            case002_comparison is not None,
            case002_comparison is not None,
            True,
            "cases/002_2d_tm_dtn_equivalence/records/comparison.json",
        )
    )
    if case002_comparison is not None:
        comparison_metadata = case002_comparison.get("metadata", {})
        if (
            comparison_metadata.get("provenance")
            == "canonical_lightweight_rerun_from_frozen_case_contract"
        ):
            tracked_source_dirty = comparison_metadata.get("tracked_source_dirty")
            gates.append(
                Gate(
                    "canonical_lightweight_tracked_source_clean:"
                    "case002_explicit_vs_auxiliary",
                    tracked_source_dirty is False,
                    tracked_source_dirty,
                    False,
                    "cases/002_2d_tm_dtn_equivalence/records/comparison.json",
                )
            )
        field_difference = float(case002_comparison["field_relative_difference"])
        rta_differences = [
            float(value)
            for value in case002_comparison["absolute_differences"].values()
        ]
        max_rta_difference = max(rta_differences, default=0.0)
        gates.extend(
            (
                Gate(
                    "case002_field_equivalence",
                    field_difference
                    <= expected["case002_field_relative_difference_max"],
                    field_difference,
                    expected["case002_field_relative_difference_max"],
                    "case002 comparison",
                ),
                Gate(
                    "case002_rta_equivalence",
                    max_rta_difference
                    <= expected["case002_rta_absolute_difference_max"],
                    max_rta_difference,
                    expected["case002_rta_absolute_difference_max"],
                    "case002 comparison",
                ),
                Gate(
                    "case002_matrix_identity",
                    case002_comparison["explicit"]["auxiliary_dofs"] == 0
                    and case002_comparison["auxiliary"]["auxiliary_dofs"] > 0
                    and case002_comparison["auxiliary"]["matrix_rows"]
                    > case002_comparison["explicit"]["matrix_rows"],
                    {
                        "explicit": {
                            "rows": case002_comparison["explicit"]["matrix_rows"],
                            "aux": case002_comparison["explicit"]["auxiliary_dofs"],
                        },
                        "auxiliary": {
                            "rows": case002_comparison["auxiliary"]["matrix_rows"],
                            "aux": case002_comparison["auxiliary"]["auxiliary_dofs"],
                        },
                    },
                    "explicit has no auxiliary rows; auxiliary system is augmented",
                    "case002 comparison",
                ),
            )
        )

    for benchmark_id in ("case002_explicit", "case002_auxiliary"):
        record = records.get(benchmark_id)
        if record is None:
            continue
        residual = float(record["solver"]["linear_true_residual"])
        closure = float(record["official_rta"]["energy_closure_error"])
        gates.extend(
            (
                Gate(
                    f"two_d_residual:{benchmark_id}",
                    residual <= expected["two_d_linear_residual_max"],
                    residual,
                    expected["two_d_linear_residual_max"],
                    benchmark_id,
                ),
                Gate(
                    f"lossless_energy:{benchmark_id}",
                    abs(closure) <= expected["two_d_energy_closure_abs_max"],
                    closure,
                    expected["two_d_energy_closure_abs_max"],
                    benchmark_id,
                ),
            )
        )

    for benchmark_id in ("case003_tm_lossy", "case003_te_lossy"):
        record = records.get(benchmark_id)
        if record is None:
            continue
        residual = float(record["solver"]["linear_true_residual"])
        official = record["official_rta"]
        closure = float(official["energy_closure_error"])
        balance_difference = abs(
            float(official["A_balance"]) - float(official["A_volume"])
        )
        nonnegative = {
            key: float(official[key]) for key in ("R_total", "T_total", "A_volume")
        }
        probe = record.get("diagnostic_probe") or {}
        gates.extend(
            (
                Gate(
                    f"lossy_residual:{benchmark_id}",
                    residual <= expected["two_d_linear_residual_max"],
                    residual,
                    expected["two_d_linear_residual_max"],
                    benchmark_id,
                ),
                Gate(
                    f"lossy_nonnegative:{benchmark_id}",
                    all(value >= 0.0 for value in nonnegative.values()),
                    nonnegative,
                    ">= 0",
                    benchmark_id,
                ),
                Gate(
                    f"lossy_energy:{benchmark_id}",
                    abs(closure) <= expected["two_d_energy_closure_abs_max"],
                    closure,
                    expected["two_d_energy_closure_abs_max"],
                    benchmark_id,
                ),
                Gate(
                    f"lossy_absorption_balance:{benchmark_id}",
                    balance_difference
                    <= expected["two_d_absorption_balance_difference_max"],
                    balance_difference,
                    expected["two_d_absorption_balance_difference_max"],
                    benchmark_id,
                ),
                Gate(
                    f"probe_is_diagnostic:{benchmark_id}",
                    probe.get("identity") == "diagnostic_only"
                    and probe.get("must_not_replace_official") is True,
                    probe.get("identity"),
                    "diagnostic_only and must_not_replace_official=true",
                    benchmark_id,
                ),
            )
        )

    tm_lossy = records.get("case003_tm_lossy")
    if tm_lossy is not None:
        auxiliary_trace = tm_lossy.get("auxiliary_vs_trace") or {}
        maximum = max(
            (abs(float(value)) for value in auxiliary_trace.values()),
            default=float("inf"),
        )
        gates.append(
            Gate(
                "lossy_tm_auxiliary_trace",
                maximum <= expected["two_d_auxiliary_trace_abs_difference_max"],
                maximum,
                expected["two_d_auxiliary_trace_abs_difference_max"],
                "case003_tm_lossy",
            )
        )

    zero_contrast = records.get("l1_2d_zero_contrast")
    if zero_contrast is not None:
        lossless_sum = float(zero_contrast["R_plus_T"])
        gates.append(
            Gate(
                "lossless_zero_contrast_regression",
                abs(lossless_sum - 1.0) <= expected["two_d_energy_closure_abs_max"],
                lossless_sum,
                1.0,
                "l1_2d_zero_contrast",
            )
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

    case060_expected = _load_json(
        cases_root / "060_multilevel_hcurl_iterative_solver" / "expected" / "gates.json"
    )
    task030_ids = {
        "h5": "task030_compact_h5",
        "h3": "task030_compact_h3",
        "h2": "task030_compact_h2",
    }
    task030 = {label: records.get(name) for label, name in task030_ids.items()}
    task030_present = all(record is not None for record in task030.values())
    gates.append(
        Gate(
            "task030_h5_h3_h2_present",
            task030_present,
            task030_present,
            True,
            ",".join(task030_ids.values()),
        )
    )
    if task030_present:
        contract = case060_expected["record_contract"]
        numeric = case060_expected["numeric_common"]
        direct_ids = {
            "h5": "l3_direct_h5",
            "h3": "l3_direct_h3",
            "h2": "l3_direct_h2",
        }
        canonical_iterative_ids = {
            "h5": "l3_iterative_h5",
            "h3": "l3_iterative_h3",
            "h2": "l3_iterative_h2",
        }
        for label, benchmark_id in task030_ids.items():
            record = task030[label]
            assert record is not None
            metadata = record.get("metadata") or {}
            artifact_hash = metadata.get("source_artifact_sha256")
            artifact_path = ROOT / str(record.get("source_artifact", ""))
            observed_artifact_hash = (
                _sha256(artifact_path) if artifact_path.is_file() else None
            )
            hash_format_ok = (
                isinstance(artifact_hash, str)
                and re.fullmatch(
                    contract["source_artifact_sha256_pattern"], artifact_hash
                )
                is not None
            )
            artifact_hash_ok = hash_format_ok and (
                observed_artifact_hash is None
                or observed_artifact_hash == artifact_hash
            )
            gates.append(
                Gate(
                    f"task030_source_artifact_sha256:{benchmark_id}",
                    artifact_hash_ok,
                    observed_artifact_hash or "heavy artifact unavailable by policy",
                    artifact_hash,
                    str(record.get("source_artifact")),
                )
            )
            provenance_qualified = (
                metadata.get("git_dirty") is True
                and metadata.get("tracked_source_dirty") is True
                and metadata.get("provenance")
                == "working_tree_source_artifact_recovered_without_rerun"
                and bool(metadata.get("provenance_qualification"))
                and bool(metadata.get("actual_source_artifact_root"))
                and metadata.get("container_image") != "unknown"
                and metadata.get("container_digest") != "unknown"
            )
            gates.append(
                Gate(
                    f"task030_provenance_qualified:{benchmark_id}",
                    provenance_qualified,
                    {
                        "git_dirty": metadata.get("git_dirty"),
                        "tracked_source_dirty": metadata.get("tracked_source_dirty"),
                        "provenance": metadata.get("provenance"),
                    },
                    "honest dirty-source qualification with pinned artifact identity",
                    benchmark_id,
                )
            )
            relation = _commit_relation(
                metadata.get("commit_sha"), metadata.get("provenance")
            )
            gates.append(
                Gate(
                    f"task030_source_commit_relation:{benchmark_id}",
                    relation in set(expected["record_commit_relations_accepted"]),
                    relation,
                    sorted(expected["record_commit_relations_accepted"]),
                    benchmark_id,
                )
            )
            identity_ok = (
                record.get("profile_identity") == contract["profile_identity"]
                and record.get("final_solver_identity")
                == contract["final_solver_identity"]
                and record.get("hierarchy_infrastructure_status")
                == contract["hierarchy_infrastructure_status"]
                and record.get("p_h_multigrid_solver_disposition")
                == contract["p_h_multigrid_solver_disposition"]
            )
            gates.append(
                Gate(
                    f"task030_solver_identity:{benchmark_id}",
                    identity_ok,
                    {
                        "profile": record.get("profile_identity"),
                        "final_solver": record.get("final_solver_identity"),
                        "hierarchy": record.get("hierarchy_infrastructure_status"),
                        "p_h_solver": record.get("p_h_multigrid_solver_disposition"),
                    },
                    {
                        "profile": contract["profile_identity"],
                        "final_solver": contract["final_solver_identity"],
                        "hierarchy": contract["hierarchy_infrastructure_status"],
                        "p_h_solver": contract["p_h_multigrid_solver_disposition"],
                    },
                    benchmark_id,
                )
            )
            qualification_ok = record.get("qualified_profile") is False and bool(
                record.get("qualification_deviations")
            )
            gates.append(
                Gate(
                    f"task030_explicit_opt_in_identity:{benchmark_id}",
                    qualification_ok,
                    {
                        "qualified_profile": record.get("qualified_profile"),
                        "deviations": record.get("qualification_deviations"),
                    },
                    "qualified_profile=false with explicit deviations",
                    benchmark_id,
                )
            )
            modal = record.get("modal_identity") or {}
            common_contract_ok = (
                record.get("ordinary_default_changed")
                is contract["ordinary_default_changed"]
                and record.get("n_aux") == contract["n_aux"]
                and modal.get("n_aux_before_condensation") == contract["n_aux"]
                and record.get("physical_model")
                == canonical_config.get("physical_model")
            )
            gates.append(
                Gate(
                    f"task030_frozen_contract:{benchmark_id}",
                    common_contract_ok,
                    {
                        "ordinary_default_changed": record.get(
                            "ordinary_default_changed"
                        ),
                        "n_aux": record.get("n_aux"),
                        "modal_n_aux": modal.get("n_aux_before_condensation"),
                        "physical_model_match": record.get("physical_model")
                        == canonical_config.get("physical_model"),
                    },
                    "ordinary default false, same physical model and 80 modes",
                    benchmark_id,
                )
            )
            gates.append(
                Gate(
                    f"task030_ksp_converged:{benchmark_id}",
                    int(record.get("ksp_reason", 0)) > 0,
                    record.get("ksp_reason"),
                    "> 0",
                    benchmark_id,
                )
            )
            reported = float(record["reported_relative_residual"])
            condensed = float(record["condensed_true_residual"])
            full = float(record["full_augmented_true_residual"])
            maximum_residual = max(reported, condensed, full)
            maximum_mismatch = max(
                _relative_difference(reported, condensed),
                _relative_difference(reported, full),
            )
            gates.extend(
                (
                    Gate(
                        f"task030_residual_max:{benchmark_id}",
                        maximum_residual <= numeric["full_true_residual_max"],
                        maximum_residual,
                        numeric["full_true_residual_max"],
                        benchmark_id,
                    ),
                    Gate(
                        f"task030_residual_consistency:{benchmark_id}",
                        maximum_mismatch
                        <= numeric["reported_true_relative_difference_max"],
                        maximum_mismatch,
                        numeric["reported_true_relative_difference_max"],
                        benchmark_id,
                    ),
                )
            )
            rta_complete = all(
                record.get(key) is not None
                for key in ("R_total", "T_total", "A_volume_total")
            )
            gates.append(
                Gate(
                    f"task030_official_rta:{benchmark_id}",
                    rta_complete,
                    rta_complete,
                    True,
                    benchmark_id,
                )
            )
            closure = record.get("energy_closure_error")
            gates.append(
                Gate(
                    f"task030_energy_closure:{benchmark_id}",
                    closure is not None
                    and abs(float(closure)) <= numeric["energy_closure_abs_max"],
                    closure,
                    numeric["energy_closure_abs_max"],
                    benchmark_id,
                )
            )
            direct = records.get(direct_ids[label])
            direct_delta = float("inf")
            if direct is not None and rta_complete:
                direct_delta = max(
                    abs(float(record[key]) - float(direct[key]))
                    for key in ("R_total", "T_total", "A_volume_total")
                )
            gates.append(
                Gate(
                    f"task030_rta_delta_from_direct:{benchmark_id}",
                    direct_delta <= numeric["rta_delta_from_direct_max"],
                    direct_delta,
                    numeric["rta_delta_from_direct_max"],
                    f"{benchmark_id},{direct_ids[label]}",
                )
            )

        task030_h5 = task030["h5"]
        task030_h3 = task030["h3"]
        task030_h2 = task030["h2"]
        assert task030_h5 is not None
        assert task030_h3 is not None
        assert task030_h2 is not None
        canonical_h3 = records.get(canonical_iterative_ids["h3"])
        task030_h3_peak = _iterative_peak_rss(task030_h3)
        canonical_h3_peak = (
            _iterative_peak_rss(canonical_h3) if canonical_h3 is not None else None
        )
        h3_memory_reduction = (
            None
            if task030_h3_peak is None or canonical_h3_peak is None
            else (canonical_h3_peak - task030_h3_peak) / canonical_h3_peak
        )
        h3_memory_pass = task030_h3_peak is not None and (
            task030_h3_peak <= case060_expected["h3_full"]["peak_rss_gb_max"]
            or (
                h3_memory_reduction is not None
                and h3_memory_reduction
                >= case060_expected["h3_full"]["minimum_memory_reduction_fraction"]
            )
        )
        gates.append(
            Gate(
                "task030_h3_memory_gate",
                h3_memory_pass,
                {
                    "peak_rss_gb": task030_h3_peak,
                    "relative_reduction": h3_memory_reduction,
                    "absolute_gate_pass": task030_h3_peak is not None
                    and task030_h3_peak
                    <= case060_expected["h3_full"]["peak_rss_gb_max"],
                    "relative_gate_pass": h3_memory_reduction is not None
                    and h3_memory_reduction
                    >= case060_expected["h3_full"]["minimum_memory_reduction_fraction"],
                },
                "RSS <= 3.8 GB OR reduction >= 25%",
                "task030_compact_h3,l3_iterative_h3",
            )
        )
        h3_h5_ratio = float(task030_h3["iterations"]) / float(task030_h5["iterations"])
        gates.append(
            Gate(
                "task030_h3_h5_iteration_ratio",
                h3_h5_ratio
                <= case060_expected["h3_full"]["h3_to_h5_iteration_ratio_max"],
                h3_h5_ratio,
                case060_expected["h3_full"]["h3_to_h5_iteration_ratio_max"],
                "task030_compact_h5,task030_compact_h3",
            )
        )
        task030_h2_peak = _iterative_peak_rss(task030_h2)
        gates.append(
            Gate(
                "task030_h2_peak_rss",
                task030_h2_peak is not None
                and task030_h2_peak <= case060_expected["h2_full"]["peak_rss_gb_max"],
                task030_h2_peak,
                case060_expected["h2_full"]["peak_rss_gb_max"],
                "task030_compact_h2",
            )
        )
        strong_claim_absent = (
            task030_h2.get("strong_workstation_success")
            is contract["strong_workstation_success"]
            and "strong_workstation_success"
            not in str(task030_h2.get("classification", ""))
            and task030_h2.get("preferred_iteration_target_pass") is False
        )
        gates.append(
            Gate(
                "task030_h2_classification_not_strong",
                strong_claim_absent,
                {
                    "classification": task030_h2.get("classification"),
                    "strong_workstation_success": task030_h2.get(
                        "strong_workstation_success"
                    ),
                    "preferred_iteration_target_pass": task030_h2.get(
                        "preferred_iteration_target_pass"
                    ),
                },
                "strong success false and preferred iteration target missed",
                "task030_compact_h2",
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
