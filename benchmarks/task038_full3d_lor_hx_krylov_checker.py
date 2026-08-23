"""Independent checker for the K0 Krylov requalification facts.

The checker reads only JSON and ``.npy`` artifacts.  It intentionally does
not import the runner, the HX fixture, PETSc, MPI, or any solver module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np


SCHEMA = "task038.lor-native-complex-hx.k0-record.v1"
CHECKER_SCHEMA = "task038.lor-native-complex-hx.k0-check.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
OLD_L2_RECORD_SHA = "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3"
OLD_L2_RHO = 1.7348663090876784
OLD_L2_LIMIT = 0.45
OLD_L2_CLASSIFICATION = "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE"
K0_GMRES_RESTART = 80
K0_GMRES_MAX_IT = 200
K0_GMRES_RTOL = 1.0e-8
K0_GMRES_ATOL = 0.0
K0_TRUE_RESIDUAL_LIMIT = 1.0e-8
K0_FIRST_PASS_MAX_IT = 80
K0_CHECKPOINTS = (0, 1, 2, 5, 10, 20, 40, 80, 120, 160, 200)
K0_LINEARITY_LIMIT = 1.0e-12
K0_REPEAT_LIMIT = 1.0e-13
K0_PHASE_APPLICATION = "algebraic_slave_zero_action_internal_finalized_mpc_once"
K0_SOURCE_FORMULA = (
    "analytic deterministic pseudo-random edge field from fixed noninteger "
    "trigonometric frequencies and phases"
)
K0_DIRECTION_CONSTRUCTION = "deterministic SHA256 parity of canonical full-space row keys"
K0_DIRECTION_INPUT_ROLE = (
    "full_fe_dual_canonical_packets_reconstructed_with_T_H_no_new_phase"
)
K0_DIRECTION_COEFFICIENTS = (0.375 + 0.25j, -0.625 + 0.5j)
K0_RUNNER_MODULE = "benchmarks.run_task038_full3d_lor_hx_krylov"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    if left_array.shape != right_array.shape:
        raise ValueError("relative operands have different shapes")
    return float(
        np.linalg.norm(left_array - right_array)
        / max(float(np.linalg.norm(right_array)), np.finfo(float).tiny)
    )


def _finite(array: np.ndarray) -> bool:
    if array.dtype.kind in "OUS":
        return True
    return bool(np.all(np.isfinite(array)))


def _artifact_path(raw_dir: Path, descriptor: dict[str, Any]) -> Path:
    path = (raw_dir / str(descriptor["relative_path"])).resolve()
    if raw_dir.resolve() not in path.parents:
        raise ValueError("artifact escapes raw directory")
    return path


def _read_array(
    record: dict[str, Any], descriptors: dict[str, dict[str, Any]], name: str
) -> tuple[np.ndarray | None, str | None]:
    descriptor = descriptors.get(name)
    if descriptor is None:
        return None, f"missing artifact descriptor {name}"
    try:
        raw_dir = Path(str(record["raw_dir"])).resolve()
        path = _artifact_path(raw_dir, descriptor)
        if not path.is_file():
            raise ValueError("file is missing")
        if int(descriptor["bytes"]) != path.stat().st_size:
            raise ValueError("byte count mismatch")
        if _sha256(path) != str(descriptor["sha256"]):
            raise ValueError("SHA256 mismatch")
        array = np.asarray(np.load(path, allow_pickle=False, mmap_mode="r"))
        if str(array.dtype) != str(descriptor["dtype"]):
            raise ValueError("dtype mismatch")
        if list(array.shape) != list(descriptor["shape"]):
            raise ValueError("shape mismatch")
        if not _finite(array):
            raise ValueError("non-finite values")
        return array, None
    except Exception as exc:
        return None, f"artifact {name}: {type(exc).__name__}: {exc}"


def _load_pair(
    record: dict[str, Any],
    descriptors: dict[str, dict[str, Any]],
    roles: dict[str, Any],
    role: str,
    errors: list[str],
) -> tuple[np.ndarray | None, np.ndarray | None]:
    names = roles.get(role)
    if not isinstance(names, dict) or set(names) != {"keys", "values"}:
        errors.append(f"canonical role {role} is missing keys/values names")
        return None, None
    keys, error = _read_array(record, descriptors, str(names["keys"]))
    if error:
        errors.append(error)
    values, error = _read_array(record, descriptors, str(names["values"]))
    if error:
        errors.append(error)
    if keys is not None:
        if keys.ndim != 1 or keys.dtype.kind not in "OUS":
            errors.append(f"canonical keys {role} must be one-dimensional strings")
    if values is not None:
        if values.ndim != 1 or values.dtype != np.dtype(np.complex128):
            errors.append(f"canonical values {role} must be one-dimensional complex128")
    if keys is not None and values is not None and keys.shape != values.shape:
        errors.append(f"canonical role {role} keys/values shape mismatch")
    return keys, values


def _same_keys(
    left: np.ndarray | None, right: np.ndarray | None, label: str, errors: list[str]
) -> bool:
    if left is None or right is None:
        return False
    left_tokens = [str(value) for value in left.tolist()]
    right_tokens = [str(value) for value in right.tolist()]
    if len(set(left_tokens)) != len(left_tokens):
        errors.append(f"canonical keys are duplicated for {label}/left")
        return False
    if len(set(right_tokens)) != len(right_tokens):
        errors.append(f"canonical keys are duplicated for {label}/right")
        return False
    if not np.array_equal(left, right):
        errors.append(f"canonical key mismatch for {label}")
        return False
    return True


def _reorder_values_by_keys(
    source_keys: np.ndarray | None,
    source_values: np.ndarray | None,
    target_keys: np.ndarray | None,
    label: str,
    errors: list[str],
) -> np.ndarray | None:
    """Align one cross-section packet value array without sorting its values."""

    if source_keys is None or source_values is None or target_keys is None:
        return None
    source_tokens = [str(value) for value in source_keys.tolist()]
    target_tokens = [str(value) for value in target_keys.tolist()]
    if len(set(source_tokens)) != len(source_tokens):
        errors.append(f"canonical keys are duplicated for {label}/source")
        return None
    if len(set(target_tokens)) != len(target_tokens):
        errors.append(f"canonical keys are duplicated for {label}/target")
        return None
    source_set = set(source_tokens)
    target_set = set(target_tokens)
    if source_set != target_set:
        missing = sorted(target_set - source_set)
        extra = sorted(source_set - target_set)
        errors.append(
            f"canonical key set mismatch for {label}: missing={missing}, extra={extra}"
        )
        return None
    if source_values.ndim != 1 or source_values.shape[0] != len(source_tokens):
        errors.append(f"canonical values do not align with keys for {label}")
        return None
    source_index = {token: index for index, token in enumerate(source_tokens)}
    indices = [source_index[token] for token in target_tokens]
    return np.asarray(source_values[indices], dtype=source_values.dtype)


def _complex_value(value: Any) -> complex:
    if isinstance(value, dict):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _canonical_key_bytes(key: Any) -> bytes:
    if isinstance(key, dict):
        value = {str(item): _canonical_key_bytes(entry).decode("utf-8") for item, entry in key.items()}
    elif isinstance(key, (tuple, list)):
        value = [_canonical_key_bytes(entry).decode("utf-8") for entry in key]
    else:
        value = key.item() if isinstance(key, np.generic) else key
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _canonical_direction_mask(keys: np.ndarray) -> np.ndarray:
    serialized = [_canonical_key_bytes(key) for key in np.asarray(keys, dtype=object).tolist()]
    if len(set(serialized)) != len(serialized):
        raise ValueError("canonical direction keys are duplicated")
    return np.asarray([hashlib.sha256(value).digest()[0] & 1 for value in serialized], dtype=bool)


def _canonical_key_set_sha256(keys: np.ndarray) -> str:
    serialized = sorted(
        _canonical_key_bytes(key) for key in np.asarray(keys, dtype=object).tolist()
    )
    return hashlib.sha256(b"\0".join(serialized)).hexdigest()


def _check_identity(record: dict[str, Any], errors: list[str]) -> None:
    if record.get("schema") != SCHEMA:
        errors.append("schema is not the K0 record schema")
    if record.get("stage") != "k0" or record.get("scope") != "krylov_requalification":
        errors.append("stage/scope is not K0")
    if record.get("case") != "p2-mpi1" or record.get("degree") != 2:
        errors.append("K0 first case must be p2-mpi1")
    if record.get("mpi_size") != 1:
        errors.append("K0 first case must have MPI size 1")
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source identity is missing")
    else:
        start = source.get("commit_sha_start")
        end = source.get("commit_sha_end")
        expected = source.get("expected_sha")
        if not all(isinstance(value, str) and SHA40.fullmatch(value) for value in (start, end, expected)):
            errors.append("source identity SHA fields are not full 40-digit hex")
        elif not (start == end == expected):
            errors.append("source identity start/end/expected SHA do not close")
        if source.get("branch") != BRANCH:
            errors.append("source branch is not the frozen execution branch")
        if source.get("clean_start") is not True or source.get("clean_end") is not True:
            errors.append("source identity is not clean at both ends")
    runtime = record.get("runtime")
    required_runtime = {
        "qualified_activation": "1",
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
    }
    if not isinstance(runtime, dict):
        errors.append("runtime identity is missing")
    else:
        for key, expected in required_runtime.items():
            if runtime.get(key) != expected:
                errors.append(f"runtime.{key} does not equal {expected!r}")
    production = record.get("production")
    if not isinstance(production, dict) or production.get("production_pc_alpha_applied") is not False:
        errors.append("production_pc_alpha_applied must be exactly false")
    forbidden = record.get("forbidden")
    if not isinstance(forbidden, dict):
        errors.append("forbidden audit is missing")
    else:
        for key in (
            "global_numeric_allgather",
            "high_order_global_aij",
            "global_dense_transfer",
            "global_direct_coarse",
        ):
            if forbidden.get(key) is not False:
                errors.append(f"forbidden.{key} must be false")


def _check_settings(record: dict[str, Any], errors: list[str]) -> None:
    settings = record.get("settings")
    expected = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": K0_GMRES_RESTART,
        "max_it": K0_GMRES_MAX_IT,
        "rtol": K0_GMRES_RTOL,
        "atol": K0_GMRES_ATOL,
        "initial_guess_nonzero": False,
    }
    if not isinstance(settings, dict):
        errors.append("fixed K0 settings are missing")
        return
    for key, value in expected.items():
        if settings.get(key) != value:
            errors.append(f"settings.{key} is not the frozen value {value!r}")


def _check_command(
    record: dict[str, Any], record_path: Path, errors: list[str]
) -> None:
    command = record.get("command")
    source = record.get("source")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        errors.append("command provenance is missing or not a string argv")
        return
    if not isinstance(source, dict):
        errors.append("command provenance cannot bind without source identity")
        return
    expected = [
        command[0] if command else "",
        "-m",
        K0_RUNNER_MODULE,
        "--case",
        str(record.get("case")),
        "--raw-dir",
        str(Path(str(record.get("raw_dir", ""))).resolve()),
        "--record",
        str(record_path.resolve()),
        "--expected-source-sha",
        str(source.get("expected_sha")),
        "--expected-mpi-size",
        str(record.get("mpi_size")),
    ]
    if not command or not Path(command[0]).is_absolute():
        errors.append("command Python executable must be an absolute path")
    if command != expected:
        errors.append("command provenance does not close with record identity")


def _check_old_l2_reference(record: dict[str, Any], errors: list[str]) -> None:
    reference = record.get("old_l2_reference")
    if not isinstance(reference, dict):
        errors.append("old_l2_reference is missing")
        return
    if reference.get("record_sha256") != OLD_L2_RECORD_SHA:
        errors.append("old L2 record SHA was changed")
    if reference.get("rho") != OLD_L2_RHO:
        errors.append("old L2 rho authority was changed")
    if reference.get("limit") != OLD_L2_LIMIT:
        errors.append("old L2 limit was changed")
    if reference.get("classification") != OLD_L2_CLASSIFICATION:
        errors.append("old L2 classification was changed")


def _check_one_apply(
    record: dict[str, Any],
    descriptors: dict[str, dict[str, Any]],
    errors: list[str],
    gate_failures: list[str],
) -> dict[str, Any]:
    section = record.get("one_apply")
    if not isinstance(section, dict):
        errors.append("one_apply facts are missing")
        return {}
    roles = section.get("artifacts")
    if not isinstance(roles, dict):
        errors.append("one_apply artifact roles are missing")
        return {}
    if section.get("input_role") != "dual":
        errors.append("one_apply input_role must be exactly dual")
    if section.get("output_role") != "primal":
        errors.append("one_apply output_role must be exactly primal")
    loaded: dict[str, tuple[np.ndarray | None, np.ndarray | None]] = {}
    for role in (
        "source_before",
        "source_after",
        "residual_before",
        "residual_after",
        "residual",
        "pc_output",
        "pc_repeat",
        "applied_output",
        "true_residual",
    ):
        loaded[role] = _load_pair(record, descriptors, roles, role, errors)
    before_keys, before = loaded["source_before"]
    after_keys, after = loaded["source_after"]
    residual_before_keys, residual_before = loaded["residual_before"]
    residual_after_keys, residual_after = loaded["residual_after"]
    residual_keys, residual = loaded["residual"]
    pc_keys, pc_output = loaded["pc_output"]
    pc_repeat_keys, pc_repeat = loaded["pc_repeat"]
    applied_keys, applied = loaded["applied_output"]
    true_keys, true = loaded["true_residual"]
    _same_keys(before_keys, after_keys, "source before/after", errors)
    _same_keys(residual_before_keys, residual_after_keys, "residual before/after", errors)
    _same_keys(residual_before_keys, residual_keys, "residual before/canonical residual", errors)
    _same_keys(residual_keys, applied_keys, "residual/action", errors)
    _same_keys(residual_keys, true_keys, "residual/true residual", errors)
    _same_keys(pc_keys, pc_repeat_keys, "PC output/repeat", errors)
    source_unchanged = before is not None and after is not None and np.array_equal(before, after)
    residual_input_unchanged = (
        residual_before is not None
        and residual_after is not None
        and np.array_equal(residual_before, residual_after)
    )
    if section.get("source_unchanged") is not source_unchanged:
        errors.append("stored source_unchanged does not match raw source snapshots")
    if section.get("residual_input_unchanged") is not residual_input_unchanged:
        errors.append("stored residual_input_unchanged does not match raw snapshots")
    if not source_unchanged:
        gate_failures.append("one-apply primal source was modified")
    if not residual_input_unchanged:
        gate_failures.append("one-apply dual residual input was modified")
    repeat = None
    if pc_output is not None and pc_repeat is not None:
        repeat = _relative(pc_repeat, pc_output)
        if section.get("repeat_relative") is None or abs(
            float(section["repeat_relative"]) - repeat
        ) > 1.0e-13:
            errors.append("stored PC repeat_relative does not match raw outputs")
        if repeat > K0_REPEAT_LIMIT:
            gate_failures.append(f"one-apply PC repeat {repeat} > {K0_REPEAT_LIMIT}")
    if residual is not None and applied is not None and true is not None:
        recomputed_true = residual - applied
        true_error = _relative(true, recomputed_true)
        rho = float(
            np.linalg.norm(recomputed_true)
            / max(float(np.linalg.norm(residual)), np.finfo(float).tiny)
        )
        if true_error > K0_REPEAT_LIMIT:
            errors.append(f"true residual artifact mismatch {true_error}")
        try:
            stored_rho = float(section["rho"])
            if abs(stored_rho - rho) > 1.0e-13:
                errors.append("worker rho does not match independently recomputed rho")
        except (KeyError, TypeError, ValueError):
            errors.append("one_apply rho is missing or non-numeric")
        if not np.isfinite(rho):
            gate_failures.append("one-apply rho is non-finite")
        finite = all(
            array is not None and _finite(array)
            for array in (residual, pc_output, pc_repeat, applied, true)
        )
        if section.get("finite") is not finite:
            errors.append("stored one_apply finite does not match raw arrays")
    alpha = section.get("alpha")
    if not isinstance(alpha, dict) or alpha.get("production_pc_alpha_applied") is not False:
        errors.append("alpha diagnostic is missing or marked as production-applied")
    elif residual is not None and applied is not None:
        denominator = np.vdot(applied, applied)
        if abs(denominator) <= np.finfo(float).tiny:
            errors.append("alpha diagnostic has zero applied direction")
        else:
            alpha_value = np.vdot(applied, residual) / denominator
            rho_alpha = float(
                np.linalg.norm(residual - alpha_value * applied)
                / max(float(np.linalg.norm(residual)), np.finfo(float).tiny)
            )
            try:
                stored_alpha = _complex_value(alpha["alpha_star"])
                stored_rho_alpha = float(alpha["rho_alpha"])
                if abs(stored_alpha - alpha_value) > 1.0e-13:
                    errors.append("alpha_star does not match complex inner-product recomputation")
                if abs(stored_rho_alpha - rho_alpha) > 1.0e-13:
                    errors.append("rho_alpha does not match recomputation")
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"malformed alpha diagnostic: {exc}")
    return {
        "residual": residual,
        "residual_keys": residual_keys,
        "applied": applied,
        "rho": section.get("rho"),
        "source_unchanged": source_unchanged,
        "residual_input_unchanged": residual_input_unchanged,
    }


def _check_linearity(
    record: dict[str, Any],
    descriptors: dict[str, dict[str, Any]],
    residual: np.ndarray | None,
    residual_keys: np.ndarray | None,
    errors: list[str],
    gate_failures: list[str],
) -> None:
    section = record.get("linearity")
    if not isinstance(section, dict):
        errors.append("linearity facts are missing")
        return
    if section.get("construction") != K0_DIRECTION_CONSTRUCTION:
        errors.append("linearity direction construction is not canonical-key based")
    if section.get("input_role") != "dual":
        errors.append("linearity input_role must be exactly dual")
    if section.get("input_semantics") != K0_DIRECTION_INPUT_ROLE:
        errors.append("linearity input semantics is not the finalized-MPC dual packet role")
    if section.get("output_role") != "primal":
        errors.append("linearity output_role must be exactly primal")
    if section.get("output_semantics") != "full_fe_primal_canonical_packets":
        errors.append("linearity output semantics is not the full-FE primal packet role")
    roles = section.get("artifacts")
    if not isinstance(roles, dict):
        errors.append("linearity artifact roles are missing")
        return
    loaded = {
        role: _load_pair(record, descriptors, roles, role, errors)
        for role in (
            "r1",
            "r2",
            "combined",
            "p1",
            "p2",
            "pcombined",
            "pcombined_repeat",
        )
    }
    values = {role: pair[1] for role, pair in loaded.items()}
    input_keys = loaded["r1"][0]
    output_keys = loaded["p1"][0]
    for role in ("r1", "r2", "combined"):
        _same_keys(input_keys, loaded[role][0], f"linearity/input/{role}", errors)
    for role in ("p1", "p2", "pcombined", "pcombined_repeat"):
        _same_keys(output_keys, loaded[role][0], f"linearity/output/{role}", errors)
    if (
        residual is None
        or residual_keys is None
        or input_keys is None
        or output_keys is None
        or any(
        value is None for value in values.values()
        )
    ):
        return
    aligned_residual = _reorder_values_by_keys(
        residual_keys,
        residual,
        input_keys,
        "linearity/input/residual",
        errors,
    )
    if aligned_residual is None:
        return
    try:
        direction_mask = _canonical_direction_mask(input_keys)
        if section.get("input_key_set_sha256") != _canonical_key_set_sha256(input_keys):
            errors.append("linearity input key-set digest does not close")
        if section.get("output_key_set_sha256") != _canonical_key_set_sha256(output_keys):
            errors.append("linearity output key-set digest does not close")
        if section.get("direction_mask") != direction_mask.tolist():
            errors.append("linearity direction mask does not close")
    except ValueError as exc:
        errors.append(f"linearity canonical direction keys are invalid: {exc}")
        return
    coefficient_a, coefficient_b = K0_DIRECTION_COEFFICIENTS
    r1, r2 = values["r1"], values["r2"]
    combined = values["combined"]
    if not np.allclose(r1[~direction_mask], 0.0) or not np.allclose(
        r2[direction_mask], 0.0
    ):
        errors.append("linearity direction values do not follow canonical-key mask")
    if min(float(np.linalg.norm(r1)), float(np.linalg.norm(r2))) <= np.finfo(float).tiny:
        errors.append("linearity directions are degenerate")
    if _relative(r1 + r2, aligned_residual) > K0_REPEAT_LIMIT:
        errors.append("linearity directions do not reconstruct the residual")
    if _relative(combined, coefficient_a * r1 + coefficient_b * r2) > K0_REPEAT_LIMIT:
        errors.append("linearity combined direction is not the frozen combination")
    expected = coefficient_a * values["p1"] + coefficient_b * values["p2"]
    relative = _relative(values["pcombined"], expected)
    repeat = _relative(values["pcombined_repeat"], values["pcombined"])
    finite = all(np.all(np.isfinite(values[role])) for role in values)
    if section.get("relative") is None or abs(
        float(section["relative"]) - relative
    ) > 1.0e-13:
        errors.append("stored linearity relative does not match raw outputs")
    if section.get("repeat_relative") is None or abs(
        float(section["repeat_relative"]) - repeat
    ) > 1.0e-13:
        errors.append("stored linearity repeat_relative does not match raw outputs")
    if section.get("finite") is not finite:
        errors.append("stored linearity finite does not match raw arrays")
    if section.get("input_unchanged") is not True:
        errors.append("linearity input_unchanged is not true")
    if relative > K0_LINEARITY_LIMIT:
        gate_failures.append(f"linearity relative {relative} > {K0_LINEARITY_LIMIT}")
    if repeat > K0_REPEAT_LIMIT:
        gate_failures.append(f"linearity repeat {repeat} > {K0_REPEAT_LIMIT}")


def _check_krylov(
    record: dict[str, Any],
    descriptors: dict[str, dict[str, Any]],
    rhs: np.ndarray | None,
    errors: list[str],
    gate_failures: list[str],
) -> dict[str, Any]:
    section = record.get("krylov")
    if not isinstance(section, dict):
        errors.append("krylov facts are missing")
        return {}
    history = section.get("history")
    if not isinstance(history, list):
        errors.append("krylov history is missing")
        return {}
    iterations = section.get("iterations")
    reason = section.get("reason")
    if not isinstance(iterations, int) or not 0 <= iterations <= K0_GMRES_MAX_IT:
        errors.append("krylov iterations are outside the frozen range")
        return {}
    if not isinstance(reason, int):
        errors.append("krylov reason is missing")
        return {}
    if [row.get("iteration") for row in history] != list(range(iterations + 1)):
        errors.append("krylov history is not contiguous from 0 through iterations")
    rows: dict[int, dict[str, Any]] = {}
    previous_matvec = previous_pc = previous_monitor = -1
    for row in history:
        if not isinstance(row, dict):
            errors.append("malformed krylov history row")
            continue
        iteration = row.get("iteration")
        if not isinstance(iteration, int):
            errors.append("history iteration is not an integer")
            continue
        rows[iteration] = row
        for key in (
            "reported_unpreconditioned_relative",
            "explicit_true_residual",
            "elapsed_seconds",
        ):
            if not isinstance(row.get(key), (int, float)) or not np.isfinite(row[key]):
                errors.append(f"history {iteration} field {key} is not finite")
        for key, previous in (
            ("matvec_count", previous_matvec),
            ("pc_apply_count", previous_pc),
            ("monitor_action_count", previous_monitor),
        ):
            value = row.get(key)
            if not isinstance(value, int) or value < previous:
                errors.append(f"history {iteration} count {key} is not monotone")
        if row.get("monitor_action_count") != iteration + 1:
            errors.append(
                f"history {iteration} monitor_action_count must equal iteration+1"
            )
        previous_matvec = int(row.get("matvec_count", previous_matvec))
        previous_pc = int(row.get("pc_apply_count", previous_pc))
        previous_monitor = int(row.get("monitor_action_count", previous_monitor))
    if history:
        final_row = history[-1]
        for key in ("matvec_count", "pc_apply_count"):
            if not isinstance(section.get(key), int) or section[key] < final_row.get(key, 0):
                errors.append(f"krylov.{key} is below the last monitor row")
        if section.get("monitor_action_count") != final_row.get("monitor_action_count"):
            errors.append("krylov.monitor_action_count does not close with final history row")
        if section.get("monitor_action_count") != len(history):
            errors.append("krylov.monitor_action_count must equal history row count")
    first_true_pass = next(
        (
            iteration
            for iteration, row in rows.items()
            if float(row.get("explicit_true_residual", np.inf)) <= K0_TRUE_RESIDUAL_LIMIT
        ),
        None,
    )
    early_pass = first_true_pass is not None and first_true_pass <= K0_FIRST_PASS_MAX_IT
    if not early_pass:
        if any(
            float(row.get("explicit_true_residual", np.inf)) <= K0_TRUE_RESIDUAL_LIMIT
            for row in rows.values()
        ):
            gate_failures.append("true residual passes only after the 80-step qualification window")
        else:
            gate_failures.append("explicit true residual never reaches the K0 limit")
    if section.get("first_true_pass_iteration") != first_true_pass:
        errors.append("recorded first_true_pass_iteration disagrees with history")
    if section.get("qualification_pass") is not early_pass:
        errors.append("recorded qualification_pass disagrees with independent history")

    checkpoint_records = section.get("checkpoints")
    if not isinstance(checkpoint_records, dict):
        errors.append("checkpoint records are missing")
        return {"first_true_pass": first_true_pass, "early_pass": early_pass}
    for checkpoint in K0_CHECKPOINTS:
        key = str(checkpoint)
        item = checkpoint_records.get(key)
        if not isinstance(item, dict):
            errors.append(f"checkpoint {checkpoint} is missing")
            continue
        expected_status = (
            "measured"
            if checkpoint <= iterations
            else "not_reached"
            if reason < 0
            else "not_run_after_convergence"
            if first_true_pass is not None and checkpoint > first_true_pass
            else "not_reached"
        )
        if item.get("status") != expected_status:
            errors.append(
                f"checkpoint {checkpoint} status {item.get('status')!r} != {expected_status!r}"
            )
        roles = item.get("artifacts")
        if expected_status != "measured":
            if roles not in (None, {}):
                errors.append(f"unmeasured checkpoint {checkpoint} has artifacts")
            continue
        if not isinstance(roles, dict):
            errors.append(f"measured checkpoint {checkpoint} has no artifacts")
            continue
        loaded = {
            role: _load_pair(record, descriptors, roles, role, errors)
            for role in ("solution", "action", "true_residual")
        }
        action_keys, action = loaded["action"]
        true_keys, true = loaded["true_residual"]
        _same_keys(action_keys, true_keys, f"checkpoint {checkpoint} action/true", errors)
        if rhs is not None and action is not None and true is not None:
            recomputed = rhs - action
            error = _relative(true, recomputed)
            if error > K0_REPEAT_LIMIT:
                errors.append(f"checkpoint {checkpoint} true residual mismatch {error}")
            explicit = float(
                np.linalg.norm(recomputed)
                / max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
            )
            row = rows.get(checkpoint)
            if row is None or abs(float(row["explicit_true_residual"]) - explicit) > 1.0e-13:
                errors.append(f"checkpoint {checkpoint} history residual disagrees with raw arrays")
    return {"first_true_pass": first_true_pass, "early_pass": early_pass}


def check_record(record_path: str | Path) -> dict[str, Any]:
    """Independently classify one K0 record without changing it."""

    record_path = Path(record_path).resolve()
    errors: list[str] = []
    gate_failures: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema": CHECKER_SCHEMA,
            "passed": False,
            "contract_errors": [f"cannot parse record: {type(exc).__name__}: {exc}"],
            "gate_failures": [],
        }
    if not isinstance(record, dict):
        return {
            "schema": CHECKER_SCHEMA,
            "passed": False,
            "contract_errors": ["record root is not an object"],
            "gate_failures": [],
        }
    _check_identity(record, errors)
    _check_command(record, record_path, errors)
    _check_settings(record, errors)
    _check_old_l2_reference(record, errors)
    source_facts = record.get("source_facts")
    if not isinstance(source_facts, dict):
        errors.append("source_facts are missing")
    else:
        if source_facts.get("name") != "random":
            errors.append("K0 source is not frozen random")
        if source_facts.get("formula") != K0_SOURCE_FORMULA:
            errors.append("K0 source formula changed")
        if source_facts.get("phase_application") != K0_PHASE_APPLICATION:
            errors.append("K0 phase application contract changed")
    descriptors_list = record.get("artifacts")
    descriptors: dict[str, dict[str, Any]] = {}
    if not isinstance(descriptors_list, list):
        errors.append("artifacts list is missing")
    else:
        for descriptor in descriptors_list:
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("name"), str):
                errors.append("malformed artifact descriptor")
                continue
            name = descriptor["name"]
            if name in descriptors:
                errors.append(f"duplicate artifact descriptor {name}")
            descriptors[name] = descriptor
    one_apply = _check_one_apply(record, descriptors, errors, gate_failures)
    _check_linearity(
        record,
        descriptors,
        one_apply.get("residual"),
        one_apply.get("residual_keys"),
        errors,
        gate_failures,
    )
    _check_krylov(record, descriptors, one_apply.get("residual"), errors, gate_failures)
    return {
        "schema": CHECKER_SCHEMA,
        "passed": not errors and not gate_failures,
        "contract_errors": errors,
        "gate_failures": gate_failures,
        "facts": {
            "old_l2_rho": OLD_L2_RHO,
            "old_l2_limit": OLD_L2_LIMIT,
            "first_case": "p2-mpi1",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = check_record(args.record)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
