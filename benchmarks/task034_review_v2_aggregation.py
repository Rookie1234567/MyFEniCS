"""Rebuild the accepted Task034 fact table without opening heavy artifacts.

The compact fixture is tracked in Git. Its ``evidence_path`` values are provenance
labels only: this module deliberately never resolves or reads those paths.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


COLUMNS = [
    "case_key", "p", "h_nm", "method", "M_per_direction", "MPI",
    "polarization", "status", "data_identity", "source_sha", "elements",
    "fe_dofs", "external_aux_dofs", "modal_unknowns", "total_rows",
    "assembled_nnz", "factor_nnz", "R_total", "T_total", "A_balance",
    "A_volume", "R00_s", "R00_p", "R00_total", "T00_s", "T00_p",
    "T00_total", "true_relative_residual", "assembly_seconds",
    "factorization_seconds", "solve_seconds", "total_seconds",
    "peak_memory_gib", "swap_bytes", "full3d_hybrid_closure_status",
    "evidence_path",
]

FIXTURE_RELATIVE = Path(
    "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
    "all_model_compact_fixture.json"
)
CASE093_RELATIVE = Path(
    "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/"
    "convergence_summary.json"
)
MPI_RELATIVE = Path(
    "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/"
    "mpi_identity_summary.json"
)
CASE092_RECORDS = Path(
    "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records"
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _same_value(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual == expected
    try:
        return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12)
    except (TypeError, ValueError):
        return actual == expected


def _require_equal(label: str, actual: Any, expected: Any) -> None:
    if not _same_value(actual, expected):
        raise ValueError(f"{label}: compact={actual!r}, authority={expected!r}")


def _validate_fixture(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    if fixture.get("schema_version") != "task034.compact-model-measurements.v1":
        raise ValueError("unsupported Task034 compact fixture schema")
    if fixture.get("columns") != COLUMNS:
        raise ValueError("compact fixture columns do not match the public schema")
    raw_rows = fixture.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("compact fixture rows must be a list")
    if fixture.get("row_count") != len(raw_rows) or len(raw_rows) != 40:
        raise ValueError("compact fixture must contain exactly 40 rows")
    generator = _mapping(fixture.get("generator"))
    if generator.get("version") != "task034.compact-fixture-generator.v1":
        raise ValueError("compact fixture generator version is missing or unsupported")
    if not _mapping(fixture.get("field_sources")):
        raise ValueError("compact fixture field_sources metadata is required")
    provenance = fixture.get("provenance")
    if not isinstance(provenance, list) or len(provenance) != 40:
        raise ValueError("compact fixture must contain 40 provenance descriptors")
    provenance_by_key = {
        item.get("case_key"): item for item in provenance if isinstance(item, Mapping)
    }
    if len(provenance_by_key) != 40:
        raise ValueError("compact fixture provenance case_key coverage mismatch")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_rows):
        if not isinstance(value, dict) or set(value) != set(COLUMNS):
            raise ValueError(f"compact fixture row {index} schema mismatch")
        row = {column: value[column] for column in COLUMNS}
        key = row["case_key"]
        if not isinstance(key, str) or key in seen:
            raise ValueError(f"compact fixture row {index} has invalid case_key")
        seen.add(key)
        if row["polarization"] != "s":
            raise ValueError(f"{key}: Task034 production table must remain S-mainline")
        evidence = row["evidence_path"]
        if not isinstance(evidence, str):
            raise ValueError(f"{key}: evidence_path must be a provenance string")
        path = PurePosixPath(evidence)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{key}: evidence_path must be repository-relative")
        if not evidence.startswith("benchmarks/artifacts/"):
            raise ValueError(f"{key}: unexpected evidence provenance namespace")
        descriptor = _mapping(provenance_by_key.get(key))
        if descriptor.get("evidence_path") != evidence:
            raise ValueError(f"{key}: provenance evidence_path mismatch")
        if descriptor.get("source_sha") != row["source_sha"]:
            raise ValueError(f"{key}: provenance source_sha mismatch")
        artifact_sha = descriptor.get("artifact_sha256")
        if not isinstance(artifact_sha, str) or len(artifact_sha) != 64:
            raise ValueError(f"{key}: artifact_sha256 must be a 64-character digest")
        try:
            int(artifact_sha, 16)
        except ValueError as error:
            raise ValueError(f"{key}: artifact_sha256 is not hexadecimal") from error
        if not descriptor.get("field_source"):
            raise ValueError(f"{key}: provenance field_source is required")
        components = (
            row["fe_dofs"], row["external_aux_dofs"], row["modal_unknowns"]
        )
        if row["total_rows"] is not None and all(
            component is not None for component in components[:2]
        ):
            expected_rows = sum(int(component or 0) for component in components)
            if int(row["total_rows"]) != expected_rows:
                raise ValueError(f"{key}: total_rows decomposition mismatch")
        if row["factor_nnz"] is not None and row["method"] != "Full3D":
            raise ValueError(f"{key}: factor_nnz is only qualified for Full3D inventory")
        rows.append(row)
    return rows


def _validate_case093(root: Path, by_key: Mapping[str, Mapping[str, Any]]) -> None:
    summary = _load(root / CASE093_RELATIVE)
    for point in summary.get("points", []):
        if not isinstance(point, Mapping):
            raise ValueError("Case093 point must be an object")
        for source_key in ("full3d", "hybrid"):
            source = _mapping(point.get(source_key))
            key = f"case093_{point['key']}_{source_key}"
            row = by_key.get(key)
            if row is None:
                raise ValueError(f"missing compact Case093 row: {key}")
            official = _mapping(source.get("official_values"))
            evidence = _mapping(source.get("evidence"))
            resource = _mapping(source.get("resource"))
            checks = {
                "p": source.get("degree"),
                "h_nm": source.get("h_nm"),
                "MPI": source.get("mpi_size"),
                "polarization": source.get("polarization_kind"),
                "status": source.get("status"),
                "source_sha": _mapping(source.get("source")).get("commit_sha"),
                "R_total": official.get("R_total"),
                "T_total": official.get("T_total"),
                "A_balance": official.get("A_balance"),
                "A_volume": official.get("A_volume_total"),
                "true_relative_residual": source.get("true_relative_residual"),
                "peak_memory_gib": resource.get("peak_memory_gib"),
                "evidence_path": evidence.get("path"),
            }
            for field, expected in checks.items():
                _require_equal(f"{key}.{field}", row[field], expected)


def _validate_mpi(root: Path, by_key: Mapping[str, Mapping[str, Any]]) -> None:
    summary = _load(root / MPI_RELATIVE)
    expected_keys: set[str] = set()
    for method_key, method in _mapping(summary.get("methods")).items():
        identity = _mapping(_mapping(method).get("identity"))
        for comparison in _mapping(method).get("comparisons", []):
            mpi_size = comparison.get("mpi_size")
            key = f"mpi_p3_h5_{method_key}_mpi{mpi_size}"
            expected_keys.add(key)
            row = by_key.get(key)
            if row is None:
                raise ValueError(f"missing compact MPI identity row: {key}")
            _require_equal(f"{key}.MPI", row["MPI"], mpi_size)
            _require_equal(
                f"{key}.source_sha", row["source_sha"], identity.get("source_sha")
            )
            _require_equal(
                f"{key}.true_relative_residual",
                row["true_relative_residual"],
                comparison.get("true_relative_residual"),
            )
    actual_keys = {key for key in by_key if key.startswith("mpi_p3_h5_")}
    if actual_keys != expected_keys or len(expected_keys) != 8:
        raise ValueError("compact MPI identity coverage must be exactly 8 rows")


def _validate_supplemental(
    root: Path, by_key: Mapping[str, Mapping[str, Any]]
) -> None:
    for stem in ("p2_h1", "p3_h2", "p4_h3"):
        payload = _load(root / CASE092_RECORDS / f"{stem}_execution_outcome.json")
        scope = _mapping(payload.get("case")) or _mapping(payload.get("scope"))
        degree = int(scope["degree"])
        h_nm = float(scope["h_nm"])
        full = _mapping(payload.get("full3d"))
        gate = _load(root / CASE092_RECORDS / f"{stem}_resource_gate.json")
        gate_assembly = _mapping(gate.get("assembly_measurement"))
        elapsed = full.get("assembly_elapsed_seconds") or gate_assembly.get(
            "elapsed_seconds"
        )
        full_key = f"supplemental_p{degree}_h{h_nm:g}_full3d"
        full_row = by_key[full_key]
        for field, expected in {
            "total_rows": full.get("exact_rows"),
            "assembled_nnz": full.get("exact_assembled_nnz"),
            "assembly_seconds": elapsed,
            "total_seconds": elapsed,
            "peak_memory_gib": full.get("assembly_peak_memory_gib"),
        }.items():
            _require_equal(f"{full_key}.{field}", full_row[field], expected)
        hybrid = _mapping(payload.get("hybrid_m160")) or _mapping(payload.get("hybrid"))
        hybrid_key = f"supplemental_p{degree}_h{h_nm:g}_hybrid_m160"
        hybrid_row = by_key[hybrid_key]
        _require_equal(
            f"{hybrid_key}.peak_memory_gib",
            hybrid_row["peak_memory_gib"],
            hybrid.get("peak_memory_gib"),
        )


def build(root: Path) -> dict[str, Any]:
    root = root.resolve()
    fixture = _load(root / FIXTURE_RELATIVE)
    rows = _validate_fixture(fixture)
    by_key = {row["case_key"]: row for row in rows}
    _validate_case093(root, by_key)
    _validate_mpi(root, by_key)
    _validate_supplemental(root, by_key)
    return {
        "schema_version": "task034.all-model-results.v1",
        "record_type": "accepted_measured_and_formal_not_run_fact_table",
        "identity": {
            "is_pde_run": False,
            "source": str(FIXTURE_RELATIVE).replace("\\", "/"),
            "hermetic_no_artifact_reads": True,
            "polarization_mainline": "s",
            "R00_p_semantics": "cross-polarized p output under S incidence",
            "p_incidence_rerun_required": False,
            "factor_nnz_semantics": (
                "measured direct-factor inventory matrix_nnz_used; null when unavailable"
            ),
            "null_means": "not available in accepted evidence; never imputed",
        },
        "columns": COLUMNS,
        "row_count": len(rows),
        "rows": rows,
    }


def write_outputs(result: Mapping[str, Any], json_output: Path, csv_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with csv_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["rows"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.root)
    write_outputs(result, args.json_output, args.csv_output)
    print(json.dumps({"row_count": result["row_count"]}, indent=2))


if __name__ == "__main__":
    main()
