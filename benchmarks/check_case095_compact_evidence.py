"""Hermetic checker for the compact Task035b Case095 authority."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
CONFIG = CASE / "config.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _check_candidate_ledger(
    config: dict[str, Any],
    authority: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    info = config.get("candidate_ledger", {})
    json_path = _repo_path(str(info.get("json_path", "")))
    csv_path = _repo_path(str(info.get("csv_path", "")))
    if not json_path.is_file() or not csv_path.is_file():
        failures.append("candidate_ledger_missing")
        return {
            "candidate_count": 0,
            "candidate_availability_counts": {},
            "candidate_compact_unique_records": 0,
            "candidate_archive_local_reads": 0,
        }
    if _sha256(json_path) != info.get("json_sha256"):
        failures.append("candidate_ledger_json_hash")
    if _sha256(csv_path) != info.get("csv_sha256"):
        failures.append("candidate_ledger_csv_hash")

    ledger = json.loads(json_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    candidates = ledger.get("candidates", [])
    ids = [str(row.get("candidate_id", "")) for row in candidates]
    csv_ids = [str(row.get("candidate_id", "")) for row in csv_rows]
    if ledger.get("schema_version") != "task035b.all-candidates.v3":
        failures.append("candidate_ledger_schema")
    if len(candidates) != info.get("candidate_count") or len(ids) != len(
        set(ids)
    ):
        failures.append("candidate_ledger_count_or_uniqueness")
    if csv_ids != ids:
        failures.append("candidate_ledger_csv_order")

    counts = Counter(
        str(row.get("record_availability", "")) for row in candidates
    )
    if dict(counts) != info.get("availability_counts"):
        failures.append("candidate_ledger_availability_counts")
    authority_names = {
        str(item.get("name", "")) for item in authority.get("records", [])
    }
    compact_names: set[str] = set()
    csv_by_id = {str(row.get("candidate_id", "")): row for row in csv_rows}
    for index, row in enumerate(candidates):
        availability = row.get("record_availability")
        record = row.get("record")
        archive = row.get("archive_record_path")
        csv_row = csv_by_id.get(str(row.get("candidate_id", "")), {})
        for key in (
            "record",
            "record_sha256",
            "source_sha",
            "record_availability",
            "archive_record_path",
        ):
            expected = "" if row.get(key) is None else str(row.get(key, ""))
            if csv_row.get(key) != expected:
                failures.append(f"candidate[{index}]:csv_{key}")
        if availability == "tracked_compact_authority":
            if not record or archive is not None:
                failures.append(f"candidate[{index}]:compact_shape")
                continue
            record_path = _repo_path(str(record))
            compact_names.add(record_path.name)
            if (
                record_path.name not in authority_names
                or not record_path.is_file()
                or _sha256(record_path) != row.get("record_sha256")
            ):
                failures.append(f"candidate[{index}]:compact_binding")
        elif availability == "tracked_project_document":
            if (
                not record
                or archive is not None
                or not _repo_path(str(record)).is_file()
            ):
                failures.append(f"candidate[{index}]:document_binding")
        elif availability == "source_branch_archive_not_merged":
            if (
                record is not None
                or not archive
                or not re.fullmatch(
                    r"[0-9a-f]{64}", str(row.get("record_sha256", ""))
                )
                or not re.fullmatch(
                    r"[0-9a-f]{40}", str(row.get("source_sha", ""))
                )
            ):
                failures.append(f"candidate[{index}]:archive_binding")
        else:
            failures.append(f"candidate[{index}]:availability")
    if len(compact_names) != info.get("compact_unique_record_count"):
        failures.append("candidate_ledger_compact_unique_records")

    return {
        "candidate_count": len(candidates),
        "candidate_availability_counts": dict(counts),
        "candidate_compact_unique_records": len(compact_names),
        # The checker deliberately validates archive locators and hashes as
        # ledger data; it never reads excluded source-branch record files.
        "candidate_archive_local_reads": 0,
    }


def check_case095() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    failures: list[str] = []
    authority_info = config.get("compact_authority", {})
    authority_path = _repo_path(str(authority_info.get("path", "")))
    if not authority_path.is_file():
        return {
            "status": "case095_compact_authority_fail",
            "failures": ["compact_authority_missing"],
        }
    if _sha256(authority_path) != authority_info.get("sha256"):
        failures.append("compact_authority_hash")
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    if (
        authority.get("schema_version")
        != "task035b.case095-compact-authority.v1"
    ):
        failures.append("compact_authority_schema")
    records = authority.get("records", [])
    if len(records) != authority.get("record_count"):
        failures.append("record_count_internal")
    if len(records) != authority_info.get("record_count"):
        failures.append("record_count_config")
    if len({item.get("role") for item in records}) != len(records):
        failures.append("record_roles_not_unique")

    loaded: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(records):
        path = authority_path.parent / str(item.get("name", ""))
        if not path.is_file():
            failures.append(f"record[{index}]:missing")
            continue
        if _sha256(path) != item.get("sha256"):
            failures.append(f"record[{index}]:hash_mismatch")
            continue
        loaded[str(item["name"])] = json.loads(
            path.read_text(encoding="utf-8")
        )

    h13 = loaded.get(
        "fixed_p5trace_p6interior_h13_directional_z_mpi8.json",
        {},
    )
    comparison = h13.get("diffraction_channel_comparison", {})
    if comparison.get("significant_power_pass_count") != 10:
        failures.append("h13_power_gate_not_10_of_12")
    if comparison.get("significant_complex_amplitude_pass_count") != 10:
        failures.append("h13_amplitude_gate_not_10_of_12")
    if h13.get("candidate", {}).get(
        "linear_system_relative_residual"
    ) != 5.808278021301951e-12:
        failures.append("h13_true_residual")

    iterative = loaded.get("h15_factor_free_iterative_mpi8_v1.json", {})
    ratios = [
        profile.get("unpreconditioned_residual_final_to_initial")
        for profile in iterative.get("profiles", [])
    ]
    slab_ratio = (
        loaded.get(
            "h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json",
            {},
        )
        .get("formal_screen", {})
        .get("unpreconditioned_residual_final_to_initial")
    )
    expected = (0.8616624409266612, 0.9996606193679304)
    if tuple(ratios) != expected or slab_ratio != 0.9962645476420617:
        failures.append("iterative_controlled_negative_values")

    selective = loaded.get(
        "physical_selective_trace_execution_capability_v2.json",
        {},
    )
    if (
        selective.get("formal_pde_started") is not False
        or selective.get("formal_accuracy_boundary", {}).get(
            "selective_pde_run_count"
        )
        != 0
    ):
        failures.append("selective_trace_was_misclassified")

    prohibited = {
        "production_selective_trace",
        "condensed_iterative_profiles",
        "regionwise_or_non_exact_sequence_local_p",
        "irregular_geometry",
        "tetra_static_condensation",
        "mixed_cell_mesh",
    }
    if set(authority.get("not_promoted", [])) != prohibited:
        failures.append("not_promoted_contract")
    if config.get("ordinary_default_changed") is not False:
        failures.append("ordinary_default_changed")
    candidate_audit = _check_candidate_ledger(
        config,
        authority,
        failures,
    )

    return {
        "status": (
            "case095_compact_authority_pass"
            if not failures
            else "case095_compact_authority_fail"
        ),
        "failures": failures,
        "record_count": len(records),
        "hash_verified_count": len(loaded),
        "h13_significant_gate": {
            "powers": comparison.get("significant_power_pass_count"),
            "amplitudes": comparison.get(
                "significant_complex_amplitude_pass_count"
            ),
        },
        "iterative_terminal_ratios": [*ratios, slab_ratio],
        "selective_trace_formal_pde_runs": (
            selective.get("formal_accuracy_boundary", {}).get(
                "selective_pde_run_count"
            )
        ),
        "starts_pde": False,
        "reads_ignored_artifacts": False,
        **candidate_audit,
    }


def main() -> int:
    result = check_case095()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "case095_compact_authority_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
