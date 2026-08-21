"""Independent, read-only checker for the R3 residual authority record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    compare_canonical_packets,
    read_canonical_manifest,
    read_canonical_packet_shards,
)


R3_SCHEMA = "task038.full3d.iterative.r3.residual-record.v1"
R3_CHECK_SCHEMA = "task038.full3d.iterative.r3.check.v1"
R3_PROFILE = "full3d_scalable_v1"
R3_SOURCE_NAME = "CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE"
EXPECTED_MODE_COUNT = 80
EXPECTED_MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
EXPECTED_INPUT_BYTES = 2119
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_BYTES = 4076
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
OLD_SOURCE_SHA = "41cbbd454eb8336d9ea5378ed618447acfc60aac"
OLD_SOLUTION_FACTS = {
    "file_sha256": "d2a5a7e7b94a73d5212bc693d43282cace2883aadd0bb66780a3f8ae7b9e535e",
    "array_sha256": "620b5e496536d69c0bc471731b09a15424c29044e6836881ccd85340cbee0c39",
    "shape": [173802],
    "dtype": "complex128",
}
ACTION_LIMIT = 1.0e-11
ROUNDTRIP_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-12
SWAP_REQUIRED = 0


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _read_artifact(raw_dir: Path, descriptor: Mapping[str, Any], expected_role: str) -> tuple[tuple[Any, ...], dict[str, Any]]:
    errors: list[str] = []
    if not isinstance(descriptor, Mapping):
        return (), {"errors": ["canonical artifact descriptor is not an object"]}
    relative = descriptor.get("manifest_relative_path")
    if not isinstance(relative, str):
        return (), {"errors": ["canonical manifest path is missing"]}
    path = raw_dir / relative
    if not path.is_file():
        return (), {"errors": [f"canonical manifest is missing: {path}"]}
    actual_sha = _sha256_path(path)
    if actual_sha != descriptor.get("manifest_sha256"):
        errors.append(f"canonical manifest SHA mismatch: {relative}")
    try:
        manifest = read_canonical_manifest(path, actual_sha)
        shards = tuple(path.parent / item["filename"] for item in manifest["per_rank_shards"])
        packets = read_canonical_packet_shards(
            shards,
            tuple(item["file_sha256"] for item in manifest["per_rank_shards"]),
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return (), {"errors": errors + [f"canonical manifest read failed: {exc}"]}
    if manifest.get("role") != expected_role:
        errors.append(f"canonical role mismatch for {relative}")
    if int(manifest.get("global_summed_packet_count", -1)) != len(packets):
        errors.append(f"canonical packet count mismatch for {relative}")
    if int(descriptor.get("packet_count", -1)) != len(packets):
        errors.append(f"descriptor packet count mismatch for {relative}")
    duplicate = len(packets) - len({key for key, _value in packets})
    finite = all(np.isfinite(complex(value)) for _key, value in packets)
    if duplicate != int(descriptor.get("duplicate_count", -1)):
        errors.append(f"canonical duplicate count mismatch for {relative}")
    if not finite or descriptor.get("finite") is not True:
        errors.append(f"canonical finite gate failed for {relative}")
    return packets, {
        "path": str(path),
        "manifest_sha256": actual_sha,
        "packet_count": len(packets),
        "duplicate_count": duplicate,
        "finite": finite,
        "norm": float(np.linalg.norm([complex(value) for _key, value in packets])),
        "errors": errors,
    }


def _check_file_artifact(
    raw_dir: Path,
    descriptor: Mapping[str, Any] | None,
    expected_bytes: int,
    expected_sha: str,
    label: str,
    errors: list[str],
) -> bool:
    if not isinstance(descriptor, Mapping):
        errors.append(f"{label} artifact descriptor is missing")
        return False
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str):
        errors.append(f"{label} artifact path is missing")
        return False
    path = raw_dir / relative
    if not path.is_file():
        errors.append(f"{label} artifact is missing")
        return False
    actual_bytes = int(path.stat().st_size)
    actual_sha = _sha256_path(path)
    passed = (
        actual_bytes == int(expected_bytes)
        and actual_sha == expected_sha
        and descriptor.get("bytes") == actual_bytes
        and descriptor.get("sha256") == actual_sha
    )
    if not passed:
        errors.append(f"{label} artifact identity failed")
    return passed


def _subtract_packets(
    left: Iterable[tuple[Any, complex]], right: Iterable[tuple[Any, complex]]
) -> tuple[tuple[Any, complex], ...] | None:
    left_rows = tuple(left)
    right_rows = tuple(right)
    left_map = {key: complex(value) for key, value in left_rows}
    right_map = {key: complex(value) for key, value in right_rows}
    if len(left_map) != len(left_rows) or len(right_map) != len(right_rows):
        return None
    if set(left_map) != set(right_map):
        return None
    return tuple((key, left_map[key] - right_map[key]) for key in sorted(left_map, key=repr))


def _comparison(left: Iterable[tuple[Any, complex]], right: Iterable[tuple[Any, complex]], tolerance: float) -> dict[str, Any]:
    return compare_canonical_packets(left, right, relative_tolerance=tolerance)


def _check_old_solution(record: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    facts = record.get("historical_solution")
    if record.get("mpi", {}).get("size") != 1:
        return {"status": "not_read_mpi2"}
    if not isinstance(facts, Mapping):
        errors.append("MPI1 historical solution facts are missing")
        return {"status": "missing"}
    path_value = facts.get("path")
    if not isinstance(path_value, str) or not Path(path_value).is_file():
        errors.append("MPI1 historical solution file is missing")
        return {"status": "missing"}
    path = Path(path_value)
    try:
        array = np.asarray(np.load(path, allow_pickle=False))
    except (OSError, ValueError) as exc:
        errors.append(f"historical solution cannot be read: {exc}")
        return {"status": "unreadable"}
    observed = {
        "file_sha256": _sha256_path(path),
        "array_sha256": _array_sha256(array),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finite": bool(np.all(np.isfinite(array))),
    }
    for key, expected in OLD_SOLUTION_FACTS.items():
        if observed.get(key) != expected:
            errors.append(f"historical solution {key} mismatch")
    return observed


def _check_mpi1_primal_input(record: Mapping[str, Any], errors: list[str]) -> bool:
    if record.get("mpi", {}).get("size") != 2:
        return True
    facts = record.get("mpi", {}).get("mpi1_primal_manifest")
    if not isinstance(facts, Mapping):
        errors.append("MPI2 primal input manifest facts are missing")
        return False
    path_value = facts.get("path")
    if not isinstance(path_value, str):
        errors.append("MPI2 primal input manifest path is missing")
        return False
    path = Path(path_value)
    if not path.is_file():
        errors.append("MPI2 primal input manifest is missing")
        return False
    try:
        manifest = read_canonical_manifest(path, facts.get("sha256"))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"MPI2 primal input manifest is invalid: {exc}")
        return False
    passed = (
        manifest.get("role") == "full_fe"
        and int(manifest.get("mpi_size", 0)) == 1
        and int(manifest.get("global_summed_packet_count", -1))
        == int(facts.get("packet_count", -2))
    )
    if not passed:
        errors.append("MPI2 primal input manifest identity failed")
    return passed


def check_record(record: Mapping[str, Any], record_path: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    gates: dict[str, bool] = {}
    if record.get("schema") != R3_SCHEMA:
        errors.append("R3 record schema mismatch")
    if record.get("profile") != R3_PROFILE:
        errors.append("R3 profile mismatch")
    if record.get("source_name") != R3_SOURCE_NAME:
        errors.append("R3 source name mismatch")
    path_a = record.get("path_a", {})
    gates["path_a_not_qualified"] = (
        path_a.get("status") == "NOT_QUALIFIED"
        and path_a.get("fit_or_scaling") == "forbidden_and_not_attempted"
    )
    if not gates["path_a_not_qualified"]:
        errors.append("Path A is not explicitly NOT_QUALIFIED")
    path_b = record.get("path_b", {})
    if (
        path_b.get("source_name") != R3_SOURCE_NAME
        or path_b.get("old_source_sha") != OLD_SOURCE_SHA
        or path_b.get("empirical_scaling") is not False
    ):
        errors.append("Path B source boundary or scaling contract is invalid")
    source = record.get("source", {})
    expected_sha = source.get("expected_sha")
    gates["source_clean_identity"] = bool(
        isinstance(expected_sha, str)
        and len(expected_sha) == 40
        and expected_sha.islower()
        and all(char in "0123456789abcdef" for char in expected_sha)
        and source.get("commit_sha_start") == expected_sha
        and source.get("commit_sha_end") == expected_sha
        and source.get("tracked_status_start") == ""
        and source.get("tracked_status_end") == ""
    )
    if not gates["source_clean_identity"]:
        errors.append("source identity is not one clean expected SHA")

    input_facts = record.get("input", {})
    gates["frozen_input"] = (
        input_facts.get("template_bytes") == EXPECTED_INPUT_BYTES
        and input_facts.get("template_sha256") == EXPECTED_INPUT_SHA256
        and input_facts.get("resolved_config_bytes") == EXPECTED_RESOLVED_BYTES
        and input_facts.get("resolved_config_sha256") == EXPECTED_RESOLVED_SHA256
        and input_facts.get("physical_model_sha256") == EXPECTED_PHYSICAL_MODEL_SHA256
    )
    if not gates["frozen_input"]:
        errors.append("frozen input identity failed")
    model = record.get("model", {})
    gates["dynamic_mode_identity"] = (
        model.get("wavelength_nm") == 13.5
        and model.get("nedelec_degree") == 6
        and model.get("mesh_target_nm") == 10.0
        and model.get("mode_count") == EXPECTED_MODE_COUNT
        and model.get("mode_manifest_sha256") == EXPECTED_MODE_MANIFEST_SHA256
    )
    if not gates["dynamic_mode_identity"]:
        errors.append("dynamic mode identity failed")

    raw_value = record.get("raw_dir")
    raw_dir = Path(raw_value) if isinstance(raw_value, str) else None
    if raw_dir is None:
        errors.append("raw_dir is missing")
        raw_dir = Path(".")
    artifacts = record.get("artifacts", {})
    gates["raw_input_identity"] = (
        _check_file_artifact(
            raw_dir,
            artifacts.get("input_template"),
            EXPECTED_INPUT_BYTES,
            EXPECTED_INPUT_SHA256,
            "input template",
            errors,
        )
        and _check_file_artifact(
            raw_dir,
            artifacts.get("resolved_config"),
            EXPECTED_RESOLVED_BYTES,
            EXPECTED_RESOLVED_SHA256,
            "resolved config",
            errors,
        )
        and _check_file_artifact(
            raw_dir,
            artifacts.get("mode_manifest"),
            86377,
            EXPECTED_MODE_MANIFEST_SHA256,
            "mode manifest",
            errors,
        )
    )
    if not gates["raw_input_identity"]:
        errors.append("raw input/mode artifact identity failed")
    states: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for label, role in (
        ("primal_source", "full_fe"),
        ("primal_roundtrip", "full_fe"),
        ("current_rhs", "full_fe_dual"),
        ("action", "full_fe_dual"),
        ("action_repeat", "full_fe_dual"),
        ("residual", "full_fe_dual"),
    ):
        descriptor = artifacts.get(label)
        if descriptor is None:
            if label == "primal_roundtrip" and record.get("mpi", {}).get("size") == 2:
                states[label] = ((), {"status": "not_run_mpi2", "errors": []})
                continue
            errors.append(f"artifact descriptor missing: {label}")
            states[label] = ((), {"errors": ["missing"]})
            continue
        states[label] = _read_artifact(raw_dir, descriptor, role)
        errors.extend(states[label][1].get("errors", []))

    primal = states["primal_source"]
    roundtrip = states["primal_roundtrip"]
    if record.get("mpi", {}).get("size") == 1:
        comparison = _comparison(primal[0], roundtrip[0], ROUNDTRIP_LIMIT)
        gates["primal_roundtrip"] = bool(comparison["pass"])
        derived_roundtrip = comparison
    else:
        gates["primal_roundtrip"] = True
        derived_roundtrip = {"status": "checked_by_cross_mpi_pair"}
    if not gates["primal_roundtrip"]:
        errors.append("historical primal canonical roundtrip gate failed")

    rhs, action, repeat, residual = (
        states["current_rhs"],
        states["action"],
        states["action_repeat"],
        states["residual"],
    )
    action_repeat_comparison = _comparison(action[0], repeat[0], REPEAT_LIMIT)
    gates["action_repeat"] = bool(action_repeat_comparison["pass"])
    if not gates["action_repeat"]:
        errors.append("current action repeat gate failed")
    recomputed = _subtract_packets(rhs[0], action[0])
    if recomputed is None:
        residual_comparison = {"pass": False, "reason": "RHS/action packet keys do not close"}
    else:
        residual_comparison = _comparison(recomputed, residual[0], ACTION_LIMIT)
    gates["residual_recompute"] = bool(residual_comparison.get("pass"))
    if not gates["residual_recompute"]:
        errors.append("current residual recomputation gate failed")
    gates["finite_nonzero"] = all(
        facts.get("finite") is True and facts.get("norm", 0.0) > 0.0
        for _packets, facts in (primal, rhs, action, repeat, residual)
        if not facts.get("status", "").startswith("not_run")
    )
    if not gates["finite_nonzero"]:
        errors.append("finite/nonzero canonical gate failed")

    observations = record.get("observations", {})
    telemetry = observations.get("apply_telemetry", [])
    gates["apply_and_swap"] = (
        observations.get("apply_count") == 2
        and len(telemetry) == 2
        and all(
            int(item.get("rank_max_current_swap_bytes", -1)) == SWAP_REQUIRED
            for item in telemetry
        )
    )
    if not gates["apply_and_swap"]:
        errors.append("apply count or swap gate failed")
    operator = record.get("operator", {})
    audit = operator.get("audit", {})
    operator_artifact = operator.get("audit_artifact")
    operator_path = (
        raw_dir / operator_artifact.get("relative_path", "")
        if isinstance(operator_artifact, Mapping)
        else raw_dir / "missing"
    )
    raw_operator = None
    if operator_path.is_file():
        try:
            raw_operator = json.loads(operator_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw_operator = None
    gates["operator_contract"] = bool(
        isinstance(raw_operator, Mapping)
        and operator.get("audit_sha256") == _sha256_path(operator_path)
        and isinstance(operator_artifact, Mapping)
        and operator_artifact.get("sha256") == _sha256_path(operator_path)
        and raw_operator == audit
    )
    gates["operator_contract"] = bool(
        gates["operator_contract"]
        and audit.get("operator") == "A_volume_plus_dynamic_DtN"
        and audit.get("t4_transmission_included") is False
        and audit.get("global_aij_materialized") is False
        and audit.get("global_schur_materialized") is False
        and audit.get("ksp_created") is False
        and audit.get("numeric_allgather") is False
    )
    if not gates["operator_contract"]:
        errors.append("current physical operator contract failed")
    gates["no_pde"] = record.get("pde_solved") is False and record.get("ksp_created") is False
    if not gates["no_pde"]:
        errors.append("R3 action-only/no-KSP contract failed")
    old_solution = _check_old_solution(record, errors)
    gates["mpi1_primal_input"] = _check_mpi1_primal_input(record, errors)
    if record.get("mpi", {}).get("size") == 1:
        gates["old_solution_identity"] = not any(
            text.startswith("historical solution") or text.startswith("MPI1 historical")
            for text in errors
        )
    else:
        gates["old_solution_identity"] = True
    status = "pass" if not errors and all(gates.values()) else "fail"
    return {
        "schema": R3_CHECK_SCHEMA,
        "status": status,
        "record": str(record_path) if record_path is not None else None,
        "errors": errors,
        "gates": gates,
        "derived": {
            "primal_roundtrip": derived_roundtrip,
            "action_repeat": action_repeat_comparison,
            "residual_recompute": residual_comparison,
            "old_solution": old_solution,
            "source_name": record.get("source_name"),
        },
    }


def check_record_path(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema": R3_CHECK_SCHEMA, "status": "fail", "errors": [str(exc)], "gates": {}}
    return check_record(record, path)


def check_pair(first_path: Path, second_path: Path) -> dict[str, Any]:
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    first_check = check_record(first, first_path)
    second_check = check_record(second, second_path)
    errors = list(first_check["errors"]) + list(second_check["errors"])
    if first.get("mpi", {}).get("size") != 1 or second.get("mpi", {}).get("size") != 2:
        errors.append("R3 pair must be MPI1 followed by MPI2")
    if first.get("source", {}).get("expected_sha") != second.get("source", {}).get("expected_sha"):
        errors.append("R3 pair source SHA differs")
    first_primal = first.get("artifacts", {}).get("primal_source", {})
    second_input = second.get("mpi", {}).get("mpi1_primal_manifest", {})
    if (
        not isinstance(first_primal, Mapping)
        or not isinstance(second_input, Mapping)
        or second_input.get("sha256") != first_primal.get("manifest_sha256")
    ):
        errors.append("MPI2 primal input is not hash-bound to the MPI1 mapped solution manifest")
    cross: dict[str, Any] = {}
    for label in ("primal_source", "current_rhs", "action", "action_repeat", "residual"):
        left_descriptor = first.get("artifacts", {}).get(label)
        right_descriptor = second.get("artifacts", {}).get(label)
        try:
            left, _left_facts = _read_artifact(Path(first["raw_dir"]), left_descriptor, "full_fe" if label == "primal_source" else "full_fe_dual")
            right, _right_facts = _read_artifact(Path(second["raw_dir"]), right_descriptor, "full_fe" if label == "primal_source" else "full_fe_dual")
            cross[label] = _comparison(left, right, ROUNDTRIP_LIMIT)
        except (TypeError, KeyError, ValueError) as exc:
            cross[label] = {"pass": False, "reason": str(exc)}
        if not cross[label].get("pass"):
            errors.append(f"cross-MPI {label} canonical identity failed")
    status = "pass" if not errors else "fail"
    return {
        "schema": R3_CHECK_SCHEMA,
        "status": status,
        "errors": errors,
        "individual": {"mpi1": first_check, "mpi2": second_check},
        "cross_mpi": cross,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R3 independent residual checker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", type=Path)
    group.add_argument("--pair", nargs=2, type=Path, metavar=("MPI1_RECORD", "MPI2_RECORD"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = (
        check_record_path(args.record)
        if args.record is not None
        else check_pair(args.pair[0], args.pair[1])
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
