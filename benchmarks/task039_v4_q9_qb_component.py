"""Research-only MPI8 operator parity component for Task039 Q-B."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import resource
import sys
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task039_v4_h4_hybrid_direct import (
    _validate_shared_h4_mode_identity,
    validate_v4_h4_specification,
)
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.quadratic_beta_eigenproblem import assemble_quadratic_beta_operators
from src.modes.selected_mode_packet import load_selected_mode_packet

ROOT = Path(__file__).resolve().parents[1]
FIXED_PROBE_COUNT = 4
METRIC_SPACE = "distributed_owner_row_coefficient_euclidean"
METRIC_KEYS = (
    "max_principal_angle_rad",
    "projector_error",
    "relative_reconstruction_error",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_norm(value: np.ndarray, reference: np.ndarray) -> float:
    scale = max(float(np.linalg.norm(reference)), 1.0e-30)
    return float(np.linalg.norm(value) / scale)


def audit_qep_sign_involution(
    k0: np.ndarray,
    k1: np.ndarray,
    k2: np.ndarray,
    sign: np.ndarray,
    *,
    beta: complex = 0.137 - 0.271j,
) -> dict[str, Any]:
    """Check the QEP sign identity on a small dense component fixture."""

    matrices = [np.asarray(value, dtype=np.complex128) for value in (k0, k1, k2)]
    if any(value.ndim != 2 or value.shape[0] != value.shape[1] for value in matrices):
        raise ValueError("QEP coefficient matrices must be square")
    size = matrices[0].shape[0]
    if any(value.shape != (size, size) for value in matrices[1:]):
        raise ValueError("QEP coefficient matrix shapes differ")
    sign_values = np.asarray(sign, dtype=np.complex128)
    if sign_values.ndim == 1:
        if sign_values.shape != (size,):
            raise ValueError("QEP sign vector has the wrong size")
        sign_matrix = np.diag(sign_values)
    elif sign_values.shape == (size, size):
        sign_matrix = sign_values
    else:
        raise ValueError("QEP sign must be a vector or square matrix")
    involution = _relative_norm(sign_matrix @ sign_matrix - np.eye(size), np.eye(size))
    even0 = _relative_norm(
        sign_matrix @ matrices[0] @ sign_matrix - matrices[0], matrices[0]
    )
    odd1 = _relative_norm(
        sign_matrix @ matrices[1] @ sign_matrix + matrices[1], matrices[1]
    )
    even2 = _relative_norm(
        sign_matrix @ matrices[2] @ sign_matrix - matrices[2], matrices[2]
    )
    q_plus = matrices[0] + beta * matrices[1] + beta**2 * matrices[2]
    q_minus = matrices[0] - beta * matrices[1] + beta**2 * matrices[2]
    polynomial = _relative_norm(sign_matrix @ q_plus @ sign_matrix - q_minus, q_minus)
    errors = (involution, even0, odd1, even2, polynomial)
    return {
        "sign_definition": "diag(+I_Et,-I_Ez)",
        "involution_error": involution,
        "K0_even_relative_error": even0,
        "K1_odd_relative_error": odd1,
        "K2_even_relative_error": even2,
        "Q_beta_to_minus_beta_relative_error": polynomial,
        "right_map": "S",
        "left_map": "S",
        "additional_conjugation": False,
        "beta": [float(complex(beta).real), float(complex(beta).imag)],
        "pass": bool(np.isfinite(errors).all() and max(errors) <= 1.0e-12),
    }


def _relative_error(first: Any, second: Any) -> float:
    scale = max(float(second.norm()), 1.0e-30)
    difference = first.duplicate()
    first.copy(difference)
    difference.axpy(-1.0, second)
    value = float(difference.norm()) / scale
    difference.destroy()
    return value


def _owned_sign(spaces: Any, full_local_size: int) -> np.ndarray:
    transverse = np.asarray(spaces.transverse_to_mixed, dtype=np.int64)
    longitudinal = np.asarray(spaces.longitudinal_to_mixed, dtype=np.int64)
    transverse = transverse[(transverse >= 0) & (transverse < full_local_size)]
    longitudinal = longitudinal[(longitudinal >= 0) & (longitudinal < full_local_size)]
    overlap = np.intersect1d(transverse, longitudinal)
    covered = np.unique(np.concatenate((transverse, longitudinal)))
    if overlap.size or covered.size != full_local_size:
        raise RuntimeError("mixed Et/Ez ownership does not define one sign per row")
    signs = np.ones(full_local_size, dtype=np.complex128)
    signs[longitudinal] = -1.0
    return signs


def _apply_sign(
    transform: Any,
    matrix: Any,
    signs: np.ndarray,
    free_local: list[int],
    vector: Any,
) -> Any:
    full = transform.createVecLeft()
    transform.mult(vector, full)
    values = np.asarray(full.getArray(readonly=True), dtype=np.complex128)
    result = matrix.createVecRight()
    result.getArray()[:] = values[free_local] * signs[free_local]
    full.destroy()
    return result


def _probe_vector(matrix: Any, index: int) -> Any:
    vector = matrix.createVecRight()
    start, end = (int(value) for value in vector.getOwnershipRange())
    global_index = np.arange(start, end, dtype=np.float64)
    vector.getArray()[:] = np.sin(
        (global_index + 1.0) * (index + 1.0) * 0.017
    ) + 1j * np.cos((global_index + 2.0) * (index + 2.0) * 0.013)
    return vector


def _matrix_action(matrix: Any, vector: Any) -> Any:
    result = matrix.createVecLeft()
    matrix.mult(vector, result)
    return result


def _qep_action(k0: Any, k1: Any, k2: Any, beta: complex, vector: Any) -> Any:
    result = _matrix_action(k0, vector)
    work = _matrix_action(k1, vector)
    result.axpy(beta, work)
    work.destroy()
    work = _matrix_action(k2, vector)
    result.axpy(beta * beta, work)
    work.destroy()
    return result


def _free_row_layout(operators: Any) -> list[int]:
    transform = operators.transform.matrix
    row_start, row_end = (int(value) for value in transform.getOwnershipRange())
    local_slaves = {int(value) for value in operators.constraints.slave_global}
    free_local = [
        global_index - row_start
        for global_index in range(row_start, row_end)
        if global_index not in local_slaves
    ]
    if len(free_local) != int(operators.transform.reduced_local_size):
        raise RuntimeError("reduced ownership does not match the free mixed rows")
    reduced_start, reduced_end = (
        int(value) for value in operators.K0.getOwnershipRange()
    )
    for local_index, full_offset in enumerate(free_local):
        columns, values = transform.getRow(row_start + full_offset)
        if len(columns) != 1 or int(columns[0]) != reduced_start + local_index:
            raise RuntimeError(
                "constraint transform free rows are not the documented identity "
                "map into the rank-local reduced ordering"
            )
        if abs(complex(values[0]) - 1.0) > 1.0e-12:
            raise RuntimeError("constraint transform free-row identity is not one")
    if reduced_end - reduced_start != len(free_local):
        raise RuntimeError("reduced ownership range disagrees with free-row count")
    return free_local


def _operator_parity_audit(operators: Any, spaces: Any) -> dict[str, Any]:
    transform = operators.transform.matrix
    free_local = _free_row_layout(operators)
    signs = _owned_sign(spaces, int(operators.transform.full_local_size))
    matrices = {
        "K0": (operators.K0, 1.0),
        "K1": (operators.K1, -1.0),
        "K2": (operators.K2, 1.0),
    }
    errors = {name: [] for name in matrices}
    involution_errors = []
    q_errors = []
    beta = 0.137 - 0.271j
    for probe in range(FIXED_PROBE_COUNT):
        vector = _probe_vector(operators.K0, probe)
        signed = _apply_sign(transform, operators.K0, signs, free_local, vector)
        signed_twice = _apply_sign(transform, operators.K0, signs, free_local, signed)
        involution_errors.append(_relative_error(signed_twice, vector))
        signed.destroy()
        signed_twice.destroy()
        for name, (matrix, parity) in matrices.items():
            matrix_vector = _matrix_action(matrix, vector)
            signed_vector = _apply_sign(
                transform, operators.K0, signs, free_local, vector
            )
            matrix_signed = _matrix_action(matrix, signed_vector)
            signed_matrix = _apply_sign(
                transform, operators.K0, signs, free_local, matrix_vector
            )
            if parity < 0:
                signed_matrix.scale(-1.0)
            errors[name].append(_relative_error(matrix_signed, signed_matrix))
            matrix_vector.destroy()
            signed_vector.destroy()
            matrix_signed.destroy()
            signed_matrix.destroy()
        q_signed = _apply_sign(transform, operators.K0, signs, free_local, vector)
        left = _qep_action(operators.K0, operators.K1, operators.K2, beta, q_signed)
        left_signed = _apply_sign(transform, operators.K0, signs, free_local, left)
        right = _qep_action(operators.K0, operators.K1, operators.K2, -beta, vector)
        q_errors.append(_relative_error(left_signed, right))
        q_signed.destroy()
        left.destroy()
        left_signed.destroy()
        right.destroy()
        vector.destroy()
    local = {
        "involution_error": max(involution_errors, default=0.0),
        **{
            f"{name}_relative_error": max(values, default=0.0)
            for name, values in errors.items()
        },
        "Q_beta_to_minus_beta_relative_error": max(q_errors, default=0.0),
    }
    comm = operators.K0.comm.tompi4py()
    global_values = {
        name: float(comm.allreduce(value, op=MPI.MAX)) for name, value in local.items()
    }
    global_values.update(
        {
            "sign_definition": "diag(+I_Et,-I_Ez)",
            "left_map": "S",
            "right_map": "S",
            "additional_conjugation": False,
            "probe_count": FIXED_PROBE_COUNT,
            "tolerance": 1.0e-10,
            "pass": max(global_values.values(), default=0.0) <= 1.0e-10,
        }
    )
    return global_values


def _source_provenance(comm: MPI.Intracomm, expected_sha: str) -> dict[str, Any]:
    if comm.rank == 0:
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            status = subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            payload = {"ok": True, "head": head, "status": status}
        except (OSError, subprocess.CalledProcessError) as error:
            payload = {"ok": False, "error": str(error)}
    else:
        payload = None
    payload = comm.bcast(payload, root=0)
    if not payload["ok"]:
        raise RuntimeError(f"cannot verify Q-B source provenance: {payload['error']}")
    head = str(payload["head"])
    status = str(payload["status"])
    expected = expected_sha.strip().lower()
    if (
        len(expected) != 40
        or any(character not in "0123456789abcdef" for character in expected)
        or head.lower() != expected
    ):
        raise RuntimeError("Q-B audit source SHA does not match current HEAD")
    if status:
        raise RuntimeError(
            "Q-B component requires a clean worktree including nonignored untracked paths"
        )
    return {
        "component_source_sha": head,
        "git_clean": True,
        "verification": "git_rev_parse_and_status_porcelain_all_untracked",
    }


def _packet_authority(
    manifest: dict[str, Any], shards: list[dict[str, Any]]
) -> dict[str, Any]:
    names = sorted(
        {str(name) for shard in shards for name in dict(shard.get("files", {}))}
    )
    expected = {
        "positive_right",
        "positive_left",
        "negative_right",
        "negative_left",
    }
    pairing = manifest.get("metadata", {}).get("reciprocal_pairing")
    pairing_present = isinstance(pairing, dict)
    return {
        "array_names": names,
        "stored_right_left_full": {
            "status": "present" if expected.issubset(names) else "not_proven",
            "source": "manifest.shards[*].files",
            "arrays": [name for name in names if name in expected],
        },
        "reciprocal_pairing_metadata": {
            "status": "present" if pairing_present else "not_proven",
            "source": (
                "manifest.metadata.reciprocal_pairing"
                if pairing_present
                else "source_contract_only"
            ),
            "complete": pairing.get("complete") if pairing_present else None,
            "count": pairing.get("count") if pairing_present else None,
        },
        "qep_workspace_persisted": manifest.get("qep_workspace_persisted"),
        "consumer_qep_required": manifest.get("consumer_qep_required"),
    }


def _owner_rows_to_reduced(
    matrix: Any,
    owner_rows: np.ndarray,
    free_local: list[int],
    signs: np.ndarray,
) -> Any:
    vector = matrix.createVecRight()
    vector.getArray()[:] = np.asarray(owner_rows)[free_local] * signs[free_local]
    return vector


def _polynomial_relative_residual(
    matrices: tuple[Any, Any, Any],
    beta: complex,
    vector: Any,
    frobenius_norms: tuple[float, float, float],
    *,
    hermitian: bool,
) -> float:
    residual = matrices[0].createVecLeft()
    work = matrices[0].createVecLeft()
    for index, matrix in enumerate(matrices):
        if hermitian:
            matrix.multHermitian(vector, work)
        else:
            matrix.mult(vector, work)
        coefficient = beta**index
        if index == 0:
            work.copy(residual)
        else:
            residual.axpy(coefficient, work)
    numerator = float(residual.norm(PETSc.NormType.NORM_2))
    denominator = float(vector.norm()) * sum(
        abs(beta) ** index * frobenius_norms[index] for index in range(3)
    )
    residual.destroy()
    work.destroy()
    return numerator / max(denominator, 1.0e-30)


def _allreduce_gram(first: np.ndarray, second: np.ndarray, comm: Any) -> np.ndarray:
    local = np.asarray(first.conj().T @ second, dtype=np.complex128)
    global_value = np.empty_like(local)
    comm.Allreduce(local, global_value, op=MPI.SUM)
    return global_value


def _subspace_metrics(
    first: np.ndarray, second: np.ndarray, comm: Any
) -> dict[str, float]:
    first_gram = _allreduce_gram(first, first, comm)
    second_gram = _allreduce_gram(second, second, comm)
    cross_gram = _allreduce_gram(first, second, comm)

    def inverse_square_root(value: np.ndarray) -> np.ndarray:
        hermitian = 0.5 * (value + value.conj().T)
        eigenvalues, eigenvectors = np.linalg.eigh(hermitian)
        if np.min(eigenvalues) <= 0.0:
            raise RuntimeError("paired subspace Gram matrix is not positive definite")
        return (eigenvectors * (1.0 / np.sqrt(eigenvalues))) @ eigenvectors.conj().T

    first_inverse = np.linalg.inv(first_gram)
    whitened = (
        inverse_square_root(first_gram) @ cross_gram @ inverse_square_root(second_gram)
    )
    singular_values = np.clip(np.linalg.svd(whitened, compute_uv=False).real, 0.0, 1.0)
    coefficients = first_inverse @ cross_gram
    residual_gram = second_gram - cross_gram.conj().T @ coefficients
    residual_energy = max(float(np.trace(residual_gram).real), 0.0)
    total_energy = max(float(np.trace(second_gram).real), 1.0e-30)
    return {
        "max_principal_angle_rad": float(np.max(np.arccos(singular_values))),
        "projector_error": float(
            np.sqrt(max(len(singular_values) - np.sum(singular_values**2), 0.0))
        ),
        "relative_reconstruction_error": float(np.sqrt(residual_energy / total_energy)),
    }


def _group_blocks(group_ids: Any, count: int) -> list[tuple[int, ...]]:
    values = [int(value) for value in group_ids[:count]]
    if len(values) != count or (
        count < len(group_ids) and group_ids[count - 1] == group_ids[count]
    ):
        raise ValueError("nested count splits a positive near-degenerate group")
    blocks: list[tuple[int, ...]] = []
    start = 0
    while start < count:
        group_id = values[start]
        stop = start + 1
        while stop < count and values[stop] == group_id:
            stop += 1
        blocks.append(tuple(range(start, stop)))
        start = stop
    return blocks


def _pair_targets(
    pairs: list[Mapping[str, Any]],
    count: int,
    negative_groups: Any,
    positive_blocks: list[tuple[int, ...]],
) -> tuple[tuple[int, ...], float]:
    targets: dict[int, int] = {}
    beta_errors: list[float] = []
    for row in pairs:
        positive = int(row["positive_index"])
        if positive >= count:
            continue
        negative = int(row["negative_index"])
        if positive in targets or negative >= count:
            raise ValueError(
                "reciprocal pair target is not one-to-one in nested prefix"
            )
        targets[positive] = negative
        beta_errors.append(float(row["relative_beta_error"]))
    if tuple(sorted(targets)) != tuple(range(count)):
        raise ValueError("reciprocal pair mapping does not cover nested prefix")
    negative_members: dict[int, set[int]] = {}
    for index, group_id in enumerate(negative_groups):
        negative_members.setdefault(int(group_id), set()).add(index)
    for block in positive_blocks:
        target_members = {targets[index] for index in block}
        target_groups = {int(negative_groups[index]) for index in target_members}
        if len(target_groups) != 1:
            raise ValueError(
                "positive near-degenerate block maps to multiple negative groups"
            )
        group_id = next(iter(target_groups))
        if negative_members[group_id] != target_members:
            raise ValueError(
                "reciprocal pair mapping does not preserve the complete negative group"
            )
    return tuple(targets[index] for index in range(count)), max(
        beta_errors, default=0.0
    )


def _nested_pairing_audit(
    packet: Mapping[str, Any], operators: Any, spaces: Any
) -> dict[str, Any]:
    free_local = _free_row_layout(operators)
    signs = _owned_sign(spaces, int(operators.transform.full_local_size))
    full_size = len(signs)
    trace_indices = np.asarray(spaces.transverse_to_mixed, dtype=np.int64)
    trace_indices = trace_indices[(trace_indices >= 0) & (trace_indices < full_size)]
    if len(np.unique(trace_indices)) != len(trace_indices):
        raise RuntimeError("transverse-to-mixed owner mapping contains duplicates")
    positive_selection = packet["selection"]["positive"]
    negative_selection = packet["selection"]["negative"]
    pairs = list(packet["metadata"]["reciprocal_pairing"]["pairs"])
    positive_right = packet["positive"]["right_full"]
    negative_right = packet["negative"]["right_full"]
    positive_left = packet["positive"]["left_full"]
    negative_left = packet["negative"]["left_full"]
    matrices = (operators.K0, operators.K1, operators.K2)
    frobenius_norms = tuple(
        float(matrix.norm(PETSc.NormType.FROBENIUS)) for matrix in matrices
    )
    right_residuals: list[float] = []
    left_residuals: list[float] = []
    for index, beta_plus in enumerate(positive_selection["beta"]):
        beta_partner = -complex(beta_plus)
        right = _owner_rows_to_reduced(
            operators.K0, positive_right[index], free_local, signs
        )
        left = _owner_rows_to_reduced(
            operators.K0, positive_left[index], free_local, signs
        )
        try:
            right_residuals.append(
                _polynomial_relative_residual(
                    matrices, beta_partner, right, frobenius_norms, hermitian=False
                )
            )
            left_residuals.append(
                _polynomial_relative_residual(
                    matrices,
                    np.conj(beta_partner),
                    left,
                    frobenius_norms,
                    hermitian=True,
                )
            )
        finally:
            right.destroy()
            left.destroy()

    comm = operators.K0.comm.tompi4py()
    result: dict[str, Any] = {
        "residual_tolerance": 1.0e-10,
        "trace_tolerance": 1.0e-10,
        "trace_owner_row_count": int(comm.allreduce(len(trace_indices), op=MPI.SUM)),
        "nested": {},
    }
    for count in (120, 240, 480):
        try:
            positive_blocks = _group_blocks(positive_selection["groups"], count)
            targets, beta_error = _pair_targets(
                pairs, count, negative_selection["groups"], positive_blocks
            )
            full_right_metrics: list[dict[str, float]] = []
            full_left_metrics: list[dict[str, float]] = []
            trace_right_metrics: list[dict[str, float]] = []
            trace_left_metrics: list[dict[str, float]] = []
            for block in positive_blocks:
                negative_block = tuple(targets[index] for index in block)
                right_first = (positive_right[list(block), :] * signs[None, :]).T
                right_second = negative_right[list(negative_block), :].T
                left_first = (positive_left[list(block), :] * signs[None, :]).T
                left_second = negative_left[list(negative_block), :].T
                full_right_metrics.append(
                    _subspace_metrics(right_first, right_second, comm)
                )
                full_left_metrics.append(
                    _subspace_metrics(left_first, left_second, comm)
                )
                trace_right_metrics.append(
                    _subspace_metrics(
                        right_first[trace_indices, :],
                        right_second[trace_indices, :],
                        comm,
                    )
                )
                trace_left_metrics.append(
                    _subspace_metrics(
                        left_first[trace_indices, :],
                        left_second[trace_indices, :],
                        comm,
                    )
                )

            def maximum(metrics: list[dict[str, float]]) -> dict[str, float]:
                return {
                    "metric_space": METRIC_SPACE,
                    **{
                        key: max(float(item[key]) for item in metrics)
                        for key in metrics[0]
                    },
                }

            trace_max = max(
                (
                    float(item[key])
                    for metrics in (trace_right_metrics, trace_left_metrics)
                    for item in metrics
                    for key in METRIC_KEYS
                ),
                default=0.0,
            )
            right_residual_max = max(right_residuals[:count])
            left_residual_max = max(left_residuals[:count])
            right_residual_pass = right_residual_max <= 1.0e-10
            left_residual_pass = left_residual_max <= 1.0e-10
            trace_gate_pass = trace_max <= 1.0e-10
            result["nested"][str(count)] = {
                "status": "measured",
                "group_count": len(positive_blocks),
                "pair_target_max_relative_beta_error": beta_error,
                "paired_right_residual_max": right_residual_max,
                "paired_left_residual_max": left_residual_max,
                "paired_right_residual_pass": right_residual_pass,
                "paired_left_residual_pass": left_residual_pass,
                "paired_residual_pass": right_residual_pass and left_residual_pass,
                "full_right": maximum(full_right_metrics),
                "full_left": maximum(full_left_metrics),
                "trace_right": maximum(trace_right_metrics),
                "trace_left": maximum(trace_left_metrics),
                "trace_gate_pass": trace_gate_pass,
                "pairing_trace_pass": (
                    right_residual_pass and left_residual_pass and trace_gate_pass
                ),
            }
        except (RuntimeError, ValueError) as error:
            result["nested"][str(count)] = {
                "status": "NOT_ESTABLISHED",
                "reason": str(error),
            }
    measured = [
        entry for entry in result["nested"].values() if entry["status"] == "measured"
    ]
    if len(measured) != 3:
        result["pairing_trace_summary"] = {
            "status": "NOT_ESTABLISHED",
            "pass": None,
            "per_M": {
                count: result["nested"].get(str(count), {}).get("pairing_trace_pass")
                for count in (120, 240, 480)
            },
        }
    else:
        nested_pass = all(entry["pairing_trace_pass"] for entry in measured)
        result["pairing_trace_summary"] = {
            "status": "pass" if nested_pass else "failed",
            "pass": nested_pass,
            "per_M": {
                count: result["nested"][str(count)]["pairing_trace_pass"]
                for count in (120, 240, 480)
            },
        }
    return result


def run_component(args: argparse.Namespace) -> dict[str, Any] | None:
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise RuntimeError(f"Q-B h4 component requires MPI8, got {comm.size}")
    source_provenance = _source_provenance(comm, args.audit_source_sha)
    input_path = Path(args.input).resolve()
    manifest_path = Path(args.packet_manifest).resolve()
    identity_path = Path(args.identity_json).resolve()
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    validate_v4_h4_specification(specification)
    identity = json.loads(identity_path.read_text())
    _validate_shared_h4_mode_identity(identity, payload)
    markers: list[str] = []

    def log(message: str) -> None:
        markers.append(str(message))
        print(f"rank={comm.rank} {message}", flush=True)

    started = time.perf_counter()
    log("ENTER_PACKET_OWNER_SHARD")
    packet = load_selected_mode_packet(
        manifest_path,
        identity=identity,
        expected_manifest_sha256=args.expected_manifest_sha,
        scope="task039_v4_h4_m480",
        comm=comm,
    )
    actual_manifest_sha = packet["manifest_sha256"]
    log("AFTER_PACKET_OWNER_SHARD")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("mode_count") != 480 or manifest.get("rank_count") != 8:
        raise RuntimeError("Q-B component requires the shared h4/M480 packet")
    shards = list(manifest.get("shards", ()))
    packet_authority = _packet_authority(manifest, shards)
    cfg = simulation_config_3d_from_normalized(payload)
    log("ENTER_MESH")
    cross_section = build_matching_cross_section(cfg, "stage4_xy", comm=comm)
    log("AFTER_MESH")
    spaces = build_cross_section_spaces(cross_section, transverse_degree=6)
    log("AFTER_SPACES")
    operators = None
    try:
        operators = assemble_quadratic_beta_operators(
            cfg, cross_section, spaces, log=log
        )
        log("AFTER_QEP_OPERATOR_ASSEMBLY")
        operator_range = tuple(
            int(value) for value in operators.transform.matrix.getOwnershipRange()
        )
        if tuple(packet["ownership_range"]) != operator_range:
            raise RuntimeError(
                "selected-mode packet ownership does not match the assembled "
                "mixed-space owner rows"
            )
        parity = _operator_parity_audit(operators, spaces)
        log("AFTER_QEP_PARITY_AUDIT")
        nested_pairing = _nested_pairing_audit(packet, operators, spaces)
        log("AFTER_PACKET_PAIRED_RESIDUAL_AND_TRACE_AUDIT")
        rank_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        elapsed = comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        rss_max = comm.allreduce(rank_rss, op=MPI.MAX)
        parity_status = "pass" if parity["pass"] else "failed"
        pairing_trace_status = nested_pairing["pairing_trace_summary"]["status"].lower()
        result = {
            "schema": "task039.v4-9-q-b-component.v1",
            "status": (
                "sampled_operator_action_parity_"
                f"{parity_status}_pairing_trace_{pairing_trace_status}_"
                "traction_observables_not_established"
            ),
            "provenance": {
                **source_provenance,
                "packet_source_sha": identity.get("source_sha"),
                "argv": list(sys.argv),
            },
            "inputs": {
                "input": {
                    "path": str(input_path),
                    "sha256": specification.input_sha256,
                },
                "manifest": {"path": str(manifest_path), "sha256": actual_manifest_sha},
                "identity": {
                    "path": str(identity_path),
                    "sha256": _sha256(identity_path),
                },
            },
            "operator_authority": {
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "constraints": {
                    "transverse_count": operators.constraints.transverse_constraint_count,
                    "longitudinal_count": operators.constraints.longitudinal_constraint_count,
                    "phase_x": [
                        float(operators.constraints.phase_x.real),
                        float(operators.constraints.phase_x.imag),
                    ],
                    "phase_y": [
                        float(operators.constraints.phase_y.real),
                        float(operators.constraints.phase_y.imag),
                    ],
                },
            },
            "exact_transform": {
                "formula": "Q(beta)=K0+beta*K1+beta^2*K2; S=diag(+I_Et,-I_Ez); S Q(beta) S=Q(-beta)",
                "left_right": "left_partner=S*left, right_partner=S*right",
                "additional_conjugation": False,
                "parity": parity,
            },
            "numerical_pairing": {
                "status": (
                    "measured_operator_sign_partner"
                    if nested_pairing["pairing_trace_summary"]["status"]
                    != "NOT_ESTABLISHED"
                    else "NOT_ESTABLISHED"
                ),
                **nested_pairing,
                "available_packet_authority": {
                    "mode_count": manifest.get("mode_count"),
                    **packet_authority,
                },
                "formal_gate": "NOT_ESTABLISHED_observables_not_run",
            },
            "qualification": {
                "status": "NOT_ESTABLISHED",
                "pass": False,
                "operator_parity_pass": bool(parity["pass"]),
                "pairing_trace_pass": nested_pairing["pairing_trace_summary"]["pass"],
                "traction_status": "NOT_ESTABLISHED",
                "observables_status": "NOT_ESTABLISHED",
            },
            "trace_traction": {
                "status": "measured_trace_owner_row_subspace",
                "mapping_source": "spaces.transverse_to_mixed owner rows",
                "gate": "max principal-angle/projector/reconstruction <= 1e-10",
                "target": 1.0e-10,
                "traction": {
                    "status": "NOT_ESTABLISHED",
                    "source_contract": {
                        "source": "src/coupling/hybrid_internal_modes.py::_ReusableModeTractionEvaluator",
                        "formula": "t=(sign*(i*beta*Et_x-Ez_x), sign*(-Ez_y+i*beta*Et_y))",
                        "transform": "Et_partner=Et, Ez_partner=-Ez, beta_partner=-beta",
                        "result": "traction_partner=-traction",
                        "additional_conjugation": False,
                    },
                    "reason": "traction is not persisted and this component does not reconstruct all 480 traction columns",
                },
            },
            "observables": {
                "status": "NOT_ESTABLISHED",
                "reason": "No reduced solve, trace/traction reconstruction, or field authority was run in this component.",
                "target": 1.0e-8,
            },
            "resources": {
                "rank_historical_ru_maxrss_mib": float(rss_max),
                "process_tree_peak_rss_mib": "not_measured",
                "swap": "not_measured",
                "elapsed_seconds_max_rank": float(elapsed),
            },
            "markers": markers,
        }
    finally:
        if operators is not None:
            operators.destroy()
        del operators, spaces, cross_section
        gc.collect()
    comm.barrier()
    print(f"rank={comm.rank} RELEASED", flush=True)
    if comm.rank == 0:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--packet-manifest", type=Path, required=True)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-source-sha", required=True)
    result = run_component(parser.parse_args())
    return 0 if result is None or result["exact_transform"]["parity"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
