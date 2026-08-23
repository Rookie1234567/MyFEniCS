"""Thin K0/K1 worker for the independent Krylov LOR-HX requalification lane.

The historical K0 route records one p2/h50 MPI1 attempt; the K1 suite route
parameterizes the four frozen degree/MPI cases and four frozen sources.
Numerical construction remains in ``src.solvers.fullspace_lor_hx_krylov`` and
the existing positive fixture; this file only owns provenance, canonical
evidence, and lifecycle markers.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.run_task038_full3d_lor_hx import (
    _append_stage_marker,
    _prepare_paths,
    _runtime_identity,
    _source_identity,
)
from src.solvers.fullspace_lor_hx_krylov import (
    K0_ALPHA_PRODUCTION_APPLIED,
    K0_CHECKPOINTS,
    K0_DIRECTION_INPUT_ROLE,
    K0_SETTINGS,
    alpha_diagnostic,
    destroy_k0_gmres_result,
    relative_error,
    run_k0_gmres,
    two_direction_linearity,
)
from src.solvers.fullspace_lor_native_hx_fixture import (
    L2_SOURCE_NAMES,
    RealL2PositiveHXFixture,
    l2_source_formula,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-native-complex-hx.k0-record.v1"
K0_SOURCE_FORMULA = (
    "analytic deterministic pseudo-random edge field from fixed noninteger "
    "trigonometric frequencies and phases"
)
K0_PHASE_APPLICATION = "algebraic_slave_zero_action_internal_finalized_mpc_once"
OLD_L2_RECORD_SHA = "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3"
OLD_L2_RHO = 1.7348663090876784
OLD_L2_LIMIT = 0.45
OLD_L2_CLASSIFICATION = "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE"
K0_WORKER_RECORD_SHA = "87594e2c06de8ea031dad0ce8ac364626dcc2dbb6d9ff8846ad6f19663d9098d"
K0_CHECKER_V2_SHA = "0ad2b91aceb08b5cdd5ae68944f3625689f0a3f38c2ae0dfeb43461a827df807"
K1_SCHEMA = "task038.lor-native-complex-hx.k1-suite-record.v1"
K1_CASE_SPECS = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
}
K1_SOURCE_NAMES = tuple(L2_SOURCE_NAMES)


def _vec_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    numerator = float(difference.norm())
    denominator = max(float(right.norm()), np.finfo(float).tiny)
    difference.destroy()
    return numerator / denominator


def _vec_global_norm_ratio(numerator: Any, denominator: Any) -> float:
    """Return ``||numerator||_2 / ||denominator||_2`` using PETSc norms."""

    denominator_norm = max(float(denominator.norm()), np.finfo(float).tiny)
    return float(numerator.norm()) / denominator_norm


def _vec_finite(comm: MPI.Comm, vector: Any) -> bool:
    local = bool(np.all(np.isfinite(vector.getArray(readonly=True))))
    return bool(comm.allreduce(1 if local else 0, op=MPI.MIN))


def _global_bool(comm: MPI.Comm, value: bool) -> bool:
    return bool(comm.allreduce(1 if value else 0, op=MPI.MIN))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _packet_digest(key: Any) -> str:
    return hashlib.sha256(_json_bytes(key)).hexdigest()


def _sort_packets(packets: list[tuple[Any, complex]]) -> list[tuple[Any, complex]]:
    return sorted(packets, key=lambda item: _packet_digest(item[0]))


def _merge_packets(parts: list[list[tuple[Any, complex]]]) -> tuple[np.ndarray, np.ndarray]:
    merged: dict[str, complex] = {}
    for packets in parts:
        for key, value in packets:
            digest = _packet_digest(key)
            if digest in merged:
                raise RuntimeError(f"duplicate canonical packet {digest}")
            merged[digest] = complex(value)
    keys = np.asarray(sorted(merged), dtype="<U64")
    values = np.asarray([merged[key] for key in keys], dtype=np.complex128)
    return keys, values


def _artifact(raw_dir: Path, name: str, array: np.ndarray) -> dict[str, Any]:
    path = raw_dir / f"{name}.npy"
    array = np.asarray(array)
    np.save(path, array, allow_pickle=False)
    return {
        "name": name,
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(array.dtype),
        "shape": list(array.shape),
    }


def _canonical_packets(fixture: Any, vector: Any, role: str) -> list[tuple[Any, complex]]:
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    if role == "primal":
        return extract_canonical_full_fe_packets(
            fixture.high_space, vector, fixture.high_floquet
        )[0]
    if role == "dual":
        return extract_canonical_full_fe_dual_packets(
            fixture.high_space, fixture.high_floquet.mpc, vector
        )[0]
    raise ValueError(f"unknown canonical role {role!r}")


def _write_canonical_role(
    comm: MPI.Comm,
    fixture: Any,
    raw_dir: Path,
    role: str,
    vector: Any,
    vector_role: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, str] | None:
    packets = _canonical_packets(fixture, vector, vector_role)
    gathered = comm.gather(packets, root=0)
    if comm.rank != 0:
        return None
    keys, values = _merge_packets(gathered)
    key_name = f"{role}_keys"
    value_name = f"{role}_values"
    artifacts.append(_artifact(raw_dir, key_name, keys))
    artifacts.append(_artifact(raw_dir, value_name, values))
    return {"keys": key_name, "values": value_name}


def _write_numpy_role(
    raw_dir: Path,
    role: str,
    values: np.ndarray,
    artifacts: list[dict[str, Any]],
    canonical_keys: np.ndarray | None = None,
) -> dict[str, str]:
    keys = (
        np.asarray(canonical_keys, dtype="<U64")
        if canonical_keys is not None
        else np.asarray([f"row-{index}" for index in range(values.size)], dtype="<U32")
    )
    key_name = f"{role}_keys"
    value_name = f"{role}_values"
    artifacts.append(_artifact(raw_dir, key_name, keys))
    artifacts.append(_artifact(raw_dir, value_name, np.asarray(values, dtype=np.complex128)))
    return {"keys": key_name, "values": value_name}


def _destroy_vectors(vectors: list[Any]) -> None:
    for vector in vectors:
        if vector is not None:
            vector.destroy()


def run_worker(
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
    case: str,
) -> None:
    comm = MPI.COMM_WORLD
    if case != "p2-mpi1" or expected_mpi_size != 1 or comm.size != 1:
        raise ValueError("K0 currently accepts only p2-mpi1/MPI1")
    _prepare_paths(raw_dir, record_path, comm, stage="k0")
    _append_stage_marker(raw_dir, "paths_ready", comm.rank)
    root = Path.cwd()
    source = _source_identity(root, expected_source_sha)
    source["commit_sha_end"] = source["commit_sha_start"]
    source["tracked_status_end"] = source["tracked_status_start"]
    source["clean_end"] = source["clean_start"]
    _append_stage_marker(raw_dir, "source_identity_closed", comm.rank)
    runtime = _runtime_identity(root, expected_mpi_size)
    _append_stage_marker(raw_dir, "runtime_identity", comm.rank)

    fixture = None
    source_before = source_after = residual = None
    residual_before = residual_after = None
    pc_output = pc_repeat = applied_output = true_residual = None
    k0_result: dict[str, Any] | None = None
    try:
        fixture = RealL2PositiveHXFixture(2, comm)
        _append_stage_marker(raw_dir, "fixture_built", comm.rank)
        source_before, source_facts = fixture.build_l2_source("random")
        residual = fixture.apply_high_action_copy(source_before)
        source_after = source_before.copy()
        residual_before = residual.copy()
        pc_output = fixture.apply_high_preconditioner(residual)
        pc_repeat = fixture.apply_high_preconditioner(residual)
        residual_after = residual.copy()
        applied_output = fixture.apply_high_action_copy(pc_output)
        true_residual = residual.copy()
        true_residual.axpy(-1.0, applied_output)
        _append_stage_marker(raw_dir, "k0_one_apply", comm.rank)

        from src.solvers.hcurl_canonical_vector_dolfinx import (
            extract_canonical_full_fe_packets,
            reconstruct_canonical_full_fe_dual_vector,
        )

        residual_packets = _sort_packets(_canonical_packets(fixture, residual, "dual"))
        packet_keys = [key for key, _value in residual_packets]
        canonical_keys = np.asarray(
            [_packet_digest(key) for key in packet_keys], dtype="<U64"
        )
        residual_values = np.asarray(
            [value for _key, value in residual_packets], dtype=np.complex128
        )
        output_packets = _sort_packets(
            _canonical_packets(fixture, pc_output, "primal")
        )
        output_packet_keys = [key for key, _value in output_packets]
        output_canonical_keys = np.asarray(
            [_packet_digest(key) for key in output_packet_keys], dtype="<U64"
        )

        def apply_canonical(values: np.ndarray) -> np.ndarray:
            packet_values = [
                (key, complex(value))
                for key, value in zip(packet_keys, values, strict=True)
            ]
            vector = reconstruct_canonical_full_fe_dual_vector(
                fixture.high_space,
                fixture.high_floquet.mpc,
                packet_values,
            )
            output = fixture.apply_high_preconditioner(vector)
            try:
                packets = extract_canonical_full_fe_packets(
                    fixture.high_space, output, fixture.high_floquet
                )[0]
                values_by_key = {
                    _packet_digest(key): complex(value) for key, value in packets
                }
                if set(values_by_key) != set(output_canonical_keys.tolist()):
                    raise RuntimeError("canonical linearity output key set changed")
                return np.asarray(
                    [values_by_key[key] for key in output_canonical_keys],
                    dtype=np.complex128,
                )
            finally:
                output.destroy()
                vector.destroy()

        linearity = two_direction_linearity(
            apply_canonical, residual_values, canonical_keys, output_canonical_keys
        )
        _append_stage_marker(raw_dir, "k0_linearity", comm.rank)
        applied_packets = _canonical_packets(fixture, applied_output, "dual")
        applied_by_key = {
            _packet_digest(key): complex(value) for key, value in applied_packets
        }
        if set(applied_by_key) != set(canonical_keys.tolist()):
            raise RuntimeError("one-apply canonical action key set changed")
        applied_values = np.asarray(
            [applied_by_key[key] for key in canonical_keys], dtype=np.complex128
        )
        alpha = alpha_diagnostic(
            residual_values,
            applied_values,
        )
        k0_result = run_k0_gmres(fixture, residual)
        _append_stage_marker(raw_dir, "krylov_ready", comm.rank)
        _append_stage_marker(raw_dir, "krylov_solved", comm.rank)

        artifacts: list[dict[str, Any]] = []
        one_apply_roles: dict[str, dict[str, str] | None] = {}
        one_apply_roles["source_before"] = _write_canonical_role(
            comm, fixture, raw_dir, "k0_random_source_before", source_before, "primal", artifacts
        )
        one_apply_roles["source_after"] = _write_canonical_role(
            comm, fixture, raw_dir, "k0_random_source_after", source_after, "primal", artifacts
        )
        for role, vector, vector_role in (
            ("residual_before", residual_before, "dual"),
            ("residual_after", residual_after, "dual"),
            ("residual", residual, "dual"),
            ("pc_output", pc_output, "primal"),
            ("pc_repeat", pc_repeat, "primal"),
            ("applied_output", applied_output, "dual"),
            ("true_residual", true_residual, "dual"),
        ):
            one_apply_roles[role] = _write_canonical_role(
                comm, fixture, raw_dir, f"k0_random_{role}", vector, vector_role, artifacts
            )

        linearity_roles: dict[str, dict[str, str]] = {}
        for role, values in linearity["direction_values"].items():
            linearity_roles[role] = _write_numpy_role(
                raw_dir,
                f"k0_linearity_{role}",
                values,
                artifacts,
                canonical_keys if role in {"r1", "r2", "combined"} else output_canonical_keys,
            )

        checkpoint_records: dict[str, dict[str, Any]] = {}
        for checkpoint in K0_CHECKPOINTS:
            status = k0_result["checkpoint_status"][checkpoint]
            item: dict[str, Any] = {"status": status}
            if status == "measured":
                vectors = k0_result["checkpoints"][checkpoint]
                roles: dict[str, dict[str, str]] = {}
                for role, vector, vector_role in (
                    ("solution", vectors["solution"], "primal"),
                    ("action", vectors["action"], "dual"),
                    ("true_residual", vectors["true_residual"], "dual"),
                ):
                    roles[role] = _write_canonical_role(
                        comm,
                        fixture,
                        raw_dir,
                        f"k0_checkpoint_{checkpoint}_{role}",
                        vector,
                        vector_role,
                        artifacts,
                    )
                item["artifacts"] = roles
            checkpoint_records[str(checkpoint)] = item

        _append_stage_marker(raw_dir, "canonical_packets_gathered", comm.rank)
        if comm.rank == 0:
            record = {
                "schema": SCHEMA,
                "stage": "k0",
                "scope": "krylov_requalification",
                "case": case,
                "degree": 2,
                "mpi_size": 1,
                "raw_dir": str(raw_dir.resolve()),
                "command": [
                    str(Path(sys.executable).resolve()),
                    "-m",
                    "benchmarks.run_task038_full3d_lor_hx_krylov",
                    "--case",
                    case,
                    "--raw-dir",
                    str(raw_dir.resolve()),
                    "--record",
                    str(record_path.resolve()),
                    "--expected-source-sha",
                    expected_source_sha,
                    "--expected-mpi-size",
                    str(expected_mpi_size),
                ],
                "source": source,
                "runtime": runtime,
                "settings": K0_SETTINGS.as_dict(),
                "old_l2_reference": {
                    "record_sha256": OLD_L2_RECORD_SHA,
                    "rho": OLD_L2_RHO,
                    "limit": OLD_L2_LIMIT,
                    "classification": OLD_L2_CLASSIFICATION,
                },
                "source_facts": {
                    **_jsonable(source_facts),
                    "name": "random",
                    "formula": K0_SOURCE_FORMULA,
                    "phase_application": K0_PHASE_APPLICATION,
                    "primal_role": "full_fe",
                },
                "one_apply": {
                    "artifacts": one_apply_roles,
                    "input_role": "dual",
                    "output_role": "primal",
                    "rho": float(
                        true_residual.norm()
                        / max(residual.norm(), np.finfo(float).tiny)
                    ),
                    "residual_norm": float(residual.norm()),
                    "finite": bool(
                        np.all(np.isfinite(residual.array))
                        and np.all(np.isfinite(pc_output.array))
                        and np.all(np.isfinite(applied_output.array))
                        and np.all(np.isfinite(true_residual.array))
                    ),
                    "source_unchanged": bool(
                        np.array_equal(source_before.array, source_after.array)
                    ),
                    "residual_input_unchanged": bool(
                        np.array_equal(residual_before.array, residual_after.array)
                    ),
                    "repeat_relative": relative_error(pc_repeat.array, pc_output.array),
                    "alpha": {
                        "alpha_star": alpha["alpha_star"],
                        "rho_alpha": alpha["rho_alpha"],
                        "production_pc_alpha_applied": K0_ALPHA_PRODUCTION_APPLIED,
                    },
                },
                "linearity": {
                    "construction": linearity["construction"],
                    "input_role": linearity["input_role"],
                    "input_semantics": K0_DIRECTION_INPUT_ROLE,
                    "output_role": linearity["output_role"],
                    "output_semantics": "full_fe_primal_canonical_packets",
                    "input_key_set_sha256": linearity["input_key_set_sha256"],
                    "output_key_set_sha256": linearity["output_key_set_sha256"],
                    "direction_mask": linearity["direction_mask"],
                    "coefficient_a": linearity["coefficient_a"],
                    "coefficient_b": linearity["coefficient_b"],
                    "direction_norms": linearity["direction_norms"],
                    "relative": linearity["relative"],
                    "repeat_relative": linearity["repeat_relative"],
                    "finite": linearity["finite"],
                    "input_unchanged": linearity["input_unchanged"],
                    "artifacts": linearity_roles,
                },
                "krylov": {
                    "history": k0_result["history"],
                    "checkpoints": checkpoint_records,
                    "reason": int(k0_result["reason"]),
                    "iterations": int(k0_result["iterations"]),
                    "first_true_pass_iteration": k0_result["first_true_pass_iteration"],
                    "late_true_pass_iteration": k0_result["late_true_pass_iteration"],
                    "qualification_pass": bool(k0_result["qualification_pass"]),
                    "reported_final_residual": k0_result["reported_final_residual"],
                    "matvec_count": int(k0_result["operator_context"].matvec_count),
                    "pc_apply_count": int(k0_result["pc_context"].apply_count),
                    "monitor_action_count": int(k0_result["monitor_action_count"]),
                },
                "fixture_audit": _jsonable(fixture.audit),
                "hx_audit_after_k0": _jsonable(fixture.hx.audit),
                "production": {
                    "production_pc_alpha_applied": K0_ALPHA_PRODUCTION_APPLIED,
                    "global_numeric_allgather": False,
                    "global_high_order_aij": False,
                    "global_dense_transfer": False,
                    "global_direct_coarse": False,
                    "evidence_root_gather_only": True,
                },
                "forbidden": {
                    "global_numeric_allgather": False,
                    "high_order_global_aij": False,
                    "global_dense_transfer": False,
                    "global_direct_coarse": False,
                },
                "artifacts": artifacts,
                "status": "facts_written_not_qualified",
            }
            record_path.write_bytes(_json_bytes(record))
            _append_stage_marker(raw_dir, "record_written", comm.rank)
            print(
                json.dumps(
                    {
                        "record": str(record_path),
                        "case": case,
                        "status": record["status"],
                        "first_true_pass_iteration": record["krylov"]["first_true_pass_iteration"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        comm.barrier()
    finally:
        if k0_result is not None:
            destroy_k0_gmres_result(k0_result)
        _destroy_vectors(
            [
                true_residual,
                residual_after,
                residual_before,
                applied_output,
                pc_repeat,
                pc_output,
                residual,
                source_after,
                source_before,
            ]
        )
        if fixture is not None:
            fixture.destroy()


def run_suite_worker(
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
    case: str,
    source_name: str,
) -> None:
    """Record one parameterized K1 degree/MPI/source suite member."""

    comm = MPI.COMM_WORLD
    try:
        degree, case_mpi_size = K1_CASE_SPECS[case]
    except KeyError as exc:
        raise ValueError(f"unsupported K1 suite case {case!r}") from exc
    if source_name not in K1_SOURCE_NAMES:
        raise ValueError(f"unsupported K1 suite source {source_name!r}")
    if expected_mpi_size != case_mpi_size or comm.size != case_mpi_size:
        raise ValueError("K1 case and MPI size do not agree")

    _prepare_paths(raw_dir, record_path, comm, stage="k1-suite")
    _append_stage_marker(raw_dir, "paths_ready", comm.rank)
    root = Path.cwd()
    source = _source_identity(root, expected_source_sha) if comm.rank == 0 else None
    source = comm.bcast(source, root=0)
    source["probe_rank"] = 0
    source["probe_scope"] = "rank0_git_probe_broadcast"
    _append_stage_marker(raw_dir, "source_identity_broadcast", comm.rank)
    runtime = _runtime_identity(root, expected_mpi_size)
    _append_stage_marker(raw_dir, "runtime_identity", comm.rank)

    fixture = None
    source_before = source_after = residual = None
    residual_before = residual_after = None
    pc_output = pc_repeat = applied_output = true_residual = None
    final_solution = final_action = final_true_residual = None
    k1_result: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = []
    try:
        fixture = RealL2PositiveHXFixture(degree, comm)
        _append_stage_marker(raw_dir, "fixture_built", comm.rank)
        source_before, source_facts = fixture.build_l2_source(source_name)
        residual = fixture.apply_high_action_copy(source_before)
        source_after = source_before.copy()
        residual_before = residual.copy()
        pc_output = fixture.apply_high_preconditioner(residual)
        pc_repeat = fixture.apply_high_preconditioner(residual)
        residual_after = residual.copy()
        applied_output = fixture.apply_high_action_copy(pc_output)
        true_residual = residual.copy()
        true_residual.axpy(-1.0, applied_output)
        repeat_relative = _vec_relative(pc_repeat, pc_output)
        rho = _vec_global_norm_ratio(true_residual, residual)
        finite = True
        for vector in (
            source_before,
            source_after,
            residual,
            pc_output,
            pc_repeat,
            applied_output,
            true_residual,
        ):
            finite = _vec_finite(comm, vector) and finite
        source_unchanged = _global_bool(
            comm, np.array_equal(source_before.array, source_after.array)
        )
        residual_input_unchanged = _global_bool(
            comm, np.array_equal(residual_before.array, residual_after.array)
        )
        _append_stage_marker(raw_dir, "suite_one_apply", comm.rank)

        k1_result = run_k0_gmres(fixture, residual)
        final_solution = k1_result["solution"].copy()
        final_action = fixture.apply_high_action_copy(k1_result["solution"])
        final_true_residual = residual.copy()
        final_true_residual.axpy(-1.0, final_action)
        _append_stage_marker(raw_dir, "suite_krylov_solved", comm.rank)

        one_apply_roles: dict[str, dict[str, str] | None] = {}
        prefix = f"k1_{source_name}"
        one_apply_roles["source_before"] = _write_canonical_role(
            comm, fixture, raw_dir, f"{prefix}_source_before", source_before, "primal", artifacts
        )
        one_apply_roles["source_after"] = _write_canonical_role(
            comm, fixture, raw_dir, f"{prefix}_source_after", source_after, "primal", artifacts
        )
        for role, vector, vector_role in (
            ("residual_before", residual_before, "dual"),
            ("residual_after", residual_after, "dual"),
            ("residual", residual, "dual"),
            ("pc_output", pc_output, "primal"),
            ("pc_repeat", pc_repeat, "primal"),
            ("applied_output", applied_output, "dual"),
            ("true_residual", true_residual, "dual"),
        ):
            one_apply_roles[role] = _write_canonical_role(
                comm, fixture, raw_dir, f"{prefix}_{role}", vector, vector_role, artifacts
            )

        checkpoint_records: dict[str, dict[str, Any]] = {}
        for checkpoint in K0_CHECKPOINTS:
            status = k1_result["checkpoint_status"][checkpoint]
            item: dict[str, Any] = {"status": status}
            if status == "measured":
                vectors = k1_result["checkpoints"][checkpoint]
                roles: dict[str, dict[str, str]] = {}
                for role, vector, vector_role in (
                    ("solution", vectors["solution"], "primal"),
                    ("action", vectors["action"], "dual"),
                    ("true_residual", vectors["true_residual"], "dual"),
                ):
                    roles[role] = _write_canonical_role(
                        comm,
                        fixture,
                        raw_dir,
                        f"{prefix}_checkpoint_{checkpoint}_{role}",
                        vector,
                        vector_role,
                        artifacts,
                    )
                item["artifacts"] = roles
            checkpoint_records[str(checkpoint)] = item

        final_roles = {
            "solution": _write_canonical_role(
                comm, fixture, raw_dir, f"{prefix}_final_solution", final_solution, "primal", artifacts
            ),
            "action": _write_canonical_role(
                comm, fixture, raw_dir, f"{prefix}_final_action", final_action, "dual", artifacts
            ),
            "true_residual": _write_canonical_role(
                comm,
                fixture,
                raw_dir,
                f"{prefix}_final_true_residual",
                final_true_residual,
                "dual",
                artifacts,
            ),
        }
        _append_stage_marker(raw_dir, "canonical_packets_gathered", comm.rank)

        rank_fact = {
            "rank": int(comm.rank),
            "runtime": runtime,
            "matvec_count": int(k1_result["operator_context"].matvec_count),
            "pc_apply_count": int(k1_result["pc_context"].apply_count),
            "monitor_action_count": int(k1_result["monitor_action_count"]),
            "iterations": int(k1_result["iterations"]),
            "reason": int(k1_result["reason"]),
        }
        rank_facts = comm.gather(rank_fact, root=0)
        if comm.rank == 0:
            count_ranges = {
                key: {
                    "min": min(int(item[key]) for item in rank_facts),
                    "max": max(int(item[key]) for item in rank_facts),
                }
                for key in ("matvec_count", "pc_apply_count", "monitor_action_count")
            }
            record = {
                "schema": K1_SCHEMA,
                "stage": "k1-suite",
                "scope": "krylov_requalification_suite",
                "case": case,
                "degree": degree,
                "source_name": source_name,
                "mpi_size": expected_mpi_size,
                "raw_dir": str(raw_dir.resolve()),
                "command": [
                    str(Path(sys.executable).resolve()),
                    "-m",
                    "benchmarks.run_task038_full3d_lor_hx_krylov",
                    "--stage",
                    "k1-suite",
                    "--case",
                    case,
                    "--source",
                    source_name,
                    "--raw-dir",
                    str(raw_dir.resolve()),
                    "--record",
                    str(record_path.resolve()),
                    "--expected-source-sha",
                    expected_source_sha,
                    "--expected-mpi-size",
                    str(expected_mpi_size),
                ],
                "source": source,
                "runtime": runtime,
                "rank_facts": rank_facts,
                "settings": K0_SETTINGS.as_dict(),
                "old_l2_reference": {
                    "record_sha256": OLD_L2_RECORD_SHA,
                    "rho": OLD_L2_RHO,
                    "limit": OLD_L2_LIMIT,
                    "classification": OLD_L2_CLASSIFICATION,
                },
                "linearity_authority": {
                    "status": "引用K0 authority，不在K1重复计算",
                    "record_path": "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_krylov_p2_mpi1_random_v1.json",
                    "record_sha256": K0_WORKER_RECORD_SHA,
                    "checker_path": "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_krylov_p2_mpi1_random_check_v2.json",
                    "checker_sha256": K0_CHECKER_V2_SHA,
                    "old_one_apply_rho": OLD_L2_RHO,
                    "old_one_apply_classification": OLD_L2_CLASSIFICATION,
                },
                "source_facts": {
                    **_jsonable(source_facts),
                    "name": source_name,
                    "formula": l2_source_formula(source_name),
                    "phase_application": K0_PHASE_APPLICATION,
                    "primal_role": "full_fe",
                },
                "one_apply": {
                    "artifacts": one_apply_roles,
                    "input_role": "dual",
                    "output_role": "primal",
                    "rho": float(rho),
                    "rho_status": "diagnostic_only_not_a_gate",
                    "residual_norm": float(residual.norm()),
                    "finite": finite,
                    "source_unchanged": source_unchanged,
                    "residual_input_unchanged": residual_input_unchanged,
                    "repeat_relative": float(repeat_relative),
                    "alpha_status": "not_repeated_by_contract",
                },
                "krylov": {
                    "history": k1_result["history"],
                    "checkpoints": checkpoint_records,
                    "final_artifacts": final_roles,
                    "reason": int(k1_result["reason"]),
                    "iterations": int(k1_result["iterations"]),
                    "first_true_pass_iteration": k1_result["first_true_pass_iteration"],
                    "late_true_pass_iteration": k1_result["late_true_pass_iteration"],
                    "qualification_pass": bool(k1_result["qualification_pass"]),
                    "reported_final_residual": k1_result["reported_final_residual"],
                    "final_true_residual": float(
                        final_true_residual.norm()
                        / max(float(residual.norm()), np.finfo(float).tiny)
                    ),
                    "matvec_count": int(k1_result["operator_context"].matvec_count),
                    "pc_apply_count": int(k1_result["pc_context"].apply_count),
                    "monitor_action_count": int(k1_result["monitor_action_count"]),
                    "final_action_count": 1,
                },
                "count_ranges": count_ranges,
                "fixture_audit": _jsonable(fixture.audit),
                "hx_audit_after_k1": _jsonable(fixture.hx.audit),
                "production": {
                    "production_pc_alpha_applied": False,
                    "global_numeric_allgather": False,
                    "high_order_global_aij": False,
                    "global_dense_transfer": False,
                    "global_direct_coarse": False,
                    "evidence_root_gather_only": True,
                },
                "forbidden": {
                    "production_pc_alpha_applied": False,
                    "global_numeric_allgather": False,
                    "high_order_global_aij": False,
                    "global_dense_transfer": False,
                    "global_direct_coarse": False,
                },
                "artifacts": artifacts,
                "status": "facts_written_no_worker_classification",
            }
            record_path.write_bytes(_json_bytes(record))
            print(
                json.dumps(
                    {
                        "record": str(record_path),
                        "case": case,
                        "source": source_name,
                        "status": record["status"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        _append_stage_marker(raw_dir, "record_written", comm.rank)
        comm.barrier()
    finally:
        if k1_result is not None:
            destroy_k0_gmres_result(k1_result)
        _destroy_vectors(
            [
                final_true_residual,
                final_action,
                final_solution,
                true_residual,
                residual_after,
                residual_before,
                applied_output,
                pc_repeat,
                pc_output,
                residual,
                source_after,
                source_before,
            ]
        )
        if fixture is not None:
            fixture.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("k0", "k1-suite"), default="k0")
    parser.add_argument("--case", required=True)
    parser.add_argument("--source")
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", required=True, type=int)
    args = parser.parse_args(argv)
    if args.stage == "k1-suite":
        if args.source is None:
            parser.error("--source is required for --stage k1-suite")
        run_suite_worker(
            args.raw_dir,
            args.record,
            args.expected_source_sha,
            args.expected_mpi_size,
            args.case,
            args.source,
        )
    else:
        if args.source is not None:
            parser.error("--source is only valid for --stage k1-suite")
        run_worker(
            args.raw_dir,
            args.record,
            args.expected_source_sha,
            args.expected_mpi_size,
            args.case,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
