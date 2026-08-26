"""Independent contract checker for the small same-mesh p3/p1 candidate.

Only raw JSON, checkpoint manifests, and NumPy shard files are read here.  No
runner, solver, PETSc, MPI, or DOLFINx module is imported, so this checker
cannot reproduce the numerical implementation or trust a worker decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


CHECKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.small-check.v1"
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.small-record.v1"
CHECKPOINT_SCHEMA = "fixed-memory-krylov.solution-checkpoint.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
LEVELS = [3, 1]
PAIR = [3, 1]
ADJOINT_LIMIT = 1.0e-11
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
ENERGY_LIMIT = 1.0e-9
SMALL_RESIDUAL_LIMIT = 1.0e-8
SMALL_RSS_LIMIT = 500_000_000

_FORBIDDEN_FALSE = (
    "global_high_order_aij",
    "global_dense_transfer",
    "global_transfer_matrix",
    "numeric_allgather",
    "lor_mesh",
    "hx_hierarchy_built",
    "pcgamg_hierarchy_built",
    "physical_solve",
    "pde",
    "physical",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_sha(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(float(value))


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _validate_watchdog_worker_command(
    actual: Any, expected: Any, mpi_size: int
) -> tuple[bool, str]:
    if mpi_size == 1:
        return actual == expected, "direct"
    if mpi_size == 2:
        valid = (
            isinstance(actual, list)
            and isinstance(expected, list)
            and len(actual) == len(expected) + 3
            and isinstance(actual[0], str)
            and actual[0] == "/usr/bin/mpiexec"
            and actual[1:3] == ["-n", "2"]
            and actual[3:] == expected
        )
        return valid, "mpiexec_n2"
    return False, "invalid_mpi_size"


def _check_watchdog(
    watchdog_compact: Mapping[str, Any] | Path | str | None,
    record: Mapping[str, Any],
    record_path: Path | None,
    provenance: Mapping[str, Any] | None,
    mpi_size: int,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any] | None:
    """Check the external process-tree authority, not rank-local sampling."""

    if watchdog_compact is None:
        _error(errors, "external watchdog compact is required")
        return None
    if isinstance(watchdog_compact, Mapping):
        compact = watchdog_compact
    else:
        try:
            compact = json.loads(
                Path(watchdog_compact).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            _error(errors, f"watchdog compact cannot be read: {type(exc).__name__}")
            return None
    if not isinstance(compact, Mapping):
        _error(errors, "watchdog compact is not a JSON object")
        return None
    if compact.get("schema") != WATCHDOG_SCHEMA:
        _error(errors, "watchdog compact schema is invalid")
    if compact.get("watchdog_rss_limit_bytes") != SMALL_RSS_LIMIT:
        _error(errors, "watchdog RSS limit is not the 500MB authority")
    if provenance is not None and compact.get("source_sha") != provenance.get("source_sha"):
        _error(errors, "watchdog source SHA differs from record provenance")
    command_valid, launcher_validation = _validate_watchdog_worker_command(
        compact.get("worker_command"), record.get("command"), mpi_size
    )
    if not command_valid:
        _error(errors, "watchdog worker command differs from record command")
    worker_record = compact.get("worker_record")
    if not isinstance(worker_record, str) or not Path(worker_record).is_absolute():
        _error(errors, "watchdog worker record path is not absolute")
    elif record_path is not None and Path(worker_record).resolve() != record_path.resolve():
        _error(errors, "watchdog worker record path differs from checked record")

    raw_value = compact.get("watchdog_raw")
    raw_path = Path(raw_value) if isinstance(raw_value, str) else None
    samples: list[Mapping[str, Any]] = []
    if raw_path is None or not raw_path.is_absolute() or not raw_path.is_file():
        _error(errors, "watchdog raw path is not an existing absolute file")
    else:
        if compact.get("raw_sha256") != _sha256_file(raw_path):
            _error(errors, "watchdog raw SHA does not match compact")
        try:
            for line in raw_path.read_bytes().splitlines():
                sample = json.loads(line)
                if not isinstance(sample, Mapping):
                    raise ValueError("sample is not an object")
                samples.append(sample)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            _error(errors, f"watchdog raw samples cannot be read: {type(exc).__name__}")
    rss: list[int] = []
    swap: list[int] = []
    readable: list[bool] = []
    for sample in samples:
        authority = sample.get("authority")
        tree = authority.get("process_tree") if isinstance(authority, Mapping) else None
        if not isinstance(tree, Mapping):
            _error(errors, "watchdog sample lacks process-tree facts")
            continue
        values = (tree.get("rss_bytes"), tree.get("swap_bytes"))
        if any(type(value) is not int or value < 0 for value in values):
            _error(errors, "watchdog process-tree memory fact is invalid")
            continue
        rss.append(int(values[0]))
        swap.append(int(values[1]))
        readable.append(tree.get("all_status_readable") is True)
    if not samples or len(rss) != len(samples):
        _error(errors, "watchdog has no complete process-tree sample inventory")
    expected_peak = max(rss, default=-1)
    expected_swap = max(swap, default=-1)
    expected_readable = bool(readable) and all(readable)
    if (
        compact.get("sample_count") != len(samples)
        or compact.get("peak_process_tree_rss_bytes") != expected_peak
        or compact.get("max_process_tree_swap_bytes") != expected_swap
        or compact.get("all_status_readable") is not expected_readable
    ):
        _error(errors, "watchdog compact is not derived from process-tree raw facts")
    for key, expected_type in (
        ("natural_exit", bool),
        ("no_orphan", bool),
        ("all_status_readable", bool),
    ):
        if type(compact.get(key)) is not expected_type:
            _error(errors, f"watchdog {key} fact is malformed")
    if compact.get("returncode") != 0 or compact.get("natural_exit") is not True or compact.get("no_orphan") is not True:
        gates.append("external watchdog lifecycle")
    peak = compact.get("peak_process_tree_rss_bytes")
    if type(peak) is not int or peak < 0:
        _error(errors, "watchdog peak RSS fact is malformed")
    elif peak >= SMALL_RSS_LIMIT:
        gates.append("external process-tree RSS >= 500MB")
    max_swap = compact.get("max_process_tree_swap_bytes")
    if type(max_swap) is not int or max_swap < 0:
        _error(errors, "watchdog swap fact is malformed")
    elif max_swap != 0:
        gates.append("external process-tree swap")
    if compact.get("all_status_readable") is not True:
        gates.append("external process-tree readability")
    checked = dict(compact)
    checked["launcher_validation"] = launcher_validation
    return checked


def _check_provenance(
    record: Mapping[str, Any], expected_source_sha: str | None, errors: list[str]
) -> dict[str, Any] | None:
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        _error(errors, "provenance is missing")
        return None
    source_sha = provenance.get("source_sha")
    if not isinstance(source_sha, str) or len(source_sha) != 40 or any(
        char not in "0123456789abcdef" for char in source_sha
    ):
        _error(errors, "provenance source_sha is not a lowercase full Git SHA")
    if expected_source_sha is not None and source_sha != expected_source_sha:
        _error(errors, "provenance source_sha does not match the expected SHA")
    if provenance.get("branch") != BRANCH or record.get("branch") != BRANCH:
        _error(errors, "branch identity is not frozen")
    if provenance.get("qualified_activation") != "1":
        _error(errors, "qualified activation fact is missing")
    executable = provenance.get("python_executable")
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        _error(errors, "qualified Python executable is not absolute")
    threads = provenance.get("threads")
    if not isinstance(threads, Mapping) or any(
        threads.get(name) != "1"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        _error(errors, "one-thread facts are not closed")
    command = provenance.get("command")
    if not isinstance(command, list) or command != record.get("command"):
        _error(errors, "record command and provenance command differ")
    input_path_value = provenance.get("input_path")
    input_path = Path(input_path_value) if isinstance(input_path_value, str) else None
    input_sha = None
    if input_path is None or not input_path.is_absolute() or not input_path.is_file():
        _error(errors, "provenance input path is not an existing absolute file")
    else:
        input_sha = _sha256_file(input_path)
        if provenance.get("input_sha256") != input_sha:
            _error(errors, "input file SHA does not match provenance")

    source = record.get("source")
    source_name = record.get("source_name")
    authority = provenance.get("input_identity_authority")
    if not isinstance(source, Mapping) or not isinstance(authority, Mapping):
        _error(errors, "input identity authority is missing")
    elif input_sha is not None and source_sha == provenance.get("source_sha"):
        expected_authority = {
            "source_name": source_name,
            "source_sha": source_sha,
            "source_facts": dict(source),
            "input_path": str(input_path.resolve()),
            "input_sha256": input_sha,
            "dtype": "complex128",
            "ownership": "PETSc owner-local",
        }
        if dict(authority) != expected_authority:
            _error(errors, "input identity authority payload is not reproducible")
        if provenance.get("input_identity_sha256") != _stable_sha(expected_authority):
            _error(errors, "input identity SHA is not reproducible")
    return dict(provenance)


def _global_matrix_facts(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        key: value[key]
        for key in value
        if key not in {"local_rows", "local_cols"}
    }


def _check_architecture(record: Mapping[str, Any], errors: list[str]) -> None:
    architecture = record.get("architecture")
    if not isinstance(architecture, Mapping):
        _error(errors, "architecture is missing")
        return
    for key in _FORBIDDEN_FALSE:
        if key not in architecture or architecture[key] is not False:
            _error(errors, f"architecture.{key} is not explicitly false")
    for key, expected in (
        ("small_only", True),
        ("p3_sparse_allowed", True),
        ("p1_exact_factor", True),
        ("p3_exact_factor", False),
        ("smoother_instances", 1),
        ("power_steps", 10),
    ):
        if architecture.get(key) != expected:
            _error(errors, f"architecture.{key} is not {expected!r}")
    if architecture.get("levels") != LEVELS or architecture.get("pairs") != [PAIR]:
        _error(errors, "architecture level or pair identity is not fixed")


def _check_matrix_and_identity(
    record: Mapping[str, Any], provenance: Mapping[str, Any] | None, errors: list[str]
) -> None:
    matrices = record.get("matrices")
    if not isinstance(matrices, Mapping) or matrices.get("same_physical_mesh") is not True:
        _error(errors, "same physical mesh matrix facts are missing")
        return
    clean_matrices: dict[str, Any] = {}
    for name in ("fine", "coarse"):
        facts = matrices.get(name)
        if not isinstance(facts, Mapping):
            _error(errors, f"{name} matrix facts are missing")
            continue
        required = ("rows", "cols", "local_rows", "local_cols", "global_nnz")
        if any(key not in facts for key in required):
            _error(errors, f"{name} matrix layout is incomplete")
            continue
        if facts["rows"] != facts["cols"] or int(facts["rows"]) <= 0:
            _error(errors, f"{name} matrix is not positive square")
        if int(facts["local_rows"]) <= 0 or int(facts["local_cols"]) <= 0:
            _error(errors, f"{name} local matrix layout is empty")
        if int(facts["global_nnz"]) <= 0:
            _error(errors, f"{name} global NNZ is not positive")
        if facts.get("finite_diagonal") is not True or facts.get("positive_diagonal") is not True:
            _error(errors, f"{name} diagonal facts are not finite positive")
        clean_matrices[name] = _global_matrix_facts(facts)
    if provenance is None or not clean_matrices:
        return
    authority = provenance.get("operator_identity_authority")
    material = record.get("material")
    if not isinstance(authority, Mapping) or not isinstance(material, Mapping):
        _error(errors, "operator identity authority is missing")
        return
    cell_counts = material.get("cell_counts")
    positive = material.get("positive_coefficients")
    if not isinstance(cell_counts, Mapping) or not isinstance(positive, Mapping):
        _error(errors, "global coefficient audit is incomplete")
        return
    global_material = {
        "cell_counts": dict(cell_counts),
        "positive_coefficients": dict(positive),
        "global_cell_count": int(sum(int(value) for value in cell_counts.values())),
    }
    architecture = dict(record.get("architecture", {}))
    local_slave_count = architecture.pop("fine_owned_mpc_slave_count", None)
    global_slave_count = architecture.get("fine_global_owned_mpc_slave_count")
    if type(local_slave_count) is not int or local_slave_count < 0:
        _error(errors, "local owned-slave diagnostic is not a nonnegative integer")
    if type(global_slave_count) is not int or global_slave_count < 0:
        _error(errors, "global owned-slave identity fact is not a nonnegative integer")
    rank_facts = provenance.get("rank_facts")
    if not isinstance(rank_facts, Mapping):
        _error(errors, "rank-local ownership facts are missing")
    elif type(rank_facts.get("fine_owned_mpc_slave_count")) is not int or rank_facts.get(
        "fine_owned_mpc_slave_count"
    ) != local_slave_count:
        _error(errors, "rank-local owned-slave fact differs from architecture")
    expected_operator = {
        "architecture": architecture,
        "matrix_facts": clean_matrices,
        "coefficient_audit": global_material,
        "matrix_free_action": "FullspaceMpcFormAction",
        "same_form": "curl_plus_mass",
    }
    if dict(authority) != expected_operator:
        _error(errors, "operator identity authority payload is not reproducible")
    if provenance.get("operator_identity_sha256") != _stable_sha(expected_operator):
        _error(errors, "operator identity SHA is not reproducible")
    physical = {
        "input_identity_sha256": provenance.get("input_identity_sha256"),
        "coefficient_audit": global_material,
    }
    if provenance.get("physical_model_sha256") != _stable_sha(physical):
        _error(errors, "physical model identity SHA is not reproducible")


def _check_transfer(record: Mapping[str, Any], errors: list[str], gates: list[str]) -> None:
    transfer = record.get("transfer")
    local = record.get("local_transfer")
    if not isinstance(transfer, Mapping) or not isinstance(local, Mapping):
        _error(errors, "owner/local transfer facts are missing")
        return
    if transfer.get("pair_fine_to_coarse") != PAIR:
        _error(errors, "owner transfer pair is not p3-to-p1")
    for key in ("fine_global_rows", "coarse_global_rows"):
        value = transfer.get(key)
        if not isinstance(value, int) or value <= 0:
            _error(errors, f"owner transfer {key} is missing or invalid")
    for key in ("global_transfer_matrix", "numeric_allgather"):
        if transfer.get(key) is not False:
            _error(errors, f"owner transfer {key} is not false")
    if transfer.get("phase_application") != "finalized_floquet_mpc_once":
        _error(errors, "owner transfer phase application is not once")
    if local.get("pair_fine_to_coarse") != PAIR:
        _error(errors, "local transfer pair is not p3-to-p1")
    if local.get("fine_lagrange_variant") != "legendre" or local.get("coarse_lagrange_variant") != "legendre":
        _error(errors, "local transfer Lagrange variants are not Legendre")
    if local.get("full_column_rank") is not True or local.get("rank") != local.get("expected_rank"):
        gates.append("local transfer full-column-rank")
    for key, limit in (
        ("edge_functional_relative", 1.0e-11),
        ("gradient_commuting_relative", 1.0e-11),
        ("curl_commuting_relative", 1.0e-11),
        ("adjoint_work_relative", ADJOINT_LIMIT),
        ("linearity_relative", LINEARITY_LIMIT),
        ("repeat_relative", REPEAT_LIMIT),
    ):
        value = local.get(key)
        if not _finite(value):
            gates.append(f"local transfer {key}")
        elif float(value) > limit:
            gates.append(f"local transfer {key}")
    if local.get("input_unchanged") is not True or local.get("finite") is not True:
        gates.append("local transfer finite/input")


def _check_structure(record: Mapping[str, Any], errors: list[str], gates: list[str]) -> None:
    structure = record.get("structure")
    if not isinstance(structure, Mapping):
        _error(errors, "global structure probe facts are missing")
        return
    for key in (
        "source_finite",
        "projected_full_finite",
        "projected_finite",
        "source_input_unchanged",
        "source_nonzero",
        "finite",
    ):
        if structure.get(key) is not True:
            gates.append(f"structure {key}")
    for key, limit in (
        ("assembled_form_action_relative", ADJOINT_LIMIT),
        ("global_adjoint_work_relative", ADJOINT_LIMIT),
        ("projected_repeat_relative", REPEAT_LIMIT),
        ("galerkin_energy_relative", ENERGY_LIMIT),
    ):
        value = structure.get(key)
        if not _finite(value) or float(value) > limit:
            gates.append(f"structure {key}")
    for key in ("fine_matrix_hermitian", "coarse_matrix_hermitian"):
        if structure.get(key) is not True:
            gates.append(f"structure {key}")
    for key in ("fine_matrix_hermitian_defect", "coarse_matrix_hermitian_defect"):
        value = structure.get(key)
        if not _finite(value) or float(value) > 1.0e-12:
            gates.append(f"structure {key}")
    for key, limit in (
        ("full_primal_constraint_residual", ADJOINT_LIMIT),
        ("algebraic_slave_storage_max", 0.0),
    ):
        value = structure.get(key)
        if not _finite(value) or float(value) > limit:
            gates.append(f"structure {key}")
    for key in ("coarse_energy", "galerkin_energy"):
        value = structure.get(key)
        if not isinstance(value, list) or len(value) != 2 or not all(
            _finite(item) for item in value
        ):
            gates.append(f"structure {key}")
            continue
        real, imag = (float(item) for item in value)
        if real <= 0.0 or abs(imag) > ADJOINT_LIMIT * max(abs(real), np.finfo(float).tiny):
            gates.append(f"structure {key} positive Hermitian energy")
    material = record.get("material")
    positive = material.get("positive_coefficients") if isinstance(material, Mapping) else None
    if not isinstance(positive, Mapping) or not positive:
        _error(errors, "positive same-mesh material audit is missing")
    else:
        for role, coefficients in positive.items():
            if not isinstance(coefficients, Mapping) or any(
                not _finite(coefficients.get(name)) or float(coefficients[name]) <= 0.0
                for name in ("mu_inverse", "k0_squared_abs_epsilon")
            ):
                _error(errors, f"material positive audit is invalid for {role}")
    source = structure.get("source")
    if not isinstance(source, Mapping) or source.get("source_generation") != "physical_canonical_key_sha256_v1":
        _error(errors, "global probe source identity is not physical-canonical")
    if record.get("source_name") != "random" and record.get("source_name") not in {"gradient", "curl", "checkerboard"}:
        _error(errors, "source name is not one of the frozen small sources")


def _check_vcycle(
    record: Mapping[str, Any], errors: list[str], gates: list[str]
) -> None:
    vcycle = record.get("vcycle")
    if not isinstance(vcycle, Mapping):
        _error(errors, "vcycle raw facts are missing")
        return
    last_apply = vcycle.get("last_apply")
    if not isinstance(last_apply, Mapping):
        _error(errors, "vcycle last-apply facts are missing")
    else:
        for key, expected in (
            ("smoother_apply_count", 2),
            ("transfer_3_1_adjoint_count", 1),
            ("transfer_3_1_primal_count", 1),
            ("p1_solve_count", 1),
        ):
            if last_apply.get(key) != expected:
                gates.append(f"last V-cycle {key}")
        value = last_apply.get("owned_slave_max")
        if not _finite(value) or float(value) != 0.0:
            gates.append("last V-cycle algebraic slave-zero output")
        residual = last_apply.get("p1_relative_residual")
        if not _finite(residual) or float(residual) > ADJOINT_LIMIT:
            gates.append("last V-cycle p1 residual")
    facts = record.get("vcycle_qualification")
    if not isinstance(facts, Mapping):
        _error(errors, "independent V-cycle qualification is missing")
        return
    for key in ("finite", "input_unchanged", "each_apply_counts"):
        if facts.get(key) is not True:
            gates.append(f"V-cycle qualification {key}")
    for key, limit in (
        ("repeat_relative", REPEAT_LIMIT),
        ("linearity_relative", LINEARITY_LIMIT),
        ("p1_relative_residual_max", ADJOINT_LIMIT),
    ):
        value = facts.get(key)
        if not _finite(value) or float(value) > limit:
            gates.append(f"V-cycle qualification {key}")
    if facts.get("probe_apply_count") != 4:
        _error(errors, "V-cycle qualification apply count is not four")
    apply_count = facts.get("probe_apply_count")
    if type(apply_count) is int and apply_count == 4:
        for key, expected in (
            ("smoother_apply_total", 8),
            ("transfer_3_1_adjoint_total", 4),
            ("transfer_3_1_primal_total", 4),
            ("p1_solve_total", 4),
        ):
            if facts.get(key) != expected:
                gates.append(f"V-cycle qualification {key}")
    value = facts.get("owned_slave_max")
    if not _finite(value) or float(value) != 0.0:
        gates.append("V-cycle qualification algebraic slave-zero output")


def _check_manifest(
    checkpoint_fact: Mapping[str, Any],
    provenance: Mapping[str, Any],
    record: Mapping[str, Any],
    errors: list[str],
) -> None:
    path_value = checkpoint_fact.get("manifest_path")
    if not isinstance(path_value, str):
        _error(errors, "checkpoint manifest path is missing")
        return
    manifest_path = Path(path_value)
    if not manifest_path.is_absolute() or not manifest_path.is_file():
        _error(errors, "checkpoint manifest path is not an existing absolute file")
        return
    if checkpoint_fact.get("manifest_sha256") != _sha256_file(manifest_path):
        _error(errors, "checkpoint manifest SHA mismatch")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _error(errors, f"checkpoint manifest cannot be read: {type(exc).__name__}")
        return
    if not isinstance(manifest, Mapping) or manifest.get("schema") != CHECKPOINT_SCHEMA:
        _error(errors, "checkpoint manifest schema is invalid")
        return
    for key in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
        if manifest.get(key) != provenance.get(key):
            _error(errors, f"checkpoint {key} does not match stage identity")
    if manifest.get("source_sha") != provenance.get("source_sha"):
        _error(errors, "checkpoint source SHA does not match stage identity")
    if manifest.get("solution_only") is not True or manifest.get("numeric_allgather") is not False:
        _error(errors, "checkpoint is not solution-only")
    if manifest.get("vector_roles") != ["solution"] or manifest.get("forbidden_vector_roles") != [
        "action", "residual", "krylov_basis"
    ]:
        _error(errors, "checkpoint vector-role contract is invalid")
    if manifest.get("iteration") != checkpoint_fact.get("iteration"):
        _error(errors, "checkpoint iteration fact differs from manifest")
    ranks = manifest.get("ranks")
    if not isinstance(ranks, list) or len(ranks) != int(record.get("mpi_size", -1)):
        _error(errors, "checkpoint rank inventory is incomplete")
        return
    for rank_fact in ranks:
        if not isinstance(rank_fact, Mapping):
            _error(errors, "checkpoint rank fact is malformed")
            continue
        ownership = rank_fact.get("ownership")
        descriptor = rank_fact.get("solution")
        if not isinstance(ownership, Mapping) or not isinstance(descriptor, Mapping):
            _error(errors, "checkpoint ownership or solution fact is missing")
            continue
        shard_value = descriptor.get("relative_path")
        shard_path = manifest_path.parent / shard_value if isinstance(shard_value, str) else None
        if shard_path is None or not shard_path.is_file():
            _error(errors, "checkpoint solution shard is missing")
            continue
        if descriptor.get("bytes") != shard_path.stat().st_size or descriptor.get("sha256") != _sha256_file(shard_path):
            _error(errors, "checkpoint solution file descriptor does not match file")
        try:
            values = np.load(shard_path, allow_pickle=False)
        except (OSError, ValueError):
            _error(errors, "checkpoint solution shard cannot be loaded")
            continue
        if str(values.dtype) != descriptor.get("dtype") or list(values.shape) != descriptor.get("shape"):
            _error(errors, "checkpoint solution dtype or shape differs")
        if not np.all(np.isfinite(values)):
            _error(errors, "checkpoint solution shard is non-finite")


def _check_krylov(
    record: Mapping[str, Any], provenance: Mapping[str, Any] | None, errors: list[str], gates: list[str]
) -> None:
    krylov = record.get("krylov")
    if not isinstance(krylov, Mapping):
        _error(errors, "krylov raw facts are missing")
        return
    settings = krylov.get("settings")
    expected_settings = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": 20,
        "cycle_max_it": 20,
        "max_it": 10_000,
        "start_iteration": 0,
        "residual_limit": 1.0e-8,
        "residual_replacement": True,
        "first_checkpoint_iteration": 500,
        "checkpoint_interval": 500,
    }
    if not isinstance(settings, Mapping):
        _error(errors, "fixed Krylov settings are missing")
    else:
        for key, expected in expected_settings.items():
            if settings.get(key) != expected:
                _error(errors, f"Krylov setting {key} is not frozen")
        if settings.get("initial_guess_nonzero") is not False:
            _error(errors, "Krylov initial guess is not zero")
    initial_true = krylov.get("initial_true_residual")
    if not _finite(initial_true):
        gates.append("Krylov initial true residual is non-finite")
    elif abs(float(initial_true) - 1.0) > 1.0e-13:
        gates.append("Krylov zero-initial residual is not one")
    cycles = krylov.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        _error(errors, "Krylov cycle ledger is missing")
        return
    cursor = 0
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, Mapping):
            _error(errors, "Krylov cycle fact is malformed")
            continue
        if cycle.get("cycle_index") != index or cycle.get("start_iteration") != cursor:
            _error(errors, "Krylov cycle ledger is not continuous")
        end = cycle.get("end_iteration")
        iterations = cycle.get("iterations")
        if (
            type(end) is not int
            or type(iterations) is not int
            or end - cursor != iterations
            or not 0 < iterations <= 20
        ):
            _error(errors, "Krylov cycle interval is invalid")
        if cycle.get("initial_guess_nonzero") is not (index > 0):
            _error(errors, "Krylov initial-guess lifecycle is invalid")
        if not _finite(cycle.get("explicit_true_residual")):
            gates.append("Krylov explicit residual")
        elif not _finite(cycle.get("reported_final_residual")):
            gates.append("Krylov reported residual")
        if cycle.get("ksp_destroyed") is not True:
            gates.append("Krylov KSP lifecycle")
        cycle_matvec = cycle.get("matvec_count")
        cycle_pc = cycle.get("pc_apply_count")
        if type(iterations) is int:
            expected_matvec = iterations + (1 if index > 0 else 0)
            if type(cycle_matvec) is not int or cycle_matvec != expected_matvec:
                _error(errors, "Krylov cycle matvec count is malformed")
            expected_pc = iterations + 1
            if type(cycle_pc) is not int or cycle_pc != expected_pc:
                _error(errors, "Krylov cycle PC count is malformed")
        resource = cycle.get("resource")
        if not isinstance(resource, Mapping) or resource.get("scope") != "rank-root-diagnostic":
            _error(errors, "resource fact is not labeled rank-root diagnostic")
        cursor = end if type(end) is int else cursor
    iterations_total = krylov.get("iterations")
    if type(iterations_total) is not int or iterations_total != cursor:
        _error(errors, "Krylov total iteration count does not close")
    elif iterations_total > 10_000:
        gates.append("Krylov iterations exceed max_it")
    final_residual = krylov.get("final_true_residual")
    if not _finite(final_residual):
        gates.append("Krylov final true residual is non-finite")
    elif float(final_residual) > SMALL_RESIDUAL_LIMIT:
        gates.append("Krylov final true residual")
    last_cycle = cycles[-1]
    if not isinstance(last_cycle, Mapping):
        _error(errors, "Krylov final cycle fact is malformed")
        return
    if krylov.get("reason") != last_cycle.get("reason"):
        _error(errors, "Krylov final reason does not match last cycle")
    if final_residual != last_cycle.get("explicit_true_residual"):
        _error(errors, "Krylov final residual does not match last cycle")
    cycle_matvec_total = sum(
        int(cycle.get("matvec_count", -1))
        for cycle in cycles
        if isinstance(cycle, Mapping) and type(cycle.get("matvec_count")) is int
    )
    cycle_pc_total = sum(
        int(cycle.get("pc_apply_count", -1))
        for cycle in cycles
        if isinstance(cycle, Mapping) and type(cycle.get("pc_apply_count")) is int
    )
    for key, expected in (
        ("matvec_count", cycle_matvec_total),
        ("pc_apply_count", cycle_pc_total),
        ("explicit_action_count", len(cycles) + 1),
        ("ksp_destroy_count", len(cycles)),
    ):
        value = krylov.get(key)
        if value != expected:
            _error(errors, f"Krylov {key} does not close")
    checkpoint_facts = krylov.get("checkpoint_facts")
    if not isinstance(checkpoint_facts, list):
        _error(errors, "checkpoint facts are missing")
        return
    expected_iterations = list(range(500, cursor + 1, 500))
    actual_iterations = [fact.get("iteration") for fact in checkpoint_facts if isinstance(fact, Mapping)]
    if actual_iterations != expected_iterations:
        _error(errors, "checkpoint inventory is not the exact 500-step list")
    if provenance is not None:
        for fact in checkpoint_facts:
            if isinstance(fact, Mapping):
                _check_manifest(fact, provenance, record, errors)


def check_record(
    record_or_path: Mapping[str, Any] | Path | str,
    *,
    expected_source_sha: str | None = None,
    watchdog_compact: Mapping[str, Any] | Path | str | None = None,
) -> dict[str, Any]:
    """Independently classify one raw candidate record."""

    record_path: Path | None = None
    if isinstance(record_or_path, Mapping):
        record = record_or_path
    else:
        path = Path(record_or_path)
        record_path = path.resolve()
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "schema": CHECKER_SCHEMA,
                "passed": False,
                "classification": "CONTRACT_INVALID",
                "contract_errors": [f"record cannot be read: {type(exc).__name__}"],
                "gate_failures": [],
            }
    errors: list[str] = []
    gates: list[str] = []
    if not isinstance(record, Mapping):
        errors.append("record is not a JSON object")
        return {
            "schema": CHECKER_SCHEMA,
            "passed": False,
            "classification": "CONTRACT_INVALID",
            "contract_errors": errors,
            "gate_failures": gates,
        }
    if record.get("schema") != RECORD_SCHEMA:
        _error(errors, "record schema is invalid")
    if "status" in record or "classification" in record:
        _error(errors, "worker record must not contain a decision field")
    if record.get("stage") != "c1-small" or record.get("mpi_size") not in (1, 2):
        _error(errors, "small candidate profile is invalid")
    provenance = _check_provenance(record, expected_source_sha, errors)
    mpi_size = record.get("mpi_size")
    watchdog = _check_watchdog(
        watchdog_compact,
        record,
        record_path,
        provenance,
        int(mpi_size) if type(mpi_size) is int else -1,
        errors,
        gates,
    )
    _check_architecture(record, errors)
    _check_matrix_and_identity(record, provenance, errors)
    _check_transfer(record, errors, gates)
    _check_structure(record, errors, gates)
    _check_vcycle(record, errors, gates)
    _check_krylov(record, provenance, errors, gates)
    if errors:
        classification = "CONTRACT_INVALID"
    elif gates:
        classification = "C1_SMALL_GATE_FAIL"
    else:
        classification = "SMALL_SAME_MESH_PMG_PASS"
    return {
        "schema": CHECKER_SCHEMA,
        "passed": not errors and not gates,
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "watchdog": watchdog,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    result = check_record(
        args.record,
        expected_source_sha=args.expected_source_sha,
        watchdog_compact=args.watchdog_compact,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if result["passed"] else 1


__all__ = [
    "CHECKER_SCHEMA",
    "_check_watchdog",
    "_validate_watchdog_worker_command",
    "check_record",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
