"""Read-only checker for the N1 local-spectral source/action evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np


SCHEMA = "task038.full3d.iterative.local-spectral-record.v1"
EXPECTED_PROFILE = "local_spectral_cell_patch_regional_oracle_v1"
EXPECTED_DEGREES = {2, 3}
EXPECTED_MESH_NM = 50.0
EXPECTED_WAVELENGTH_NM = 13.5
EXPECTED_THETA = 21.131
EXPECTED_PHI = 33.690
MODE_CAP = 8
REGIONAL_RANK_CAP = 16
CLASS_CAP = 32
ALGEBRA_LIMIT = 1.0e-11
MPI_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
POU_LIMIT = 1.0e-13
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(left) - np.asarray(right))
        / max(float(np.linalg.norm(np.asarray(right))), 1.0e-300)
    )


def _finite(values: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(values))))


def _artifact_path(raw_dir: Path, descriptor: dict[str, Any]) -> Path:
    relative = Path(str(descriptor["relative_path"]))
    path = (raw_dir / relative).resolve()
    if raw_dir.resolve() not in path.parents:
        raise ValueError("artifact escapes raw directory")
    return path


def _verify_file(path: Path, descriptor: dict[str, Any]) -> None:
    if not path.is_file():
        raise ValueError(f"missing artifact {path}")
    if int(path.stat().st_size) != int(descriptor["bytes"]):
        raise ValueError(f"artifact byte count mismatch for {path}")
    if _sha256(path) != str(descriptor["sha256"]):
        raise ValueError(f"artifact SHA256 mismatch for {path}")


def _check_identity(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    case = record.get("case")
    mpi_size = record.get("mpi_size")
    if record.get("schema") != SCHEMA:
        errors.append("schema mismatch")
    if record.get("stage") != "n1":
        errors.append("stage is not n1")
    if record.get("profile") != EXPECTED_PROFILE:
        errors.append("profile mismatch")
    if not isinstance(case, str) or not re.fullmatch(r"p[23]-mpi[12]", case):
        errors.append("case is not one of p2/p3 MPI1/MPI2")
    if mpi_size not in {1, 2}:
        errors.append("mpi_size is not 1 or 2")
    elif case != f"p{record.get('degree')}-mpi{mpi_size}":
        errors.append("case/degree/mpi identity mismatch")
    if record.get("degree") not in EXPECTED_DEGREES:
        errors.append("degree is not p2 or p3")
    if float(record.get("mesh_target_nm", float("nan"))) != EXPECTED_MESH_NM:
        errors.append("mesh target is not 50 nm")
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source facts are missing")
    else:
        expected = source.get("expected_sha")
        if not isinstance(expected, str) or not SHA40.fullmatch(expected):
            errors.append("expected source SHA is not lowercase 40-hex")
        for field in ("commit_sha_start", "commit_sha_end"):
            if source.get(field) != expected:
                errors.append(f"source {field} is not bound to expected SHA")
        if source.get("branch") != "codex/20260820-task38-extra-full3d-iterative-0p7nm":
            errors.append("source branch mismatch")
        if source.get("tracked_status_start") != "" or source.get("tracked_status_end") != "":
            errors.append("formal source tracked status is dirty")
        if source.get("clean_start") is not True or source.get("clean_end") is not True:
            errors.append("formal source is not clean at both boundaries")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime facts are missing")
    else:
        if runtime.get("qualified_activation") != "1":
            errors.append("qualified activation marker is not 1")
        if runtime.get("petsc_scalar_type") != "complex128":
            errors.append("PETSc scalar is not complex128")
        if runtime.get("petsc_int_type") != "int32":
            errors.append("PETSc integer type is not int32")
        executable = str(runtime.get("sys_executable", ""))
        if "/.venv/" not in executable or "/mnt/c/" in executable:
            errors.append("runtime executable is not the qualified Linux .venv")
    model = record.get("model")
    if not isinstance(model, dict):
        errors.append("model identity is missing")
    else:
        if float(model.get("wavelength_nm", float("nan"))) != EXPECTED_WAVELENGTH_NM:
            errors.append("wavelength identity mismatch")
        if abs(float(model.get("incident_theta_deg", float("nan"))) - EXPECTED_THETA) > 1.0e-12:
            errors.append("incident theta identity mismatch")
        if abs(float(model.get("incident_phi_deg", float("nan"))) - EXPECTED_PHI) > 1.0e-12:
            errors.append("incident phi identity mismatch")
        if not str(model.get("source_key_identity", "")).startswith("physical canonical"):
            errors.append("source key identity is missing")
    input_facts = record.get("input")
    if not isinstance(input_facts, dict):
        errors.append("input identity is missing")
    else:
        input_path = Path(str(input_facts.get("path", "")))
        if not input_path.is_file():
            errors.append("resolved input path is missing")
        elif _sha256(input_path) != input_facts.get("sha256"):
            errors.append("input SHA256 mismatch")
    return errors


def _check_forbidden(record: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    forbidden = record.get("forbidden")
    required = (
        "global_numeric_allgather",
        "global_aij_in_production",
        "global_schur",
        "global_factor",
        "per_rank_full_basis_replication",
    )
    if not isinstance(forbidden, dict) or any(forbidden.get(key) is not False for key in required):
        errors.append("record forbidden materialization audit is not explicitly false")
    for rank_fact in facts.get("rank_facts", []):
        patch_forbidden = rank_fact.get("patch_audit", {}).get("forbidden_objects")
        if not isinstance(patch_forbidden, dict) or any(
            patch_forbidden.get(key) is not False
            for key in (
                "global_numeric_allgather",
                "global_aij",
                "global_schur",
                "static_condensation",
                "trace_harmonic_backend",
                "per_patch_retained_dense_block",
            )
        ):
            errors.append("patch forbidden audit is missing or true")
        regional = rank_fact.get("regional_audit", {})
        if regional.get("global_numeric_allgather") is not False:
            errors.append("regional numeric allgather audit is not false")
        if regional.get("regional_dense_row_operator_materialized") is not False:
            errors.append("regional dense row operator audit is not false")
    return errors


def _check_numeric_facts(record: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    rank_facts = facts.get("rank_facts")
    if not isinstance(rank_facts, list) or len(rank_facts) != int(record["mpi_size"]):
        return {"errors": ["rank facts do not match MPI size"]}
    patch_count = sum(int(item.get("owned_patch_count", -1)) for item in rank_facts)
    class_counts = {
        int(item.get("patch_audit", {}).get("class_count", -1))
        for item in rank_facts
    }
    if len(class_counts) != 1 or next(iter(class_counts)) <= 0:
        errors.append("class count facts are not consistent")
    class_count = next(iter(class_counts), -1)
    if class_count > CLASS_CAP:
        errors.append("class count exceeds 32")
    factor_count = sum(
        int(item.get("patch_audit", {}).get("owner_factor_count", -1))
        for item in rank_facts
    )
    if factor_count != class_count:
        errors.append("owner factor count is not exactly one per class")
    maxima = {}
    for field in (
        "B0_hermitian_relative_defect",
        "M_local_hermitian_relative_defect",
        "gradient_m_gram_relative_defect_max",
        "projected_eigen_residual_max",
        "fixed_solve_residual_max",
        "restriction_prolongation_adjoint_relative_error_max",
        "pou_closure_relative_error",
    ):
        values = [float(item.get("patch_audit", {}).get(field, float("nan"))) for item in rank_facts]
        maxima[field] = max(values, default=float("nan"))
        if not np.isfinite(maxima[field]):
            errors.append(f"missing/nonfinite {field}")
    for field in (
        "B0_hermitian_relative_defect",
        "M_local_hermitian_relative_defect",
        "gradient_m_gram_relative_defect_max",
        "projected_eigen_residual_max",
        "fixed_solve_residual_max",
    ):
        if maxima[field] > ALGEBRA_LIMIT:
            errors.append(f"{field}={maxima[field]} exceeds {ALGEBRA_LIMIT}")
    for field in ("restriction_prolongation_adjoint_relative_error_max", "pou_closure_relative_error"):
        if maxima[field] > POU_LIMIT:
            errors.append(f"{field}={maxima[field]} exceeds {POU_LIMIT}")
    if min(float(item.get("patch_audit", {}).get("B0_min_eigenvalue", -1.0)) for item in rank_facts) <= 0.0:
        errors.append("B0 is not positive")
    if min(float(item.get("patch_audit", {}).get("M_local_min_eigenvalue", -1.0)) for item in rank_facts) <= 0.0:
        errors.append("local mass is not positive")
    if min(int(item.get("patch_audit", {}).get("gradient_rank_min", -1)) for item in rank_facts) != 3:
        errors.append("gradient candidate rank is not three")
    if any(not item.get("patch_audit", {}).get("dense_workspace_released", False) for item in rank_facts):
        errors.append("dense local workspace was not released")
    regional_residual = max(
        float(item.get("regional_audit", {}).get("regional_projected_eigen_residual_max", float("nan")))
        for item in rank_facts
    )
    regional_mass = max(
        float(item.get("regional_audit", {}).get("regional_mass_orthogonality_max", float("nan")))
        for item in rank_facts
    )
    if not np.isfinite(regional_residual) or not np.isfinite(regional_mass):
        errors.append("regional algebra facts are missing/nonfinite")
    if regional_residual > ALGEBRA_LIMIT or regional_mass > ALGEBRA_LIMIT:
        errors.append("regional algebra exceeds 1e-11")
    selected_mode_count = int(record.get("local_spectral", {}).get("selected_mode_count_max", -1))
    if selected_mode_count != MODE_CAP:
        errors.append("local selected mode count is not fixed eight")
    if any(int(item.get("local_mode_count", -1)) != MODE_CAP for item in rank_facts):
        errors.append("rank local selected mode count is not eight")
    if any(not bool(item.get("mode_repeat_exact", False)) for item in rank_facts):
        errors.append("mode repeat is not exact")
    if int(facts.get("mode_cap", -1)) != MODE_CAP or int(facts.get("regional_rank_cap", -1)) != REGIONAL_RANK_CAP:
        errors.append("frozen mode/rank caps are missing")
    return {
        "errors": errors,
        "patch_count": patch_count,
        "class_count": class_count,
        "owner_factor_count": factor_count,
        "maxima": maxima,
        "regional_projected_eigen_residual_max": regional_residual,
        "regional_mass_orthogonality_max": regional_mass,
        "regional_projector_diagnostic": "not a hard Gate",
    }


def _read_canonical(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw_dir = Path(str(record["raw_dir"])).resolve()
    manifest_desc = record["source_action"]["manifest"]
    manifest_path = _artifact_path(raw_dir, manifest_desc["file"])
    _verify_file(manifest_path, manifest_desc["file"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected_mpi = int(record["mpi_size"])
    shards = manifest.get("per_rank_shards")
    if manifest.get("mpi_size") != expected_mpi or not isinstance(shards, list) or len(shards) != expected_mpi:
        errors.append("canonical manifest MPI/shard count mismatch")
        return {}, errors
    if manifest.get("role") != "full_space_source_action_owner_local_shards":
        errors.append("canonical manifest role mismatch")
    if manifest.get("key_encoding") != "canonical_key_json_bytes" or manifest.get("dtype") != "complex128":
        errors.append("canonical manifest encoding/dtype mismatch")
    shard_data = []
    for descriptor in shards:
        try:
            path = _artifact_path(raw_dir, descriptor)
            _verify_file(path, descriptor)
            with np.load(path, allow_pickle=False) as data:
                names = {"key_json", "source", "action", "source_repeat", "action_repeat"}
                if set(data.files) != names:
                    raise ValueError("canonical shard fields mismatch")
                keys = tuple(str(value) for value in data["key_json"].tolist())
                arrays = {name: np.asarray(data[name], dtype=np.complex128) for name in names - {"key_json"}}
            if len(keys) != len(set(keys)):
                raise ValueError("canonical shard contains duplicate keys")
            if any(array.shape != (len(keys),) for array in arrays.values()):
                raise ValueError("canonical shard vector shape mismatch")
            if any(not _finite(array) for array in arrays.values()):
                raise ValueError("canonical shard contains nonfinite values")
            shard_data.append((keys, arrays))
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return {}, errors
    key_sets = [set(keys) for keys, _arrays in shard_data]
    if any(keys != key_sets[0] for keys in key_sets[1:]):
        errors.append("canonical shard key sets differ")
        return {}, errors
    keys = tuple(sorted(key_sets[0]))
    merged: dict[str, np.ndarray] = {}
    for name in ("source", "action", "source_repeat", "action_repeat"):
        values = []
        for shard_keys, arrays in shard_data:
            index = {key: position for position, key in enumerate(shard_keys)}
            values.append(np.asarray([arrays[name][index[key]] for key in keys]))
        if name in {"source", "source_repeat"}:
            first = values[0]
            if any(not np.array_equal(first, value) for value in values[1:]):
                errors.append(f"{name} differs between rank shards")
            merged[name] = first
        else:
            merged[name] = np.sum(np.stack(values, axis=0), axis=0)
    return {"keys": keys, **merged}, errors


def _check_record_impl(record_path: Path) -> dict[str, Any]:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("record is not an object")
    errors = _check_identity(record)
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    facts_desc = record.get("local_spectral", {}).get("facts_artifact")
    if not isinstance(facts_desc, dict):
        errors.append("facts artifact descriptor is missing")
        facts = {}
    else:
        facts_path = _artifact_path(raw_dir, facts_desc)
        try:
            _verify_file(facts_path, facts_desc)
            facts = json.loads(facts_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(str(exc))
            facts = {}
    numeric = _check_numeric_facts(record, facts) if facts else {"errors": ["facts unavailable"]}
    errors.extend(numeric.get("errors", []))
    errors.extend(_check_forbidden(record, facts))
    try:
        canonical, canonical_errors = _read_canonical(record)
    except Exception as exc:
        canonical, canonical_errors = {}, [str(exc)]
    errors.extend(canonical_errors)
    source_action = {}
    if record.get("source_action", {}).get("role") != "full_space_source_action_owner_local_shards":
        errors.append("record source/action role mismatch")
    if canonical:
        source_action = {
            "key_count": len(canonical["keys"]),
            "source_finite": _finite(canonical["source"]),
            "action_finite": _finite(canonical["action"]),
            "source_repeat_relative": _relative(canonical["source"], canonical["source_repeat"]),
            "action_repeat_relative": _relative(canonical["action"], canonical["action_repeat"]),
            "action_repeat_exact": bool(np.array_equal(canonical["action"], canonical["action_repeat"])),
        }
        if not source_action["source_finite"] or not source_action["action_finite"]:
            errors.append("canonical source/action is nonfinite")
        if source_action["source_repeat_relative"] > REPEAT_LIMIT or source_action["action_repeat_relative"] > REPEAT_LIMIT:
            errors.append("canonical repeat exceeds 1e-13")
        if not source_action["action_repeat_exact"]:
            errors.append("canonical action repeat is not exact")
        if int(facts.get("source_packet_count", -1)) != source_action["key_count"]:
            errors.append("facts/source packet count mismatch")
    ufl = record.get("serial_assembled_oracle")
    ufl_result = {"status": ufl.get("status") if isinstance(ufl, dict) else None}
    if int(record.get("mpi_size", -1)) == 1:
        if not isinstance(ufl, dict) or ufl.get("status") != "measured":
            errors.append("MPI1 assembled UFL oracle is not measured")
        else:
            try:
                path = _artifact_path(raw_dir, ufl["artifact"])
                _verify_file(path, ufl["artifact"])
                with np.load(path, allow_pickle=False) as data:
                    keys = tuple(str(value) for value in data["key_json"].tolist())
                    values = np.asarray(data["action"], dtype=np.complex128)
                if tuple(keys) != tuple(canonical.get("keys", ())):
                    errors.append("MPI1 UFL key set differs from canonical action")
                ufl_relative = _relative(canonical["action"], values)
                ufl_result["relative_error"] = ufl_relative
                if ufl_relative > ALGEBRA_LIMIT:
                    errors.append(f"UFL action relative error {ufl_relative} exceeds {ALGEBRA_LIMIT}")
            except Exception as exc:
                errors.append(str(exc))
    elif not isinstance(ufl, dict) or ufl.get("boundary") != "mpi2_distributed_local_cell_action_only; independent assembled UFL oracle is MPI1-only":
        errors.append("MPI2 assembled UFL boundary is not exact")
    return {
        "record": str(record_path),
        "case": record.get("case"),
        "mpi_size": record.get("mpi_size"),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "gates": {
            "identity": not bool(_check_identity(record)),
            "local_algebra": not bool(numeric.get("errors")),
            "forbidden": not bool(_check_forbidden(record, facts)),
            "canonical_source_action": not bool(canonical_errors),
            "serial_ufl": not any("UFL" in error or "oracle" in error for error in errors),
        },
        "numeric": numeric,
        "source_action": source_action,
        "serial_assembled_oracle": ufl_result,
        "regional_projector_gate": "diagnostic_only_not_a_hard_gate",
        "raw_dir": str(raw_dir),
        "record_sha256": _sha256(record_path),
    }


def check_worker_record(record_path: str | Path) -> dict[str, Any]:
    """Return a fail-closed compact result without importing the solver."""

    path = Path(record_path).resolve()
    try:
        return _check_record_impl(path)
    except Exception as exc:
        return {
            "record": str(path),
            "status": "FAIL",
            "errors": [f"checker exception: {type(exc).__name__}: {exc}"],
            "regional_projector_gate": "diagnostic_only_not_a_hard_gate",
        }


def _compare_pair(left_path: Path, right_path: Path) -> dict[str, Any]:
    left = check_worker_record(left_path)
    right = check_worker_record(right_path)
    errors = list(left.get("errors", [])) + list(right.get("errors", []))
    if left.get("status") != "PASS" or right.get("status") != "PASS":
        errors.append("individual record is not PASS")
        return {"status": "FAIL", "errors": errors, "left": left, "right": right}
    left_record = json.loads(left_path.read_text(encoding="utf-8"))
    right_record = json.loads(right_path.read_text(encoding="utf-8"))
    if left_record["degree"] != right_record["degree"] or left_record["case"].split("-")[0] != right_record["case"].split("-")[0]:
        errors.append("MPI pair degree mismatch")
    left_canonical, left_errors = _read_canonical(left_record)
    right_canonical, right_errors = _read_canonical(right_record)
    errors.extend(left_errors + right_errors)
    if left_canonical and right_canonical:
        if left_canonical["keys"] != right_canonical["keys"]:
            errors.append("MPI source/action canonical keys differ")
        else:
            source_relative = _relative(left_canonical["source"], right_canonical["source"])
            action_relative = _relative(left_canonical["action"], right_canonical["action"])
            if source_relative > MPI_LIMIT:
                errors.append(f"MPI source relative error {source_relative} exceeds {MPI_LIMIT}")
            if action_relative > MPI_LIMIT:
                errors.append(f"MPI action relative error {action_relative} exceeds {MPI_LIMIT}")
    else:
        source_relative = float("nan")
        action_relative = float("nan")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "source_relative_error": source_relative,
        "action_relative_error": action_relative,
        "hard_gate": "canonical full-space source/action <= 1e-12",
        "regional_projector_gate": "diagnostic_only_not_a_hard_gate",
        "left": left,
        "right": right,
    }


def check_aggregate(record_paths: list[str | Path]) -> dict[str, Any]:
    paths = [Path(path).resolve() for path in record_paths]
    individual = [check_worker_record(path) for path in paths]
    errors = [error for result in individual for error in result.get("errors", [])]
    if len(paths) != 4:
        errors.append("aggregate requires exactly four records")
    cases = {result.get("case") for result in individual}
    if cases != {"p2-mpi1", "p2-mpi2", "p3-mpi1", "p3-mpi2"}:
        errors.append("aggregate case set is not the frozen four cases")
    pairs = []
    for degree in (2, 3):
        left = next((path for path in paths if path.name == f"n1_local_spectral_p{degree}_mpi1_v1.json"), None)
        right = next((path for path in paths if path.name == f"n1_local_spectral_p{degree}_mpi2_v1.json"), None)
        if left is None or right is None:
            errors.append(f"missing p{degree} MPI pair")
        else:
            pair = _compare_pair(left, right)
            pairs.append(pair)
            errors.extend(pair.get("errors", []))
    return {
        "schema": "task038.n1.local-spectral-aggregate.v1",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "individual": individual,
        "pairs": pairs,
        "hard_gate": "canonical full-space source/action <= 1e-12; repeat <= 1e-13",
        "regional_diagnostic_debt": {
            "projector_relative": 1.59451e-11,
            "packet_relative": 1.66085e-10,
            "classification": "measured_diagnostic_debt_not_hard_gate",
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record")
    parser.add_argument("--output")
    parser.add_argument("--aggregate-records", nargs=4)
    parser.add_argument("--aggregate-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.record:
        if not args.output:
            raise SystemExit("--record requires --output")
        result = check_worker_record(args.record)
        Path(args.output).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0 if result.get("status") == "PASS" else 1
    if args.aggregate_records:
        if not args.aggregate_output:
            raise SystemExit("--aggregate-records requires --aggregate-output")
        result = check_aggregate(args.aggregate_records)
        Path(args.aggregate_output).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0 if result.get("status") == "PASS" else 1
    raise SystemExit("provide --record or --aggregate-records")


if __name__ == "__main__":
    raise SystemExit(main())
