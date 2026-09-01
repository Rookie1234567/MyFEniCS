"""Independent, read-only checker for V15 F1 selector and real-oracle records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np


SCHEMA = "task038.v15.floquet-f1-selector.record.v1"
REAL_SCHEMA = "task038.v15.floquet-f1-real-small.record.v1"
CHECKER_SCHEMA = "task038.v15.floquet-f1.checker.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
SELECTOR_SCHEMA = "task038.v15.floquet-selection.v1"
SELECTOR_POLICY = "eligible_class_filter__normalized_abs_beta_ascending__mode_index_tiebreak"
SELECTOR_PAYLOAD_SHA256 = "7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3"
PMG_SCHEMA = "task038.same_mesh_hcurl_pmg.global.v1"
PMG_METHOD = "same_mesh_hcurl_pmg_v1"
PMG_LEVELS = [3, 1]
REPO_ROOT = Path(__file__).resolve().parents[1]
LEXICAL_PYTHON = str(REPO_ROOT / ".venv/bin/python")
LEXICAL_PREFIX = str(REPO_ROOT / ".venv")
SELECTED = (
    38,
    39,
    72,
    73,
    76,
    77,
    32,
    33,
    36,
    37,
    40,
    41,
    0,
    1,
    42,
    43,
    46,
    47,
    2,
    3,
    6,
    7,
    74,
    75,
    34,
    35,
    66,
    67,
    70,
    71,
    26,
    27,
)


def _complex_value(value: object, name: str) -> complex:
    if isinstance(value, dict):
        if set(value) != {"real", "imag"}:
            raise ValueError(f"{name} keys")
        result = complex(value["real"], value["imag"])
    else:
        result = complex(value)
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"{name} finite")
    return result


def _mode_facts(manifest: dict) -> list[dict]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest object")
    wavelength_nm = float(manifest["wavelength_nm"])
    if not math.isfinite(wavelength_nm) or wavelength_nm <= 0:
        raise ValueError("wavelength_nm")
    k0 = 2.0 * math.pi / wavelength_nm
    rows = manifest["modes"]
    if not isinstance(rows, list) or len(rows) != 80:
        raise ValueError("mode count")
    facts = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("mode row")
        required = {
            "mode_index",
            "classification",
            "side",
            "polarization",
            "beta",
            "refractive_index",
        }
        if set(row) != required:
            raise ValueError("mode row keys")
        index = row["mode_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 80:
            raise ValueError("mode index")
        if row["classification"] not in {"propagating", "near-cutoff", "evanescent"}:
            raise ValueError("classification")
        if row["side"] not in {"top", "bottom"} or row["polarization"] not in {"s", "p"}:
            raise ValueError("side/polarization")
        denominator = abs(_complex_value(row["refractive_index"], "refractive_index")) * k0
        if denominator <= 0:
            raise ValueError("eta denominator")
        eta = abs(_complex_value(row["beta"], "beta")) / denominator
        if not math.isfinite(eta):
            raise ValueError("eta")
        facts.append(
            {
                "mode_index": index,
                "classification": row["classification"],
                "side": row["side"],
                "polarization": row["polarization"],
                "eta": eta,
            }
        )
    if {fact["mode_index"] for fact in facts} != set(range(80)):
        raise ValueError("mode indices")
    return facts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_selector(
    record_path: Path, expected_source_sha: str, manifest_argument: Path
) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        return False, ["record must be a JSON object"], {}
    if record.get("schema") != SCHEMA:
        errors.append("record schema")
    if record.get("oracle_kind") != "synthetic_algebra":
        errors.append("oracle kind")
    if any(key in record for key in ("passed", "classification", "status")):
        errors.append("raw record contains checker-owned status")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha)
        or record.get("source_sha") != expected_source_sha
    ):
        errors.append("source SHA")
    if record.get("branch") != BRANCH or record.get("stage") != "f1-selector-only":
        errors.append("branch/stage")
    if record.get("profile") != "p6/h10/13.5nm/s/grazing1/phi0":
        errors.append("profile")
    identity = record.get("identity")
    if identity != {
        "input_sha256": INPUT_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
    }:
        errors.append("identity")
    manifest_info = record.get("manifest")
    if not isinstance(manifest_info, dict):
        errors.append("manifest facts")
        manifest_info = {}
    manifest_path = manifest_argument.absolute()
    if not isinstance(manifest_info, dict) or manifest_info.get("path") != str(manifest_path):
        errors.append("manifest path")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
        errors.append("manifest SHA")
    facts = _mode_facts(manifest)
    if (
        manifest_info.get("mode_count") != 80
        or manifest_info.get("wavelength_nm") != manifest["wavelength_nm"]
        or manifest_info.get("k0_nm_inv") != 2.0 * math.pi / float(manifest["wavelength_nm"])
    ):
        errors.append("manifest facts")
    ordered = sorted(
        [fact for fact in facts if fact["classification"] in {"propagating", "near-cutoff"}],
        key=lambda fact: (fact["eta"], fact["mode_index"]),
    )
    selector = record.get("selector")
    if not isinstance(selector, dict):
        errors.append("selector")
        selector = {}
    if selector.get("schema") != SELECTOR_SCHEMA:
        errors.append("selector schema")
    if selector.get("wavelength_nm") != manifest["wavelength_nm"]:
        errors.append("selector wavelength")
    if selector.get("k0_nm_inv") != 2.0 * math.pi / float(manifest["wavelength_nm"]):
        errors.append("selector k0")
    if selector.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
        errors.append("selector manifest")
    if selector.get("selected_mode_indices") != list(SELECTED):
        errors.append("selected indices")
    if selector.get("eligible_order") != [fact["mode_index"] for fact in ordered]:
        errors.append("eligible order")
    if selector.get("selected_rank") != 32 or selector.get("eligible_count") != 78:
        errors.append("selector counts")
    selected_facts = ordered[:32]
    if selector.get("selected_classification_counts") != dict(
        Counter(fact["classification"] for fact in selected_facts)
    ):
        errors.append("classification counts")
    if selector.get("selected_side_counts") != dict(
        Counter(fact["side"] for fact in selected_facts)
    ):
        errors.append("side counts")
    if selector.get("selected_polarization_counts") != dict(
        Counter(fact["polarization"] for fact in selected_facts)
    ):
        errors.append("polarization counts")
    payload = {
        "schema": SELECTOR_SCHEMA,
        "source_mode_manifest_sha256": MODE_MANIFEST_SHA256,
        "policy": SELECTOR_POLICY,
        "eligible_classifications": ["near-cutoff", "propagating"],
        "selected_mode_indices": [fact["mode_index"] for fact in selected_facts],
        "rank": 32,
    }
    payload_sha256 = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()
    if selector.get("selector_rule") != SELECTOR_POLICY:
        errors.append("selector policy")
    if selector.get("selector_payload") != payload:
        errors.append("selector payload")
    if (
        selector.get("selector_payload_sha256") != payload_sha256
        or payload_sha256 != SELECTOR_PAYLOAD_SHA256
        or selector.get("authority_match") is not True
    ):
        errors.append("selector authority")
    if record.get("mode_facts") != facts:
        errors.append("mode facts")
    execution = record.get("execution")
    if execution != {
        "checkpoint": False,
        "compile": False,
        "jit": False,
        "ksp": False,
        "mesh": False,
        "pde": False,
        "physical_recovery": False,
    }:
        errors.append("execution flags")
    metrics = {
        "mode_count": 80,
        "eligible_count": 78,
        "selected_rank": 32,
        "selected_mode_indices": list(SELECTED),
        "k0_nm_inv": 2.0 * math.pi / float(manifest["wavelength_nm"]),
    }
    return not errors, errors, metrics


def _relative_arrays(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        raise ValueError("canonical vectors have different shapes")
    denominator = float(np.linalg.norm(right))
    return float(np.linalg.norm(left - right) / max(denominator, np.finfo(float).tiny))


def _check_vector_artifact(record: dict, errors: list[str]) -> dict[str, np.ndarray] | None:
    vectors = record.get("vectors")
    if not isinstance(vectors, dict):
        errors.append("real vector facts")
        return None
    for key in (
        "artifact_sha256",
        "modal_dual_sha256",
        "pc_output_sha256",
    ):
        if not isinstance(vectors.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", vectors[key]):
            errors.append(f"real vector {key}")
    artifact_path = Path(vectors.get("artifact_path", ""))
    if not artifact_path.is_file():
        errors.append("real vector artifact missing")
        return None
    if _sha256_file(artifact_path) != vectors.get("artifact_sha256"):
        errors.append("real vector artifact SHA")
    try:
        with np.load(artifact_path, allow_pickle=False) as archive:
            if set(archive.files) != {"modal_dual", "pc_output"}:
                errors.append("real vector artifact keys")
                return None
            arrays = {key: np.asarray(archive[key]) for key in archive.files}
    except (OSError, ValueError) as exc:
        errors.append(f"real vector artifact unreadable: {exc}")
        return None
    for key, sha_key in (
        ("modal_dual", "modal_dual_sha256"),
        ("pc_output", "pc_output_sha256"),
    ):
        array = arrays[key]
        if (
            array.dtype != np.dtype(np.complex128)
            or array.ndim != 1
            or not np.all(np.isfinite(array))
        ):
            errors.append(f"real vector {key} type/finite")
        if hashlib.sha256(array.tobytes(order="C")).hexdigest() != vectors.get(sha_key):
            errors.append(f"real vector {key} SHA")
        norm_key = "modal_dual_global_l2" if key == "modal_dual" else "pc_output_global_l2"
        try:
            if not math.isfinite(float(vectors[norm_key])) or not math.isclose(
                float(np.linalg.norm(array)), float(vectors[norm_key]), rel_tol=1e-12, abs_tol=1e-12
            ):
                errors.append(f"real vector {norm_key}")
        except (KeyError, TypeError, ValueError):
            errors.append(f"real vector {norm_key}")
    return arrays


def _argv_value(argv: object, name: str) -> str | None:
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        return None
    try:
        index = argv.index(name)
        return argv[index + 1]
    except (ValueError, IndexError):
        return None


def _check_provenance(
    record: dict,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
    errors: list[str],
) -> None:
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("real provenance object")
        return
    source = provenance.get("source")
    expected_source = {
        "branch": BRANCH,
        "head_sha": expected_source_sha,
        "upstream": f"origin/{BRANCH}",
        "upstream_sha": expected_source_sha,
        "ahead": 0,
        "behind": 0,
        "status_porcelain": "",
    }
    if source != expected_source:
        errors.append("real source checkout provenance")
    runtime = provenance.get("runtime")
    expected_runtime = {
        "qualified_activation": "1",
        "python_executable": LEXICAL_PYTHON,
        "python_prefix": LEXICAL_PREFIX,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "mpi_size": expected_mpi_size,
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
    }
    if runtime != expected_runtime:
        errors.append("real runtime provenance")
    command = provenance.get("command")
    if not isinstance(command, dict):
        errors.append("real command provenance")
        return
    cache_dir = command.get("cache_dir")
    expected_input = str(REPO_ROOT / "input/templates/full3d_iterative_example.dat")
    if (
        command.get("mode") != "real-small-p3-h50"
        or command.get("expected_mpi_size") != expected_mpi_size
        or command.get("input") != expected_input
        or command.get("record") != str(record_path.absolute())
        or not isinstance(cache_dir, str)
        or not Path(cache_dir).is_absolute()
        or not Path(cache_dir).is_dir()
    ):
        errors.append("real command paths")
    argv = command.get("argv")
    if (
        _argv_value(argv, "--mode") != "real-small-p3-h50"
        or _argv_value(argv, "--source-sha") != expected_source_sha
        or _argv_value(argv, "--record") != str(record_path.absolute())
        or _argv_value(argv, "--input") != expected_input
        or _argv_value(argv, "--cache-dir") != cache_dir
        or _argv_value(argv, "--expected-mpi-size") != str(expected_mpi_size)
    ):
        errors.append("real command argv")


def _check_real(
    record_path: Path,
    expected_source_sha: str,
    compare_path: Path | None,
    expected_mpi_size: int,
) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        return False, ["real record must be a JSON object"], {}
    if record.get("schema") != REAL_SCHEMA:
        errors.append("real record schema")
    if record.get("oracle_kind") != "real_small_oracle":
        errors.append("real oracle kind")
    if any(key in record for key in ("passed", "classification", "status")):
        errors.append("real raw record contains checker status")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha)
        or record.get("source_sha") != expected_source_sha
    ):
        errors.append("real source SHA")
    if record.get("branch") != BRANCH or record.get("stage") != "f1-real-small-p3-h50":
        errors.append("real branch/stage")
    if record.get("profile") != "p3/h50/13.5nm/s/grazing1/phi0/small-oracle":
        errors.append("real profile")
    if record.get("mpi_size") != expected_mpi_size:
        errors.append("real MPI size")
    if expected_mpi_size not in {1, 2}:
        errors.append("real MPI size domain")
    _check_provenance(record, record_path, expected_source_sha, expected_mpi_size, errors)
    if record.get("identity") != {
        "input_sha256": INPUT_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
    }:
        errors.append("real identity")
    mode_inventory = record.get("mode_inventory")
    if mode_inventory != {
        "origin": "build_dynamic_mode_inventory",
        "mode_count": 80,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
        "selector_input": "dynamic_mode_rows",
        "selected_mode_indices": list(SELECTED),
    }:
        errors.append("real dynamic mode inventory")
    configuration = record.get("configuration")
    expected_configuration = {
        "degree": 3,
        "mesh_target_nm": 50.0,
        "mesh_cell_type": "hexahedron",
        "mesh_axis_cell_counts": [4, 4, 3],
        "wavelength_nm": 13.5,
        "grazing_deg": 1.0,
        "phi_deg": 0.0,
        "polarization": "s",
        "use_pml": False,
        "divergence_penalty": 0.0,
    }
    if configuration != expected_configuration:
        errors.append("real configuration")
    mode = record.get("mode")
    if not isinstance(mode, dict):
        errors.append("real mode object")
        mode = {}
    if (
        mode.get("mode_index") != SELECTED[0]
        or mode.get("selection_schema") != SELECTOR_SCHEMA
        or mode.get("selector_payload_sha256") != SELECTOR_PAYLOAD_SHA256
    ):
        errors.append("real mode identity")
    if record.get("modal_rhs_apply_count") != 4:
        errors.append("real modal RHS apply count")
    if record.get("pmg") != {
        "schema": PMG_SCHEMA,
        "method": PMG_METHOD,
        "levels": PMG_LEVELS,
        "apply_count": 4,
    }:
        errors.append("real PMG facts")
    execution = record.get("execution")
    if execution != {
        "checkpoint": False,
        "form_jit": True,
        "ksp": False,
        "long_krylov": False,
        "mesh": True,
        "official_physics": False,
        "p6": False,
        "physical_recovery": False,
    }:
        errors.append("real execution scope")
    arrays = _check_vector_artifact(record, errors)
    vectors = record.get("vectors")
    if not isinstance(vectors, dict):
        errors.append("real vectors object")
        vectors = {}
    for key, limit in (
        ("modal_repeat_relative", 1e-12),
        ("modal_linearity_relative", 1e-12),
        ("pc_repeat_relative", 1e-12),
        ("pc_linearity_relative", 1e-12),
        ("pc_input_unchanged_relative", 1e-12),
    ):
        try:
            if not math.isfinite(float(vectors[key])) or float(vectors[key]) > limit:
                errors.append(f"real {key}")
        except (KeyError, TypeError, ValueError):
            errors.append(f"real {key}")
    if vectors.get("modal_finite") is not True or vectors.get("pc_finite") is not True:
        errors.append("real vector finite")
    for key in ("modal_owned_slave_max", "pc_owned_slave_max"):
        if vectors.get(key) != 0.0:
            errors.append(f"real {key}")
    owner = record.get("owner_transfer")
    if not isinstance(owner, dict) or owner.get("finite") is not True:
        errors.append("real owner finite")
        owner = {}
    if owner.get("primal_finite") is not True or owner.get("adjoint_finite") is not True:
        errors.append("real owner component finite")
    for key, limit in (
        ("primal_repeat_relative", 1e-12),
        ("adjoint_repeat_relative", 1e-12),
        ("adjoint_relative", 1e-11),
        ("primal_input_unchanged_relative", 1e-12),
        ("adjoint_input_unchanged_relative", 1e-12),
        ("primal_constraint_residual", 1e-11),
    ):
        try:
            if not math.isfinite(float(owner[key])) or float(owner[key]) > limit:
                errors.append(f"real owner {key}")
        except (KeyError, TypeError, ValueError):
            errors.append(f"real owner {key}")
    if owner.get("adjoint_coarse_slave_storage_max") != 0.0:
        errors.append("real owner slave max")
    if owner.get("primal_apply_count") != 2 or owner.get("adjoint_apply_count") != 2:
        errors.append("real owner apply count")
    audit = owner.get("owner_transfer_audit")
    if (
        not isinstance(audit, dict)
        or audit.get("owner_local") is not True
        or audit.get("numeric_allgather") is not False
    ):
        errors.append("real owner audit")
    metrics = {"mpi_size": record.get("mpi_size"), "mode_index": SELECTED[0]}
    if compare_path is not None:
        other_passed, other_errors, other_metrics = _check_real(
            compare_path, expected_source_sha, None, 3 - expected_mpi_size
        )
        errors.extend(f"compare: {item}" for item in other_errors)
        metrics["compare_mpi_size"] = other_metrics.get("mpi_size")
        other_record = json.loads(compare_path.read_text(encoding="utf-8"))
        if not isinstance(other_record, dict):
            errors.append("compare: real record must be a JSON object")
            return False, errors, metrics
        other_mode = other_record.get("mode") if isinstance(other_record, dict) else {}
        if not isinstance(other_mode, dict) or mode.get("mode_key") != other_mode.get("mode_key"):
            errors.append("MPI mode key differs")
        if arrays is None:
            return False, errors, metrics
        other_arrays = _check_vector_artifact(other_record, errors)
        if other_arrays is None:
            return False, errors, metrics
        for key, limit in (
            ("modal_dual", 1e-12),
            ("pc_output", 1e-10),
        ):
            try:
                identity_error = _relative_arrays(arrays[key], other_arrays[key])
                metrics[f"{key}_mpi_identity_relative"] = identity_error
                if identity_error > limit:
                    errors.append(f"MPI {key} identity")
            except ValueError as exc:
                errors.append(f"MPI {key} identity: {exc}")
    return not errors, errors, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("selector-only", "real-small-p3-h50"),
        default="selector-only",
    )
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--compare-record", type=Path)
    parser.add_argument("--expected-mpi-size", type=int, default=1)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("checker output already exists")
    if args.expected_mpi_size not in {1, 2}:
        raise SystemExit("expected MPI size must be 1 or 2")
    try:
        if args.mode == "selector-only":
            if args.manifest is None or args.compare_record is not None:
                raise ValueError("selector-only requires --manifest and no compare record")
            passed, errors, metrics = _check_selector(
                args.record.absolute(), args.expected_source_sha, args.manifest
            )
            classification = "F1_SELECTOR_ORACLE_PASS" if passed else "F1_SELECTOR_CONTRACT_INVALID"
        else:
            if args.manifest is not None or args.compare_record is None:
                raise ValueError("real-small-p3-h50 requires --compare-record and no manifest")
            passed, errors, metrics = _check_real(
                args.record.absolute(),
                args.expected_source_sha,
                args.compare_record.absolute(),
                args.expected_mpi_size,
            )
            classification = (
                "F1_REAL_SMALL_ORACLE_PASS"
                if passed
                else "F1_REAL_SMALL_CONTRACT_INVALID"
            )
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        IndexError,
        json.JSONDecodeError,
    ) as exc:
        passed = False
        errors = [f"independent checker exception: {exc}"]
        metrics = {}
        classification = (
            "F1_SELECTOR_CONTRACT_INVALID"
            if args.mode == "selector-only"
            else "F1_REAL_SMALL_CONTRACT_INVALID"
        )
    output = {
        "schema": CHECKER_SCHEMA,
        "passed": passed,
        "classification": classification,
        "errors": errors,
        "metrics": metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
