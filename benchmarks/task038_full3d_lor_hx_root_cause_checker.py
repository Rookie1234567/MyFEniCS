"""Independent checker for the M0 multiplicative LOR-HX diagnostic.

Only the record and its NumPy artifacts are read here.  This module does not
import the runner, a solver, PETSc, MPI, DOLFINx, or SciPy.  Production
PCGAMG versus exact-nodal differences remain diagnostics; the checker gates
only the fixed M0 identity and algebraic facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task038.lor-native-complex-hx.m0-record.v1"
CHECKER_SCHEMA = "task038.lor-native-complex-hx.m0-check.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
M0_SOURCE = "random"
M0_DIRECT_BACKEND = "petsc-preonly-lu-mumps"
M0_EXACT_LIMIT = 1.0e-10
M0_PRODUCTION_EQUIVALENCE_LIMIT = 1.0e-13
M0_INPUT_LIMIT = 1.0e-12
M0_REPEAT_LIMIT = 1.0e-13
M0_TRACE_NAMES = (
    "edge_jacobi_pre",
    "gradient",
    "pi_x",
    "pi_y",
    "pi_z",
    "edge_jacobi_post",
)
OLD_L2_RECORD_SHA = "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3"
OLD_L2_RHO = 1.7348663090876784
OLD_L2_LIMIT = 0.45
OLD_L2_CLASSIFICATION = "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left)
    right = np.asarray(right)
    return float(
        np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny)
    )


def _finite(array: np.ndarray) -> bool:
    array = np.asarray(array)
    if array.dtype.kind in "OUS":
        return True
    return bool(np.all(np.isfinite(array)))


def _artifact_path(raw_dir: Path, descriptor: dict[str, Any]) -> Path:
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str):
        raise ValueError("artifact relative_path is missing")
    path = (raw_dir / relative).resolve()
    if raw_dir.resolve() not in path.parents:
        raise ValueError("artifact escapes raw_dir")
    return path


def _read_arrays(
    record: dict[str, Any], required: set[str]
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]], list[str]]:
    raw_value = record.get("raw_dir")
    if not isinstance(raw_value, str):
        return {}, {}, ["raw_dir is missing"]
    raw_dir = Path(raw_value).resolve()
    descriptors = record.get("artifacts")
    if not isinstance(descriptors, list):
        return {}, {}, ["artifacts list is missing"]
    by_name: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for descriptor in descriptors:
        if not isinstance(descriptor, dict) or not isinstance(
            descriptor.get("name"), str
        ):
            errors.append("malformed artifact descriptor")
            continue
        name = descriptor["name"]
        if name in by_name:
            errors.append(f"duplicate artifact descriptor: {name}")
        by_name[name] = descriptor
    missing = sorted(required - set(by_name))
    errors.extend(f"missing artifact: {name}" for name in missing)
    arrays: dict[str, np.ndarray] = {}
    for name, descriptor in by_name.items():
        try:
            path = _artifact_path(raw_dir, descriptor)
            if not path.is_file():
                raise ValueError("file is missing")
            if path.stat().st_size != int(descriptor["bytes"]):
                raise ValueError("byte count mismatch")
            if _sha256(path) != descriptor["sha256"]:
                raise ValueError("SHA256 mismatch")
            array = np.load(path, allow_pickle=False, mmap_mode="r")
            if str(array.dtype) != str(descriptor["dtype"]):
                raise ValueError("dtype mismatch")
            if list(array.shape) != list(descriptor["shape"]):
                raise ValueError("shape mismatch")
            if not _finite(array):
                raise ValueError("non-finite values")
            arrays[name] = np.asarray(array)
        except Exception as exc:
            errors.append(f"artifact {name}: {type(exc).__name__}: {exc}")
    return arrays, by_name, errors


def _required_role_names(
    record: dict[str, Any] | None = None,
) -> tuple[dict[str, str], set[str]]:
    roles: dict[str, str] = {
        "high_source_before": "primal",
        "high_source_after": "primal",
        "high_residual": "dual",
        "high_residual_before": "dual",
        "high_residual_after": "dual",
        "production_output": "primal",
        "production_repeat": "primal",
        "production_action": "dual",
        "exact_edge_correction": "primal",
        "exact_edge_action": "dual",
        "production_replay_output": "primal",
        "exact_nodal_output": "primal",
        "low_input": "dual",
    }
    for prefix in ("production", "exact_nodal"):
        for name in M0_TRACE_NAMES:
            stem = f"{prefix}_{name}"
            roles.update(
                {
                    f"{stem}_result": "primal",
                    f"{stem}_remaining": "dual",
                    f"{stem}_edge_delta": "primal",
                    f"{stem}_edge_action": "dual",
                }
            )
            if name not in ("edge_jacobi_pre", "edge_jacobi_post"):
                roles.update(
                    {
                        f"{stem}_rhs": "dual",
                        f"{stem}_nodal_delta": "primal",
                    }
                )
    if record is not None:
        facts = record.get("facts")
        labels = facts.get("outer_artifact_labels") if isinstance(facts, dict) else None
        if isinstance(labels, list):
            for label in labels:
                if not isinstance(label, str):
                    continue
                if label.endswith("_solution"):
                    roles[label] = "primal"
                elif label.endswith("_action") or label.endswith("_true_residual"):
                    roles[label] = "dual"
    names: set[str] = set()
    canonical_roles = roles
    for role in canonical_roles:
        names.add(f"{role}_keys")
        names.add(f"{role}_values")
    return roles, names


def _load_role_arrays(
    record: dict[str, Any],
    arrays: dict[str, np.ndarray],
    role_kinds: dict[str, str],
    role: str,
    errors: list[str],
) -> tuple[np.ndarray, np.ndarray] | None:
    roles = record.get("canonical_roles")
    if not isinstance(roles, dict) or not isinstance(roles.get(role), dict):
        errors.append(f"canonical role is missing: {role}")
        return None
    descriptor = roles[role]
    key_name = descriptor.get("keys")
    value_name = descriptor.get("values")
    if key_name != f"{role}_keys" or value_name != f"{role}_values":
        errors.append(f"canonical role artifact names are not exact: {role}")
        return None
    if role_kinds.get(role) not in {"primal", "dual"}:
        errors.append(f"canonical role kind is missing: {role}")
    keys = arrays.get(key_name)
    values = arrays.get(value_name)
    if keys is None or values is None:
        errors.append(f"canonical role arrays are missing: {role}")
        return None
    if keys.ndim != 1 or values.ndim != 1 or keys.shape != values.shape:
        errors.append(f"canonical role shape mismatch: {role}")
        return None
    if keys.dtype.kind not in "US" or values.dtype != np.dtype(np.complex128):
        errors.append(f"canonical role dtype mismatch: {role}")
        return None
    if len(set(str(value) for value in keys.tolist())) != keys.size:
        errors.append(f"canonical role has duplicate keys: {role}")
    if not _finite(values):
        errors.append(f"canonical role is non-finite: {role}")
    return keys, values


def _identity_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("schema") != SCHEMA or record.get("stage") != "m0":
        errors.append("schema/stage mismatch")
    case = record.get("case")
    expected = {"p2-mpi1": (2, 1), "p2-mpi2": (2, 2)}
    if case not in expected:
        errors.append("case is not a frozen M0 case")
    if case in expected and (
        record.get("degree"),
        record.get("mpi_size"),
    ) != expected[case]:
        errors.append("degree/MPI identity mismatch")
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source identity is missing")
    else:
        expected_sha = source.get("expected_sha")
        if not isinstance(expected_sha, str) or not SHA40.fullmatch(expected_sha):
            errors.append("source expected SHA is not lowercase 40-hex")
        if source.get("commit_sha_start") != expected_sha or source.get("commit_sha_end") != expected_sha:
            errors.append("source SHA is not closed")
        if source.get("branch") != BRANCH:
            errors.append("source branch mismatch")
        if source.get("clean_start") is not True or source.get("clean_end") is not True:
            errors.append("source clean boundaries are not true")
    runtime = record.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime identity is missing")
    else:
        if runtime.get("qualified_activation") != "1":
            errors.append("qualified activation is not 1")
        if runtime.get("mpi_size") != record.get("mpi_size"):
            errors.append("runtime MPI identity mismatch")
        if runtime.get("petsc_scalar_type") != "complex128" or runtime.get("petsc_int_type") != "int32":
            errors.append("PETSc ABI identity mismatch")
        executable = str(runtime.get("sys_executable", ""))
        if "/.venv/" not in executable or "/mnt/c/" in executable:
            errors.append("runtime executable is not qualified Linux .venv")
    rank_facts = record.get("rank_facts")
    mpi_size = record.get("mpi_size")
    if not isinstance(rank_facts, list) or not isinstance(mpi_size, int) or len(rank_facts) != mpi_size:
        errors.append("rank_facts count mismatch")
    else:
        ids = [fact.get("rank") if isinstance(fact, dict) else None for fact in rank_facts]
        if sorted(ids) != list(range(mpi_size)):
            errors.append("rank_facts rank IDs are incomplete")
        for fact in rank_facts:
            fact_runtime = fact.get("runtime") if isinstance(fact, dict) else None
            if not isinstance(fact_runtime, dict):
                errors.append("rank runtime identity is missing")
                continue
            if fact_runtime.get("qualified_activation") != "1":
                errors.append("rank qualified activation is not 1")
            if fact_runtime.get("petsc_scalar_type") != "complex128" or fact_runtime.get("petsc_int_type") != "int32":
                errors.append("rank PETSc ABI identity mismatch")
    settings = record.get("settings")
    if not isinstance(settings, dict):
        errors.append("settings are missing")
    else:
        if settings.get("variant") != "sequential-v1" or settings.get("source") != M0_SOURCE:
            errors.append("M0 fixed variant/source mismatch")
        if settings.get("direct_backend") != M0_DIRECT_BACKEND:
            errors.append("direct backend mismatch")
        direct = settings.get("exact_nodal_direct")
        if not isinstance(direct, dict) or direct != {
            "ksp_type": "preonly",
            "pc_type": "lu",
            "factor_solver_type": "mumps",
            "factor_reused_within_diagnostic_apply": True,
        }:
            errors.append("exact nodal direct settings mismatch")
        outer = settings.get("outer_gmres")
        if not isinstance(outer, dict) or outer != {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 20,
            "cycle_max_it": 20,
            "max_cycles": 10,
            "max_it": 200,
            "rtol": 1.0e-8,
            "atol": 0.0,
            "zero_initial_guess": True,
            "residual_replacement": True,
        }:
            errors.append("outer diagnostic GMRES settings mismatch")
        if settings.get("pair_gates") != {
            "input": 1.0e-12,
            "exact_correction_action": 1.0e-10,
            "exact_component": 1.0e-10,
        }:
            errors.append("M0 pair gates mismatch")
    old = record.get("old_l2_reference")
    if not isinstance(old, dict) or old.get("record_sha256") != OLD_L2_RECORD_SHA or old.get("rho") != OLD_L2_RHO or old.get("limit") != OLD_L2_LIMIT or old.get("classification") != OLD_L2_CLASSIFICATION:
        errors.append("old L2 immutable authority mismatch")
    production = record.get("production")
    required_production = {
        "variant": "sequential-v1",
        "production_pc_alpha_applied": False,
        "global_transfer_matrix": False,
        "global_numeric_allgather": False,
        "global_direct_coarse": False,
        "high_order_global_aij": False,
        "additive_v2": False,
        "ordinary_default_changed": False,
    }
    if not isinstance(production, dict) or any(
        production.get(key) != value for key, value in required_production.items()
    ):
        errors.append("production M0 audit is not exact")
    fixture = record.get("fixture_audit")
    hx = fixture.get("hx_audit_after_diagnostic") if isinstance(fixture, dict) else None
    if not isinstance(fixture, dict) or not isinstance(hx, dict):
        errors.append("fixture/HX audit snapshot is missing")
    else:
        for facts in (fixture, hx):
            if facts.get("variant") != "sequential-v1":
                errors.append("fixture/HX variant is not sequential-v1")
            if facts.get("global_transfer_matrix") is not False or facts.get("global_numeric_allgather") is not False or facts.get("global_direct_coarse") is not False:
                errors.append("fixture/HX forbidden materialization audit is not false")
        for key, value in {
            "edge_jacobi_correction_count": 2,
            "nodal_correction_count": 4,
            "hierarchy_object_count": 1,
            "one_shared_scalar_hierarchy": True,
            "original_residual_for_all_corrections": False,
        }.items():
            if hx.get(key) != value:
                errors.append(f"HX fixed audit mismatch: {key}")
    return errors


def _record_check(record_path: Path) -> dict[str, Any]:
    contract_errors = []
    gate_failures = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema": CHECKER_SCHEMA,
            "record": str(record_path.resolve()),
            "passed": False,
            "contract_errors": [f"record parse: {type(exc).__name__}: {exc}"],
            "gate_failures": [],
        }
    if not isinstance(record, dict):
        contract_errors.append("record root is not an object")
        record = {}
    contract_errors.extend(_identity_errors(record))
    role_kinds = record.get("canonical_role_kinds")
    expected_roles, required_artifacts = _required_role_names(record)
    if role_kinds != expected_roles:
        contract_errors.append("canonical_role_kinds is not the exact M0 map")
    arrays, descriptors, artifact_errors = _read_arrays(record, required_artifacts)
    contract_errors.extend(artifact_errors)
    roles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for role, kind in expected_roles.items():
        pair = _load_role_arrays(record, arrays, role_kinds or {}, role, contract_errors)
        if pair is not None:
            roles[role] = pair
    facts = record.get("facts")
    if not isinstance(facts, dict):
        contract_errors.append("facts are missing")
        facts = {}
    if record.get("status") != "facts_written_not_qualified":
        contract_errors.append("worker status is not facts_written_not_qualified")
    if facts.get("source_formula") != "analytic deterministic pseudo-random edge field from fixed noninteger trigonometric frequencies and phases":
        contract_errors.append("M0 source formula mismatch")
    if facts.get("source_phase_application") != "algebraic_slave_zero_action_internal_finalized_mpc_once":
        contract_errors.append("M0 source phase contract mismatch")
    for key in ("source_unchanged", "residual_input_unchanged", "finite"):
        if facts.get(key) is not True:
            gate_failures.append(f"{key}=false")
    for left, right, name in (
        ("high_source_before", "high_source_after", "source_input"),
        ("high_residual_before", "high_residual_after", "residual_input"),
    ):
        if left in roles and right in roles:
            left_keys, left_values = roles[left]
            right_keys, right_values = roles[right]
            if not np.array_equal(left_keys, right_keys):
                contract_errors.append(f"{name} key order changed")
            else:
                value = _relative(right_values, left_values)
                if value > M0_INPUT_LIMIT:
                    gate_failures.append(f"{name} relative={value} > {M0_INPUT_LIMIT}")
    production_repeat = roles.get("production_repeat")
    production_output = roles.get("production_output")
    if production_repeat is not None and production_output is not None and np.array_equal(production_repeat[0], production_output[0]):
        repeat = _relative(production_repeat[1], production_output[1])
        if repeat > M0_REPEAT_LIMIT:
            gate_failures.append(f"production repeat relative={repeat} > {M0_REPEAT_LIMIT}")
    else:
        contract_errors.append("production output/repeat keys are not closed")
    direct = facts.get("direct_edge")
    if not isinstance(direct, dict):
        contract_errors.append("direct edge facts are missing")
    else:
        for key in ("relative_residual", "rhs_norm", "solution_norm", "residual_norm"):
            if not isinstance(direct.get(key), (int, float)):
                contract_errors.append(f"direct edge fact missing: {key}")
        if direct.get("backend") != M0_DIRECT_BACKEND or direct.get("finite") is not True:
            contract_errors.append("direct edge backend/finite contract mismatch")
        if isinstance(direct.get("relative_residual"), (int, float)) and direct["relative_residual"] > M0_EXACT_LIMIT:
            gate_failures.append(f"direct edge relative residual={direct['relative_residual']} > {M0_EXACT_LIMIT}")
    if facts.get("trace_count") != 6:
        contract_errors.append("trace_count is not six")
    if facts.get("nodal_correction_count") != 4:
        contract_errors.append("nodal_correction_count is not four")
    for trace_key in ("production_trace", "exact_nodal_trace"):
        trace = facts.get(trace_key)
        if not isinstance(trace, list) or [item.get("name") for item in trace if isinstance(item, dict)] != list(M0_TRACE_NAMES):
            contract_errors.append(f"{trace_key} sequence is not frozen")
    production_replay = facts.get("production_replay_relative")
    repeat_fact = facts.get("production_repeat_relative")
    for value, name, limit in (
        (production_replay, "production replay", M0_PRODUCTION_EQUIVALENCE_LIMIT),
        (repeat_fact, "production repeat", M0_REPEAT_LIMIT),
    ):
        if not isinstance(value, (int, float)):
            contract_errors.append(f"{name} fact is missing")
        elif value > limit:
            gate_failures.append(f"{name} relative={value} > {limit}")
    exact_trace = facts.get("exact_nodal_trace")
    if isinstance(exact_trace, list):
        for item in exact_trace:
            solver = item.get("solver") if isinstance(item, dict) else None
            if not isinstance(solver, dict):
                contract_errors.append("exact nodal solver facts are missing")
                continue
            if item.get("name") not in ("edge_jacobi_pre", "edge_jacobi_post"):
                for key, expected in (
                    ("ksp_type", "preonly"),
                    ("pc_type", "lu"),
                    ("factor_solver_type", "mumps"),
                ):
                    if solver.get(key) != expected:
                        contract_errors.append(f"exact nodal {item.get('name')} {key} mismatch")
                if solver.get("finite") is not True or not isinstance(solver.get("relative_residual"), (int, float)):
                    contract_errors.append(f"exact nodal {item.get('name')} residual facts missing")
                elif solver["relative_residual"] > M0_EXACT_LIMIT:
                    gate_failures.append(
                        f"exact nodal {item.get('name')} relative residual={solver['relative_residual']} > {M0_EXACT_LIMIT}"
                    )
    outer_histories = facts.get("outer_histories")
    expected_outer_settings = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": 20,
        "cycle_max_it": 20,
        "max_cycles": 10,
        "max_it": 200,
        "rtol": 1.0e-8,
        "atol": 0.0,
        "zero_initial_guess": True,
        "residual_replacement": True,
    }
    if not isinstance(outer_histories, dict) or set(outer_histories) != {
        "production",
        "exact_nodal",
    }:
        contract_errors.append("outer production/exact-nodal histories are missing")
    else:
        labels = facts.get("outer_artifact_labels")
        expected_final_labels = {
            "production_outer_final_solution",
            "production_outer_final_action",
            "production_outer_final_true_residual",
            "exact_nodal_outer_final_solution",
            "exact_nodal_outer_final_action",
            "exact_nodal_outer_final_true_residual",
        }
        if not isinstance(labels, list) or set(labels) != expected_final_labels:
            contract_errors.append("outer artifacts must contain final packets only")
        if isinstance(labels, list) and any("checkpoint" in str(label) for label in labels):
            contract_errors.append("outer checkpoint field artifacts are forbidden")
        for label, history_facts in outer_histories.items():
            if not isinstance(history_facts, dict):
                contract_errors.append(f"outer history facts missing: {label}")
                continue
            if history_facts.get("settings") != expected_outer_settings:
                contract_errors.append(f"outer GMRES settings mismatch: {label}")
            history = history_facts.get("history")
            if not isinstance(history, list) or not history:
                contract_errors.append(f"outer history is missing: {label}")
                continue
            previous_iteration = -1
            previous_counts = {
                "matvec_count": -1,
                "solver_pc_apply_count": -1,
                "monitor_reconstruction_pc_applies": -1,
                "monitor_action_count": -1,
            }
            explicit_rows = 0
            for row in history:
                if not isinstance(row, dict):
                    contract_errors.append(f"outer history row is not an object: {label}")
                    continue
                for key in (
                    "iteration",
                    "reported_residual",
                    "reported_relative",
                    "explicit_true_residual",
                    "matvec_count",
                    "solver_pc_apply_count",
                    "monitor_reconstruction_pc_applies",
                    "monitor_action_count",
                ):
                    if key not in row or (
                        key != "explicit_true_residual"
                        and not isinstance(row[key], (int, float))
                    ):
                        contract_errors.append(f"outer history field missing: {label}:{key}")
                if not isinstance(row.get("iteration"), int):
                    continue
                if row["iteration"] < previous_iteration:
                    contract_errors.append(f"outer history iteration order changed: {label}")
                previous_iteration = row["iteration"]
                for key in previous_counts:
                    if isinstance(row.get(key), int):
                        if row[key] < previous_counts[key]:
                            contract_errors.append(f"outer history count decreased: {label}:{key}")
                        previous_counts[key] = row[key]
                if row.get("explicit_true_residual") is not None:
                    explicit_rows += 1
                if not all(
                    np.isfinite(float(row[key]))
                    for key in ("reported_residual", "reported_relative")
                    if isinstance(row.get(key), (int, float))
                ) or (
                    row.get("explicit_true_residual") is not None
                    and not np.isfinite(float(row["explicit_true_residual"]))
                ):
                    contract_errors.append(f"outer history non-finite: {label}")
            checkpoint_status = history_facts.get("checkpoint_status")
            if not isinstance(checkpoint_status, dict) or set(checkpoint_status) != {
                str(value) for value in (0, 1, 2, 5, 10, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200)
            }:
                contract_errors.append(f"outer checkpoint status is incomplete: {label}")
            if isinstance(checkpoint_status, dict):
                allowed_status = {"measured", "not_reached", "not_run_after_convergence"}
                if any(value not in allowed_status for value in checkpoint_status.values()):
                    contract_errors.append(f"outer checkpoint status value is invalid: {label}")
            for key in (
                "matvec_count",
                "solver_pc_apply_count",
                "monitor_reconstruction_pc_applies",
                "monitor_action_count",
                "final_action_count",
                "total_pc_apply_count",
                "iterations",
                "reason",
                "cycle_count",
            ):
                if not isinstance(history_facts.get(key), int):
                    contract_errors.append(f"outer count/reason missing: {label}:{key}")
            if isinstance(history_facts.get("total_pc_apply_count"), int) and isinstance(
                history_facts.get("solver_pc_apply_count"), int
            ) and isinstance(history_facts.get("monitor_reconstruction_pc_applies"), int):
                if history_facts["total_pc_apply_count"] != (
                    history_facts["solver_pc_apply_count"]
                    + history_facts["monitor_reconstruction_pc_applies"]
                ):
                    contract_errors.append(f"outer PC count partition mismatch: {label}")
            if isinstance(history_facts.get("monitor_action_count"), int) and history_facts[
                "monitor_action_count"
            ] != explicit_rows:
                contract_errors.append(f"outer explicit action count mismatch: {label}")
            cycles = history_facts.get("cycles")
            cycle_count = history_facts.get("cycle_count")
            if not isinstance(cycles, list) or not isinstance(cycle_count, int) or len(cycles) != cycle_count or cycle_count > 10:
                contract_errors.append(f"outer replacement cycles are incomplete: {label}")
            else:
                for index, cycle in enumerate(cycles):
                    if not isinstance(cycle, dict):
                        contract_errors.append(f"outer cycle is not an object: {label}:{index}")
                        continue
                    for key in (
                        "cycle_index",
                        "start_iteration",
                        "iterations",
                        "cumulative_end_iteration",
                        "reason",
                        "reported_final_relative",
                        "explicit_true_residual",
                        "solver_pc_apply_count",
                        "monitor_reconstruction_pc_applies",
                        "monitor_action_count",
                    ):
                        if key not in cycle or not isinstance(cycle[key], (int, float)):
                            contract_errors.append(f"outer cycle field missing: {label}:{index}:{key}")
                    if cycle.get("cycle_index") != index:
                        contract_errors.append(f"outer cycle index mismatch: {label}:{index}")
                    if cycle.get("iterations", 0) > 20:
                        contract_errors.append(f"outer cycle exceeds twenty steps: {label}:{index}")
                    if cycle.get("cumulative_end_iteration") != cycle.get("start_iteration", 0) + cycle.get("iterations", 0):
                        contract_errors.append(f"outer cycle cumulative iteration mismatch: {label}:{index}")
                    if cycle.get("initial_guess_nonzero") is not (index != 0):
                        contract_errors.append(f"outer cycle initial-guess contract mismatch: {label}:{index}")
    diagnostics = {
        "production_pcgamg_vs_exact_nodal": facts.get("exact_nodal_vs_production_relative"),
        "role_count": len(roles),
        "artifact_count": len(descriptors),
        "outer_history_labels": sorted(outer_histories) if isinstance(outer_histories, dict) else [],
    }
    return {
        "schema": CHECKER_SCHEMA,
        "record": str(record_path.resolve()),
        "record_sha256": _sha256(record_path),
        "case": record.get("case"),
        "passed": not contract_errors and not gate_failures,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "diagnostics": diagnostics,
    }


def _aligned_relative(
    left: tuple[np.ndarray, np.ndarray], right: tuple[np.ndarray, np.ndarray]
) -> float:
    left_keys, left_values = left
    right_keys, right_values = right
    if set(str(value) for value in left_keys.tolist()) != set(str(value) for value in right_keys.tolist()):
        raise ValueError("canonical key sets differ")
    right_by_key = {str(key): value for key, value in zip(right_keys, right_values, strict=True)}
    aligned = np.asarray([right_by_key[str(key)] for key in left_keys], dtype=np.complex128)
    return _relative(left_values, aligned)


def _pair_check(record_paths: list[Path]) -> dict[str, Any]:
    results = [_record_check(path) for path in record_paths]
    contract_errors = [
        f"{result['case']}: {error}"
        for result in results
        for error in result["contract_errors"]
    ]
    gate_failures = [
        f"{result['case']}: {error}"
        for result in results
        for error in result["gate_failures"]
    ]
    by_case = {result.get("case"): result for result in results}
    if set(by_case) != {"p2-mpi1", "p2-mpi2"} or len(by_case) != 2:
        contract_errors.append("M0 pair must contain exactly p2-mpi1 and p2-mpi2")
    loaded: dict[str, dict[str, Any]] = {}
    for path in record_paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            loaded[str(record["case"])] = record
        except Exception:
            pass
    source_shas = [
        record.get("source", {}).get("expected_sha")
        for record in loaded.values()
        if isinstance(record.get("source"), dict)
    ]
    if len(source_shas) != 2 or source_shas[0] != source_shas[1]:
        contract_errors.append("pair records do not share one exact source SHA")
    arrays_by_case: dict[str, dict[str, np.ndarray]] = {}
    roles_by_case: dict[str, dict[str, str]] = {}
    for case, record in loaded.items():
        role_names, required = _required_role_names(record)
        roles_by_case[case] = role_names
        arrays, _descriptors, errors = _read_arrays(record, required)
        if errors:
            contract_errors.extend(f"{case}: {error}" for error in errors)
        arrays_by_case[case] = arrays
    aligned_metrics: dict[str, float] = {}
    production_metrics: dict[str, dict[str, Any]] = {}
    first_divergent_component: str | None = None
    left_record = loaded.get("p2-mpi1")
    right_record = loaded.get("p2-mpi2")
    if left_record is not None and right_record is not None:
        left_roles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        right_roles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for role in roles_by_case.get("p2-mpi1", {}):
            left_pair = _load_role_arrays(
                left_record,
                arrays_by_case["p2-mpi1"],
                roles_by_case["p2-mpi1"],
                role,
                contract_errors,
            )
            right_pair = _load_role_arrays(
                right_record,
                arrays_by_case["p2-mpi2"],
                roles_by_case.get("p2-mpi2", {}),
                role,
                contract_errors,
            )
            if left_pair is None or right_pair is None:
                continue
            left_roles[role] = left_pair
            right_roles[role] = right_pair
        for role, limit, label in (
            ("high_source_before", M0_INPUT_LIMIT, "input source"),
            ("high_residual", M0_INPUT_LIMIT, "input residual"),
            ("low_input", M0_INPUT_LIMIT, "low dual input"),
            ("exact_edge_correction", M0_EXACT_LIMIT, "exact edge correction"),
            ("exact_edge_action", M0_EXACT_LIMIT, "exact edge action"),
            ("exact_nodal_output", M0_EXACT_LIMIT, "exact nodal output"),
        ):
            if role not in left_roles or role not in right_roles:
                continue
            try:
                value = _aligned_relative(left_roles[role], right_roles[role])
            except ValueError as exc:
                contract_errors.append(f"{label}: {exc}")
                continue
            aligned_metrics[role] = value
            if value > limit:
                gate_failures.append(f"{label} relative={value} > {limit}")
        for role in sorted(set(left_roles) & set(right_roles)):
            if role.startswith("exact_nodal_") and role not in {"exact_nodal_output"}:
                try:
                    value = _aligned_relative(left_roles[role], right_roles[role])
                except ValueError as exc:
                    contract_errors.append(f"{role}: {exc}")
                    continue
                aligned_metrics[role] = value
                if value > M0_EXACT_LIMIT:
                    gate_failures.append(f"{role} relative={value} > {M0_EXACT_LIMIT}")
        for name in M0_TRACE_NAMES:
            for field in (
                "rhs",
                "nodal_delta",
                "edge_delta",
                "edge_action",
                "remaining",
                "result",
            ):
                role = f"production_{name}_{field}"
                if role not in left_roles or role not in right_roles:
                    continue
                metric_name = f"{name}.{field}"
                try:
                    value = _aligned_relative(left_roles[role], right_roles[role])
                    production_metrics[metric_name] = {
                        "key_sets_equal": True,
                        "relative": value,
                        "threshold": M0_EXACT_LIMIT,
                        "diagnostic_only": True,
                    }
                    if value > M0_EXACT_LIMIT and first_divergent_component is None:
                        first_divergent_component = metric_name
                except ValueError:
                    production_metrics[metric_name] = {
                        "key_sets_equal": False,
                        "relative": None,
                        "threshold": M0_EXACT_LIMIT,
                        "diagnostic_only": True,
                    }
                    if first_divergent_component is None:
                        first_divergent_component = metric_name
        if "production_output" in left_roles and "production_output" in right_roles:
            try:
                value = _aligned_relative(
                    left_roles["production_output"], right_roles["production_output"]
                )
                production_metrics["final_production_output"] = {
                    "key_sets_equal": True,
                    "relative": value,
                    "threshold": M0_EXACT_LIMIT,
                    "diagnostic_only": True,
                }
                if value > M0_EXACT_LIMIT and first_divergent_component is None:
                    first_divergent_component = "final_production_output"
            except ValueError:
                production_metrics["final_production_output"] = {
                    "key_sets_equal": False,
                    "relative": None,
                    "threshold": M0_EXACT_LIMIT,
                    "diagnostic_only": True,
                }
                if first_divergent_component is None:
                    first_divergent_component = "final_production_output"
    return {
        "schema": CHECKER_SCHEMA,
        "records": [str(path.resolve()) for path in record_paths],
        "record_sha256": [_sha256(path) for path in record_paths],
        "passed": not contract_errors and not gate_failures,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "pair_metrics": aligned_metrics,
        "production_pair_diagnostic": {
            "diagnostic_only": True,
            "threshold": M0_EXACT_LIMIT,
            "first_divergent_component": first_divergent_component,
            "metrics": production_metrics,
        },
        "individual": results,
    }


def check_record(record_path: Path | str) -> dict[str, Any]:
    """Check one M0 record and return a JSON-compatible result."""

    return _record_check(Path(record_path))


def check_records(record_paths: list[Path | str]) -> dict[str, Any]:
    """Check the fixed p2 MPI1/MPI2 M0 pair."""

    return _pair_check([Path(path) for path in record_paths])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [Path(value) for value in args.record]
    result = check_record(paths[0]) if len(paths) == 1 else check_records(paths)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
